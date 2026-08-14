from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import re
import struct
import wave
from pathlib import Path
from typing import Any

from .asset_library import search_asset_library
from .lora_registry import project_relative_path, utc_timestamp
from .settings import AppSettings
from .storyboard import Shot, get_storyboard_path, load_storyboard
from .storyboard_editor_manifest import normalize_editor_manifest_path


CUE_ID_PATTERN = re.compile(r"[^a-z0-9_-]+")
DEFAULT_LANGUAGE = "ja"
DEFAULT_VOICE_CHARS_PER_SECOND = 8.0
DEFAULT_SFX_DURATION_SECONDS = 1.0
DEFAULT_MOTION_DURATION_SECONDS = 1.0
DEFAULT_SFX_ASSET_LIMIT = 3
SFX_ASSET_KINDS = ("sfx", "audio", "other")
SUPPORTED_LIP_SYNC_PROVIDERS = {"text", "wav-rms"}
SFX_TAG_PATTERN = re.compile(r"[a-z0-9_-]+|[一-龥ぁ-んァ-ンー]+", re.IGNORECASE)
SFX_TAG_KEYWORDS = {
    "ambience": ("ambience",),
    "ambient": ("ambience",),
    "atmos": ("ambience",),
    "bgm": ("music",),
    "door": ("door", "impact"),
    "explosion": ("explosion", "impact"),
    "fire": ("fire",),
    "footstep": ("footstep", "movement"),
    "footsteps": ("footstep", "movement"),
    "hit": ("impact",),
    "impact": ("impact",),
    "magic": ("magic",),
    "rain": ("rain", "water", "ambience"),
    "soft": ("soft",),
    "sparkle": ("magic", "sparkle"),
    "thunder": ("thunder", "impact"),
    "water": ("water",),
    "wind": ("wind", "ambience"),
    "whoosh": ("whoosh", "movement"),
    "風": ("wind", "ambience"),
    "雨": ("rain", "water", "ambience"),
    "足音": ("footstep", "movement"),
    "爆発": ("explosion", "impact"),
    "魔法": ("magic",),
}


@dataclass(frozen=True)
class Phase6ManifestResult:
    manifest_path: Path
    shot_count: int
    voice_count: int
    lip_sync_count: int
    sfx_count: int
    motion_count: int


@dataclass(frozen=True)
class CueWriteResult:
    manifest_path: Path
    cue_id: str
    cue_count: int


@dataclass(frozen=True)
class LipSyncPlanResult:
    manifest_path: Path
    cue_count: int


def add_voice_cue(
    settings: AppSettings,
    story_id: str,
    shot_id: str,
    text: str,
    speaker: str = "",
    character_id: str = "",
    voice_asset_path: str | Path = "",
    emotion: str = "",
    language: str = DEFAULT_LANGUAGE,
    start_seconds: float = 0.0,
    duration_seconds: float | None = None,
    notes: str = "",
) -> CueWriteResult:
    shot = find_shot(settings, story_id, shot_id)
    validate_non_empty(text, "text")
    validate_non_negative(start_seconds, "start_seconds")
    resolved_duration = duration_seconds if duration_seconds is not None else estimate_voice_duration(text, shot)
    validate_positive(resolved_duration, "duration_seconds")
    cue_id = build_cue_id("voice", shot_id, text)
    cue = {
        "cue_id": cue_id,
        "shot_id": shot.shot_id,
        "order": shot.order,
        "character_id": character_id or shot.character_id,
        "speaker": speaker or character_id or shot.character_id,
        "text": text,
        "language": language,
        "emotion": emotion,
        "voice_asset_path": normalize_optional_asset_path(settings, voice_asset_path),
        "start_seconds": start_seconds,
        "duration_seconds": resolved_duration,
        "notes": notes,
        "updated_at": utc_timestamp(),
    }
    return upsert_cue(get_voice_cues_path(settings, story_id), "storyboard_voice_cues", story_id, cue)


