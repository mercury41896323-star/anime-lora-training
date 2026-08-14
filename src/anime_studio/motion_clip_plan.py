from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from .lora_registry import utc_timestamp
from .settings import AppSettings
from .storyboard import get_storyboard_path, load_storyboard


MOTION_CUE_MANIFEST_TYPE = "storyboard_motion_cues"
MOTION_CLIP_PLAN_MANIFEST_TYPE = "storyboard_motion_clip_plan"
DEFAULT_FRAME_RATE = 24


@dataclass(frozen=True)
class MotionClipPlanResult:
    manifest_path: Path
    clip_count: int
    target_count: int


def build_motion_clip_plan(
    settings: AppSettings,
    story_id: str,
    output_path: str | Path | None = None,
    frame_rate: int = DEFAULT_FRAME_RATE,
) -> MotionClipPlanResult:
    if frame_rate <= 0:
        raise ValueError("frame_rate must be greater than 0.")
    storyboard = load_storyboard(settings, story_id)
    cues = read_motion_cues(settings, story_id)
    clips = [build_motion_clip(cue, frame_rate=frame_rate) for cue in cues]
    targets = sorted({str(clip.get("target", "")) for clip in clips if clip.get("target")})
    manifest_path = normalize_motion_clip_plan_path(settings, story_id, output_path)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "manifest_type": MOTION_CLIP_PLAN_MANIFEST_TYPE,
                "generated_at": utc_timestamp(),
                "story": {
                    "story_id": storyboard.story_id,
                    "title": storyboard.title,
                },
                "settings": {
                    "frame_rate": frame_rate,
                    "coordinate_space": "local_transform",
                },
                "counts": {
                    "clip_count": len(clips),
                    "target_count": len(targets),
                },
                "targets": targets,
                "clips": clips,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return MotionClipPlanResult(manifest_path=manifest_path, clip_count=len(clips), target_count=len(targets))


def build_motion_clip(cue: dict[str, Any], frame_rate: int) -> dict[str, Any]:
    duration = max(0.1, float(cue.get("duration_seconds", 1.0)))
    intensity = max(0.1, float(cue.get("intensity", 1.0)))
    motion_text = combined_lower(cue.get("target", ""), cue.get("motion", ""), cue.get("notes", ""))
    preset = infer_motion_preset(motion_text)
    return {
        "clip_id": "anim_" + str(cue.get("cue_id", "motion_cue")),
        "cue_id": str(cue.get("cue_id", "")),
        "shot_id": str(cue.get("shot_id", "")),
        "order": int(cue.get("order", 0)),
        "target": str(cue.get("target", "")),
        "track_name": "Phase6_Motion_" + safe_track_name(str(cue.get("target", "motion_target"))),
        "motion": str(cue.get("motion", "")),
        "source": str(cue.get("source", "")),
        "preset": preset,
        "frame_rate": frame_rate,
        "start_seconds": float(cue.get("start_seconds", 0.0)),
        "duration_seconds": duration,
        "intensity": intensity,
        "keyframes": build_keyframes(preset, duration=duration, intensity=intensity),
        "notes": str(cue.get("notes", "")),
    }


def infer_motion_preset(motion_text: str) -> str:
    if contains_any(motion_text, "nod", "bow", "うなず", "お辞儀"):
        return "head_nod"
    if contains_any(motion_text, "shake", "head shake", "首振"):
        return "head_shake"
    if contains_any(motion_text, "jump", "hop", "跳"):
        return "small_jump"
    if contains_any(motion_text, "step", "walk", "move", "歩", "移動"):
        return "small_step"
    if contains_any(motion_text, "pan", "truck", "dolly", "camera"):
        return "camera_drift"
    if contains_any(motion_text, "breathe", "idle", "呼吸"):
        return "idle_breathe"
    return "subtle_emphasis"


