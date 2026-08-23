from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from anime_studio.settings import load_settings
from anime_studio.video_frame_cleaner import build_clean_video_frames
from anime_studio.video_shot_pipeline import sampled_manifest_path


class VideoFrameCleanerTest(unittest.TestCase):
    def test_builds_cropped_text_safe_dataset_and_excludes_tagged_text(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = write_settings(root)
            frame_dir = root / "assets" / "processed" / "characters" / "test_character" / "frames" / "scene01"
            frame_dir.mkdir(parents=True, exist_ok=True)
            clean_source = frame_dir / "frame_000001.png"
            text_source = frame_dir / "frame_000002.png"
            Image.new("RGB", (960, 540), color=(80, 120, 180)).save(clean_source)
            Image.new("RGB", (960, 540), color=(100, 140, 200)).save(text_source)
            write_sampled_manifest(root, clean_source, text_source)

            result = build_clean_video_frames(
                settings=settings,
                character_id="test_character",
                video_id="scene01",
            )

            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            output_path = root / manifest["frames"][0]["output_path"]
            with Image.open(output_path) as output:
                self.assertEqual(output.size, (512, 512))

            self.assertEqual(result.processed_count, 1)
            self.assertEqual(result.excluded_count, 1)
            self.assertEqual(manifest["manifest_type"], "video_clean_frame_manifest")
            self.assertFalse(manifest["cleanup_policy"]["ocr_verified"])
            self.assertTrue(manifest["cleanup_policy"]["human_review_required"])
            self.assertLess(manifest["frames"][0]["crop_box"]["bottom"], 540)
            self.assertEqual(manifest["frames"][1]["status"], "excluded_text_tag")


def write_sampled_manifest(root: Path, clean_source: Path, text_source: Path) -> None:
    path = root / "manifests" / "characters" / "test_character" / "video_analysis" / "scene01_sampled_frames.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "manifest_type": "video_sampled_frame_manifest",
                "character_id": "test_character",
                "video_id": "scene01",
                "frames": [
                    {
                        "shot_id": "shot_001",
                        "frame_path": clean_source.relative_to(root).as_posix(),
                        "frame_index": 1,
                        "timestamp_seconds": 0.0,
                        "role": "start",
                        "tags": ["test_character", "front", "portrait"],
                    },
                    {
                        "shot_id": "shot_001",
                        "frame_path": text_source.relative_to(root).as_posix(),
                        "frame_index": 2,
                        "timestamp_seconds": 1.0,
                        "role": "end",
                        "tags": ["test_character", "subtitle"],
                    },
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )


def write_settings(root: Path):
    config_dir = root / "config"
    config_dir.mkdir(parents=True)
    config_path = config_dir / "local_6gb.json"
    config_path.write_text(
        json.dumps(
            {
                "runtime": {"name": "test", "max_vram_gb": 6.0, "target_gpu_utilization": 0.8, "target_gpu_temp_c": 60},
                "assets": {"raw_dir": "assets/raw", "processed_dir": "assets/processed"},
                "datasets": {"lora_dir": "datasets/lora"},
                "models": {"wd14_dir": "models/wd14"},
                "asset_types": {"image_extensions": [".png"], "video_extensions": [".mp4"]},
            }
        ),
        encoding="utf-8",
    )
    return load_settings(config_path)


if __name__ == "__main__":
    unittest.main()
