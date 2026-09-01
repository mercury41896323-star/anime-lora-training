from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen
import uuid

from .lora_registry import project_relative_path, utc_timestamp
from .settings import AppSettings


DEFAULT_COMFYUI_BASE_URL = "http://127.0.0.1:8188"
DEFAULT_QUEUE_PATH = Path("queues/comfyui/jobs.json")


@dataclass(frozen=True)
class ComfyQueueResult:
    queue_path: Path
    job: dict[str, Any]


def enqueue_comfyui_workflow(
    settings: AppSettings,
    workflow_path: str | Path,
    base_url: str = DEFAULT_COMFYUI_BASE_URL,
    queue_path: str | Path | None = None,
) -> ComfyQueueResult:
    resolved_workflow = normalize_project_path(settings, workflow_path)
    if not resolved_workflow.exists():
        raise FileNotFoundError(f"ComfyUI workflow not found: {resolved_workflow}")

    resolved_queue = normalize_queue_path(settings, queue_path)
    queue = read_queue(resolved_queue)
    timestamp = utc_timestamp()
    job = {
        "job_id": build_job_id(resolved_workflow),
        "status": "pending",
        "workflow_path": project_relative_path(settings, resolved_workflow),
        "comfyui_base_url": normalize_base_url(base_url),
        "prompt_id": "",
        "queue_number": None,
        "created_at": timestamp,
        "updated_at": timestamp,
        "submitted_at": "",
        "checked_at": "",
        "response": {},
        "error": "",
    }
    queue["jobs"].append(job)
    write_queue(resolved_queue, queue)
    return ComfyQueueResult(queue_path=resolved_queue, job=job)


def submit_comfyui_job(
    settings: AppSettings,
    job_id: str | None = None,
    workflow_path: str | Path | None = None,
    base_url: str | None = None,
    queue_path: str | Path | None = None,
    dry_run: bool = False,
    timeout_seconds: float = 15.0,
) -> ComfyQueueResult:
    if workflow_path is not None:
        enqueued = enqueue_comfyui_workflow(
            settings=settings,
            workflow_path=workflow_path,
            base_url=base_url or DEFAULT_COMFYUI_BASE_URL,
            queue_path=queue_path,
        )
        job_id = str(enqueued.job["job_id"])

    resolved_queue = normalize_queue_path(settings, queue_path)
    queue = read_queue(resolved_queue)
    job = find_job(queue, job_id)
    if job is None:
        raise ValueError("No pending ComfyUI queue job found.")

    if base_url:
        job["comfyui_base_url"] = normalize_base_url(base_url)

    workflow = read_workflow(settings, job["workflow_path"])
    timestamp = utc_timestamp()
    if dry_run:
        job.update(
            {
                "status": "dry_run",
                "updated_at": timestamp,
                "checked_at": timestamp,
                "response": {"prompt": workflow},
                "error": "",
            }
        )
        write_queue(resolved_queue, queue)
        return ComfyQueueResult(queue_path=resolved_queue, job=job)

    try:
        response = post_json(
            urljoin(str(job["comfyui_base_url"]) + "/", "prompt"),
            {"prompt": workflow},
            timeout_seconds=timeout_seconds,
        )
        prompt_id = str(response.get("prompt_id", ""))
        job.update(
            {
                "status": "submitted" if prompt_id else "failed",
                "prompt_id": prompt_id,
                "queue_number": response.get("number"),
                "submitted_at": timestamp,
                "updated_at": timestamp,
                "response": response,
                "error": "" if prompt_id else "ComfyUI response did not include prompt_id.",
            }
        )
    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as error:
        job.update(
            {
                "status": "failed",
                "updated_at": timestamp,
                "error": str(error),
            }
        )

    write_queue(resolved_queue, queue)
    return ComfyQueueResult(queue_path=resolved_queue, job=job)


def refresh_comfyui_job(
    settings: AppSettings,
    job_id: str,
    queue_path: str | Path | None = None,
    timeout_seconds: float = 15.0,
) -> ComfyQueueResult:
    resolved_queue = normalize_queue_path(settings, queue_path)
    queue = read_queue(resolved_queue)
    job = find_job(queue, job_id, include_non_pending=True)
    if job is None:
        raise ValueError(f"ComfyUI queue job not found: {job_id}")
    prompt_id = str(job.get("prompt_id", ""))
    if not prompt_id:
        raise ValueError(f"ComfyUI queue job has no prompt_id: {job_id}")

    timestamp = utc_timestamp()
    try:
        response = get_json(
            urljoin(str(job["comfyui_base_url"]) + "/", f"history/{prompt_id}"),
            timeout_seconds=timeout_seconds,
        )
        status, execution_error = classify_comfyui_history(prompt_id, response)
        job.update(
            {
                "status": status,
                "checked_at": timestamp,
                "updated_at": timestamp,
                "response": response,
                "error": execution_error,
            }
        )
    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as error:
        job.update(
            {
                "checked_at": timestamp,
                "updated_at": timestamp,
                "error": str(error),
            }
        )

    write_queue(resolved_queue, queue)
    return ComfyQueueResult(queue_path=resolved_queue, job=job)


