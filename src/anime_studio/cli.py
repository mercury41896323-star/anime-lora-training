from __future__ import annotations

import argparse
import json
from pathlib import Path

from .asset_inventory import collect_asset_inventory
from .asset_library import collect_asset_library, write_asset_library_index
from .character_manager import register_character_asset
from .character_profile import confirm_character_source_rights, create_character_profile
from .comfyui_queue import (
    DEFAULT_COMFYUI_BASE_URL,
    enqueue_comfyui_workflow,
    list_comfyui_jobs,
    refresh_comfyui_job,
    refresh_submitted_comfyui_jobs,
    submit_comfyui_job,
)
from .comfyui_results import import_comfyui_results
from .comfyui_workflow_export import export_comfyui_workflow, list_comfyui_templates
from .dataset_builder import build_lora_dataset, build_motion_dataset
from .edit_export import export_edit_timeline
from .edit_preview import build_preview_movie
from .frame_extraction import build_frame_extraction_plan, extract_frames
from .kohya_config import KohyaLowVramSettings, generate_kohya_low_vram_config
from .lora_manifest import generate_lora_manifest
from .lora_registry import list_lora_artifacts, register_lora_result
from .settings import load_settings
from .studio_status import build_studio_status, open_studio_dashboard
from .storyboard import add_shot, create_storyboard, list_storyboard_shots
from .storyboard_comfyui import export_storyboard_comfyui_workflows
from .storyboard_editor import write_storyboard_editor
from .storyboard_editor_manifest import export_selected_shot_manifest
from .storyboard_results import (
    link_comfyui_results_to_storyboard,
    link_shot_result,
    list_shot_results,
)
from .storyboard_review import set_shot_result_decision, write_storyboard_preview
from .tagger import finalize_tag_sidecars, generate_auto_tag_records, update_manual_tags
from .timeline_revision import adopt_timeline_revision, review_timeline_revisions
from .training_readiness import check_training_readiness, run_training_smoke


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="anime-studio",
        description="Small local tools for the AI Anime Studio prototype.",
    )
    parser.add_argument(
        "--config",
        default="config/local_6gb.json",
        help="Path to the local runtime profile.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)
    inventory = subparsers.add_parser(
        "inventory",
        help="Scan raw assets and write a lightweight inventory JSON.",
    )
    inventory.add_argument(
        "--output",
        default="assets/processed/inventory.json",
        help="Where to write the generated inventory JSON.",
    )
    inventory.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON output.",
    )

    library = subparsers.add_parser(
        "library",
        help="Browse and export the lightweight Asset Library.",
    )
    library_subparsers = library.add_subparsers(dest="library_command", required=True)
    library_list = library_subparsers.add_parser(
        "list",
        help="List CharacterProfile assets across the project.",
    )
    add_asset_library_filters(library_list)
    library_list.add_argument(
        "--json",
        action="store_true",
        help="Print full JSON records.",
    )
    library_index = library_subparsers.add_parser(
        "index",
        help="Write a reusable Asset Library index JSON.",
    )
    add_asset_library_filters(library_index)
    library_index.add_argument(
        "--output",
        default="assets/processed/library_index.json",
        help="Output index JSON path.",
    )

    character = subparsers.add_parser(
        "character",
        help="Create and manage lightweight character metadata.",
    )
    character_subparsers = character.add_subparsers(dest="character_command", required=True)
    character_init = character_subparsers.add_parser(
        "init",
        help="Create a CharacterProfile JSON file.",
    )
    character_init.add_argument("--id", required=True, help="Stable character id.")
    character_init.add_argument("--name", required=True, help="Human-readable character name.")
    character_init.add_argument(
        "--trigger-tag",
        action="append",
        default=None,
        help="Training or generation trigger tag. Can be passed more than once.",
    )
    character_register = character_subparsers.add_parser(
        "register-asset",
        help="Register an image or video under a character workspace.",
    )
    character_register.add_argument("--id", required=True, help="Stable character id.")
    character_register.add_argument("--source", required=True, help="Source asset path.")
    character_rights = character_subparsers.add_parser(
        "confirm-source-rights",
        help="Record explicit permission to use character sources for training.",
    )
    character_rights.add_argument("--id", required=True, help="Character id.")
    character_rights.add_argument("--reviewer", required=True, help="Person confirming the source rights.")
    character_rights.add_argument("--notes", default="", help="Optional permission or license notes.")
    character_rights.add_argument(
        "--confirm",
        action="store_true",
        required=True,
        help="Required explicit confirmation flag.",
    )

    storyboard = subparsers.add_parser(
        "storyboard",
        help="Create lightweight storyboards and shot lists.",
    )
    storyboard_subparsers = storyboard.add_subparsers(dest="storyboard_command", required=True)
    storyboard_init = storyboard_subparsers.add_parser(
        "init",
        help="Create a storyboard JSON file.",
    )
    storyboard_init.add_argument("--id", required=True, help="Stable story id.")
    storyboard_init.add_argument("--title", required=True, help="Storyboard title.")
    storyboard_add_shot = storyboard_subparsers.add_parser(
        "add-shot",
        help="Append a shot to a storyboard.",
    )
    storyboard_add_shot.add_argument("--story-id", required=True, help="Storyboard id.")
    storyboard_add_shot.add_argument("--shot-id", required=True, help="Stable shot id.")
    storyboard_add_shot.add_argument("--title", required=True, help="Shot title.")
    storyboard_add_shot.add_argument("--character-id", default="", help="Optional character id.")
    storyboard_add_shot.add_argument("--prompt", default="", help="Draft generation prompt.")
    storyboard_add_shot.add_argument("--negative-prompt", default="", help="Shot-specific negative prompt.")
    storyboard_add_shot.add_argument(
        "--duration",
        type=float,
        default=3.0,
        help="Shot duration in seconds.",
    )
    storyboard_add_shot.add_argument("--camera", default="", help="Camera note.")
    storyboard_add_shot.add_argument("--lighting", default="", help="Lighting note.")
    storyboard_add_shot.add_argument("--seed", type=int, default=None, help="Optional fixed generation seed.")
    storyboard_add_shot.add_argument("--width", type=int, default=None, help="Optional generated image width.")
    storyboard_add_shot.add_argument("--height", type=int, default=None, help="Optional generated image height.")
    storyboard_add_shot.add_argument("--steps", type=int, default=None, help="Optional sampler steps.")
    storyboard_add_shot.add_argument("--notes", default="", help="Shot notes.")
    storyboard_list = storyboard_subparsers.add_parser(
        "list",
        help="List shots in a storyboard.",
    )
    storyboard_list.add_argument("--story-id", required=True, help="Storyboard id.")
    storyboard_list.add_argument(
        "--json",
        action="store_true",
        help="Print full JSON records.",
    )
    storyboard_export_comfyui = storyboard_subparsers.add_parser(
        "export-comfyui",
        help="Export one ComfyUI workflow per storyboard shot.",
    )
    storyboard_export_comfyui.add_argument("--story-id", required=True, help="Storyboard id.")
    storyboard_export_comfyui.add_argument(
        "--template",
        default=None,
        help="ComfyUI workflow template JSON.",
    )
    storyboard_export_comfyui.add_argument(
        "--output-dir",
        default=None,
        help="Output directory. Defaults to outputs/comfyui/storyboards/<story-id>.",
    )
    storyboard_export_comfyui.add_argument(
        "--lora-index",
        type=int,
        default=0,
        help="Index of the LoRA entry to inject from each character manifest.",
    )
    storyboard_export_comfyui.add_argument(
        "--queue",
        action="store_true",
        help="Also add exported workflows to the local ComfyUI queue.",
    )
    storyboard_export_comfyui.add_argument(
        "--base-url",
        default=DEFAULT_COMFYUI_BASE_URL,
        help="ComfyUI server URL used when --queue is set.",
    )
    storyboard_export_comfyui.add_argument(
        "--queue-path",
        default=None,
        help="Queue JSON path. Defaults to queues/comfyui/jobs.json.",
    )
    storyboard_export_comfyui.add_argument(
        "--b-control",
        action="store_true",
        help="Export workflows in B-control mode with structured pose, face-direction, camera, and lighting hints.",
    )
    storyboard_link_result = storyboard_subparsers.add_parser(
        "link-result",
        help="Link a generated asset to a storyboard shot.",
    )
    storyboard_link_result.add_argument("--story-id", required=True, help="Storyboard id.")
    storyboard_link_result.add_argument("--shot-id", required=True, help="Shot id.")
    storyboard_link_result.add_argument("--result", required=True, help="Generated result path.")
    storyboard_link_result.add_argument("--kind", default="image", help="Result kind.")
    storyboard_link_result.add_argument("--source", default="manual", help="Result source.")
    storyboard_link_result.add_argument(
        "--source-reference",
        default="",
        help="Original source reference, such as a ComfyUI output reference.",
    )
    storyboard_link_comfyui = storyboard_subparsers.add_parser(
        "link-comfyui-results",
        help="Link imported ComfyUI results to the storyboard shot stored in workflow metadata.",
    )
    storyboard_link_comfyui.add_argument("--job-id", required=True, help="ComfyUI queue job id.")
    storyboard_link_comfyui.add_argument(
        "--queue",
        default=None,
        help="Queue JSON path. Defaults to queues/comfyui/jobs.json.",
    )
    storyboard_link_comfyui.add_argument(
        "--results-manifest",
        default=None,
        help="Imported ComfyUI results manifest. Defaults to the CharacterProfile generated folder.",
    )
    storyboard_results = storyboard_subparsers.add_parser(
        "results",
        help="List generated results linked to storyboard shots.",
    )
    storyboard_results.add_argument("--story-id", required=True, help="Storyboard id.")
    storyboard_results.add_argument("--shot-id", default=None, help="Optional shot id filter.")
    storyboard_results.add_argument(
        "--json",
        action="store_true",
        help="Print full JSON records.",
    )
    storyboard_decide = storyboard_subparsers.add_parser(
        "decide-result",
        help="Mark a linked shot result as candidate, selected, or rejected.",
    )
    storyboard_decide.add_argument("--story-id", required=True, help="Storyboard id.")
    storyboard_decide.add_argument("--result-id", required=True, help="Shot result id.")
    storyboard_decide.add_argument(
        "--decision",
        required=True,
        choices=["candidate", "selected", "rejected"],
        help="Decision state for the result.",
    )
    storyboard_decide.add_argument("--notes", default="", help="Decision notes.")
    storyboard_preview = storyboard_subparsers.add_parser(
        "preview",
        help="Write a lightweight HTML preview for storyboard results.",
    )
    storyboard_preview.add_argument("--story-id", required=True, help="Storyboard id.")
    storyboard_preview.add_argument("--output", default=None, help="Preview HTML output path.")
    storyboard_export_selected = storyboard_subparsers.add_parser(
        "export-selected",
        help="Export selected shot results for Unity and editing tools.",
    )
    storyboard_export_selected.add_argument("--story-id", required=True, help="Storyboard id.")
    storyboard_export_selected.add_argument("--output", default=None, help="Selected shot manifest output path.")
    storyboard_editor = storyboard_subparsers.add_parser(
        "editor",
        help="Write a lightweight HTML ShotEditor for a storyboard.",
    )
    storyboard_editor.add_argument("--story-id", required=True, help="Storyboard id.")
    storyboard_editor.add_argument("--output", default=None, help="Editor HTML output path.")

    frames = subparsers.add_parser(
        "frames",
        help="Prepare or run lightweight video frame extraction.",
    )
    frames.add_argument("--video", required=True, help="Source video path.")
    frames.add_argument("--character-id", required=True, help="Character id for output grouping.")
    frames.add_argument("--fps", type=float, default=1.0, help="Frames per second to extract.")
    frames.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the ffmpeg command without running it.",
    )

    tags = subparsers.add_parser(
        "tags",
        help="Generate, edit, and finalize character image tags.",
    )
    tag_subparsers = tags.add_subparsers(dest="tag_command", required=True)
    tags_auto = tag_subparsers.add_parser(
        "auto",
        help="Generate editable auto tag records.",
    )
    tags_auto.add_argument("--character-id", required=True, help="Character id to tag.")
    tags_auto.add_argument(
        "--provider",
        default="baseline",
        help="Auto tag provider name. Current lightweight provider is baseline.",
    )
    tags_auto.add_argument(
        "--extra-tag",
        action="append",
        default=None,
        help="Additional auto tag. Can be passed more than once.",
    )
    tags_auto.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing auto tag records while preserving manual edits.",
    )
    tags_manual = tag_subparsers.add_parser(
        "manual",
        help="Add manual tags or reject unwanted tags.",
    )
    tags_manual.add_argument("--character-id", required=True, help="Character id to edit.")
    tags_manual.add_argument(
        "--add-tag",
        action="append",
        default=None,
        help="Manual tag to add. Can be passed more than once.",
    )
    tags_manual.add_argument(
        "--reject-tag",
        action="append",
        default=None,
        help="Tag to exclude from final captions. Can be passed more than once.",
    )
    tags_finalize = tag_subparsers.add_parser(
        "finalize",
        help="Write final .txt captions from tag records.",
    )
    tags_finalize.add_argument("--character-id", required=True, help="Character id to finalize.")
    tags_finalize.add_argument(
        "--no-overwrite",
        action="store_true",
        help="Keep existing .txt captions.",
    )

    dataset = subparsers.add_parser(
        "dataset",
        help="Build lightweight training datasets.",
    )
    dataset_subparsers = dataset.add_subparsers(dest="dataset_command", required=True)
    dataset_lora = dataset_subparsers.add_parser(
        "build-lora",
        help="Build a LoRA image/caption dataset for one character.",
    )
    dataset_lora.add_argument("--character-id", required=True, help="Character id to export.")
    dataset_motion = dataset_subparsers.add_parser(
        "build-motion",
        help="Build a motion dataset from selected storyboard shots, Phase 6 motion cues, and B-control hints.",
    )
    dataset_motion.add_argument("--story-id", required=True, help="Storyboard id to export.")
    dataset_motion.add_argument(
        "--output-dir",
        default=None,
        help="Motion dataset directory. Defaults to datasets/motion/<story-id>.",
    )
    dataset_motion.add_argument(
        "--manifest",
        default=None,
        help="Manifest output path. Defaults to manifests/storyboards/<story-id>/motion_dataset_manifest.json.",
    )

    lora = subparsers.add_parser(
        "lora",
        help="Prepare low-VRAM LoRA training configs.",
    )
    lora_subparsers = lora.add_subparsers(dest="lora_command", required=True)
    kohya = lora_subparsers.add_parser(
        "kohya-config",
        help="Generate Kohya/sd-scripts config files for low-VRAM LoRA training.",
    )
    kohya.add_argument("--character-id", required=True, help="Character id to train.")
    kohya.add_argument(
        "--pretrained-model",
        required=True,
        help="Path or Hugging Face model id for the SD base model.",
    )
    kohya.add_argument(
        "--kohya-root",
        default=".",
        help="Path to the sd-scripts or Kohya scripts directory.",
    )
    kohya.add_argument("--resolution", type=int, default=512, help="Training resolution.")
    kohya.add_argument("--repeats", type=int, default=10, help="Dataset repeats.")
    kohya.add_argument("--epochs", type=int, default=10, help="Max train epochs.")
    kohya.add_argument("--network-dim", type=int, default=16, help="LoRA rank.")
    kohya.add_argument("--network-alpha", type=int, default=8, help="LoRA alpha.")
    kohya.add_argument("--learning-rate", default="1e-4", help="Learning rate.")
    kohya.add_argument(
        "--dataset-dir",
        default=None,
        help="Optional reviewed dataset directory. Defaults to datasets/lora/<character-id>.",
    )
    kohya.add_argument(
        "--require-2p5d",
        action="store_true",
        help="Require a ready Character 2.5D Definition before writing training files.",
    )
    lora_register = lora_subparsers.add_parser(
        "register-result",
        help="Link a trained LoRA model file to a CharacterProfile.",
    )
    lora_register.add_argument("--character-id", required=True, help="Character id to update.")
    lora_register.add_argument("--model-path", required=True, help="Trained LoRA model path.")
    lora_register.add_argument(
        "--source-config-dir",
        default=None,
        help="Kohya config directory used for this training run.",
    )
    lora_register.add_argument("--name", default=None, help="Display name for this LoRA result.")
    lora_register.add_argument("--notes", default="", help="Short training notes.")
    lora_register.add_argument("--status", default="trained", help="Result status.")
    lora_list = lora_subparsers.add_parser(
        "list",
        help="List LoRA configs and results linked to a CharacterProfile.",
    )
    lora_list.add_argument("--character-id", required=True, help="Character id to inspect.")
    lora_manifest = lora_subparsers.add_parser(
        "manifest",
        help="Generate a lightweight LoRA manifest for ComfyUI and Unity.",
    )
    lora_manifest.add_argument("--character-id", required=True, help="Character id to export.")
    lora_manifest.add_argument(
        "--output",
        default=None,
        help="Manifest output path. Defaults to manifests/characters/<id>/lora_manifest.json.",
    )
    lora_manifest.add_argument(
        "--weight",
        type=float,
        default=0.75,
        help="Default LoRA and CLIP weight for downstream tools.",
    )

    comfyui = subparsers.add_parser(
        "comfyui",
        help="Export ComfyUI workflow files from project metadata.",
    )
    comfyui_subparsers = comfyui.add_subparsers(dest="comfyui_command", required=True)
    comfyui_subparsers.add_parser(
        "list-templates",
        help="List bundled ComfyUI workflow templates.",
    )
    comfyui_export = comfyui_subparsers.add_parser(
        "export-workflow",
        help="Inject a registered LoRA into a ComfyUI workflow template.",
    )
    comfyui_export.add_argument("--character-id", required=True, help="Character id to export.")
    comfyui_export.add_argument(
        "--template",
        default=None,
        help="ComfyUI workflow template JSON. Defaults to the bundled SD1.5 LoRA draft template.",
    )
    comfyui_export.add_argument(
        "--output",
        default=None,
        help="Output workflow path. Defaults to outputs/comfyui/<id>/<template>_with_lora.json.",
    )
    comfyui_export.add_argument(
        "--manifest",
        default=None,
        help="LoRA manifest path. Defaults to manifests/characters/<id>/lora_manifest.json.",
    )
    comfyui_export.add_argument(
        "--lora-index",
        type=int,
        default=0,
        help="Index of the LoRA entry to inject from the manifest.",
    )
    comfyui_queue_add = comfyui_subparsers.add_parser(
        "queue-add",
        help="Add an exported workflow to the local ComfyUI submission queue.",
    )
    comfyui_queue_add.add_argument("--workflow", required=True, help="Exported workflow JSON.")
    comfyui_queue_add.add_argument(
        "--base-url",
        default=DEFAULT_COMFYUI_BASE_URL,
        help="ComfyUI server URL.",
    )
    comfyui_queue_add.add_argument(
        "--queue",
        default=None,
        help="Queue JSON path. Defaults to queues/comfyui/jobs.json.",
    )
    comfyui_queue_submit = comfyui_subparsers.add_parser(
        "queue-submit",
        help="Submit a queued or exported workflow to the ComfyUI API.",
    )
    comfyui_queue_submit.add_argument("--job-id", default=None, help="Queued job id.")
    comfyui_queue_submit.add_argument(
        "--workflow",
        default=None,
        help="Workflow JSON to enqueue and submit in one step.",
    )
    comfyui_queue_submit.add_argument(
        "--base-url",
        default=None,
        help="ComfyUI server URL. Defaults to the job URL or local ComfyUI.",
    )
    comfyui_queue_submit.add_argument(
        "--queue",
        default=None,
        help="Queue JSON path. Defaults to queues/comfyui/jobs.json.",
    )
    comfyui_queue_submit.add_argument(
        "--dry-run",
        action="store_true",
        help="Record the payload without calling ComfyUI.",
    )
    comfyui_queue_submit.add_argument(
        "--timeout",
        type=float,
        default=15.0,
        help="HTTP timeout in seconds.",
    )
    comfyui_queue_list = comfyui_subparsers.add_parser(
        "queue-list",
        help="List local ComfyUI queue jobs.",
    )
    comfyui_queue_list.add_argument(
        "--queue",
        default=None,
        help="Queue JSON path. Defaults to queues/comfyui/jobs.json.",
    )
    comfyui_queue_refresh = comfyui_subparsers.add_parser(
        "queue-refresh",
        help="Refresh one submitted job from ComfyUI history.",
    )
    comfyui_queue_refresh.add_argument("--job-id", required=True, help="Queued job id.")
    comfyui_queue_refresh.add_argument(
        "--queue",
        default=None,
        help="Queue JSON path. Defaults to queues/comfyui/jobs.json.",
    )
    comfyui_queue_refresh.add_argument(
        "--timeout",
        type=float,
        default=15.0,
        help="HTTP timeout in seconds.",
    )
    comfyui_queue_refresh_all = comfyui_subparsers.add_parser(
        "queue-refresh-all",
        help="Refresh every submitted job from ComfyUI history.",
    )
    comfyui_queue_refresh_all.add_argument(
        "--queue",
        default=None,
        help="Queue JSON path. Defaults to queues/comfyui/jobs.json.",
    )
    comfyui_queue_refresh_all.add_argument(
        "--timeout",
        type=float,
        default=15.0,
        help="HTTP timeout in seconds per job.",
    )
    comfyui_import_results = comfyui_subparsers.add_parser(
        "import-results",
        help="Import generated ComfyUI image outputs into a CharacterProfile asset folder.",
    )
    comfyui_import_results.add_argument("--character-id", required=True, help="Character id.")
    comfyui_import_results.add_argument("--job-id", required=True, help="Queued job id.")
    comfyui_import_results.add_argument(
        "--comfyui-output-dir",
        required=True,
        help="ComfyUI output directory that contains generated image files.",
    )
    comfyui_import_results.add_argument(
        "--queue",
        default=None,
        help="Queue JSON path. Defaults to queues/comfyui/jobs.json.",
    )
    comfyui_import_results.add_argument(
        "--metadata-only",
        action="store_true",
        help="Record ComfyUI output references without copying files.",
    )

    edit = subparsers.add_parser(
        "edit",
        help="Finalize Phase 7 edit outputs and Unity Timeline handoffs.",
    )
    edit_subparsers = edit.add_subparsers(dest="edit_command", required=True)
    edit_export = edit_subparsers.add_parser(
        "export",
        help="Export edit_timeline_manifest.json to FFmpeg concat, EDL, and FCPXML.",
    )
    edit_export.add_argument("--story-id", required=True, help="Storyboard id.")
    edit_export.add_argument("--manifest", default=None, help="Optional edit_timeline_manifest.json path.")
    edit_export.add_argument("--output-dir", default=None, help="Optional export output directory.")
    edit_export.add_argument("--formats", default="ffmpeg,edl,fcpxml", help="Comma-separated formats.")
    edit_preview = edit_subparsers.add_parser(
        "preview-movie",
        help="Write or run an FFmpeg preview movie command.",
    )
    edit_preview.add_argument("--story-id", required=True, help="Storyboard id.")
    edit_preview.add_argument("--manifest", default=None, help="Optional edit_timeline_manifest.json path.")
    edit_preview.add_argument("--output", default=None, help="Preview movie output path.")
    edit_preview.add_argument("--ffmpeg", default="ffmpeg", help="FFmpeg executable path.")
    edit_preview.add_argument("--run", action="store_true", help="Run FFmpeg instead of only writing the plan.")
    edit_preview.add_argument("--no-overwrite", action="store_true", help="Do not overwrite existing preview movie.")
    edit_review = edit_subparsers.add_parser(
        "revision-review",
        help="Review Unity Timeline revision folders.",
    )
    edit_review.add_argument("--story-id", required=True, help="Storyboard id.")
    edit_review.add_argument("--timeline-root", default=None, help="Optional Unity Timeline root folder.")
    edit_review.add_argument("--edit-manifest", default=None, help="Optional edit_timeline_manifest.json path.")
    edit_review.add_argument("--output", default=None, help="Optional review manifest path.")
    edit_adopt = edit_subparsers.add_parser(
        "revision-adopt",
        help="Adopt a reviewed Unity Timeline revision.",
    )
    edit_adopt.add_argument("--story-id", required=True, help="Storyboard id.")
    edit_adopt.add_argument("--revision-id", default=None, help="Revision id. Defaults to recommended revision.")
    edit_adopt.add_argument("--review", default=None, help="Optional review manifest path.")
    edit_adopt.add_argument("--output", default=None, help="Optional selected revision manifest path.")

    training = subparsers.add_parser(
        "training",
        help="Check and prepare local LoRA training readiness.",
    )
    training_subparsers = training.add_subparsers(dest="training_command", required=True)
    training_ready = training_subparsers.add_parser(
        "readiness",
        help="Check whether a character is ready for local LoRA training.",
    )
    training_ready.add_argument("--character-id", required=True, help="Character id.")
    training_ready.add_argument("--min-images", type=int, default=20, help="Minimum recommended image count.")
    training_ready.add_argument("--output", default=None, help="Optional readiness manifest path.")
    training_ready.add_argument("--dataset-dir", default=None, help="Optional reviewed dataset directory.")
    training_ready.add_argument("--require-2p5d", action="store_true", help="Require a ready 2.5D Definition.")
    training_smoke = training_subparsers.add_parser(
        "smoke",
        help="Run dataset -> Kohya config -> readiness without launching training.",
    )
    training_smoke.add_argument("--character-id", required=True, help="Character id.")
    training_smoke.add_argument("--pretrained-model", required=True, help="SD base model path or id for generated config.")
    training_smoke.add_argument("--kohya-root", default=".", help="Kohya/sd-scripts root path.")
    training_smoke.add_argument("--min-images", type=int, default=1, help="Minimum image count for smoke readiness.")
    training_smoke.add_argument("--provider", default="baseline", help="Tag provider for smoke auto tags.")
    training_smoke.add_argument("--output", default=None, help="Optional smoke manifest path.")
    status = subparsers.add_parser(
        "status",
        help="Build a system, character, and production readiness dashboard.",
    )
    status.add_argument("--output-dir", default=None, help="Dashboard output directory.")
    status.add_argument("--comfyui-url", default="http://127.0.0.1:8188", help="ComfyUI API base URL.")
    status.add_argument("--no-live", action="store_true", help="Skip live GPU and ComfyUI probes.")
    status.add_argument("--open", action="store_true", help="Open the generated dashboard in the default browser.")
    return parser


