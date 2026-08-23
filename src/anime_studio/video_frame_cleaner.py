from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, field
import json
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from .character_profile import validate_character_id
from .lora_registry import project_relative_path, utc_timestamp
from .settings import AppSettings, load_settings
from .video_shot_pipeline import sampled_manifest_path


CLEAN_FRAME_MANIFEST_TYPE = "video_clean_frame_manifest"
DEFAULT_EXCLUDED_TEXT_TAGS = (
    "text",
    "subtitle",
    "subtitles",
    "caption",
    "watermark",
    "logo",
    "signature",
    "speech_bubble",
)


@dataclass(frozen=True)
class CleanFrameItem:
    source_frame_path: str
    output_path: str
    caption_path: str
    shot_id: str
    frame_index: int
    timestamp_seconds: float
    role: str
    status: str
    text_free_candidate: bool
    crop_box: dict[str, int] = field(default_factory=dict)
    source_size: dict[str, int] = field(default_factory=dict)
    output_size: dict[str, int] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    excluded_tag_hits: list[str] = field(default_factory=list)
    reason: str = ""


@dataclass(frozen=True)
class CleanFrameBuildResult:
    manifest_path: Path
    dataset_dir: Path
    processed_count: int
    excluded_count: int


def build_clean_video_frames(
    settings: AppSettings,
    character_id: str,
    video_id: str,
    target_width: int = 512,
    target_height: int = 512,
    top_trim_ratio: float = 0.04,
    bottom_trim_ratio: float = 0.18,
    excluded_text_tags: list[str] | tuple[str, ...] | None = None,
) -> CleanFrameBuildResult:
    validate_character_id(character_id)
    validate_dimensions(target_width, target_height)
    validate_trim_ratios(top_trim_ratio, bottom_trim_ratio)
    excluded_tags = normalize_tags(excluded_text_tags or DEFAULT_EXCLUDED_TEXT_TAGS)
    source_manifest_path = sampled_manifest_path(settings, character_id, video_id)
    if not source_manifest_path.is_file():
        raise FileNotFoundError(f"Sampled frame manifest does not exist: {source_manifest_path}")

    source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
    dataset_dir = settings.datasets.lora / character_id / f"video_{video_id}_clean"
    images_dir = dataset_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    items: list[CleanFrameItem] = []

    for index, frame in enumerate(source_manifest.get("frames", []), start=1):
        source_path = resolve_project_path(settings, str(frame.get("frame_path", "")))
        tags = normalize_tags(frame.get("tags", []))
        excluded_hits = find_excluded_tag_hits(tags, excluded_tags)
        common = {
            "source_frame_path": project_relative_path(settings, source_path),
            "shot_id": str(frame.get("shot_id", "")),
            "frame_index": int(frame.get("frame_index", index) or index),
            "timestamp_seconds": float(frame.get("timestamp_seconds", 0.0) or 0.0),
            "role": str(frame.get("role", "sampled")),
            "tags": tags,
        }
        if excluded_hits:
            items.append(
                CleanFrameItem(
                    output_path="",
                    caption_path="",
                    status="excluded_text_tag",
                    text_free_candidate=False,
                    excluded_tag_hits=excluded_hits,
                    reason="Source tags indicate visible text, subtitle, watermark, or logo.",
                    **common,
                )
            )
            continue
        if not source_path.is_file():
            items.append(
                CleanFrameItem(
                    output_path="",
                    caption_path="",
                    status="invalid_source",
                    text_free_candidate=False,
                    reason="Source frame does not exist.",
                    **common,
                )
            )
            continue

        output_name = f"{index:04d}_{source_path.stem}.png"
        output_path = images_dir / output_name
        caption_path = output_path.with_suffix(".txt")
        try:
            with Image.open(source_path) as source_image:
                image = source_image.convert("RGB")
                crop_box = calculate_safe_crop_box(
                    image.width,
                    image.height,
                    target_width / target_height,
                    top_trim_ratio,
                    bottom_trim_ratio,
                )
                cropped = image.crop(
                    (crop_box["left"], crop_box["top"], crop_box["right"], crop_box["bottom"])
                )
                resized = cropped.resize((target_width, target_height), Image.Resampling.LANCZOS)
                resized.save(output_path, format="PNG", optimize=True)
                source_size = {"width": image.width, "height": image.height}
        except (OSError, UnidentifiedImageError) as error:
            items.append(
                CleanFrameItem(
                    output_path="",
                    caption_path="",
                    status="invalid_image",
                    text_free_candidate=False,
                    reason=str(error),
                    **common,
                )
            )
            continue

        cleaned_tags = [tag for tag in tags if tag not in excluded_tags]
        if character_id not in cleaned_tags:
            cleaned_tags.insert(0, character_id)
        caption_path.write_text(", ".join(cleaned_tags) + "\n", encoding="utf-8")
        items.append(
            CleanFrameItem(
                output_path=project_relative_path(settings, output_path),
                caption_path=project_relative_path(settings, caption_path),
                status="review_candidate",
                text_free_candidate=True,
                crop_box=crop_box,
                source_size=source_size,
                output_size={"width": target_width, "height": target_height},
                reason="Safe-area crop removed common subtitle bands; human visual review is still required.",
                **common,
            )
        )

    processed_count = sum(1 for item in items if item.status == "review_candidate")
    excluded_count = len(items) - processed_count
    manifest_path = clean_frame_manifest_path(settings, character_id, video_id)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "manifest_type": CLEAN_FRAME_MANIFEST_TYPE,
                "generated_at": utc_timestamp(),
                "character_id": character_id,
                "video_id": video_id,
                "source_manifest": project_relative_path(settings, source_manifest_path),
                "dataset_dir": project_relative_path(settings, dataset_dir),
                "cleanup_policy": {
                    "method": "safe_area_crop_and_text_tag_exclusion",
                    "target_width": target_width,
                    "target_height": target_height,
                    "top_trim_ratio": top_trim_ratio,
                    "bottom_trim_ratio": bottom_trim_ratio,
                    "excluded_text_tags": excluded_tags,
                    "ocr_verified": False,
                    "human_review_required": True,
                },
                "counts": {
                    "source_frames": len(items),
                    "processed_frames": processed_count,
                    "excluded_frames": excluded_count,
                },
                "frames": [asdict(item) for item in items],
                "next_steps": [
                    "Visually reject any remaining frame containing text, logos, or character occlusion.",
                    "Use only accepted clean frames for Character Sheet Draft and LoRA dataset review.",
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (dataset_dir / "metadata.json").write_text(
        json.dumps(
            {
                "character_id": character_id,
                "video_id": video_id,
                "image_count": processed_count,
                "source_manifest": project_relative_path(settings, manifest_path),
                "human_review_required": True,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return CleanFrameBuildResult(manifest_path, dataset_dir, processed_count, excluded_count)


def calculate_safe_crop_box(
    width: int,
    height: int,
    target_aspect: float,
    top_trim_ratio: float,
    bottom_trim_ratio: float,
) -> dict[str, int]:
    safe_top = min(height - 1, max(0, int(round(height * top_trim_ratio))))
    safe_bottom = max(safe_top + 1, min(height, int(round(height * (1.0 - bottom_trim_ratio)))))
    safe_height = safe_bottom - safe_top
    safe_width = width
    safe_aspect = safe_width / safe_height
    if safe_aspect > target_aspect:
        crop_width = max(1, int(round(safe_height * target_aspect)))
        left = max(0, (width - crop_width) // 2)
        right = min(width, left + crop_width)
        top = safe_top
        bottom = safe_bottom
    else:
        crop_height = max(1, int(round(safe_width / target_aspect)))
        top = safe_top + max(0, (safe_height - crop_height) // 2)
        bottom = min(safe_bottom, top + crop_height)
        left = 0
        right = width
    return {"left": left, "top": top, "right": right, "bottom": bottom}


def find_excluded_tag_hits(tags: list[str], excluded_tags: list[str]) -> list[str]:
    hits: list[str] = []
    for tag in tags:
        normalized = tag.replace(" ", "_")
        if any(token == normalized or token in normalized for token in excluded_tags):
            hits.append(tag)
    return hits


def normalize_tags(values) -> list[str]:
    result: list[str] = []
    for value in values:
        normalized = str(value).strip().lower().replace(" ", "_")
        if normalized and normalized not in result:
            result.append(normalized)
    return result


def resolve_project_path(settings: AppSettings, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return settings.project_root / path


def validate_dimensions(width: int, height: int) -> None:
    if width <= 0 or height <= 0:
        raise ValueError("Target width and height must be greater than 0.")


def validate_trim_ratios(top_trim_ratio: float, bottom_trim_ratio: float) -> None:
    if not 0.0 <= top_trim_ratio < 1.0 or not 0.0 <= bottom_trim_ratio < 1.0:
        raise ValueError("Trim ratios must be between 0.0 and 1.0.")
    if top_trim_ratio + bottom_trim_ratio >= 0.8:
        raise ValueError("Combined trim ratios must leave at least 20 percent of the image.")


def clean_frame_manifest_path(settings: AppSettings, character_id: str, video_id: str) -> Path:
    return (
        settings.project_root
        / "manifests"
        / "characters"
        / character_id
        / "video_analysis"
        / f"{video_id}_clean_frames.json"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="anime-video-clean-frames",
        description="Build cropped, subtitle-safe frame candidates from sampled video frames.",
    )
    parser.add_argument("--config", default="config/local_6gb.json", help="Path to the local runtime profile.")
    parser.add_argument("--character-id", required=True, help="Character id.")
    parser.add_argument("--video-id", required=True, help="Imported video id.")
    parser.add_argument("--width", type=int, default=512, help="Output width.")
    parser.add_argument("--height", type=int, default=512, help="Output height.")
    parser.add_argument("--top-trim", type=float, default=0.04, help="Top safe-area trim ratio.")
    parser.add_argument("--bottom-trim", type=float, default=0.18, help="Bottom subtitle-band trim ratio.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = load_settings(args.config)
    result = build_clean_video_frames(
        settings=settings,
        character_id=args.character_id,
        video_id=args.video_id,
        target_width=args.width,
        target_height=args.height,
        top_trim_ratio=args.top_trim,
        bottom_trim_ratio=args.bottom_trim,
    )
    print(f"Clean frame manifest: {result.manifest_path}")
    print(f"Dataset: {result.dataset_dir}")
    print(f"Processed: {result.processed_count}")
    print(f"Excluded: {result.excluded_count}")
    return 0 if result.processed_count else 1


if __name__ == "__main__":
    raise SystemExit(main())
