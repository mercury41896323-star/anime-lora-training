from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path

from .character_profile import (
    character_profile_path,
    link_character_2p5d_definition,
    load_character_profile,
    validate_character_id,
)
from .lora_registry import project_relative_path, utc_timestamp
from .settings import AppSettings, load_settings


DEFINITION_MANIFEST_TYPE = "character_2p5d_definition"


@dataclass(frozen=True)
class Character2p5DDefinitionResult:
    manifest_path: Path
    character_id: str
    video_id: str


def generate_character_2p5d_definition(
    settings: AppSettings,
    character_id: str,
    source_manifest: str | Path | None = None,
) -> Character2p5DDefinitionResult:
    validate_character_id(character_id)
    master_manifest_path = resolve_master_manifest_path(settings, character_id, source_manifest)
    master_manifest = load_optional_manifest(master_manifest_path)
    profile = load_character_profile(settings, character_id)
    video_id = str(master_manifest.get("video_id", ""))
    coverage = dict(master_manifest.get("coverage", {}))
    paths = dict(master_manifest.get("paths", {}))
    section_assets = {
        str(item.get("section_id", "")): dict(item)
        for item in master_manifest.get("section_assets", [])
        if item.get("section_id")
    }
    profile_sections, profile_references = build_profile_reference_sections(
        settings,
        profile.source_assets,
    )
    for section_id, item in profile_sections.items():
        section_assets.setdefault(section_id, item)
    if profile_references and not coverage:
        coverage = {
            "main_portrait": "ready",
            "face_angles": "needs_review",
            "expressions": "needs_review",
            "full_body": "needs_review",
            "back_view": "needs_review",
            "costume_detail": "needs_review",
        }
    fallback_reference = str(
        paths.get("definition_source_image")
        or paths.get("master_image")
        or paths.get("reviewed_image")
        or (profile_references[0] if profile_references else "")
    )
    view_anchors = build_view_anchors(coverage, section_assets, fallback_reference)
    expression_controls = build_expression_controls(coverage, section_assets, fallback_reference)
    body_controls = build_body_controls(coverage, section_assets, fallback_reference)
    identity_references = collect_identity_references(
        view_anchors,
        expression_controls,
        body_controls,
        fallback_reference,
        profile_references,
    )
    source_kind = "character_master_asset" if master_manifest else "character_profile"

    manifest_path = settings.project_root / "manifests" / "characters" / character_id / "character_2p5d_definition.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "manifest_type": DEFINITION_MANIFEST_TYPE,
                "generated_at": utc_timestamp(),
                "character_id": character_id,
                "video_id": video_id,
                "source_kind": source_kind,
                "source_profile": project_relative_path(
                    settings, character_profile_path(settings, character_id)
                ),
                "source_master_asset": project_relative_path(settings, master_manifest_path)
                if master_manifest
                else "",
                "definition_status": "ready" if identity_references else "needs_master_reference",
                "identity_reference_images": identity_references,
                "view_anchors": view_anchors,
                "expression_controls": expression_controls,
                "body_controls": body_controls,
                "layer_plan": [
                    {"layer_id": "head_base", "purpose": "identity anchor", "status": "manual_review_required"},
                    {"layer_id": "hair_front", "purpose": "front silhouette", "status": "manual_review_required"},
                    {"layer_id": "hair_back", "purpose": "back silhouette", "status": "manual_review_required"},
                    {"layer_id": "eyes", "purpose": "expression control", "status": "manual_review_required"},
                    {"layer_id": "mouth", "purpose": "expression control", "status": "manual_review_required"},
                    {"layer_id": "torso", "purpose": "upper body control", "status": "manual_review_required"},
                ],
                "control_hints": {
                    "lora_role": "residual detail, texture, motion continuity, and rendering completion",
                    "2p5d_role": "primary identity, shape, anchor, and layer control",
                    "recommended_external_controls": ["pose", "composition", "camera direction"],
                },
                "learning_order": [
                    "character_profile",
                    "character_sheet",
                    "2p5d_definition",
                    "lora_residual_completion",
                ],
                "generation_binding": {
                    "comfyui": {
                        "ipadapter_reference_images": identity_references,
                        "controlnet_view_anchors": view_anchors,
                        "prompt_hint": "preserve character master identity and 2.5D view anchors",
                    },
                    "video_control": {
                        "identity_anchor_images": identity_references,
                        "expression_controls": expression_controls,
                        "body_controls": body_controls,
                        "preserve_across_frames": True,
                    },
                    "b_control": {
                        "enabled": bool(identity_references),
                        "definition_manifest": project_relative_path(settings, manifest_path),
                    },
                },
                "notes": [
                    "This definition is a lightweight control manifest, not a fully rigged 2.5D asset.",
                    "External profile images can create identity anchors without a source video.",
                    "LoRA is trained after this definition and complements the 2.5D animation base.",
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    link_character_2p5d_definition(settings, character_id, manifest_path)
    return Character2p5DDefinitionResult(
        manifest_path=manifest_path,
        character_id=character_id,
        video_id=video_id,
    )


def resolve_master_manifest_path(settings: AppSettings, character_id: str, source_manifest: str | Path | None) -> Path:
    if source_manifest not in (None, ""):
        path = Path(source_manifest)
        if not path.is_absolute():
            path = settings.project_root / path
        return path
    return settings.project_root / "manifests" / "characters" / character_id / "character_sheet" / "character_master_asset.json"


def load_optional_manifest(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def build_profile_reference_sections(
    settings: AppSettings,
    source_assets: list[str],
) -> tuple[dict[str, dict[str, object]], list[str]]:
    sections: dict[str, dict[str, object]] = {}
    references: list[str] = []
    fallback_order = [
        "main_portrait",
        "face_angle_45",
        "face_angle_side",
        "pose_reference",
        "expressions",
        "turnaround_back",
    ]
    for value in source_assets:
        path = resolve_profile_asset_path(settings, value)
        if not path.is_file() or path.suffix.lower() not in {
            extension.lower() for extension in settings.image_extensions
        }:
            continue
        relative = project_relative_path(settings, path)
        if relative not in references:
            references.append(relative)
        tags = read_reference_tags(path)
        section_id = infer_profile_section_id(tags)
        if not section_id:
            section_id = fallback_order[min(len(sections), len(fallback_order) - 1)]
        sections.setdefault(
            section_id,
            {
                "section_id": section_id,
                "title": section_id.replace("_", " ").title(),
                "image_path": relative,
                "tags": tags,
                "source_type": "character_profile_asset",
            },
        )
    return sections, references


def resolve_profile_asset_path(settings: AppSettings, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return settings.project_root / path


def read_reference_tags(path: Path) -> list[str]:
    caption_path = path.with_suffix(".txt")
    if not caption_path.is_file():
        return []
    return [
        value.strip().lower().replace(" ", "_")
        for value in caption_path.read_text(encoding="utf-8").split(",")
        if value.strip()
    ]


def infer_profile_section_id(tags: list[str]) -> str:
    combined = " ".join(tags)
    if "back" in combined or "rear" in combined:
        return "turnaround_back"
    if "side" in combined or "profile" in combined:
        return "face_angle_side"
    if "three_quarter" in combined or "45_degree" in combined:
        return "face_angle_45"
    if "full_body" in combined or "pose" in combined:
        return "pose_reference"
    if any(value in combined for value in ("smile", "expression", "angry", "sad")):
        return "expressions"
    if "front" in combined or "portrait" in combined:
        return "main_portrait"
    return ""


def build_view_anchors(
    coverage: dict[str, object],
    sections: dict[str, dict[str, object]] | None = None,
    fallback_reference: str = "",
) -> list[dict[str, str]]:
    sections = sections or {}
    face_status = str(coverage.get("face_angles", "missing"))
    portrait_status = str(coverage.get("main_portrait", "missing"))
    return [
        build_anchor("front", portrait_status, sections, fallback_reference, "main_portrait", "face_angle_front", "turnaround_front"),
        build_anchor("three_quarter", face_status, sections, fallback_reference, "face_angle_45", "main_portrait"),
        build_anchor("side", face_status, sections, fallback_reference, "face_angle_side", "turnaround_side"),
        build_anchor("back", str(coverage.get("back_view", "missing")), sections, fallback_reference, "turnaround_back"),
        build_anchor("up", face_status, sections, fallback_reference, "main_portrait"),
        build_anchor("down", face_status, sections, fallback_reference, "main_portrait"),
    ]


def build_expression_controls(
    coverage: dict[str, object],
    sections: dict[str, dict[str, object]] | None = None,
    fallback_reference: str = "",
) -> list[dict[str, str]]:
    sections = sections or {}
    status = str(coverage.get("expressions", "missing"))
    reference = section_reference(sections, "expressions") or fallback_reference
    return [
        {"control": "neutral", "status": status, "reference_image": reference},
        {"control": "smile", "status": status, "reference_image": reference},
        {"control": "serious", "status": status, "reference_image": reference},
        {"control": "surprised", "status": status, "reference_image": reference},
    ]


def build_body_controls(
    coverage: dict[str, object],
    sections: dict[str, dict[str, object]] | None = None,
    fallback_reference: str = "",
) -> list[dict[str, str]]:
    sections = sections or {}
    status = str(coverage.get("full_body", "missing"))
    pose_reference = section_reference(sections, "pose_reference") or fallback_reference
    return [
        {"control": "head_to_torso_anchor", "status": status, "reference_image": pose_reference},
        {"control": "full_body_pose_anchor", "status": status, "reference_image": pose_reference},
        {"control": "costume_silhouette", "status": str(coverage.get("costume_detail", "missing")), "reference_image": pose_reference},
    ]


def build_anchor(
    view: str,
    status: str,
    sections: dict[str, dict[str, object]],
    fallback_reference: str,
    *section_ids: str,
) -> dict[str, str]:
    reference = ""
    for section_id in section_ids:
        reference = section_reference(sections, section_id)
        if reference:
            break
    return {
        "view": view,
        "status": status,
        "reference_image": reference or fallback_reference,
    }


def section_reference(sections: dict[str, dict[str, object]], section_id: str) -> str:
    return str(sections.get(section_id, {}).get("image_path", ""))


def collect_identity_references(*values) -> list[str]:
    result: list[str] = []
    for value in values:
        if isinstance(value, str):
            candidates = [value]
        else:
            candidates = [
                str(item.get("reference_image", ""))
                if isinstance(item, dict)
                else str(item)
                for item in value
            ]
        for candidate in candidates:
            if candidate and candidate not in result:
                result.append(candidate)
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="anime-character-2p5d",
        description="Generate a 2.5D definition from a CharacterProfile or Character Master Asset.",
    )
    parser.add_argument("--config", default="config/local_6gb.json", help="Path to the local runtime profile.")
    parser.add_argument("--character-id", required=True, help="Character id.")
    parser.add_argument("--source-manifest", default=None, help="Optional source character master asset manifest.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    settings = load_settings(args.config)
    result = generate_character_2p5d_definition(
        settings=settings,
        character_id=args.character_id,
        source_manifest=args.source_manifest,
    )
    print(f"2.5D definition: {result.manifest_path}")
    print(f"Character: {result.character_id}")
    print(f"Video id: {result.video_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
