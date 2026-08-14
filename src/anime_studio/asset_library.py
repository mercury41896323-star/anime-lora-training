from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
from typing import Any

from .character_profile import load_character_profile, validate_character_id
from .settings import AppSettings


ASSET_QUERY_PATTERN = re.compile(r"[a-z0-9_./-]+|[一-龥ぁ-んァ-ンー]+", re.IGNORECASE)


@dataclass(frozen=True)
class AssetLibraryItem:
    character_id: str
    display_name: str
    kind: str
    source: str
    stored_path: str
    original_path: str
    size_bytes: int
    exists: bool
    metadata: dict[str, Any]


def collect_asset_library(
    settings: AppSettings,
    character_id: str | None = None,
    kind: str | None = None,
    source: str | None = None,
    query: str | None = None,
) -> list[AssetLibraryItem]:
    character_dirs = list_character_dirs(settings, character_id)
    items: list[AssetLibraryItem] = []
    for character_dir in character_dirs:
        current_character_id = character_dir.name
        try:
            profile = load_character_profile(settings, current_character_id)
            display_name = profile.display_name
        except FileNotFoundError:
            display_name = current_character_id

        manifest_path = character_dir / "assets.json"
        if not manifest_path.exists():
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        for raw_asset in manifest.get("assets", []):
            asset = dict(raw_asset)
            item = AssetLibraryItem(
                character_id=current_character_id,
                display_name=display_name,
                kind=str(asset.get("kind", "")),
                source=str(asset.get("source", "manual")),
                stored_path=str(asset.get("stored_path", "")),
                original_path=str(asset.get("original_path", "")),
                size_bytes=int(asset.get("size_bytes", 0)),
                exists=asset_exists(settings, str(asset.get("stored_path", ""))),
                metadata=dict(asset.get("metadata") or {}),
            )
            if matches_filters(item, kind=kind, source=source, query=query):
                items.append(item)
    return sorted(items, key=lambda item: (item.character_id, item.kind, item.stored_path))


def write_asset_library_index(
    settings: AppSettings,
    output_path: str | Path,
    character_id: str | None = None,
    kind: str | None = None,
    source: str | None = None,
    query: str | None = None,
) -> Path:
    items = collect_asset_library(
        settings=settings,
        character_id=character_id,
        kind=kind,
        source=source,
        query=query,
    )
    output = normalize_project_path(settings, output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "library_type": "asset_library_index",
                "filters": {
                    "character_id": character_id or "",
                    "kind": kind or "",
                    "source": source or "",
                    "query": query or "",
                },
                "count": len(items),
                "items": [asdict(item) for item in items],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return output


def search_asset_library(
    settings: AppSettings,
    query: str,
    kinds: list[str] | tuple[str, ...] | None = None,
    character_id: str | None = None,
    source: str | None = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    if limit <= 0:
        return []
    allowed_kinds = {item.lower() for item in kinds or []}
    tokens = tokenize_asset_query(query)
    matches: list[tuple[int, AssetLibraryItem]] = []
    for item in collect_asset_library(settings=settings, character_id=character_id, source=source):
        if allowed_kinds and item.kind.lower() not in allowed_kinds:
            continue
        score = score_asset_library_item(item, tokens)
        if score > 0 or not tokens:
            matches.append((score, item))
    matches.sort(key=lambda pair: (-pair[0], pair[1].character_id, pair[1].stored_path))
    return [asset_library_item_reference(item, score) for score, item in matches[:limit]]


def list_character_dirs(settings: AppSettings, character_id: str | None) -> list[Path]:
    characters_dir = settings.assets.processed / "characters"
    if character_id:
        validate_character_id(character_id)
        return [characters_dir / character_id]
    if not characters_dir.exists():
        return []
    return sorted(path for path in characters_dir.iterdir() if path.is_dir())


def matches_filters(
    item: AssetLibraryItem,
    kind: str | None,
    source: str | None,
    query: str | None,
) -> bool:
    if kind and item.kind != kind:
        return False
    if source and item.source != source:
        return False
    if query:
        needle = query.lower()
        haystack = json.dumps(asdict(item), ensure_ascii=False).lower()
        if needle not in haystack:
            return False
    return True


def tokenize_asset_query(query: str) -> list[str]:
    return [match.group(0).lower() for match in ASSET_QUERY_PATTERN.finditer(query)]


def score_asset_library_item(item: AssetLibraryItem, tokens: list[str]) -> int:
    if not tokens:
        return 1
    haystack = json.dumps(asdict(item), ensure_ascii=False).lower()
    filename = Path(item.stored_path).stem.lower()
    score = 0
    for token in tokens:
        if token in haystack:
            score += 1
        if token and token in filename:
            score += 2
        metadata_tags = item.metadata.get("tags")
        if isinstance(metadata_tags, list) and token in {str(tag).lower() for tag in metadata_tags}:
            score += 3
    return score


def asset_library_item_reference(item: AssetLibraryItem, score: int) -> dict[str, Any]:
    return {
        "character_id": item.character_id,
        "display_name": item.display_name,
        "kind": item.kind,
        "source": item.source,
        "stored_path": item.stored_path,
        "original_path": item.original_path,
        "exists": item.exists,
        "score": score,
        "metadata": item.metadata,
    }


def asset_exists(settings: AppSettings, stored_path: str) -> bool:
    if not stored_path:
        return False
    return normalize_project_path(settings, stored_path).exists()


def normalize_project_path(settings: AppSettings, path: str | Path) -> Path:
    resolved = Path(path)
    if not resolved.is_absolute():
        resolved = settings.project_root / resolved
    return resolved
