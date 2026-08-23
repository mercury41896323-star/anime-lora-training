from __future__ import annotations

from pathlib import Path
import json
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from anime_studio.character_manager import register_character_asset
from anime_studio.character_profile import create_character_profile, load_character_profile
from anime_studio.kohya_config import KohyaLowVramSettings, generate_kohya_low_vram_config
from anime_studio.settings import load_settings
from anime_studio.tagger import generate_auto_tag_records


class KohyaConfigTest(unittest.TestCase):
    def test_generates_low_vram_kohya_files(self) -> None:
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
            generate_auto_tag_records(settings, "sample_hero")

            result = generate_kohya_low_vram_config(
                settings=settings,
                character_id="sample_hero",
                kohya_settings=KohyaLowVramSettings(
                    pretrained_model_name_or_path="models/sd15.safetensors",
                    kohya_root="C:/tools/sd-scripts",
                    max_train_epochs=3,
                ),
            )

            dataset_toml = result.dataset_config.read_text(encoding="utf-8")
            training_toml = result.training_config.read_text(encoding="utf-8")
            run_script = result.run_script.read_text(encoding="utf-8")

            self.assertEqual(result.dataset_image_count, 1)
            self.assertIn("enable_bucket = true", dataset_toml)
            self.assertIn("batch_size = 1", dataset_toml)
            self.assertIn("class_tokens = 'sample_hero'", dataset_toml)
            self.assertIn("profile = 'low_vram_rtx3050_6gb'", training_toml)
            self.assertIn("gradient_checkpointing", training_toml)
            self.assertIn("& 'accelerate' 'launch'", run_script)
            self.assertIn("'--dataset_config'", run_script)

            profile = load_character_profile(settings, "sample_hero")
            self.assertEqual(len(profile.lora_artifacts), 1)
            artifact = profile.lora_artifacts[0]
            self.assertEqual(artifact.artifact_id, "kohya_low_vram_config")
            self.assertEqual(artifact.kind, "kohya_config")
            self.assertEqual(artifact.status, "configured")
            self.assertEqual(artifact.dataset_config, "config/kohya/sample_hero/dataset.toml")
            self.assertEqual(artifact.trigger_tags, ["sample_hero"])
            self.assertEqual(artifact.metadata["dataset_image_count"], 1)

    def test_uses_clean_video_dataset_override(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = write_settings(root)
            create_character_profile(settings, "clean_hero", "Clean Hero", trigger_tags=["clean_hero"])
            clean_dataset = root / "datasets" / "lora" / "clean_hero" / "video_scene01_clean"
            images_dir = clean_dataset / "images"
            images_dir.mkdir(parents=True)
            (images_dir / "frame_001.png").write_bytes(b"image")
            (images_dir / "frame_001.txt").write_text("clean_hero, front\n", encoding="utf-8")

            result = generate_kohya_low_vram_config(
                settings=settings,
                character_id="clean_hero",
                kohya_settings=KohyaLowVramSettings(
                    pretrained_model_name_or_path="models/sd15.safetensors",
                ),
                dataset_dir=clean_dataset,
            )

            dataset_toml = result.dataset_config.read_text(encoding="utf-8")
            training_toml = result.training_config.read_text(encoding="utf-8")
            self.assertEqual(result.dataset_image_count, 1)
            self.assertIn(str(images_dir), dataset_toml)
            self.assertIn(str(clean_dataset), training_toml)


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
