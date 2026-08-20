from __future__ import annotations

from pathlib import Path
import json
import sys
import tempfile
import unittest

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from anime_studio.character_profile import load_character_profile
from anime_studio.character_sheet_importer import import_character_sheet
from anime_studio.settings import load_settings


class CharacterSheetImporterTest(unittest.TestCase):
    def test_imports_sheet_regions_and_updates_profile(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = write_settings(root)

            source = root / "assets" / "raw" / "yonagi_sheet.png"
            source.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (1000, 1000), color=(180, 120, 220)).save(source)

            result = import_character_sheet(
                settings=settings,
                character_id="sample_yonagi",
                source_image=source,
                source_label="yonagi_sheet_v1",
                display_name="Sample Yonagi",
            )

            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            profile = load_character_profile(settings, "sample_yonagi")

            self.assertEqual(manifest["manifest_type"], "character_sheet_import")
            self.assertEqual(manifest["sheet_id"], "yonagi_sheet_v1")
            self.assertEqual(result.section_count, 11)
            self.assertTrue((result.asset_dir / "main_portrait.png").exists())
            self.assertTrue((result.asset_dir / "main_portrait.txt").exists())
            self.assertIn("character sheet imported", profile.source_notes)


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