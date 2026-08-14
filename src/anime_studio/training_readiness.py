from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from .character_profile import character_profile_path, load_character_profile, validate_character_id
from .dataset_builder import build_lora_dataset
from .kohya_config import KohyaLowVramSettings, generate_kohya_low_vram_config
from .lora_registry import project_relative_path, utc_timestamp
from .settings import AppSettings
from .tagger import collect_character_images, finalize_tag_sidecars, generate_auto_tag_records, tag_record_path


READINESS_MANIFEST_TYPE = "local_lora_training_readiness"
SMOKE_MANIFEST_TYPE = "local_lora_training_smoke"
DEFAULT_MIN_IMAGES = 20


@dataclass(frozen=True)
class TrainingReadinessResult:
    manifest_path: Path
    ready: bool
    issue_count: int
    image_count: int


@dataclass(frozen=True)
class TrainingSmokeResult:
    manifest_path: Path
    readiness_path: Path
    dataset_dir: Path
    kohya_config_dir: Path
    ready: bool


def check_training_readiness(
    settings: AppSettings,
    character_id: str,
    min_images: int = DEFAULT_MIN_IMAGES,
    output_path: str | Path | None = None,
) -> TrainingReadinessResult:
    validate_character_id(character_id)
    issues: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    profile_path = character_profile_path(settings, character_id)
    profile = None
    if profile_path.exists():
        profile = load_character_profile(settings, character_id)
    else:
        issues.append(issue("missing_profile", f"CharacterProfile is missing: {profile_path}"))

    image_paths = collect_character_images(settings, character_id)
    if len(image_paths) < min_images:
        issues.append(issue("not_enough_images", f"Need at least {min_images} images, found {len(image_paths)}."))

    tag_records = [tag_record_path(path) for path in image_paths]
    missing_tag_records = [path for path in tag_records if not path.exists()]
    caption_paths = [path.with_suffix(".txt") for path in image_paths]
    missing_captions = [path for path in caption_paths if not path.exists()]
    empty_captions = [path for path in caption_paths if path.exists() and not path.read_text(encoding="utf-8").strip()]
    if missing_tag_records:
        warnings.append(issue("missing_tag_records", f"{len(missing_tag_records)} images do not have .tags.json records."))
    if missing_captions:
        issues.append(issue("missing_captions", f"{len(missing_captions)} images do not have .txt captions."))
    if empty_captions:
        issues.append(issue("empty_captions", f"{len(empty_captions)} captions are empty."))

    dataset_dir = settings.datasets.lora / character_id
    dataset_metadata = dataset_dir / "metadata.json"
    dataset_images = list((dataset_dir / "images").glob("*")) if (dataset_dir / "images").exists() else []
    if not dataset_metadata.exists():
        warnings.append(issue("missing_dataset_metadata", f"Dataset metadata is missing: {dataset_metadata}"))
    if image_paths and not dataset_images:
        warnings.append(issue("missing_dataset_images", f"Dataset images are not built yet: {dataset_dir / 'images'}"))

    kohya_dir = settings.project_root / "config" / "kohya" / character_id
    required_kohya = [kohya_dir / "dataset.toml", kohya_dir / "train_low_vram.toml", kohya_dir / "run_train.ps1"]
    missing_kohya = [path for path in required_kohya if not path.exists()]
    if missing_kohya:
        warnings.append(issue("missing_kohya_config", f"{len(missing_kohya)} Kohya low-VRAM files are missing."))

    manifest_path = normalize_readiness_path(settings, character_id, output_path)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    ready = not issues
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "manifest_type": READINESS_MANIFEST_TYPE,
                "generated_at": utc_timestamp(),
                "character_id": character_id,
                "ready": ready,
                "counts": {
                    "image_count": len(image_paths),
                    "tag_record_count": len(tag_records) - len(missing_tag_records),
                    "caption_count": len(caption_paths) - len(missing_captions),
                    "issue_count": len(issues),
                    "warning_count": len(warnings),
                },
                "paths": {
                    "profile": project_relative_path(settings, profile_path),
                    "dataset_dir": project_relative_path(settings, dataset_dir),
                    "kohya_config_dir": project_relative_path(settings, kohya_dir),
                },
                "trigger_tags": profile.trigger_tags if profile else [],
                "issues": issues,
                "warnings": warnings,
                "next_actions": next_actions(issues, warnings),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return TrainingReadinessResult(manifest_path, ready, len(issues), len(image_paths))


