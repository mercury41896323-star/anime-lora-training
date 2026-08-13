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
from anime_studio.dataset_builder import build_lora_dataset
from anime_studio.settings import load_settings
from anime_studio.tagger import prepare_tag_sidecars


class TaggerAndDatasetTest(unittest.TestCase):
    def test_prepares_tags_and_builds_lora_dataset(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = write_settings(root)
            source = root / "assets" / "raw" / "hero.png"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"image")

            create_character_profile(
                settings,
                "sample_hero",
                "Sample Hero",
                trigger_tags=["sample_hero"],
            )
            register_character_asset(settings, "sample_hero", source)

            tag_result = prepare_tag_sidecars(
                settings,
                "sample_hero",
                extra_tags=["anime_style"],
            )
            dataset = build_lora_dataset(settings, "sample_hero")

            self.assertEqual(len(tag_result.files_written), 1)
            self.assertEqual(dataset.image_count, 1)
            self.assertEqual(dataset.caption_count, 1)
            caption = next((dataset.dataset_dir / "images").glob("*.txt"))
            self.assertEqual(caption.read_text(encoding="utf-8").strip(), "sample_hero, anime_style")


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
