from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from typing import Any

from .comfyui_queue import find_job, normalize_queue_path, read_queue, read_workflow
from .lora_registry import project_relative_path, utc_timestamp
from .settings import AppSettings
from .storyboard import Shot, get_storyboard_path, load_storyboard


@dataclass(frozen=True)
class ShotResult:
    result_id: str
    shot_id: str
    order: int
    kind: str
    source: str
    stored_path: str
    source_reference: str = ""
    job_id: str = ""
    prompt_id: str = ""
    node_id: str = ""
    linked_at: str = ""
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class ShotResultLinkResult:
    manifest_path: Path
    linked: list[ShotResult]
    skipped_count: int = 0


def link_shot_result(
    settings: AppSettings,
    story_id: str,
    shot_id: str,
    result_path: str | Path,
    kind: str = "image",
    source: str = "manual",
    source_reference: str = "",
    job_id: str = "",
    prompt_id: str = "",
    node_id: str = "",
    metadata: dict[str, Any] | None = None,
) -> ShotResultLinkResult:
    shot = find_storyboard_shot(settings, story_id, shot_id)
    stored_path = normalize_result_reference(settings, result_path)
    result = build_shot_result(
        shot=shot,
        kind=kind,
        source=source,
        stored_path=stored_path,
        source_reference=source_reference,
        job_id=job_id,
        prompt_id=prompt_id,
        node_id=node_id,
        metadata=metadata,
    )
    manifest_path, _ = append_shot_results(settings, story_id, [result])
    return ShotResultLinkResult(manifest_path=manifest_path, linked=[result])


def link_comfyui_results_to_storyboard(
    settings: AppSettings,
    job_id: str,
    queue_path: str | Path | None = None,
    results_manifest_path: str | Path | None = None,
) -> ShotResultLinkResult:
    queue = read_queue(normalize_queue_path(settings, queue_path))
    job = find_job(queue, job_id, include_non_pending=True)
    if job is None:
        raise ValueError(f"ComfyUI queue job not found: {job_id}")

    workflow = read_workflow(settings, job["workflow_path"])
    meta = dict(workflow.get("meta", {}))
    story_id = str(meta.get("story_id", ""))
    shot_id = str(meta.get("shot_id", ""))
    character_id = str(meta.get("shot_character_id", meta.get("character_id", "")))
    if not story_id or not shot_id:
        raise ValueError(f"ComfyUI workflow is not linked to a storyboard shot: {job['workflow_path']}")
    if not character_id:
        raise ValueError(f"ComfyUI workflow is missing a character id: {job['workflow_path']}")

    shot = find_storyboard_shot(settings, story_id, shot_id)
    resolved_manifest = normalize_results_manifest_path(
        settings=settings,
        character_id=character_id,
        job_id=job_id,
        results_manifest_path=results_manifest_path,
    )
    data = json.loads(resolved_manifest.read_text(encoding="utf-8-sig"))

    linked: list[ShotResult] = []
    for item in data.get("results", []):
        result_data = dict(item)
        stored_path = str(result_data.get("stored_path", ""))
        if not stored_path:
            stored_path = str(result_data.get("source_reference", ""))
        result = build_shot_result(
            shot=shot,
            kind=str(result_data.get("kind", "image")),
            source="comfyui_result",
            stored_path=stored_path,
            source_reference=str(result_data.get("source_reference", "")),
            job_id=str(result_data.get("job_id", job_id)),
            prompt_id=str(result_data.get("prompt_id", job.get("prompt_id", ""))),
            node_id=str(result_data.get("node_id", "")),
            metadata={
                "character_id": character_id,
                "results_manifest_path": project_relative_path(settings, resolved_manifest),
                "workflow_path": str(job.get("workflow_path", "")),
            },
        )
        linked.append(result)

    manifest_path, skipped_count = append_shot_results(settings, story_id, linked)
    return ShotResultLinkResult(
        manifest_path=manifest_path,
        linked=linked,
        skipped_count=skipped_count,
    )


def list_shot_results(
    settings: AppSettings,
    story_id: str,
    shot_id: str | None = None,
) -> list[ShotResult]:
    if shot_id is not None:
        find_storyboard_shot(settings, story_id, shot_id)
    manifest = read_shot_results_manifest(get_shot_results_path(settings, story_id))
    results = [shot_result_from_dict(item) for item in manifest.get("results", [])]
    if shot_id is not None:
        results = [result for result in results if result.shot_id == shot_id]
    return sorted(results, key=lambda result: (result.order, result.linked_at, result.result_id))


