from __future__ import annotations

from pathlib import Path
import json
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from anime_studio.character_profile import create_character_profile
from anime_studio.comfyui_workflow_export import (
    export_comfyui_workflow,
    list_comfyui_templates,
)
from anime_studio.lora_manifest import generate_lora_manifest
from anime_studio.lora_registry import register_lora_result
from anime_studio.settings import load_settings


class ComfyWorkflowExportTest(unittest.TestCase):
    def test_exports_template_with_lora_manifest_values(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = write_settings(root)
            create_character_profile(
                settings,
                "sample_hero",
                "Sample Hero",
                trigger_tags=["sample_hero"],
            )
            register_lora_result(
                settings=settings,
                character_id="sample_hero",
                model_path="outputs/lora/sample_hero/sample_hero_v1.safetensors",
                display_name="Sample Hero v1",
            )
            generate_lora_manifest(settings, "sample_hero", default_weight=0.6)
            template_path = root / "templates" / "comfyui" / "draft.json"
            template_path.parent.mkdir(parents=True)
            template_path.write_text(
                json.dumps(sample_workflow_template()),
                encoding="utf-8-sig",
            )

            result = export_comfyui_workflow(
                settings=settings,
                character_id="sample_hero",
                template_path=template_path,
            )

            workflow = json.loads(result.workflow_path.read_text(encoding="utf-8"))
            lora_inputs = workflow["2"]["inputs"]
            prompt = workflow["3"]["inputs"]["text"]
            self.assertEqual(result.lora_name, "sample_hero_v1.safetensors")
            self.assertEqual(result.template_path, template_path)
            self.assertEqual(lora_inputs["lora_name"], "sample_hero_v1.safetensors")
            self.assertEqual(lora_inputs["strength_model"], 0.6)
            self.assertEqual(lora_inputs["strength_clip"], 0.6)
            self.assertEqual(prompt, "masterpiece, sample_hero")
            self.assertEqual(workflow["meta"]["character_id"], "sample_hero")
            self.assertEqual(
                result.workflow_path,
                root / "outputs" / "comfyui" / "sample_hero" / "draft_with_lora.json",
            )

    def test_exports_with_default_template_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = write_settings(root)
            create_character_profile(
                settings,
                "default_hero",
                "Default Hero",
                trigger_tags=["default_hero"],
            )
            register_lora_result(
                settings=settings,
                character_id="default_hero",
                model_path="outputs/lora/default_hero/default_hero_v1.safetensors",
                display_name="Default Hero v1",
            )
            template_path = root / "templates" / "comfyui" / "sd15_lora_txt2img_512.json"
            template_path.parent.mkdir(parents=True)
            template_path.write_text(
                (ROOT / "templates" / "comfyui" / "sd15_lora_txt2img_512.json").read_text(
                    encoding="utf-8"
                ),
                encoding="utf-8",
            )

            result = export_comfyui_workflow(
                settings=settings,
                character_id="default_hero",
            )

            workflow = json.loads(result.workflow_path.read_text(encoding="utf-8"))
            self.assertEqual(result.template_path, template_path)
            self.assertEqual(workflow["2"]["inputs"]["lora_name"], "default_hero_v1.safetensors")
            self.assertEqual(workflow["2"]["inputs"]["strength_model"], 0.75)
            self.assertEqual(workflow["3"]["inputs"]["text"], "masterpiece, best quality, anime style, default_hero")
            self.assertEqual(workflow["8"]["inputs"]["filename_prefix"], "anime_studio/default_hero/default_hero_v1")
            self.assertEqual(
                result.workflow_path,
                root / "outputs" / "comfyui" / "default_hero" / "sd15_lora_txt2img_512_with_lora.json",
            )

    def test_lists_bundled_templates(self) -> None:
        settings = load_settings(ROOT / "config" / "local_6gb.json")

        templates = list_comfyui_templates(settings)

        self.assertIn(
            ROOT / "templates" / "comfyui" / "sd15_lora_txt2img_512.json",
            templates,
        )


def sample_workflow_template() -> dict[str, object]:
    return {
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": "sd15.safetensors"},
        },
        "2": {
            "class_type": "LoraLoader",
            "inputs": {
                "model": ["1", 0],
                "clip": ["1", 1],
                "lora_name": "placeholder.safetensors",
                "strength_model": 1.0,
                "strength_clip": 1.0,
            },
        },
        "3": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": "masterpiece, {{positive_prompt_tags}}"},
        },
        "meta": {
            "character_id": "{{character_id}}",
            "lora_path": "{{lora_model_path}}",
        },
    }


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
