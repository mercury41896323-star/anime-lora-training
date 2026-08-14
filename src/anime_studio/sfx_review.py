from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from .lora_registry import project_relative_path, utc_timestamp
from .settings import AppSettings
from .storyboard import get_storyboard_path, load_storyboard


SFX_CUE_MANIFEST_TYPE = "storyboard_sfx_cues"
SFX_REVIEW_MANIFEST_TYPE = "storyboard_sfx_asset_review"


@dataclass(frozen=True)
class SfxReviewResult:
    manifest_path: Path
    cue_count: int
    recommended_count: int


@dataclass(frozen=True)
class SfxSelectionResult:
    manifest_path: Path
    cue_id: str
    selected_asset_path: str


def build_sfx_asset_review(
    settings: AppSettings,
    story_id: str,
    output_path: str | Path | None = None,
) -> SfxReviewResult:
    storyboard = load_storyboard(settings, story_id)
    cues = read_sfx_cues(settings, story_id)
    review_items = [build_review_item(cue) for cue in cues]
    manifest_path = normalize_review_manifest_path(settings, story_id, output_path)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "manifest_type": SFX_REVIEW_MANIFEST_TYPE,
                "generated_at": utc_timestamp(),
                "story": {
                    "story_id": storyboard.story_id,
                    "title": storyboard.title,
                },
                "counts": {
                    "cue_count": len(review_items),
                    "recommended_count": sum(1 for item in review_items if item.get("recommended_candidate")),
                },
                "items": review_items,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return SfxReviewResult(
        manifest_path=manifest_path,
        cue_count=len(review_items),
        recommended_count=sum(1 for item in review_items if item.get("recommended_candidate")),
    )


def apply_sfx_asset_candidate(
    settings: AppSettings,
    story_id: str,
    cue_id: str,
    candidate_index: int = 0,
    candidate_path: str = "",
    notes: str = "",
) -> SfxSelectionResult:
    if candidate_index < 0:
        raise ValueError("candidate_index must be 0 or greater.")
    path = get_sfx_cues_path(settings, story_id)
    cues = read_sfx_cues(settings, story_id)
    for cue in cues:
        if str(cue.get("cue_id", "")) != cue_id:
            continue
        candidate = select_candidate(cue, candidate_index=candidate_index, candidate_path=candidate_path)
        selected_path = str(candidate.get("stored_path", ""))
        if not selected_path:
            raise ValueError(f"Selected candidate has no stored_path: {cue_id}")
        cue["asset_path"] = project_relative_path(settings, selected_path)
        cue["asset_source"] = "asset_library"
        cue["selected_asset_candidate"] = candidate
        cue["selection_notes"] = notes
        cue["updated_at"] = utc_timestamp()
        write_sfx_cues(path, story_id, cues)
        return SfxSelectionResult(manifest_path=path, cue_id=cue_id, selected_asset_path=cue["asset_path"])
    raise ValueError(f"SFX cue not found: {cue_id}")


def build_review_item(cue: dict[str, Any]) -> dict[str, Any]:
    candidates = list(cue.get("asset_library_candidates") or [])
    recommended = first_existing_candidate(candidates) or (candidates[0] if candidates else {})
    asset_path = str(cue.get("asset_path", ""))
    status = "ready" if asset_path else "needs_selection" if recommended else "missing_candidates"
    return {
        "cue_id": str(cue.get("cue_id", "")),
        "shot_id": str(cue.get("shot_id", "")),
        "order": int(cue.get("order", 0)),
        "label": str(cue.get("label", "")),
        "status": status,
        "asset_path": asset_path,
        "asset_source": str(cue.get("asset_source", "")),
        "tags": list(cue.get("tags") or []),
        "tag_source": str(cue.get("tag_source", "")),
        "asset_library_query": str(cue.get("asset_library_query", "")),
        "candidate_count": len(candidates),
        "recommended_candidate": recommended,
        "selected_asset_candidate": dict(cue.get("selected_asset_candidate") or {}),
    }


