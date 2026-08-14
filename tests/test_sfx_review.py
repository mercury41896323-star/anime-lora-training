from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from anime_studio.character_manager import RegisteredAsset, append_asset_manifest
from anime_studio.character_profile import create_character_profile
from anime_studio.phase6_pipeline import add_sfx_cue
from anime_studio.settings import load_settings
from anime_studio.sfx_review import apply_sfx_asset_candidate, build_sfx_asset_review
from anime_studio.storyboard import add_shot, create_storyboard


class SfxReviewTest(unittest.TestCase):
    def test_builds_review_manifest_and_applies_candidate(self) -> None:
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
                duration_seconds=3.0,
            )
            stored_path = "assets/processed/characters/sample_hero/soft_wind.wav"
            stored = root / stored_path
            stored.parent.mkdir(parents=True, exist_ok=True)
            stored.write_bytes(b"wav")
            append_asset_manifest(
                settings,
                "sample_hero",
                RegisteredAsset(
                    original_path="library/soft_wind.wav",
                    stored_path=stored_path,
                    kind="sfx",
                    size_bytes=3,
                    source="asset_library",
                    metadata={"tags": ["wind", "ambience"]},
                ),
            )
            sfx = add_sfx_cue(
                settings=settings,
                story_id="pilot_scene",
                shot_id="shot_001",
                label="soft wind",
            )

            review = build_sfx_asset_review(settings, "pilot_scene")

            review_manifest = json.loads(review.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(review_manifest["manifest_type"], "storyboard_sfx_asset_review")
            self.assertEqual(review_manifest["counts"]["cue_count"], 1)
            self.assertEqual(review_manifest["items"][0]["status"], "needs_selection")
            self.assertEqual(review_manifest["items"][0]["recommended_candidate"]["stored_path"], stored_path)

            selection = apply_sfx_asset_candidate(
                settings=settings,
                story_id="pilot_scene",
                cue_id=sfx.cue_id,
                candidate_index=0,
                notes="approved for draft",
            )

            sfx_manifest = json.loads(selection.manifest_path.read_text(encoding="utf-8"))
            cue = sfx_manifest["items"][0]
            self.assertEqual(cue["asset_path"], stored_path)
            self.assertEqual(cue["asset_source"], "asset_library")
            self.assertEqual(cue["selected_asset_candidate"]["stored_path"], stored_path)
            self.assertEqual(cue["selection_notes"], "approved for draft")

            refreshed = build_sfx_asset_review(settings, "pilot_scene")
            refreshed_manifest = json.loads(refreshed.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(refreshed_manifest["items"][0]["status"], "ready")

    def test_rejects_missing_candidate_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = write_settings(root)
            create_storyboard(settings, "pilot_scene", "Pilot Scene")
            add_shot(settings=settings, story_id="pilot_scene", shot_id="shot_001", title="Opening")
            sfx = add_sfx_cue(settings=settings, story_id="pilot_scene", shot_id="shot_001", label="soft wind")

            with self.assertRaises(ValueError):
                apply_sfx_asset_candidate(
                    settings=settings,
                    story_id="pilot_scene",
                    cue_id=sfx.cue_id,
                    candidate_path="assets/missing.wav",
                )


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
