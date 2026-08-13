from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import shutil

from .character_profile import load_character_profile, validate_character_id
from .tagger import collect_character_images, finalize_tag_sidecars
from .settings import AppSettings


@dataclass(frozen=True)
class DatasetBuildResult:
    character_id: str
    dataset_dir: Path
    image_count: int
    caption_count: int


def build_lora_dataset(settings: AppSettings, character_id: str) -> DatasetBuildResult:
    validate_character_id(character_id)
    profile = load_character_profile(settings, character_id)
    finalize_tag_sidecars(settings, character_id, overwrite=True)
    image_paths = collect_character_images(settings, character_id)

    dataset_dir = settings.datasets.lora / character_id
    images_dir = dataset_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    image_count = 0
    caption_count = 0
    for image_path in image_paths:
        destination_image = unique_destination(images_dir, image_path.name)
        shutil.copy2(image_path, destination_image)
        image_count += 1

        source_caption = image_path.with_suffix(".txt")
        destination_caption = destination_image.with_suffix(".txt")
        if source_caption.exists():
            shutil.copy2(source_caption, destination_caption)
        else:
            destination_caption.write_text(
                ", ".join(profile.trigger_tags) + "\n",
                encoding="utf-8",
            )
        caption_count += 1

    metadata_path = dataset_dir / "metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "character_id": character_id,
                "display_name": profile.display_name,
                "trigger_tags": profile.trigger_tags,
                "image_count": image_count,
                "caption_count": caption_count,
                "profile_path": str(
                    settings.assets.processed / "characters" / character_id / "profile.json"
                ),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    return DatasetBuildResult(
        character_id=character_id,
        dataset_dir=dataset_dir,
        image_count=image_count,
        caption_count=caption_count,
    )


def unique_destination(directory: Path, filename: str) -> Path:
    destination = directory / filename
    if not destination.exists():
        return destination

    stem = destination.stem
    suffix = destination.suffix
    index = 2
    while True:
        candidate = directory / f"{stem}_{index}{suffix}"
        if not candidate.exists():
            return candidate
        index += 1
