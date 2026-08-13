from __future__ import annotations

from pathlib import Path
import json
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from anime_studio.character_profile import create_character_profile, load_character_profile
from anime_studio.lora_registry import register_lora_result
from anime_studio.settings import load_settings


class LoraRegistryTest(unittest.TestCase):
    def test_registers_trained_lora_result_in_profile(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = write_settings(root)
            create_character_profile(
                settings,
                "sample_hero",
                "Sample Hero",
                trigger_tags=["sample_hero"],
            )

            result = register_lora_result(
                settings=settings,
                character_id="sample_hero",
                model_path="outputs/lora/sample_hero/sample_hero_v1.safetensors",
                source_config_dir="config/kohya/sample_hero",
                display_name="Sample Hero v1",
                notes="First low-VRAM training result.",
            )

            profile = load_character_profile(settings, "sample_hero")
            self.assertEqual(result.profile_path, root / "assets" / "processed" / "characters" / "sample_hero" / "profile.json")
            self.assertEqual(profile.lora_files, ["outputs/lora/sample_hero/sample_hero_v1.safetensors"])
            self.assertEqual(len(profile.lora_artifacts), 1)
            artifact = profile.lora_artifacts[0]
            self.assertEqual(artifact.artifact_id, "sample_hero_v1")
            self.assertEqual(artifact.kind, "trained_lora")
            self.assertEqual(artifact.status, "trained")
            self.assertEqual(artifact.display_name, "Sample Hero v1")
            self.assertEqual(artifact.config_dir, "config/kohya/sample_hero")
            self.assertEqual(artifact.model_path, "outputs/lora/sample_hero/sample_hero_v1.safetensors")
            self.assertEqual(artifact.trigger_tags, ["sample_hero"])


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
