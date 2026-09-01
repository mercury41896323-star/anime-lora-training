from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path

from .character_2p5d_definition import generate_character_2p5d_definition
from .character_bootstrap import bootstrap_character_from_video
from .character_master_asset import import_character_master_asset
from .character_profile import character_profile_path, confirm_character_source_rights
from .character_sheet_draft import generate_character_sheet_draft
from .frame_extraction import build_frame_extraction_plan, extract_frames
from .kohya_config import KohyaLowVramSettings, generate_kohya_low_vram_config
from .lora_registry import project_relative_path, utc_timestamp
from .settings import AppSettings, load_settings
from .tagger import finalize_tag_sidecars, generate_auto_tag_records
from .training_readiness import check_training_readiness
from .video_analysis import analyze_video_learning
from .video_domain_datasets import build_video_domain_datasets
from .video_frame_cleaner import build_clean_video_frames
from .video_importer import import_video_asset
from .video_shot_pipeline import (
    choose_effective_fps,
    classify_sampled_frames,
    detect_video_shots,
    probe_video_metadata,
    sample_shot_frames,
)


PIPELINE_MANIFEST_TYPE = "phase3_5_video_pipeline"


@dataclass(frozen=True)
class VideoPhase35PipelineResult:
    manifest_path: Path
    character_id: str
    video_id: str
    effective_fps: float
    ready: bool


