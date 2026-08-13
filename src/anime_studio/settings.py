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
class AppSettings:
    runtime: RuntimeProfile
    assets: AssetPaths
    image_extensions: tuple[str, ...]
    video_extensions: tuple[str, ...]


def load_settings(config_path: str | Path) -> AppSettings:
    path = Path(config_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    base_dir = path.parent.parent

    runtime = data["runtime"]
    assets = data["assets"]

    return AppSettings(
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
        image_extensions=tuple(data["asset_types"]["image_extensions"]),
        video_extensions=tuple(data["asset_types"]["video_extensions"]),
    )
