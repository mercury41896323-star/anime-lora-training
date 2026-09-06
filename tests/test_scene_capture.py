from __future__ import annotations

from pathlib import Path

import pytest

from anime_studio.scene_capture import SceneCaptureConfig, default_scene_capture_dir


def test_scene_capture_config_defaults_are_valid() -> None:
    SceneCaptureConfig().validate()


def test_scene_capture_config_rejects_invalid_values() -> None:
    with pytest.raises(ValueError):
        SceneCaptureConfig(threshold=0).validate()
    with pytest.raises(ValueError):
        SceneCaptureConfig(images_per_scene=0).validate()
    with pytest.raises(ValueError):
        SceneCaptureConfig(image_format="bmp").validate()


def test_default_scene_capture_dir_uses_video_stem() -> None:
    assert default_scene_capture_dir("assets/raw/sample.mp4") == Path(
        "assets/processed/scene_captures/sample"
    )
