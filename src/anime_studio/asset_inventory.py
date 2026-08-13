from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .settings import AppSettings


@dataclass(frozen=True)
class AssetItem:
    path: str
    kind: str
    size_bytes: int


def collect_asset_inventory(settings: AppSettings) -> dict[str, object]:
    raw_dir = settings.assets.raw
    raw_dir.mkdir(parents=True, exist_ok=True)
    settings.assets.processed.mkdir(parents=True, exist_ok=True)

    image_extensions = {value.lower() for value in settings.image_extensions}
    video_extensions = {value.lower() for value in settings.video_extensions}

    items: list[AssetItem] = []
    for path in sorted(raw_dir.rglob("*")):
        if not path.is_file() or path.name == ".gitkeep":
            continue

        suffix = path.suffix.lower()
        if suffix in image_extensions:
            kind = "image"
        elif suffix in video_extensions:
            kind = "video"
        else:
            kind = "other"

        items.append(
            AssetItem(
                path=path.relative_to(raw_dir).as_posix(),
                kind=kind,
                size_bytes=path.stat().st_size,
            )
        )

    counts = {
        "image": sum(1 for item in items if item.kind == "image"),
        "video": sum(1 for item in items if item.kind == "video"),
        "other": sum(1 for item in items if item.kind == "other"),
    }

    return {
        "profile": settings.runtime.name,
        "limits": {
            "max_vram_gb": settings.runtime.max_vram_gb,
            "target_gpu_utilization": settings.runtime.target_gpu_utilization,
            "target_gpu_temp_c": settings.runtime.target_gpu_temp_c,
        },
        "raw_dir": str(raw_dir),
        "processed_dir": str(settings.assets.processed),
        "counts": counts,
        "items": [item.__dict__ for item in items],
    }
