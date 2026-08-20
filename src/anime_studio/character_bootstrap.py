from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
import json
from pathlib import Path

from .character_profile import (
    CharacterProfile,
    character_profile_path,
    create_character_profile,
    load_character_profile,
    save_character_profile,
    validate_character_id,
)
from .lora_registry import project_relative_path, utc_timestamp
from .settings import AppSettings, load_settings
from .video_importer import import_video_asset


@dataclass(frozen=True)
class CharacterBootstrapResult:
    character_id: str
    profile_path: Path
    video_manifest_path: Path
    bootstrap_manifest_path: Path
    created_profile: bool
    video_id: str


def bootstrap_character_from_video(
    settings: AppSettings,
    character_id: str,
    display_name: str,
    video_path: str | Path,
    trigger_tags: list[str] | None = None,
    source_label: str = "",
    appearance_notes: str = "",
    source_notes: str = "",
    allow_existing_profile: bool = True,
    allow_existing_video: bool = True,
) -> CharacterBootstrapResult:
    validate_character_id(character_id)
    profile_path = character_profile_path(settings, character_id)
    created_profile = False

    if profile_path.exists():
        if not allow_existing_profile:
            raise FileExistsError(f"Character profile already exists: {profile_path}")
        profile = load_character_profile(settings, character_id)
        updated = merge_profile_notes(
            profile=profile,
            display_name=display_name,
            trigger_tags=trigger_tags,
            appearance_notes=appearance_notes,
            source_notes=source_notes,
        )
        save_character_profile(settings, updated)
    else:
        create_character_profile(
            settings=settings,
            character_id=character_id,
            display_name=display_name,
            trigger_tags=trigger_tags,
        )
        created_profile = True
        profile = load_character_profile(settings, character_id)
        updated = merge_profile_notes(
            profile=profile,
            display_name=display_name,
            trigger_tags=trigger_tags,
            appearance_notes=appearance_notes,
            source_notes=source_notes,
        )
        save_character_profile(settings, updated)

    import_result = import_video_asset(
        settings=settings,
        character_id=character_id,
        source_path=video_path,
        source_label=source_label,
        allow_existing=allow_existing_video,
    )
    bootstrap_manifest_path = write_bootstrap_manifest(
        settings=settings,
        character_id=character_id,
        display_name=display_name,
        profile_path=profile_path,
        created_profile=created_profile,
        video_manifest_path=import_result.manifest_path,
        video_id=import_result.asset.video_id,
        source_label=import_result.asset.source_label,
    )
    return CharacterBootstrapResult(
        character_id=character_id,
        profile_path=profile_path,
        video_manifest_path=import_result.manifest_path,
        bootstrap_manifest_path=bootstrap_manifest_path,
        created_profile=created_profile,
        video_id=import_result.asset.video_id,
    )


def merge_profile_notes(
    profile: CharacterProfile,
    display_name: str,
    trigger_tags: list[str] | None,
    appearance_notes: str,
    source_notes: str,
) -> CharacterProfile:
    combined_source_notes = append_unique_note(profile.source_notes, source_notes)
    combined_appearance_notes = append_unique_note(profile.appearance_notes, appearance_notes)
    merged_trigger_tags = list(profile.trigger_tags)
    for tag in trigger_tags or []:
        normalized = tag.strip()
        if normalized and normalized not in merged_trigger_tags:
            merged_trigger_tags.append(normalized)
    return replace(
        profile,
        display_name=display_name or profile.display_name,
        trigger_tags=merged_trigger_tags,
        appearance_notes=combined_appearance_notes,
        source_notes=combined_source_notes,
    )


def append_unique_note(existing: str, addition: str) -> str:
    normalized = addition.strip()
    if not normalized:
        return existing
    if normalized in existing:
        return existing
    return f"{existing}\n{normalized}".strip()


def write_bootstrap_manifest(
    settings: AppSettings,
    character_id: str,
    display_name: str,
    profile_path: Path,
    created_profile: bool,
    video_manifest_path: Path,
    video_id: str,
    source_label: str,
) -> Path:
    manifest_path = settings.project_root / "manifests" / "characters" / character_id / "character_bootstrap.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "manifest_type": "character_bootstrap",
                "generated_at": utc_timestamp(),
                "character_id": character_id,
                "display_name": display_name,
                "created_profile": created_profile,
                "video_id": video_id,
                "source_label": source_label,
                "paths": {
                    "profile": project_relative_path(settings, profile_path),
                    "video_manifest": project_relative_path(settings, video_manifest_path),
                },
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return manifest_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="anime-character-bootstrap",
        description="Create or update a CharacterProfile from a source video.",
    )
    parser.add_argument("--config", default="config/local_6gb.json", help="Path to the local runtime profile.")
    parser.add_argument("--character-id", required=True, help="Character id.")
    parser.add_argument("--name", required=True, help="Display name.")
    parser.add_argument("--video", required=True, help="Source video path.")
    parser.add_argument("--trigger-tag", action="append", default=None, help="Optional trigger tag.")
    parser.add_argument("--source-label", default="", help="Optional short label for the source video.")
    parser.add_argument("--appearance-notes", default="", help="Optional appearance notes.")
    parser.add_argument("--source-notes", default="", help="Optional source notes.")
    parser.add_argument("--no-profile-reuse", action="store_true", help="Fail if the CharacterProfile already exists.")
    parser.add_argument("--no-video-reuse", action="store_true", help="Fail if the video is already imported.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    settings = load_settings(args.config)
    result = bootstrap_character_from_video(
        settings=settings,
        character_id=args.character_id,
        display_name=args.name,
        video_path=args.video,
        trigger_tags=args.trigger_tag,
        source_label=args.source_label,
        appearance_notes=args.appearance_notes,
        source_notes=args.source_notes,
        allow_existing_profile=not args.no_profile_reuse,
        allow_existing_video=not args.no_video_reuse,
    )
    print(f"Character profile: {result.profile_path}")
    print(f"Video manifest: {result.video_manifest_path}")
    print(f"Bootstrap manifest: {result.bootstrap_manifest_path}")
    print(f"Video id: {result.video_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
