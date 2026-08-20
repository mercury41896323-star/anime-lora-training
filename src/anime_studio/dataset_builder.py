from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import shutil
from typing import Any

from .character_profile import load_character_profile, validate_character_id
from .lora_registry import project_relative_path, utc_timestamp
from .phase6_pipeline import get_motion_cues_path, normalize_phase6_manifest_path, read_cue_items
from .tagger import collect_character_images, finalize_tag_sidecars
from .settings import AppSettings
from .storyboard import load_storyboard
from .storyboard_editor_manifest import normalize_editor_manifest_path


MOTION_DATASET_MANIFEST_TYPE = "storyboard_motion_dataset"


@dataclass(frozen=True)
class DatasetBuildResult:
    character_id: str
    dataset_dir: Path
    image_count: int
    caption_count: int


@dataclass(frozen=True)
class MotionDatasetBuildResult:
    story_id: str
    dataset_dir: Path
    manifest_path: Path
    entry_count: int
    transition_count: int
    asset_count: int


def build_lora_dataset(settings: AppSettings, character_id: str) -> DatasetBuildResult:
    validate_character_id(character_id)
    profile = load_character_profile(settings, character_id)
    finalize_tag_sidecars(settings, character_id, overwrite=True)
    image_paths = collect_character_images(settings, character_id)

    dataset_dir = settings.datasets.lora / character_id
    images_dir = dataset_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    image_count = 0
    caption_count = 0
    for image_path in image_paths:
        destination_image = unique_destination(images_dir, image_path.name)
        shutil.copy2(image_path, destination_image)
        image_count += 1

        source_caption = image_path.with_suffix(".txt")
        destination_caption = destination_image.with_suffix(".txt")
        if source_caption.exists():
            shutil.copy2(source_caption, destination_caption)
        else:
            destination_caption.write_text(
                ", ".join(profile.trigger_tags) + "\n",
                encoding="utf-8",
            )
        caption_count += 1

    metadata_path = dataset_dir / "metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "character_id": character_id,
                "display_name": profile.display_name,
                "trigger_tags": profile.trigger_tags,
                "image_count": image_count,
                "caption_count": caption_count,
                "profile_path": str(
                    settings.assets.processed / "characters" / character_id / "profile.json"
                ),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    return DatasetBuildResult(
        character_id=character_id,
        dataset_dir=dataset_dir,
        image_count=image_count,
        caption_count=caption_count,
    )


