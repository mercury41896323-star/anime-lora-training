from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from .lora_registry import utc_timestamp
from .settings import AppSettings
from .storyboard import Shot, get_storyboard_path, load_storyboard
from .storyboard_review import read_raw_shot_results, result_decision


@dataclass(frozen=True)
class StoryboardEditorManifestResult:
    manifest_path: Path
    selected_shot_count: int
    missing_shot_count: int


def export_selected_shot_manifest(
    settings: AppSettings,
    story_id: str,
    output_path: str | Path | None = None,
) -> StoryboardEditorManifestResult:
    storyboard = load_storyboard(settings, story_id)
    results = read_raw_shot_results(settings, story_id)
    selected_by_shot = select_results_by_shot(results)
    ordered_shots = sorted(storyboard.shots, key=lambda item: item.order)
    selected_shots = [
        render_selected_shot(story_id, shot, selected_by_shot[shot.shot_id])
        for shot in ordered_shots
        if shot.shot_id in selected_by_shot
    ]
    missing_shots = [
        render_missing_shot(shot)
        for shot in ordered_shots
        if shot.shot_id not in selected_by_shot
    ]

    manifest_path = normalize_editor_manifest_path(settings, story_id, output_path)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "manifest_type": "storyboard_selected_shots_manifest",
                "generated_at": utc_timestamp(),
                "story": {
                    "story_id": storyboard.story_id,
                    "title": storyboard.title,
                },
                "counts": {
                    "shot_count": len(ordered_shots),
                    "selected_shot_count": len(selected_shots),
                    "missing_shot_count": len(missing_shots),
                },
                "shots": selected_shots,
                "missing_shots": missing_shots,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return StoryboardEditorManifestResult(
        manifest_path=manifest_path,
        selected_shot_count=len(selected_shots),
        missing_shot_count=len(missing_shots),
    )


def select_results_by_shot(results: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    selected: dict[str, dict[str, Any]] = {}
    for result in sorted(results, key=lambda item: str(item.get("decided_at", ""))):
        if result_decision(result) == "selected":
            selected[str(result.get("shot_id", ""))] = result
    return selected


def render_selected_shot(story_id: str, shot: Shot, result: dict[str, Any]) -> dict[str, Any]:
    result_id = str(result.get("result_id", ""))
    stored_path = str(result.get("stored_path", ""))
    return {
        "shot_id": shot.shot_id,
        "order": shot.order,
        "title": shot.title,
        "character_id": shot.character_id,
        "duration_seconds": shot.duration_seconds,
        "prompt": shot.prompt,
        "camera": shot.camera,
        "lighting": shot.lighting,
        "notes": shot.notes,
        "selected_result": {
            "result_id": result_id,
            "kind": str(result.get("kind", "")),
            "source": str(result.get("source", "")),
            "stored_path": stored_path,
            "source_reference": str(result.get("source_reference", "")),
            "job_id": str(result.get("job_id", "")),
            "prompt_id": str(result.get("prompt_id", "")),
            "node_id": str(result.get("node_id", "")),
            "decision_notes": str(result.get("decision_notes", "")),
            "decided_at": str(result.get("decided_at", "")),
            "metadata": result.get("metadata") or {},
        },
        "unity": {
            "timeline_clip_name": f"{shot.order:03d}_{shot.shot_id}",
            "asset_reference": stored_path,
            "addressable_key": f"storyboards/{story_id}/{shot.shot_id}/{result_id}",
            "duration_seconds": shot.duration_seconds,
        },
        "editor": {
            "label": f"{shot.order:03d} {shot.title}",
            "status": "selected",
        },
    }


def render_missing_shot(shot: Shot) -> dict[str, Any]:
    return {
        "shot_id": shot.shot_id,
        "order": shot.order,
        "title": shot.title,
        "character_id": shot.character_id,
        "reason": "No selected shot result.",
    }


def normalize_editor_manifest_path(
    settings: AppSettings,
    story_id: str,
    output_path: str | Path | None,
) -> Path:
    if output_path is None:
        return settings.project_root / "manifests" / "storyboards" / story_id / "selected_shots.json"
    path = Path(output_path)
    if not path.is_absolute():
        path = settings.project_root / path
    return path
