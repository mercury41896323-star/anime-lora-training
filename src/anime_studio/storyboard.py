from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import re
from pathlib import Path

from .character_profile import validate_character_id
from .lora_registry import utc_timestamp
from .settings import AppSettings


STORY_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{1,62}$")


@dataclass(frozen=True)
class Shot:
    shot_id: str
    order: int
    title: str
    character_id: str = ""
    prompt: str = ""
    negative_prompt: str = ""
    duration_seconds: float = 3.0
    camera: str = ""
    lighting: str = ""
    seed: int | None = None
    width: int | None = None
    height: int | None = None
    steps: int | None = None
    notes: str = ""


@dataclass(frozen=True)
class Storyboard:
    story_id: str
    title: str
    created_at: str
    updated_at: str
    shots: list[Shot] = field(default_factory=list)


def create_storyboard(settings: AppSettings, story_id: str, title: str) -> Path:
    validate_story_id(story_id)
    storyboard_path = get_storyboard_path(settings, story_id)
    if storyboard_path.exists():
        raise FileExistsError(f"Storyboard already exists: {storyboard_path}")
    timestamp = utc_timestamp()
    storyboard = Storyboard(
        story_id=story_id,
        title=title,
        created_at=timestamp,
        updated_at=timestamp,
    )
    return save_storyboard(settings, storyboard)


def add_shot(
    settings: AppSettings,
    story_id: str,
    shot_id: str,
    title: str,
    character_id: str = "",
    prompt: str = "",
    negative_prompt: str = "",
    duration_seconds: float = 3.0,
    camera: str = "",
    lighting: str = "",
    seed: int | None = None,
    width: int | None = None,
    height: int | None = None,
    steps: int | None = None,
    notes: str = "",
) -> Path:
    validate_story_id(shot_id)
    if character_id:
        validate_character_id(character_id)
    validate_optional_positive_int(seed, "seed")
    validate_optional_positive_int(width, "width")
    validate_optional_positive_int(height, "height")
    validate_optional_positive_int(steps, "steps")
    storyboard = load_storyboard(settings, story_id)
    if any(shot.shot_id == shot_id for shot in storyboard.shots):
        raise ValueError(f"Shot already exists: {shot_id}")
    shot = Shot(
        shot_id=shot_id,
        order=len(storyboard.shots) + 1,
        title=title,
        character_id=character_id,
        prompt=prompt,
        negative_prompt=negative_prompt,
        duration_seconds=duration_seconds,
        camera=camera,
        lighting=lighting,
        seed=seed,
        width=width,
        height=height,
        steps=steps,
        notes=notes,
    )
    updated = Storyboard(
        story_id=storyboard.story_id,
        title=storyboard.title,
        created_at=storyboard.created_at,
        updated_at=utc_timestamp(),
        shots=[*storyboard.shots, shot],
    )
    return save_storyboard(settings, updated)


def list_storyboard_shots(settings: AppSettings, story_id: str) -> list[Shot]:
    return load_storyboard(settings, story_id).shots


def load_storyboard(settings: AppSettings, story_id: str) -> Storyboard:
    validate_story_id(story_id)
    path = get_storyboard_path(settings, story_id)
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    return Storyboard(
        story_id=str(data["story_id"]),
        title=str(data["title"]),
        created_at=str(data.get("created_at", "")),
        updated_at=str(data.get("updated_at", "")),
        shots=[shot_from_dict(item) for item in data.get("shots", [])],
    )


def save_storyboard(settings: AppSettings, storyboard: Storyboard) -> Path:
    path = get_storyboard_path(settings, storyboard.story_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(asdict(storyboard), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def get_storyboard_path(settings: AppSettings, story_id: str) -> Path:
    validate_story_id(story_id)
    return settings.project_root / "storyboards" / story_id / "storyboard.json"


def shot_from_dict(data: dict[str, object]) -> Shot:
    return Shot(
        shot_id=str(data["shot_id"]),
        order=int(data["order"]),
        title=str(data["title"]),
        character_id=str(data.get("character_id", "")),
        prompt=str(data.get("prompt", "")),
        negative_prompt=str(data.get("negative_prompt", "")),
        duration_seconds=float(data.get("duration_seconds", 3.0)),
        camera=str(data.get("camera", "")),
        lighting=str(data.get("lighting", "")),
        seed=optional_int(data.get("seed")),
        width=optional_int(data.get("width")),
        height=optional_int(data.get("height")),
        steps=optional_int(data.get("steps")),
        notes=str(data.get("notes", "")),
    )


def validate_story_id(value: str) -> None:
    if not STORY_ID_PATTERN.match(value):
        raise ValueError(
            "story_id and shot_id must be 2-63 chars using lowercase letters, "
            "numbers, hyphens, or underscores."
        )


def optional_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def validate_optional_positive_int(value: int | None, name: str) -> None:
    if value is not None and value <= 0:
        raise ValueError(f"{name} must be a positive integer.")