def run_video_phase35_pipeline(
    settings: AppSettings,
    character_id: str,
    video_path: str | Path,
    display_name: str,
    pretrained_model: str,
    kohya_root: str = ".",
    requested_fps: float = 2.0,
    target_max_frames: int = 240,
    min_images: int = 20,
    provider: str = "baseline",
    source_label: str = "",
    sequence_seconds: float = 12.0,
    max_frames_per_shot: int = 6,
    reviewed_image: str | Path | None = None,
    master_image: str | Path | None = None,
    clean_width: int = 512,
    clean_height: int = 512,
    top_trim_ratio: float = 0.04,
    bottom_trim_ratio: float = 0.18,
    source_rights_reviewer: str = "",
) -> VideoPhase35PipelineResult:
    profile_exists = character_profile_path(settings, character_id).exists()
    bootstrap = bootstrap_character_from_video(
        settings=settings,
        character_id=character_id,
        display_name=display_name or character_id,
        video_path=video_path,
        trigger_tags=[character_id] if not profile_exists else None,
        source_label=source_label,
        allow_existing_profile=True,
        allow_existing_video=True,
    )
    if source_rights_reviewer.strip():
        confirm_character_source_rights(
            settings=settings,
            character_id=character_id,
            reviewer=source_rights_reviewer,
            notes="Confirmed during Phase 3.5 video pipeline execution.",
        )

    imported = import_video_asset(
        settings=settings,
        character_id=character_id,
        source_path=video_path,
        source_label=source_label,
        allow_existing=True,
    )
    probe = probe_video_metadata(imported.asset.stored_path)
    effective_fps = choose_effective_fps(probe.duration_seconds, requested_fps, target_max_frames)
    frame_plan = build_frame_extraction_plan(
        settings=settings,
        character_id=character_id,
        video_path=imported.asset.stored_path,
        fps=effective_fps,
        output_group=imported.asset.video_id,
    )
    extraction_return_code = extract_frames(frame_plan)
    if extraction_return_code != 0:
        raise RuntimeError(f"Frame extraction failed with code {extraction_return_code}.")
    generate_auto_tag_records(
        settings=settings,
        character_id=character_id,
        provider=provider,
        overwrite=False,
    )
    finalize_tag_sidecars(settings=settings, character_id=character_id, overwrite=True)
    analysis = analyze_video_learning(
        settings=settings,
        character_id=character_id,
        video_path=video_path,
        fps=effective_fps,
        sequence_seconds=sequence_seconds,
        sample_every_n=3,
        auto_extract=False,
        reuse_import=True,
        source_label=source_label,
        create_storyboard_draft=True,
    )
    shots = detect_video_shots(
        settings=settings,
        character_id=character_id,
        video_path=video_path,
        fps=requested_fps,
        source_label=source_label,
        auto_extract=False,
        reuse_import=True,
        min_shot_seconds=2.0,
        max_shot_seconds=12.0,
        tag_change_threshold=0.55,
        target_max_frames=target_max_frames,
    )
    sampled = sample_shot_frames(
        settings=settings,
        character_id=character_id,
        video_id=shots.video_id,
        similarity_threshold=0.85,
        max_frames_per_shot=max_frames_per_shot,
        min_frame_gap=2,
    )
    classified = classify_sampled_frames(
        settings=settings,
        character_id=character_id,
        video_id=shots.video_id,
    )
    clean_frames = build_clean_video_frames(
        settings=settings,
        character_id=character_id,
        video_id=shots.video_id,
        target_width=clean_width,
        target_height=clean_height,
        top_trim_ratio=top_trim_ratio,
        bottom_trim_ratio=bottom_trim_ratio,
    )
    draft = generate_character_sheet_draft(
        settings=settings,
        character_id=character_id,
        video_id=shots.video_id,
    )

    master_asset = None
    if reviewed_image not in (None, "") or master_image not in (None, ""):
        master_asset = import_character_master_asset(
            settings=settings,
            character_id=character_id,
            video_id=shots.video_id,
            reviewed_image=reviewed_image,
            master_image=master_image,
        )
    definition = generate_character_2p5d_definition(settings=settings, character_id=character_id)
    definition_data = json.loads(definition.manifest_path.read_text(encoding="utf-8"))
    domain_datasets = build_video_domain_datasets(
        settings=settings,
        character_id=character_id,
        video_id=shots.video_id,
    )
    clean_kohya = None
    clean_metadata_path = clean_frames.dataset_dir / "metadata.json"
    clean_metadata = json.loads(clean_metadata_path.read_text(encoding="utf-8")) if clean_metadata_path.is_file() else {}
    review_completed = bool(clean_metadata.get("review_completed", False)) or not bool(
        clean_metadata.get("human_review_required", False)
    )
    if definition_data.get("definition_status") == "ready" and review_completed:
        clean_kohya = generate_kohya_low_vram_config(
            settings=settings,
            character_id=character_id,
            kohya_settings=KohyaLowVramSettings(
                pretrained_model_name_or_path=pretrained_model,
                kohya_root=kohya_root,
                resolution=min(clean_width, clean_height),
            ),
            dataset_dir=clean_frames.dataset_dir,
            require_2p5d=True,
            definition_path=definition.manifest_path,
        )
    readiness = check_training_readiness(
        settings=settings,
        character_id=character_id,
        min_images=min_images,
        dataset_dir=clean_frames.dataset_dir,
        require_2p5d=True,
    )

    manifest_path = settings.project_root / "manifests" / "characters" / character_id / "phase3_5_video_pipeline.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "manifest_type": PIPELINE_MANIFEST_TYPE,
                "generated_at": utc_timestamp(),
                "character_id": character_id,
                "video_id": shots.video_id,
                "display_name": display_name or character_id,
                "ready": readiness.ready,
                "learning_architecture": "2p5d_base_lora_completion",
                "video_probe": asdict(probe),
                "analysis_profile": {
                    "requested_fps": requested_fps,
                    "effective_fps": effective_fps,
                    "target_max_frames": target_max_frames,
                    "sequence_seconds": sequence_seconds,
                    "max_frames_per_shot": max_frames_per_shot,
                    "clean_frame_size": [clean_width, clean_height],
                    "top_trim_ratio": top_trim_ratio,
                    "bottom_trim_ratio": bottom_trim_ratio,
                },
                "steps": [
                    "video_import",
                    "frame_extraction",
                    "auto_tags",
                    "image_analysis",
                    "shot_detector_splitter",
                    "similarity_dedup_frame_sampler",
                    "face_angle_expression_full_body_classification",
                    "safe_crop_and_text_tag_exclusion",
                    "character_sheet_draft_generator",
                    "reviewed_master_reimport_optional",
                    "character_profile_or_master_to_2p5d",
                    "video_domain_dataset_bundle",
                    "lora_residual_config_after_2p5d_and_human_frame_review",
                    "readiness_check",
                    "asset_storage",
                ],
                "outputs": {
                    "bootstrap_manifest": project_relative_path(settings, bootstrap.bootstrap_manifest_path),
                    "imported_video_manifest": project_relative_path(settings, imported.manifest_path),
                    "frame_output_dir": project_relative_path(settings, frame_plan.output_dir),
                    "video_analysis": project_relative_path(settings, analysis.analysis_manifest_path),
                    "shot_manifest": project_relative_path(settings, shots.manifest_path),
                    "sampled_manifest": project_relative_path(settings, sampled.manifest_path),
                    "sampled_dataset_dir": project_relative_path(settings, sampled.dataset_dir),
                    "classification_manifest": project_relative_path(settings, classified.manifest_path),
                    "clean_frame_manifest": project_relative_path(settings, clean_frames.manifest_path),
                    "clean_dataset_dir": project_relative_path(settings, clean_frames.dataset_dir),
                    "video_domain_datasets": project_relative_path(settings, domain_datasets.manifest_path),
                    "clean_kohya_config_dir": project_relative_path(settings, clean_kohya.config_dir)
                    if clean_kohya
                    else "",
                    "training_readiness": project_relative_path(settings, readiness.manifest_path),
                    "character_sheet_draft": project_relative_path(settings, draft.draft_manifest_path),
                    "character_sheet_draft_image": project_relative_path(settings, draft.draft_sheet_path),
                    "character_sheet_review": project_relative_path(settings, draft.review_manifest_path),
                    "character_sheet_completeness": project_relative_path(settings, draft.completeness_manifest_path),
                },
                "optional_outputs": {
                    "character_master_asset": project_relative_path(settings, master_asset.manifest_path) if master_asset else "",
                    "character_2p5d_definition": project_relative_path(settings, definition.manifest_path),
                },
                "next_steps": [
                    "Visually reject any clean-frame candidate that still contains text or occlusion.",
                    "Review shot boundaries and sampled frames.",
                    "Review classification coverage for face angles, expressions, and full body frames.",
                    "Import reviewed/master sheets when the 2.5D definition is not ready.",
                    "Run LoRA only after the readiness manifest confirms the 2.5D-first gate.",
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return VideoPhase35PipelineResult(
        manifest_path=manifest_path,
        character_id=character_id,
        video_id=shots.video_id,
        effective_fps=effective_fps,
        ready=readiness.ready,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="anime-video-phase35",
        description="Run the end-to-end Phase 3.5 video pipeline for 60-300 second clips.",
    )
    parser.add_argument("--config", default="config/local_6gb.json", help="Path to the local runtime profile.")
    parser.add_argument("--character-id", required=True, help="Character id.")
    parser.add_argument("--name", required=True, help="Display name.")
    parser.add_argument("--video", required=True, help="Source video path.")
    parser.add_argument("--pretrained-model", required=True, help="Base SD model path or id.")
    parser.add_argument("--kohya-root", default=".", help="Kohya/sd-scripts root path.")
    parser.add_argument("--requested-fps", type=float, default=2.0, help="Requested analysis fps before adaptive reduction.")
    parser.add_argument("--target-max-frames", type=int, default=240, help="Adaptive cap for 60-300 second video analysis.")
    parser.add_argument("--min-images", type=int, default=20, help="Minimum recommended image count for readiness.")
    parser.add_argument("--provider", default="baseline", help="Tag provider for auto tags.")
    parser.add_argument("--source-label", default="", help="Optional source label.")
    parser.add_argument("--sequence-seconds", type=float, default=12.0, help="Target duration for sequence buckets.")
    parser.add_argument("--max-frames-per-shot", type=int, default=6, help="Maximum sampled frames per shot.")
    parser.add_argument("--reviewed-image", default=None, help="Optional reviewed character sheet image.")
    parser.add_argument("--master-image", default=None, help="Optional master character sheet image.")
    parser.add_argument("--clean-width", type=int, default=512, help="Clean training frame width.")
    parser.add_argument("--clean-height", type=int, default=512, help="Clean training frame height.")
    parser.add_argument("--top-trim", type=float, default=0.04, help="Top safe-area trim ratio.")
    parser.add_argument("--bottom-trim", type=float, default=0.18, help="Bottom subtitle-band trim ratio.")
    parser.add_argument(
        "--confirm-source-rights",
        default="",
        metavar="REVIEWER",
        help="Confirm training rights for this source and record the reviewer name.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    settings = load_settings(args.config)
    result = run_video_phase35_pipeline(
        settings=settings,
        character_id=args.character_id,
        video_path=args.video,
        display_name=args.name,
        pretrained_model=args.pretrained_model,
        kohya_root=args.kohya_root,
        requested_fps=args.requested_fps,
        target_max_frames=args.target_max_frames,
        min_images=args.min_images,
        provider=args.provider,
        source_label=args.source_label,
        sequence_seconds=args.sequence_seconds,
        max_frames_per_shot=args.max_frames_per_shot,
        reviewed_image=args.reviewed_image,
        master_image=args.master_image,
        clean_width=args.clean_width,
        clean_height=args.clean_height,
        top_trim_ratio=args.top_trim,
        bottom_trim_ratio=args.bottom_trim,
        source_rights_reviewer=args.confirm_source_rights,
    )
    print(f"Phase 3.5 pipeline manifest: {result.manifest_path}")
    print(f"Character: {result.character_id}")
    print(f"Video id: {result.video_id}")
    print(f"Effective fps: {result.effective_fps}")
    print(f"Ready: {result.ready}")
    return 0 if result.ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
