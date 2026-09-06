from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PIL import Image

from anime_studio.bernini_low_vram import assemble_bernini_segments, export_bernini_low_vram_shot
from anime_studio.character_profile import create_character_profile
from anime_studio.settings import load_settings
from anime_studio.storyboard import add_shot, create_storyboard


class BerniniLowVramTest(unittest.TestCase):
    def test_exports_segmented_reference_to_video_workflows(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = write_settings(root)
            create_character_profile(settings, "chiyoko", "Chiyoko")
            reference = write_identity_reference(root)
            write_definition(root, reference)
            create_storyboard(settings, "pilot_scene", "Pilot Scene")
            add_shot(
                settings=settings,
                story_id="pilot_scene",
                shot_id="shot_001",
                title="Chiyoko walks into the light",
                character_id="chiyoko",
                prompt="Chiyoko walks forward and looks at the camera",
                duration_seconds=10.0,
                camera="slow dolly in",
                lighting="soft morning light",
            )
            comfyui_input = root / "comfyui" / "input"
            comfyui_input.mkdir(parents=True)

            result = export_bernini_low_vram_shot(
                settings=settings,
                story_id="pilot_scene",
                shot_id="shot_001",
                comfyui_input_dir=comfyui_input,
                enqueue=True,
            )

            self.assertEqual(result.requested_duration_seconds, 10.0)
            self.assertEqual(len(result.segments), 8)
            self.assertTrue(result.comfyui_reference.exists())
            self.assertEqual(result.segments[0].frame_count, 17)
            workflow_path = root / result.segments[0].workflow_path
            workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
            self.assertEqual(workflow["1"]["class_type"], "UnetLoaderGGUF")
            self.assertEqual(workflow["1"]["inputs"]["unet_name"], "bernini_r_1.3B-Q4_K_M.gguf")
            self.assertEqual(workflow["10"]["inputs"]["length"], 17)
            self.assertEqual(workflow["10"]["inputs"]["width"], 512)
            self.assertEqual(workflow["16"]["class_type"], "VAEDecodeTiled")
            self.assertEqual(workflow["17"]["class_type"], "BerniniRSaveVideo")
            self.assertNotIn("LoraLoader", {node.get("class_type") for node in workflow.values()})
            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["maximum_duration_seconds"], 30.0)
            self.assertEqual(manifest["runtime_limits"]["max_vram_gb"], 5.25)
            queue = json.loads((root / "queues" / "comfyui" / "jobs.json").read_text(encoding="utf-8"))
            self.assertEqual(len(queue["jobs"]), 8)

    def test_rejects_duration_above_hard_limit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = write_settings(root)
            create_character_profile(settings, "chiyoko", "Chiyoko")
            reference = write_identity_reference(root)
            write_definition(root, reference)
            create_storyboard(settings, "pilot_scene", "Pilot Scene")
            add_shot(
                settings=settings,
                story_id="pilot_scene",
                shot_id="shot_001",
                title="Too long",
                character_id="chiyoko",
                duration_seconds=31.0,
            )
            comfyui_input = root / "comfyui" / "input"
            comfyui_input.mkdir(parents=True)

            with self.assertRaisesRegex(ValueError, "exceeds the low-VRAM limit"):
                export_bernini_low_vram_shot(
                    settings=settings,
                    story_id="pilot_scene",
                    shot_id="shot_001",
                    comfyui_input_dir=comfyui_input,
                )

    def test_assembles_imported_segments_and_trims_duration(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = write_settings(root)
            video = root / "assets" / "processed" / "characters" / "chiyoko" / "generated" / "comfyui" / "job-1" / "segment.mp4"
            video.parent.mkdir(parents=True)
            video.write_bytes(b"segment")
            (video.parent / "results.json").write_text(
                json.dumps({"results": [{"kind": "video", "stored_path": video.relative_to(root).as_posix()}]}),
                encoding="utf-8",
            )
            plan = root / "outputs" / "comfyui" / "bernini" / "shot" / "bernini_low_vram_plan.json"
            plan.parent.mkdir(parents=True)
            plan.write_text(
                json.dumps(
                    {
                        "manifest_type": "bernini_low_vram_generation_plan",
                        "character_id": "chiyoko",
                        "requested_duration_seconds": 1.0,
                        "segments": [{"index": 1, "queued_job_id": "job-1", "workflow_path": "segment_001.json"}],
                    }
                ),
                encoding="utf-8",
            )

            def fake_run(command, **kwargs):
                Path(command[-1]).write_bytes(b"assembled")
                return type("Completed", (), {"returncode": 0, "stdout": "", "stderr": ""})()

            with patch("anime_studio.bernini_low_vram.shutil.which", return_value="ffmpeg"), patch(
                "anime_studio.bernini_low_vram.subprocess.run", side_effect=fake_run
            ):
                result = assemble_bernini_segments(settings, plan)

            self.assertEqual(result.output_path.read_bytes(), b"assembled")
            self.assertIn("-t", result.command)
            self.assertEqual(result.command[result.command.index("-t") + 1], "1")
            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["processor"], "ffmpeg_cpu")


def write_identity_reference(root: Path) -> Path:
    reference = root / "assets" / "processed" / "characters" / "chiyoko" / "main_portrait.png"
    reference.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (288, 421), (245, 240, 250)).save(reference)
    return reference


def write_definition(root: Path, reference: Path) -> None:
    path = root / "manifests" / "characters" / "chiyoko" / "character_2p5d_definition.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "definition_status": "ready",
                "identity_reference_images": [reference.relative_to(root).as_posix()],
                "generation_binding": {
                    "video_control": {
                        "identity_anchor_images": [reference.relative_to(root).as_posix()]
                    }
                },
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
                "bernini_low_vram": {
                    "enabled": True,
                    "renderer_model": "bernini_r_1.3B-Q4_K_M.gguf",
                    "text_encoder": "umt5-xxl-encoder-Q5_K_M.gguf",
                    "vae": "wan_2.1_vae.safetensors",
                    "width": 512,
                    "height": 320,
                    "fps": 12,
                    "steps": 16,
                    "segment_duration_seconds": 1.25,
                    "max_duration_seconds": 30.0,
                    "max_vram_gb": 5.25,
                    "max_ram_gb": 28.0,
                    "vae_tile_size": 256,
                    "vae_temporal_size": 8,
                },
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
