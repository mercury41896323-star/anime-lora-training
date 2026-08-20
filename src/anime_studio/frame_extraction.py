from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess

from .settings import AppSettings


@dataclass(frozen=True)
class FrameExtractionPlan:
    video_path: Path
    output_dir: Path
    fps: float
    frame_pattern: str

    @property
    def command(self) -> list[str]:
        return [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(self.video_path),
            "-vf",
            f"fps={self.fps}",
            str(self.output_dir / self.frame_pattern),
        ]


def build_frame_extraction_plan(
    settings: AppSettings,
    video_path: str | Path,
    character_id: str,
    fps: float = 1.0,
    output_group: str | None = None,
) -> FrameExtractionPlan:
    source = Path(video_path)
    if fps <= 0:
        raise ValueError("fps must be greater than 0.")

    output_dir = settings.assets.processed / "characters" / character_id / "frames"
    if output_group:
        output_dir = output_dir / normalize_output_group(output_group)
    return FrameExtractionPlan(
        video_path=source,
        output_dir=output_dir,
        fps=fps,
        frame_pattern="frame_%06d.png",
    )


def extract_frames(plan: FrameExtractionPlan) -> int:
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg was not found. Install ffmpeg before extracting frames.")

    plan.output_dir.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(plan.command, check=False)
    return completed.returncode


def normalize_output_group(value: str) -> str:
    normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
    filtered = "".join(character for character in normalized if character.isalnum() or character == "_")
    return filtered or "video"
