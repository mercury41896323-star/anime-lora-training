from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from .lora_registry import project_relative_path, utc_timestamp
from .phase6_pipeline import normalize_phase6_manifest_path
from .settings import AppSettings
from .storyboard import get_storyboard_path, load_storyboard
from .storyboard_editor_manifest import normalize_editor_manifest_path


EDIT_TIMELINE_MANIFEST_TYPE = "storyboard_edit_timeline"
DEFAULT_FRAME_RATE = 24
TRACK_ORDER = {
    "video_main": 10,
    "voice_main": 20,
    "sfx_main": 30,
    "lip_sync_signals": 40,
}


@dataclass(frozen=True)
class EditTimelineManifestResult:
    manifest_path: Path
    track_count: int
    clip_count: int
    duration_seconds: float


def build_edit_timeline_manifest(
    settings: AppSettings,
    story_id: str,
    output_path: str | Path | None = None,
    frame_rate: int = DEFAULT_FRAME_RATE,
) -> EditTimelineManifestResult:
    if frame_rate <= 0:
        raise ValueError("frame_rate must be greater than 0.")
    storyboard = load_storyboard(settings, story_id)
    selected_manifest = read_optional_manifest(normalize_editor_manifest_path(settings, story_id, None))
    phase6_manifest = read_optional_manifest(normalize_phase6_manifest_path(settings, story_id, None))
    motion_plan = read_optional_manifest(get_motion_clip_plan_path(settings, story_id))
    b_control_manifest = read_optional_manifest(get_b_control_manifest_path(settings, story_id))

    shot_entries = build_shot_entries(storyboard.shots, selected_manifest, phase6_manifest, b_control_manifest)
    tracks = build_tracks(settings, shot_entries, motion_plan)
    duration_seconds = round(
        max((clip["start_seconds"] + clip["duration_seconds"] for track in tracks for clip in track["clips"]), default=0.0),
        3,
    )
    manifest_path = normalize_edit_timeline_manifest_path(settings, story_id, output_path)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "manifest_type": EDIT_TIMELINE_MANIFEST_TYPE,
                "generated_at": utc_timestamp(),
                "story": {
                    "story_id": storyboard.story_id,
                    "title": storyboard.title,
                },
                "settings": {
                    "frame_rate": frame_rate,
                    "timeline_unit": "seconds",
                },
                "counts": {
                    "shot_count": len(shot_entries),
                    "track_count": len(tracks),
                    "clip_count": sum(len(track["clips"]) for track in tracks),
                },
                "duration_seconds": duration_seconds,
                "source_manifests": source_manifest_refs(settings, story_id),
                "tracks": tracks,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return EditTimelineManifestResult(
        manifest_path=manifest_path,
        track_count=len(tracks),
        clip_count=sum(len(track["clips"]) for track in tracks),
        duration_seconds=duration_seconds,
    )


def build_shot_entries(
    storyboard_shots: list[Any],
    selected_manifest: dict[str, Any],
    phase6_manifest: dict[str, Any],
    b_control_manifest: dict[str, Any],
) -> list[dict[str, Any]]:
    selected_by_shot = {str(shot.get("shot_id", "")): dict(shot) for shot in selected_manifest.get("shots", [])}
    phase6_by_shot = {str(shot.get("shot_id", "")): dict(shot) for shot in phase6_manifest.get("shots", [])}
    b_control_by_shot = {str(shot.get("shot_id", "")): dict(shot) for shot in b_control_manifest.get("shots", [])}
    entries: list[dict[str, Any]] = []
    cursor = 0.0
    for shot in sorted(storyboard_shots, key=lambda item: item.order):
        selected = selected_by_shot.get(shot.shot_id)
        phase6 = phase6_by_shot.get(shot.shot_id, {})
        b_control = b_control_by_shot.get(shot.shot_id, {})
        if selected is None:
            continue
        duration = positive_float(selected.get("duration_seconds", shot.duration_seconds), fallback=shot.duration_seconds or 1.0)
        entries.append(
            {
                "shot_id": shot.shot_id,
                "order": shot.order,
                "title": shot.title,
                "duration_seconds": duration,
                "timeline_start_seconds": round(cursor, 3),
                "selected": selected,
                "phase6": phase6,
                "b_control": b_control,
            }
        )
        cursor += duration
    return entries


