from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import shutil

from .character_profile import character_profile_path, link_character_source_asset, validate_character_id
from .settings import AppSettings


@dataclass(frozen=True)
class RegisteredAsset:
    original_path: str
    stored_path: str
    kind: str
    size_bytes: int
    source: str = "manual"
    metadata: dict[str, object] | None = None


def register_character_asset(
    settings: AppSettings,
    character_id: str,
    source_path: str | Path,
) -> RegisteredAsset:
    validate_character_id(character_id)
    profile_path = character_profile_path(settings, character_id)
    if not profile_path.exists():
        raise FileNotFoundError(f"Character profile does not exist: {profile_path}")

    source = Path(source_path)
    if not source.is_file():
        raise FileNotFoundError(f"Source asset does not exist: {source}")

    kind = classify_asset(settings, source)
    destination_dir = settings.assets.processed / "characters" / character_id / "sources" / kind
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / source.name

    if destination.exists():
        raise FileExistsError(f"Registered asset already exists: {destination}")

    shutil.copy2(source, destination)
    copy_asset_sidecars(source, destination)

    asset = RegisteredAsset(
        original_path=str(source),
        stored_path=str(destination),
        kind=kind,
        size_bytes=destination.stat().st_size,
    )
    append_asset_manifest(settings, character_id, asset)
    link_character_source_asset(settings, character_id, destination)
    return asset


def copy_asset_sidecars(source: Path, destination: Path) -> None:
    for suffix in (".txt", ".tags.json"):
        source_sidecar = source.with_suffix(suffix)
        if not source_sidecar.is_file():
            continue
        shutil.copy2(source_sidecar, destination.with_suffix(suffix))


def classify_asset(settings: AppSettings, path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {value.lower() for value in settings.image_extensions}:
        return "image"
    if suffix in {value.lower() for value in settings.video_extensions}:
        return "video"
    return "other"


def append_asset_manifest(
    settings: AppSettings,
    character_id: str,
    asset: RegisteredAsset,
) -> Path:
    manifest_path = settings.assets.processed / "characters" / character_id / "assets.json"
    if manifest_path.exists():
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    else:
        data = {"character_id": character_id, "assets": []}

    data["assets"].append(asdict(asset))
    manifest_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest_path
