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
from anime_studio.settings import load_settings
from anime_studio.storyboard import add_shot, create_storyboard
from anime_studio.storyboard_comfyui import export_storyboard_comfyui_workflows


class StoryboardComfyUITest(unittest.TestCase):
    def test_exports_one_workflow_per_character_shot(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = write_settings(root)
            write_template(root)
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
            create_storyboard(settings, "pilot_scene", "Pilot Scene")
            add_shot(
                settings=settings,
                story_id="pilot_scene",
                shot_id="shot_001",
                title="Opening close-up",
                character_id="sample_hero",
                prompt="sample_hero, close-up, hopeful smile",
                negative_prompt="blurry, low quality",
                camera="close-up",
                lighting="soft morning light",
                seed=12345,
                width=640,
                height=384,
                steps=18,
            )
            add_shot(
                settings=settings,
                story_id="pilot_scene",
                shot_id="shot_002",
                title="Unassigned cutaway",
            )

            result = export_storyboard_comfyui_workflows(settings, "pilot_scene")

            self.assertEqual(len(result.workflows), 1)
            self.assertEqual(len(result.skipped_shots), 1)
            self.assertEqual(result.workflows[0].shot_id, "shot_001")
            self.assertEqual(
                result.workflows[0].workflow_path,
                "outputs/comfyui/storyboards/pilot_scene/001_shot_001.json",
            )
            workflow_path = root / result.workflows[0].workflow_path
            workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
            prompt = workflow["3"]["inputs"]["text"]
            self.assertIn("sample_hero", prompt)
            self.assertIn("hopeful smile", prompt)
            self.assertIn("close-up", prompt)
            self.assertIn("soft morning light", prompt)
            self.assertIn("blurry", workflow["4"]["inputs"]["text"])
            self.assertEqual(workflow["6"]["inputs"]["seed"], 12345)
            self.assertEqual(workflow["6"]["inputs"]["steps"], 18)
            self.assertEqual(workflow["5"]["inputs"]["width"], 640)
            self.assertEqual(workflow["5"]["inputs"]["height"], 384)
            self.assertEqual(
                workflow["8"]["inputs"]["filename_prefix"],
                "anime_studio/storyboards/pilot_scene/001_shot_001",
            )
            self.assertEqual(workflow["meta"]["story_id"], "pilot_scene")
            self.assertEqual(workflow["meta"]["shot_id"], "shot_001")
            self.assertEqual(workflow["meta"]["shot_seed"], 12345)
            self.assertTrue(result.manifest_path.exists())

    def test_can_enqueue_exported_workflows(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = write_settings(root)
            write_template(root)
            create_character_profile(settings, "sample_hero", "Sample Hero")
            register_lora_result(
                settings=settings,
                character_id="sample_hero",
                model_path="outputs/lora/sample_hero/sample_hero_v1.safetensors",
            )
            create_storyboard(settings, "pilot_scene", "Pilot Scene")
            add_shot(
                settings=settings,
                story_id="pilot_scene",
                shot_id="shot_001",
                title="Opening",
                character_id="sample_hero",
            )

            result = export_storyboard_comfyui_workflows(
                settings,
                "pilot_scene",
                enqueue=True,
            )

            queue_path = root / "queues" / "comfyui" / "jobs.json"
            queue = json.loads(queue_path.read_text(encoding="utf-8"))
            self.assertEqual(len(queue["jobs"]), 1)
            self.assertEqual(result.workflows[0].queued_job_id, queue["jobs"][0]["job_id"])


def write_template(root: Path) -> None:
    template_path = root / "templates" / "comfyui" / "sd15_lora_txt2img_512.json"
    template_path.parent.mkdir(parents=True)
    template_path.write_text(
        (ROOT / "templates" / "comfyui" / "sd15_lora_txt2img_512.json").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )


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
