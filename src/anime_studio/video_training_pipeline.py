from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path

from .frame_extraction import build_frame_extraction_plan, extract_frames
from .lora_registry import project_relative_path, utc_timestamp
from .settings import AppSettings, load_settings
from .training_readiness import TrainingSmokeResult, run_training_smoke
from .video_importer import import_video_asset


VIDEO_SMOKE_MANIFEST_TYPE = "phase3_5_video_to_training_smoke"


@dataclass(frozen=True)
class VideoTrainingSmokeResult:
    manifest_path: Path
    imported_video_manifest_path: Path
    training_smoke_manifest_path: Path
    readiness_path: Path
    frame_output_dir: Path
    dataset_dir: Path
    kohya_config_dir: Path
    video_id: str
    ready: bool
    extraction_return_code: int | None


def run_video_training_smoke(
    settings: AppSettings,
    character_id: str,
    video_path: str,
    pretrained_model: str,
    kohya_root: str = ".",
    fps: float = 1.0,
    min_images: int = 1,
    provider: str = "baseline",
    source_label: str = "",
    skip_extract: bool = False,
    reuse_import: bool = False,
    output_path: str | Path | None = None,
) -> VideoTrainingSmokeResult:
    import_result = import_video_asset(
        settings=settings,
        character_id=character_id,
        source_path=video_path,
        source_label=source_label,
        allow_existing=reuse_import,
    )
    frame_plan = build_frame_extraction_plan(
        settings=settings,
        video_path=import_result.asset.stored_path,
        character_id=character_id,
        fps=fps,
        output_group=import_result.asset.video_id,
    )

    extraction_return_code: int | None = None
    if not skip_extract:
        extraction_return_code = extract_frames(frame_plan)
        if extraction_return_code != 0:
            raise RuntimeError(f"Frame extraction failed with code {extraction_return_code}.")

    smoke = run_training_smoke(
        settings=settings,
        character_id=character_id,
        pretrained_model=pretrained_model,
        kohya_root=kohya_root,
        min_images=min_images,
        provider=provider,
    )
    manifest_path = normalize_video_smoke_path(settings, character_id, output_path)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "manifest_type": VIDEO_SMOKE_MANIFEST_TYPE,
                "generated_at": utc_timestamp(),
                "character_id": character_id,
                "video": {
                    "video_id": import_result.asset.video_id,
                    "source_label": import_result.asset.source_label,
                    "stored_path": project_relative_path(settings, import_result.asset.stored_path),
                    "video_manifest": project_relative_path(settings, import_result.manifest_path),
                },
                "frame_extraction": {
                    "fps": fps,
                    "output_dir": project_relative_path(settings, frame_plan.output_dir),
                    "command": frame_plan.command,
                    "status": "skipped" if skip_extract else "completed",
                    "return_code": extraction_return_code,
                },
                "training_smoke": {
                    "manifest": project_relative_path(settings, smoke.manifest_path),
                    "readiness": project_relative_path(settings, smoke.readiness_path),
                    "dataset_dir": project_relative_path(settings, smoke.dataset_dir),
                    "kohya_config_dir": project_relative_path(settings, smoke.kohya_config_dir),
                },
                "steps": [
                    "video_import",
                    "frame_extraction" if not skip_extract else "frame_extraction_skipped",
                    "auto_tags",
                    "final_captions",
                    "dataset_build",
                    "kohya_low_vram_config",
                    "readiness_check",
                ],
                "ready": smoke.ready,
                "notes": (
                    "Video-to-training smoke stops before launching Kohya training."
                    if not skip_extract
                    else "Frame extraction was skipped. Prepare frames first if they do not already exist."
                ),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return VideoTrainingSmokeResult(
        manifest_path=manifest_path,
        imported_video_manifest_path=import_result.manifest_path,
        training_smoke_manifest_path=smoke.manifest_path,
        readiness_path=smoke.readiness_path,
        frame_output_dir=frame_plan.output_dir,
        dataset_dir=smoke.dataset_dir,
        kohya_config_dir=smoke.kohya_config_dir,
        video_id=import_result.asset.video_id,
        ready=smoke.ready,
        extraction_return_code=extraction_return_code,
    )


def normalize_video_smoke_path(settings: AppSettings, character_id: str, output_path: str | Path | None) -> Path:
    if output_path is None:
        return settings.project_root / "manifests" / "training" / character_id / "video_training_smoke.json"
    path = Path(output_path)
    if not path.is_absolute():
        path = settings.project_root / path
    return path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="anime-video-training",
        description="Run the Phase 3.5 video-to-training smoke pipeline.",
    )
    parser.add_argument("--config", default="config/local_6gb.json", help="Path to the local runtime profile.")
    parser.add_argument("--character-id", required=True, help="Character id.")
    parser.add_argument("--video", required=True, help="Source video path.")
    parser.add_argument("--pretrained-model", required=True, help="SD base model path or id for generated config.")
    parser.add_argument("--kohya-root", default=".", help="Kohya/sd-scripts root path.")
    parser.add_argument("--fps", type=float, default=1.0, help="Frames per second to sample from the video.")
    parser.add_argument("--min-images", type=int, default=1, help="Minimum image count for smoke readiness.")
    parser.add_argument("--provider", default="baseline", help="Tag provider for smoke auto tags.")
    parser.add_argument("--source-label", default="", help="Optional short label such as baseline clip.")
    parser.add_argument("--skip-extract", action="store_true", help="Skip ffmpeg frame extraction and reuse existing frames.")
    parser.add_argument("--reuse-import", action="store_true", help="Reuse an already imported video entry instead of failing.")
    parser.add_argument("--output", default=None, help="Optional video smoke manifest path.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    settings = load_settings(args.config)
    result = run_video_training_smoke(
        settings=settings,
        character_id=args.character_id,
        video_path=args.video,
        pretrained_model=args.pretrained_model,
        kohya_root=args.kohya_root,
        fps=args.fps,
        min_images=args.min_images,
        provider=args.provider,
        source_label=args.source_label,
        skip_extract=args.skip_extract,
        reuse_import=args.reuse_import,
        output_path=args.output,
    )
    print(f"Wrote video training smoke manifest: {result.manifest_path}")
    print(f"Video id: {result.video_id}")
    print(f"Frames: {result.frame_output_dir}")
    print(f"Dataset: {result.dataset_dir}")
    print(f"Kohya config: {result.kohya_config_dir}")
    print(f"Ready: {result.ready}")
    return 0 if result.ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
