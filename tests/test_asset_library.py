from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from anime_studio.asset_library import collect_asset_library, search_asset_library, write_asset_library_index
from anime_studio.character_manager import RegisteredAsset, append_asset_manifest
from anime_studio.character_profile import create_character_profile
from anime_studio.settings import load_settings


class AssetLibraryTest(unittest.TestCase):
    def test_collects_and_filters_character_assets(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = write_settings(root)
            create_character_profile(settings, "sample_hero", "Sample Hero")
            stored = root / "assets" / "processed" / "characters" / "sample_hero" / "generated.png"
            stored.parent.mkdir(parents=True, exist_ok=True)
            stored.write_bytes(b"image")
            append_asset_manifest(
                settings,
                "sample_hero",
                RegisteredAsset(
                    original_path="comfy/output/generated.png",
                    stored_path="assets/processed/characters/sample_hero/generated.png",
                    kind="image",
                    size_bytes=5,
                    source="comfyui_result",
                    metadata={"prompt_id": "prompt-1", "tag": "smile"},
                ),
            )

            items = collect_asset_library(
                settings,
                character_id="sample_hero",
                kind="image",
                source="comfyui_result",
                query="smile",
            )

            self.assertEqual(len(items), 1)
            self.assertEqual(items[0].display_name, "Sample Hero")
            self.assertTrue(items[0].exists)
            self.assertEqual(items[0].metadata["prompt_id"], "prompt-1")

    def test_searches_asset_library_by_weighted_tags(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = write_settings(root)
            create_character_profile(settings, "sample_hero", "Sample Hero")
            stored = root / "assets" / "processed" / "characters" / "sample_hero" / "soft_wind.wav"
            stored.parent.mkdir(parents=True, exist_ok=True)
            stored.write_bytes(b"wav")
            append_asset_manifest(
                settings,
                "sample_hero",
                RegisteredAsset(
                    original_path="library/soft_wind.wav",
                    stored_path="assets/processed/characters/sample_hero/soft_wind.wav",
                    kind="sfx",
                    size_bytes=3,
                    source="asset_library",
                    metadata={"tags": ["wind", "ambience"]},
                ),
            )

            matches = search_asset_library(settings, query="wind ambience", kinds=("sfx",), limit=1)

            self.assertEqual(len(matches), 1)
            self.assertEqual(matches[0]["stored_path"], "assets/processed/characters/sample_hero/soft_wind.wav")
            self.assertGreater(matches[0]["score"], 1)

    def test_writes_asset_library_index(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = write_settings(root)
            create_character_profile(settings, "sample_hero", "Sample Hero")
            append_asset_manifest(
                settings,
                "sample_hero",
                RegisteredAsset(
                    original_path="manual.png",
                    stored_path="assets/processed/characters/sample_hero/missing.png",
                    kind="image",
                    size_bytes=0,
                ),
            )

            output = write_asset_library_index(settings, "assets/processed/library_index.json")

            index = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(index["count"], 1)
            self.assertFalse(index["items"][0]["exists"])


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
