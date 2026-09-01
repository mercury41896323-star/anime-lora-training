from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any

from .character_profile import validate_character_id
from .lora_registry import project_relative_path, utc_timestamp
from .settings import AppSettings, load_settings


LOSS_PATTERN = re.compile(r"(?:^|[\s,])loss[=:]\s*([-+]?\d+(?:\.\d+)?(?:e[-+]?\d+)?)", re.IGNORECASE)
EPOCH_PATTERN = re.compile(r"epoch\s*(\d+)(?:\s*/\s*(\d+))?", re.IGNORECASE)


@dataclass(frozen=True)
class TrainingDiagnosticsResult:
    manifest_path: Path
    status: str
    issue_count: int
    loss_point_count: int


def analyze_training_run(
    settings: AppSettings,
    character_id: str,
    console_log: str | Path | None = None,
    gpu_log: str | Path | None = None,
    result_log: str | Path | None = None,
    output_path: str | Path | None = None,
) -> TrainingDiagnosticsResult:
    validate_character_id(character_id)
    result_path = resolve_optional_path(settings, result_log)
    run_result = read_optional_json(result_path)
    console_value = console_log or str(run_result.get("console_log", ""))
    if not console_value:
        raise ValueError("console_log is required directly or through result_log.")
    console_path = resolve_project_path(settings, console_value)
    if not console_path.is_file():
        raise FileNotFoundError(f"Training console log does not exist: {console_path}")
    console_text = console_path.read_text(encoding="utf-8-sig", errors="replace")
    gpu_path = resolve_optional_path(settings, gpu_log or str(run_result.get("gpu_log", "")))
    losses = [float(match.group(1)) for match in LOSS_PATTERN.finditer(console_text)]
    epochs = [
        {"epoch": int(match.group(1)), "total_epochs": int(match.group(2)) if match.group(2) else None}
        for match in EPOCH_PATTERN.finditer(console_text)
    ]
    lower = console_text.lower()
    issues: list[dict[str, str]] = []
    if "out of memory" in lower or "cuda error: out of memory" in lower:
        issues.append(issue("cuda_out_of_memory", "CUDA out of memory was detected."))
    if any(token in lower for token in ("loss=nan", "loss: nan", "nan loss")):
        issues.append(issue("nan_loss", "NaN loss was detected."))
    if "traceback (most recent call last)" in lower:
        issues.append(issue("python_traceback", "A Python traceback was detected in the training log."))
    exit_code = optional_int(run_result.get("exit_code"))
    if exit_code not in (None, 0):
        issues.append(issue("nonzero_exit", f"Training process exited with code {exit_code}."))
    gpu_summary = summarize_gpu_log(gpu_path)
    if float(gpu_summary.get("max_temperature_c") or 0) > settings.runtime.target_gpu_temp_c:
        issues.append(
            issue(
                "gpu_temperature_high",
                f"GPU temperature reached {gpu_summary['max_temperature_c']} C; target is {settings.runtime.target_gpu_temp_c} C.",
            )
        )
    if any(item["code"] in {"cuda_out_of_memory", "nan_loss", "python_traceback", "nonzero_exit"} for item in issues):
        status = "failed"
    elif exit_code == 0:
        status = "completed"
    else:
        status = "incomplete"
    manifest_path = normalize_output_path(settings, character_id, output_path)
    payload = {
        "schema_version": 1,
        "manifest_type": "kohya_training_diagnostics",
        "generated_at": utc_timestamp(),
        "character_id": character_id,
        "status": status,
        "paths": {
            "console_log": project_relative_path(settings, console_path),
            "gpu_log": project_relative_path(settings, gpu_path) if gpu_path else "",
            "result_log": project_relative_path(settings, result_path) if result_path else "",
        },
        "run": {
            "exit_code": exit_code,
            "started_at": str(run_result.get("started_at", "")),
            "ended_at": str(run_result.get("ended_at", "")),
        },
        "loss": summarize_losses(losses),
        "epochs": {
            "observed": sorted({item["epoch"] for item in epochs}),
            "last": epochs[-1] if epochs else {},
        },
        "gpu": gpu_summary,
        "issues": issues,
        "next_actions": diagnostic_actions(issues, status),
    }
    write_json(manifest_path, payload)
    return TrainingDiagnosticsResult(manifest_path, status, len(issues), len(losses))


