from __future__ import annotations

import argparse
from dataclasses import dataclass
from html import escape
import json
from pathlib import Path
import shutil
import webbrowser
from typing import Any

from .character_profile import validate_character_id
from .lora_registry import project_relative_path, utc_timestamp
from .settings import AppSettings, load_settings
from .video_frame_cleaner import clean_frame_manifest_path


REVIEW_MANIFEST_TYPE = "video_clean_frame_review"


@dataclass(frozen=True)
class CleanFrameReviewResult:
    review_path: Path
    gallery_path: Path
    candidate_count: int


@dataclass(frozen=True)
class FinalizedCleanFrameDatasetResult:
    review_path: Path
    dataset_dir: Path
    accepted_count: int
    rejected_count: int


def build_clean_frame_review(
    settings: AppSettings,
    character_id: str,
    video_id: str,
    output_dir: str | Path | None = None,
) -> CleanFrameReviewResult:
    validate_character_id(character_id)
    clean_manifest = read_required_json(clean_frame_manifest_path(settings, character_id, video_id))
    candidates = candidate_frames(clean_manifest)
    review_path = clean_frame_review_path(settings, character_id, video_id)
    previous = read_optional_json(review_path)
    previous_by_index = {
        int(item.get("frame_index", 0)): dict(item)
        for item in previous.get("frames", [])
        if isinstance(item, dict)
    }
    frames = []
    for item in candidates:
        frame_index = int(item.get("frame_index", 0))
        old = previous_by_index.get(frame_index, {})
        frames.append(
            {
                "frame_index": frame_index,
                "shot_id": str(item.get("shot_id", "")),
                "timestamp_seconds": float(item.get("timestamp_seconds", 0.0) or 0.0),
                "image_path": str(item.get("output_path", "")),
                "caption_path": str(item.get("caption_path", "")),
                "decision": str(old.get("decision", "pending")),
                "notes": str(old.get("notes", "")),
            }
        )
    payload = {
        "schema_version": 1,
        "manifest_type": REVIEW_MANIFEST_TYPE,
        "generated_at": utc_timestamp(),
        "character_id": character_id,
        "video_id": video_id,
        "status": "pending_review",
        "reviewer": str(previous.get("reviewer", "")),
        "source_manifest": project_relative_path(settings, clean_frame_manifest_path(settings, character_id, video_id)),
        "reviewed_dataset_dir": "",
        "counts": summarize_decisions(frames),
        "frames": frames,
    }
    write_json(review_path, payload)
    gallery_dir = normalize_gallery_dir(settings, character_id, video_id, output_dir)
    gallery_dir.mkdir(parents=True, exist_ok=True)
    gallery_path = gallery_dir / "clean_frame_review.html"
    gallery_path.write_text(render_gallery(settings, payload), encoding="utf-8")
    return CleanFrameReviewResult(review_path, gallery_path, len(candidates))


def finalize_clean_frame_review(
    settings: AppSettings,
    character_id: str,
    video_id: str,
    accepted_indices: set[int],
    reviewer: str,
    notes: str = "",
) -> FinalizedCleanFrameDatasetResult:
    validate_character_id(character_id)
    reviewer_name = reviewer.strip()
    if not reviewer_name:
        raise ValueError("reviewer is required to finalize clean frame review.")
    if not accepted_indices:
        raise ValueError("At least one accepted frame index is required.")
    clean_manifest = read_required_json(clean_frame_manifest_path(settings, character_id, video_id))
    candidates = candidate_frames(clean_manifest)
    by_index = {int(item.get("frame_index", 0)): item for item in candidates}
    missing = sorted(accepted_indices - set(by_index))
    if missing:
        raise ValueError(f"Accepted frame indices are not review candidates: {missing}")

    dataset_dir = settings.datasets.lora / character_id / f"video_{video_id}_reviewed"
    images_dir = dataset_dir / "images"
    reset_generated_files(images_dir)
    frames: list[dict[str, Any]] = []
    accepted_count = 0
    for frame_index, item in sorted(by_index.items()):
        accepted = frame_index in accepted_indices
        image_source = resolve_project_path(settings, str(item.get("output_path", "")))
        caption_source = resolve_project_path(settings, str(item.get("caption_path", "")))
        image_output = images_dir / image_source.name
        caption_output = images_dir / caption_source.name
        if accepted:
            if not image_source.is_file() or not caption_source.is_file():
                raise FileNotFoundError(f"Accepted frame asset is missing: {image_source}")
            shutil.copy2(image_source, image_output)
            shutil.copy2(caption_source, caption_output)
            accepted_count += 1
        frames.append(
            {
                "frame_index": frame_index,
                "shot_id": str(item.get("shot_id", "")),
                "timestamp_seconds": float(item.get("timestamp_seconds", 0.0) or 0.0),
                "image_path": project_relative_path(settings, image_output) if accepted else str(item.get("output_path", "")),
                "caption_path": project_relative_path(settings, caption_output) if accepted else str(item.get("caption_path", "")),
                "decision": "accepted" if accepted else "rejected",
                "notes": notes.strip() if accepted else "Not selected during final clean frame review.",
            }
        )
    rejected_count = len(frames) - accepted_count
    review_path = clean_frame_review_path(settings, character_id, video_id)
    payload = {
        "schema_version": 1,
        "manifest_type": REVIEW_MANIFEST_TYPE,
        "generated_at": utc_timestamp(),
        "character_id": character_id,
        "video_id": video_id,
        "status": "completed",
        "reviewer": reviewer_name,
        "review_notes": notes.strip(),
        "source_manifest": project_relative_path(settings, clean_frame_manifest_path(settings, character_id, video_id)),
        "reviewed_dataset_dir": project_relative_path(settings, dataset_dir),
        "counts": summarize_decisions(frames),
        "frames": frames,
    }
    write_json(review_path, payload)
    write_json(
        dataset_dir / "metadata.json",
        {
            "schema_version": 1,
            "manifest_type": "reviewed_lora_dataset",
            "character_id": character_id,
            "video_id": video_id,
            "image_count": accepted_count,
            "human_review_required": False,
            "review_completed": True,
            "reviewer": reviewer_name,
            "review_manifest": project_relative_path(settings, review_path),
        },
    )
    return FinalizedCleanFrameDatasetResult(review_path, dataset_dir, accepted_count, rejected_count)