def build_tracks(
    settings: AppSettings,
    shot_entries: list[dict[str, Any]],
    motion_plan: dict[str, Any],
) -> list[dict[str, Any]]:
    track_map: dict[str, dict[str, Any]] = {
        "video_main": {"track_id": "video_main", "track_type": "video", "order": TRACK_ORDER["video_main"], "clips": []},
        "voice_main": {"track_id": "voice_main", "track_type": "audio", "order": TRACK_ORDER["voice_main"], "clips": []},
        "sfx_main": {"track_id": "sfx_main", "track_type": "audio", "order": TRACK_ORDER["sfx_main"], "clips": []},
        "lip_sync_signals": {
            "track_id": "lip_sync_signals",
            "track_type": "signal",
            "order": TRACK_ORDER["lip_sync_signals"],
            "clips": [],
        },
    }
    motion_by_cue = {str(clip.get("cue_id", "")): dict(clip) for clip in motion_plan.get("clips", [])}
    for entry in shot_entries:
        add_video_clip(track_map["video_main"], entry)
        for cue in entry["phase6"].get("voice_cues", []):
            track_map["voice_main"]["clips"].append(build_voice_clip(settings, entry, cue))
        for cue in entry["phase6"].get("sfx_cues", []):
            track_map["sfx_main"]["clips"].append(build_sfx_clip(settings, entry, cue))
        for cue in entry["phase6"].get("lip_sync_cues", []):
            add_lip_sync_clips(track_map["lip_sync_signals"], entry, cue)
        for cue in entry["phase6"].get("motion_cues", []):
            motion_clip = motion_by_cue.get(str(cue.get("cue_id", "")))
            track_id = str((motion_clip or {}).get("track_name") or "motion_" + safe_track_name(str(cue.get("target", "motion_target"))))
            track = track_map.setdefault(
                track_id,
                {
                    "track_id": track_id,
                    "track_type": "animation",
                    "order": 100 + len(track_map),
                    "clips": [],
                },
            )
            track["clips"].append(build_motion_clip(entry, cue, motion_clip))
    return [
        {
            "track_id": track["track_id"],
            "track_type": track["track_type"],
            "order": track["order"],
            "clips": sorted(track["clips"], key=lambda item: (float(item["start_seconds"]), str(item["clip_id"]))),
        }
        for track in sorted(track_map.values(), key=lambda item: (int(item["order"]), str(item["track_id"])))
        if track["clips"]
    ]


def add_video_clip(track: dict[str, Any], entry: dict[str, Any]) -> None:
    selected = entry["selected"]
    result = dict(selected.get("selected_result") or {})
    unity = dict(selected.get("unity") or {})
    b_control = dict((entry.get("b_control") or {}).get("controls") or {})
    track["clips"].append(
        base_clip(
            clip_id="video_" + entry["shot_id"],
            shot_id=entry["shot_id"],
            source_type="selected_shot",
            source_path=str(result.get("stored_path", "")),
            start_seconds=entry["timeline_start_seconds"],
            duration_seconds=entry["duration_seconds"],
            metadata={
                "title": entry["title"],
                "result_id": str(result.get("result_id", "")),
                "timeline_clip_name": str(unity.get("timeline_clip_name", "")),
                "addressable_key": str(unity.get("addressable_key", "")),
                "kind": str(result.get("kind", "")),
                "b_control": b_control,
            },
        )
    )


def build_voice_clip(settings: AppSettings, entry: dict[str, Any], cue: dict[str, Any]) -> dict[str, Any]:
    source_path = str(cue.get("voice_asset_path", ""))
    return base_clip(
        clip_id="voice_" + str(cue.get("cue_id", "")),
        shot_id=entry["shot_id"],
        source_type="voice_cue",
        source_path=source_path,
        start_seconds=entry["timeline_start_seconds"] + non_negative_float(cue.get("start_seconds", 0.0)),
        duration_seconds=positive_float(cue.get("duration_seconds", 0.0), fallback=1.0),
        metadata={
            "cue_id": str(cue.get("cue_id", "")),
            "speaker": str(cue.get("speaker", "")),
            "text": str(cue.get("text", "")),
            "emotion": str(cue.get("emotion", "")),
            "exists": asset_exists(settings, source_path),
        },
    )


def build_sfx_clip(settings: AppSettings, entry: dict[str, Any], cue: dict[str, Any]) -> dict[str, Any]:
    source_path = str(cue.get("asset_path", ""))
    return base_clip(
        clip_id="sfx_" + str(cue.get("cue_id", "")),
        shot_id=entry["shot_id"],
        source_type="sfx_cue",
        source_path=source_path,
        start_seconds=entry["timeline_start_seconds"] + non_negative_float(cue.get("start_seconds", 0.0)),
        duration_seconds=positive_float(cue.get("duration_seconds", 0.0), fallback=1.0),
        metadata={
            "cue_id": str(cue.get("cue_id", "")),
            "label": str(cue.get("label", "")),
            "volume": float(cue.get("volume", 1.0)),
            "tags": list(cue.get("tags") or []),
            "asset_source": str(cue.get("asset_source", "")),
            "exists": asset_exists(settings, source_path),
        },
    )


def add_lip_sync_clips(track: dict[str, Any], entry: dict[str, Any], cue: dict[str, Any]) -> None:
    cue_start = entry["timeline_start_seconds"] + non_negative_float(cue.get("start_seconds", 0.0))
    for index, viseme in enumerate(cue.get("visemes", []) or []):
        time_seconds = cue_start + non_negative_float(viseme.get("time_seconds", 0.0))
        track["clips"].append(
            base_clip(
                clip_id=f"lip_{cue.get('cue_id', '')}_{index:03d}",
                shot_id=entry["shot_id"],
                source_type="lip_sync_viseme",
                source_path="",
                start_seconds=time_seconds,
                duration_seconds=0.01,
                metadata={
                    "cue_id": str(cue.get("cue_id", "")),
                    "voice_cue_id": str(cue.get("voice_cue_id", "")),
                    "mouth": str(viseme.get("mouth", "")),
                    "method": str(cue.get("method", "")),
                },
            )
        )


