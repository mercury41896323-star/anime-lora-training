from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, field
import json
from pathlib import Path

from .character_profile import validate_character_id
from .frame_extraction import build_frame_extraction_plan, extract_frames
from .lora_registry import project_relative_path, utc_timestamp
from .settings import AppSettings, load_settings
from .storyboard import Shot, Storyboard, save_storyboard, validate_story_id
from .video_importer import import_video_asset


@dataclass(frozen=True)
class SequenceFrame:
    frame_path: str
    frame_index: int
    timestamp_seconds: float
    role: str


@dataclass(frozen=True)
class VideoSequence:
    sequence_id: str
    order: int
    start_seconds: float
    end_seconds: float
    duration_seconds: float
    frame_count: int
    sampled_frames: list[SequenceFrame] = field(default_factory=list)
    key_frames: list[SequenceFrame] = field(default_factory=list)


@dataclass(frozen=True)
class LearningAssetCandidate:
    asset_id: str
    sequence_id: str
    role: str
    frame_path: str
    timestamp_seconds: float
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class VideoAnalysisResult:
    analysis_manifest_path: Path
    sequence_manifest_path: Path
    asset_manifest_path: Path
    storyboard_path: Path | None
    video_id: str
    frame_count: int
    sequence_count: int
    asset_count: int


def analyze_video_learning(
    settings: AppSettings,
    character_id: str,
    video_path: str | Path,
    fps: float = 1.0,
    sequence_seconds: float = 12.0,
    sample_every_n: int = 3,
    auto_extract: bool = False,
    reuse_import: bool = True,
    source_label: str = "",
    create_storyboard_draft: bool = True,
) -> VideoAnalysisResult:
    validate_character_id(character_id)
    if fps <= 0:
        raise ValueError("fps must be greater than 0.")
    if sequence_seconds <= 0:
        raise ValueError("sequence_seconds must be greater than 0.")
    if sample_every_n <= 0:
        raise ValueError("sample_every_n must be greater than 0.")

    import_result = import_video_asset(
        settings=settings,
        character_id=character_id,
        source_path=video_path,
        source_label=source_label,
        allow_existing=reuse_import,
    )
    frame_plan = build_frame_extraction_plan(
        settings=settings,
        video_path=import_result.asset.stored_path,
        character_id=character_id,
        fps=fps,
        output_group=import_result.asset.video_id,
    )
    if auto_extract and not frame_plan.output_dir.exists():
        return_code = extract_frames(frame_plan)
        if return_code != 0:
            raise RuntimeError(f"Frame extraction failed with code {return_code}.")

    frame_paths = collect_video_frames(frame_plan.output_dir)
    if not frame_paths:
        raise FileNotFoundError(
            f"No frames found for video analysis: {frame_plan.output_dir}. Run frame extraction first or use --auto-extract."
        )

    sequences = build_sequences(
        settings=settings,
        character_id=character_id,
        video_id=import_result.asset.video_id,
        frame_paths=frame_paths,
        fps=fps,
        sequence_seconds=sequence_seconds,
        sample_every_n=sample_every_n,
    )
    assets = build_learning_assets(
        settings=settings,
        character_id=character_id,
        video_id=import_result.asset.video_id,
        sequences=sequences,
    )
    sequence_manifest_path = write_sequence_manifest(
        settings=settings,
        character_id=character_id,
        video_id=import_result.asset.video_id,
        fps=fps,
        sequence_seconds=sequence_seconds,
        frame_dir=frame_plan.output_dir,
        sequences=sequences,
    )
    asset_manifest_path = write_learning_asset_manifest(
        settings=settings,
        character_id=character_id,
        video_id=import_result.asset.video_id,
        assets=assets,
    )
    storyboard_path = None
    if create_storyboard_draft:
        storyboard_path = write_sequence_storyboard(
            settings=settings,
            character_id=character_id,
            video_id=import_result.asset.video_id,
            source_label=import_result.asset.source_label,
            sequences=sequences,
        )
    analysis_manifest_path = write_analysis_manifest(
        settings=settings,
        character_id=character_id,
        video_id=import_result.asset.video_id,
        imported_video_path=import_result.asset.stored_path,
        frame_dir=frame_plan.output_dir,
        sequence_manifest_path=sequence_manifest_path,
        asset_manifest_path=asset_manifest_path,
        storyboard_path=storyboard_path,
        fps=fps,
        sequence_seconds=sequence_seconds,
        sample_every_n=sample_every_n,
        frame_count=len(frame_paths),
        sequence_count=len(sequences),
        asset_count=len(assets),
    )
    return VideoAnalysisResult(
        analysis_manifest_path=analysis_manifest_path,
        sequence_manifest_path=sequence_manifest_path,
        asset_manifest_path=asset_manifest_path,
        storyboard_path=storyboard_path,
        video_id=import_result.asset.video_id,
        frame_count=len(frame_paths),
        sequence_count=len(sequences),
        asset_count=len(assets),
    )


