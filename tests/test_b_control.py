from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from anime_studio.character_profile import create_character_profile
from anime_studio.lora_registry import register_lora_result
from anime_studio.phase6_pipeline import add_motion_cue
from anime_studio.settings import load_settings
from anime_studio.storyboard import add_shot, create_storyboard
from anime_studio.storyboard_comfyui import export_storyboard_comfyui_workflows
from anime_studio.storyboard_editor_manifest import export_selected_shot_manifest
from anime_studio.storyboard_production import set_camera_work, set_lighting_setup
from anime_studio.storyboard_results import link_shot_result
from anime_studio.storyboard_review import set_shot_result_decision


class BControlTest(unittest.TestCase):
    def test_exports_b_control_manifest_and_workflow_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = write_settings(root)
            write_template(root)
            create_character_profile(settings, "sample_hero", "Sample Hero", trigger_tags=["sample_hero"])
            write_character_definition(root)
            write_simple_2p5d_workflow(root)
            register_lora_result(
                settings=settings,
                character_id="sample_hero",
                model_path="outputs/lora/sample_hero/sample_hero_v1.safetensors",
                display_name="Sample Hero v1",
            )
            create_storyboard(settings, "pilot_scene", "Pilot Scene")
            add_shot(
                settings=settings,
                story_id="pilot_scene",
                shot_id="shot_001",
                title="Face turn",
                character_id="sample_hero",
                prompt="sample_hero, hopeful smile, three-quarter view",
                camera="close-up",
                lighting="soft rim light",
            )
            set_camera_work(
                settings=settings,
                story_id="pilot_scene",
                shot_id="shot_001",
                framing="close-up",
                movement="slow turn reveal",
                angle="three-quarter view",
            )
            set_lighting_setup(
                settings=settings,
                story_id="pilot_scene",
                shot_id="shot_001",
                key_light="soft front light",
                rim_light="gentle rim light",
            )
            add_motion_cue(
                settings=settings,
                story_id="pilot_scene",
                shot_id="shot_001",
                target="sample_hero",
                motion="face turn",
                source="motion_library",
                duration_seconds=1.2,
            )
            selected_image = root / "outputs" / "manual" / "shot_001.png"
            selected_image.parent.mkdir(parents=True, exist_ok=True)
            selected_image.write_bytes(b"image")
            linked = link_shot_result(settings, "pilot_scene", "shot_001", selected_image)
            set_shot_result_decision(settings, "pilot_scene", linked.linked[0].result_id, "selected")
            export_selected_shot_manifest(settings, "pilot_scene")

            result = export_storyboard_comfyui_workflows(
                settings=settings,
                story_id="pilot_scene",
                b_control=True,
            )

            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            workflow = json.loads((root / result.workflows[0].workflow_path).read_text(encoding="utf-8"))
            b_control_manifest = json.loads(result.b_control_manifest_path.read_text(encoding="utf-8"))

            self.assertEqual(manifest["generation_mode"], "B-control")
            self.assertEqual(manifest["workflow_modes"], ["simple_2p5d_face_repair"])
            self.assertEqual(result.workflows[0].workflow_mode, "simple_2p5d_face_repair")
            self.assertTrue(result.b_control_manifest_path.exists())
            self.assertEqual(b_control_manifest["manifest_type"], "storyboard_b_control_manifest")
            self.assertEqual(b_control_manifest["shots"][0]["controls"]["face_direction"], "three_quarter")
            self.assertEqual(workflow["meta"]["generation_mode"], "B-control")
            self.assertEqual(workflow["meta"]["b_control"]["controls"]["motion_intents"][0]["motion"], "face turn")
            self.assertEqual(
                workflow["meta"]["character_2p5d_definition"]["selected_view_anchor"]["view"],
                "three_quarter",
            )
            self.assertEqual(
                b_control_manifest["shots"][0]["controls"]["reference_images"][0],
                "assets/processed/characters/sample_hero/character_sheet/source/master/face_angle_45.png",
            )
            self.assertIn("B-control guided generation", workflow["3"]["inputs"]["text"])
            self.assertIn("2.5D character master identity", workflow["3"]["inputs"]["text"])
            self.assertEqual(workflow["18"]["class_type"], "SaveImage")
            self.assertTrue(workflow["18"]["inputs"]["filename_prefix"].endswith("_face_repaired"))


def write_template(root: Path) -> None:
    template_path = root / "templates" / "comfyui" / "sd15_lora_txt2img_512.json"
    template_path.parent.mkdir(parents=True)
    template_path.write_text(
        (ROOT / "templates" / "comfyui" / "sd15_lora_txt2img_512.json").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )


def write_character_definition(root: Path) -> None:
    path = root / "manifests" / "characters" / "sample_hero" / "character_2p5d_definition.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "manifest_type": "character_2p5d_definition",
                "definition_status": "ready",
                "source_master_asset": "manifests/characters/sample_hero/character_sheet/character_master_asset.json",
                "identity_reference_images": [
                    "assets/processed/characters/sample_hero/character_sheet/source/master/main_portrait.png"
                ],
                "view_anchors": [
                    {
                        "view": "three_quarter",
                        "status": "ready",
                        "reference_image": "assets/processed/characters/sample_hero/character_sheet/source/master/face_angle_45.png",
                    }
                ],
                "expression_controls": [],
                "body_controls": [],
                "generation_binding": {
                    "video_control": {"preserve_across_frames": True}
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )


def write_simple_2p5d_workflow(root: Path) -> None:
    output_path = root / "outputs" / "comfyui" / "sample_hero" / "simple_2p5d_control_workflow.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(
            {
                "2": {"class_type": "LoraLoader", "inputs": {"lora_name": "sample_hero_v1.safetensors"}},
                "3": {"class_type": "CLIPTextEncode", "inputs": {"text": "sample_hero"}},
                "4": {"class_type": "CLIPTextEncode", "inputs": {"text": "low quality"}},
                "11": {"class_type": "EmptyLatentImage", "inputs": {"width": 512, "height": 768}},
                "12": {
                    "class_type": "KSampler",
                    "inputs": {"seed": 1, "steps": 20, "positive": ["3", 0], "negative": ["4", 0]},
                },
                "14": {"class_type": "SaveImage", "inputs": {"filename_prefix": "sample_hero", "images": ["13", 0]}},
                "17": {
                    "class_type": "ImageCompositeMasked",
                    "inputs": {"destination": ["13", 0], "source": ["5", 0], "mask": ["16", 0]},
                },
                "18": {
                    "class_type": "SaveImage",
                    "inputs": {"filename_prefix": "sample_hero_face_repaired", "images": ["17", 0]},
                },
                "meta": {"face_repair": {"enabled": True}},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    readiness_path = root / "manifests" / "characters" / "sample_hero" / "simple_2p5d_generation_readiness.json"
    readiness_path.write_text(json.dumps({"ready": True}) + "\n", encoding="utf-8")


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
