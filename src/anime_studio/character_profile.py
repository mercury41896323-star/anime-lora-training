from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
import json
import re
from pathlib import Path

from .settings import AppSettings


CHARACTER_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{1,62}$")


@dataclass(frozen=True)
class LoraArtifact:
    artifact_id: str
    kind: str
    status: str
    display_name: str
    config_dir: str = ""
    dataset_config: str = ""
    training_config: str = ""
    run_script: str = ""
    model_path: str = ""
    output_name: str = ""
    trigger_tags: list[str] = field(default_factory=list)
    notes: str = ""
    created_at: str = ""
    updated_at: str = ""
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class CharacterProfile:
    character_id: str
    display_name: str
    trigger_tags: list[str] = field(default_factory=list)
    appearance_notes: str = ""
    source_notes: str = ""
    lora_files: list[str] = field(default_factory=list)
    lora_artifacts: list[LoraArtifact] = field(default_factory=list)
    source_assets: list[str] = field(default_factory=list)
    definition_2p5d: str = ""
    learning_strategy: str = "2p5d_base_lora_completion"


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

    save_character_profile(settings, profile)
    return profile_path


def character_profile_path(settings: AppSettings, character_id: str) -> Path:
    validate_character_id(character_id)
    return settings.assets.processed / "characters" / character_id / "profile.json"


def load_character_profile(settings: AppSettings, character_id: str) -> CharacterProfile:
    profile_path = character_profile_path(settings, character_id)
    data = json.loads(profile_path.read_text(encoding="utf-8"))
    return CharacterProfile(
        character_id=data["character_id"],
        display_name=data["display_name"],
        trigger_tags=list(data.get("trigger_tags", [])),
        appearance_notes=data.get("appearance_notes", ""),
        source_notes=data.get("source_notes", ""),
        lora_files=list(data.get("lora_files", [])),
        lora_artifacts=[
            lora_artifact_from_dict(item)
            for item in data.get("lora_artifacts", [])
        ],
        source_assets=[str(value) for value in data.get("source_assets", [])],
        definition_2p5d=str(data.get("definition_2p5d", "")),
        learning_strategy=str(
            data.get("learning_strategy", "2p5d_base_lora_completion")
        ),
    )


def save_character_profile(settings: AppSettings, profile: CharacterProfile) -> Path:
    validate_character_id(profile.character_id)
    profile_dir = settings.assets.processed / "characters" / profile.character_id
    profile_dir.mkdir(parents=True, exist_ok=True)
    profile_path = profile_dir / "profile.json"
    profile_path.write_text(
        json.dumps(asdict(profile), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return profile_path


def link_character_source_asset(
    settings: AppSettings,
    character_id: str,
    asset_path: str | Path,
) -> Path:
    profile = load_character_profile(settings, character_id)
    normalized = project_relative_path(settings, asset_path)
    if normalized in profile.source_assets:
        return character_profile_path(settings, character_id)
    return save_character_profile(
        settings,
        replace(profile, source_assets=[*profile.source_assets, normalized]),
    )


def link_character_2p5d_definition(
    settings: AppSettings,
    character_id: str,
    definition_path: str | Path,
) -> Path:
    profile = load_character_profile(settings, character_id)
    normalized = project_relative_path(settings, definition_path)
    return save_character_profile(
        settings,
        replace(
            profile,
            definition_2p5d=normalized,
            learning_strategy="2p5d_base_lora_completion",
        ),
    )


def project_relative_path(settings: AppSettings, value: str | Path) -> str:
    path = Path(value)
    if not path.is_absolute():
        path = settings.project_root / path
    try:
        return path.resolve().relative_to(settings.project_root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def lora_artifact_from_dict(data: dict[str, object]) -> LoraArtifact:
    return LoraArtifact(
        artifact_id=str(data["artifact_id"]),
        kind=str(data["kind"]),
        status=str(data["status"]),
        display_name=str(data["display_name"]),
        config_dir=str(data.get("config_dir", "")),
        dataset_config=str(data.get("dataset_config", "")),
        training_config=str(data.get("training_config", "")),
        run_script=str(data.get("run_script", "")),
        model_path=str(data.get("model_path", "")),
        output_name=str(data.get("output_name", "")),
        trigger_tags=list(data.get("trigger_tags", [])),
        notes=str(data.get("notes", "")),
        created_at=str(data.get("created_at", "")),
        updated_at=str(data.get("updated_at", "")),
        metadata=dict(data.get("metadata", {})),
    )
