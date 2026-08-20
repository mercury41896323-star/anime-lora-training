from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, field
import json
import math
from pathlib import Path
import shutil
import subprocess
from typing import Any

from .character_profile import validate_character_id
from .frame_extraction import build_frame_extraction_plan, extract_frames
from .lora_registry import project_relative_path, utc_timestamp
from .settings import AppSettings, load_settings
from .tagger import infer_filename_tags, load_tag_record
from .video_importer import build_video_id, import_video_asset


SHOT_MANIFEST_TYPE = "video_shot_manifest"
SAMPLED_MANIFEST_TYPE = "video_sampled_frame_manifest"
CLASSIFICATION_MANIFEST_TYPE = "video_frame_classification_manifest"


@dataclass(frozen=True)
class DetectedShot:
    shot_id: str
    order: int
    start_seconds: float
    end_seconds: float
    duration_seconds: float
    frame_count: int
    frame_paths: list[str] = field(default_factory=list)
    key_frames: list[str] = field(default_factory=list)
    boundary_reason: str = "duration"
    tags_summary: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SampledFrame:
    shot_id: str
    frame_path: str
    frame_index: int
    timestamp_seconds: float
    role: str
    similarity_score: float
    tags: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ClassifiedFrame:
    frame_path: str
    shot_id: str
    face_angle: str
    expression: str
    body_framing: str
    tags: list[str] = field(default_factory=list)
    confidence: str = "heuristic"


@dataclass(frozen=True)
class ShotDetectionResult:
    manifest_path: Path
    video_id: str
    shot_count: int
    frame_count: int
    effective_fps: float


@dataclass(frozen=True)
class FrameSamplingResult:
    manifest_path: Path
    dataset_dir: Path
    selected_frame_count: int


@dataclass(frozen=True)
class FrameClassificationResult:
    manifest_path: Path
    classified_frame_count: int


@dataclass(frozen=True)
class VideoProbeResult:
    duration_seconds: float | None
    width: int | None
    height: int | None
    average_fps: float | None
    source: str


def probe_video_metadata(video_path: str | Path) -> VideoProbeResult:
    source = Path(video_path)
    if shutil.which("ffprobe") is None:
        return VideoProbeResult(None, None, None, None, "ffprobe_unavailable")
    command = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height,avg_frame_rate",
        "-show_entries",
        "format=duration",
        "-of",
        "json",
        str(source),
    ]
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    if completed.returncode != 0:
        return VideoProbeResult(None, None, None, None, "ffprobe_error")
    data = json.loads(completed.stdout or "{}")
    stream = (data.get("streams") or [{}])[0]
    avg_fps = parse_fraction(stream.get("avg_frame_rate"))
    duration = data.get("format", {}).get("duration")
    return VideoProbeResult(
        duration_seconds=float(duration) if duration not in (None, "") else None,
        width=optional_int(stream.get("width")),
        height=optional_int(stream.get("height")),
        average_fps=avg_fps,
        source="ffprobe",
    )


def choose_effective_fps(
    duration_seconds: float | None,
    requested_fps: float,
    target_max_frames: int,
    minimum_fps: float = 0.2,
) -> float:
    if requested_fps <= 0:
        raise ValueError("requested_fps must be greater than 0.")
    if duration_seconds is None or duration_seconds <= 0 or target_max_frames <= 0:
        return requested_fps
    adaptive_fps = target_max_frames / duration_seconds
    adaptive_fps = max(minimum_fps, adaptive_fps)
    return round(min(requested_fps, adaptive_fps), 4)