def add_sfx_cue(
    settings: AppSettings,
    story_id: str,
    shot_id: str,
    label: str,
    asset_path: str | Path = "",
    start_seconds: float = 0.0,
    duration_seconds: float = DEFAULT_SFX_DURATION_SECONDS,
    volume: float = 1.0,
    tags: list[str] | None = None,
    asset_query: str = "",
    asset_limit: int = DEFAULT_SFX_ASSET_LIMIT,
    notes: str = "",
) -> CueWriteResult:
    shot = find_shot(settings, story_id, shot_id)
    validate_non_empty(label, "label")
    validate_non_negative(start_seconds, "start_seconds")
    validate_positive(duration_seconds, "duration_seconds")
    if volume < 0:
        raise ValueError("volume must be 0 or greater.")
    auto_tags = infer_sfx_tags(label=label, asset_path=asset_path)
    resolved_tags = normalize_sfx_tags(tags) if tags else auto_tags
    candidate_query = asset_query.strip() or build_sfx_asset_query(label, resolved_tags)
    asset_candidates = suggest_sfx_asset_candidates(settings, candidate_query, asset_limit)
    cue_id = build_cue_id("sfx", shot_id, label)
    cue = {
        "cue_id": cue_id,
        "shot_id": shot.shot_id,
        "order": shot.order,
        "label": label,
        "asset_path": normalize_optional_asset_path(settings, asset_path),
        "start_seconds": start_seconds,
        "duration_seconds": duration_seconds,
        "volume": volume,
        "tags": resolved_tags,
        "auto_tags": auto_tags,
        "tag_source": "manual" if tags else "auto",
        "asset_library_query": candidate_query,
        "asset_library_candidates": asset_candidates,
        "notes": notes,
        "updated_at": utc_timestamp(),
    }
    return upsert_cue(get_sfx_cues_path(settings, story_id), "storyboard_sfx_cues", story_id, cue)


def add_motion_cue(
    settings: AppSettings,
    story_id: str,
    shot_id: str,
    target: str,
    motion: str,
    source: str = "manual",
    start_seconds: float = 0.0,
    duration_seconds: float = DEFAULT_MOTION_DURATION_SECONDS,
    intensity: float = 1.0,
    notes: str = "",
) -> CueWriteResult:
    shot = find_shot(settings, story_id, shot_id)
    validate_non_empty(target, "target")
    validate_non_empty(motion, "motion")
    validate_non_negative(start_seconds, "start_seconds")
    validate_positive(duration_seconds, "duration_seconds")
    if intensity < 0:
        raise ValueError("intensity must be 0 or greater.")
    cue_id = build_cue_id("motion", shot_id, f"{target}-{motion}")
    cue = {
        "cue_id": cue_id,
        "shot_id": shot.shot_id,
        "order": shot.order,
        "target": target,
        "motion": motion,
        "source": source,
        "start_seconds": start_seconds,
        "duration_seconds": duration_seconds,
        "intensity": intensity,
        "notes": notes,
        "updated_at": utc_timestamp(),
    }
    return upsert_cue(get_motion_cues_path(settings, story_id), "storyboard_motion_cues", story_id, cue)


def build_lip_sync_plan(
    settings: AppSettings,
    story_id: str,
    output_path: str | Path | None = None,
    provider: str = "text",
) -> LipSyncPlanResult:
    load_storyboard(settings, story_id)
    validate_lip_sync_provider(provider)
    voice_cues = read_cue_items(get_voice_cues_path(settings, story_id), "storyboard_voice_cues")
    lip_sync_cues = [render_lip_sync_cue(cue, settings=settings, provider=provider) for cue in voice_cues]
    path = normalize_lip_sync_plan_path(settings, story_id, output_path)
    write_cue_manifest(path, "storyboard_lip_sync_plan", story_id, lip_sync_cues)
    return LipSyncPlanResult(manifest_path=path, cue_count=len(lip_sync_cues))


