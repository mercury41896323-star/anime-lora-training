from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from .edit_export import read_timeline_manifest
from .lora_registry import project_relative_path, utc_timestamp
from .settings import AppSettings
from .timeline_manifest import normalize_edit_timeline_manifest_path


REVISION_REVIEW_MANIFEST_TYPE = "unity_timeline_revision_review"
SELECTED_REVISION_MANIFEST_TYPE = "unity_selected_timeline_revision"


@dataclass(frozen=True)
class TimelineRevisionReviewResult:
    manifest_path: Path
    revision_count: int
    recommended_revision_id: str


@dataclass(frozen=True)
class TimelineRevisionAdoptionResult:
    manifest_path: Path
    revision_id: str
    timeline_asset: str


def review_timeline_revisions(
    settings: AppSettings,
    story_id: str,
    timeline_root: str | Path | None = None,
    edit_manifest_path: str | Path | None = None,
    output_path: str | Path | None = None,
) -> TimelineRevisionReviewResult:
    edit_manifest = read_timeline_manifest(normalize_edit_timeline_manifest_path(settings, story_id, edit_manifest_path))
    root = normalize_timeline_root(settings, story_id, timeline_root)
    revisions = discover_timeline_revisions(settings, root)
    current_clip_count = int(edit_manifest.get("counts", {}).get("clip_count", 0))
    current_duration = float(edit_manifest.get("duration_seconds", 0.0))
    reviewed = [
        {
            **revision,
            "score": score_revision(revision, current_clip_count, current_duration),
            "comparison": {
                "current_clip_count": current_clip_count,
                "current_duration_seconds": current_duration,
                "has_build_report": bool(revision.get("build_report_path")),
            },
        }
        for revision in revisions
    ]
    reviewed.sort(key=lambda item: (-int(item["score"]), str(item.get("revision_id", ""))))
    recommended = str(reviewed[0]["revision_id"]) if reviewed else ""
    path = normalize_revision_review_path(settings, story_id, output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "manifest_type": REVISION_REVIEW_MANIFEST_TYPE,
                "generated_at": utc_timestamp(),
                "story_id": story_id,
                "timeline_root": project_relative_path(settings, root),
                "source_edit_manifest": project_relative_path(
                    settings,
                    normalize_edit_timeline_manifest_path(settings, story_id, edit_manifest_path),
                ),
                "recommended_revision_id": recommended,
                "counts": {
                    "revision_count": len(reviewed),
                    "current_clip_count": current_clip_count,
                },
                "revisions": reviewed,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return TimelineRevisionReviewResult(path, len(reviewed), recommended)


def adopt_timeline_revision(
    settings: AppSettings,
    story_id: str,
    revision_id: str | None = None,
    review_path: str | Path | None = None,
    output_path: str | Path | None = None,
) -> TimelineRevisionAdoptionResult:
    review_file = normalize_revision_review_path(settings, story_id, review_path)
    if not review_file.exists():
        raise FileNotFoundError(f"Timeline revision review not found: {review_file}")
    review = json.loads(review_file.read_text(encoding="utf-8-sig"))
    selected_id = revision_id or str(review.get("recommended_revision_id", ""))
    revisions = {str(item.get("revision_id", "")): dict(item) for item in review.get("revisions", [])}
    if selected_id not in revisions:
        raise ValueError(f"Timeline revision not found in review: {selected_id}")
    selected = revisions[selected_id]
    path = normalize_selected_revision_path(settings, story_id, output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "manifest_type": SELECTED_REVISION_MANIFEST_TYPE,
                "updated_at": utc_timestamp(),
                "story_id": story_id,
                "revision_id": selected_id,
                "timeline_asset": selected.get("timeline_asset", ""),
                "revision_folder": selected.get("revision_folder", ""),
                "source_review": project_relative_path(settings, review_file),
                "status": "adopted",
                "notes": "This revision is the currently adopted Unity Timeline handoff.",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return TimelineRevisionAdoptionResult(path, selected_id, str(selected.get("timeline_asset", "")))


def discover_timeline_revisions(settings: AppSettings, timeline_root: Path) -> list[dict[str, Any]]:
    if not timeline_root.exists():
        return []
    revisions: list[dict[str, Any]] = []
    for directory in sorted(path for path in timeline_root.iterdir() if path.is_dir() and path.name.startswith("Revision_")):
        report_path = directory / "timeline_build_report.json"
        report = load_json_if_exists(report_path)
        revision_id = directory.name
        timeline_asset = str(report.get("timeline_asset", "")) or first_asset(directory, ".playable")
        revisions.append(
            {
                "revision_id": revision_id,
                "revision_folder": project_relative_path(settings, directory),
                "timeline_asset": timeline_asset,
                "build_report_path": project_relative_path(settings, report_path) if report_path.exists() else "",
                "generated_at": str(report.get("generated_at", "")),
                "source_manifest": str(report.get("source_manifest", "")),
                "protection_policy": str(report.get("protection_policy", "")),
            }
        )
    return revisions


def score_revision(revision: dict[str, Any], current_clip_count: int, current_duration: float) -> int:
    score = 0
    if revision.get("timeline_asset"):
        score += 20
    if revision.get("build_report_path"):
        score += 20
    if revision.get("protection_policy") == "create_new_revision_never_overwrite_existing_timeline":
        score += 10
    if current_clip_count > 0:
        score += 5
    if current_duration > 0:
        score += 5
    return score


def load_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def first_asset(directory: Path, suffix: str) -> str:
    for path in sorted(directory.rglob("*" + suffix)):
        return path.as_posix()
    return ""


def normalize_timeline_root(settings: AppSettings, story_id: str, timeline_root: str | Path | None) -> Path:
    if timeline_root is None:
        return settings.project_root / "integrations" / "unity" / "Assets" / "AIAnimeStudio" / "Timelines" / story_id
    path = Path(timeline_root)
    if not path.is_absolute():
        path = settings.project_root / path
    return path


def normalize_revision_review_path(settings: AppSettings, story_id: str, output_path: str | Path | None) -> Path:
    if output_path is None:
        return settings.project_root / "manifests" / "storyboards" / story_id / "timeline_revision_review.json"
    path = Path(output_path)
    if not path.is_absolute():
        path = settings.project_root / path
    return path


def normalize_selected_revision_path(settings: AppSettings, story_id: str, output_path: str | Path | None) -> Path:
    if output_path is None:
        return settings.project_root / "manifests" / "storyboards" / story_id / "selected_timeline_revision.json"
    path = Path(output_path)
    if not path.is_absolute():
        path = settings.project_root / path
    return path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="anime-timeline-revision",
        description="Review and adopt Unity Timeline revision folders.",
    )
    parser.add_argument("--config", default="config/local_6gb.json", help="Path to the local runtime profile.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    review = subparsers.add_parser("review", help="Scan revision folders and write a review manifest.")
    review.add_argument("--story-id", required=True, help="Storyboard id.")
    review.add_argument("--timeline-root", default=None, help="Optional Unity Timeline root folder.")
    review.add_argument("--edit-manifest", default=None, help="Optional edit_timeline_manifest.json path.")
    review.add_argument("--output", default=None, help="Optional review manifest path.")
    adopt = subparsers.add_parser("adopt", help="Select a revision from a review manifest.")
    adopt.add_argument("--story-id", required=True, help="Storyboard id.")
    adopt.add_argument("--revision-id", default=None, help="Revision id. Defaults to recommended revision.")
    adopt.add_argument("--review", default=None, help="Optional review manifest path.")
    adopt.add_argument("--output", default=None, help="Optional selected revision manifest path.")
    return parser


def main(argv: list[str] | None = None) -> int:
    from .settings import load_settings

    parser = build_parser()
    args = parser.parse_args(argv)
    settings = load_settings(args.config)
    if args.command == "review":
        result = review_timeline_revisions(
            settings=settings,
            story_id=args.story_id,
            timeline_root=args.timeline_root,
            edit_manifest_path=args.edit_manifest,
            output_path=args.output,
        )
        print(f"Wrote timeline revision review: {result.manifest_path}")
        print(f"Revisions: {result.revision_count}")
        print(f"Recommended: {result.recommended_revision_id or 'none'}")
        return 0
    if args.command == "adopt":
        result = adopt_timeline_revision(
            settings=settings,
            story_id=args.story_id,
            revision_id=args.revision_id,
            review_path=args.review,
            output_path=args.output,
        )
        print(f"Adopted timeline revision: {result.revision_id}")
        print(f"Timeline asset: {result.timeline_asset}")
        print(f"Manifest: {result.manifest_path}")
        return 0
    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
