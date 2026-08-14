from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from anime_studio.motion_clip_plan import build_motion_clip_plan
from anime_studio.phase6_pipeline import add_motion_cue
from anime_studio.settings import load_settings
from anime_studio.storyboard import add_shot, create_storyboard


class MotionClipPlanTest(unittest.TestCase):
    def test_exports_motion_clip_plan_with_presets_and_keyframes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = write_settings(root)
            create_storyboard(settings, "pilot_scene", "Pilot Scene")
            add_shot(
                settings=settings,
                story_id="pilot_scene",
                shot_id="shot_001",
                title="Opening",
                character_id="sample_hero",
                duration_seconds=3.0,
            )
            add_motion_cue(
                settings=settings,
                story_id="pilot_scene",
                shot_id="shot_001",
                target="sample_hero",
                motion="small nod",
                intensity=1.5,
            )
            add_motion_cue(
                settings=settings,
                story_id="pilot_scene",
                shot_id="shot_001",
                target="camera_main",
                motion="camera pan",
                duration_seconds=2.0,
            )

            result = build_motion_clip_plan(settings, "pilot_scene", frame_rate=12)

            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["manifest_type"], "storyboard_motion_clip_plan")
            self.assertEqual(manifest["settings"]["frame_rate"], 12)
            self.assertEqual(manifest["counts"]["clip_count"], 2)
            self.assertEqual(manifest["counts"]["target_count"], 2)
            presets = {clip["target"]: clip["preset"] for clip in manifest["clips"]}
            self.assertEqual(presets["sample_hero"], "head_nod")
            self.assertEqual(presets["camera_main"], "camera_drift")
            hero_clip = next(clip for clip in manifest["clips"] if clip["target"] == "sample_hero")
            self.assertGreater(hero_clip["keyframes"][1]["local_euler"][0], 8.0)
            camera_clip = next(clip for clip in manifest["clips"] if clip["target"] == "camera_main")
            self.assertEqual(camera_clip["duration_seconds"], 2.0)
            self.assertGreater(camera_clip["keyframes"][-1]["local_position"][0], 0.0)

    def test_rejects_invalid_frame_rate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = write_settings(root)
            create_storyboard(settings, "pilot_scene", "Pilot Scene")

            with self.assertRaises(ValueError):
                build_motion_clip_plan(settings, "pilot_scene", frame_rate=0)


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
