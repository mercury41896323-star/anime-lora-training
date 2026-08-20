from __future__ import annotations

from pathlib import Path
import json
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from anime_studio.character_bootstrap import bootstrap_character_from_video
from anime_studio.character_profile import load_character_profile
from anime_studio.settings import load_settings


class CharacterBootstrapTest(unittest.TestCase):
    def test_bootstraps_profile_and_imports_video(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = write_settings(root)
            source_video = root / "assets" / "raw" / "episode01.mp4"
            source_video.parent.mkdir(parents=True)
            source_video.write_bytes(b"video")

            result = bootstrap_character_from_video(
                settings=settings,
                character_id="sample_yonagi",
                display_name="Sample Yonagi",
                video_path=source_video,
                trigger_tags=["sample_yonagi"],
                source_label="episode01",
                source_notes="video reference",
            )

            profile = load_character_profile(settings, "sample_yonagi")
            manifest = json.loads(result.bootstrap_manifest_path.read_text(encoding="utf-8"))

            self.assertTrue(result.created_profile)
            self.assertEqual(profile.display_name, "Sample Yonagi")
            self.assertIn("video reference", profile.source_notes)
            self.assertEqual(manifest["manifest_type"], "character_bootstrap")
            self.assertEqual(manifest["video_id"], "episode01")


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
                    "video_extensions": [".mp4", ".mov"],
                },
            }
        ),
        encoding="utf-8",
    )
    return load_settings(config_path)


if __name__ == "__main__":
    unittest.main()
