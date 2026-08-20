from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any
import zlib

from .b_control import (
    apply_b_control_to_workflow,
    build_b_control_prompt_fragment,
    export_b_control_manifest,
    load_b_control_map,
)
from .comfyui_queue import DEFAULT_COMFYUI_BASE_URL, enqueue_comfyui_workflow
from .comfyui_workflow_export import export_comfyui_workflow
from .lora_registry import project_relative_path, utc_timestamp
from .settings import AppSettings
from .storyboard import Shot, Storyboard, load_storyboard
from .storyboard_production import (
    CameraWork,
    LightingSetup,
    build_production_prompt,
    load_camera_work_map,
    load_lighting_setup_map,
)


@dataclass(frozen=True)
class StoryboardWorkflowItem:
    shot_id: str
    order: int
    character_id: str
    workflow_path: str
    lora_name: str
    queued_job_id: str = ""


@dataclass(frozen=True)
class StoryboardWorkflowSkip:
    shot_id: str
    order: int
    reason: str


@dataclass(frozen=True)
class StoryboardWorkflowExportResult:
    story_id: str
    export_dir: Path
    manifest_path: Path
    workflows: list[StoryboardWorkflowItem]
    skipped_shots: list[StoryboardWorkflowSkip]
    b_control_manifest_path: Path | None = None