def refresh_submitted_comfyui_jobs(
    settings: AppSettings,
    queue_path: str | Path | None = None,
    timeout_seconds: float = 15.0,
) -> list[ComfyQueueResult]:
    resolved_queue = normalize_queue_path(settings, queue_path)
    queue = read_queue(resolved_queue)
    job_ids = [
        str(job.get("job_id", ""))
        for job in queue.get("jobs", [])
        if isinstance(job, dict)
        and str(job.get("status", "")) == "submitted"
        and str(job.get("prompt_id", ""))
    ]
    return [
        refresh_comfyui_job(
            settings=settings,
            job_id=job_id,
            queue_path=resolved_queue,
            timeout_seconds=timeout_seconds,
        )
        for job_id in job_ids
    ]


def classify_comfyui_history(prompt_id: str, response: dict[str, Any]) -> tuple[str, str]:
    raw_record = response.get(prompt_id)
    if not isinstance(raw_record, dict) or not raw_record:
        return "submitted", ""
    status_info = raw_record.get("status", {})
    status_info = status_info if isinstance(status_info, dict) else {}
    status_text = str(status_info.get("status_str", "")).lower()
    error_message = extract_execution_error(status_info.get("messages", []))
    if status_text in {"error", "failed"} or error_message:
        return "failed", error_message or f"ComfyUI execution status: {status_text}"
    if bool(status_info.get("completed", False)) or status_text in {"success", "completed"}:
        return "completed", ""
    if isinstance(raw_record.get("outputs"), dict):
        return "completed", ""
    return "submitted", ""


def extract_execution_error(messages: Any) -> str:
    if not isinstance(messages, list):
        return ""
    for message in reversed(messages):
        if not isinstance(message, (list, tuple)) or len(message) < 2:
            continue
        message_type = str(message[0]).lower()
        payload = message[1] if isinstance(message[1], dict) else {}
        if message_type not in {"execution_error", "execution_interrupted", "error"}:
            continue
        detail = str(
            payload.get("exception_message")
            or payload.get("message")
            or payload.get("exception_type")
            or message_type
        )
        node_id = str(payload.get("node_id", ""))
        return f"Node {node_id}: {detail}" if node_id else detail
    return ""


def list_comfyui_jobs(
    settings: AppSettings,
    queue_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    return list(read_queue(normalize_queue_path(settings, queue_path))["jobs"])


def read_queue(queue_path: Path) -> dict[str, Any]:
    if not queue_path.exists():
        return {
            "schema_version": 1,
            "queue_type": "comfyui_workflow_queue",
            "jobs": [],
        }
    data = json.loads(queue_path.read_text(encoding="utf-8-sig"))
    data.setdefault("schema_version", 1)
    data.setdefault("queue_type", "comfyui_workflow_queue")
    data.setdefault("jobs", [])
    return data


def write_queue(queue_path: Path, queue: dict[str, Any]) -> None:
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    queue_path.write_text(
        json.dumps(queue, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def find_job(
    queue: dict[str, Any],
    job_id: str | None,
    include_non_pending: bool = False,
) -> dict[str, Any] | None:
    jobs = list(queue.get("jobs", []))
    if job_id:
        return next((job for job in jobs if job.get("job_id") == job_id), None)
    if include_non_pending:
        return jobs[0] if jobs else None
    return next((job for job in jobs if job.get("status") == "pending"), None)


def read_workflow(settings: AppSettings, workflow_path: str | Path) -> dict[str, Any]:
    resolved_workflow = normalize_project_path(settings, workflow_path)
    return json.loads(resolved_workflow.read_text(encoding="utf-8-sig"))


def post_json(url: str, payload: dict[str, Any], timeout_seconds: float) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    request = Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=timeout_seconds) as response:
        return json.loads(response.read().decode("utf-8"))


def get_json(url: str, timeout_seconds: float) -> dict[str, Any]:
    request = Request(url, method="GET")
    with urlopen(request, timeout=timeout_seconds) as response:
        return json.loads(response.read().decode("utf-8"))


def build_job_id(workflow_path: Path) -> str:
    return f"{workflow_path.stem}-{uuid.uuid4().hex[:8]}"


def normalize_queue_path(settings: AppSettings, queue_path: str | Path | None) -> Path:
    if queue_path is None:
        return settings.project_root / DEFAULT_QUEUE_PATH
    return normalize_project_path(settings, queue_path)


def normalize_project_path(settings: AppSettings, path: str | Path) -> Path:
    resolved = Path(path)
    if not resolved.is_absolute():
        resolved = settings.project_root / resolved
    return resolved


def normalize_base_url(base_url: str) -> str:
    return base_url.rstrip("/")