def detect_video_shots(
    settings: AppSettings,
    character_id: str,
    video_path: str | Path,
    fps: float = 2.0,
    source_label: str = "",
    auto_extract: bool = False,
    reuse_import: bool = True,
    min_shot_seconds: float = 2.0,
    max_shot_seconds: float = 12.0,
    tag_change_threshold: float = 0.55,
    target_max_frames: int = 240,
) -> ShotDetectionResult:
    validate_character_id(character_id)
    if min_shot_seconds <= 0 or max_shot_seconds <= 0:
        raise ValueError("Shot duration settings must be greater than 0.")
    if min_shot_seconds > max_shot_seconds:
        raise ValueError("min_shot_seconds must not exceed max_shot_seconds.")

    import_result = import_video_asset(
        settings=settings,
        character_id=character_id,
        source_path=video_path,
        source_label=source_label,
        allow_existing=reuse_import,
    )
    probe = probe_video_metadata(import_result.asset.stored_path)
    effective_fps = choose_effective_fps(probe.duration_seconds, fps, target_max_frames)
    frame_plan = build_frame_extraction_plan(
        settings=settings,
        video_path=import_result.asset.stored_path,
        character_id=character_id,
        fps=effective_fps,
        output_group=import_result.asset.video_id,
    )
    if auto_extract and not frame_plan.output_dir.exists():
        return_code = extract_frames(frame_plan)
        if return_code != 0:
            raise RuntimeError(f"Frame extraction failed with code {return_code}.")

    frame_paths = sorted(path for path in frame_plan.output_dir.glob("*.png") if path.is_file())
    if not frame_paths:
        raise FileNotFoundError(
            f"No frames found for shot detection: {frame_plan.output_dir}. Run frame extraction first or use --auto-extract."
        )

    shots = split_frames_into_shots(
        settings=settings,
        frame_paths=frame_paths,
        fps=effective_fps,
        min_shot_seconds=min_shot_seconds,
        max_shot_seconds=max_shot_seconds,
        tag_change_threshold=tag_change_threshold,
    )
    manifest_path = shot_manifest_path(settings, character_id, import_result.asset.video_id)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "manifest_type": SHOT_MANIFEST_TYPE,
                "generated_at": utc_timestamp(),
                "character_id": character_id,
                "video_id": import_result.asset.video_id,
                "source_label": import_result.asset.source_label,
                "analysis_profile": {
                    "requested_fps": fps,
                    "effective_fps": effective_fps,
                    "target_max_frames": target_max_frames,
                    "min_shot_seconds": min_shot_seconds,
                    "max_shot_seconds": max_shot_seconds,
                    "tag_change_threshold": tag_change_threshold,
                },
                "video_probe": asdict(probe),
                "frame_dir": project_relative_path(settings, frame_plan.output_dir),
                "shots": [asdict(shot) for shot in shots],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return ShotDetectionResult(
        manifest_path=manifest_path,
        video_id=import_result.asset.video_id,
        shot_count=len(shots),
        frame_count=len(frame_paths),
        effective_fps=effective_fps,
    )


def split_frames_into_shots(
    settings: AppSettings,
    frame_paths: list[Path],
    fps: float,
    min_shot_seconds: float,
    max_shot_seconds: float,
    tag_change_threshold: float,
) -> list[DetectedShot]:
    min_frames = max(1, int(round(min_shot_seconds * fps)))
    max_frames = max(1, int(round(max_shot_seconds * fps)))
    shots: list[DetectedShot] = []
    current_frames: list[Path] = []
    current_tags: list[list[str]] = []
    current_reason = "duration"

    for frame_path in frame_paths:
        frame_tags = read_frame_tags(frame_path)
        if not current_frames:
            current_frames = [frame_path]
            current_tags = [frame_tags]
            continue

        previous_tags = current_tags[-1]
        rolling_tags = dedupe_tags([tag for tags in current_tags[-3:] for tag in tags])
        boundary_score = tag_distance(previous_tags, frame_tags)
        rolling_score = tag_distance(rolling_tags, frame_tags)
        if len(current_frames) >= max_frames:
            shots.append(build_detected_shot(settings, current_frames, fps, len(shots) + 1, current_reason))
            current_frames = [frame_path]
            current_tags = [frame_tags]
            current_reason = "max_duration"
            continue
        if len(current_frames) >= min_frames and max(boundary_score, rolling_score) >= tag_change_threshold:
            shots.append(build_detected_shot(settings, current_frames, fps, len(shots) + 1, "tag_change"))
            current_frames = [frame_path]
            current_tags = [frame_tags]
            current_reason = "tag_change"
            continue

        current_frames.append(frame_path)
        current_tags.append(frame_tags)

    if current_frames:
        shots.append(build_detected_shot(settings, current_frames, fps, len(shots) + 1, current_reason))
    return shots


