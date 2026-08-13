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
from anime_studio.storyboard_production import set_camera_work, set_lighting_setup
from anime_studio.storyboard_results import link_shot_result, set_shot_result_decision
from anime_studio.storyboard_suggestions import build_shot_suggestion_report


class StoryboardSuggestionsTest(unittest.TestCase):
    def test_writes_phase5_suggestion_report(self) -> None:
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
                prompt="sample_hero, hopeful smile",
                negative_prompt="blurry, low quality",
                seed=12345,
                width=512,
                height=512,
                steps=20,
            )
            add_shot(settings, "pilot_scene", "shot_002", "Cutaway")
            set_camera_work(
                settings=settings,
                story_id="pilot_scene",
                shot_id="shot_001",
                framing="close-up",
                movement="slow dolly in",
                lens_mm=35,
            )
            set_lighting_setup(
                settings=settings,
                story_id="pilot_scene",
                shot_id="shot_001",
                key_light="soft key light",
                mood="warm hopeful mood",
            )
            linked = link_shot_result(
                settings=settings,
                story_id="pilot_scene",
                shot_id="shot_001",
                result_path="outputs/manual/opening.png",
            )
            set_shot_result_decision(
                settings=settings,
                story_id="pilot_scene",
                result_id=linked.linked[0].result_id,
                decision="selected",
            )

            report = build_shot_suggestion_report(settings, "pilot_scene")
            manifest = json.loads(report.manifest_path.read_text(encoding="utf-8"))

            self.assertEqual(report.shot_count, 2)
            self.assertEqual(report.ready_count, 1)
            self.assertEqual(report.blocked_count, 1)
            self.assertEqual(manifest["manifest_type"], "storyboard_shot_suggestions")
            self.assertEqual(manifest["policy"]["default_width"], 512)
            self.assertEqual(manifest["shots"][0]["risk_level"], "ready")
            self.assertEqual(manifest["shots"][0]["selected_result_id"], linked.linked[0].result_id)
            self.assertIn("slow dolly in", manifest["shots"][0]["prompt_additions"])
            self.assertIn("warm hopeful mood", manifest["shots"][0]["prompt"])
            self.assertEqual(manifest["shots"][1]["risk_level"], "blocked")
            self.assertIn("character_id", manifest["shots"][1]["missing"])

    def test_flags_settings_that_are_risky_for_6gb_vram(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = write_settings(root)
            create_character_profile(settings, "sample_hero", "Sample Hero")
            create_storyboard(settings, "pilot_scene", "Pilot Scene")
            add_shot(
                settings=settings,
                story_id="pilot_scene",
                shot_id="shot_001",
                title="Large Draft",
                character_id="sample_hero",
                prompt="wide exterior",
                width=1024,
                height=1024,
                steps=32,
            )

            report = build_shot_suggestion_report(settings, "pilot_scene")
            manifest = json.loads(report.manifest_path.read_text(encoding="utf-8"))
            flags = manifest["shots"][0]["quality_flags"]

            self.assertEqual(report.needs_attention_count, 1)
            self.assertIn("large_resolution_for_6gb", flags)
            self.assertIn("high_steps_for_6gb", flags)
            self.assertIn("missing_negative_prompt", flags)


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
