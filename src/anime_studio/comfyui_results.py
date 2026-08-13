from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import shutil
from typing import Any

from .character_manager import RegisteredAsset, append_asset_manifest
from .character_profile import character_profile_path, validate_character_id
from .comfyui_queue import find_job, normalize_queue_path, read_queue
from .lora_registry import project_relative_path, utc_timestamp
from .settings import AppSettings


@dataclass(frozen=True)
class ComfyUIImportedResult:
    job_id: str
    prompt_id: str
    source_reference: str
    stored_path: str
    node_id: str
    kind: str
    size_bytes: int


@dataclass(frozen=True)
class ComfyUIImportResult:
    results_manifest_path: Path
    assets_manifest_path: Path
    imported: list[ComfyUIImportedResult]


def import_comfyui_results(
    settings: AppSettings,
    character_id: str,
    job_id: str,
    comfyui_output_dir: str | Path,
    queue_path: str | Path | None = None,
    metadata_only: bool = False,
) -> ComfyUIImportResult:
    validate_character_id(character_id)
    profile_path = character_profile_path(settings, character_id)
    if not profile_path.exists():
        raise FileNotFoundError(f"Character profile does not exist: {profile_path}")

    queue = read_queue(normalize_queue_path(settings, queue_path))
    job = find_job(queue, job_id, include_non_pending=True)
    if job is None:
        raise ValueError(f"ComfyUI queue job not found: {job_id}")

    prompt_id = str(job.get("prompt_id", ""))
    output_items = extract_history_images(job)
    if not output_items:
        raise ValueError(f"No ComfyUI image outputs found for job: {job_id}")

    source_root = normalize_project_path(settings, comfyui_output_dir)
    destination_dir = (
        settings.assets.processed
        / "characters"
        / character_id
        / "generated"
        / "comfyui"
        / job_id
    )
    destination_dir.mkdir(parents=True, exist_ok=True)

    imported: list[ComfyUIImportedResult] = []
    for item in output_items:
        source = resolve_comfyui_output_path(source_root, item)
        destination = destination_dir / source.name
        if source.exists() and not metadata_only:
            destination = unique_destination(destination)
            shutil.copy2(source, destination)
            stored_path = project_relative_path(settings, destination)
            size_bytes = destination.stat().st_size
        elif metadata_only:
            stored_path = ""
            size_bytes = 0
        else:
            raise FileNotFoundError(f"ComfyUI output image not found: {source}")

        imported_item = ComfyUIImportedResult(
            job_id=job_id,
            prompt_id=prompt_id,
            source_reference=render_source_reference(item),
            stored_path=stored_path,
            node_id=str(item["node_id"]),
            kind="image",
            size_bytes=size_bytes,
        )
        imported.append(imported_item)

        asset = RegisteredAsset(
            original_path=str(source),
            stored_path=stored_path,
            kind="image",
            size_bytes=size_bytes,
            source="comfyui_result",
            metadata={
                "job_id": job_id,
                "prompt_id": prompt_id,
                "node_id": str(item["node_id"]),
                "filename": str(item["filename"]),
                "subfolder": str(item.get("subfolder", "")),
                "type": str(item.get("type", "output")),
                "metadata_only": metadata_only,
            },
        )
        assets_manifest_path = append_asset_manifest(settings, character_id, asset)

    results_manifest_path = destination_dir / "results.json"
    results_manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "manifest_type": "comfyui_imported_results",
                "character_id": character_id,
                "job_id": job_id,
                "prompt_id": prompt_id,
                "imported_at": utc_timestamp(),
                "metadata_only": metadata_only,
                "results": [asdict(item) for item in imported],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return ComfyUIImportResult(
        results_manifest_path=results_manifest_path,
        assets_manifest_path=assets_manifest_path,
        imported=imported,
    )


def extract_history_images(job: dict[str, Any]) -> list[dict[str, object]]:
    prompt_id = str(job.get("prompt_id", ""))
    response = dict(job.get("response", {}))
    prompt_history = dict(response.get(prompt_id, {}))
    outputs = dict(prompt_history.get("outputs", {}))
    images: list[dict[str, object]] = []
    for node_id, node_output in outputs.items():
        for image in dict(node_output).get("images", []):
            item = dict(image)
            item["node_id"] = str(node_id)
            images.append(item)
    return images


def resolve_comfyui_output_path(source_root: Path, item: dict[str, object]) -> Path:
    subfolder = str(item.get("subfolder", "")).strip("/\\")
    filename = str(item["filename"])
    if subfolder:
        return source_root / subfolder / filename
    return source_root / filename


def render_source_reference(item: dict[str, object]) -> str:
    output_type = str(item.get("type", "output"))
    subfolder = str(item.get("subfolder", "")).strip("/\\")
    filename = str(item["filename"])
    if subfolder:
        return f"{output_type}:{subfolder}/{filename}"
    return f"{output_type}:{filename}"


def unique_destination(destination: Path) -> Path:
    if not destination.exists():
        return destination
    stem = destination.stem
    suffix = destination.suffix
    for index in range(1, 1000):
        candidate = destination.with_name(f"{stem}_{index}{suffix}")
        if not candidate.exists():
            return candidate
    raise FileExistsError(f"Could not create unique destination for: {destination}")


def normalize_project_path(settings: AppSettings, path: str | Path) -> Path:
    resolved = Path(path)
    if not resolved.is_absolute():
        resolved = settings.project_root / resolved
    return resolved
