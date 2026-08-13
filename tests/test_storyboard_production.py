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
from anime_studio.storyboard import add_shot, create_storyboard
from anime_studio.storyboard_production import (
    build_draft_generation_plan,
    set_camera_work,
    set_lighting_setup,
)


class StoryboardProductionTest(unittest.TestCase):
    def test_writes_camera_lighting_and_draft_plan(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = write_settings(root)
            create_character_profile(settings, "sample_hero", "Sample Hero")
            create_storyboard(settings, "pilot_scene", "Pilot Scene")
            add_shot(
                settings=settings,
                story_id="pilot_scene",
                shot_id="shot_001",
                title="Opening",
                character_id="sample_hero",
                prompt="hopeful smile",
                negative_prompt="blurry",
                seed=12345,
                width=640,
                height=384,
                steps=18,
            )
            add_shot(settings, "pilot_scene", "shot_002", "Cutaway")

            camera = set_camera_work(
                settings=settings,
                story_id="pilot_scene",
                shot_id="shot_001",
                framing="close-up",
                movement="slow dolly in",
                lens_mm=35,
                angle="eye level",
                focus="shallow depth of field",
            )
            lighting = set_lighting_setup(
                settings=settings,
                story_id="pilot_scene",
                shot_id="shot_001",
                key_light="soft key light",
                fill_light="low fill",
                mood="warm hopeful mood",
                time_of_day="morning",
                color_palette="amber and blue",
            )
            draft = build_draft_generation_plan(settings, "pilot_scene")

            camera_manifest = json.loads(camera.manifest_path.read_text(encoding="utf-8"))
            lighting_manifest = json.loads(lighting.manifest_path.read_text(encoding="utf-8"))
            draft_manifest = json.loads(draft.plan_path.read_text(encoding="utf-8"))

            self.assertEqual(camera.item_count, 1)
            self.assertEqual(lighting.item_count, 1)
            self.assertEqual(draft.draft_count, 1)
            self.assertEqual(draft.skipped_count, 1)
            self.assertEqual(camera_manifest["items"][0]["movement"], "slow dolly in")
            self.assertEqual(lighting_manifest["items"][0]["mood"], "warm hopeful mood")
            self.assertIn("slow dolly in", draft_manifest["drafts"][0]["prompt"])
            self.assertIn("warm hopeful mood", draft_manifest["drafts"][0]["prompt"])
            self.assertEqual(draft_manifest["drafts"][0]["generation"]["width"], 640)
            self.assertEqual(draft_manifest["skipped_shots"][0]["shot_id"], "shot_002")


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
