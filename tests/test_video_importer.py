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
from anime_studio.video_importer import import_video_asset


class VideoImporterTest(unittest.TestCase):
    def test_imports_video_and_writes_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = write_settings(root)
            source = root / "assets" / "raw" / "scene 001.mp4"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"video")

            create_character_profile(settings, "sample_yonagi", "Sample Yonagi")
            result = import_video_asset(
                settings=settings,
                character_id="sample_yonagi",
                source_path=source,
                source_label="baseline_clip",
            )

            self.assertEqual(result.asset.video_id, "scene_001")
            self.assertTrue(Path(result.asset.stored_path).exists())
            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["manifest_type"], "character_video_sources")
            self.assertEqual(len(manifest["videos"]), 1)
            self.assertEqual(manifest["videos"][0]["pipeline_state"]["shot_detection"], "pending")


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
