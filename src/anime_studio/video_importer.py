from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
import shutil
from typing import Any

from .character_profile import character_profile_path, link_character_source_asset, validate_character_id
from .settings import AppSettings, load_settings


@dataclass(frozen=True)
class ImportedVideoAsset:
    video_id: str
    character_id: str
    original_path: str
    stored_path: str
    source_label: str
    size_bytes: int
    status: str = "imported"
    pipeline_state: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class VideoImportResult:
    asset: ImportedVideoAsset
    manifest_path: Path


def import_video_asset(
    settings: AppSettings,
    character_id: str,
    source_path: str | Path,
    source_label: str = "",
    allow_existing: bool = False,
) -> VideoImportResult:
    validate_character_id(character_id)
    profile_path = character_profile_path(settings, character_id)
    if not profile_path.exists():
        raise FileNotFoundError(f"Character profile does not exist: {profile_path}")

    source = Path(source_path)
    if not source.is_file():
        raise FileNotFoundError(f"Source video does not exist: {source}")

    video_extensions = {value.lower() for value in settings.video_extensions}
    if source.suffix.lower() not in video_extensions:
        raise ValueError(f"Source asset is not a supported video file: {source}")

    manifest_path = video_manifest_path(settings, character_id)
    existing_assets = list_imported_video_assets(settings, character_id)
    destination_dir = settings.assets.processed / "characters" / character_id / "sources" / "video"
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / source.name
    video_id = build_video_id(source)
    existing_asset = find_matching_video_asset(existing_assets, source=source, destination=destination, video_id=video_id)

    if destination.exists():
        if not allow_existing:
            raise FileExistsError(f"Imported video already exists: {destination}")
        if existing_asset is not None:
            link_character_source_asset(settings, character_id, existing_asset.stored_path)
            return VideoImportResult(asset=existing_asset, manifest_path=manifest_path)
        asset = build_imported_video_asset(
            character_id=character_id,
            source=source,
            destination=destination,
            source_label=source_label,
        )
        manifest_path = append_video_manifest(settings, character_id, asset)
        link_character_source_asset(settings, character_id, asset.stored_path)
        return VideoImportResult(asset=asset, manifest_path=manifest_path)

    shutil.copy2(source, destination)
    asset = build_imported_video_asset(
        character_id=character_id,
        source=source,
        destination=destination,
        source_label=source_label,
    )
    manifest_path = append_video_manifest(settings, character_id, asset)
    link_character_source_asset(settings, character_id, asset.stored_path)
    return VideoImportResult(asset=asset, manifest_path=manifest_path)


def build_imported_video_asset(
    character_id: str,
    source: Path,
    destination: Path,
    source_label: str,
) -> ImportedVideoAsset:
    return ImportedVideoAsset(
        video_id=build_video_id(source),
        character_id=character_id,
        original_path=str(source),
        stored_path=str(destination),
        source_label=source_label.strip() or source.stem,
        size_bytes=destination.stat().st_size,
        pipeline_state={
            "shot_detection": "pending",
            "frame_sampling": "pending",
            "character_sheet": "pending",
        },
        metadata={
            "filename": destination.name,
            "extension": destination.suffix.lower(),
        },
    )


def build_video_id(path: Path) -> str:
    normalized = path.stem.lower().replace("-", "_").replace(" ", "_")
    filtered = "".join(character for character in normalized if character.isalnum() or character == "_")
    return filtered or "video"


def video_manifest_path(settings: AppSettings, character_id: str) -> Path:
    return settings.assets.processed / "characters" / character_id / "video_sources.json"


def list_imported_video_assets(settings: AppSettings, character_id: str) -> list[ImportedVideoAsset]:
    manifest_path = video_manifest_path(settings, character_id)
    if not manifest_path.exists():
        return []
    data = load_video_manifest_data(manifest_path, character_id)
    return [imported_video_asset_from_dict(item) for item in data.get("videos", [])]


def load_video_manifest_data(manifest_path: Path, character_id: str) -> dict[str, Any]:
    if manifest_path.exists():
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    return {
        "schema_version": 1,
        "manifest_type": "character_video_sources",
        "phase": "3.5",
        "character_id": character_id,
        "videos": [],
    }


def imported_video_asset_from_dict(data: dict[str, Any]) -> ImportedVideoAsset:
    return ImportedVideoAsset(
        video_id=str(data["video_id"]),
        character_id=str(data["character_id"]),
        original_path=str(data["original_path"]),
        stored_path=str(data["stored_path"]),
        source_label=str(data.get("source_label", "")),
        size_bytes=int(data.get("size_bytes", 0)),
        status=str(data.get("status", "imported")),
        pipeline_state=dict(data.get("pipeline_state", {})),
        metadata=dict(data.get("metadata", {})),
    )


def find_matching_video_asset(
    assets: list[ImportedVideoAsset],
    source: Path,
    destination: Path,
    video_id: str,
) -> ImportedVideoAsset | None:
    for asset in assets:
        if Path(asset.stored_path).name == destination.name:
            return asset
        if asset.video_id == video_id and Path(asset.original_path).name == source.name:
            return asset
    return None


def append_video_manifest(
    settings: AppSettings,
    character_id: str,
    asset: ImportedVideoAsset,
) -> Path:
    manifest_path = video_manifest_path(settings, character_id)
    data = load_video_manifest_data(manifest_path, character_id)
    data["videos"].append(asdict(asset))
    manifest_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="anime-video-import",
        description="Import a source video into the Phase 3.5 character workspace.",
    )
    parser.add_argument(
        "--config",
        default="config/local_6gb.json",
        help="Path to the local runtime profile.",
    )
    parser.add_argument("--character-id", required=True, help="Character id.")
    parser.add_argument("--source", required=True, help="Source video path.")
    parser.add_argument(
        "--source-label",
        default="",
        help="Optional short label such as scene, episode, or baseline clip.",
    )
    parser.add_argument(
        "--reuse-existing",
        action="store_true",
        help="Reuse an already imported video entry instead of failing.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    settings = load_settings(args.config)
    result = import_video_asset(
        settings=settings,
        character_id=args.character_id,
        source_path=args.source,
        source_label=args.source_label,
        allow_existing=args.reuse_existing,
    )
    print(f"Imported video asset: {result.asset.stored_path}")
    print(f"Video id: {result.asset.video_id}")
    print(f"Video manifest: {result.manifest_path}")
    print("Next pipeline: shot_detection -> frame_sampling -> character_sheet")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