def collect_video_frames(frame_dir: Path) -> list[Path]:
    return sorted(path for path in frame_dir.glob("*.png") if path.is_file())


def build_sequences(
    settings: AppSettings,
    character_id: str,
    video_id: str,
    frame_paths: list[Path],
    fps: float,
    sequence_seconds: float,
    sample_every_n: int,
) -> list[VideoSequence]:
    frames_per_sequence = max(1, int(round(sequence_seconds * fps)))
    sequences: list[VideoSequence] = []
    for start_index in range(0, len(frame_paths), frames_per_sequence):
        chunk = frame_paths[start_index : start_index + frames_per_sequence]
        order = len(sequences) + 1
        sequence_id = f"{video_id}_seq_{order:03d}"
        first_frame_index = parse_frame_index(chunk[0])
        last_frame_index = parse_frame_index(chunk[-1])
        start_seconds = max(0.0, (first_frame_index - 1) / fps)
        end_seconds = max(start_seconds, (last_frame_index - 1) / fps)
        sampled_frames = build_sampled_frames(settings, chunk, fps, sample_every_n)
        key_frames = build_key_frames(settings, chunk, fps)
        sequences.append(
            VideoSequence(
                sequence_id=sequence_id,
                order=order,
                start_seconds=start_seconds,
                end_seconds=end_seconds,
                duration_seconds=max((len(chunk) - 1) / fps, 1.0 / fps),
                frame_count=len(chunk),
                sampled_frames=sampled_frames,
                key_frames=key_frames,
            )
        )
    return sequences


def build_sampled_frames(settings: AppSettings, frame_paths: list[Path], fps: float, sample_every_n: int) -> list[SequenceFrame]:
    sampled: list[SequenceFrame] = []
    for position, frame_path in enumerate(frame_paths):
        if position % sample_every_n != 0:
            continue
        frame_index = parse_frame_index(frame_path)
        sampled.append(
            SequenceFrame(
                frame_path=project_relative_path(settings, frame_path),
                frame_index=frame_index,
                timestamp_seconds=max(0.0, (frame_index - 1) / fps),
                role="sampled",
            )
        )
    return sampled