def build_detected_shot(
    settings: AppSettings,
    frame_paths: list[Path],
    fps: float,
    order: int,
    boundary_reason: str,
) -> DetectedShot:
    first_index = parse_frame_index(frame_paths[0])
    last_index = parse_frame_index(frame_paths[-1])
    tags_summary = summarize_tags(frame_paths)
    key_frames = pick_key_frames(frame_paths)
    return DetectedShot(
        shot_id=f"shot_{order:03d}",
        order=order,
        start_seconds=max(0.0, (first_index - 1) / fps),
        end_seconds=max(0.0, (last_index - 1) / fps),
        duration_seconds=max((len(frame_paths) - 1) / fps, 1.0 / fps),
        frame_count=len(frame_paths),
        frame_paths=[project_relative_path(settings, path) for path in frame_paths],
        key_frames=[project_relative_path(settings, path) for path in key_frames],
        boundary_reason=boundary_reason,
        tags_summary=tags_summary,
    )


def sample_shot_frames(
    settings: AppSettings,
    character_id: str,
    video_id: str,
    similarity_threshold: float = 0.85,
    max_frames_per_shot: int = 6,
    min_frame_gap: int = 2,
) -> FrameSamplingResult:
    validate_character_id(character_id)
    if max_frames_per_shot <= 0:
        raise ValueError("max_frames_per_shot must be greater than 0.")
    shot_manifest = load_json(shot_manifest_path(settings, character_id, video_id))
    selected_frames: list[SampledFrame] = []
    for shot in shot_manifest.get("shots", []):
        frame_paths = [resolve_project_path(settings, value) for value in shot.get("frame_paths", [])]
        selected_frames.extend(
            select_frames_for_shot(
                settings=settings,
                shot_id=str(shot.get("shot_id", "")),
                frame_paths=frame_paths,
                fps=float(shot_manifest.get("analysis_profile", {}).get("effective_fps", 1.0) or 1.0),
                similarity_threshold=similarity_threshold,
                max_frames_per_shot=max_frames_per_shot,
                min_frame_gap=min_frame_gap,
            )
        )
    dataset_dir = export_sampled_dataset(settings, character_id, video_id, selected_frames)
    manifest_path = sampled_manifest_path(settings, character_id, video_id)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "manifest_type": SAMPLED_MANIFEST_TYPE,
                "generated_at": utc_timestamp(),
                "character_id": character_id,
                "video_id": video_id,
                "sampling": {
                    "similarity_threshold": similarity_threshold,
                    "max_frames_per_shot": max_frames_per_shot,
                    "min_frame_gap": min_frame_gap,
                },
                "dataset_dir": project_relative_path(settings, dataset_dir),
                "frames": [asdict(frame) for frame in selected_frames],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return FrameSamplingResult(
        manifest_path=manifest_path,
        dataset_dir=dataset_dir,
        selected_frame_count=len(selected_frames),
    )


