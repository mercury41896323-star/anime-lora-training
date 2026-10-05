from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
from typing import Sequence

from .lora_registry import project_relative_path, utc_timestamp
from .settings import AppSettings
from .training_readiness import check_training_readiness


@dataclass(frozen=True)
class TrainingRunResult:
    character_id: str
    status: str
    exit_code: int
    result_manifest: Path
    run_script: Path


def run_kohya_training(
    settings: AppSettings,
    character_id: str,
    *,
    execute: bool = False,
    min_images: int = 20,
    require_2p5d: bool = False,
    run_script: str | Path | None = None,
    output_path: str | Path | None = None,
    powershell_executable: str = "powershell.exe",
) -> TrainingRunResult:
    if not execute:
        raise ValueError(
            "Training is intentionally blocked unless execute=True. "
            "Pass --execute only after reviewing the generated Kohya config."
        )

    readiness = check_training_readiness(
        settings=settings,
        character_id=character_id,
        min_images=min_images,
        require_2p5d=require_2p5d,
    )
    if not readiness.ready:
        raise RuntimeError(
            f"Training readiness is false: {readiness.manifest_path}. "
            "Fix the reported issues before starting GPU training."
        )

    resolved_script = _resolve_path(
        settings,
        run_script or (settings.project_root / "config" / "kohya" / character_id / "run_train.ps1"),
    )
    if not resolved_script.is_file():
        raise FileNotFoundError(f"Kohya run script does not exist: {resolved_script}")

    result_path = _resolve_output_path(
        settings,
        character_id,
        output_path,
    )
    result_path.parent.mkdir(parents=True, exist_ok=True)

    command = [
        powershell_executable,
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(resolved_script),
    ]
    started_at = utc_timestamp()
    completed = subprocess.run(command, cwd=str(settings.project_root), check=False)
    ended_at = utc_timestamp()
    status = "completed" if completed.returncode == 0 else "failed"

    result_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "manifest_type": "kohya_training_run",
                "generated_at": ended_at,
                "character_id": character_id,
                "status": status,
                "exit_code": completed.returncode,
                "started_at": started_at,
                "ended_at": ended_at,
                "command": command,
                "run_script": project_relative_path(settings, resolved_script),
                "readiness": project_relative_path(settings, readiness.manifest_path),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    return TrainingRunResult(
        character_id=character_id,
        status=status,
        exit_code=completed.returncode,
        result_manifest=result_path,
        run_script=resolved_script,
    )


def _resolve_path(settings: AppSettings, value: str | Path) -> Path:
    path = Path(str(value))
    return path if path.is_absolute() else settings.project_root / path


def _resolve_output_path(
    settings: AppSettings,
    character_id: str,
    value: str | Path | None,
) -> Path:
    if value is None:
        return settings.project_root / "manifests" / "training" / character_id / "training_run.json"
    return _resolve_path(settings, value)