def build_key_frames(settings: AppSettings, frame_paths: list[Path], fps: float) -> list[SequenceFrame]:
    positions = sorted({0, len(frame_paths) // 2, len(frame_paths) - 1})
    roles = {0: "start", len(frame_paths) // 2: "middle", len(frame_paths) - 1: "end"}
    key_frames: list[SequenceFrame] = []
    for position in positions:
        frame_path = frame_paths[position]
        frame_index = parse_frame_index(frame_path)
        key_frames.append(
            SequenceFrame(
                frame_path=project_relative_path(settings, frame_path),
                frame_index=frame_index,
                timestamp_seconds=max(0.0, (frame_index - 1) / fps),
                role=roles[position],
            )
        )
    return key_frames


def build_learning_assets(
    settings: AppSettings,
    character_id: str,
    video_id: str,
    sequences: list[VideoSequence],
) -> list[LearningAssetCandidate]:
    assets: list[LearningAssetCandidate] = []
    for sequence in sequences:
        for frame in sequence.key_frames:
            assets.append(
                LearningAssetCandidate(
                    asset_id=f"{sequence.sequence_id}_{frame.role}",
                    sequence_id=sequence.sequence_id,
                    role="keyframe",
                    frame_path=frame.frame_path,
                    timestamp_seconds=frame.timestamp_seconds,
                    tags=[character_id, video_id, frame.role, "keyframe"],
                    metadata={
                        "sequence_order": sequence.order,
                        "frame_role": frame.role,
                    },
                )
            )
        for frame in sequence.sampled_frames:
            assets.append(
                LearningAssetCandidate(
                    asset_id=f"{sequence.sequence_id}_sample_{frame.frame_index:06d}",
                    sequence_id=sequence.sequence_id,
                    role="learning_frame",
                    frame_path=frame.frame_path,
                    timestamp_seconds=frame.timestamp_seconds,
                    tags=[character_id, video_id, "sampled", "learning_frame"],
                    metadata={
                        "sequence_order": sequence.order,
                        "frame_index": frame.frame_index,
                    },
                )
            )
    return assets


def write_sequence_manifest(
    settings: AppSettings,
    character_id: str,
    video_id: str,
    fps: float,
    sequence_seconds: float,
    frame_dir: Path,
    sequences: list[VideoSequence],
) -> Path:
    path = sequence_manifest_path(settings, character_id, video_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "manifest_type": "video_sequence_manifest",
                "generated_at": utc_timestamp(),
                "character_id": character_id,
                "video_id": video_id,
                "fps": fps,
                "sequence_seconds": sequence_seconds,
                "frame_dir": project_relative_path(settings, frame_dir),
                "sequences": [asdict(sequence) for sequence in sequences],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def write_learning_asset_manifest(
    settings: AppSettings,
    character_id: str,
    video_id: str,
    assets: list[LearningAssetCandidate],
) -> Path:
    path = learning_asset_manifest_path(settings, character_id, video_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "manifest_type": "video_learning_asset_manifest",
                "generated_at": utc_timestamp(),
                "character_id": character_id,
                "video_id": video_id,
                "assets": [asdict(asset) for asset in assets],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def write_sequence_storyboard(
    settings: AppSettings,
    character_id: str,
    video_id: str,
    source_label: str,
    sequences: list[VideoSequence],
) -> Path:
    story_id = build_story_id(character_id, video_id)
    validate_story_id(story_id)
    storyboard = Storyboard(
        story_id=story_id,
        title=f"{character_id} {video_id} sequence draft",
        created_at=utc_timestamp(),
        updated_at=utc_timestamp(),
        shots=[
            Shot(
                shot_id=f"shot_{sequence.order:03d}",
                order=sequence.order,
                title=f"Sequence {sequence.order:03d}",
                character_id=character_id,
                prompt=f"{character_id}, derived from {source_label or video_id}",
                duration_seconds=sequence.duration_seconds,
                camera="reference sequence",
                lighting="reference sequence",
                notes=build_storyboard_notes(sequence),
            )
            for sequence in sequences
        ],
    )
    return save_storyboard(settings, storyboard)


def build_storyboard_notes(sequence: VideoSequence) -> str:
    key_paths = ", ".join(frame.frame_path for frame in sequence.key_frames)
    return (
        f"start={sequence.start_seconds:.2f}s, end={sequence.end_seconds:.2f}s, "
        f"frames={sequence.frame_count}, keyframes={key_paths}"
    )


def write_analysis_manifest(
    settings: AppSettings,
    character_id: str,
    video_id: str,
    imported_video_path: Path,
    frame_dir: Path,
    sequence_manifest_path: Path,
    asset_manifest_path: Path,
    storyboard_path: Path | None,
    fps: float,
    sequence_seconds: float,
    sample_every_n: int,
    frame_count: int,
    sequence_count: int,
    asset_count: int,
) -> Path:
    path = analysis_manifest_path(settings, character_id, video_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "manifest_type": "video_learning_analysis",
        "generated_at": utc_timestamp(),
        "character_id": character_id,
        "video_id": video_id,
        "counts": {
            "frame_count": frame_count,
            "sequence_count": sequence_count,
            "asset_count": asset_count,
        },
        "settings": {
            "fps": fps,
            "sequence_seconds": sequence_seconds,
            "sample_every_n": sample_every_n,
        },
        "paths": {
            "video": project_relative_path(settings, imported_video_path),
            "frame_dir": project_relative_path(settings, frame_dir),
            "sequence_manifest": project_relative_path(settings, sequence_manifest_path),
            "asset_manifest": project_relative_path(settings, asset_manifest_path),
        },
        "next_steps": [
            "Review sequence manifest for shot boundaries.",
            "Review learning asset candidates for identity and motion usefulness.",
            "Promote selected sequences into Character Sheet or storyboard workflows.",
        ],
    }
    if storyboard_path is not None:
        payload["paths"]["storyboard"] = project_relative_path(settings, storyboard_path)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def build_story_id(character_id: str, video_id: str) -> str:
    story_id = f"{character_id}_{video_id}_seq"
    return story_id[:63].rstrip("_")


def parse_frame_index(frame_path: Path) -> int:
    digits = "".join(character for character in frame_path.stem if character.isdigit())
    if not digits:
        raise ValueError(f"Frame path does not contain an index: {frame_path}")
    return int(digits)


def sequence_manifest_path(settings: AppSettings, character_id: str, video_id: str) -> Path:
    return settings.project_root / "manifests" / "characters" / character_id / "video_analysis" / f"{video_id}_sequences.json"


def learning_asset_manifest_path(settings: AppSettings, character_id: str, video_id: str) -> Path:
    return settings.project_root / "manifests" / "characters" / character_id / "video_analysis" / f"{video_id}_learning_assets.json"


def analysis_manifest_path(settings: AppSettings, character_id: str, video_id: str) -> Path:
    return settings.project_root / "manifests" / "characters" / character_id / "video_analysis" / f"{video_id}_analysis.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="anime-video-analysis",
        description="Analyze video-derived frames into learning assets and sequence manifests.",
    )
    parser.add_argument("--config", default="config/local_6gb.json", help="Path to the local runtime profile.")
    parser.add_argument("--character-id", required=True, help="Character id.")
    parser.add_argument("--video", required=True, help="Source video path.")
    parser.add_argument("--fps", type=float, default=1.0, help="Frames per second used for extraction.")
    parser.add_argument("--sequence-seconds", type=float, default=12.0, help="Target duration of one sequence bucket.")
    parser.add_argument("--sample-every", type=int, default=3, help="Keep every Nth frame as a sampled learning frame.")
    parser.add_argument("--source-label", default="", help="Optional short label such as scene or episode.")
    parser.add_argument("--auto-extract", action="store_true", help="Run frame extraction if the grouped frame folder does not exist.")
    parser.add_argument("--no-storyboard", action="store_true", help="Do not create a storyboard draft from sequences.")
    parser.add_argument("--no-import-reuse", action="store_true", help="Fail if the video is already imported.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    settings = load_settings(args.config)
    result = analyze_video_learning(
        settings=settings,
        character_id=args.character_id,
        video_path=args.video,
        fps=args.fps,
        sequence_seconds=args.sequence_seconds,
        sample_every_n=args.sample_every,
        auto_extract=args.auto_extract,
        reuse_import=not args.no_import_reuse,
        source_label=args.source_label,
        create_storyboard_draft=not args.no_storyboard,
    )
    print(f"Analysis manifest: {result.analysis_manifest_path}")
    print(f"Sequence manifest: {result.sequence_manifest_path}")
    print(f"Learning assets: {result.asset_manifest_path}")
    if result.storyboard_path is not None:
        print(f"Storyboard: {result.storyboard_path}")
    print(f"Video id: {result.video_id}")
    print(f"Frames: {result.frame_count}")
    print(f"Sequences: {result.sequence_count}")
    print(f"Assets: {result.asset_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
