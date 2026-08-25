from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from anime_studio.character_profile import load_character_profile
from anime_studio.settings import load_settings
from anime_studio.simple_2p5d_management import (
    approve_simple_2p5d_rig,
    bind_generation_lora,
    check_simple_2p5d_generation_readiness,
    inspect_simple_2p5d_rig,
)
from anime_studio.simple_2p5d_rig import build_simple_2p5d_rig_pipeline


class Simple2p5DManagementTest(unittest.TestCase):
    def test_requires_review_then_binds_exact_lora_and_becomes_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = write_settings(root)
            sheet = write_sheet(root)
            input_dir = root / "comfyui" / "input"
            controlnet_dir = root / "comfyui" / "models" / "controlnet"
            lora_dir = root / "comfyui" / "models" / "loras"
            controlnet_dir.mkdir(parents=True)
            lora_dir.mkdir(parents=True)
            (controlnet_dir / "openpose.safetensors").write_bytes(b"openpose")
            (controlnet_dir / "depth.safetensors").write_bytes(b"depth")

            build_simple_2p5d_rig_pipeline(
                settings=settings,
                character_id="managed_hero",
                display_name="Managed Hero",
                sheet_image=sheet,
                comfyui_input_dir=input_dir,
                openpose_controlnet_name="openpose.safetensors",
                depth_controlnet_name="depth.safetensors",
            )
            inspection = inspect_simple_2p5d_rig(settings, "managed_hero")
            self.assertEqual(inspection.status, "pending_review")
            self.assertEqual(inspection.issue_count, 0)

            blocked = check_simple_2p5d_generation_readiness(
                settings, "managed_hero", controlnet_dir, lora_dir, input_dir
            )
            blocked_data = json.loads(blocked.manifest_path.read_text(encoding="utf-8"))
            self.assertFalse(blocked.ready)
            self.assertIn("rig_not_approved", {item["code"] for item in blocked_data["issues"]})
            self.assertIn("missing_lora_binding", {item["code"] for item in blocked_data["issues"]})

            approved = approve_simple_2p5d_rig(
                settings, "managed_hero", reviewer="unit_test", notes="visual checks complete"
            )
            self.assertEqual(approved.status, "approved")
            (lora_dir / "managed_hero.safetensors").write_bytes(b"lora")
            bind_generation_lora(
                settings=settings,
                character_id="managed_hero",
                lora_name="managed_hero.safetensors",
                trigger_tag="managed_hero_token",
                comfyui_lora_dir=lora_dir,
                reviewer="unit_test",
            )

            ready = check_simple_2p5d_generation_readiness(
                settings, "managed_hero", controlnet_dir, lora_dir, input_dir
            )
            readiness = json.loads(ready.manifest_path.read_text(encoding="utf-8"))
            workflow = json.loads(
                (root / "outputs" / "comfyui" / "managed_hero" / "simple_2p5d_control_workflow.json").read_text(encoding="utf-8")
            )
            profile = load_character_profile(settings, "managed_hero")
            self.assertTrue(ready.ready)
            self.assertEqual(readiness["review_status"], "approved")
            self.assertEqual(workflow["2"]["inputs"]["lora_name"], "managed_hero.safetensors")
            self.assertTrue(workflow["3"]["inputs"]["text"].startswith("managed_hero_token,"))
            self.assertEqual(profile.profile_data["generation"]["selected_lora"], "managed_hero.safetensors")


def write_sheet(root: Path) -> Path:
    sheet = root / "managed_sheet.png"
    image = Image.new("RGB", (1347, 1168), (239, 235, 226))
    draw = ImageDraw.Draw(image)
    draw.ellipse((555, 70, 620, 145), fill=(184, 160, 120), outline=(40, 40, 40), width=3)
    draw.rectangle((568, 140, 608, 430), fill=(45, 48, 47), outline=(20, 20, 20), width=3)
    draw.rectangle((555, 175, 568, 360), fill=(224, 190, 170))
    draw.rectangle((608, 175, 621, 360), fill=(224, 190, 170))
    draw.rectangle((570, 430, 586, 475), fill=(35, 35, 35))
    draw.rectangle((592, 430, 608, 475), fill=(35, 35, 35))
    image.save(sheet)
    return sheet


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