def append_shot_results(
    settings: AppSettings,
    story_id: str,
    results: list[ShotResult],
) -> tuple[Path, int]:
    load_storyboard(settings, story_id)
    manifest_path = get_shot_results_path(settings, story_id)
    manifest = read_shot_results_manifest(manifest_path)
    existing = [shot_result_from_dict(item) for item in manifest.get("results", [])]
    existing_ids = {item.result_id for item in existing}
    merged = list(existing)
    skipped_count = 0
    for result in results:
        if result.result_id in existing_ids:
            skipped_count += 1
            continue
        merged.append(result)
        existing_ids.add(result.result_id)

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "manifest_type": "storyboard_shot_results",
                "story_id": story_id,
                "updated_at": utc_timestamp(),
                "results": [asdict(result) for result in merged],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return manifest_path, skipped_count


def build_shot_result(
    shot: Shot,
    kind: str,
    source: str,
    stored_path: str,
    source_reference: str = "",
    job_id: str = "",
    prompt_id: str = "",
    node_id: str = "",
    metadata: dict[str, Any] | None = None,
) -> ShotResult:
    return ShotResult(
        result_id=build_result_id(
            shot_id=shot.shot_id,
            stored_path=stored_path,
            source_reference=source_reference,
            job_id=job_id,
            node_id=node_id,
        ),
        shot_id=shot.shot_id,
        order=shot.order,
        kind=kind,
        source=source,
        stored_path=stored_path,
        source_reference=source_reference,
        job_id=job_id,
        prompt_id=prompt_id,
        node_id=node_id,
        linked_at=utc_timestamp(),
        metadata=metadata or {},
    )


def find_storyboard_shot(settings: AppSettings, story_id: str, shot_id: str) -> Shot:
    storyboard = load_storyboard(settings, story_id)
    for shot in storyboard.shots:
        if shot.shot_id == shot_id:
            return shot
    raise ValueError(f"Storyboard shot not found: {story_id}/{shot_id}")


def get_shot_results_path(settings: AppSettings, story_id: str) -> Path:
    storyboard_path = get_storyboard_path(settings, story_id)
    return storyboard_path.parent / "shot_results.json"


def read_shot_results_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "schema_version": 1,
            "manifest_type": "storyboard_shot_results",
            "story_id": path.parent.name,
            "updated_at": "",
            "results": [],
        }
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    data.setdefault("schema_version", 1)
    data.setdefault("manifest_type", "storyboard_shot_results")
    data.setdefault("results", [])
    return data


def shot_result_from_dict(data: dict[str, Any]) -> ShotResult:
    return ShotResult(
        result_id=str(data["result_id"]),
        shot_id=str(data["shot_id"]),
        order=int(data["order"]),
        kind=str(data.get("kind", "image")),
        source=str(data.get("source", "manual")),
        stored_path=str(data.get("stored_path", "")),
        source_reference=str(data.get("source_reference", "")),
        job_id=str(data.get("job_id", "")),
        prompt_id=str(data.get("prompt_id", "")),
        node_id=str(data.get("node_id", "")),
        linked_at=str(data.get("linked_at", "")),
        metadata=dict(data.get("metadata") or {}),
    )


def normalize_results_manifest_path(
    settings: AppSettings,
    character_id: str,
    job_id: str,
    results_manifest_path: str | Path | None,
) -> Path:
    if results_manifest_path is None:
        return (
            settings.assets.processed
            / "characters"
            / character_id
            / "generated"
            / "comfyui"
            / job_id
            / "results.json"
        )
    path = Path(results_manifest_path)
    if not path.is_absolute():
        path = settings.project_root / path
    return path


def normalize_result_reference(settings: AppSettings, result_path: str | Path) -> str:
    path = Path(result_path)
    if path.is_absolute():
        try:
            return project_relative_path(settings, path)
        except ValueError:
            return str(path)
    return str(path).replace("\\", "/")


def build_result_id(
    shot_id: str,
    stored_path: str,
    source_reference: str,
    job_id: str,
    node_id: str,
) -> str:
    digest = hashlib.sha1(
        f"{shot_id}|{stored_path}|{source_reference}|{job_id}|{node_id}".encode("utf-8")
    ).hexdigest()[:10]
    return f"{shot_id}-{digest}"


def set_shot_result_decision(
    settings: AppSettings,
    story_id: str,
    result_id: str,
    decision: str,
    notes: str = "",
):
    from .storyboard_review import set_shot_result_decision as implementation

    return implementation(
        settings=settings,
        story_id=story_id,
        result_id=result_id,
        decision=decision,
        notes=notes,
    )