def parse_frame_indices(value: str) -> set[int]:
    result: set[int] = set()
    for chunk in value.split(","):
        token = chunk.strip()
        if not token:
            continue
        if "-" in token:
            start_text, end_text = token.split("-", 1)
            start = int(start_text)
            end = int(end_text)
            if start <= 0 or end < start:
                raise ValueError(f"Invalid frame range: {token}")
            result.update(range(start, end + 1))
        else:
            index = int(token)
            if index <= 0:
                raise ValueError(f"Frame index must be positive: {token}")
            result.add(index)
    return result


def candidate_frames(clean_manifest: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        dict(item)
        for item in clean_manifest.get("frames", [])
        if isinstance(item, dict) and item.get("status") == "review_candidate" and item.get("output_path")
    ]


def render_gallery(settings: AppSettings, payload: dict[str, Any]) -> str:
    cards = []
    for item in payload["frames"]:
        image_path = resolve_project_path(settings, item["image_path"])
        cards.append(
            "<article class='card'>"
            f"<img src='{escape(image_path.resolve().as_uri())}' alt='frame {item['frame_index']}'>"
            f"<h3>Frame {item['frame_index']}</h3>"
            f"<p>Shot: {escape(str(item['shot_id']))}<br>Time: {item['timestamp_seconds']:.3f}s</p>"
            "</article>"
        )
    return f"""<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Clean Frame Review</title><style>
body{{margin:0;background:#10151d;color:#eef3ff;font-family:"Segoe UI","Yu Gothic UI",sans-serif}}main{{max-width:1400px;margin:auto;padding:24px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px}}.card{{background:#1b2230;padding:12px;border-radius:12px;border:1px solid #303a4d}}
img{{width:100%;aspect-ratio:1;object-fit:contain;background:#0a0d12;border-radius:8px}}code{{color:#8bd5ff}}.note{{color:#aeb9cc}}
</style></head><body><main><h1>Clean Frame Review: {escape(str(payload['character_id']))}</h1>
<p class="note">採用するFrame番号を確認し、PowerShellで finalize を実行します。例: <code>--accept "1,3,5-8"</code></p>
<div class="grid">{''.join(cards)}</div></main></body></html>"""


def summarize_decisions(frames: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "candidate_count": len(frames),
        "accepted_count": sum(item.get("decision") == "accepted" for item in frames),
        "rejected_count": sum(item.get("decision") == "rejected" for item in frames),
        "pending_count": sum(item.get("decision") == "pending" for item in frames),
    }


def clean_frame_review_path(settings: AppSettings, character_id: str, video_id: str) -> Path:
    return settings.project_root / "manifests" / "characters" / character_id / "video_analysis" / f"{video_id}_clean_frame_review.json"


def normalize_gallery_dir(settings: AppSettings, character_id: str, video_id: str, value: str | Path | None) -> Path:
    if value in (None, ""):
        return settings.project_root / "outputs" / "review" / character_id / video_id
    path = Path(value)
    return path if path.is_absolute() else settings.project_root / path


def resolve_project_path(settings: AppSettings, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else settings.project_root / path


def reset_generated_files(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for path in directory.iterdir():
        if path.is_file():
            path.unlink()


def read_required_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"Clean frame manifest does not exist: {path}")
    return json.loads(path.read_text(encoding="utf-8-sig"))


def read_optional_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Review clean video frames before LoRA training.")
    parser.add_argument("--config", default="config/local_6gb.json")
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare = subparsers.add_parser("prepare", help="Create a numbered HTML clean-frame gallery.")
    prepare.add_argument("--character-id", required=True)
    prepare.add_argument("--video-id", required=True)
    prepare.add_argument("--output-dir", default=None)
    prepare.add_argument("--open", action="store_true")
    finalize = subparsers.add_parser("finalize", help="Create a reviewed dataset from accepted frame indices.")
    finalize.add_argument("--character-id", required=True)
    finalize.add_argument("--video-id", required=True)
    finalize.add_argument("--accept", required=True, help='Frame indices such as "1,3,5-8".')
    finalize.add_argument("--reviewer", required=True)
    finalize.add_argument("--notes", default="")
    finalize.add_argument("--confirm", action="store_true", required=True, help="Required explicit finalization flag.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = load_settings(args.config)
    if args.command == "prepare":
        result = build_clean_frame_review(settings, args.character_id, args.video_id, args.output_dir)
        print(f"Review manifest: {result.review_path}")
        print(f"Review gallery: {result.gallery_path}")
        print(f"Candidates: {result.candidate_count}")
        if args.open:
            webbrowser.open(result.gallery_path.resolve().as_uri())
        return 0
    result = finalize_clean_frame_review(
        settings,
        args.character_id,
        args.video_id,
        parse_frame_indices(args.accept),
        args.reviewer,
        args.notes,
    )
    print(f"Reviewed dataset: {result.dataset_dir}")
    print(f"Accepted: {result.accepted_count}")
    print(f"Rejected: {result.rejected_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
