from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from anime_studio.b_control import export_b_control_manifest
from anime_studio.dataset_builder import build_motion_dataset
from anime_studio.phase6_pipeline import add_motion_cue
from anime_studio.settings import load_settings
from anime_studio.storyboard import add_shot, create_storyboard
from anime_studio.storyboard_editor_manifest import export_selected_shot_manifest
from anime_studio.storyboard_production import set_camera_work, set_lighting_setup
from anime_studio.storyboard_results import link_shot_result
from anime_studio.storyboard_review import set_shot_result_decision


class MotionDatasetTest(unittest.TestCase):
    def test_builds_motion_dataset_with_entries_and_transitions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = write_settings(root)
            create_storyboard(settings, "pilot_scene", "Pilot Scene")
            add_shot(
                settings=settings,
                story_id="pilot_scene",
                shot_id="shot_001",
                title="Turn start",
                character_id="sample_hero",
                prompt="sample_hero, side view",
                duration_seconds=2.0,
            )
            add_shot(
                settings=settings,
                story_id="pilot_scene",
                shot_id="shot_002",
                title="Turn finish",
                character_id="sample_hero",
                prompt="sample_hero, front view",
                duration_seconds=2.0,
            )
            set_camera_work(settings, "pilot_scene", "shot_001", framing="close-up", angle="side")
            set_camera_work(settings, "pilot_scene", "shot_002", framing="close-up", angle="front")
            set_lighting_setup(settings, "pilot_scene", "shot_001", key_light="side light")
            set_lighting_setup(settings, "pilot_scene", "shot_002", key_light="front light")
            add_motion_cue(
                settings=settings,
                story_id="pilot_scene",
                shot_id="shot_001",
                target="sample_hero",
                motion="turn left to front",
                duration_seconds=1.0,
            )
            add_motion_cue(
                settings=settings,
                story_id="pilot_scene",
                shot_id="shot_002",
                target="sample_hero",
                motion="settle front pose",
                duration_seconds=0.8,
            )

            image1 = root / "outputs" / "manual" / "shot_001.png"
            image2 = root / "outputs" / "manual" / "shot_002.png"
            image1.parent.mkdir(parents=True, exist_ok=True)
            image1.write_bytes(b"image1")
            image2.write_bytes(b"image2")
            linked1 = link_shot_result(settings, "pilot_scene", "shot_001", image1)
            linked2 = link_shot_result(settings, "pilot_scene", "shot_002", image2)
            set_shot_result_decision(settings, "pilot_scene", linked1.linked[0].result_id, "selected")
            set_shot_result_decision(settings, "pilot_scene", linked2.linked[0].result_id, "selected")
            export_selected_shot_manifest(settings, "pilot_scene")
            export_b_control_manifest(settings, "pilot_scene")

            result = build_motion_dataset(settings, "pilot_scene")

            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["manifest_type"], "storyboard_motion_dataset")
            self.assertEqual(result.entry_count, 2)
            self.assertEqual(result.transition_count, 1)
            self.assertEqual(manifest["transitions"][0]["requires_b_control"], True)
            self.assertTrue((result.dataset_dir / "entries.jsonl").exists())
            self.assertTrue((result.dataset_dir / "transitions.jsonl").exists())
            first_entry_id = manifest["entries"][0]["entry_id"]
            self.assertTrue((result.dataset_dir / "captions" / f"{first_entry_id}.txt").exists())


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
