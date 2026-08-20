from __future__ import annotations

from pathlib import Path
import json
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from anime_studio.frame_extraction import build_frame_extraction_plan
from anime_studio.settings import load_settings


class FrameExtractionTest(unittest.TestCase):
    def test_builds_ffmpeg_command(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_dir = root / "config"
            config_dir.mkdir(parents=True)
            config_path = config_dir / "local_6gb.json"
            config_path.write_text(
                json.dumps(
                    {
                        "runtime": {
                            "name": "test",
                            "max_vram_gb": 6.0,
                            "target_gpu_utilization": 0.8,
                            "target_gpu_temp_c": 60,
                        },
                        "assets": {
                            "raw_dir": "assets/raw",
                            "processed_dir": "assets/processed",
                        },
                        "asset_types": {
                            "image_extensions": [".png"],
                            "video_extensions": [".mp4"],
                        },
                    }
                ),
                encoding="utf-8",
            )

            settings = load_settings(config_path)
            plan = build_frame_extraction_plan(
                settings=settings,
                video_path="assets/raw/sample.mp4",
                character_id="sample_hero",
                fps=0.5,
            )

            self.assertEqual(plan.command[0], "ffmpeg")
            self.assertIn("fps=0.5", plan.command)
            self.assertTrue(str(plan.output_dir).endswith("sample_hero\\frames"))

    def test_builds_grouped_output_dir(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_dir = root / "config"
            config_dir.mkdir(parents=True)
            config_path = config_dir / "local_6gb.json"
            config_path.write_text(
                json.dumps(
                    {
                        "runtime": {
                            "name": "test",
                            "max_vram_gb": 6.0,
                            "target_gpu_utilization": 0.8,
                            "target_gpu_temp_c": 60,
                        },
                        "assets": {
                            "raw_dir": "assets/raw",
                            "processed_dir": "assets/processed",
                        },
                        "asset_types": {
                            "image_extensions": [".png"],
                            "video_extensions": [".mp4"],
                        },
                    }
                ),
                encoding="utf-8",
            )

            settings = load_settings(config_path)
            plan = build_frame_extraction_plan(
                settings=settings,
                video_path="assets/raw/sample.mp4",
                character_id="sample_hero",
                fps=1.0,
                output_group="Scene 001",
            )

            self.assertTrue(str(plan.output_dir).endswith("sample_hero\\frames\\scene_001"))


if __name__ == "__main__":
    unittest.main()
