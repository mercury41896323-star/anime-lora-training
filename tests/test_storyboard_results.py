from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from anime_studio.character_profile import create_character_profile
from anime_studio.settings import load_settings
from anime_studio.storyboard import add_shot, create_storyboard
from anime_studio.storyboard_results import (
    link_comfyui_results_to_storyboard,
    link_shot_result,
    list_shot_results,
)


class StoryboardResultsTest(unittest.TestCase):
    def test_links_manual_result_to_shot(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = write_settings(root)
            create_storyboard(settings, "pilot_scene", "Pilot Scene")
            add_shot(settings, "pilot_scene", "shot_001", "Opening")
            result_file = root / "outputs" / "manual" / "opening.png"
            result_file.parent.mkdir(parents=True)
            result_file.write_bytes(b"image")

            linked = link_shot_result(
                settings=settings,
                story_id="pilot_scene",
                shot_id="shot_001",
                result_path=result_file,
            )

            results = list_shot_results(settings, "pilot_scene")
            self.assertEqual(len(linked.linked), 1)
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].shot_id, "shot_001")
            self.assertEqual(results[0].stored_path, "outputs/manual/opening.png")
            self.assertTrue(linked.manifest_path.exists())

    def test_links_imported_comfyui_result_using_workflow_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = write_settings(root)
            create_character_profile(settings, "sample_hero", "Sample Hero")
            create_storyboard(settings, "pilot_scene", "Pilot Scene")
            add_shot(
                settings=settings,
                story_id="pilot_scene",
                shot_id="shot_001",
                title="Opening",
                character_id="sample_hero",
            )
            write_storyboard_workflow(root)
            write_queue(root)
            write_imported_results(root)

            linked = link_comfyui_results_to_storyboard(settings, "job-1")
            linked_again = link_comfyui_results_to_storyboard(settings, "job-1")

            results = list_shot_results(settings, "pilot_scene", "shot_001")
            self.assertEqual(len(linked.linked), 1)
            self.assertEqual(linked_again.skipped_count, 1)
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].source, "comfyui_result")
            self.assertEqual(results[0].job_id, "job-1")
            self.assertEqual(results[0].prompt_id, "prompt-1")
            self.assertEqual(results[0].node_id, "8")
            self.assertEqual(
                results[0].stored_path,
                "assets/processed/characters/sample_hero/generated/comfyui/job-1/sample.png",
            )


def write_storyboard_workflow(root: Path) -> None:
    workflow_path = root / "outputs" / "comfyui" / "storyboards" / "pilot_scene" / "001_shot_001.json"
    workflow_path.parent.mkdir(parents=True)
    workflow_path.write_text(
        json.dumps(
            {
                "meta": {
                    "story_id": "pilot_scene",
                    "shot_id": "shot_001",
                    "shot_character_id": "sample_hero",
                }
            }
        ),
        encoding="utf-8",
    )


def write_queue(root: Path) -> None:
    queue_path = root / "queues" / "comfyui" / "jobs.json"
    queue_path.parent.mkdir(parents=True)
    queue_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "queue_type": "comfyui_workflow_queue",
                "jobs": [
                    {
                        "job_id": "job-1",
                        "status": "completed",
                        "workflow_path": "outputs/comfyui/storyboards/pilot_scene/001_shot_001.json",
                        "comfyui_base_url": "http://127.0.0.1:8188",
                        "prompt_id": "prompt-1",
                        "response": {},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def write_imported_results(root: Path) -> None:
    results_path = (
        root
        / "assets"
        / "processed"
        / "characters"
        / "sample_hero"
        / "generated"
        / "comfyui"
        / "job-1"
        / "results.json"
    )
    results_path.parent.mkdir(parents=True)
    results_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "manifest_type": "comfyui_imported_results",
                "character_id": "sample_hero",
                "job_id": "job-1",
                "prompt_id": "prompt-1",
                "results": [
                    {
                        "job_id": "job-1",
                        "prompt_id": "prompt-1",
                        "source_reference": "output:sample.png",
                        "stored_path": "assets/processed/characters/sample_hero/generated/comfyui/job-1/sample.png",
                        "node_id": "8",
                        "kind": "image",
                        "size_bytes": 5,
                    }
                ],
            }
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
