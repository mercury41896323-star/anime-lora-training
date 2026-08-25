from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
import hashlib
import json
from pathlib import Path
from typing import Any

from PIL import Image

from .character_profile import load_character_profile, save_character_profile, validate_character_id
from .lora_registry import project_relative_path, utc_timestamp
from .settings import AppSettings, load_settings
from .simple_2p5d_rig import build_readiness_issues, generation_readiness_status, read_json, write_json


REVIEW_MANIFEST_TYPE = "simple_2p5d_rig_review"
READINESS_MANIFEST_TYPE = "simple_2p5d_generation_readiness"
REQUIRED_PARTS = {
    "hair_back", "head", "face", "eyes", "mouth", "hair_front",
    "torso", "left_arm", "right_arm", "hips", "left_leg", "right_leg",
}
CONTROL_IMAGE_SIZE = (512, 768)
MIN_CONTROL_MARGIN_RATIO = 0.05


@dataclass(frozen=True)
class Simple2p5DReviewResult:
    manifest_path: Path
    status: str
    issue_count: int
    warning_count: int


@dataclass(frozen=True)
class Simple2p5DReadinessResult:
    manifest_path: Path
    ready: bool
    issue_count: int


def inspect_simple_2p5d_rig(
    settings: AppSettings,
    character_id: str,
) -> Simple2p5DReviewResult:
    validate_character_id(character_id)
    paths = character_paths(settings, character_id)
    profile = load_character_profile(settings, character_id)
    rig = read_json(paths["rig"])
    definition = read_json(paths["definition"])
    master = read_json(paths["master"])
    bundle = read_json(paths["bundle"])
    previous = read_json(paths["review"])
    issues: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []

    require_manifest(rig, "simple_2p5d_rig", "rig", paths["rig"], issues)
    require_manifest(definition, "character_2p5d_definition", "definition", paths["definition"], issues)
    require_manifest(master, "character_master_asset", "master", paths["master"], issues)
    require_manifest(bundle, "simple_2p5d_control_bundle", "control_bundle", paths["bundle"], issues)

    sections = {
        str(item.get("section_id", ""))
        for item in master.get("section_assets", [])
        if item.get("section_id")
    }
    required_sections = {
        "main_portrait", "turnaround_front", "turnaround_side", "turnaround_back",
        "face_angle_front", "face_angle_45", "face_angle_side", "expressions", "pose_reference",
    }
    missing_sections = sorted(required_sections - sections)
    if missing_sections:
        issues.append(issue("missing_required_crops", ", ".join(missing_sections)))

    parts = {str(item.get("part_id", "")): dict(item) for item in rig.get("parts", [])}
    missing_parts = sorted(REQUIRED_PARTS - set(parts))
    if missing_parts:
        issues.append(issue("missing_rig_parts", ", ".join(missing_parts)))
    for part_id, part in parts.items():
        check_image_reference(settings, str(part.get("mask_image", "")), f"{part_id} mask", issues)
        check_image_reference(settings, str(part.get("transparent_image", "")), f"{part_id} transparent image", issues)
        mesh = dict(part.get("mesh", {}))
        if len(mesh.get("vertices", [])) < 4 or len(mesh.get("triangles", [])) < 2:
            issues.append(issue("invalid_mesh", part_id))

    controls = dict(rig.get("controls", {}))
    for control in ("pose", "depth"):
        check_image_reference(settings, str(controls.get(control, "")), control, issues)
    check_image_reference(settings, str(rig.get("silhouette_mask", "")), "silhouette", issues)
    inspect_mask_layout(settings, str(rig.get("silhouette_mask", "")), issues, warnings)

    if not bool(profile.profile_data.get("training", {}).get("source_rights_confirmed", False)):
        warnings.append(issue("source_rights_unconfirmed", "Confirm source rights before training or distribution."))

    signature = artifact_signature(paths["rig"], paths["definition"], paths["master"])
    preserve_approval = (
        str(previous.get("status", "")) == "approved"
        and str(previous.get("artifact_signature", "")) == signature
        and not issues
    )
    status = "approved" if preserve_approval else "pending_review"
    review = {
        "schema_version": 1,
        "manifest_type": REVIEW_MANIFEST_TYPE,
        "generated_at": utc_timestamp(),
        "character_id": character_id,
        "status": status,
        "artifact_signature": signature,
        "checks": {
            "required_crop_count": len(required_sections),
            "available_crop_count": len(sections),
            "required_part_count": len(REQUIRED_PARTS),
            "available_part_count": len(parts),
            "issue_count": len(issues),
            "warning_count": len(warnings),
        },
        "review_items": {
            "crop_alignment": previous_item(previous, "crop_alignment", preserve_approval),
            "identity_similarity": previous_item(previous, "identity_similarity", preserve_approval),
            "part_masks": previous_item(previous, "part_masks", preserve_approval),
            "depth_order": previous_item(previous, "depth_order", preserve_approval),
            "pose_alignment": previous_item(previous, "pose_alignment", preserve_approval),
            "mesh_pivots": previous_item(previous, "mesh_pivots", preserve_approval),
            "live2d_mapping": previous_item(previous, "live2d_mapping", preserve_approval),
        },
        "approval": dict(previous.get("approval", {})) if preserve_approval else {},
        "issues": issues,
        "warnings": warnings,
        "paths": {key: project_relative_path(settings, value) for key, value in paths.items() if key != "review"},
        "notes": [
            "Automatic checks validate files and schema only.",
            "A person must review identity, masks, depth, pose, pivots, and Live2D mapping.",
        ],
    }
    write_json(paths["review"], review)
    return Simple2p5DReviewResult(paths["review"], status, len(issues), len(warnings))