def select_frames_for_shot(
    settings: AppSettings,
    shot_id: str,
    frame_paths: list[Path],
    fps: float,
    similarity_threshold: float,
    max_frames_per_shot: int,
    min_frame_gap: int,
) -> list[SampledFrame]:
    if not frame_paths:
        return []
    anchor_positions = sorted({0, len(frame_paths) // 2, len(frame_paths) - 1})
    selected_positions: list[int] = []
    selected: list[SampledFrame] = []
    for position in anchor_positions:
        selected_positions.append(position)
        selected.append(build_sampled_frame(settings, shot_id, frame_paths[position], fps, role=anchor_role(position, len(frame_paths)), similarity_score=0.0))
    for position, frame_path in enumerate(frame_paths):
        if position in anchor_positions:
            continue
        if len(selected) >= max_frames_per_shot:
            break
        if any(abs(position - other) < min_frame_gap for other in selected_positions):
            continue
        candidate_tags = read_frame_tags(frame_path)
        similarity = max(
            frame_similarity(candidate_tags, item.tags, frame_path, resolve_project_path(settings, item.frame_path))
            for item in selected
        )
        if similarity >= similarity_threshold:
            continue
        selected_positions.append(position)
        selected.append(build_sampled_frame(settings, shot_id, frame_path, fps, role="sampled", similarity_score=similarity))
    return sorted(selected, key=lambda item: item.frame_index)


def build_sampled_frame(settings: AppSettings, shot_id: str, frame_path: Path, fps: float, role: str, similarity_score: float) -> SampledFrame:
    frame_index = parse_frame_index(frame_path)
    return SampledFrame(
        shot_id=shot_id,
        frame_path=project_relative_path(settings, frame_path),
        frame_index=frame_index,
        timestamp_seconds=max(0.0, (frame_index - 1) / fps),
        role=role,
        similarity_score=round(similarity_score, 4),
        tags=read_frame_tags(frame_path),
    )


def export_sampled_dataset(
    settings: AppSettings,
    character_id: str,
    video_id: str,
    sampled_frames: list[SampledFrame],
) -> Path:
    dataset_dir = settings.datasets.lora / character_id / f"video_{video_id}_sampled"
    images_dir = dataset_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    for frame in sampled_frames:
        source = resolve_project_path(settings, frame.frame_path)
        destination = unique_destination(images_dir, source.name)
        shutil.copy2(source, destination)
        caption_source = source.with_suffix(".txt")
        caption_destination = destination.with_suffix(".txt")
        if caption_source.exists():
            shutil.copy2(caption_source, caption_destination)
        else:
            caption_destination.write_text(", ".join(frame.tags) + "\n", encoding="utf-8")
    metadata_path = dataset_dir / "metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "character_id": character_id,
                "video_id": video_id,
                "sampled_frame_count": len(sampled_frames),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return dataset_dir


def classify_sampled_frames(
    settings: AppSettings,
    character_id: str,
    video_id: str,
) -> FrameClassificationResult:
    validate_character_id(character_id)
    sampled_manifest = load_json(sampled_manifest_path(settings, character_id, video_id))
    classified_frames: list[ClassifiedFrame] = []
    for item in sampled_manifest.get("frames", []):
        tags = [normalize_tag(tag) for tag in item.get("tags", [])]
        classified_frames.append(
            ClassifiedFrame(
                frame_path=str(item.get("frame_path", "")),
                shot_id=str(item.get("shot_id", "")),
                face_angle=classify_face_angle(tags),
                expression=classify_expression(tags),
                body_framing=classify_body_framing(tags),
                tags=tags,
            )
        )
    manifest_path = classification_manifest_path(settings, character_id, video_id)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "manifest_type": CLASSIFICATION_MANIFEST_TYPE,
                "generated_at": utc_timestamp(),
                "character_id": character_id,
                "video_id": video_id,
                "counts": {
                    "classified_frames": len(classified_frames),
                },
                "classifications": [asdict(item) for item in classified_frames],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return FrameClassificationResult(manifest_path=manifest_path, classified_frame_count=len(classified_frames))


def read_frame_tags(frame_path: Path) -> list[str]:
    record_path = frame_path.with_suffix(".tags.json")
    if record_path.exists():
        try:
            record = load_tag_record(record_path)
            return [normalize_tag(tag) for tag in record.final_tags]
        except Exception:
            pass
    caption_path = frame_path.with_suffix(".txt")
    if caption_path.exists():
        text = caption_path.read_text(encoding="utf-8").strip()
        if text:
            return [normalize_tag(tag) for tag in text.split(",") if tag.strip()]
    file_size_bucket = max(1, frame_path.stat().st_size // 1024)
    fallback = [*infer_filename_tags(frame_path), f"size_{file_size_bucket}"]
    return [normalize_tag(tag) for tag in fallback]


def summarize_tags(frame_paths: list[Path], limit: int = 8) -> list[str]:
    counts: dict[str, int] = {}
    for frame_path in frame_paths:
        for tag in read_frame_tags(frame_path):
            counts[tag] = counts.get(tag, 0) + 1
    return [item[0] for item in sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))[:limit]]


def pick_key_frames(frame_paths: list[Path]) -> list[Path]:
    if not frame_paths:
        return []
    positions = sorted({0, len(frame_paths) // 2, len(frame_paths) - 1})
    return [frame_paths[position] for position in positions]


def tag_distance(tags_a: list[str], tags_b: list[str]) -> float:
    set_a = set(tags_a)
    set_b = set(tags_b)
    if not set_a and not set_b:
        return 0.0
    union = set_a | set_b
    intersection = set_a & set_b
    return 1.0 - (len(intersection) / max(1, len(union)))


def frame_similarity(tags_a: list[str], tags_b: list[str], frame_a: Path, frame_b: Path) -> float:
    set_a = set(tags_a)
    set_b = set(tags_b)
    union = set_a | set_b
    tag_score = len(set_a & set_b) / max(1, len(union)) if union else 1.0
    size_a = frame_a.stat().st_size
    size_b = frame_b.stat().st_size
    size_score = 1.0 - min(abs(size_a - size_b) / max(size_a, size_b, 1), 1.0)
    return round((tag_score * 0.8) + (size_score * 0.2), 4)


def classify_face_angle(tags: list[str]) -> str:
    if has_any(tags, "back_view", "from_behind"):
        return "back"
    if has_any(tags, "side", "side_view", "profile"):
        return "side"
    if has_any(tags, "three_quarter", "45_degree", "45"):
        return "three_quarter"
    if has_any(tags, "looking_up", "up"):
        return "up"
    if has_any(tags, "looking_down", "down"):
        return "down"
    if has_any(tags, "front", "looking_at_viewer", "portrait"):
        return "front"
    return "unknown"


def classify_expression(tags: list[str]) -> str:
    if has_any(tags, "smile", "happy", "grin"):
        return "smile"
    if has_any(tags, "angry", "frown"):
        return "angry"
    if has_any(tags, "sad", "cry"):
        return "sad"
    if has_any(tags, "surprised", "shock", "wide_eyes"):
        return "surprised"
    if has_any(tags, "serious", "neutral_face"):
        return "serious"
    return "unknown"


def classify_body_framing(tags: list[str]) -> str:
    if has_any(tags, "full_body", "standing", "sitting", "pose"):
        return "full_body"
    if has_any(tags, "upper_body", "waist_up", "cowboy_shot"):
        return "upper_body"
    if has_any(tags, "portrait", "close_up", "face_focus"):
        return "portrait"
    return "unknown"


def has_any(tags: list[str], *candidates: str) -> bool:
    values = set(tags)
    return any(normalize_tag(candidate) in values for candidate in candidates)


def normalize_tag(value: str) -> str:
    return value.strip().lower().replace(" ", "_")


def dedupe_tags(tags: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        normalized = normalize_tag(tag)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def parse_fraction(value: object) -> float | None:
    if value in (None, "", "0/0"):
        return None
    text = str(value)
    if "/" not in text:
        return float(text)
    numerator, denominator = text.split("/", 1)
    if float(denominator) == 0:
        return None
    return float(numerator) / float(denominator)


def parse_frame_index(frame_path: Path) -> int:
    digits = "".join(character for character in frame_path.stem if character.isdigit())
    if not digits:
        raise ValueError(f"Frame path does not contain an index: {frame_path}")
    return int(digits)


def optional_int(value: object) -> int | None:
    if value in (None, ""):
        return None
    return int(value)


def unique_destination(directory: Path, filename: str) -> Path:
    destination = directory / filename
    if not destination.exists():
        return destination
    stem = destination.stem
    suffix = destination.suffix
    index = 2
    while True:
        candidate = directory / f"{stem}_{index}{suffix}"
        if not candidate.exists():
            return candidate
        index += 1


def anchor_role(position: int, total: int) -> str:
    if position == 0:
        return "start"
    if position == total - 1:
        return "end"
    return "middle"


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Required manifest does not exist: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_project_path(settings: AppSettings, value: str | Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = settings.project_root / path
    return path


def shot_manifest_path(settings: AppSettings, character_id: str, video_id: str) -> Path:
    return settings.project_root / "manifests" / "characters" / character_id / "video_analysis" / f"{video_id}_shots.json"


def sampled_manifest_path(settings: AppSettings, character_id: str, video_id: str) -> Path:
    return settings.project_root / "manifests" / "characters" / character_id / "video_analysis" / f"{video_id}_sampled_frames.json"


def classification_manifest_path(settings: AppSettings, character_id: str, video_id: str) -> Path:
    return settings.project_root / "manifests" / "characters" / character_id / "video_analysis" / f"{video_id}_classifications.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="anime-video-shot",
        description="Shot detection, sampled-frame export, and lightweight classification for video analysis.",
    )
    parser.add_argument("--config", default="config/local_6gb.json", help="Path to the local runtime profile.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    detect = subparsers.add_parser("detect", help="Detect provisional shots from extracted video frames.")
    detect.add_argument("--character-id", required=True, help="Character id.")
    detect.add_argument("--video", required=True, help="Source video path.")
    detect.add_argument("--fps", type=float, default=2.0, help="Requested analysis fps.")
    detect.add_argument("--source-label", default="", help="Optional source label.")
    detect.add_argument("--auto-extract", action="store_true", help="Run frame extraction if frames are missing.")
    detect.add_argument("--reuse-import", action="store_true", help="Reuse an already imported video entry.")
    detect.add_argument("--min-shot-seconds", type=float, default=2.0, help="Minimum shot duration.")
    detect.add_argument("--max-shot-seconds", type=float, default=12.0, help="Maximum shot duration before forced split.")
    detect.add_argument("--tag-change-threshold", type=float, default=0.55, help="Boundary threshold for tag changes.")
    detect.add_argument("--target-max-frames", type=int, default=240, help="Adaptive cap for 60-300 second video analysis.")

    sample = subparsers.add_parser("sample", help="Remove similar frames and export a sampled dataset.")
    sample.add_argument("--character-id", required=True, help="Character id.")
    sample.add_argument("--video-id", required=True, help="Imported video id.")
    sample.add_argument("--similarity-threshold", type=float, default=0.85, help="Maximum similarity allowed between kept frames.")
    sample.add_argument("--max-frames-per-shot", type=int, default=6, help="Maximum kept frames per shot.")
    sample.add_argument("--min-frame-gap", type=int, default=2, help="Minimum positional gap between kept frames.")

    classify = subparsers.add_parser("classify", help="Classify sampled frames into face angle / expression / body framing.")
    classify.add_argument("--character-id", required=True, help="Character id.")
    classify.add_argument("--video-id", required=True, help="Imported video id.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    settings = load_settings(args.config)
    if args.command == "detect":
        result = detect_video_shots(
            settings=settings,
            character_id=args.character_id,
            video_path=args.video,
            fps=args.fps,
            source_label=args.source_label,
            auto_extract=args.auto_extract,
            reuse_import=args.reuse_import,
            min_shot_seconds=args.min_shot_seconds,
            max_shot_seconds=args.max_shot_seconds,
            tag_change_threshold=args.tag_change_threshold,
            target_max_frames=args.target_max_frames,
        )
        print(f"Shot manifest: {result.manifest_path}")
        print(f"Video id: {result.video_id}")
        print(f"Shots: {result.shot_count}")
        print(f"Frames: {result.frame_count}")
        print(f"Effective fps: {result.effective_fps}")
        return 0
    if args.command == "sample":
        result = sample_shot_frames(
            settings=settings,
            character_id=args.character_id,
            video_id=args.video_id,
            similarity_threshold=args.similarity_threshold,
            max_frames_per_shot=args.max_frames_per_shot,
            min_frame_gap=args.min_frame_gap,
        )
        print(f"Sampled manifest: {result.manifest_path}")
        print(f"Dataset: {result.dataset_dir}")
        print(f"Selected frames: {result.selected_frame_count}")
        return 0
    if args.command == "classify":
        result = classify_sampled_frames(
            settings=settings,
            character_id=args.character_id,
            video_id=args.video_id,
        )
        print(f"Classification manifest: {result.manifest_path}")
        print(f"Classified frames: {result.classified_frame_count}")
        return 0
    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
