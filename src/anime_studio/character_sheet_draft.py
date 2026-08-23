from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, field
import json
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from .character_sheet_importer import DEFAULT_TEMPLATE_V1, TemplateRegion
from .character_profile import validate_character_id
from .lora_registry import project_relative_path, utc_timestamp
from .settings import AppSettings, load_settings
from .video_analysis import (
    learning_asset_manifest_path,
    sequence_manifest_path,
)
from .video_frame_cleaner import clean_frame_manifest_path
from .video_shot_pipeline import classification_manifest_path


@dataclass(frozen=True)
class CharacterSheetCandidate:
    asset_id: str
    frame_path: str
    sequence_id: str
    timestamp_seconds: float
    tags: list[str] = field(default_factory=list)
    reason: str = ""
    face_angle: str = "unknown"
    expression: str = "unknown"
    body_framing: str = "unknown"
    review_status: str = "pending"


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
    draft_sheet_path: Path | None = None
    review_manifest_path: Path | None = None


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

    clean_manifest_path = clean_frame_manifest_path(settings, character_id, video_id)
    classification_path = classification_manifest_path(settings, character_id, video_id)
    clean_manifest = load_optional_json(clean_manifest_path)
    classification_manifest = load_optional_json(classification_path)
    classifications = build_classification_map(classification_manifest)
    clean_assets = build_clean_assets(clean_manifest, classifications)
    assets = clean_assets or list(asset_manifest.get("assets", []))
    sequences = {item["sequence_id"]: item for item in sequence_manifest.get("sequences", [])}

    main_candidate = select_main_portrait_candidate(assets)
    face_angle_candidates = select_unique_candidates(
        assets,
        lambda item: item.get("face_angle", "unknown") != "unknown"
        or item.get("role") == "keyframe",
        limit=max_face_angles,
        reason="Sequence keyframe candidate for face angle review.",
        diversity_key="face_angle",
    )
    expression_candidates = select_unique_candidates(
        assets,
        lambda item: item.get("expression", "unknown") != "unknown"
        or (
            item.get("role") == "keyframe"
            and item.get("metadata", {}).get("frame_role") in {"middle", "end"}
        ),
        limit=max_expression_frames,
        reason="Sequence middle/end frame candidate for expression review.",
        diversity_key="expression",
    )
    full_body_candidates = select_unique_candidates(
        assets,
        lambda item: item.get("body_framing") == "full_body"
        or item.get("role") == "learning_frame",
        limit=max_full_body_frames,
        reason="Sampled learning frame candidate for pose and full body review.",
        diversity_key="body_framing",
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
            "clean_frame_manifest": project_relative_path(settings, clean_manifest_path)
            if clean_manifest_path.exists()
            else "",
            "classification_manifest": project_relative_path(settings, classification_path)
            if classification_path.exists()
            else "",
        },
        "candidate_source": "clean_frames" if clean_assets else "video_analysis",
        "sections": [asdict(section) for section in sections],
        "sequence_references": build_sequence_references(sequences),
        "notes": [
            "This draft is a lightweight candidate sheet, not a final approved character sheet.",
            "The sheet image contains no labels so its fixed regions can be re-imported after human editing.",
            "Human review is required before promoting this draft to reviewed or master.",
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
    draft_sheet_path = character_sheet_draft_image_path(settings, character_id, video_id)
    review_manifest_path = character_sheet_review_manifest_path(settings, character_id, video_id)
    draft_path.parent.mkdir(parents=True, exist_ok=True)
    render_character_sheet_draft(settings, sections, draft_sheet_path)
    review_manifest_path.write_text(
        json.dumps(
            build_review_manifest(settings, character_id, video_id, sections, draft_sheet_path),
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    draft_manifest["draft_sheet_image"] = project_relative_path(settings, draft_sheet_path)
    draft_manifest["review_manifest"] = project_relative_path(settings, review_manifest_path)
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
        draft_sheet_path=draft_sheet_path,
        review_manifest_path=review_manifest_path,
    )


def load_json(path: Path) -> dict[str, object]:
    if not path.exists():
        raise FileNotFoundError(f"Required manifest does not exist: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def load_optional_json(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def build_classification_map(manifest: dict[str, object]) -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for item in manifest.get("classifications", []):
        frame_path = str(item.get("frame_path", ""))
        if frame_path:
            result[frame_path.replace("\\", "/")] = dict(item)
    return result


def build_clean_assets(
    clean_manifest: dict[str, object],
    classifications: dict[str, dict[str, object]],
) -> list[dict[str, object]]:
    assets: list[dict[str, object]] = []
    for index, item in enumerate(clean_manifest.get("frames", []), start=1):
        if item.get("status") != "review_candidate" or not item.get("output_path"):
            continue
        source_path = str(item.get("source_frame_path", "")).replace("\\", "/")
        classification = classifications.get(source_path, {})
        assets.append(
            {
                "asset_id": f"clean_{index:04d}",
                "frame_path": str(item.get("output_path", "")),
                "sequence_id": str(item.get("shot_id", "")),
                "timestamp_seconds": float(item.get("timestamp_seconds", 0.0) or 0.0),
                "role": str(item.get("role", "sampled")),
                "tags": [str(tag) for tag in item.get("tags", [])],
                "face_angle": str(classification.get("face_angle", "unknown")),
                "expression": str(classification.get("expression", "unknown")),
                "body_framing": str(classification.get("body_framing", "unknown")),
                "metadata": {
                    "frame_role": str(item.get("role", "sampled")),
                    "source_frame_path": source_path,
                    "text_free_candidate": bool(item.get("text_free_candidate", False)),
                },
            }
        )
    return assets


def select_main_portrait_candidate(assets: list[dict[str, object]]) -> CharacterSheetCandidate | None:
    preferred = [
        item
        for item in assets
        if item.get("face_angle") == "front"
        and item.get("body_framing") in {"portrait", "upper_body", "unknown"}
    ]
    if not preferred:
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
    diversity_key: str = "",
) -> list[CharacterSheetCandidate]:
    selected: list[CharacterSheetCandidate] = []
    seen_paths: set[str] = set()
    seen_values: set[str] = set()
    matching = [item for item in assets if predicate(item)]
    if diversity_key:
        matching.sort(key=lambda item: str(item.get(diversity_key, "unknown")) in seen_values)
    for item in matching:
        frame_path = str(item.get("frame_path", ""))
        if not frame_path or frame_path in seen_paths:
            continue
        diversity_value = str(item.get(diversity_key, "")) if diversity_key else ""
        if diversity_value and diversity_value != "unknown" and diversity_value in seen_values:
            continue
        seen_paths.add(frame_path)
        if diversity_value and diversity_value != "unknown":
            seen_values.add(diversity_value)
        selected.append(candidate_from_asset(item, reason=reason))
        if len(selected) >= limit:
            break
    if len(selected) < limit and diversity_key:
        for item in matching:
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
        face_angle=str(asset.get("face_angle", "unknown")),
        expression=str(asset.get("expression", "unknown")),
        body_framing=str(asset.get("body_framing", "unknown")),
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


def render_character_sheet_draft(
    settings: AppSettings,
    sections: list[CharacterSheetSection],
    output_path: Path,
    canvas_size: int = 1600,
) -> None:
    section_map = {section.section_id: section for section in sections}
    canvas = Image.new("RGB", (canvas_size, canvas_size), color=(245, 245, 245))
    assignments = build_template_assignments(section_map)
    for region in DEFAULT_TEMPLATE_V1:
        candidates = assignments.get(region.section_id, [])
        if candidates:
            paste_candidates_into_region(settings, canvas, region, candidates)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path, format="PNG", optimize=True)


def build_template_assignments(
    sections: dict[str, CharacterSheetSection],
) -> dict[str, list[CharacterSheetCandidate]]:
    main = list(sections.get("main_portrait", empty_section()).candidates)
    face = list(sections.get("face_angles", empty_section()).candidates)
    expressions = list(sections.get("expressions", empty_section()).candidates)
    full_body = list(sections.get("full_body", empty_section()).candidates)
    return {
        "main_portrait": main[:1],
        "turnaround_front": choose_by_value(face + full_body, "face_angle", "front")[:1] or main[:1],
        "turnaround_side": choose_by_value(face + full_body, "face_angle", "side")[:1],
        "turnaround_back": choose_by_value(face + full_body, "face_angle", "back")[:1],
        "face_angle_front": choose_by_value(face, "face_angle", "front")[:1] or main[:1],
        "face_angle_45": choose_by_value(face, "face_angle", "three_quarter")[:1],
        "face_angle_side": choose_by_value(face, "face_angle", "side")[:1],
        "expressions": expressions[:6],
        "pose_reference": full_body[:4],
    }


def empty_section() -> CharacterSheetSection:
    return CharacterSheetSection("", "", "missing", False)


def choose_by_value(
    candidates: list[CharacterSheetCandidate],
    field_name: str,
    value: str,
) -> list[CharacterSheetCandidate]:
    return [candidate for candidate in candidates if getattr(candidate, field_name) == value]


def paste_candidates_into_region(
    settings: AppSettings,
    canvas: Image.Image,
    region: TemplateRegion,
    candidates: list[CharacterSheetCandidate],
) -> None:
    left = int(round(region.left * canvas.width))
    top = int(round(region.top * canvas.height))
    right = int(round(region.right * canvas.width))
    bottom = int(round(region.bottom * canvas.height))
    columns = 1 if len(candidates) == 1 else 2
    rows = max(1, (len(candidates) + columns - 1) // columns)
    cell_width = max(1, (right - left) // columns)
    cell_height = max(1, (bottom - top) // rows)
    for index, candidate in enumerate(candidates):
        path = resolve_candidate_path(settings, candidate.frame_path)
        try:
            with Image.open(path) as source:
                tile = ImageOps.fit(
                    source.convert("RGB"),
                    (cell_width, cell_height),
                    method=Image.Resampling.LANCZOS,
                )
        except (FileNotFoundError, OSError, UnidentifiedImageError):
            continue
        column = index % columns
        row = index // columns
        canvas.paste(tile, (left + column * cell_width, top + row * cell_height))


def resolve_candidate_path(settings: AppSettings, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return settings.project_root / path


def build_review_manifest(
    settings: AppSettings,
    character_id: str,
    video_id: str,
    sections: list[CharacterSheetSection],
    draft_sheet_path: Path,
) -> dict[str, object]:
    review_root = settings.assets.processed / "characters" / character_id / "character_sheet"
    reviewed_dir = review_root / "reviewed"
    master_dir = review_root / "master"
    reviewed_dir.mkdir(parents=True, exist_ok=True)
    master_dir.mkdir(parents=True, exist_ok=True)
    return {
        "schema_version": 1,
        "manifest_type": "character_sheet_review_package",
        "generated_at": utc_timestamp(),
        "character_id": character_id,
        "video_id": video_id,
        "draft_sheet_image": project_relative_path(settings, draft_sheet_path),
        "reviewed_output_dir": project_relative_path(settings, reviewed_dir),
        "master_output_dir": project_relative_path(settings, master_dir),
        "checks": [
            "No subtitles, watermarks, logos, or speech bubbles remain.",
            "Face, hair, costume, and body proportions describe one identity.",
            "Front, three-quarter, side, expression, and pose references are consistent.",
            "Rejected or uncertain frames are replaced before master promotion.",
        ],
        "sections": [
            {
                "section_id": section.section_id,
                "status": section.status,
                "decision": "pending",
                "candidate_count": len(section.candidates),
                "notes": "",
            }
            for section in sections
        ],
        "promotion": {
            "reviewed_filename": f"{character_id}_{video_id}_reviewed.png",
            "master_filename": f"{character_id}_{video_id}_master.png",
            "requires_human_approval": True,
        },
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


def character_sheet_draft_image_path(settings: AppSettings, character_id: str, video_id: str) -> Path:
    return (
        settings.assets.processed
        / "characters"
        / character_id
        / "character_sheet"
        / "draft"
        / f"{video_id}_draft_sheet.png"
    )


def character_sheet_review_manifest_path(settings: AppSettings, character_id: str, video_id: str) -> Path:
    return (
        settings.project_root
        / "manifests"
        / "characters"
        / character_id
        / "character_sheet"
        / f"{video_id}_review.json"
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
    if result.draft_sheet_path is not None:
        print(f"Draft sheet: {result.draft_sheet_path}")
    if result.review_manifest_path is not None:
        print(f"Review package: {result.review_manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
