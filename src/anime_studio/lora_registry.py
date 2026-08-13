from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
import re
from pathlib import Path

from .character_profile import (
    LoraArtifact,
    load_character_profile,
    save_character_profile,
    validate_character_id,
)
from .settings import AppSettings


ARTIFACT_ID_PATTERN = re.compile(r"[^a-z0-9_-]+")


@dataclass(frozen=True)
class LoraRegistryResult:
    profile_path: Path
    artifact: LoraArtifact


def link_kohya_config(
    settings: AppSettings,
    character_id: str,
    config_dir: Path,
    dataset_config: Path,
    training_config: Path,
    run_script: Path,
    output_name: str,
    dataset_image_count: int,
    trigger_tags: list[str],
) -> LoraRegistryResult:
    validate_character_id(character_id)
    timestamp = utc_timestamp()
    artifact = LoraArtifact(
        artifact_id="kohya_low_vram_config",
        kind="kohya_config",
        status="configured",
        display_name="Kohya low-VRAM config",
        config_dir=project_relative_path(settings, config_dir),
        dataset_config=project_relative_path(settings, dataset_config),
        training_config=project_relative_path(settings, training_config),
        run_script=project_relative_path(settings, run_script),
        output_name=output_name,
        trigger_tags=trigger_tags,
        notes="Generated low-VRAM LoRA training config. Review before training.",
        created_at=timestamp,
        updated_at=timestamp,
        metadata={
            "dataset_image_count": dataset_image_count,
            "profile": "low_vram_rtx3050_6gb",
        },
    )
    return upsert_lora_artifact(settings, character_id, artifact)


def register_lora_result(
    settings: AppSettings,
    character_id: str,
    model_path: str | Path,
    source_config_dir: str | Path | None = None,
    display_name: str | None = None,
    notes: str = "",
    status: str = "trained",
) -> LoraRegistryResult:
    validate_character_id(character_id)
    profile = load_character_profile(settings, character_id)
    normalized_model_path = project_relative_path(settings, normalize_project_path(settings, model_path))
    timestamp = utc_timestamp()
    artifact_id = build_artifact_id(Path(str(model_path)).stem or character_id)
    config_dir = (
        project_relative_path(settings, normalize_project_path(settings, source_config_dir))
        if source_config_dir
        else project_relative_path(settings, settings.project_root / "config" / "kohya" / character_id)
    )
    artifact = LoraArtifact(
        artifact_id=artifact_id,
        kind="trained_lora",
        status=status,
        display_name=display_name or artifact_id.replace("_", " "),
        config_dir=config_dir,
        model_path=normalized_model_path,
        output_name=Path(str(model_path)).stem,
        trigger_tags=profile.trigger_tags,
        notes=notes,
        created_at=timestamp,
        updated_at=timestamp,
        metadata={
            "source": "manual_registration",
        },
    )
    return upsert_lora_artifact(settings, character_id, artifact)


def list_lora_artifacts(settings: AppSettings, character_id: str) -> list[LoraArtifact]:
    return load_character_profile(settings, character_id).lora_artifacts


def upsert_lora_artifact(
    settings: AppSettings,
    character_id: str,
    artifact: LoraArtifact,
) -> LoraRegistryResult:
    profile = load_character_profile(settings, character_id)
    existing = {item.artifact_id: item for item in profile.lora_artifacts}
    previous = existing.get(artifact.artifact_id)
    created_at = previous.created_at if previous and previous.created_at else artifact.created_at
    artifact = replace(artifact, created_at=created_at, updated_at=utc_timestamp())
    artifacts = [
        item for item in profile.lora_artifacts
        if item.artifact_id != artifact.artifact_id
    ]
    artifacts.append(artifact)

    lora_files = list(profile.lora_files)
    if artifact.model_path and artifact.model_path not in lora_files:
        lora_files.append(artifact.model_path)

    updated_profile = replace(
        profile,
        lora_files=lora_files,
        lora_artifacts=artifacts,
    )
    profile_path = save_character_profile(settings, updated_profile)
    return LoraRegistryResult(profile_path=profile_path, artifact=artifact)


def build_artifact_id(raw_name: str) -> str:
    artifact_id = ARTIFACT_ID_PATTERN.sub("_", raw_name.lower()).strip("_")
    return artifact_id or "lora_result"


def normalize_project_path(settings: AppSettings, path: str | Path) -> Path:
    normalized = Path(path)
    if not normalized.is_absolute():
        normalized = settings.project_root / normalized
    return normalized


def project_relative_path(settings: AppSettings, path: str | Path) -> str:
    normalized = normalize_project_path(settings, path).resolve()
    try:
        return normalized.relative_to(settings.project_root.resolve()).as_posix()
    except ValueError:
        return str(normalized)


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
