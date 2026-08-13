from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from anime_studio.character_profile import create_character_profile
from anime_studio.comfyui_results import import_comfyui_results
from anime_studio.settings import load_settings


class ComfyUIResultsTest(unittest.TestCase):
    def test_imports_comfyui_history_images_into_character_assets(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = write_settings(root)
            create_character_profile(settings, "sample_hero", "Sample Hero")
            source_dir = root / "comfyui_output" / "anime_studio"
            source_dir.mkdir(parents=True)
            source_image = source_dir / "sample.png"
            source_image.write_bytes(b"generated-image")
            write_queue(root)

            result = import_comfyui_results(
                settings=settings,
                character_id="sample_hero",
                job_id="job-1",
                comfyui_output_dir=source_dir.parent,
            )

            self.assertEqual(len(result.imported), 1)
            stored_path = root / result.imported[0].stored_path
            self.assertTrue(stored_path.exists())
            self.assertEqual(stored_path.read_bytes(), b"generated-image")
            self.assertTrue(result.results_manifest_path.exists())
            assets = json.loads(result.assets_manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(assets["assets"][0]["source"], "comfyui_result")
            self.assertEqual(assets["assets"][0]["metadata"]["prompt_id"], "prompt-1")
            self.assertEqual(assets["assets"][0]["metadata"]["node_id"], "8")

    def test_metadata_only_import_records_missing_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = write_settings(root)
            create_character_profile(settings, "sample_hero", "Sample Hero")
            write_queue(root)

            result = import_comfyui_results(
                settings=settings,
                character_id="sample_hero",
                job_id="job-1",
                comfyui_output_dir=root / "missing_comfyui_output",
                metadata_only=True,
            )

            self.assertEqual(result.imported[0].stored_path, "")
            self.assertEqual(result.imported[0].size_bytes, 0)
            assets = json.loads(result.assets_manifest_path.read_text(encoding="utf-8"))
            self.assertTrue(assets["assets"][0]["metadata"]["metadata_only"])


def write_queue(root: Path) -> Path:
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
                        "workflow_path": "outputs/comfyui/sample/workflow.json",
                        "comfyui_base_url": "http://127.0.0.1:8188",
                        "prompt_id": "prompt-1",
                        "response": {
                            "prompt-1": {
                                "outputs": {
                                    "8": {
                                        "images": [
                                            {
                                                "filename": "sample.png",
                                                "subfolder": "anime_studio",
                                                "type": "output",
                                            }
                                        ]
                                    }
                                }
                            }
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return queue_path


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
