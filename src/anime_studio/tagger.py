from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .character_profile import load_character_profile, validate_character_id
from .settings import AppSettings


@dataclass(frozen=True)
class TaggingResult:
    character_id: str
    method: str
    files_written: list[str]


def prepare_tag_sidecars(
    settings: AppSettings,
    character_id: str,
    extra_tags: list[str] | None = None,
    overwrite: bool = False,
) -> TaggingResult:
    validate_character_id(character_id)
    profile = load_character_profile(settings, character_id)
    tags = dedupe_tags([*profile.trigger_tags, *(extra_tags or [])])

    image_paths = collect_character_images(settings, character_id)
    files_written: list[str] = []
    for image_path in image_paths:
        sidecar_path = image_path.with_suffix(".txt")
        if sidecar_path.exists() and not overwrite:
            continue
        sidecar_path.write_text(", ".join(tags) + "\n", encoding="utf-8")
        files_written.append(str(sidecar_path))

    return TaggingResult(
        character_id=character_id,
        method="manual_baseline",
        files_written=files_written,
    )


def collect_character_images(settings: AppSettings, character_id: str) -> list[Path]:
    character_dir = settings.assets.processed / "characters" / character_id
    candidates = [
        character_dir / "frames",
        character_dir / "sources" / "image",
    ]
    image_extensions = {value.lower() for value in settings.image_extensions}
    image_paths: list[Path] = []

    for candidate in candidates:
        if not candidate.exists():
            continue
        image_paths.extend(
            path
            for path in candidate.rglob("*")
            if path.is_file() and path.suffix.lower() in image_extensions
        )

    return sorted(image_paths)


def dedupe_tags(tags: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        normalized = tag.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result