def approve_simple_2p5d_rig(
    settings: AppSettings,
    character_id: str,
    reviewer: str,
    notes: str = "",
) -> Simple2p5DReviewResult:
    if not reviewer.strip():
        raise ValueError("reviewer is required for 2.5D rig approval.")
    inspection = inspect_simple_2p5d_rig(settings, character_id)
    if inspection.issue_count:
        raise ValueError(f"Cannot approve a rig with {inspection.issue_count} inspection issues.")
    review = read_json(inspection.manifest_path)
    review["status"] = "approved"
    review["review_items"] = {
        key: "approved" for key in dict(review.get("review_items", {}))
    }
    review["approval"] = {
        "reviewer": reviewer.strip(),
        "reviewed_at": utc_timestamp(),
        "notes": notes.strip(),
    }
    update_rig_production_status(settings, character_id, "reviewed")
    paths = character_paths(settings, character_id)
    review["artifact_signature"] = artifact_signature(paths["rig"], paths["definition"], paths["master"])
    write_json(inspection.manifest_path, review)
    return Simple2p5DReviewResult(
        inspection.manifest_path,
        "approved",
        inspection.issue_count,
        inspection.warning_count,
    )


def bind_generation_lora(
    settings: AppSettings,
    character_id: str,
    lora_name: str,
    trigger_tag: str,
    comfyui_lora_dir: str | Path,
    reviewer: str,
) -> Path:
    validate_character_id(character_id)
    if not reviewer.strip():
        raise ValueError("reviewer is required to confirm a generation LoRA binding.")
    if not trigger_tag.strip():
        raise ValueError("trigger_tag is required for a generation LoRA binding.")
    lora_path = Path(comfyui_lora_dir) / lora_name
    if not lora_path.is_file():
        raise FileNotFoundError(f"ComfyUI LoRA does not exist: {lora_path}")

    paths = character_paths(settings, character_id)
    workflow = read_json(paths["workflow"])
    bundle = read_json(paths["bundle"])
    pipeline = read_json(paths["pipeline"])
    if not workflow or not bundle:
        raise FileNotFoundError("Build the Simple 2.5D pipeline before binding a LoRA.")
    lora_node = workflow.get("2", {})
    if str(lora_node.get("class_type", "")) != "LoraLoader":
        raise ValueError("Simple 2.5D workflow does not contain the expected LoraLoader node 2.")
    lora_node.setdefault("inputs", {})["lora_name"] = lora_name
    prompt_inputs = workflow.get("3", {}).setdefault("inputs", {})
    prompt_inputs["text"] = prepend_prompt_tag(str(prompt_inputs.get("text", "")), trigger_tag.strip())
    write_json(paths["workflow"], workflow)

    readiness = dict(bundle.get("readiness", {}))
    readiness["lora"] = True
    identity = dict(bundle.get("generation_stack", {}).get("identity", {}))
    identity.update(
        {
            "model": lora_name,
            "trigger_tag": trigger_tag.strip(),
            "binding_status": "explicitly_confirmed",
        }
    )
    bundle.setdefault("generation_stack", {})["identity"] = identity
    bundle["lora_binding"] = {
        "model": lora_name,
        "model_path": lora_path.resolve().as_posix(),
        "trigger_tag": trigger_tag.strip(),
        "reviewer": reviewer.strip(),
        "bound_at": utc_timestamp(),
        "purpose": "generation_only",
        "note": "This does not claim that the LoRA was trained for this CharacterProfile.",
    }
    bundle["readiness"] = readiness
    bundle["workflow_ready"] = all(readiness.values())
    bundle["readiness_issues"] = build_readiness_issues(readiness)
    write_json(paths["bundle"], bundle)

    if pipeline:
        pipeline["workflow_ready"] = all(readiness.values())
        for step in pipeline.get("steps", []):
            if int(step.get("step", 0) or 0) == 9:
                step["status"] = generation_readiness_status(readiness)
        write_json(paths["pipeline"], pipeline)

    profile = load_character_profile(settings, character_id)
    profile_data = json.loads(json.dumps(profile.profile_data))
    generation = dict(profile_data.get("generation", {}))
    generation["selected_lora"] = lora_name
    generation["selected_lora_trigger"] = trigger_tag.strip()
    generation["selected_lora_binding"] = "explicitly_confirmed"
    profile_data["generation"] = generation
    save_character_profile(settings, replace(profile, profile_data=profile_data))
    return paths["bundle"]


