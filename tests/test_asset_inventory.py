from __future__ import annotations

from pathlib import Path
import json
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from anime_studio.asset_inventory import collect_asset_inventory
from anime_studio.settings import load_settings


class AssetInventoryTest(unittest.TestCase):
    def test_collects_images_videos_and_other_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_dir = root / "config"
            raw_dir = root / "assets" / "raw"
            config_dir.mkdir(parents=True)
            raw_dir.mkdir(parents=True)

            (raw_dir / "hero.png").write_bytes(b"image")
            (raw_dir / "shot.mp4").write_bytes(b"video")
            (raw_dir / "notes.txt").write_text("notes", encoding="utf-8")

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
            inventory = collect_asset_inventory(settings)

            self.assertEqual(inventory["counts"]["image"], 1)
            self.assertEqual(inventory["counts"]["video"], 1)
            self.assertEqual(inventory["counts"]["other"], 1)
            self.assertEqual(
                [item["path"] for item in inventory["items"]],
                ["hero.png", "notes.txt", "shot.mp4"],
            )


if __name__ == "__main__":
    unittest.main()