def first_existing_candidate(candidates: list[Any]) -> dict[str, Any]:
    for candidate in candidates:
        candidate_dict = dict(candidate)
        if candidate_dict.get("exists"):
            return candidate_dict
    return {}


def select_candidate(
    cue: dict[str, Any],
    candidate_index: int,
    candidate_path: str,
) -> dict[str, Any]:
    candidates = [dict(candidate) for candidate in cue.get("asset_library_candidates") or []]
    if candidate_path:
        for candidate in candidates:
            if str(candidate.get("stored_path", "")) == candidate_path:
                return candidate
        raise ValueError(f"Candidate path not found: {candidate_path}")
    if candidate_index >= len(candidates):
        raise ValueError(f"candidate_index is out of range: {candidate_index}")
    return candidates[candidate_index]


def read_sfx_cues(settings: AppSettings, story_id: str) -> list[dict[str, Any]]:
    path = get_sfx_cues_path(settings, story_id)
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if data.get("manifest_type") != SFX_CUE_MANIFEST_TYPE:
        raise ValueError(f"Unexpected SFX manifest type in {path}: {data.get('manifest_type')}")
    return [dict(item) for item in data.get("items", [])]


def write_sfx_cues(path: Path, story_id: str, cues: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "manifest_type": SFX_CUE_MANIFEST_TYPE,
                "story_id": story_id,
                "updated_at": utc_timestamp(),
                "items": sorted(cues, key=lambda item: (int(item.get("order", 0)), str(item.get("cue_id", "")))),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def get_sfx_cues_path(settings: AppSettings, story_id: str) -> Path:
    return get_storyboard_path(settings, story_id).parent / "sfx_cues.json"


def normalize_review_manifest_path(settings: AppSettings, story_id: str, output_path: str | Path | None) -> Path:
    if output_path is None:
        return settings.project_root / "manifests" / "storyboards" / story_id / "sfx_asset_review.json"
    path = Path(output_path)
    if not path.is_absolute():
        path = settings.project_root / path
    return path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="anime-sfx-review",
        description="Review and select SFX Asset Library candidates for Phase 6 cues.",
    )
    parser.add_argument("--config", default="config/local_6gb.json", help="Path to the local runtime profile.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    review = subparsers.add_parser("review", help="Write a review manifest for SFX cue candidates.")
    review.add_argument("--story-id", required=True, help="Storyboard id.")
    review.add_argument("--output", default=None, help="Optional review manifest output path.")

    select = subparsers.add_parser("select", help="Apply an Asset Library candidate to an SFX cue.")
    select.add_argument("--story-id", required=True, help="Storyboard id.")
    select.add_argument("--cue-id", required=True, help="SFX cue id.")
    select.add_argument("--candidate-index", type=int, default=0, help="Candidate index to apply.")
    select.add_argument("--candidate-path", default="", help="Select by stored_path instead of index.")
    select.add_argument("--notes", default="", help="Selection notes.")
    return parser


def main(argv: list[str] | None = None) -> int:
    from .settings import load_settings

    parser = build_parser()
    args = parser.parse_args(argv)
    settings = load_settings(args.config)
    if args.command == "review":
        result = build_sfx_asset_review(settings=settings, story_id=args.story_id, output_path=args.output)
        print(f"Wrote SFX review: {result.manifest_path}")
        print(f"Cues: {result.cue_count}")
        print(f"Recommended: {result.recommended_count}")
        return 0
    if args.command == "select":
        result = apply_sfx_asset_candidate(
            settings=settings,
            story_id=args.story_id,
            cue_id=args.cue_id,
            candidate_index=args.candidate_index,
            candidate_path=args.candidate_path,
            notes=args.notes,
        )
        print(f"Selected SFX asset: {result.selected_asset_path}")
        print(f"Cue: {result.cue_id}")
        print(f"Manifest: {result.manifest_path}")
        return 0
    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
