from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import shutil

from .character_profile import load_character_profile, save_character_profile, validate_character_id
from .lora_registry import project_relative_path, utc_timestamp
from .settings import AppSettings, load_settings
from .video_shot_pipeline import classification_manifest_path


MASTER_MANIFEST_TYPE = "character_master_asset"


@dataclass(frozen=True)
class CharacterMasterAssetResult:
    manifest_path: Path
    character_id: str
    reviewed_asset_path: Path | None
    master_asset_path: Path | None


def import_character_master_asset(
    settings: AppSettings,
    character_id: str,
    video_id: str,
    reviewed_image: str | Path | None = None,
    master_image: str | Path | None = None,
    notes: str = "",
) -> CharacterMasterAssetResult:
    validate_character_id(character_id)
    draft_manifest = settings.project_root / "manifests" / "characters" / character_id / "character_sheet" / f"{video_id}_draft.json"
    completeness_manifest = settings.project_root / "manifests" / "characters" / character_id / "character_sheet" / f"{video_id}_completeness.json"
    classification_manifest = classification_manifest_path(settings, character_id, video_id)

    reviewed_asset_path = copy_character_sheet_asset(settings, character_id, reviewed_image, "reviewed")
    master_asset_path = copy_character_sheet_asset(settings, character_id, master_image, "master")
    completeness = load_optional_json(completeness_manifest)

    manifest_path = settings.project_root / "manifests" / "characters" / character_id / "character_sheet" / "character_master_asset.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "manifest_type": MASTER_MANIFEST_TYPE,
                "generated_at": utc_timestamp(),
                "character_id": character_id,
                "video_id": video_id,
                "paths": {
                    "draft_manifest": optional_relative_path(settings, draft_manifest),
                    "completeness_manifest": optional_relative_path(settings, completeness_manifest),
                    "classification_manifest": optional_relative_path(settings, classification_manifest),
                    "reviewed_image": optional_relative_path(settings, reviewed_asset_path),
                    "master_image": optional_relative_path(settings, master_asset_path),
                },
                "coverage": completeness.get("statuses", {}),
                "phase35_ready": bool(completeness.get("phase35_ready", False)),
                "notes": [item for item in [notes.strip()] if item],
                "next_steps": [
                    "Use the master asset as the human-reviewed source of truth.",
                    "Generate a 2.5D definition from the master asset manifest.",
                    "Keep LoRA training and 2.5D control definitions separated but linked.",
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    attach_master_note_to_profile(settings, character_id, video_id, reviewed_asset_path, master_asset_path)
    return CharacterMasterAssetResult(
        manifest_path=manifest_path,
        character_id=character_id,
        reviewed_asset_path=reviewed_asset_path,
        master_asset_path=master_asset_path,
    )


def copy_character_sheet_asset(
    settings: AppSettings,
    character_id: str,
    source: str | Path | None,
    stage: str,
) -> Path | None:
    if source in (None, ""):
        return None
    path = Path(source)
    if not path.is_file():
        raise FileNotFoundError(f"Character sheet source does not exist: {path}")
    destination_dir = settings.assets.processed / "characters" / character_id / "character_sheet" / stage
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / path.name
    if destination.resolve() != path.resolve():
        shutil.copy2(path, destination)
    return destination


def attach_master_note_to_profile(
    settings: AppSettings,
    character_id: str,
    video_id: str,
    reviewed_asset_path: Path | None,
    master_asset_path: Path | None,
) -> None:
    profile = load_character_profile(settings, character_id)
    note_parts = [f"character master imported from video {video_id}"]
    if reviewed_asset_path is not None:
        note_parts.append(f"reviewed={reviewed_asset_path.name}")
    if master_asset_path is not None:
        note_parts.append(f"master={master_asset_path.name}")
    note = ", ".join(note_parts)
    if note in profile.source_notes:
        return
    updated_profile = type(profile)(
        character_id=profile.character_id,
        display_name=profile.display_name,
        trigger_tags=profile.trigger_tags,
        appearance_notes=profile.appearance_notes,
        source_notes=f"{profile.source_notes}\n{note}".strip(),
        lora_files=profile.lora_files,
        lora_artifacts=profile.lora_artifacts,
    )
    save_character_profile(settings, updated_profile)


def load_optional_json(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def optional_relative_path(settings: AppSettings, path: Path | None) -> str:
    if path is None or not path.exists():
        return ""
    return project_relative_path(settings, path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="anime-character-master",
        description="Import reviewed / master character sheet assets into a reusable master asset manifest.",
    )
    parser.add_argument("--config", default="config/local_6gb.json", help="Path to the local runtime profile.")
    parser.add_argument("--character-id", required=True, help="Character id.")
    parser.add_argument("--video-id", required=True, help="Video id linked to the character sheet draft.")
    parser.add_argument("--reviewed-image", default=None, help="Optional reviewed character sheet image.")
    parser.add_argument("--master-image", default=None, help="Optional master character sheet image.")
    parser.add_argument("--notes", default="", help="Optional import notes.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    settings = load_settings(args.config)
    result = import_character_master_asset(
        settings=settings,
        character_id=args.character_id,
        video_id=args.video_id,
        reviewed_image=args.reviewed_image,
        master_image=args.master_image,
        notes=args.notes,
    )
    print(f"Master asset manifest: {result.manifest_path}")
    if result.reviewed_asset_path is not None:
        print(f"Reviewed asset: {result.reviewed_asset_path}")
    if result.master_asset_path is not None:
        print(f"Master asset: {result.master_asset_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
