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
from anime_studio.tagger import (
    finalize_tag_sidecars,
    generate_auto_tag_records,
    generate_provider_tags,
    tag_record_path,
    update_manual_tags,
)


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

            auto_result = generate_auto_tag_records(
                settings,
                "sample_hero",
                extra_tags=["anime_style"],
            )
            manual_result = update_manual_tags(
                settings,
                "sample_hero",
                add_tags=["blue_hair"],
                reject_tags=["hero"],
            )
            final_result = finalize_tag_sidecars(settings, "sample_hero")
            dataset = build_lora_dataset(settings, "sample_hero")
            registered_image = next(
                (
                    root
                    / "assets"
                    / "processed"
                    / "characters"
                    / "sample_hero"
                    / "sources"
                    / "image"
                ).glob("*.png")
            )
            tag_record = json.loads(tag_record_path(registered_image).read_text(encoding="utf-8"))

            self.assertEqual(len(auto_result.files_written), 1)
            self.assertEqual(len(manual_result.files_written), 1)
            self.assertEqual(len(final_result.files_written), 1)
            self.assertIn("sample_hero", tag_record["auto_tags"])
            self.assertIn("blue_hair", tag_record["manual_tags"])
            self.assertNotIn("hero", tag_record["final_tags"])
            self.assertEqual(dataset.image_count, 1)
            self.assertEqual(dataset.caption_count, 1)
            caption = next((dataset.dataset_dir / "images").glob("*.txt"))
            self.assertEqual(
                caption.read_text(encoding="utf-8").strip(),
                "sample_hero, anime_style, blue_hair",
            )

    def test_rejects_unknown_tag_provider(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = write_settings(Path(temp_dir))

            with self.assertRaisesRegex(ValueError, "Unknown tag provider"):
                generate_provider_tags(settings, Path("hero.png"), "unknown")


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
