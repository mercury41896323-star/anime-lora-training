from __future__ import annotations

from pathlib import Path
import json
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from anime_studio.character_manager import register_character_asset
from anime_studio.character_profile import create_character_profile
from anime_studio.settings import load_settings


class CharacterManagerTest(unittest.TestCase):
    def test_registers_character_image_asset(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = write_settings(root)
            source = root / "assets" / "raw" / "hero.png"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"image")

            create_character_profile(settings, "sample_hero", "Sample Hero")
            asset = register_character_asset(settings, "sample_hero", source)

            self.assertEqual(asset.kind, "image")
            self.assertTrue(Path(asset.stored_path).exists())
            manifest = json.loads(
                (
                    root
                    / "assets"
                    / "processed"
                    / "characters"
                    / "sample_hero"
                    / "assets.json"
                ).read_text(encoding="utf-8")
            )
            self.assertEqual(len(manifest["assets"]), 1)


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