def check_simple_2p5d_generation_readiness(
    settings: AppSettings,
    character_id: str,
    comfyui_controlnet_dir: str | Path,
    comfyui_lora_dir: str | Path,
    comfyui_input_dir: str | Path,
) -> Simple2p5DReadinessResult:
    validate_character_id(character_id)
    inspect_simple_2p5d_rig(settings, character_id)
    paths = character_paths(settings, character_id)
    review = read_json(paths["review"])
    bundle = read_json(paths["bundle"])
    workflow = read_json(paths["workflow"])
    issues: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    if str(review.get("status", "")) != "approved":
        issues.append(issue("rig_not_approved", "Approve crops, masks, depth, pose, mesh, and Live2D mapping."))
    if not workflow:
        issues.append(issue("missing_workflow", str(paths["workflow"])))

    stack = dict(bundle.get("generation_stack", {}))
    lora = str(dict(stack.get("identity", {})).get("model", ""))
    openpose = str(dict(stack.get("pose", {})).get("model", ""))
    depth = str(dict(stack.get("depth", {})).get("model", ""))
    check_model(Path(comfyui_lora_dir), lora, "lora", issues)
    check_model(Path(comfyui_controlnet_dir), openpose, "openpose_controlnet", issues)
    check_model(Path(comfyui_controlnet_dir), depth, "depth_controlnet", issues)
    for name in ("reference.png", "pose.png", "depth.png", "mask.png"):
        path = Path(comfyui_input_dir) / "anime_studio" / character_id / name
        if not path.is_file():
            issues.append(issue("missing_comfyui_input", str(path)))

    if not bool(load_character_profile(settings, character_id).profile_data.get("training", {}).get("source_rights_confirmed", False)):
        warnings.append(issue("source_rights_unconfirmed", "Required before training or distribution, not local generation testing."))
    ready = not issues
    payload = {
        "schema_version": 1,
        "manifest_type": READINESS_MANIFEST_TYPE,
        "generated_at": utc_timestamp(),
        "character_id": character_id,
        "ready": ready,
        "review_status": str(review.get("status", "missing")),
        "counts": {"issue_count": len(issues), "warning_count": len(warnings)},
        "models": {"lora": lora, "openpose_controlnet": openpose, "depth_controlnet": depth},
        "issues": issues,
        "warnings": warnings,
        "next_actions": readiness_actions(issues),
        "paths": {key: project_relative_path(settings, value) for key, value in paths.items()},
    }
    write_json(paths["readiness"], payload)
    return Simple2p5DReadinessResult(paths["readiness"], ready, len(issues))


