from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, field
import json
from pathlib import Path

from .character_profile import validate_character_id
from .lora_registry import project_relative_path, utc_timestamp
from .settings import AppSettings, load_settings
from .video_analysis import (
    learning_asset_manifest_path,
    sequence_manifest_path,
)


@dataclass(frozen=True)
class CharacterSheetCandidate:
    asset_id: str
    frame_path: str
    sequence_id: str
    timestamp_seconds: float
    tags: list[str] = field(default_factory=list)
    reason: str = ""


@dataclass(frozen=True)
class CharacterSheetSection:
    section_id: str
    title: str
    status: str
    required: bool
    candidates: list[CharacterSheetCandidate] = field(default_factory=list)
    notes: str = ""


@dataclass(frozen=True)
class CharacterSheetDraftResult:
    draft_manifest_path: Path
    completeness_manifest_path: Path
    video_id: str
    section_count: int
    ready_sections: int
    missing_sections: int


REQUIRED_SECTIONS = (
    "main_portrait",
    "face_angles",
    "expressions",
    "full_body",
)


OPTIONAL_SECTION_TITLES = {
    "costume_detail": "Costume Detail",
    "hair_detail": "Hair Detail",
    "back_view": "Back View",
    "color_palette": "Color Palette",
}


def generate_character_sheet_draft(
    settings: AppSettings,
    character_id: str,
    video_id: str,
    max_face_angles: int = 6,
    max_expression_frames: int = 6,
    max_full_body_frames: int = 6,
) -> CharacterSheetDraftResult:
    validate_character_id(character_id)
    if max_face_angles <= 0:
        raise ValueError("max_face_angles must be greater than 0.")
    if max_expression_frames <= 0:
        raise ValueError("max_expression_frames must be greater than 0.")
    if max_full_body_frames <= 0:
        raise ValueError("max_full_body_frames must be greater than 0.")

    sequence_manifest = load_json(sequence_manifest_path(settings, character_id, video_id))
    asset_manifest = load_json(learning_asset_manifest_path(settings, character_id, video_id))

    assets = list(asset_manifest.get("assets", []))
    sequences = {item["sequence_id"]: item for item in sequence_manifest.get("sequences", [])}

    main_candidate = select_main_portrait_candidate(assets)
    face_angle_candidates = select_unique_candidates(
        assets,
        lambda item: item.get("role") == "keyframe",
        limit=max_face_angles,
        reason="Sequence keyframe candidate for face angle review.",
    )
    expression_candidates = select_unique_candidates(
        assets,
        lambda item: item.get("role") == "keyframe"
        and item.get("metadata", {}).get("frame_role") in {"middle", "end"},
        limit=max_expression_frames,
        reason="Sequence middle/end frame candidate for expression review.",
    )
    full_body_candidates = select_unique_candidates(
        assets,
        lambda item: item.get("role") == "learning_frame",
        limit=max_full_body_frames,
        reason="Sampled learning frame candidate for pose and full body review.",
    )

    sections = [
        CharacterSheetSection(
            section_id="main_portrait",
            title="Main Portrait",
            status="ready" if main_candidate else "missing",
            required=True,
            candidates=[main_candidate] if main_candidate else [],
            notes="Use as the first identity anchor for manual review.",
        ),
        CharacterSheetSection(
            section_id="face_angles",
            title="Face Angles",
            status=section_status(face_angle_candidates, minimum_ready=3),
            required=True,
            candidates=face_angle_candidates,
            notes="Covers start / middle / end keyframes across sequences.",
        ),
        CharacterSheetSection(
            section_id="expressions",
            title="Expressions",
            status=section_status(expression_candidates, minimum_ready=2),
            required=True,
            candidates=expression_candidates,
            notes="Expression labels are not inferred yet; human review is required.",
        ),
        CharacterSheetSection(
            section_id="full_body",
            title="Full Body / Pose",
            status=section_status(full_body_candidates, minimum_ready=2),
            required=True,
            candidates=full_body_candidates,
            notes="Sampled frames act as provisional pose / silhouette references.",
        ),
    ]

    for section_id, title in OPTIONAL_SECTION_TITLES.items():
        sections.append(
            CharacterSheetSection(
                section_id=section_id,
                title=title,
                status="missing",
                required=False,
                candidates=[],
                notes="Not auto-detected in the lightweight draft stage.",
            )
        )

    draft_manifest = {
        "schema_version": 1,
        "manifest_type": "character_sheet_draft",
        "generated_at": utc_timestamp(),
        "character_id": character_id,
        "video_id": video_id,
        "source_manifests": {
            "sequence_manifest": project_relative_path(
                settings, sequence_manifest_path(settings, character_id, video_id)
            ),
            "learning_asset_manifest": project_relative_path(
                settings, learning_asset_manifest_path(settings, character_id, video_id)
            ),
        },
        "sections": [asdict(section) for section in sections],
        "sequence_references": build_sequence_references(sequences),
        "notes": [
            "This draft is a lightweight candidate sheet, not a final approved character sheet.",
            "Missing sections are expected until Shot Detector, classifier, and external review are added.",
        ],
    }

    completeness_manifest = build_completeness_manifest(
        settings=settings,
        character_id=character_id,
        video_id=video_id,
        sections=sections,
    )

    draft_path = character_sheet_draft_path(settings, character_id, video_id)
    completeness_path = character_sheet_completeness_path(settings, character_id, video_id)
    draft_path.parent.mkdir(parents=True, exist_ok=True)
    draft_path.write_text(json.dumps(draft_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    completeness_path.write_text(
        json.dumps(completeness_manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    ready_sections = sum(1 for section in sections if section.status == "ready")
    missing_sections = sum(1 for section in sections if section.status == "missing")
    return CharacterSheetDraftResult(
        draft_manifest_path=draft_path,
        completeness_manifest_path=completeness_path,
        video_id=video_id,
        section_count=len(sections),
        ready_sections=ready_sections,
        missing_sections=missing_sections,
    )


def load_json(path: Path) -> dict[str, object]:
    if not path.exists():
        raise FileNotFoundError(f"Required manifest does not exist: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def select_main_portrait_candidate(assets: list[dict[str, object]]) -> CharacterSheetCandidate | None:
    preferred = [
        item
        for item in assets
        if item.get("metadata", {}).get("frame_role") == "middle"
    ]
    if not preferred:
        preferred = [item for item in assets if item.get("role") == "keyframe"]
    if not preferred:
        return None
    return candidate_from_asset(
        preferred[0],
        reason="Preferred middle keyframe candidate for identity anchor.",
    )


def select_unique_candidates(
    assets: list[dict[str, object]],
    predicate,
    *,
    limit: int,
    reason: str,
) -> list[CharacterSheetCandidate]:
    selected: list[CharacterSheetCandidate] = []
    seen_paths: set[str] = set()
    for item in assets:
        if not predicate(item):
            continue
        frame_path = str(item.get("frame_path", ""))
        if not frame_path or frame_path in seen_paths:
            continue
        seen_paths.add(frame_path)
        selected.append(candidate_from_asset(item, reason=reason))
        if len(selected) >= limit:
            break
    return selected


def candidate_from_asset(asset: dict[str, object], reason: str) -> CharacterSheetCandidate:
    return CharacterSheetCandidate(
        asset_id=str(asset.get("asset_id", "")),
        frame_path=str(asset.get("frame_path", "")),
        sequence_id=str(asset.get("sequence_id", "")),
        timestamp_seconds=float(asset.get("timestamp_seconds", 0.0)),
        tags=[str(tag) for tag in asset.get("tags", [])],
        reason=reason,
    )


def section_status(candidates: list[CharacterSheetCandidate], minimum_ready: int) -> str:
    if len(candidates) >= minimum_ready:
        return "ready"
    if candidates:
        return "needs_review"
    return "missing"


def build_sequence_references(sequences: dict[str, dict[str, object]]) -> list[dict[str, object]]:
    ordered = sorted(sequences.values(), key=lambda item: int(item.get("order", 0)))
    references: list[dict[str, object]] = []
    for item in ordered:
        references.append(
            {
                "sequence_id": item.get("sequence_id", ""),
                "order": item.get("order", 0),
                "start_seconds": item.get("start_seconds", 0.0),
                "end_seconds": item.get("end_seconds", 0.0),
                "frame_count": item.get("frame_count", 0),
                "key_frames": [frame.get("frame_path", "") for frame in item.get("key_frames", [])],
            }
        )
    return references


def build_completeness_manifest(
    settings: AppSettings,
    character_id: str,
    video_id: str,
    sections: list[CharacterSheetSection],
) -> dict[str, object]:
    status_map = {section.section_id: section.status for section in sections}
    required_ready = sum(1 for section in sections if section.required and section.status == "ready")
    required_total = sum(1 for section in sections if section.required)
    return {
        "schema_version": 1,
        "manifest_type": "character_sheet_completeness",
        "generated_at": utc_timestamp(),
        "character_id": character_id,
        "video_id": video_id,
        "paths": {
            "draft_manifest": project_relative_path(
                settings, character_sheet_draft_path(settings, character_id, video_id)
            ),
        },
        "required_sections": {
            "ready": required_ready,
            "total": required_total,
        },
        "statuses": status_map,
        "next_steps": [
            "Review main portrait and face angles for identity stability.",
            "Promote accepted frames into a reviewed character sheet.",
            "Fill missing sections after Shot Detector, classifier, or manual correction.",
        ],
        "phase35_ready": required_ready == required_total,
    }


def character_sheet_draft_path(settings: AppSettings, character_id: str, video_id: str) -> Path:
    return (
        settings.project_root
        / "manifests"
        / "characters"
        / character_id
        / "character_sheet"
        / f"{video_id}_draft.json"
    )


def character_sheet_completeness_path(settings: AppSettings, character_id: str, video_id: str) -> Path:
    return (
        settings.project_root
        / "manifests"
        / "characters"
        / character_id
        / "character_sheet"
        / f"{video_id}_completeness.json"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="anime-character-sheet-draft",
        description="Create a lightweight character sheet draft from video analysis manifests.",
    )
    parser.add_argument("--config", default="config/local_6gb.json", help="Path to the local runtime profile.")
    parser.add_argument("--character-id", required=True, help="Character id.")
    parser.add_argument("--video-id", required=True, help="Imported video id / analysis target id.")
    parser.add_argument("--max-face-angles", type=int, default=6, help="Maximum keyframe candidates for face angle review.")
    parser.add_argument("--max-expression-frames", type=int, default=6, help="Maximum keyframe candidates for expression review.")
    parser.add_argument("--max-full-body-frames", type=int, default=6, help="Maximum sampled frames for pose / full body review.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    settings = load_settings(args.config)
    result = generate_character_sheet_draft(
        settings=settings,
        character_id=args.character_id,
        video_id=args.video_id,
        max_face_angles=args.max_face_angles,
        max_expression_frames=args.max_expression_frames,
        max_full_body_frames=args.max_full_body_frames,
    )
    print(f"Draft manifest: {result.draft_manifest_path}")
    print(f"Completeness: {result.completeness_manifest_path}")
    print(f"Video id: {result.video_id}")
    print(f"Sections: {result.section_count}")
    print(f"Ready sections: {result.ready_sections}")
    print(f"Missing sections: {result.missing_sections}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
