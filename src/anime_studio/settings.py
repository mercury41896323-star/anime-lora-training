from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path


@dataclass(frozen=True)
class RuntimeProfile:
    name: str
    max_vram_gb: float
    target_gpu_utilization: float
    target_gpu_temp_c: int


@dataclass(frozen=True)
class AssetPaths:
    raw: Path
    processed: Path


@dataclass(frozen=True)
class DatasetPaths:
    lora: Path


@dataclass(frozen=True)
class ModelPaths:
    wd14: Path


@dataclass(frozen=True)
class AppSettings:
    project_root: Path
    runtime: RuntimeProfile
    assets: AssetPaths
    datasets: DatasetPaths
    models: ModelPaths
    image_extensions: tuple[str, ...]
    video_extensions: tuple[str, ...]


def load_settings(config_path: str | Path) -> AppSettings:
    path = Path(config_path)
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    base_dir = path.parent.parent

    runtime = data["runtime"]
    assets = data["assets"]
    datasets = data.get("datasets", {})
    models = data.get("models", {})

    return AppSettings(
        project_root=base_dir.resolve(),
        runtime=RuntimeProfile(
            name=runtime["name"],
            max_vram_gb=float(runtime["max_vram_gb"]),
            target_gpu_utilization=float(runtime["target_gpu_utilization"]),
            target_gpu_temp_c=int(runtime["target_gpu_temp_c"]),
        ),
        assets=AssetPaths(
            raw=(base_dir / assets["raw_dir"]).resolve(),
            processed=(base_dir / assets["processed_dir"]).resolve(),
        ),
        datasets=DatasetPaths(
            lora=(base_dir / datasets.get("lora_dir", "datasets/lora")).resolve(),
        ),
        models=ModelPaths(
            wd14=(base_dir / models.get("wd14_dir", "models/wd14")).resolve(),
        ),
        image_extensions=tuple(data["asset_types"]["image_extensions"]),
        video_extensions=tuple(data["asset_types"]["video_extensions"]),
    )
