from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import re
from pathlib import Path

from .character_profile import load_character_profile, validate_character_id
from .settings import AppSettings
from .wd14_provider import WD14Config, generate_wd14_tags


@dataclass(frozen=True)
class ImageTagRecord:
    image_path: str
    provider: str
    auto_tags: list[str] = field(default_factory=list)
    manual_tags: list[str] = field(default_factory=list)
    rejected_tags: list[str] = field(default_factory=list)

    @property
    def final_tags(self) -> list[str]:
        rejected = set(self.rejected_tags)
        return [tag for tag in dedupe_tags([*self.auto_tags, *self.manual_tags]) if tag not in rejected]


@dataclass(frozen=True)
class TaggingResult:
    character_id: str
    method: str
    files_written: list[str]


def generate_auto_tag_records(
    settings: AppSettings,
    character_id: str,
    provider: str = "baseline",
    extra_tags: list[str] | None = None,
    overwrite: bool = False,
) -> TaggingResult:
    validate_character_id(character_id)
    profile = load_character_profile(settings, character_id)
    image_paths = collect_character_images(settings, character_id)
    files_written: list[str] = []

    for image_path in image_paths:
        record_path = tag_record_path(image_path)
        existing = load_tag_record(record_path) if record_path.exists() else None
        if existing and not overwrite:
            continue

        auto_tags = generate_provider_tags(settings, image_path, provider)
        auto_tags = dedupe_tags([*profile.trigger_tags, *auto_tags, *(extra_tags or [])])
        record = ImageTagRecord(
            image_path=str(image_path),
            provider=provider,
            auto_tags=auto_tags,
            manual_tags=existing.manual_tags if existing else [],
            rejected_tags=existing.rejected_tags if existing else [],
        )
        save_tag_record(record_path, record)
        files_written.append(str(record_path))

    return TaggingResult(character_id, f"auto:{provider}", files_written)


def update_manual_tags(
    settings: AppSettings,
    character_id: str,
    add_tags: list[str] | None = None,
    reject_tags: list[str] | None = None,
) -> TaggingResult:
    validate_character_id(character_id)
    image_paths = collect_character_images(settings, character_id)
    files_written: list[str] = []

    for image_path in image_paths:
        record_path = tag_record_path(image_path)
        record = load_or_create_tag_record(record_path, image_path)
        updated = ImageTagRecord(
            image_path=record.image_path,
            provider=record.provider,
            auto_tags=record.auto_tags,
            manual_tags=dedupe_tags([*record.manual_tags, *(add_tags or [])]),
            rejected_tags=dedupe_tags([*record.rejected_tags, *(reject_tags or [])]),
        )
        save_tag_record(record_path, updated)
        files_written.append(str(record_path))

    return TaggingResult(character_id, "manual", files_written)


def finalize_tag_sidecars(
    settings: AppSettings,
    character_id: str,
    overwrite: bool = True,
) -> TaggingResult:
    validate_character_id(character_id)
    image_paths = collect_character_images(settings, character_id)
    files_written: list[str] = []

    for image_path in image_paths:
        caption_path = image_path.with_suffix(".txt")
        if caption_path.exists() and not overwrite:
            continue
        record = load_or_create_tag_record(tag_record_path(image_path), image_path)
        caption_path.write_text(", ".join(record.final_tags) + "\n", encoding="utf-8")
        files_written.append(str(caption_path))

    return TaggingResult(character_id, "finalize", files_written)


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


def tag_record_path(image_path: Path) -> Path:
    return image_path.with_suffix(".tags.json")


def load_or_create_tag_record(record_path: Path, image_path: Path) -> ImageTagRecord:
    if record_path.exists():
        return load_tag_record(record_path)
    return ImageTagRecord(image_path=str(image_path), provider="manual")


def load_tag_record(record_path: Path) -> ImageTagRecord:
    data = json.loads(record_path.read_text(encoding="utf-8"))
    return ImageTagRecord(
        image_path=data["image_path"],
        provider=data.get("provider", "unknown"),
        auto_tags=list(data.get("auto_tags", [])),
        manual_tags=list(data.get("manual_tags", [])),
        rejected_tags=list(data.get("rejected_tags", [])),
    )


def save_tag_record(record_path: Path, record: ImageTagRecord) -> None:
    record_path.write_text(
        json.dumps(
            {**asdict(record), "final_tags": record.final_tags},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def infer_filename_tags(image_path: Path) -> list[str]:
    stem = image_path.stem.lower()
    return [
        token
        for token in re.split(r"[^a-z0-9]+", stem)
        if token and not token.isdigit()
    ]


def generate_provider_tags(settings: AppSettings, image_path: Path, provider: str) -> list[str]:
    if provider == "baseline":
        return infer_filename_tags(image_path)
    if provider == "wd14":
        return generate_wd14_tags(
            image_path=image_path,
            model_dir=settings.models.wd14,
            config=WD14Config(),
        )
    raise ValueError(f"Unknown tag provider: {provider}")


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