def export_phase6_manifest(
    settings: AppSettings,
    story_id: str,
    output_path: str | Path | None = None,
) -> Phase6ManifestResult:
    storyboard = load_storyboard(settings, story_id)
    selected_shots = read_selected_shot_map(settings, story_id)
    voice_by_shot = group_by_shot(read_cue_items(get_voice_cues_path(settings, story_id), "storyboard_voice_cues"))
    lip_sync_by_shot = group_by_shot(read_cue_items(get_lip_sync_plan_path(settings, story_id), "storyboard_lip_sync_plan"))
    sfx_by_shot = group_by_shot(read_cue_items(get_sfx_cues_path(settings, story_id), "storyboard_sfx_cues"))
    motion_by_shot = group_by_shot(read_cue_items(get_motion_cues_path(settings, story_id), "storyboard_motion_cues"))
    shots = [
        {
            "shot_id": shot.shot_id,
            "order": shot.order,
            "title": shot.title,
            "duration_seconds": shot.duration_seconds,
            "selected_result": selected_shots.get(shot.shot_id, {}).get("selected_result", {}),
            "voice_cues": voice_by_shot.get(shot.shot_id, []),
            "lip_sync_cues": lip_sync_by_shot.get(shot.shot_id, []),
            "sfx_cues": sfx_by_shot.get(shot.shot_id, []),
            "motion_cues": motion_by_shot.get(shot.shot_id, []),
        }
        for shot in sorted(storyboard.shots, key=lambda item: item.order)
    ]
    manifest_path = normalize_phase6_manifest_path(settings, story_id, output_path)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "manifest_type": "storyboard_phase6_manifest",
                "generated_at": utc_timestamp(),
                "story": {"story_id": storyboard.story_id, "title": storyboard.title},
                "counts": {
                    "shot_count": len(shots),
                    "voice_count": sum(len(items) for items in voice_by_shot.values()),
                    "lip_sync_count": sum(len(items) for items in lip_sync_by_shot.values()),
                    "sfx_count": sum(len(items) for items in sfx_by_shot.values()),
                    "motion_count": sum(len(items) for items in motion_by_shot.values()),
                },
                "unity": {
                    "timeline_track_hints": [
                        "voice_audio_track",
                        "lip_sync_signal_track",
                        "sfx_audio_track",
                        "motion_animation_track",
                    ]
                },
                "shots": shots,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return Phase6ManifestResult(
        manifest_path=manifest_path,
        shot_count=len(shots),
        voice_count=sum(len(items) for items in voice_by_shot.values()),
        lip_sync_count=sum(len(items) for items in lip_sync_by_shot.values()),
        sfx_count=sum(len(items) for items in sfx_by_shot.values()),
        motion_count=sum(len(items) for items in motion_by_shot.values()),
    )


def render_lip_sync_cue(
    voice_cue: dict[str, Any],
    settings: AppSettings | None = None,
    provider: str = "text",
) -> dict[str, Any]:
    validate_lip_sync_provider(provider)
    duration = float(voice_cue.get("duration_seconds", 1.0))
    text = str(voice_cue.get("text", ""))
    source_voice_asset_path = str(voice_cue.get("voice_asset_path", ""))
    if provider == "wav-rms" and settings is not None and source_voice_asset_path:
        audio_result = build_wav_rms_visemes(
            settings=settings,
            voice_asset_path=source_voice_asset_path,
            text=text,
            fallback_duration_seconds=duration,
        )
        return {
            "cue_id": build_cue_id("lip", str(voice_cue.get("shot_id", "")), str(voice_cue.get("cue_id", ""))),
            "shot_id": str(voice_cue.get("shot_id", "")),
            "order": int(voice_cue.get("order", 0)),
            "voice_cue_id": str(voice_cue.get("cue_id", "")),
            "method": audio_result["method"],
            "provider": provider,
            "source_voice_asset_path": source_voice_asset_path,
            "text": text,
            "start_seconds": float(voice_cue.get("start_seconds", 0.0)),
            "duration_seconds": audio_result["duration_seconds"],
            "visemes": audio_result["visemes"],
            "analysis": audio_result["analysis"],
            "updated_at": utc_timestamp(),
        }
    return {
        "cue_id": build_cue_id("lip", str(voice_cue.get("shot_id", "")), str(voice_cue.get("cue_id", ""))),
        "shot_id": str(voice_cue.get("shot_id", "")),
        "order": int(voice_cue.get("order", 0)),
        "voice_cue_id": str(voice_cue.get("cue_id", "")),
        "method": "placeholder_viseme_timing",
        "provider": provider,
        "source_voice_asset_path": source_voice_asset_path,
        "text": text,
        "start_seconds": float(voice_cue.get("start_seconds", 0.0)),
        "duration_seconds": duration,
        "visemes": build_placeholder_visemes(text, duration),
        "updated_at": utc_timestamp(),
    }