def build_keyframes(preset: str, duration: float, intensity: float) -> list[dict[str, Any]]:
    if preset == "head_nod":
        return [
            keyframe(0.0),
            keyframe(duration * 0.5, euler=(8.0 * intensity, 0.0, 0.0)),
            keyframe(duration),
        ]
    if preset == "head_shake":
        return [
            keyframe(0.0),
            keyframe(duration * 0.33, euler=(0.0, -8.0 * intensity, 0.0)),
            keyframe(duration * 0.66, euler=(0.0, 8.0 * intensity, 0.0)),
            keyframe(duration),
        ]
    if preset == "small_jump":
        return [
            keyframe(0.0),
            keyframe(duration * 0.5, position=(0.0, 0.35 * intensity, 0.0)),
            keyframe(duration),
        ]
    if preset == "small_step":
        return [
            keyframe(0.0),
            keyframe(duration, position=(0.35 * intensity, 0.0, 0.0)),
        ]
    if preset == "camera_drift":
        return [
            keyframe(0.0),
            keyframe(duration, position=(0.25 * intensity, 0.05 * intensity, 0.0), euler=(0.0, 3.0 * intensity, 0.0)),
        ]
    if preset == "idle_breathe":
        return [
            keyframe(0.0),
            keyframe(duration * 0.5, scale=(1.0, 1.02 * intensity, 1.0)),
            keyframe(duration),
        ]
    return [
        keyframe(0.0),
        keyframe(duration, euler=(0.0, 0.0, 4.0 * intensity)),
    ]


def keyframe(
    time_seconds: float,
    position: tuple[float, float, float] = (0.0, 0.0, 0.0),
    euler: tuple[float, float, float] = (0.0, 0.0, 0.0),
    scale: tuple[float, float, float] = (1.0, 1.0, 1.0),
) -> dict[str, Any]:
    return {
        "time_seconds": round(time_seconds, 3),
        "local_position": [round(value, 4) for value in position],
        "local_euler": [round(value, 4) for value in euler],
        "local_scale": [round(value, 4) for value in scale],
    }


def read_motion_cues(settings: AppSettings, story_id: str) -> list[dict[str, Any]]:
    path = get_motion_cues_path(settings, story_id)
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if data.get("manifest_type") != MOTION_CUE_MANIFEST_TYPE:
        raise ValueError(f"Unexpected motion manifest type in {path}: {data.get('manifest_type')}")
    return [dict(item) for item in data.get("items", [])]


def get_motion_cues_path(settings: AppSettings, story_id: str) -> Path:
    return get_storyboard_path(settings, story_id).parent / "motion_cues.json"


def normalize_motion_clip_plan_path(settings: AppSettings, story_id: str, output_path: str | Path | None) -> Path:
    if output_path is None:
        return settings.project_root / "manifests" / "storyboards" / story_id / "motion_clip_plan.json"
    path = Path(output_path)
    if not path.is_absolute():
        path = settings.project_root / path
    return path


def contains_any(source: str, *values: str) -> bool:
    return any(value.lower() in source for value in values)


def combined_lower(*values: object) -> str:
    return " ".join(str(value) for value in values if value).lower()


def safe_track_name(value: str) -> str:
    normalized = "".join(character if character.isalnum() or character in {"_", "-"} else "_" for character in value)
    return normalized.strip("_") or "motion_target"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="anime-motion-plan",
        description="Export Phase 6 motion cues as lightweight Unity AnimationClip plans.",
    )
    parser.add_argument("--config", default="config/local_6gb.json", help="Path to the local runtime profile.")
    parser.add_argument("--story-id", required=True, help="Storyboard id.")
    parser.add_argument("--output", default=None, help="Optional motion clip plan output path.")
    parser.add_argument("--frame-rate", type=int, default=DEFAULT_FRAME_RATE, help="Animation frame rate hint.")
    return parser


def main(argv: list[str] | None = None) -> int:
    from .settings import load_settings

    parser = build_parser()
    args = parser.parse_args(argv)
    settings = load_settings(args.config)
    result = build_motion_clip_plan(
        settings=settings,
        story_id=args.story_id,
        output_path=args.output,
        frame_rate=args.frame_rate,
    )
    print(f"Wrote motion clip plan: {result.manifest_path}")
    print(f"Clips: {result.clip_count}")
    print(f"Targets: {result.target_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
