from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SceneCaptureConfig:
    threshold: float = 27.0
    images_per_scene: int = 1
    image_format: str = "png"

    def validate(self) -> None:
        if self.threshold <= 0:
            raise ValueError("threshold must be greater than 0.")
        if self.images_per_scene <= 0:
            raise ValueError("images_per_scene must be greater than 0.")
        if self.image_format not in {"png", "jpg", "jpeg", "webp"}:
            raise ValueError("image_format must be png, jpg, jpeg, or webp.")


def default_scene_capture_dir(video_path: str | Path) -> Path:
    source = Path(video_path)
    return Path("assets/processed/scene_captures") / source.stem


def _load_scenedetect() -> tuple[Any, Any, Any, Any]:
    try:
        from scenedetect import ContentDetector, SceneManager, open_video
        from scenedetect.output import save_images
    except ImportError as exc:
        raise RuntimeError(
            "PySceneDetect is not installed. Install requirements-scene.txt first."
        ) from exc
    return ContentDetector, SceneManager, open_video, save_images


def analyze_and_capture_scenes(
    video_path: str | Path,
    output_dir: str | Path | None = None,
    config: SceneCaptureConfig | None = None,
) -> dict[str, Any]:
    source = Path(video_path)
    if not source.exists():
        raise FileNotFoundError(f"Video not found: {source}")

    capture_config = config or SceneCaptureConfig()
    capture_config.validate()

    destination = Path(output_dir) if output_dir is not None else default_scene_capture_dir(source)
    destination.mkdir(parents=True, exist_ok=True)

    ContentDetector, SceneManager, open_video, save_images = _load_scenedetect()

    video = open_video(str(source))
    scene_manager = SceneManager()
    scene_manager.add_detector(ContentDetector(threshold=capture_config.threshold))
    scene_manager.detect_scenes(video=video)
    scene_list = scene_manager.get_scene_list()

    image_names: dict[int, list[str]] = {}
    if scene_list:
        image_names = save_images(
            scene_list=scene_list,
            video=video,
            num_images=capture_config.images_per_scene,
            output_dir=destination,
            image_name_template="$VIDEO_NAME-Scene-$SCENE_NUMBER-$IMAGE_NUMBER",
            image_extension=capture_config.image_format,
            show_progress=False,
        )

    scenes: list[dict[str, Any]] = []
    for index, (start, end) in enumerate(scene_list, start=1):
        saved = image_names.get(index - 1, image_names.get(index, []))
        scenes.append(
            {
                "scene_id": f"scene_{index:04d}",
                "scene_number": index,
                "start_frame": start.get_frames(),
                "end_frame": end.get_frames(),
                "start_timecode": start.get_timecode(),
                "end_timecode": end.get_timecode(),
                "duration_seconds": (end - start).get_seconds(),
                "captures": [str(destination / name) for name in saved],
                "analysis": {
                    "characters": [],
                    "hair": [],
                    "body": [],
                    "arms": [],
                    "clothes": [],
                    "background": [],
                    "motion": [],
                },
            }
        )

    manifest = {
        "schema_version": 1,
        "source_video": str(source),
        "output_dir": str(destination),
        "detector": {
            "name": "PySceneDetect.ContentDetector",
            "threshold": capture_config.threshold,
        },
        "capture": {
            "images_per_scene": capture_config.images_per_scene,
            "image_format": capture_config.image_format,
        },
        "scene_count": len(scenes),
        "scenes": scenes,
    }

    manifest_path = destination / "scene_capture_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    manifest["manifest_path"] = str(manifest_path)
    return manifest