def build_wav_rms_visemes(
    settings: AppSettings,
    voice_asset_path: str | Path,
    text: str,
    fallback_duration_seconds: float,
) -> dict[str, Any]:
    path = normalize_project_path(settings, voice_asset_path)
    if not path.exists() or path.suffix.lower() != ".wav":
        return build_audio_fallback_result(text, fallback_duration_seconds, "missing_or_unsupported_wav")
    try:
        with wave.open(str(path), "rb") as wav_file:
            sample_rate = wav_file.getframerate()
            channel_count = wav_file.getnchannels()
            sample_width = wav_file.getsampwidth()
            frame_count = wav_file.getnframes()
            duration_seconds = round(frame_count / sample_rate, 3) if sample_rate else fallback_duration_seconds
            window_count = max(4, min(48, int(max(duration_seconds, 0.1) * 12)))
            frames_per_window = max(1, frame_count // window_count)
            energies: list[float] = []
            for _ in range(window_count):
                frame_bytes = wav_file.readframes(frames_per_window)
                if not frame_bytes:
                    break
                energies.append(calculate_pcm_rms(frame_bytes, sample_width, channel_count))
    except (wave.Error, EOFError, OSError, ValueError):
        return build_audio_fallback_result(text, fallback_duration_seconds, "wav_read_failed")
    if not energies:
        return build_audio_fallback_result(text, fallback_duration_seconds, "empty_wav")
    max_energy = max(energies) or 1.0
    letters = [character for character in text if not character.isspace()]
    visemes: list[dict[str, float | str]] = []
    for index, energy in enumerate(energies):
        normalized_energy = energy / max_energy
        time_seconds = round((duration_seconds * index) / max(len(energies), 1), 3)
        if normalized_energy < 0.08:
            mouth = "closed"
        elif letters:
            mouth = estimate_mouth_shape(letters[min(index, len(letters) - 1)])
        else:
            mouth = "neutral"
        visemes.append({"time_seconds": time_seconds, "mouth": mouth, "energy": round(normalized_energy, 3)})
    visemes.append({"time_seconds": round(duration_seconds, 3), "mouth": "closed", "energy": 0.0})
    return {
        "method": "wav_rms_viseme_timing",
        "duration_seconds": duration_seconds,
        "visemes": visemes,
        "analysis": {
            "provider": "wav-rms",
            "sample_rate": sample_rate,
            "channel_count": channel_count,
            "sample_width": sample_width,
            "frame_count": frame_count,
            "window_count": len(energies),
        },
    }


def build_audio_fallback_result(text: str, fallback_duration_seconds: float, reason: str) -> dict[str, Any]:
    return {
        "method": "placeholder_viseme_timing",
        "duration_seconds": fallback_duration_seconds,
        "visemes": build_placeholder_visemes(text, fallback_duration_seconds),
        "analysis": {"provider": "text", "fallback_reason": reason},
    }


def calculate_pcm_rms(frame_bytes: bytes, sample_width: int, channel_count: int) -> float:
    if sample_width == 1:
        samples = [sample - 128 for sample in frame_bytes]
    elif sample_width == 2:
        sample_count = len(frame_bytes) // 2
        samples = list(struct.unpack("<" + "h" * sample_count, frame_bytes[: sample_count * 2]))
    elif sample_width == 4:
        sample_count = len(frame_bytes) // 4
        samples = list(struct.unpack("<" + "i" * sample_count, frame_bytes[: sample_count * 4]))
    else:
        raise ValueError("Unsupported WAV sample width.")
    if not samples:
        return 0.0
    mono_samples = samples[:: max(channel_count, 1)]
    squared_sum = sum(sample * sample for sample in mono_samples)
    return (squared_sum / len(mono_samples)) ** 0.5


def infer_sfx_tags(label: str, asset_path: str | Path = "") -> list[str]:
    source_text = f"{label} {Path(asset_path).stem if asset_path else ''}"
    tags: list[str] = []
    for token in SFX_TAG_PATTERN.findall(source_text.lower()):
        for tag in SFX_TAG_KEYWORDS.get(token, (token,)):
            append_unique_tag(tags, tag)
    return tags[:12]


def normalize_sfx_tags(tags: list[str]) -> list[str]:
    normalized: list[str] = []
    for tag in tags:
        for token in SFX_TAG_PATTERN.findall(str(tag).lower()):
            append_unique_tag(normalized, token)
    return normalized


def build_sfx_asset_query(label: str, tags: list[str]) -> str:
    return " ".join(part for part in [label, *tags] if part).strip()


def suggest_sfx_asset_candidates(settings: AppSettings, query: str, limit: int = DEFAULT_SFX_ASSET_LIMIT) -> list[dict[str, Any]]:
    if limit <= 0 or not query.strip():
        return []
    return search_asset_library(settings=settings, query=query, kinds=SFX_ASSET_KINDS, limit=limit)


def append_unique_tag(tags: list[str], tag: str) -> None:
    normalized = tag.strip().lower().replace(" ", "_")
    if normalized and normalized not in tags:
        tags.append(normalized)


def build_placeholder_visemes(text: str, duration_seconds: float) -> list[dict[str, float | str]]:
    letters = [character for character in text if not character.isspace()]
    if not letters:
        return [{"time_seconds": 0.0, "mouth": "closed"}]
    step = duration_seconds / max(len(letters), 1)
    visemes = [{"time_seconds": round(index * step, 3), "mouth": estimate_mouth_shape(character)} for index, character in enumerate(letters)]
    visemes.append({"time_seconds": round(duration_seconds, 3), "mouth": "closed"})
    return visemes


def estimate_mouth_shape(character: str) -> str:
    lower = character.lower()
    if lower in {"a", "あ", "か", "さ", "た", "な", "は", "ま", "や", "ら", "わ"}:
        return "A"
    if lower in {"i", "い", "き", "し", "ち", "に", "ひ", "み", "り"}:
        return "I"
    if lower in {"u", "う", "く", "す", "つ", "ぬ", "ふ", "む", "ゆ", "る"}:
        return "U"
    if lower in {"e", "え", "け", "せ", "て", "ね", "へ", "め", "れ"}:
        return "E"
    if lower in {"o", "お", "こ", "そ", "と", "の", "ほ", "も", "よ", "ろ", "を"}:
        return "O"
    return "neutral"


def estimate_voice_duration(text: str, shot: Shot) -> float:
    estimated = max(1.0, len([character for character in text if not character.isspace()]) / DEFAULT_VOICE_CHARS_PER_SECOND)
    return round(min(max(estimated, 1.0), max(shot.duration_seconds, 1.0)), 2)


def upsert_cue(path: Path, manifest_type: str, story_id: str, cue: dict[str, Any]) -> CueWriteResult:
    existing = read_cue_items(path, manifest_type)
    merged = [item for item in existing if item.get("cue_id") != cue["cue_id"]]
    merged.append(cue)
    write_cue_manifest(path, manifest_type, story_id, sorted(merged, key=lambda item: (int(item.get("order", 0)), str(item.get("cue_id", "")))))
    return CueWriteResult(manifest_path=path, cue_id=str(cue["cue_id"]), cue_count=len(merged))


def read_cue_items(path: Path, manifest_type: str) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if data.get("manifest_type") != manifest_type:
        raise ValueError(f"Unexpected manifest type in {path}: {data.get('manifest_type')}")
    return [dict(item) for item in data.get("items", [])]


def write_cue_manifest(path: Path, manifest_type: str, story_id: str, items: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"schema_version": 1, "manifest_type": manifest_type, "story_id": story_id, "updated_at": utc_timestamp(), "items": items}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def read_selected_shot_map(settings: AppSettings, story_id: str) -> dict[str, dict[str, Any]]:
    path = normalize_editor_manifest_path(settings, story_id, None)
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    return {str(item.get("shot_id", "")): dict(item) for item in data.get("shots", [])}


def group_by_shot(items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        grouped.setdefault(str(item.get("shot_id", "")), []).append(item)
    return grouped


def find_shot(settings: AppSettings, story_id: str, shot_id: str) -> Shot:
    storyboard = load_storyboard(settings, story_id)
    for shot in storyboard.shots:
        if shot.shot_id == shot_id:
            return shot
    raise ValueError(f"Storyboard shot not found: {story_id}/{shot_id}")


def build_cue_id(prefix: str, shot_id: str, label: str) -> str:
    normalized = CUE_ID_PATTERN.sub("_", label.lower()).strip("_")[:40]
    return f"{prefix}_{shot_id}_{normalized or 'cue'}"


def normalize_optional_asset_path(settings: AppSettings, path: str | Path) -> str:
    if not path:
        return ""
    return project_relative_path(settings, path)


def normalize_project_path(settings: AppSettings, path: str | Path) -> Path:
    resolved = Path(path)
    if not resolved.is_absolute():
        resolved = settings.project_root / resolved
    return resolved


def validate_non_empty(value: str, name: str) -> None:
    if not value.strip():
        raise ValueError(f"{name} must not be empty.")


def validate_positive(value: float, name: str) -> None:
    if value <= 0:
        raise ValueError(f"{name} must be greater than 0.")


def validate_non_negative(value: float, name: str) -> None:
    if value < 0:
        raise ValueError(f"{name} must be 0 or greater.")


def validate_lip_sync_provider(provider: str) -> None:
    if provider not in SUPPORTED_LIP_SYNC_PROVIDERS:
        raise ValueError(f"Unsupported lip-sync provider: {provider}")


def get_voice_cues_path(settings: AppSettings, story_id: str) -> Path:
    return get_storyboard_path(settings, story_id).parent / "voice_cues.json"


def get_sfx_cues_path(settings: AppSettings, story_id: str) -> Path:
    return get_storyboard_path(settings, story_id).parent / "sfx_cues.json"


def get_motion_cues_path(settings: AppSettings, story_id: str) -> Path:
    return get_storyboard_path(settings, story_id).parent / "motion_cues.json"


def get_lip_sync_plan_path(settings: AppSettings, story_id: str) -> Path:
    return get_storyboard_path(settings, story_id).parent / "lip_sync_plan.json"


def normalize_lip_sync_plan_path(settings: AppSettings, story_id: str, output_path: str | Path | None) -> Path:
    if output_path is None:
        return get_lip_sync_plan_path(settings, story_id)
    path = Path(output_path)
    if not path.is_absolute():
        path = settings.project_root / path
    return path


def normalize_phase6_manifest_path(settings: AppSettings, story_id: str, output_path: str | Path | None) -> Path:
    if output_path is None:
        return settings.project_root / "manifests" / "storyboards" / story_id / "phase6_manifest.json"
    path = Path(output_path)
    if not path.is_absolute():
        path = settings.project_root / path
    return path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="anime-phase6", description="Lightweight Phase 6 voice, lip-sync, SFX, and motion cues.")
    parser.add_argument("--config", default="config/local_6gb.json", help="Path to the local runtime profile.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    voice = subparsers.add_parser("voice", help="Add or update a voice cue for a shot.")
    add_common_shot_args(voice)
    voice.add_argument("--text", required=True, help="Dialogue or narration text.")
    voice.add_argument("--speaker", default="", help="Speaker display name.")
    voice.add_argument("--character-id", default="", help="Optional character id override.")
    voice.add_argument("--voice-asset", default="", help="Optional generated/recorded voice asset path.")
    voice.add_argument("--emotion", default="", help="Emotion direction.")
    voice.add_argument("--language", default=DEFAULT_LANGUAGE, help="Language hint.")
    voice.add_argument("--start", type=float, default=0.0, help="Start time within the shot.")
    voice.add_argument("--duration", type=float, default=None, help="Optional cue duration.")
    voice.add_argument("--notes", default="", help="Production notes.")

    sfx = subparsers.add_parser("sfx", help="Add or update a sound effect cue for a shot.")
    add_common_shot_args(sfx)
    sfx.add_argument("--label", required=True, help="SFX label.")
    sfx.add_argument("--asset", default="", help="Optional SFX asset path.")
    sfx.add_argument("--start", type=float, default=0.0, help="Start time within the shot.")
    sfx.add_argument("--duration", type=float, default=DEFAULT_SFX_DURATION_SECONDS, help="Cue duration.")
    sfx.add_argument("--volume", type=float, default=1.0, help="Relative volume.")
    sfx.add_argument("--tags", default="", help="Comma-separated tags.")
    sfx.add_argument("--asset-query", default="", help="Optional Asset Library search query. Defaults to the label and SFX tags.")
    sfx.add_argument("--asset-limit", type=int, default=DEFAULT_SFX_ASSET_LIMIT, help="Maximum Asset Library candidates stored on the cue.")
    sfx.add_argument("--notes", default="", help="Production notes.")

    motion = subparsers.add_parser("motion", help="Add or update a motion cue for a shot.")
    add_common_shot_args(motion)
    motion.add_argument("--target", required=True, help="Motion target, such as character or camera.")
    motion.add_argument("--motion", required=True, help="Motion label.")
    motion.add_argument("--source", default="manual", help="Motion source.")
    motion.add_argument("--start", type=float, default=0.0, help="Start time within the shot.")
    motion.add_argument("--duration", type=float, default=DEFAULT_MOTION_DURATION_SECONDS, help="Cue duration.")
    motion.add_argument("--intensity", type=float, default=1.0, help="Relative intensity.")
    motion.add_argument("--notes", default="", help="Production notes.")

    lip_sync = subparsers.add_parser("lip-sync", help="Build a lip-sync timing plan from voice cues.")
    lip_sync.add_argument("--story-id", required=True, help="Storyboard id.")
    lip_sync.add_argument("--output", default=None, help="Lip-sync plan output path.")
    lip_sync.add_argument("--provider", choices=sorted(SUPPORTED_LIP_SYNC_PROVIDERS), default="text", help="Lip-sync provider. Use wav-rms for lightweight WAV amplitude analysis.")

    export = subparsers.add_parser("export", help="Export a combined Phase 6 manifest for Unity/editing tools.")
    export.add_argument("--story-id", required=True, help="Storyboard id.")
    export.add_argument("--output", default=None, help="Phase 6 manifest output path.")
    return parser


def add_common_shot_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--story-id", required=True, help="Storyboard id.")
    parser.add_argument("--shot-id", required=True, help="Shot id.")


def main(argv: list[str] | None = None) -> int:
    from .settings import load_settings

    parser = build_parser()
    args = parser.parse_args(argv)
    settings = load_settings(args.config)
    if args.command == "voice":
        result = add_voice_cue(settings, args.story_id, args.shot_id, args.text, args.speaker, args.character_id, args.voice_asset, args.emotion, args.language, args.start, args.duration, args.notes)
        print_cue_result("voice cue", result)
        return 0
    if args.command == "sfx":
        result = add_sfx_cue(
            settings=settings,
            story_id=args.story_id,
            shot_id=args.shot_id,
            label=args.label,
            asset_path=args.asset,
            start_seconds=args.start,
            duration_seconds=args.duration,
            volume=args.volume,
            tags=[tag.strip() for tag in args.tags.split(",") if tag.strip()],
            asset_query=args.asset_query,
            asset_limit=args.asset_limit,
            notes=args.notes,
        )
        print_cue_result("SFX cue", result)
        return 0
    if args.command == "motion":
        result = add_motion_cue(settings, args.story_id, args.shot_id, args.target, args.motion, args.source, args.start, args.duration, args.intensity, args.notes)
        print_cue_result("motion cue", result)
        return 0
    if args.command == "lip-sync":
        result = build_lip_sync_plan(settings=settings, story_id=args.story_id, output_path=args.output, provider=args.provider)
        print(f"Wrote lip-sync plan: {result.manifest_path}")
        print(f"Cues: {result.cue_count}")
        print(f"Provider: {args.provider}")
        return 0
    if args.command == "export":
        result = export_phase6_manifest(settings=settings, story_id=args.story_id, output_path=args.output)
        print(f"Wrote Phase 6 manifest: {result.manifest_path}")
        print(f"Shots: {result.shot_count}")
        print(f"Voice cues: {result.voice_count}")
        print(f"Lip-sync cues: {result.lip_sync_count}")
        print(f"SFX cues: {result.sfx_count}")
        print(f"Motion cues: {result.motion_count}")
        return 0
    parser.error(f"Unknown command: {args.command}")
    return 2


def print_cue_result(label: str, result: CueWriteResult) -> None:
    print(f"Wrote {label}: {result.cue_id}")
    print(f"Manifest: {result.manifest_path}")
    print(f"Cues: {result.cue_count}")


if __name__ == "__main__":
    raise SystemExit(main())
