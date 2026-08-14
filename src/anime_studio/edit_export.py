from __future__ import annotations

import argparse
from dataclasses import dataclass
import html
import json
from pathlib import Path
from typing import Any

from .lora_registry import project_relative_path, utc_timestamp
from .settings import AppSettings
from .timeline_manifest import normalize_edit_timeline_manifest_path


DEFAULT_EXPORT_FORMATS = ("ffmpeg", "edl", "fcpxml")
EXPORT_MANIFEST_TYPE = "storyboard_edit_exports"


@dataclass(frozen=True)
class EditExportResult:
    export_dir: Path
    files: dict[str, Path]
    clip_count: int


def export_edit_timeline(
    settings: AppSettings,
    story_id: str,
    manifest_path: str | Path | None = None,
    output_dir: str | Path | None = None,
    formats: tuple[str, ...] = DEFAULT_EXPORT_FORMATS,
) -> EditExportResult:
    normalized_formats = normalize_formats(formats)
    manifest_file = normalize_edit_timeline_manifest_path(settings, story_id, manifest_path)
    manifest = read_timeline_manifest(manifest_file)
    video_clips = get_track_clips(manifest, "video")
    export_dir = normalize_export_dir(settings, story_id, output_dir)
    export_dir.mkdir(parents=True, exist_ok=True)

    files: dict[str, Path] = {}
    if "ffmpeg" in normalized_formats:
        files["ffmpeg"] = write_ffmpeg_concat(settings, export_dir, video_clips)
    if "edl" in normalized_formats:
        files["edl"] = write_cmx3600_edl(export_dir, manifest, video_clips)
    if "fcpxml" in normalized_formats:
        files["fcpxml"] = write_fcpxml(settings, export_dir, manifest, video_clips)
    files["manifest"] = write_export_manifest(settings, export_dir, manifest_file, files, video_clips, normalized_formats)
    return EditExportResult(export_dir=export_dir, files=files, clip_count=len(video_clips))


def read_timeline_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Edit timeline manifest not found: {path}")
    manifest = json.loads(path.read_text(encoding="utf-8-sig"))
    if manifest.get("manifest_type") != "storyboard_edit_timeline":
        raise ValueError(f"Unexpected manifest type in {path}: {manifest.get('manifest_type')}")
    return manifest


def get_track_clips(manifest: dict[str, Any], track_type: str) -> list[dict[str, Any]]:
    clips: list[dict[str, Any]] = []
    for track in manifest.get("tracks", []):
        if track.get("track_type") == track_type:
            clips.extend(dict(clip) for clip in track.get("clips", []))
    return sorted(clips, key=lambda clip: (float(clip.get("start_seconds", 0.0)), str(clip.get("clip_id", ""))))


def write_ffmpeg_concat(settings: AppSettings, export_dir: Path, video_clips: list[dict[str, Any]]) -> Path:
    path = export_dir / "ffmpeg_concat.txt"
    lines = ["ffconcat version 1.0"]
    for clip in video_clips:
        source_path = resolve_source_path(settings, str(clip.get("source_path", "")))
        if not source_path:
            continue
        lines.append("file '" + escape_ffconcat_path(source_path) + "'")
        lines.append("duration " + format_seconds(float(clip.get("duration_seconds", 1.0))))
    if video_clips:
        last_source = resolve_source_path(settings, str(video_clips[-1].get("source_path", "")))
        if last_source:
            lines.append("file '" + escape_ffconcat_path(last_source) + "'")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_cmx3600_edl(export_dir: Path, manifest: dict[str, Any], video_clips: list[dict[str, Any]]) -> Path:
    path = export_dir / "timeline.edl"
    frame_rate = frame_rate_from_manifest(manifest)
    title = str(manifest.get("story", {}).get("title") or manifest.get("story", {}).get("story_id") or "AI Anime Studio")
    lines = [
        "TITLE: " + sanitize_edl_text(title),
        "FCM: NON-DROP FRAME",
        "",
    ]
    for index, clip in enumerate(video_clips, start=1):
        start = float(clip.get("start_seconds", 0.0))
        duration = max(float(clip.get("duration_seconds", 1.0)), 0.001)
        source_in = 0.0
        source_out = duration
        record_in = start
        record_out = start + duration
        reel = sanitize_reel_name(str(clip.get("shot_id") or clip.get("clip_id") or f"SHOT{index:03d}"))
        lines.append(
            f"{index:03d}  {reel:<8} V     C        "
            f"{to_timecode(source_in, frame_rate)} {to_timecode(source_out, frame_rate)} "
            f"{to_timecode(record_in, frame_rate)} {to_timecode(record_out, frame_rate)}"
        )
        lines.append("* FROM CLIP NAME: " + sanitize_edl_text(str(clip.get("clip_id", ""))))
        lines.append("* SOURCE FILE: " + sanitize_edl_text(str(clip.get("source_path", ""))))
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def write_fcpxml(settings: AppSettings, export_dir: Path, manifest: dict[str, Any], video_clips: list[dict[str, Any]]) -> Path:
    path = export_dir / "timeline.fcpxml"
    story = manifest.get("story", {})
    story_id = str(story.get("story_id") or "storyboard")
    title = str(story.get("title") or story_id)
    frame_rate = frame_rate_from_manifest(manifest)
    duration = float(manifest.get("duration_seconds", 0.0))
    resource_lines = [
        f'    <format id="fmt1" name="FFVideoFormatRateUndefined" frameDuration="1/{frame_rate}s"/>'
    ]
    spine_lines: list[str] = []
    for index, clip in enumerate(video_clips, start=1):
        asset_id = f"asset{index}"
        source_path = resolve_source_path(settings, str(clip.get("source_path", "")))
        resource_lines.append(
            f'    <asset id="{asset_id}" name="{xml_attr(str(clip.get("clip_id", asset_id)))}" '
            f'src="{xml_attr(path_to_file_uri(source_path))}"/>'
        )
        spine_lines.append(
            f'              <asset-clip name="{xml_attr(str(clip.get("clip_id", asset_id)))}" ref="{asset_id}" '
            f'offset="{format_seconds(float(clip.get("start_seconds", 0.0)))}s" '
            f'duration="{format_seconds(float(clip.get("duration_seconds", 1.0)))}s"/>'
        )
    xml = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<fcpxml version="1.10">',
        '  <resources>',
        *resource_lines,
        '  </resources>',
        '  <library>',
        f'    <event name="{xml_attr(story_id)}">',
        f'      <project name="{xml_attr(title)}">',
        f'        <sequence duration="{format_seconds(duration)}s" format="fmt1">',
        '          <spine>',
        *spine_lines,
        '          </spine>',
        '        </sequence>',
        '      </project>',
        '    </event>',
        '  </library>',
        '</fcpxml>',
        '',
    ]
    path.write_text("\n".join(xml), encoding="utf-8")
    return path


