from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from .character_profile import load_character_profile
from .lora_registry import project_relative_path, utc_timestamp
from .phase6_pipeline import get_motion_cues_path, read_cue_items
from .settings import AppSettings
from .storyboard import Shot, Storyboard, get_storyboard_path, load_storyboard
from .storyboard_editor_manifest import normalize_editor_manifest_path
from .storyboard_production import (
    CameraWork,
    LightingSetup,
    load_camera_work_map,
    load_lighting_setup_map,
)


B_CONTROL_MANIFEST_TYPE = "storyboard_b_control_manifest"


@dataclass(frozen=True)
class BControlManifestResult:
    manifest_path: Path
    shot_count: int
    controlled_shot_count: int


def export_b_control_manifest(
    settings: AppSettings,
    story_id: str,
    output_path: str | Path | None = None,
) -> BControlManifestResult:
    storyboard = load_storyboard(settings, story_id)
    selected_manifest = read_optional_manifest(normalize_editor_manifest_path(settings, story_id, None))
    selected_by_shot = {
        str(item.get("shot_id", "")): dict(item)
        for item in selected_manifest.get("shots", [])
    }
    camera_by_shot = load_camera_work_map(settings, story_id)
    lighting_by_shot = load_lighting_setup_map(settings, story_id)
    motion_by_shot = group_motion_by_shot(settings, story_id)

    controls: list[dict[str, Any]] = []
    for shot in sorted(storyboard.shots, key=lambda item: item.order):
        controls.append(
            build_b_control_entry(
                settings=settings,
                storyboard=storyboard,
                shot=shot,
                selected_shot=selected_by_shot.get(shot.shot_id, {}),
                camera=camera_by_shot.get(shot.shot_id),
                lighting=lighting_by_shot.get(shot.shot_id),
                motion_cues=motion_by_shot.get(shot.shot_id, []),
            )
        )

    manifest_path = normalize_b_control_manifest_path(settings, story_id, output_path)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "manifest_type": B_CONTROL_MANIFEST_TYPE,
                "generated_at": utc_timestamp(),
                "story": {
                    "story_id": storyboard.story_id,
                    "title": storyboard.title,
                },
                "counts": {
                    "shot_count": len(controls),
                    "controlled_shot_count": sum(1 for item in controls if item["controls"]["enabled"]),
                },
                "shots": controls,
                "notes": [
                    "B-control is for structured generation guidance beyond prompt-only image generation.",
                    "This lightweight manifest prepares face direction, pose, motion, camera, and lighting constraints for ComfyUI export.",
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return BControlManifestResult(
        manifest_path=manifest_path,
        shot_count=len(controls),
        controlled_shot_count=sum(1 for item in controls if item["controls"]["enabled"]),
    )


def build_b_control_entry(
    settings: AppSettings,
    storyboard: Storyboard,
    shot: Shot,
    selected_shot: dict[str, Any],
    camera: CameraWork | None,
    lighting: LightingSetup | None,
    motion_cues: list[dict[str, Any]],
) -> dict[str, Any]:
    selected_result = dict(selected_shot.get("selected_result") or {})
    face_direction = infer_face_direction(shot, camera)
    character_definition = load_character_definition(settings, shot.character_id)
    learned_domain_models = load_learned_domain_models(settings, shot.character_id)
    definition_references = select_definition_references(character_definition, face_direction)
    reference_images = merge_unique(
        definition_references,
        build_reference_images(settings, selected_result),
    )
    motion_intents = [
        {
            "cue_id": str(cue.get("cue_id", "")),
            "target": str(cue.get("target", "")),
            "motion": str(cue.get("motion", "")),
            "source": str(cue.get("source", "")),
            "duration_seconds": float(cue.get("duration_seconds", 0.0) or 0.0),
            "intensity": float(cue.get("intensity", 1.0) or 1.0),
        }
        for cue in motion_cues
    ]
    pose_targets = [item["motion"] for item in motion_intents if item["motion"]]
    preprocessors = infer_preprocessors(camera, lighting, motion_intents, reference_images)
    return {
        "shot_id": shot.shot_id,
        "order": shot.order,
        "title": shot.title,
        "character_id": shot.character_id,
        "duration_seconds": shot.duration_seconds,
        "selected_result": selected_result,
        "character_definition": build_character_definition_binding(
            settings,
            shot.character_id,
            character_definition,
            face_direction,
        ),
        "learned_domain_models": learned_domain_models,
        "controls": {
            "enabled": bool(
                shot.character_id
                and (character_definition or reference_images or motion_intents or camera or lighting)
            ),
            "mode": "B-control",
            "face_direction": face_direction,
            "camera_distance": infer_camera_distance(shot, camera),
            "camera_angle": infer_camera_angle(shot, camera),
            "pose_targets": pose_targets,
            "motion_intents": motion_intents,
            "lighting_direction": infer_lighting_direction(shot, lighting),
            "reference_images": reference_images,
            "design_constraints": [
                "preserve_character_identity",
                "preserve_costume_and_hair_shape",
                "keep_lighting_consistent_across_keyframes",
            ],
            "control_inputs": {
                "openpose": {
                    "enabled": bool(motion_intents),
                    "targets": [item["target"] for item in motion_intents if item["target"]],
                },
                "ipadapter": {
                    "enabled": bool(reference_images),
                    "reference_images": reference_images,
                    "identity_definition": bool(character_definition),
                },
                "controlnet": {
                    "enabled": bool(preprocessors),
                    "preprocessors": preprocessors,
                },
                "animatediff": {
                    "enabled": bool(motion_intents),
                    "motion_bucket": infer_motion_bucket(motion_intents),
                    "character_definition": character_definition.get("generation_binding", {}).get(
                        "video_control", {}
                    )
                    if character_definition
                    else {},
                },
            },
        },
        "camera_work": camera.__dict__ if camera else {},
        "lighting_setup": lighting.__dict__ if lighting else {},
        "phase_targets": {
            "workflow_path": f"outputs/comfyui/storyboards/{storyboard.story_id}/{shot.order:03d}_{shot.shot_id}.json",
            "edit_timeline_manifest": project_relative_path(
                settings,
                settings.project_root / "manifests" / "storyboards" / storyboard.story_id / "edit_timeline_manifest.json",
            ),
        },
    }


def build_reference_images(settings: AppSettings, selected_result: dict[str, Any]) -> list[str]:
    candidates = [
        str(selected_result.get("stored_path", "")),
        str(selected_result.get("source_reference", "")),
    ]
    result: list[str] = []
    for value in candidates:
        if not value:
            continue
        normalized = normalize_result_reference(settings, value)
        if normalized not in result:
            result.append(normalized)
    return result


def load_character_definition(settings: AppSettings, character_id: str) -> dict[str, Any]:
    if not character_id:
        return {}
    path = (
        settings.project_root
        / "manifests"
        / "characters"
        / character_id
        / "character_2p5d_definition.json"
    )
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def load_learned_domain_models(
    settings: AppSettings,
    character_id: str,
) -> dict[str, dict[str, Any]]:
    if not character_id:
        return {}
    try:
        profile = load_character_profile(settings, character_id)
    except FileNotFoundError:
        return {}
    result: dict[str, dict[str, Any]] = {}
    for domain, value in profile.domain_models.items():
        path = Path(value)
        if not path.is_absolute():
            path = settings.project_root / path
        if not path.is_file():
            continue
        model = json.loads(path.read_text(encoding="utf-8-sig"))
        result[domain] = {
            "model_path": project_relative_path(settings, path),
            "model_type": str(model.get("model_type", "")),
            "model_kind": str(model.get("model_kind", "")),
            "provider": str(model.get("provider", "")),
            "status": str(model.get("status", "")),
            "weights": str(model.get("weights", "")),
            "runtime_contract": dict(model.get("runtime_contract") or {}),
            "compatibility": dict(model.get("compatibility") or {}),
            "priors": extract_domain_priors(domain, model),
        }
    return result


def extract_domain_priors(domain: str, model: dict[str, Any]) -> dict[str, Any]:
    keys = {
        "motion": [
            "face_transition_counts",
            "expression_transition_counts",
            "body_transition_counts",
            "average_transition_seconds",
        ],
        "camera": [
            "camera_distance_distribution",
            "face_angle_distribution",
            "recommended_camera_distance",
        ],
        "background": [
            "background_tag_distribution",
            "recommended_background_tags",
        ],
        "lighting": [
            "lighting_tag_distribution",
            "recommended_lighting_tags",
            "shot_lighting_profiles",
        ],
    }.get(domain, [])
    return {key: model.get(key) for key in keys if key in model}


def select_definition_references(definition: dict[str, Any], face_direction: str) -> list[str]:
    if not definition:
        return []
    result: list[str] = []
    for anchor in definition.get("view_anchors", []):
        if str(anchor.get("view", "")) == face_direction:
            append_unique(result, str(anchor.get("reference_image", "")))
    for value in definition.get("identity_reference_images", []):
        append_unique(result, str(value))
    return result


def build_character_definition_binding(
    settings: AppSettings,
    character_id: str,
    definition: dict[str, Any],
    face_direction: str,
) -> dict[str, Any]:
    if not definition:
        return {}
    path = (
        settings.project_root
        / "manifests"
        / "characters"
        / character_id
        / "character_2p5d_definition.json"
    )
    selected_anchor = next(
        (
            dict(anchor)
            for anchor in definition.get("view_anchors", [])
            if str(anchor.get("view", "")) == face_direction
        ),
        {},
    )
    return {
        "manifest_path": project_relative_path(settings, path),
        "definition_status": str(definition.get("definition_status", "")),
        "source_master_asset": str(definition.get("source_master_asset", "")),
        "selected_view_anchor": selected_anchor,
        "identity_reference_images": [
            str(value) for value in definition.get("identity_reference_images", [])
        ],
        "expression_controls": list(definition.get("expression_controls", [])),
        "body_controls": list(definition.get("body_controls", [])),
        "generation_binding": dict(definition.get("generation_binding", {})),
    }


def merge_unique(*groups: list[str]) -> list[str]:
    result: list[str] = []
    for group in groups:
        for value in group:
            append_unique(result, value)
    return result


def append_unique(values: list[str], value: str) -> None:
    normalized = value.strip().replace("\\", "/")
    if normalized and normalized not in values:
        values.append(normalized)


def infer_face_direction(shot: Shot, camera: CameraWork | None) -> str:
    text = combined_text(
        shot.prompt,
        shot.camera,
        shot.notes,
        getattr(camera, "angle", ""),
        getattr(camera, "notes", ""),
    )
    if contains_any(text, "profile", "side", "横顔", "side_view"):
        return "side"
    if contains_any(text, "three-quarter", "three quarter", "45", "斜め"):
        return "three_quarter"
    if contains_any(text, "up", "looking up", "見上げ"):
        return "up"
    if contains_any(text, "down", "looking down", "俯瞰", "見下ろ"):
        return "down"
    if contains_any(text, "back", "rear", "後ろ"):
        return "back"
    if contains_any(text, "front", "正面", "looking at viewer"):
        return "front"
    return "front"


def infer_camera_distance(shot: Shot, camera: CameraWork | None) -> str:
    text = combined_text(shot.camera, getattr(camera, "framing", ""))
    if contains_any(text, "close-up", "close up", "portrait", "顔"):
        return "close_up"
    if contains_any(text, "bust-up", "bust up", "upper body", "waist up"):
        return "upper_body"
    if contains_any(text, "full body", "full-body", "全身"):
        return "full_body"
    if contains_any(text, "wide", "long shot", "引き"):
        return "wide"
    return "medium"


def infer_camera_angle(shot: Shot, camera: CameraWork | None) -> str:
    text = combined_text(shot.camera, getattr(camera, "angle", ""), getattr(camera, "notes", ""))
    if contains_any(text, "low angle", "ローアングル"):
        return "low_angle"
    if contains_any(text, "high angle", "ハイアングル", "俯瞰"):
        return "high_angle"
    if contains_any(text, "side", "横", "profile"):
        return "side"
    return "front"


def infer_lighting_direction(shot: Shot, lighting: LightingSetup | None) -> str:
    text = combined_text(shot.lighting, getattr(lighting, "key_light", ""), getattr(lighting, "rim_light", ""), getattr(lighting, "notes", ""))
    if contains_any(text, "backlight", "back light", "逆光"):
        return "backlight"
    if contains_any(text, "rim", "rim light"):
        return "rim_light"
    if contains_any(text, "side", "side light", "横光"):
        return "side_light"
    if contains_any(text, "top", "top light", "真上"):
        return "top_light"
    return "front_light"


def infer_preprocessors(
    camera: CameraWork | None,
    lighting: LightingSetup | None,
    motion_intents: list[dict[str, Any]],
    reference_images: list[str],
) -> list[str]:
    values: list[str] = []
    if motion_intents:
        values.append("openpose")
    if reference_images:
        values.append("reference")
    if lighting and (lighting.rim_light or lighting.key_light):
        values.append("depth")
    if camera and camera.angle:
        values.append("lineart")
    return values


def infer_motion_bucket(motion_intents: list[dict[str, Any]]) -> str:
    text = " ".join(str(item.get("motion", "")) for item in motion_intents).lower()
    if contains_any(text, "turn", "rotate", "振り向", "face turn"):
        return "turn"
    if contains_any(text, "walk", "step", "move", "歩", "移動"):
        return "move"
    if contains_any(text, "nod", "bow", "うなず", "お辞儀"):
        return "subtle"
    return "generic"


def build_b_control_prompt_fragment(entry: dict[str, Any]) -> str:
    controls = dict(entry.get("controls") or {})
    character_definition = dict(entry.get("character_definition") or {})
    learned_domain_models = dict(entry.get("learned_domain_models") or {})
    motion_intents = list(controls.get("motion_intents") or [])
    motion_labels = ", ".join(str(item.get("motion", "")) for item in motion_intents if item.get("motion"))
    parts = [
        "B-control guided generation",
        f"face direction {controls.get('face_direction', '')}",
        f"camera distance {controls.get('camera_distance', '')}",
        f"camera angle {controls.get('camera_angle', '')}",
        f"lighting {controls.get('lighting_direction', '')}",
        "character consistency",
        "2.5D character master identity" if character_definition else "",
        build_domain_prior_prompt(learned_domain_models),
        "view anchor " + str(character_definition.get("selected_view_anchor", {}).get("view", ""))
        if character_definition.get("selected_view_anchor")
        else "",
        "in-between continuity" if motion_intents else "",
        motion_labels,
    ]
    seen: list[str] = []
    for part in parts:
        normalized = str(part).strip()
        if normalized and normalized not in seen:
            seen.append(normalized)
    return ", ".join(seen)


def build_domain_prior_prompt(models: dict[str, dict[str, Any]]) -> str:
    parts: list[str] = []
    camera = dict(models.get("camera", {}).get("priors") or {})
    background = dict(models.get("background", {}).get("priors") or {})
    lighting = dict(models.get("lighting", {}).get("priors") or {})
    if camera.get("recommended_camera_distance"):
        parts.append(f"learned camera prior {camera['recommended_camera_distance']}")
    if background.get("recommended_background_tags"):
        parts.append(
            "learned background prior "
            + " ".join(str(value) for value in background["recommended_background_tags"][:3])
        )
    if lighting.get("recommended_lighting_tags"):
        parts.append(
            "learned lighting prior "
            + " ".join(str(value) for value in lighting["recommended_lighting_tags"][:3])
        )
    return ", ".join(parts)


def apply_b_control_to_workflow(workflow: dict[str, Any], entry: dict[str, Any]) -> dict[str, Any]:
    controls = dict(entry.get("controls") or {})
    character_definition = dict(entry.get("character_definition") or {})
    learned_domain_models = dict(entry.get("learned_domain_models") or {})
    meta = workflow.setdefault("meta", {})
    meta["generation_mode"] = "B-control"
    meta["b_control"] = entry
    meta["b_control_reference_images"] = list(controls.get("reference_images") or [])
    meta["b_control_preprocessors"] = list(((controls.get("control_inputs") or {}).get("controlnet") or {}).get("preprocessors") or [])
    meta["character_2p5d_definition"] = character_definition
    meta["learned_domain_models"] = learned_domain_models
    workflow.setdefault("extra", {})
    workflow["extra"]["b_control_hint"] = build_b_control_prompt_fragment(entry)
    workflow["extra"]["character_definition_manifest"] = str(
        character_definition.get("manifest_path", "")
    )

    for node in iter_comfyui_nodes(workflow):
        inputs = node.setdefault("inputs", {})
        if "control_hint" in inputs:
            inputs["control_hint"] = workflow["extra"]["b_control_hint"]
        if "face_direction" in inputs:
            inputs["face_direction"] = controls.get("face_direction", "")
        if "reference_image" in inputs and controls.get("reference_images"):
            inputs["reference_image"] = controls["reference_images"][0]
        if "preprocessor" in inputs:
            preprocessors = list(((controls.get("control_inputs") or {}).get("controlnet") or {}).get("preprocessors") or [])
            if preprocessors:
                inputs["preprocessor"] = preprocessors[0]
    return workflow


def load_b_control_map(settings: AppSettings, story_id: str) -> dict[str, dict[str, Any]]:
    path = normalize_b_control_manifest_path(settings, story_id, None)
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    return {
        str(item.get("shot_id", "")): dict(item)
        for item in data.get("shots", [])
    }


def normalize_b_control_manifest_path(
    settings: AppSettings,
    story_id: str,
    output_path: str | Path | None,
) -> Path:
    if output_path is None:
        return settings.project_root / "manifests" / "storyboards" / story_id / "b_control_manifest.json"
    path = Path(output_path)
    if not path.is_absolute():
        path = settings.project_root / path
    return path


def group_motion_by_shot(settings: AppSettings, story_id: str) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for cue in read_cue_items(get_motion_cues_path(settings, story_id), "storyboard_motion_cues"):
        grouped.setdefault(str(cue.get("shot_id", "")), []).append(dict(cue))
    return grouped


def read_optional_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def normalize_result_reference(settings: AppSettings, value: str) -> str:
    path = Path(value)
    if path.is_absolute():
        return project_relative_path(settings, path)
    return value.replace("\\", "/")


def combined_text(*values: str) -> str:
    return " ".join(str(value or "") for value in values).lower()


def contains_any(text: str, *tokens: str) -> bool:
    return any(token.lower() in text for token in tokens if token)


def iter_comfyui_nodes(value: Any):
    if isinstance(value, dict):
        if "class_type" in value and isinstance(value.get("inputs", {}), dict):
            yield value
        for item in value.values():
            yield from iter_comfyui_nodes(item)
    elif isinstance(value, list):
        for item in value:
            yield from iter_comfyui_nodes(item)
