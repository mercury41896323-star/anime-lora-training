from __future__ import annotations

from pathlib import Path
import json
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from anime_studio.settings import load_settings


class SettingsTest(unittest.TestCase):
    def test_loads_windows_utf8_bom_config(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_dir = root / "config"
            config_dir.mkdir(parents=True)
            config_path = config_dir / "local_6gb.json"
            config_path.write_text(json.dumps(sample_config()), encoding="utf-8-sig")

            settings = load_settings(config_path)

            self.assertEqual(settings.runtime.name, "test")
            self.assertEqual(settings.assets.raw, (root / "assets" / "raw").resolve())


def sample_config() -> dict[str, object]:
    return {
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


if __name__ == "__main__":
    unittest.main()
