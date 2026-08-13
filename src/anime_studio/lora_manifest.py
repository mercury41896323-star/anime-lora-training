from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from .character_profile import LoraArtifact, load_character_profile, validate_character_id
from .lora_registry import project_relative_path, utc_timestamp
from .settings import AppSettings


@dataclass(frozen=True)
class LoraManifestResult:
    manifest_path: Path
    lora_count: int


def generate_lora_manifest(
    settings: AppSettings,
    character_id: str,
    output_path: str | Path | None = None,
    default_weight: float = 0.75,
) -> LoraManifestResult:
    validate_character_id(character_id)
    profile = load_character_profile(settings, character_id)
    trained_loras = [
        artifact
        for artifact in profile.lora_artifacts
        if artifact.kind == "trained_lora" and artifact.model_path
    ]

    manifest_path = normalize_manifest_path(settings, character_id, output_path)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": 1,
        "manifest_type": "character_lora_manifest",
        "generated_at": utc_timestamp(),
        "character": {
            "character_id": profile.character_id,
            "display_name": profile.display_name,
            "trigger_tags": profile.trigger_tags,
        },
        "defaults": {
            "weight": default_weight,
            "clip_weight": default_weight,
        },
        "loras": [
            render_lora_entry(settings, profile.character_id, artifact, default_weight)
            for artifact in trained_loras
        ],
        "comfyui": {
            "usage_note": "Use model_path with a LoRA Loader node and append prompt_tag to the positive prompt.",
            "positive_prompt_tags": [
                artifact.trigger_tags[0]
                for artifact in trained_loras
                if artifact.trigger_tags
            ],
        },
        "unity": {
            "usage_note": "Treat model_path as an external asset reference for generation requests.",
            "addressable_keys": [
                f"lora/{profile.character_id}/{artifact.artifact_id}"
                for artifact in trained_loras
            ],
        },
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return LoraManifestResult(manifest_path=manifest_path, lora_count=len(trained_loras))


def render_lora_entry(
    settings: AppSettings,
    character_id: str,
    artifact: LoraArtifact,
    default_weight: float,
) -> dict[str, object]:
    prompt_tag = artifact.trigger_tags[0] if artifact.trigger_tags else artifact.output_name
    return {
        "artifact_id": artifact.artifact_id,
        "display_name": artifact.display_name,
        "status": artifact.status,
        "model_path": artifact.model_path,
        "config_dir": artifact.config_dir,
        "prompt_tag": prompt_tag,
        "trigger_tags": artifact.trigger_tags,
        "weight": default_weight,
        "clip_weight": default_weight,
        "comfyui": {
            "lora_name": Path(artifact.model_path).name,
            "loader_hint": "Load LoRA by model_path or copy/link it into ComfyUI/models/loras.",
        },
        "unity": {
            "addressable_key": f"lora/{character_id}/{artifact.artifact_id}",
            "asset_reference": artifact.model_path,
        },
        "notes": artifact.notes,
        "metadata": artifact.metadata,
        "source_profile_path": project_relative_path(
            settings,
            settings.assets.processed / "characters" / character_id / "profile.json",
        ),
    }


def normalize_manifest_path(
    settings: AppSettings,
    character_id: str,
    output_path: str | Path | None,
) -> Path:
    if output_path is None:
        return settings.project_root / "manifests" / "characters" / character_id / "lora_manifest.json"
    path = Path(output_path)
    if not path.is_absolute():
        path = settings.project_root / path
    return path