def export_storyboard_comfyui_workflows(
    settings: AppSettings,
    story_id: str,
    template_path: str | Path | None = None,
    output_dir: str | Path | None = None,
    lora_index: int = 0,
    enqueue: bool = False,
    base_url: str = DEFAULT_COMFYUI_BASE_URL,
    queue_path: str | Path | None = None,
    b_control: bool = False,
) -> StoryboardWorkflowExportResult:
    storyboard = load_storyboard(settings, story_id)
    camera_by_shot = load_camera_work_map(settings, story_id)
    lighting_by_shot = load_lighting_setup_map(settings, story_id)
    resolved_output_dir = normalize_output_dir(settings, story_id, output_dir)
    resolved_output_dir.mkdir(parents=True, exist_ok=True)
    b_control_manifest_path: Path | None = None
    b_control_by_shot: dict[str, dict[str, Any]] = {}
    if b_control:
        b_control_manifest_path = export_b_control_manifest(settings, story_id).manifest_path
        b_control_by_shot = load_b_control_map(settings, story_id)

    workflows: list[StoryboardWorkflowItem] = []
    skipped: list[StoryboardWorkflowSkip] = []
    for shot in sorted(storyboard.shots, key=lambda item: item.order):
        if not shot.character_id:
            skipped.append(
                StoryboardWorkflowSkip(
                    shot_id=shot.shot_id,
                    order=shot.order,
                    reason="character_id is required for ComfyUI LoRA workflow export.",
                )
            )
            continue
        workflow_path = resolved_output_dir / f"{shot.order:03d}_{shot.shot_id}.json"
        try:
            exported = export_comfyui_workflow(
                settings=settings,
                character_id=shot.character_id,
                template_path=template_path,
                output_path=workflow_path,
                lora_index=lora_index,
            )
            workflow = json.loads(workflow_path.read_text(encoding="utf-8-sig"))
            workflow = inject_shot_context(
                workflow,
                storyboard,
                shot,
                camera_by_shot.get(shot.shot_id),
                lighting_by_shot.get(shot.shot_id),
            )
            if b_control:
                workflow = inject_b_control_context(
                    workflow=workflow,
                    shot=shot,
                    b_control_entry=b_control_by_shot.get(shot.shot_id),
                )
            workflow_path.write_text(
                json.dumps(workflow, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

            queued_job_id = ""
            if enqueue:
                queued = enqueue_comfyui_workflow(
                    settings=settings,
                    workflow_path=workflow_path,
                    base_url=base_url,
                    queue_path=queue_path,
                )
                queued_job_id = str(queued.job["job_id"])

            workflows.append(
                StoryboardWorkflowItem(
                    shot_id=shot.shot_id,
                    order=shot.order,
                    character_id=shot.character_id,
                    workflow_path=project_relative_path(settings, workflow_path),
                    lora_name=exported.lora_name,
                    queued_job_id=queued_job_id,
                )
            )
        except (FileNotFoundError, IndexError, ValueError) as error:
            skipped.append(
                StoryboardWorkflowSkip(
                    shot_id=shot.shot_id,
                    order=shot.order,
                    reason=str(error),
                )
            )

    manifest_path = resolved_output_dir / "storyboard_workflows.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "manifest_type": "storyboard_comfyui_workflows",
                "story_id": storyboard.story_id,
                "title": storyboard.title,
                "created_at": utc_timestamp(),
                "workflow_count": len(workflows),
                "skipped_count": len(skipped),
                "generation_mode": "B-control" if b_control else "A-mode",
                "supplemental_manifests": {
                    "b_control": project_relative_path(settings, b_control_manifest_path)
                    if b_control_manifest_path is not None
                    else ""
                },
                "workflows": [asdict(item) for item in workflows],
                "skipped_shots": [asdict(item) for item in skipped],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return StoryboardWorkflowExportResult(
        story_id=storyboard.story_id,
        export_dir=resolved_output_dir,
        manifest_path=manifest_path,
        workflows=workflows,
        skipped_shots=skipped,
        b_control_manifest_path=b_control_manifest_path,
    )


def inject_shot_context(
    workflow: dict[str, Any],
    storyboard: Storyboard,
    shot: Shot,
    camera: CameraWork | None = None,
    lighting: LightingSetup | None = None,
) -> dict[str, Any]:
    positive_node = find_positive_prompt_node(workflow)
    if positive_node is not None:
        inputs = positive_node.setdefault("inputs", {})
        base_prompt = str(inputs.get("text", ""))
        inputs["text"] = build_shot_prompt(base_prompt, shot, camera, lighting)

    negative_node = find_negative_prompt_node(workflow)
    if negative_node is not None and shot.negative_prompt.strip():
        inputs = negative_node.setdefault("inputs", {})
        base_prompt = str(inputs.get("text", ""))
        inputs["text"] = build_shot_negative_prompt(base_prompt, shot)

    for node in iter_comfyui_nodes(workflow):
        if node.get("class_type") == "KSampler":
            inputs = node.setdefault("inputs", {})
            if "seed" in inputs:
                inputs["seed"] = shot.seed if shot.seed is not None else stable_shot_seed(storyboard.story_id, shot.shot_id)
            if "steps" in inputs and shot.steps is not None:
                inputs["steps"] = shot.steps
        if node.get("class_type") == "EmptyLatentImage":
            inputs = node.setdefault("inputs", {})
            if "width" in inputs and shot.width is not None:
                inputs["width"] = shot.width
            if "height" in inputs and shot.height is not None:
                inputs["height"] = shot.height
        if node.get("class_type") == "SaveImage":
            inputs = node.setdefault("inputs", {})
            inputs["filename_prefix"] = (
                f"anime_studio/storyboards/{storyboard.story_id}/"
                f"{shot.order:03d}_{shot.shot_id}"
            )

    meta = workflow.setdefault("meta", {})
    meta.update(
        {
            "story_id": storyboard.story_id,
            "storyboard_title": storyboard.title,
            "shot_id": shot.shot_id,
            "shot_order": shot.order,
            "shot_title": shot.title,
            "shot_character_id": shot.character_id,
            "shot_prompt": shot.prompt,
            "shot_negative_prompt": shot.negative_prompt,
            "shot_duration_seconds": shot.duration_seconds,
            "shot_camera": shot.camera,
            "shot_lighting": shot.lighting,
            "shot_camera_work": camera.__dict__ if camera else {},
            "shot_lighting_setup": lighting.__dict__ if lighting else {},
            "shot_seed": shot.seed,
            "shot_width": shot.width,
            "shot_height": shot.height,
            "shot_steps": shot.steps,
            "shot_notes": shot.notes,
        }
    )
    return workflow


def inject_b_control_context(
    workflow: dict[str, Any],
    shot: Shot,
    b_control_entry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not b_control_entry:
        return workflow
    positive_node = find_positive_prompt_node(workflow)
    if positive_node is not None:
        inputs = positive_node.setdefault("inputs", {})
        base_prompt = str(inputs.get("text", ""))
        b_control_prompt = build_b_control_prompt_fragment(b_control_entry)
        inputs["text"] = merge_prompt_parts(base_prompt, b_control_prompt)
    return apply_b_control_to_workflow(workflow, b_control_entry)


def build_shot_prompt(
    base_prompt: str,
    shot: Shot,
    camera: CameraWork | None = None,
    lighting: LightingSetup | None = None,
) -> str:
    parts = [base_prompt.strip()]
    production_prompt = build_production_prompt(shot, camera, lighting)
    for part in [production_prompt]:
        if part and part not in parts:
            parts.append(part)
    return ", ".join(part for part in parts if part)


def build_shot_negative_prompt(base_prompt: str, shot: Shot) -> str:
    parts = [base_prompt.strip(), shot.negative_prompt.strip()]
    return ", ".join(part for part in parts if part)


def merge_prompt_parts(*parts: str) -> str:
    merged: list[str] = []
    for part in parts:
        value = str(part).strip()
        if value and value not in merged:
            merged.append(value)
    return ", ".join(merged)


def find_positive_prompt_node(workflow: dict[str, Any]) -> dict[str, Any] | None:
    nodes_by_id = {
        key: value
        for key, value in workflow.items()
        if isinstance(value, dict) and isinstance(value.get("inputs"), dict)
    }
    for node in nodes_by_id.values():
        if node.get("class_type") != "KSampler":
            continue
        positive_link = node.get("inputs", {}).get("positive")
        if isinstance(positive_link, list) and positive_link:
            positive_node = nodes_by_id.get(str(positive_link[0]))
            if positive_node and positive_node.get("class_type") == "CLIPTextEncode":
                return positive_node

    for node in nodes_by_id.values():
        if node.get("class_type") != "CLIPTextEncode":
            continue
        text = str(node.get("inputs", {}).get("text", "")).lower()
        if "worst quality" not in text and "negative" not in text:
            return node
    return None


def find_negative_prompt_node(workflow: dict[str, Any]) -> dict[str, Any] | None:
    nodes_by_id = {
        key: value
        for key, value in workflow.items()
        if isinstance(value, dict) and isinstance(value.get("inputs"), dict)
    }
    for node in nodes_by_id.values():
        if node.get("class_type") != "KSampler":
            continue
        negative_link = node.get("inputs", {}).get("negative")
        if isinstance(negative_link, list) and negative_link:
            negative_node = nodes_by_id.get(str(negative_link[0]))
            if negative_node and negative_node.get("class_type") == "CLIPTextEncode":
                return negative_node

    for node in nodes_by_id.values():
        if node.get("class_type") != "CLIPTextEncode":
            continue
        text = str(node.get("inputs", {}).get("text", "")).lower()
        if "worst quality" in text or "negative" in text:
            return node
    return None


def iter_comfyui_nodes(value: Any):
    if isinstance(value, dict):
        if "class_type" in value and isinstance(value.get("inputs", {}), dict):
            yield value
        for item in value.values():
            yield from iter_comfyui_nodes(item)
    elif isinstance(value, list):
        for item in value:
            yield from iter_comfyui_nodes(item)


def stable_shot_seed(story_id: str, shot_id: str) -> int:
    return zlib.crc32(f"{story_id}:{shot_id}".encode("utf-8")) & 0xFFFFFFFF


def normalize_output_dir(
    settings: AppSettings,
    story_id: str,
    output_dir: str | Path | None,
) -> Path:
    if output_dir is None:
        return settings.project_root / "outputs" / "comfyui" / "storyboards" / story_id
    path = Path(output_dir)
    if not path.is_absolute():
        path = settings.project_root / path
    return path