def write_export_manifest(
    settings: AppSettings,
    export_dir: Path,
    source_manifest: Path,
    files: dict[str, Path],
    video_clips: list[dict[str, Any]],
    formats: tuple[str, ...],
) -> Path:
    path = export_dir / "edit_export_manifest.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "manifest_type": EXPORT_MANIFEST_TYPE,
                "generated_at": utc_timestamp(),
                "source_manifest": project_relative_path(settings, source_manifest),
                "formats": list(formats),
                "clip_count": len(video_clips),
                "files": {name: project_relative_path(settings, file_path) for name, file_path in files.items()},
                "notes": [
                    "ffmpeg concat output is a lightweight handoff list.",
                    "EDL and FCPXML are simple offline-edit interchange exports.",
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def normalize_export_dir(settings: AppSettings, story_id: str, output_dir: str | Path | None) -> Path:
    if output_dir is None:
        return settings.project_root / "manifests" / "storyboards" / story_id / "edit_exports"
    path = Path(output_dir)
    if not path.is_absolute():
        path = settings.project_root / path
    return path


def normalize_formats(formats: tuple[str, ...]) -> tuple[str, ...]:
    normalized: list[str] = []
    for export_format in formats:
        for item in str(export_format).split(","):
            value = item.strip().lower()
            if not value:
                continue
            if value == "xml":
                value = "fcpxml"
            if value not in DEFAULT_EXPORT_FORMATS:
                raise ValueError(f"Unsupported edit export format: {value}")
            if value not in normalized:
                normalized.append(value)
    return tuple(normalized or DEFAULT_EXPORT_FORMATS)


def resolve_source_path(settings: AppSettings, source_path: str) -> str:
    if not source_path:
        return ""
    path = Path(source_path)
    if not path.is_absolute():
        path = settings.project_root / path
    return path.resolve().as_posix()


def escape_ffconcat_path(path: str) -> str:
    return path.replace("\\", "\\\\").replace("'", "'\\''")


def to_timecode(seconds: float, frame_rate: int) -> str:
    total_frames = max(0, int(round(seconds * frame_rate)))
    frames = total_frames % frame_rate
    total_seconds = total_frames // frame_rate
    seconds_part = total_seconds % 60
    total_minutes = total_seconds // 60
    minutes = total_minutes % 60
    hours = total_minutes // 60
    return f"{hours:02d}:{minutes:02d}:{seconds_part:02d}:{frames:02d}"


def frame_rate_from_manifest(manifest: dict[str, Any]) -> int:
    frame_rate = int(manifest.get("settings", {}).get("frame_rate", 24))
    return frame_rate if frame_rate > 0 else 24


def format_seconds(value: float) -> str:
    return f"{value:.3f}".rstrip("0").rstrip(".") or "0"


def sanitize_reel_name(value: str) -> str:
    normalized = "".join(character.upper() if character.isalnum() else "_" for character in value)
    return (normalized.strip("_") or "REEL")[:8]


def sanitize_edl_text(value: str) -> str:
    return value.replace("\r", " ").replace("\n", " ").strip()


def path_to_file_uri(path: str) -> str:
    if not path:
        return ""
    return Path(path).as_uri()


def xml_attr(value: str) -> str:
    return html.escape(value, quote=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="anime-edit-export",
        description="Export an edit timeline manifest to FFmpeg concat, EDL, and FCPXML handoff files.",
    )
    parser.add_argument("--config", default="config/local_6gb.json", help="Path to the local runtime profile.")
    parser.add_argument("--story-id", required=True, help="Storyboard id.")
    parser.add_argument("--manifest", default=None, help="Optional edit_timeline_manifest.json path.")
    parser.add_argument("--output-dir", default=None, help="Optional export output directory.")
    parser.add_argument(
        "--formats",
        default=",".join(DEFAULT_EXPORT_FORMATS),
        help="Comma-separated formats: ffmpeg, edl, fcpxml.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    from .settings import load_settings

    parser = build_parser()
    args = parser.parse_args(argv)
    settings = load_settings(args.config)
    result = export_edit_timeline(
        settings=settings,
        story_id=args.story_id,
        manifest_path=args.manifest,
        output_dir=args.output_dir,
        formats=tuple(args.formats.split(",")),
    )
    print(f"Wrote edit exports: {result.export_dir}")
    print(f"Clips: {result.clip_count}")
    for name, path in result.files.items():
        print(f"{name}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