def build_motion_dataset(
    settings: AppSettings,
    story_id: str,
    output_dir: str | Path | None = None,
    manifest_path: str | Path | None = None,
) -> MotionDatasetBuildResult:
    storyboard = load_storyboard(settings, story_id)
    selected_manifest = read_optional_manifest(normalize_editor_manifest_path(settings, story_id, None))
    phase6_manifest = read_optional_manifest(normalize_phase6_manifest_path(settings, story_id, None))
    b_control_manifest = read_optional_manifest(
        settings.project_root / "manifests" / "storyboards" / story_id / "b_control_manifest.json"
    )

    selected_by_shot = {
        str(item.get("shot_id", "")): dict(item)
        for item in selected_manifest.get("shots", [])
    }
    phase6_by_shot = {
        str(item.get("shot_id", "")): dict(item)
        for item in phase6_manifest.get("shots", [])
    }
    if not phase6_by_shot:
        phase6_by_shot = build_phase6_motion_fallback(settings, story_id)
    b_control_by_shot = {
        str(item.get("shot_id", "")): dict(item)
        for item in b_control_manifest.get("shots", [])
    }

    dataset_dir = normalize_motion_dataset_dir(settings, story_id, output_dir)
    assets_dir = dataset_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    copied_assets: dict[str, str] = {}
    entries: list[dict[str, Any]] = []

    for shot in sorted(storyboard.shots, key=lambda item: item.order):
        selected = selected_by_shot.get(shot.shot_id, {})
        phase6 = phase6_by_shot.get(shot.shot_id, {})
        b_control = b_control_by_shot.get(shot.shot_id, {})
        selected_result = dict(selected.get("selected_result") or {})
        selected_asset_path = copy_motion_asset(
            settings=settings,
            assets_dir=assets_dir,
            source_path=str(selected_result.get("stored_path", "")),
            copied_assets=copied_assets,
        )
        for cue in phase6.get("motion_cues", []):
            tags = dedupe_tokens(
                [
                    shot.character_id,
                    str(cue.get("target", "")),
                    str(cue.get("motion", "")),
                    str(cue.get("source", "")),
                    str((b_control.get("controls") or {}).get("face_direction", "")),
                    str((b_control.get("controls") or {}).get("camera_distance", "")),
                    str((b_control.get("controls") or {}).get("camera_angle", "")),
                    str((b_control.get("controls") or {}).get("lighting_direction", "")),
                ]
            )
            entry = {
                "entry_id": str(cue.get("cue_id", "")),
                "story_id": story_id,
                "shot_id": shot.shot_id,
                "order": shot.order,
                "character_id": shot.character_id,
                "target": str(cue.get("target", "")),
                "motion": str(cue.get("motion", "")),
                "source": str(cue.get("source", "")),
                "start_seconds": float(cue.get("start_seconds", 0.0) or 0.0),
                "duration_seconds": float(cue.get("duration_seconds", 0.0) or 0.0),
                "intensity": float(cue.get("intensity", 1.0) or 1.0),
                "asset_path": selected_asset_path,
                "source_asset_path": str(selected_result.get("stored_path", "")),
                "prompt": shot.prompt,
                "camera": shot.camera,
                "lighting": shot.lighting,
                "camera_work": dict(selected.get("camera_work") or {}),
                "lighting_setup": dict(selected.get("lighting_setup") or {}),
                "b_control": dict(b_control.get("controls") or {}),
                "tags": tags,
            }
            entries.append(entry)
            write_motion_caption(dataset_dir, entry, tags)

    transitions = build_motion_transitions(
        storyboard=storyboard,
        selected_by_shot=selected_by_shot,
        b_control_by_shot=b_control_by_shot,
        copied_assets=copied_assets,
        settings=settings,
        assets_dir=assets_dir,
    )

    manifest_path = normalize_motion_manifest_path(settings, story_id, manifest_path)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "manifest_type": MOTION_DATASET_MANIFEST_TYPE,
                "generated_at": utc_timestamp(),
                "story": {
                    "story_id": storyboard.story_id,
                    "title": storyboard.title,
                },
                "dataset_dir": project_relative_path(settings, dataset_dir),
                "counts": {
                    "entry_count": len(entries),
                    "transition_count": len(transitions),
                    "asset_count": len(copied_assets),
                },
                "entries": entries,
                "transitions": transitions,
                "notes": [
                    "Motion dataset entries are built from selected storyboard results plus Phase 6 motion cues.",
                    "Transitions capture adjacent shot consistency targets for B-control style in-between generation.",
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    write_motion_jsonl(dataset_dir / "entries.jsonl", entries)
    write_motion_jsonl(dataset_dir / "transitions.jsonl", transitions)
    return MotionDatasetBuildResult(
        story_id=story_id,
        dataset_dir=dataset_dir,
        manifest_path=manifest_path,
        entry_count=len(entries),
        transition_count=len(transitions),
        asset_count=len(copied_assets),
    )


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


def normalize_motion_dataset_dir(
    settings: AppSettings,
    story_id: str,
    output_dir: str | Path | None,
) -> Path:
    if output_dir is None:
        return settings.project_root / "datasets" / "motion" / story_id
    path = Path(output_dir)
    if not path.is_absolute():
        path = settings.project_root / path
    return path


def normalize_motion_manifest_path(
    settings: AppSettings,
    story_id: str,
    manifest_path: str | Path | None,
) -> Path:
    if manifest_path is None:
        return settings.project_root / "manifests" / "storyboards" / story_id / "motion_dataset_manifest.json"
    path = Path(manifest_path)
    if not path.is_absolute():
        path = settings.project_root / path
    return path


def read_optional_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def copy_motion_asset(
    settings: AppSettings,
    assets_dir: Path,
    source_path: str,
    copied_assets: dict[str, str],
) -> str:
    if not source_path:
        return ""
    if source_path in copied_assets:
        return copied_assets[source_path]
    resolved = Path(source_path)
    if not resolved.is_absolute():
        resolved = settings.project_root / resolved
    if not resolved.exists() or not resolved.is_file():
        return ""
    destination = unique_destination(assets_dir, resolved.name)
    if destination.resolve() != resolved.resolve():
        shutil.copy2(resolved, destination)
    relative_destination = project_relative_path(settings, destination)
    copied_assets[source_path] = relative_destination
    return relative_destination


def write_motion_caption(dataset_dir: Path, entry: dict[str, Any], tags: list[str]) -> None:
    captions_dir = dataset_dir / "captions"
    captions_dir.mkdir(parents=True, exist_ok=True)
    cue_id = str(entry.get("entry_id", "motion_entry"))
    (captions_dir / f"{cue_id}.txt").write_text(", ".join(tags) + "\n", encoding="utf-8")


def write_motion_jsonl(path: Path, items: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(item, ensure_ascii=False) for item in items]
    path.write_text(("\n".join(lines) + "\n") if lines else "", encoding="utf-8")


def build_motion_transitions(
    storyboard: Any,
    selected_by_shot: dict[str, dict[str, Any]],
    b_control_by_shot: dict[str, dict[str, Any]],
    copied_assets: dict[str, str],
    settings: AppSettings,
    assets_dir: Path,
) -> list[dict[str, Any]]:
    transitions: list[dict[str, Any]] = []
    ordered_shots = sorted(storyboard.shots, key=lambda item: item.order)
    for previous, current in zip(ordered_shots, ordered_shots[1:]):
        previous_selected = dict(selected_by_shot.get(previous.shot_id, {}).get("selected_result") or {})
        current_selected = dict(selected_by_shot.get(current.shot_id, {}).get("selected_result") or {})
        if not previous_selected or not current_selected:
            continue
        if previous.character_id and current.character_id and previous.character_id != current.character_id:
            continue
        previous_control = dict((b_control_by_shot.get(previous.shot_id, {}) or {}).get("controls") or {})
        current_control = dict((b_control_by_shot.get(current.shot_id, {}) or {}).get("controls") or {})
        from_asset = copy_motion_asset(
            settings=settings,
            assets_dir=assets_dir,
            source_path=str(previous_selected.get("stored_path", "")),
            copied_assets=copied_assets,
        )
        to_asset = copy_motion_asset(
            settings=settings,
            assets_dir=assets_dir,
            source_path=str(current_selected.get("stored_path", "")),
            copied_assets=copied_assets,
        )
        transition = {
            "transition_id": f"{previous.shot_id}_to_{current.shot_id}",
            "story_id": storyboard.story_id,
            "from_shot_id": previous.shot_id,
            "to_shot_id": current.shot_id,
            "character_id": current.character_id or previous.character_id,
            "from_asset_path": from_asset,
            "to_asset_path": to_asset,
            "from_face_direction": str(previous_control.get("face_direction", "")),
            "to_face_direction": str(current_control.get("face_direction", "")),
            "from_camera_angle": str(previous_control.get("camera_angle", "")),
            "to_camera_angle": str(current_control.get("camera_angle", "")),
            "from_lighting_direction": str(previous_control.get("lighting_direction", "")),
            "to_lighting_direction": str(current_control.get("lighting_direction", "")),
            "requires_b_control": bool(
                previous_control.get("face_direction") != current_control.get("face_direction")
                or previous_control.get("camera_angle") != current_control.get("camera_angle")
            ),
            "tags": dedupe_tokens(
                [
                    current.character_id or previous.character_id,
                    "transition",
                    str(previous_control.get("face_direction", "")),
                    str(current_control.get("face_direction", "")),
                    str(previous_control.get("camera_angle", "")),
                    str(current_control.get("camera_angle", "")),
                ]
            ),
        }
        transitions.append(transition)
    return transitions


def dedupe_tokens(values: list[str]) -> list[str]:
    tokens: list[str] = []
    for value in values:
        for token in tokenize(value):
            if token not in tokens:
                tokens.append(token)
    return tokens


def tokenize(value: str) -> list[str]:
    normalized = (
        str(value)
        .strip()
        .lower()
        .replace("\\", " ")
        .replace("/", " ")
        .replace(",", " ")
        .replace("-", "_")
    )
    return [token for token in normalized.split() if token]


def build_phase6_motion_fallback(settings: AppSettings, story_id: str) -> dict[str, dict[str, Any]]:
    motion_cues = read_cue_items(get_motion_cues_path(settings, story_id), "storyboard_motion_cues")
    grouped: dict[str, dict[str, Any]] = {}
    for cue in motion_cues:
        shot_id = str(cue.get("shot_id", ""))
        if not shot_id:
            continue
        grouped.setdefault(shot_id, {"shot_id": shot_id, "motion_cues": []})
        grouped[shot_id]["motion_cues"].append(dict(cue))
    return grouped
