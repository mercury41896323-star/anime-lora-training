from __future__ import annotations

from pathlib import Path
import json
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from anime_studio.character_profile import create_character_profile
from anime_studio.settings import load_settings


class CharacterProfileTest(unittest.TestCase):
    def test_creates_profile_json(self) -> None:
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
            profile_path = create_character_profile(
                settings=settings,
                character_id="sample_hero",
                display_name="Sample Hero",
                trigger_tags=["sample_hero"],
            )
            profile = json.loads(profile_path.read_text(encoding="utf-8"))

            self.assertEqual(profile["character_id"], "sample_hero")
            self.assertEqual(profile["display_name"], "Sample Hero")
            self.assertEqual(profile["trigger_tags"], ["sample_hero"])
            self.assertEqual(profile["profile_template"], "character_profile_v1")
            self.assertTrue(profile["profile_data"]["training"]["require_2p5d_before_lora"])
            self.assertIn("ParamAngleX", profile["profile_data"]["rigging"]["parameters"])


if __name__ == "__main__":
    unittest.main()