def character_paths(settings: AppSettings, character_id: str) -> dict[str, Path]:
    manifest_dir = settings.project_root / "manifests" / "characters" / character_id
    rig_dir = settings.assets.processed / "characters" / character_id / "simple_2p5d_rig"
    return {
        "profile": settings.assets.processed / "characters" / character_id / "profile.json",
        "master": manifest_dir / "character_sheet" / "character_master_asset.json",
        "definition": manifest_dir / "character_2p5d_definition.json",
        "rig": rig_dir / "simple_2p5d_rig.json",
        "bundle": rig_dir / "control_bundle.json",
        "workflow": settings.project_root / "outputs" / "comfyui" / character_id / "simple_2p5d_control_workflow.json",
        "live2d": rig_dir / "live2d_bridge.json",
        "pipeline": manifest_dir / "simple_2p5d_pipeline.json",
        "review": manifest_dir / "simple_2p5d_review.json",
        "readiness": manifest_dir / "simple_2p5d_generation_readiness.json",
    }


def require_manifest(
    value: dict[str, Any],
    manifest_type: str,
    label: str,
    path: Path,
    issues: list[dict[str, str]],
) -> None:
    if not value:
        issues.append(issue(f"missing_{label}", str(path)))
    elif str(value.get("manifest_type", "")) != manifest_type:
        issues.append(issue(f"invalid_{label}_type", str(value.get("manifest_type", ""))))


def check_image_reference(
    settings: AppSettings,
    value: str,
    label: str,
    issues: list[dict[str, str]],
) -> None:
    path = resolve_project_path(settings, value)
    if not value or not path.is_file():
        issues.append(issue("missing_image", f"{label}: {path}"))


def inspect_mask_layout(
    settings: AppSettings,
    value: str,
    issues: list[dict[str, str]],
    warnings: list[dict[str, str]],
) -> None:
    path = resolve_project_path(settings, value)
    if not path.is_file():
        return
    with Image.open(path) as image:
        mask = image.convert("L")
        bounds = mask.getbbox()
        histogram = mask.histogram()
        occupied = sum(histogram[1:])
        ratio = occupied / max(1, mask.width * mask.height)
    if mask.size != CONTROL_IMAGE_SIZE:
        issues.append(issue("invalid_control_canvas", f"{mask.width}x{mask.height}; expected 512x768"))
    if bounds is None:
        issues.append(issue("empty_silhouette", str(path)))
        return
    left_margin = bounds[0] / mask.width
    top_margin = bounds[1] / mask.height
    right_margin = (mask.width - bounds[2]) / mask.width
    bottom_margin = (mask.height - bounds[3]) / mask.height
    if top_margin < MIN_CONTROL_MARGIN_RATIO or bottom_margin < MIN_CONTROL_MARGIN_RATIO:
        issues.append(issue("unsafe_vertical_crop", f"top={top_margin:.3f}, bottom={bottom_margin:.3f}"))
    if left_margin < MIN_CONTROL_MARGIN_RATIO or right_margin < MIN_CONTROL_MARGIN_RATIO:
        issues.append(issue("unsafe_horizontal_crop", f"left={left_margin:.3f}, right={right_margin:.3f}"))
    if ratio < 0.08 or ratio > 0.92:
        warnings.append(issue("suspicious_mask_occupancy", f"{ratio:.3f}"))


def artifact_signature(*paths: Path) -> str:
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes() if path.is_file() else b"missing")
    return digest.hexdigest()


def previous_item(previous: dict[str, Any], key: str, preserve: bool) -> str:
    if not preserve:
        return "pending"
    return str(dict(previous.get("review_items", {})).get(key, "approved"))