def summarize_losses(losses: list[float]) -> dict[str, Any]:
    if not losses:
        return {"point_count": 0, "first": None, "last": None, "minimum": None, "maximum": None, "trend": "unknown"}
    first = losses[0]
    last = losses[-1]
    delta = last - first
    if abs(delta) < max(abs(first) * 0.02, 1e-6):
        trend = "flat"
    else:
        trend = "decreasing" if delta < 0 else "increasing"
    return {
        "point_count": len(losses),
        "first": first,
        "last": last,
        "minimum": min(losses),
        "maximum": max(losses),
        "trend": trend,
    }


def summarize_gpu_log(path: Path | None) -> dict[str, Any]:
    if path is None or not path.is_file():
        return {"sample_count": 0, "max_memory_used_mib": None, "max_utilization_percent": None, "max_temperature_c": None}
    rows: list[dict[str, str]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        rows.extend(csv.DictReader(stream))
    return {
        "sample_count": len(rows),
        "max_memory_used_mib": max_numeric(rows, "memory_used_mib"),
        "max_utilization_percent": max_numeric(rows, "utilization_percent"),
        "max_temperature_c": max_numeric(rows, "temperature_c"),
    }


def max_numeric(rows: list[dict[str, str]], key: str) -> float | None:
    values: list[float] = []
    for row in rows:
        try:
            values.append(float(str(row.get(key, "")).strip()))
        except ValueError:
            continue
    return max(values) if values else None


def diagnostic_actions(issues: list[dict[str, str]], status: str) -> list[str]:
    codes = {item["code"] for item in issues}
    actions: list[str] = []
    if "cuda_out_of_memory" in codes:
        actions.append("Lower resolution or network_dim, keep batch size 1, then retry.")
    if "nan_loss" in codes:
        actions.append("Lower learning rate and inspect invalid captions or images.")
    if "gpu_temperature_high" in codes:
        actions.append("Improve cooling or pause training before retrying.")
    if "python_traceback" in codes or "nonzero_exit" in codes:
        actions.append("Inspect the final traceback and verify the Kohya environment.")
    if not actions and status == "completed":
        actions.append("Register the generated LoRA and run fixed-seed comparison images.")
    if not actions:
        actions.append("Wait for training completion, then analyze the final logs again.")
    return actions


def issue(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def optional_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def resolve_project_path(settings: AppSettings, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else settings.project_root / path


def resolve_optional_path(settings: AppSettings, value: str | Path | None) -> Path | None:
    if value in (None, ""):
        return None
    return resolve_project_path(settings, str(value))


def read_optional_json(path: Path | None) -> dict[str, Any]:
    if path is None or not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def normalize_output_path(settings: AppSettings, character_id: str, value: str | Path | None) -> Path:
    if value in (None, ""):
        return settings.project_root / "manifests" / "training" / character_id / "training_diagnostics.json"
    return resolve_project_path(settings, str(value))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Analyze Kohya console, GPU, and result logs.")
    parser.add_argument("--config", default="config/local_6gb.json")
    parser.add_argument("--character-id", required=True)
    parser.add_argument("--console-log", default=None)
    parser.add_argument("--gpu-log", default=None)
    parser.add_argument("--result-log", default=None)
    parser.add_argument("--output", default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = analyze_training_run(
        load_settings(args.config),
        args.character_id,
        args.console_log,
        args.gpu_log,
        args.result_log,
        args.output,
    )
    print(f"Training diagnostics: {result.manifest_path}")
    print(f"Status: {result.status}")
    print(f"Issues: {result.issue_count}")
    print(f"Loss points: {result.loss_point_count}")
    return 1 if result.status == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
