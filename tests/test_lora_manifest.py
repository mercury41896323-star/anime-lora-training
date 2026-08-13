from __future__ import annotations

from pathlib import Path
import json
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from anime_studio.character_profile import create_character_profile
from anime_studio.lora_manifest import generate_lora_manifest
from anime_studio.lora_registry import link_kohya_config, register_lora_result
from anime_studio.settings import load_settings


class LoraManifestTest(unittest.TestCase):
    def test_generates_comfyui_unity_manifest_from_trained_loras(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = write_settings(root)
            create_character_profile(
                settings,
                "sample_hero",
                "Sample Hero",
                trigger_tags=["sample_hero"],
            )
            link_kohya_config(
                settings=settings,
                character_id="sample_hero",
                config_dir=root / "config" / "kohya" / "sample_hero",
                dataset_config=root / "config" / "kohya" / "sample_hero" / "dataset.toml",
                training_config=root / "config" / "kohya" / "sample_hero" / "train_low_vram.toml",
                run_script=root / "config" / "kohya" / "sample_hero" / "run_train.ps1",
                output_name="sample_hero_lora",
                dataset_image_count=4,
                trigger_tags=["sample_hero"],
            )
            register_lora_result(
                settings=settings,
                character_id="sample_hero",
                model_path="outputs/lora/sample_hero/sample_hero_v1.safetensors",
                source_config_dir="config/kohya/sample_hero",
                display_name="Sample Hero v1",
                notes="Ready for draft shots.",
            )

            result = generate_lora_manifest(
                settings=settings,
                character_id="sample_hero",
                default_weight=0.65,
            )

            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(result.lora_count, 1)
            self.assertEqual(manifest["manifest_type"], "character_lora_manifest")
            self.assertEqual(manifest["character"]["character_id"], "sample_hero")
            self.assertEqual(manifest["defaults"]["weight"], 0.65)
            self.assertEqual(manifest["loras"][0]["artifact_id"], "sample_hero_v1")
            self.assertEqual(manifest["loras"][0]["prompt_tag"], "sample_hero")
            self.assertEqual(manifest["loras"][0]["comfyui"]["lora_name"], "sample_hero_v1.safetensors")
            self.assertEqual(manifest["loras"][0]["unity"]["addressable_key"], "lora/sample_hero/sample_hero_v1")
            self.assertEqual(manifest["comfyui"]["positive_prompt_tags"], ["sample_hero"])
            self.assertEqual(manifest["unity"]["addressable_keys"], ["lora/sample_hero/sample_hero_v1"])


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