def update_rig_production_status(settings: AppSettings, character_id: str, status: str) -> None:
    path = character_paths(settings, character_id)["rig"]
    rig = read_json(path)
    rig["production_status"] = status
    rig["reviewed_at"] = utc_timestamp()
    write_json(path, rig)


def check_model(directory: Path, name: str, label: str, issues: list[dict[str, str]]) -> None:
    if not name or name.startswith("{{"):
        issues.append(issue(f"missing_{label}_binding", name or "not set"))
        return
    if not (directory / name).is_file():
        issues.append(issue(f"missing_{label}_file", str(directory / name)))


def prepend_prompt_tag(prompt: str, trigger_tag: str) -> str:
    parts = [part.strip() for part in prompt.split(",") if part.strip()]
    if trigger_tag in parts:
        return prompt
    return ", ".join([trigger_tag, *parts])


def resolve_project_path(settings: AppSettings, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else settings.project_root / path


def issue(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def readiness_actions(issues: list[dict[str, str]]) -> list[str]:
    codes = {item["code"] for item in issues}
    actions: list[str] = []
    if "rig_not_approved" in codes:
        actions.append("Review and approve the Simple 2.5D rig.")
    if any("lora" in code for code in codes):
        actions.append("Bind an explicitly confirmed character LoRA and trigger tag.")
    if any("controlnet" in code for code in codes):
        actions.append("Install or select the matching OpenPose and Depth ControlNet models.")
    if "missing_comfyui_input" in codes:
        actions.append("Copy reference, pose, depth, and mask images into ComfyUI input.")
    if not actions:
        actions.append("Ready to submit the Simple 2.5D workflow to ComfyUI.")
    return actions


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="anime-simple-2p5d-manage",
        description="Inspect, approve, bind a LoRA, and validate Simple 2.5D generation readiness.",
    )
    parser.add_argument("--config", default="config/local_6gb.json")
    subparsers = parser.add_subparsers(dest="command", required=True)
    inspect = subparsers.add_parser("inspect")
    inspect.add_argument("--character-id", required=True)
    approve = subparsers.add_parser("approve")
    approve.add_argument("--character-id", required=True)
    approve.add_argument("--reviewer", required=True)
    approve.add_argument("--notes", default="")
    bind = subparsers.add_parser("bind-lora")
    bind.add_argument("--character-id", required=True)
    bind.add_argument("--lora-name", required=True)
    bind.add_argument("--trigger-tag", required=True)
    bind.add_argument("--comfyui-lora-dir", required=True)
    bind.add_argument("--reviewer", required=True)
    readiness = subparsers.add_parser("readiness")
    readiness.add_argument("--character-id", required=True)
    readiness.add_argument("--comfyui-controlnet-dir", required=True)
    readiness.add_argument("--comfyui-lora-dir", required=True)
    readiness.add_argument("--comfyui-input-dir", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = load_settings(args.config)
    if args.command == "inspect":
        result = inspect_simple_2p5d_rig(settings, args.character_id)
        print(f"Review manifest: {result.manifest_path}")
        print(f"Status: {result.status}")
        print(f"Issues: {result.issue_count}")
        print(f"Warnings: {result.warning_count}")
        return 0 if result.issue_count == 0 else 1
    if args.command == "approve":
        result = approve_simple_2p5d_rig(settings, args.character_id, args.reviewer, args.notes)
        print(f"Review manifest: {result.manifest_path}")
        print(f"Status: {result.status}")
        return 0
    if args.command == "bind-lora":
        path = bind_generation_lora(
            settings, args.character_id, args.lora_name, args.trigger_tag,
            args.comfyui_lora_dir, args.reviewer,
        )
        print(f"Control bundle: {path}")
        return 0
    if args.command == "readiness":
        result = check_simple_2p5d_generation_readiness(
            settings, args.character_id, args.comfyui_controlnet_dir,
            args.comfyui_lora_dir, args.comfyui_input_dir,
        )
        print(f"Readiness manifest: {result.manifest_path}")
        print(f"Ready: {result.ready}")
        print(f"Issues: {result.issue_count}")
        return 0 if result.ready else 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