def run_training_smoke(
    settings: AppSettings,
    character_id: str,
    pretrained_model: str,
    kohya_root: str = ".",
    min_images: int = 1,
    provider: str = "baseline",
    output_path: str | Path | None = None,
) -> TrainingSmokeResult:
    validate_character_id(character_id)
    generate_auto_tag_records(settings=settings, character_id=character_id, provider=provider, overwrite=False)
    finalize_tag_sidecars(settings=settings, character_id=character_id, overwrite=True)
    dataset = build_lora_dataset(settings=settings, character_id=character_id)
    kohya = generate_kohya_low_vram_config(
        settings=settings,
        character_id=character_id,
        kohya_settings=KohyaLowVramSettings(
            pretrained_model_name_or_path=pretrained_model,
            kohya_root=kohya_root,
        ),
    )
    readiness = check_training_readiness(settings=settings, character_id=character_id, min_images=min_images)
    manifest_path = normalize_smoke_path(settings, character_id, output_path)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "manifest_type": SMOKE_MANIFEST_TYPE,
                "generated_at": utc_timestamp(),
                "character_id": character_id,
                "ready": readiness.ready,
                "steps": [
                    "auto_tags",
                    "final_captions",
                    "dataset_build",
                    "kohya_low_vram_config",
                    "readiness_check",
                ],
                "outputs": {
                    "dataset_dir": project_relative_path(settings, dataset.dataset_dir),
                    "kohya_config_dir": project_relative_path(settings, kohya.config_dir),
                    "run_script": project_relative_path(settings, kohya.run_script),
                    "readiness": project_relative_path(settings, readiness.manifest_path),
                },
                "notes": "Smoke workflow stops before launching Kohya training.",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return TrainingSmokeResult(manifest_path, readiness.manifest_path, dataset.dataset_dir, kohya.config_dir, readiness.ready)


def issue(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def next_actions(issues: list[dict[str, str]], warnings: list[dict[str, str]]) -> list[str]:
    codes = {item["code"] for item in [*issues, *warnings]}
    actions: list[str] = []
    if "missing_profile" in codes:
        actions.append("Create a CharacterProfile first.")
    if "not_enough_images" in codes:
        actions.append("Add more character images before starting LoRA training.")
    if "missing_tag_records" in codes:
        actions.append("Run auto tagging, then manually adjust tags if needed.")
    if "missing_captions" in codes or "empty_captions" in codes:
        actions.append("Finalize captions after tag review.")
    if "missing_dataset_metadata" in codes or "missing_dataset_images" in codes:
        actions.append("Build the LoRA dataset.")
    if "missing_kohya_config" in codes:
        actions.append("Generate Kohya low-VRAM config files.")
    if not actions:
        actions.append("Ready for a small local LoRA training run.")
    return actions


def normalize_readiness_path(settings: AppSettings, character_id: str, output_path: str | Path | None) -> Path:
    if output_path is None:
        return settings.project_root / "manifests" / "training" / character_id / "training_readiness.json"
    path = Path(output_path)
    if not path.is_absolute():
        path = settings.project_root / path
    return path


def normalize_smoke_path(settings: AppSettings, character_id: str, output_path: str | Path | None) -> Path:
    if output_path is None:
        return settings.project_root / "manifests" / "training" / character_id / "sample_training_smoke.json"
    path = Path(output_path)
    if not path.is_absolute():
        path = settings.project_root / path
    return path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="anime-training-readiness",
        description="Check and prepare local LoRA training readiness.",
    )
    parser.add_argument("--config", default="config/local_6gb.json", help="Path to the local runtime profile.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    readiness = subparsers.add_parser("readiness", help="Check whether a character can start local LoRA training.")
    readiness.add_argument("--character-id", required=True, help="Character id.")
    readiness.add_argument("--min-images", type=int, default=DEFAULT_MIN_IMAGES, help="Minimum recommended image count.")
    readiness.add_argument("--output", default=None, help="Optional readiness manifest path.")
    smoke = subparsers.add_parser("smoke", help="Run dataset -> Kohya config -> readiness without launching training.")
    smoke.add_argument("--character-id", required=True, help="Character id.")
    smoke.add_argument("--pretrained-model", required=True, help="SD base model path or id for generated config.")
    smoke.add_argument("--kohya-root", default=".", help="Kohya/sd-scripts root path.")
    smoke.add_argument("--min-images", type=int, default=1, help="Minimum image count for smoke readiness.")
    smoke.add_argument("--provider", default="baseline", help="Tag provider for smoke auto tags.")
    smoke.add_argument("--output", default=None, help="Optional smoke manifest path.")
    return parser


def main(argv: list[str] | None = None) -> int:
    from .settings import load_settings

    parser = build_parser()
    args = parser.parse_args(argv)
    settings = load_settings(args.config)
    if args.command == "readiness":
        result = check_training_readiness(
            settings=settings,
            character_id=args.character_id,
            min_images=args.min_images,
            output_path=args.output,
        )
        print(f"Wrote training readiness: {result.manifest_path}")
        print(f"Ready: {result.ready}")
        print(f"Images: {result.image_count}")
        print(f"Issues: {result.issue_count}")
        return 0 if result.ready else 1
    if args.command == "smoke":
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
