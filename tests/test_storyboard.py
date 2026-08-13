from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from anime_studio.character_profile import create_character_profile
from anime_studio.settings import load_settings
from anime_studio.storyboard import add_shot, create_storyboard, list_storyboard_shots


class StoryboardTest(unittest.TestCase):
    def test_creates_storyboard_and_adds_ordered_shots(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = write_settings(root)
            create_character_profile(settings, "sample_hero", "Sample Hero")

            storyboard_path = create_storyboard(settings, "pilot_scene", "Pilot Scene")
            add_shot(
                settings=settings,
                story_id="pilot_scene",
                shot_id="shot_001",
                title="Opening close-up",
                character_id="sample_hero",
                prompt="sample_hero, close-up, soft light",
                negative_prompt="blurry, low quality",
                duration_seconds=2.5,
                camera="close-up",
                lighting="soft light",
                seed=12345,
                width=640,
                height=384,
                steps=18,
            )
            add_shot(
                settings=settings,
                story_id="pilot_scene",
                shot_id="shot_002",
                title="Wide reveal",
            )

            shots = list_storyboard_shots(settings, "pilot_scene")
            self.assertTrue(storyboard_path.exists())
            self.assertEqual([shot.order for shot in shots], [1, 2])
            self.assertEqual(shots[0].character_id, "sample_hero")
            self.assertEqual(shots[0].negative_prompt, "blurry, low quality")
            self.assertEqual(shots[0].duration_seconds, 2.5)
            self.assertEqual(shots[0].seed, 12345)
            self.assertEqual(shots[0].width, 640)
            self.assertEqual(shots[0].height, 384)
            self.assertEqual(shots[0].steps, 18)
            self.assertEqual(shots[1].title, "Wide reveal")

    def test_rejects_duplicate_shot_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = write_settings(root)
            create_storyboard(settings, "pilot_scene", "Pilot Scene")
            add_shot(settings, "pilot_scene", "shot_001", "Opening")

            with self.assertRaises(ValueError):
                add_shot(settings, "pilot_scene", "shot_001", "Duplicate")


def write_settings(root: Path):
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
                "datasets": {
                    "lora_dir": "datasets/lora",
                },
                "models": {
                    "wd14_dir": "models/wd14",
                },
                "asset_types": {
                    "image_extensions": [".png"],
                    "video_extensions": [".mp4"],
                },
            }
        ),
        encoding="utf-8",
    )
    return load_settings(config_path)


if __name__ == "__main__":
    unittest.main()
