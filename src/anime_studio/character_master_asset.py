from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
import json
from pathlib import Path
import shutil

from .character_sheet_importer import import_character_sheet
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
    section_manifest_path: Path | None = None


def import_character_master_asset(
    settings: AppSettings,
    character_id: str,
    video_id: str,
    reviewed_image: str | Path | None = None,
    master_image: str | Path | None = None,
    notes: str = "",
    import_sections: bool = True,
) -> CharacterMasterAssetResult:
    validate_character_id(character_id)
    draft_manifest = settings.project_root / "manifests" / "characters" / character_id / "character_sheet" / f"{video_id}_draft.json"
    completeness_manifest = settings.project_root / "manifests" / "characters" / character_id / "character_sheet" / f"{video_id}_completeness.json"
    classification_manifest = classification_manifest_path(settings, character_id, video_id)

    reviewed_asset_path = copy_character_sheet_asset(settings, character_id, reviewed_image, "reviewed")
    master_asset_path = copy_character_sheet_asset(settings, character_id, master_image, "master")
    definition_source_path = master_asset_path or reviewed_asset_path
    section_import = None
    if import_sections and definition_source_path is not None:
        section_import = import_character_sheet(
            settings=settings,
            character_id=character_id,
            source_image=definition_source_path,
            source_label=f"{video_id}_master",
            allow_create_profile=False,
        )
    completeness = load_optional_json(completeness_manifest)
    section_manifest = load_optional_json(section_import.manifest_path) if section_import else {}

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
                    "definition_source_image": optional_relative_path(settings, definition_source_path),
                    "section_import_manifest": optional_relative_path(
                        settings, section_import.manifest_path if section_import else None
                    ),
                },
                "section_assets": section_manifest.get("sections", []),
                "coverage": completeness.get("statuses", {}),
                "phase35_ready": bool(completeness.get("phase35_ready", False)),
                "definition_ready": bool(definition_source_path and section_import),
                "human_review": {
                    "reviewed_image_present": reviewed_asset_path is not None,
                    "master_image_present": master_asset_path is not None,
                    "requires_human_approval": True,
                },
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
        section_manifest_path=section_import.manifest_path if section_import else None,
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
    updated_profile = replace(
        profile,
        source_notes=f"{profile.source_notes}\n{note}".strip(),
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
    parser.add_argument("--no-section-import", action="store_true", help="Do not split the master sheet into template regions.")
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
        import_sections=not args.no_section_import,
    )
    print(f"Master asset manifest: {result.manifest_path}")
    if result.reviewed_asset_path is not None:
        print(f"Reviewed asset: {result.reviewed_asset_path}")
    if result.master_asset_path is not None:
        print(f"Master asset: {result.master_asset_path}")
    if result.section_manifest_path is not None:
        print(f"Master sections: {result.section_manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
