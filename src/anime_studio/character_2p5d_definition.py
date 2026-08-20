from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path

from .character_profile import validate_character_id
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
    master_manifest = json.loads(master_manifest_path.read_text(encoding="utf-8"))
    video_id = str(master_manifest.get("video_id", ""))
    coverage = dict(master_manifest.get("coverage", {}))

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
                "source_master_asset": project_relative_path(settings, master_manifest_path),
                "view_anchors": build_view_anchors(coverage),
                "expression_controls": build_expression_controls(coverage),
                "body_controls": build_body_controls(coverage),
                "layer_plan": [
                    {"layer_id": "head_base", "purpose": "identity anchor", "status": "manual_review_required"},
                    {"layer_id": "hair_front", "purpose": "front silhouette", "status": "manual_review_required"},
                    {"layer_id": "hair_back", "purpose": "back silhouette", "status": "manual_review_required"},
                    {"layer_id": "eyes", "purpose": "expression control", "status": "manual_review_required"},
                    {"layer_id": "mouth", "purpose": "expression control", "status": "manual_review_required"},
                    {"layer_id": "torso", "purpose": "upper body control", "status": "manual_review_required"},
                ],
                "control_hints": {
                    "lora_role": "appearance and style consistency",
                    "2p5d_role": "shape, anchor, and layer control",
                    "recommended_external_controls": ["pose", "composition", "camera direction"],
                },
                "notes": [
                    "This definition is a lightweight control manifest, not a fully rigged 2.5D asset.",
                    "Promote reviewed layers or crops into an external 2.5D tool after manual review.",
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
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


def build_view_anchors(coverage: dict[str, object]) -> list[dict[str, str]]:
    face_status = str(coverage.get("face_angles", "missing"))
    portrait_status = str(coverage.get("main_portrait", "missing"))
    return [
        {"view": "front", "status": portrait_status},
        {"view": "three_quarter", "status": face_status},
        {"view": "side", "status": face_status},
        {"view": "back", "status": str(coverage.get("back_view", "missing"))},
        {"view": "up", "status": face_status},
        {"view": "down", "status": face_status},
    ]


def build_expression_controls(coverage: dict[str, object]) -> list[dict[str, str]]:
    status = str(coverage.get("expressions", "missing"))
    return [
        {"control": "neutral", "status": status},
        {"control": "smile", "status": status},
        {"control": "serious", "status": status},
        {"control": "surprised", "status": status},
    ]


def build_body_controls(coverage: dict[str, object]) -> list[dict[str, str]]:
    status = str(coverage.get("full_body", "missing"))
    return [
        {"control": "head_to_torso_anchor", "status": status},
        {"control": "full_body_pose_anchor", "status": status},
        {"control": "costume_silhouette", "status": str(coverage.get("costume_detail", "missing"))},
    ]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="anime-character-2p5d",
        description="Generate a lightweight 2.5D definition manifest from a character master asset.",
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
