from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from anime_studio.character_profile import create_character_profile
from anime_studio.edit_preview import build_preview_movie
from anime_studio.settings import load_settings
from anime_studio.storyboard import add_shot, create_storyboard
from anime_studio.storyboard_editor import write_storyboard_editor
from anime_studio.storyboard_editor_manifest import export_selected_shot_manifest
from anime_studio.storyboard_results import link_shot_result, set_shot_result_decision
from anime_studio.timeline_manifest import build_edit_timeline_manifest
from anime_studio.timeline_revision import adopt_timeline_revision, review_timeline_revisions
from anime_studio.training_readiness import check_training_readiness, run_training_smoke


class Phase7FinishAndTrainingTest(unittest.TestCase):
    def test_preview_movie_plan_writes_ffmpeg_command_without_running(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = build_selected_story(Path(temp_dir))

            result = build_preview_movie(settings, "pilot_scene", ffmpeg_path="ffmpeg-test")

            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            self.assertFalse(manifest["ran"])
            self.assertIn("ffmpeg-test", result.command[0])
            self.assertTrue(str(result.output_movie).endswith("preview.mp4"))

    def test_reviews_and_adopts_timeline_revision(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = build_selected_story(root)
            revision = root / "integrations" / "unity" / "Assets" / "AIAnimeStudio" / "Timelines" / "pilot_scene" / "Revision_001_20260814_120000"
            revision.mkdir(parents=True)
            (revision / "pilot_scene_Edit_Timeline.playable").write_text("timeline", encoding="utf-8")
            (revision / "timeline_build_report.json").write_text(
                json.dumps(
                    {
                        "generated_at": "2026-08-14T12:00:00Z",
                        "timeline_asset": "Assets/AIAnimeStudio/Timelines/pilot_scene/Revision_001_20260814_120000/pilot_scene_Edit_Timeline.playable",
                        "protection_policy": "create_new_revision_never_overwrite_existing_timeline",
                    }
                ),
                encoding="utf-8",
            )

            review = review_timeline_revisions(settings, "pilot_scene")
            adopted = adopt_timeline_revision(settings, "pilot_scene")

            self.assertEqual(review.revision_count, 1)
            self.assertEqual(review.recommended_revision_id, "Revision_001_20260814_120000")
            self.assertEqual(adopted.revision_id, "Revision_001_20260814_120000")
            self.assertTrue(adopted.manifest_path.exists())

    def test_storyboard_editor_displays_timeline_readiness(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = build_selected_story(Path(temp_dir))
            result = write_storyboard_editor(settings, "pilot_scene")

            html = result.editor_path.read_text(encoding="utf-8")
            self.assertIn("Timeline Readiness", html)
            self.assertIn("timeline ready", html)

    def test_training_readiness_and_smoke_stop_before_training(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = write_settings(root)
            create_character_profile(settings, "sample_hero", "Sample Hero", ["sample hero"])
            image_dir = root / "assets" / "processed" / "characters" / "sample_hero" / "sources" / "image"
            image_dir.mkdir(parents=True)
            (image_dir / "sample_hero_front.png").write_bytes(b"image")

            smoke = run_training_smoke(
                settings=settings,
                character_id="sample_hero",
                pretrained_model="models/sd15.safetensors",
                min_images=1,
            )
            readiness = check_training_readiness(settings, "sample_hero", min_images=1)

            self.assertTrue(smoke.ready)
            self.assertTrue(readiness.ready)
            self.assertTrue((smoke.kohya_config_dir / "run_train.ps1").exists())
            self.assertTrue(smoke.manifest_path.exists())


def build_selected_story(root: Path):
    settings = write_settings(root)
    create_storyboard(settings, "pilot_scene", "Pilot Scene")
    add_shot(settings, "pilot_scene", "shot_001", "Opening", duration_seconds=2.0)
    image = root / "outputs" / "manual" / "opening.png"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"image")
    linked = link_shot_result(settings, "pilot_scene", "shot_001", image)
    set_shot_result_decision(settings, "pilot_scene", linked.linked[0].result_id, "selected")
    export_selected_shot_manifest(settings, "pilot_scene")
    build_edit_timeline_manifest(settings, "pilot_scene", frame_rate=24)
    return settings


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
