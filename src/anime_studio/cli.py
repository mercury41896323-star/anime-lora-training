from __future__ import annotations

import argparse
import json
from pathlib import Path

from .asset_inventory import collect_asset_inventory
from .asset_library import collect_asset_library, write_asset_library_index
from .character_manager import register_character_asset
from .character_profile import create_character_profile
from .comfyui_queue import (
    DEFAULT_COMFYUI_BASE_URL,
    enqueue_comfyui_workflow,
    list_comfyui_jobs,
    refresh_comfyui_job,
    submit_comfyui_job,
)
from .comfyui_results import import_comfyui_results
from .comfyui_workflow_export import export_comfyui_workflow, list_comfyui_templates
from .dataset_builder import build_lora_dataset
from .frame_extraction import build_frame_extraction_plan, extract_frames
from .kohya_config import KohyaLowVramSettings, generate_kohya_low_vram_config
from .lora_manifest import generate_lora_manifest
from .lora_registry import list_lora_artifacts, register_lora_result
from .settings import load_settings
from .storyboard import add_shot, create_storyboard, list_storyboard_shots
from .storyboard_comfyui import export_storyboard_comfyui_workflows
from .tagger import finalize_tag_sidecars, generate_auto_tag_records, update_manual_tags


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
    storyboard_add_shot.add_argument(
        "--duration",
        type=float,
        default=3.0,
        help="Shot duration in seconds.",
    )
    storyboard_add_shot.add_argument("--camera", default="", help="Camera note.")
    storyboard_add_shot.add_argument("--lighting", default="", help="Lighting note.")
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
            duration_seconds=args.duration,
            camera=args.camera,
            lighting=args.lighting,
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
        )
        print(f"Wrote storyboard ComfyUI manifest: {result.manifest_path}")
        print(f"Workflows: {len(result.workflows)}")
        print(f"Skipped shots: {len(result.skipped_shots)}")
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
        return 0

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
        return 0

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

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
