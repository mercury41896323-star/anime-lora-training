from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import shutil
import subprocess

from .edit_export import export_edit_timeline
from .lora_registry import project_relative_path, utc_timestamp
from .settings import AppSettings


PREVIEW_MANIFEST_TYPE = "storyboard_preview_movie_plan"


@dataclass(frozen=True)
class PreviewMovieResult:
    manifest_path: Path
    output_movie: Path
    command: list[str]
    ran: bool
    return_code: int | None


def build_preview_movie(
    settings: AppSettings,
    story_id: str,
    manifest_path: str | Path | None = None,
    output_path: str | Path | None = None,
    ffmpeg_path: str = "ffmpeg",
    run: bool = False,
    overwrite: bool = True,
) -> PreviewMovieResult:
    export_result = export_edit_timeline(
        settings=settings,
        story_id=story_id,
        manifest_path=manifest_path,
        formats=("ffmpeg",),
    )
    output_movie = normalize_output_movie(settings, story_id, output_path)
    output_movie.parent.mkdir(parents=True, exist_ok=True)
    concat_path = export_result.files["ffmpeg"]
    command = build_ffmpeg_command(ffmpeg_path, concat_path, output_movie, overwrite)
    return_code: int | None = None
    if run:
        completed = subprocess.run(command, check=False)
        return_code = completed.returncode
    preview_manifest = write_preview_manifest(
        settings=settings,
        story_id=story_id,
        concat_path=concat_path,
        output_movie=output_movie,
        command=command,
        ran=run,
        return_code=return_code,
        ffmpeg_available=shutil.which(ffmpeg_path) is not None,
    )
    return PreviewMovieResult(
        manifest_path=preview_manifest,
        output_movie=output_movie,
        command=command,
        ran=run,
        return_code=return_code,
    )


def build_ffmpeg_command(ffmpeg_path: str, concat_path: Path, output_movie: Path, overwrite: bool) -> list[str]:
    command = [
        ffmpeg_path,
        "-safe",
        "0",
        "-f",
        "concat",
        "-i",
        str(concat_path),
        "-vsync",
        "vfr",
        "-pix_fmt",
        "yuv420p",
    ]
    if overwrite:
        command.append("-y")
    else:
        command.append("-n")
    command.append(str(output_movie))
    return command


def write_preview_manifest(
    settings: AppSettings,
    story_id: str,
    concat_path: Path,
    output_movie: Path,
    command: list[str],
    ran: bool,
    return_code: int | None,
    ffmpeg_available: bool,
) -> Path:
    path = settings.project_root / "manifests" / "storyboards" / story_id / "preview_movie_plan.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "manifest_type": PREVIEW_MANIFEST_TYPE,
                "generated_at": utc_timestamp(),
                "story_id": story_id,
                "concat_file": project_relative_path(settings, concat_path),
                "output_movie": project_relative_path(settings, output_movie),
                "command": command,
                "ran": ran,
                "return_code": return_code,
                "ffmpeg_available": ffmpeg_available,
                "notes": [
                    "Default mode writes the command and manifest without running FFmpeg.",
                    "Use --run to execute FFmpeg locally after checking the concat list.",
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def normalize_output_movie(settings: AppSettings, story_id: str, output_path: str | Path | None) -> Path:
    if output_path is None:
        return settings.project_root / "outputs" / "previews" / story_id / "preview.mp4"
    path = Path(output_path)
    if not path.is_absolute():
        path = settings.project_root / path
    return path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="anime-edit-preview",
        description="Build or run an FFmpeg preview movie command from edit_timeline_manifest.json.",
    )
    parser.add_argument("--config", default="config/local_6gb.json", help="Path to the local runtime profile.")
    parser.add_argument("--story-id", required=True, help="Storyboard id.")
    parser.add_argument("--manifest", default=None, help="Optional edit_timeline_manifest.json path.")
    parser.add_argument("--output", default=None, help="Preview movie output path.")
    parser.add_argument("--ffmpeg", default="ffmpeg", help="FFmpeg executable path.")
    parser.add_argument("--run", action="store_true", help="Run FFmpeg instead of only writing the plan.")
    parser.add_argument("--no-overwrite", action="store_true", help="Do not overwrite existing preview movie.")
    return parser


def main(argv: list[str] | None = None) -> int:
    from .settings import load_settings

    parser = build_parser()
    args = parser.parse_args(argv)
    settings = load_settings(args.config)
    result = build_preview_movie(
        settings=settings,
        story_id=args.story_id,
        manifest_path=args.manifest,
        output_path=args.output,
        ffmpeg_path=args.ffmpeg,
        run=args.run,
        overwrite=not args.no_overwrite,
    )
    print(f"Wrote preview movie plan: {result.manifest_path}")
    print(f"Output movie: {result.output_movie}")
    print("Command: " + " ".join(result.command))
    if result.ran:
        print(f"FFmpeg return code: {result.return_code}")
    return result.return_code or 0


if __name__ == "__main__":
    raise SystemExit(main())