def add_asset_library_filters(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--character-id", default=None, help="Filter by character id.")
    parser.add_argument("--kind", default=None, help="Filter by asset kind.")
    parser.add_argument("--source", default=None, help="Filter by asset source.")
    parser.add_argument("--query", default=None, help="Search text across asset fields.")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    settings = load_settings(args.config)

    if args.command == "status":
        result = build_studio_status(
            settings=settings,
            output_dir=args.output_dir,
            comfyui_url=args.comfyui_url,
            probe_live=not args.no_live,
        )
        print(f"Status JSON: {result.json_path}")
        print(f"Status dashboard: {result.html_path}")
        print(f"Overall: {result.overall_status}")
        print(f"Blocking: {result.blocking_count}")
        print(f"Warnings: {result.warning_count}")
        if args.open:
            open_studio_dashboard(result.html_path)
        return 1 if result.blocking_count else 0

    if args.command == "inventory":
        inventory = collect_asset_inventory(settings)
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(
                inventory,
                ensure_ascii=False,
                indent=2 if args.pretty else None,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"Wrote inventory: {output_path}")
        print(
            "Assets: "
            f"{inventory['counts']['image']} images, "
            f"{inventory['counts']['video']} videos, "
            f"{inventory['counts']['other']} other"
        )
        return 0

    if args.command == "library" and args.library_command == "list":
        items = collect_asset_library(
            settings=settings,
            character_id=args.character_id,
            kind=args.kind,
            source=args.source,
            query=args.query,
        )
        if args.json:
            print(json.dumps([item.__dict__ for item in items], ensure_ascii=False, indent=2))
            return 0
        if not items:
            print("No library assets found.")
            return 0
        for item in items:
            status = "ok" if item.exists else "missing"
            print(f"{item.character_id}: {item.kind} / {item.source} / {status} / {item.stored_path}")
        return 0

    if args.command == "library" and args.library_command == "index":
        output_path = write_asset_library_index(
            settings=settings,
            output_path=args.output,
            character_id=args.character_id,
            kind=args.kind,
            source=args.source,
            query=args.query,
        )
        print(f"Wrote Asset Library index: {output_path}")
        return 0

    if args.command == "character" and args.character_command == "init":
        profile_path = create_character_profile(
            settings=settings,
            character_id=args.id,
            display_name=args.name,
            trigger_tags=args.trigger_tag,
        )
        print(f"Wrote character profile: {profile_path}")
        return 0

    if args.command == "character" and args.character_command == "register-asset":
        asset = register_character_asset(
            settings=settings,
            character_id=args.id,
            source_path=args.source,
        )
        print(f"Registered {asset.kind} asset: {asset.stored_path}")
        return 0

    if args.command == "character" and args.character_command == "confirm-source-rights":
        profile_path = confirm_character_source_rights(
            settings=settings,
            character_id=args.id,
            reviewer=args.reviewer,
            notes=args.notes,
        )
        print(f"Confirmed source rights: {profile_path}")
        return 0

    if args.command == "storyboard" and args.storyboard_command == "init":
        storyboard_path = create_storyboard(
            settings=settings,
            story_id=args.id,
            title=args.title,
        )
        print(f"Wrote storyboard: {storyboard_path}")
        return 0

    if args.command == "storyboard" and args.storyboard_command == "add-shot":
        storyboard_path = add_shot(
            settings=settings,
            story_id=args.story_id,
            shot_id=args.shot_id,
            title=args.title,
            character_id=args.character_id,
            prompt=args.prompt,
            negative_prompt=args.negative_prompt,
            duration_seconds=args.duration,
            camera=args.camera,
            lighting=args.lighting,
            seed=args.seed,
            width=args.width,
            height=args.height,
            steps=args.steps,
            notes=args.notes,
        )
        print(f"Updated storyboard: {storyboard_path}")
        return 0

    if args.command == "storyboard" and args.storyboard_command == "list":
        shots = list_storyboard_shots(settings=settings, story_id=args.story_id)
        if args.json:
            print(json.dumps([shot.__dict__ for shot in shots], ensure_ascii=False, indent=2))
            return 0
        if not shots:
            print("No storyboard shots.")
            return 0
        for shot in shots:
            print(f"{shot.order}. {shot.shot_id}: {shot.title} / {shot.character_id} / {shot.duration_seconds}s")
        return 0

    if args.command == "storyboard" and args.storyboard_command == "export-comfyui":
        result = export_storyboard_comfyui_workflows(
            settings=settings,
            story_id=args.story_id,
            template_path=args.template,
            output_dir=args.output_dir,
            lora_index=args.lora_index,
            enqueue=args.queue,
            base_url=args.base_url,
            queue_path=args.queue_path,
            b_control=args.b_control,
        )
        print(f"Wrote storyboard ComfyUI manifest: {result.manifest_path}")
        print(f"Workflows: {len(result.workflows)}")
        print(f"Skipped shots: {len(result.skipped_shots)}")
        if result.b_control_manifest_path is not None:
            print(f"B-control manifest: {result.b_control_manifest_path}")
        return 0

    if args.command == "storyboard" and args.storyboard_command == "link-result":
        result = link_shot_result(
            settings=settings,
            story_id=args.story_id,
            shot_id=args.shot_id,
            result_path=args.result,
            kind=args.kind,
            source=args.source,
            source_reference=args.source_reference,
        )
        print(f"Linked shot result: {result.linked[0].result_id}")
        print(f"Shot results manifest: {result.manifest_path}")
        return 0

    if args.command == "storyboard" and args.storyboard_command == "link-comfyui-results":
        result = link_comfyui_results_to_storyboard(
            settings=settings,
            job_id=args.job_id,
            queue_path=args.queue,
            results_manifest_path=args.results_manifest,
        )
        print(f"Linked ComfyUI shot results: {len(result.linked)}")
        print(f"Skipped duplicates: {result.skipped_count}")
        print(f"Shot results manifest: {result.manifest_path}")
        return 0

    if args.command == "storyboard" and args.storyboard_command == "results":
        results = list_shot_results(
            settings=settings,
            story_id=args.story_id,
            shot_id=args.shot_id,
        )
        if args.json:
            print(json.dumps([result.__dict__ for result in results], ensure_ascii=False, indent=2))
            return 0
        if not results:
            print("No storyboard shot results.")
            return 0
        for result in results:
            print(f"{result.order}. {result.shot_id}: {result.kind} / {result.source} / {result.stored_path}")
        return 0

    if args.command == "storyboard" and args.storyboard_command == "decide-result":
        result = set_shot_result_decision(
            settings=settings,
            story_id=args.story_id,
            result_id=args.result_id,
            decision=args.decision,
            notes=args.notes,
        )
        print(f"Updated shot result decision: {result.result_id}")
        print(f"Decision: {result.decision}")
        return 0

    if args.command == "storyboard" and args.storyboard_command == "preview":
        result = write_storyboard_preview(
            settings=settings,
            story_id=args.story_id,
            output_path=args.output,
        )
        print(f"Wrote storyboard preview: {result.preview_path}")
        print(f"Results: {result.result_count}")
        print(f"Selected: {result.selected_count}")
        return 0

    if args.command == "storyboard" and args.storyboard_command == "export-selected":
        result = export_selected_shot_manifest(
            settings=settings,
            story_id=args.story_id,
            output_path=args.output,
        )
        print(f"Wrote selected shot manifest: {result.manifest_path}")
        print(f"Selected shots: {result.selected_shot_count}")
        print(f"Missing shots: {result.missing_shot_count}")
        return 0

    if args.command == "storyboard" and args.storyboard_command == "editor":
        result = write_storyboard_editor(
            settings=settings,
            story_id=args.story_id,
            output_path=args.output,
        )
        print(f"Wrote storyboard editor: {result.editor_path}")
        print(f"Shots: {result.shot_count}")
        print(f"Selected: {result.selected_count}")
        print(f"Missing: {result.missing_count}")
        return 0

    if args.command == "frames":
        plan = build_frame_extraction_plan(
            settings=settings,
            video_path=args.video,
            character_id=args.character_id,
            fps=args.fps,
        )
        print(" ".join(plan.command))
        if args.dry_run:
            return 0
        return extract_frames(plan)

    if args.command == "tags" and args.tag_command == "auto":
        result = generate_auto_tag_records(
            settings=settings,
            character_id=args.character_id,
            extra_tags=args.extra_tag,
            provider=args.provider,
            overwrite=args.overwrite,
        )
        print(f"Wrote {len(result.files_written)} auto tag records")
        return 0

    if args.command == "tags" and args.tag_command == "manual":
        result = update_manual_tags(
            settings=settings,
            character_id=args.character_id,
            add_tags=args.add_tag,
            reject_tags=args.reject_tag,
        )
        print(f"Updated {len(result.files_written)} tag records")
        return 0

    if args.command == "tags" and args.tag_command == "finalize":
        result = finalize_tag_sidecars(
            settings=settings,
            character_id=args.character_id,
            overwrite=not args.no_overwrite,
        )
        print(f"Wrote {len(result.files_written)} final caption sidecars")
        return 0

    if args.command == "dataset" and args.dataset_command == "build-lora":
        result = build_lora_dataset(
            settings=settings,
            character_id=args.character_id,
        )
        print(
            f"Built dataset: {result.dataset_dir} "
            f"({result.image_count} images, {result.caption_count} captions)"
        )
        return 0

    if args.command == "dataset" and args.dataset_command == "build-motion":
        result = build_motion_dataset(
            settings=settings,
            story_id=args.story_id,
            output_dir=args.output_dir,
            manifest_path=args.manifest,
        )
        print(f"Built motion dataset: {result.dataset_dir}")
        print(f"Manifest: {result.manifest_path}")
        print(f"Entries: {result.entry_count}")
        print(f"Transitions: {result.transition_count}")
        print(f"Assets: {result.asset_count}")
        return 0

    if args.command == "lora" and args.lora_command == "kohya-config":
        result = generate_kohya_low_vram_config(
            settings=settings,
            character_id=args.character_id,
            kohya_settings=KohyaLowVramSettings(
                pretrained_model_name_or_path=args.pretrained_model,
                kohya_root=args.kohya_root,
                resolution=args.resolution,
                repeats=args.repeats,
                max_train_epochs=args.epochs,
                network_dim=args.network_dim,
                network_alpha=args.network_alpha,
                learning_rate=args.learning_rate,
            ),
            dataset_dir=args.dataset_dir,
            require_2p5d=args.require_2p5d,
        )
        print(f"Wrote Kohya config directory: {result.config_dir}")
        print(f"Dataset images: {result.dataset_image_count}")
        print(f"Run script: {result.run_script}")
        print(f"Linked CharacterProfile: {result.profile_path}")
        return 0

    if args.command == "lora" and args.lora_command == "register-result":
        result = register_lora_result(
            settings=settings,
            character_id=args.character_id,
            model_path=args.model_path,
            source_config_dir=args.source_config_dir,
            display_name=args.name,
            notes=args.notes,
            status=args.status,
        )
        print(f"Linked LoRA result: {result.artifact.display_name}")
        print(f"Model path: {result.artifact.model_path}")
        print(f"CharacterProfile: {result.profile_path}")
        return 0

    if args.command == "lora" and args.lora_command == "list":
        artifacts = list_lora_artifacts(settings, args.character_id)
        if not artifacts:
            print("No LoRA artifacts linked.")
            return 0
        for artifact in artifacts:
            target = artifact.model_path or artifact.config_dir
            print(f"{artifact.artifact_id}: {artifact.kind} / {artifact.status} / {target}")
        return 0

    if args.command == "lora" and args.lora_command == "manifest":
        result = generate_lora_manifest(
            settings=settings,
            character_id=args.character_id,
            output_path=args.output,
            default_weight=args.weight,
        )
        print(f"Wrote LoRA manifest: {result.manifest_path}")
        print(f"LoRA entries: {result.lora_count}")
        return 0

    if args.command == "comfyui" and args.comfyui_command == "list-templates":
        templates = list_comfyui_templates(settings)
        if not templates:
            print("No ComfyUI templates found.")
            return 0
        for template in templates:
            print(template)
        return 0

    if args.command == "comfyui" and args.comfyui_command == "export-workflow":
        result = export_comfyui_workflow(
            settings=settings,
            character_id=args.character_id,
            template_path=args.template,
            output_path=args.output,
            manifest_path=args.manifest,
            lora_index=args.lora_index,
        )
        print(f"Wrote ComfyUI workflow: {result.workflow_path}")
        print(f"Manifest: {result.manifest_path}")
        print(f"Template: {result.template_path}")
        print(f"LoRA: {result.lora_name}")
        return 0

    if args.command == "comfyui" and args.comfyui_command == "queue-add":
        result = enqueue_comfyui_workflow(
            settings=settings,
            workflow_path=args.workflow,
            base_url=args.base_url,
            queue_path=args.queue,
        )
        print(f"Queued ComfyUI workflow: {result.job['job_id']}")
        print(f"Status: {result.job['status']}")
        print(f"Queue: {result.queue_path}")
        return 0

    if args.command == "comfyui" and args.comfyui_command == "queue-submit":
        result = submit_comfyui_job(
            settings=settings,
            job_id=args.job_id,
            workflow_path=args.workflow,
            base_url=args.base_url,
            queue_path=args.queue,
            dry_run=args.dry_run,
            timeout_seconds=args.timeout,
        )
        print(f"ComfyUI queue job: {result.job['job_id']}")
        print(f"Status: {result.job['status']}")
        print(f"Prompt ID: {result.job.get('prompt_id', '')}")
        print(f"Queue: {result.queue_path}")
        if result.job.get("error"):
            print(f"Error: {result.job['error']}")
        return 1 if result.job["status"] == "failed" else 0

    if args.command == "comfyui" and args.comfyui_command == "queue-list":
        jobs = list_comfyui_jobs(settings=settings, queue_path=args.queue)
        if not jobs:
            print("No ComfyUI queue jobs.")
            return 0
        for job in jobs:
            prompt_id = job.get("prompt_id", "")
            print(f"{job['job_id']}: {job['status']} / prompt={prompt_id} / {job['workflow_path']}")
        return 0

    if args.command == "comfyui" and args.comfyui_command == "queue-refresh":
        result = refresh_comfyui_job(
            settings=settings,
            job_id=args.job_id,
            queue_path=args.queue,
            timeout_seconds=args.timeout,
        )
        print(f"ComfyUI queue job: {result.job['job_id']}")
        print(f"Status: {result.job['status']}")
        print(f"Prompt ID: {result.job.get('prompt_id', '')}")
        if result.job.get("error"):
            print(f"Error: {result.job['error']}")
        return 1 if result.job["status"] == "failed" else 0

    if args.command == "comfyui" and args.comfyui_command == "queue-refresh-all":
        results = refresh_submitted_comfyui_jobs(
            settings=settings,
            queue_path=args.queue,
            timeout_seconds=args.timeout,
        )
        if not results:
            print("No submitted ComfyUI queue jobs.")
            return 0
        failed_count = 0
        for result in results:
            status = str(result.job["status"])
            failed_count += status == "failed"
            print(f"{result.job['job_id']}: {status} / prompt={result.job.get('prompt_id', '')}")
            if result.job.get("error"):
                print(f"  Error: {result.job['error']}")
        print(f"Refreshed: {len(results)} / Failed: {failed_count}")
        return 1 if failed_count else 0

    if args.command == "comfyui" and args.comfyui_command == "import-results":
        result = import_comfyui_results(
            settings=settings,
            character_id=args.character_id,
            job_id=args.job_id,
            comfyui_output_dir=args.comfyui_output_dir,
            queue_path=args.queue,
            metadata_only=args.metadata_only,
        )
        print(f"Imported ComfyUI results: {len(result.imported)}")
        print(f"Results manifest: {result.results_manifest_path}")
        print(f"Assets manifest: {result.assets_manifest_path}")
        return 0

    if args.command == "edit" and args.edit_command == "export":
        result = export_edit_timeline(
            settings=settings,
            story_id=args.story_id,
            manifest_path=args.manifest,
            output_dir=args.output_dir,
            formats=tuple(args.formats.split(",")),
        )
        print(f"Wrote edit exports: {result.export_dir}")
        print(f"Clips: {result.clip_count}")
        for name, path in result.files.items():
            print(f"{name}: {path}")
        return 0

    if args.command == "edit" and args.edit_command == "preview-movie":
        result = build_preview_movie(
            settings=settings,
            story_id=args.story_id,
            manifest_path=args.manifest,
            output_path=args.output,
            ffmpeg_path=args.ffmpeg,
            run=args.run,
            overwrite=not args.no_overwrite,
        )
        print(f"Wrote preview movie plan: {result.manifest_path}")
        print(f"Output movie: {result.output_movie}")
        print("Command: " + " ".join(result.command))
        if result.ran:
            print(f"FFmpeg return code: {result.return_code}")
        return result.return_code or 0

    if args.command == "edit" and args.edit_command == "revision-review":
        result = review_timeline_revisions(
            settings=settings,
            story_id=args.story_id,
            timeline_root=args.timeline_root,
            edit_manifest_path=args.edit_manifest,
            output_path=args.output,
        )
        print(f"Wrote timeline revision review: {result.manifest_path}")
        print(f"Revisions: {result.revision_count}")
        print(f"Recommended: {result.recommended_revision_id or 'none'}")
        return 0

    if args.command == "edit" and args.edit_command == "revision-adopt":
        result = adopt_timeline_revision(
            settings=settings,
            story_id=args.story_id,
            revision_id=args.revision_id,
            review_path=args.review,
            output_path=args.output,
        )
        print(f"Adopted timeline revision: {result.revision_id}")
        print(f"Timeline asset: {result.timeline_asset}")
        print(f"Manifest: {result.manifest_path}")
        return 0

    if args.command == "training" and args.training_command == "readiness":
        result = check_training_readiness(
            settings=settings,
            character_id=args.character_id,
            min_images=args.min_images,
            output_path=args.output,
            dataset_dir=args.dataset_dir,
            require_2p5d=args.require_2p5d,
        )
        print(f"Wrote training readiness: {result.manifest_path}")
        print(f"Ready: {result.ready}")
        print(f"Images: {result.image_count}")
        print(f"Issues: {result.issue_count}")
        return 0 if result.ready else 1

    if args.command == "training" and args.training_command == "smoke":
        result = run_training_smoke(
            settings=settings,
            character_id=args.character_id,
            pretrained_model=args.pretrained_model,
            kohya_root=args.kohya_root,
            min_images=args.min_images,
            provider=args.provider,
            output_path=args.output,
        )
        print(f"Wrote training smoke manifest: {result.manifest_path}")
        print(f"Dataset: {result.dataset_dir}")
        print(f"Kohya config: {result.kohya_config_dir}")
        print(f"Ready: {result.ready}")
        return 0 if result.ready else 1

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