def build_motion_clip(
    entry: dict[str, Any],
    cue: dict[str, Any],
    motion_plan_clip: dict[str, Any] | None,
) -> dict[str, Any]:
    source_path = ""
    metadata = {
        "cue_id": str(cue.get("cue_id", "")),
        "target": str(cue.get("target", "")),
        "motion": str(cue.get("motion", "")),
        "source": str(cue.get("source", "")),
        "intensity": float(cue.get("intensity", 1.0)),
        "motion_plan": motion_plan_clip or {},
    }
    duration = positive_float(
        (motion_plan_clip or {}).get("duration_seconds", cue.get("duration_seconds", 0.0)),
        fallback=1.0,
    )
    return base_clip(
        clip_id=str((motion_plan_clip or {}).get("clip_id") or "motion_" + str(cue.get("cue_id", ""))),
        shot_id=entry["shot_id"],
        source_type="motion_cue",
        source_path=source_path,
        start_seconds=entry["timeline_start_seconds"] + non_negative_float(cue.get("start_seconds", 0.0)),
        duration_seconds=duration,
        metadata=metadata,
    )


def base_clip(
    clip_id: str,
    shot_id: str,
    source_type: str,
    source_path: str,
    start_seconds: float,
    duration_seconds: float,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    return {
        "clip_id": clip_id,
        "shot_id": shot_id,
        "source_type": source_type,
        "source_path": source_path,
        "start_seconds": round(start_seconds, 3),
        "duration_seconds": round(duration_seconds, 3),
        "metadata": metadata,
    }


def read_optional_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def source_manifest_refs(settings: AppSettings, story_id: str) -> dict[str, str]:
    base = settings.project_root / "manifests" / "storyboards" / story_id
    return {
        "selected_shots": project_relative_path(settings, normalize_editor_manifest_path(settings, story_id, None)),
        "phase6": project_relative_path(settings, normalize_phase6_manifest_path(settings, story_id, None)),
        "motion_clip_plan": project_relative_path(settings, base / "motion_clip_plan.json"),
        "sfx_asset_review": project_relative_path(settings, base / "sfx_asset_review.json"),
        "b_control": project_relative_path(settings, base / "b_control_manifest.json"),
    }


def get_motion_clip_plan_path(settings: AppSettings, story_id: str) -> Path:
    return settings.project_root / "manifests" / "storyboards" / story_id / "motion_clip_plan.json"


def get_b_control_manifest_path(settings: AppSettings, story_id: str) -> Path:
    return settings.project_root / "manifests" / "storyboards" / story_id / "b_control_manifest.json"


def normalize_edit_timeline_manifest_path(settings: AppSettings, story_id: str, output_path: str | Path | None) -> Path:
    if output_path is None:
        return settings.project_root / "manifests" / "storyboards" / story_id / "edit_timeline_manifest.json"
    path = Path(output_path)
    if not path.is_absolute():
        path = settings.project_root / path
    return path


def asset_exists(settings: AppSettings, source_path: str) -> bool:
    if not source_path:
        return False
    path = Path(source_path)
    if not path.is_absolute():
        path = settings.project_root / path
    return path.exists()


def positive_float(value: object, fallback: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return fallback
    return parsed if parsed > 0 else fallback


def non_negative_float(value: object) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, parsed)


def safe_track_name(value: str) -> str:
    normalized = "".join(character if character.isalnum() or character in {"_", "-"} else "_" for character in value)
    return normalized.strip("_") or "motion_target"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="anime-timeline-manifest",
        description="Build an edit timeline manifest from selected shots and Phase 6 cues.",
    )
    parser.add_argument("--config", default="config/local_6gb.json", help="Path to the local runtime profile.")
    parser.add_argument("--story-id", required=True, help="Storyboard id.")
    parser.add_argument("--output", default=None, help="Optional edit timeline manifest output path.")
    parser.add_argument("--frame-rate", type=int, default=DEFAULT_FRAME_RATE, help="Timeline frame rate hint.")
    return parser


def main(argv: list[str] | None = None) -> int:
    from .settings import load_settings

    parser = build_parser()
    args = parser.parse_args(argv)
    settings = load_settings(args.config)
    result = build_edit_timeline_manifest(
        settings=settings,
        story_id=args.story_id,
        output_path=args.output,
        frame_rate=args.frame_rate,
    )
    print(f"Wrote edit timeline manifest: {result.manifest_path}")
    print(f"Tracks: {result.track_count}")
    print(f"Clips: {result.clip_count}")
    print(f"Duration seconds: {result.duration_seconds}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
