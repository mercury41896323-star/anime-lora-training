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
from anime_studio.simple_2p5d_rig import build_simple_2p5d_rig_pipeline


class Simple2p5DRigTest(unittest.TestCase):
    def test_builds_sheet_to_rig_controls_workflow_and_live2d_bridge(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = write_settings(root)
            sheet = root / "hiiragi_sheet.png"
            image = Image.new("RGB", (1347, 1168), (239, 235, 226))
            draw = ImageDraw.Draw(image)
            draw.ellipse((555, 70, 620, 145), fill=(184, 160, 120), outline=(40, 40, 40), width=3)
            draw.rectangle((568, 140, 608, 430), fill=(45, 48, 47), outline=(20, 20, 20), width=3)
            draw.rectangle((555, 175, 568, 360), fill=(224, 190, 170))
            draw.rectangle((608, 175, 621, 360), fill=(224, 190, 170))
            draw.rectangle((570, 430, 586, 475), fill=(35, 35, 35))
            draw.rectangle((592, 430, 608, 475), fill=(35, 35, 35))
            image.save(sheet)
            comfyui_input = root / "comfyui_input"

            result = build_simple_2p5d_rig_pipeline(
                settings=settings,
                character_id="hiiragi_yukikaze",
                display_name="柊 雪風",
                sheet_image=sheet,
                profile_overrides={
                    "identity": {"age": "16", "height_cm": 158},
                    "visual_identity": {"eye_colors": ["orange"]},
                },
                comfyui_input_dir=comfyui_input,
                lora_name="hiiragi_yukikaze.safetensors",
                openpose_controlnet_name="control_openpose.pth",
                depth_controlnet_name="control_depth.pth",
            )

            pipeline = json.loads(result.pipeline_manifest_path.read_text(encoding="utf-8"))
            master = json.loads(result.master_manifest_path.read_text(encoding="utf-8"))
            definition = json.loads(result.definition_path.read_text(encoding="utf-8"))
            rig = json.loads(result.rig_path.read_text(encoding="utf-8"))
            controls = json.loads(result.control_bundle_path.read_text(encoding="utf-8"))
            workflow = json.loads(result.workflow_path.read_text(encoding="utf-8"))
            live2d = json.loads(result.live2d_bridge_path.read_text(encoding="utf-8"))
            profile = load_character_profile(settings, "hiiragi_yukikaze")

            self.assertEqual(master["template"], "simple_2p5d_v1")
            self.assertEqual(len(master["section_assets"]), 35)
            self.assertEqual(rig["manifest_type"], "simple_2p5d_rig")
            self.assertEqual(len(rig["parts"]), 12)
            self.assertTrue(definition["simple_2p5d_rig"]["pose_image"].endswith("pose.png"))
            self.assertTrue(definition["generation_binding"]["comfyui"]["simple_2p5d_workflow"].endswith(".json"))
            self.assertTrue(result.primary_reference_path.exists())
            self.assertTrue(result.workflow_ready)
            self.assertTrue((comfyui_input / "anime_studio" / "hiiragi_yukikaze" / "pose.png").exists())
            self.assertEqual(controls["generation_stack"]["pose"]["strength"], 1.0)
            self.assertTrue(all(controls["readiness"].values()))
            self.assertEqual(workflow["6"]["class_type"], "ControlNetLoader")
            self.assertEqual(len(live2d["art_meshes"]), 12)
            self.assertEqual(profile.profile_data["identity"]["height_cm"], 158)
            self.assertTrue(profile.rig_2p5d.endswith("simple_2p5d_rig.json"))
            self.assertEqual(pipeline["steps"][-1]["status"], "ready")

            with Image.open(root / rig["parts"][0]["transparent_image"]) as part:
                self.assertEqual(part.mode, "RGBA")

            with Image.open(root / definition["simple_2p5d_rig"]["pose_image"]) as pose:
                self.assertEqual(pose.size, (512, 768))
            with Image.open(root / definition["simple_2p5d_rig"]["silhouette_mask"]) as mask:
                bounds = mask.getbbox()
                self.assertIsNotNone(bounds)
                self.assertGreaterEqual(bounds[1], 50)
                self.assertLessEqual(bounds[3], 720)

            self.assertIn("head fully visible", workflow["3"]["inputs"]["text"])
            self.assertIn("cropped head", workflow["4"]["inputs"]["text"])
            self.assertIn("one character only", workflow["3"]["inputs"]["text"])
            self.assertIn("character sheet", workflow["4"]["inputs"]["text"])


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
