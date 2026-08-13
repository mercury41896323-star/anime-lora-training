from __future__ import annotations

from dataclasses import dataclass
import copy
import json
from pathlib import Path
from typing import Any

from .character_profile import validate_character_id
from .lora_manifest import generate_lora_manifest, normalize_manifest_path
from .settings import AppSettings


@dataclass(frozen=True)
class ComfyWorkflowExportResult:
    workflow_path: Path
    manifest_path: Path
    template_path: Path
    lora_name: str


DEFAULT_COMFYUI_TEMPLATE = Path("templates/comfyui/sd15_lora_txt2img_512.json")
COMFYUI_TEMPLATE_DIR = Path("templates/comfyui")


def export_comfyui_workflow(
    settings: AppSettings,
    character_id: str,
    template_path: str | Path | None = None,
    output_path: str | Path | None = None,
    manifest_path: str | Path | None = None,
    lora_index: int = 0,
) -> ComfyWorkflowExportResult:
    validate_character_id(character_id)
    resolved_manifest = normalize_manifest_path(settings, character_id, manifest_path)
    if not resolved_manifest.exists():
        generate_lora_manifest(settings, character_id, output_path=resolved_manifest)

    manifest = json.loads(resolved_manifest.read_text(encoding="utf-8-sig"))
    loras = list(manifest.get("loras", []))
    if not loras:
        raise ValueError(f"No trained LoRA entries in manifest: {resolved_manifest}")
    if lora_index < 0 or lora_index >= len(loras):
        raise IndexError(f"lora_index out of range: {lora_index}")

    selected_lora = dict(loras[lora_index])
    resolved_template = normalize_workflow_template_path(settings, template_path)
    workflow = json.loads(resolved_template.read_text(encoding="utf-8-sig"))
    tokens = build_placeholder_tokens(manifest, selected_lora)
    workflow = replace_placeholders(workflow, tokens)
    workflow = inject_lora_loader(workflow, selected_lora)

    resolved_output = normalize_workflow_output_path(
        settings,
        character_id,
        output_path,
        resolved_template,
    )
    resolved_output.parent.mkdir(parents=True, exist_ok=True)
    resolved_output.write_text(
        json.dumps(workflow, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    lora_name = str(selected_lora.get("comfyui", {}).get("lora_name", ""))
    return ComfyWorkflowExportResult(
        workflow_path=resolved_output,
        manifest_path=resolved_manifest,
        template_path=resolved_template,
        lora_name=lora_name,
    )


def list_comfyui_templates(settings: AppSettings) -> list[Path]:
    template_dir = settings.project_root / COMFYUI_TEMPLATE_DIR
    if not template_dir.exists():
        return []
    return sorted(path for path in template_dir.glob("*.json") if path.is_file())


def normalize_workflow_template_path(
    settings: AppSettings,
    template_path: str | Path | None,
) -> Path:
    if template_path is None:
        return settings.project_root / DEFAULT_COMFYUI_TEMPLATE

    path = Path(template_path)
    if path.is_absolute():
        return path

    candidates = [settings.project_root / path]
    if len(path.parts) == 1:
        template_dir = settings.project_root / COMFYUI_TEMPLATE_DIR
        candidates.append(template_dir / path)
        if path.suffix != ".json":
            candidates.append(template_dir / f"{path}.json")

    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def build_placeholder_tokens(
    manifest: dict[str, Any],
    selected_lora: dict[str, Any],
) -> dict[str, Any]:
    character = dict(manifest.get("character", {}))
    comfyui = dict(selected_lora.get("comfyui", {}))
    defaults = dict(manifest.get("defaults", {}))
    trigger_tags = list(character.get("trigger_tags", []))
    positive_prompt_tags = list(manifest.get("comfyui", {}).get("positive_prompt_tags", []))
    weight = selected_lora.get("weight", defaults.get("weight", 0.75))
    clip_weight = selected_lora.get("clip_weight", defaults.get("clip_weight", weight))
    return {
        "{{character_id}}": character.get("character_id", ""),
        "{{display_name}}": character.get("display_name", ""),
        "{{trigger_tags}}": ", ".join(trigger_tags),
        "{{positive_prompt_tags}}": ", ".join(positive_prompt_tags),
        "{{artifact_id}}": selected_lora.get("artifact_id", ""),
        "{{prompt_tag}}": selected_lora.get("prompt_tag", ""),
        "{{lora_name}}": comfyui.get("lora_name", ""),
        "{{lora_model_path}}": selected_lora.get("model_path", ""),
        "{{lora_weight}}": weight,
        "{{clip_weight}}": clip_weight,
    }


def replace_placeholders(value: Any, tokens: dict[str, Any]) -> Any:
    if isinstance(value, dict):
        return {
            key: replace_placeholders(item, tokens)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [replace_placeholders(item, tokens) for item in value]
    if isinstance(value, str):
        if value in tokens:
            return tokens[value]
        replaced = value
        for token, replacement in tokens.items():
            replaced = replaced.replace(token, str(replacement))
        return replaced
    return value


def inject_lora_loader(workflow: Any, selected_lora: dict[str, Any]) -> Any:
    injected = copy.deepcopy(workflow)
    lora_name = selected_lora.get("comfyui", {}).get("lora_name", "")
    weight = selected_lora.get("weight", 0.75)
    clip_weight = selected_lora.get("clip_weight", weight)
    for node in iter_comfyui_nodes(injected):
        class_type = str(node.get("class_type", ""))
        if class_type not in {"LoraLoader", "LoraLoaderModelOnly"}:
            continue
        inputs = node.setdefault("inputs", {})
        if "lora_name" in inputs or class_type == "LoraLoader":
            inputs["lora_name"] = lora_name
        if "strength_model" in inputs or class_type == "LoraLoader":
            inputs["strength_model"] = weight
        if class_type == "LoraLoader" and ("strength_clip" in inputs or "clip" in inputs):
            inputs["strength_clip"] = clip_weight
    return injected


def iter_comfyui_nodes(value: Any):
    if isinstance(value, dict):
        if "class_type" in value and isinstance(value.get("inputs", {}), dict):
            yield value
        for item in value.values():
            yield from iter_comfyui_nodes(item)
    elif isinstance(value, list):
        for item in value:
            yield from iter_comfyui_nodes(item)


def normalize_workflow_output_path(
    settings: AppSettings,
    character_id: str,
    output_path: str | Path | None,
    template_path: Path,
) -> Path:
    if output_path is None:
        return (
            settings.project_root
            / "outputs"
            / "comfyui"
            / character_id
            / f"{template_path.stem}_with_lora.json"
        )
    return normalize_project_path(settings, output_path)


def normalize_project_path(settings: AppSettings, path: str | Path) -> Path:
    resolved = Path(path)
    if not resolved.is_absolute():
        resolved = settings.project_root / resolved
    return resolved
