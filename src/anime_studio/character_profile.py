from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import re
from pathlib import Path

from .settings import AppSettings


CHARACTER_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{1,62}$")


@dataclass(frozen=True)
class CharacterProfile:
    character_id: str
    display_name: str
    trigger_tags: list[str] = field(default_factory=list)
    appearance_notes: str = ""
    source_notes: str = ""
    lora_files: list[str] = field(default_factory=list)


def validate_character_id(character_id: str) -> None:
    if not CHARACTER_ID_PATTERN.match(character_id):
        raise ValueError(
            "character_id must be 2-63 chars using lowercase letters, "
            "numbers, hyphens, or underscores."
        )


def create_character_profile(
    settings: AppSettings,
    character_id: str,
    display_name: str,
    trigger_tags: list[str] | None = None,
) -> Path:
    validate_character_id(character_id)

    profile = CharacterProfile(
        character_id=character_id,
        display_name=display_name,
        trigger_tags=trigger_tags or [character_id],
    )

    profile_dir = settings.assets.processed / "characters" / character_id
    profile_dir.mkdir(parents=True, exist_ok=True)
    profile_path = profile_dir / "profile.json"

    if profile_path.exists():
        raise FileExistsError(f"Character profile already exists: {profile_path}")

    profile_path.write_text(
        json.dumps(asdict(profile), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return profile_path
