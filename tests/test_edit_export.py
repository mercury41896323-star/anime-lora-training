from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from anime_studio.edit_export import export_edit_timeline
from anime_studio.settings import load_settings
from anime_studio.storyboard import add_shot, create_storyboard
from anime_studio.storyboard_editor_manifest import export_selected_shot_manifest
from anime_studio.storyboard_results import link_shot_result, set_shot_result_decision
from anime_studio.timeline_manifest import build_edit_timeline_manifest


class EditExportTest(unittest.TestCase):
    def test_exports_ffmpeg_edl_and_fcpxml_from_edit_timeline(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = write_settings(root)
            create_storyboard(settings, "pilot_scene", "Pilot Scene")
            add_shot(settings, "pilot_scene", "shot_001", "Opening", duration_seconds=2.5)
            add_shot(settings, "pilot_scene", "shot_002", "Reaction", duration_seconds=1.5)
            first_image = root / "outputs" / "manual" / "opening.png"
            second_image = root / "outputs" / "manual" / "reaction.png"
            first_image.parent.mkdir(parents=True)
            first_image.write_bytes(b"image1")
            second_image.write_bytes(b"image2")

            first = link_shot_result(settings, "pilot_scene", "shot_001", first_image)
            second = link_shot_result(settings, "pilot_scene", "shot_002", second_image)
            set_shot_result_decision(settings, "pilot_scene", first.linked[0].result_id, "selected")
            set_shot_result_decision(settings, "pilot_scene", second.linked[0].result_id, "selected")
            export_selected_shot_manifest(settings, "pilot_scene")
            build_edit_timeline_manifest(settings, "pilot_scene", frame_rate=24)

            result = export_edit_timeline(settings, "pilot_scene")

            self.assertEqual(result.clip_count, 2)
            concat = result.files["ffmpeg"].read_text(encoding="utf-8")
            edl = result.files["edl"].read_text(encoding="utf-8")
            fcpxml = result.files["fcpxml"].read_text(encoding="utf-8")
            export_manifest = json.loads(result.files["manifest"].read_text(encoding="utf-8"))
            self.assertIn("ffconcat version 1.0", concat)
            self.assertIn("duration 2.5", concat)
            self.assertIn("TITLE: Pilot Scene", edl)
            self.assertIn("00:00:02:12", edl)
            self.assertIn("<fcpxml", fcpxml)
            self.assertIn("asset-clip", fcpxml)
            self.assertEqual(export_manifest["manifest_type"], "storyboard_edit_exports")
            self.assertEqual(export_manifest["clip_count"], 2)


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
