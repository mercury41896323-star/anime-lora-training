from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from anime_studio.character_2p5d_definition import generate_character_2p5d_definition
from anime_studio.character_manager import register_character_asset
from anime_studio.character_profile import create_character_profile, load_character_profile
from anime_studio.kohya_config import KohyaLowVramSettings, generate_kohya_low_vram_config
from anime_studio.settings import load_settings


class LearningArchitectureTest(unittest.TestCase):
    def test_builds_2p5d_from_external_profile_images_before_lora(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = write_settings(root)
            create_character_profile(settings, "external_hero", "External Hero")
            front = root / "assets" / "raw" / "external_front.png"
            side = root / "assets" / "raw" / "external_side.png"
            front.parent.mkdir(parents=True)
            Image.new("RGB", (512, 512), color=(120, 160, 200)).save(front)
            Image.new("RGB", (512, 512), color=(100, 140, 180)).save(side)
            front.with_suffix(".txt").write_text(
                "external_hero, front, portrait\n", encoding="utf-8"
            )
            side.with_suffix(".txt").write_text(
                "external_hero, side, portrait\n", encoding="utf-8"
            )
            front_asset = register_character_asset(settings, "external_hero", front)
            side_asset = register_character_asset(settings, "external_hero", side)
            self.assertTrue(Path(front_asset.stored_path).with_suffix(".txt").exists())
            self.assertTrue(Path(side_asset.stored_path).with_suffix(".txt").exists())

            definition = generate_character_2p5d_definition(settings, "external_hero")
            definition_data = json.loads(definition.manifest_path.read_text(encoding="utf-8"))
            profile = load_character_profile(settings, "external_hero")

            self.assertEqual(definition_data["source_kind"], "character_profile")
            self.assertEqual(definition_data["definition_status"], "ready")
            self.assertGreaterEqual(len(definition_data["identity_reference_images"]), 2)
            self.assertEqual(profile.definition_2p5d, "manifests/characters/external_hero/character_2p5d_definition.json")
            self.assertEqual(profile.learning_strategy, "2p5d_base_lora_completion")

            dataset_dir = root / "datasets" / "lora" / "external_hero" / "video_external_clean"
            images_dir = dataset_dir / "images"
            images_dir.mkdir(parents=True)
            Image.new("RGB", (512, 512), color=(130, 170, 210)).save(images_dir / "frame.png")
            (images_dir / "frame.txt").write_text("external_hero, front\n", encoding="utf-8")
            result = generate_kohya_low_vram_config(
                settings=settings,
                character_id="external_hero",
                kohya_settings=KohyaLowVramSettings(
                    pretrained_model_name_or_path="models/sd15.safetensors"
                ),
                dataset_dir=dataset_dir,
                require_2p5d=True,
            )
            training_config = result.training_config.read_text(encoding="utf-8")
            self.assertIn("2p5d_residual_completion", training_config)
            self.assertIn("character_2p5d_definition.json", training_config)

    def test_blocks_final_lora_config_without_ready_2p5d(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = write_settings(root)
            create_character_profile(settings, "blocked_hero", "Blocked Hero")
            dataset_dir = root / "datasets" / "lora" / "blocked_hero" / "clean"
            images_dir = dataset_dir / "images"
            images_dir.mkdir(parents=True)
            (images_dir / "frame.png").write_bytes(b"image")
            (images_dir / "frame.txt").write_text("blocked_hero\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "ready character_2p5d_definition"):
                generate_kohya_low_vram_config(
                    settings=settings,
                    character_id="blocked_hero",
                    kohya_settings=KohyaLowVramSettings(
                        pretrained_model_name_or_path="models/sd15.safetensors"
                    ),
                    dataset_dir=dataset_dir,
                    require_2p5d=True,
                )


def write_settings(root: Path):
    config_dir = root / "config"
    config_dir.mkdir(parents=True)
    config_path = config_dir / "local_6gb.json"
    config_path.write_text(
        json.dumps(
            {
                "runtime": {"name": "test", "max_vram_gb": 6.0, "target_gpu_utilization": 0.8, "target_gpu_temp_c": 60},
                "assets": {"raw_dir": "assets/raw", "processed_dir": "assets/processed"},
                "datasets": {"lora_dir": "datasets/lora"},
                "models": {"wd14_dir": "models/wd14"},
                "asset_types": {"image_extensions": [".png"], "video_extensions": [".mp4"]},
            }
        ),
        encoding="utf-8",
    )
    return load_settings(config_path)


if __name__ == "__main__":
    unittest.main()
