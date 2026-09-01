from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from anime_studio.settings import load_settings
from anime_studio.clean_frame_review import finalize_clean_frame_review
from anime_studio.kohya_config import KohyaLowVramSettings, generate_kohya_low_vram_config
from anime_studio.training_readiness import check_training_readiness
from anime_studio.video_phase35_pipeline import run_video_phase35_pipeline


class VideoPhase35PipelineTest(unittest.TestCase):
    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg and FFprobe are required")
    def test_runs_end_to_end_with_synthetic_video(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = write_settings(root)
            video_path = root / "source" / "phase35_test.mp4"
            video_path.parent.mkdir(parents=True)
            create_test_video(video_path)
            master_image = root / "source" / "master.png"
            Image.new("RGB", (640, 960), color=(170, 130, 110)).save(master_image)

            result = run_video_phase35_pipeline(
                settings=settings,
                character_id="phase35_hero",
                video_path=video_path,
                display_name="Phase 3.5 Hero",
                pretrained_model="models/sd15.safetensors",
                requested_fps=1.0,
                target_max_frames=12,
                min_images=1,
                sequence_seconds=2.0,
                max_frames_per_shot=3,
                master_image=master_image,
                clean_width=128,
                clean_height=128,
                top_trim_ratio=0.0,
                bottom_trim_ratio=0.0,
                source_rights_reviewer="test reviewer",
            )
            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))

            self.assertFalse(result.ready)
            self.assertEqual(manifest["manifest_type"], "phase3_5_video_pipeline")
            self.assertEqual(manifest["video_probe"]["source"], "ffprobe")
            self.assertTrue(resolve_output(root, manifest, "clean_frame_manifest").is_file())
            self.assertTrue(resolve_output(root, manifest, "video_domain_datasets").is_file())
            self.assertTrue(resolve_output(root, manifest, "training_readiness").is_file())
            self.assertTrue(resolve_output(root, manifest, "character_sheet_draft_image").is_file())
            self.assertFalse((root / "config" / "kohya" / "phase35_hero" / "train_low_vram.toml").is_file())

            clean_manifest = json.loads(resolve_output(root, manifest, "clean_frame_manifest").read_text(encoding="utf-8"))
            accepted_indices = {
                int(item["frame_index"])
                for item in clean_manifest["frames"]
                if item["status"] == "review_candidate"
            }
            reviewed = finalize_clean_frame_review(
                settings,
                "phase35_hero",
                result.video_id,
                accepted_indices,
                "test reviewer",
            )
            generate_kohya_low_vram_config(
                settings,
                "phase35_hero",
                KohyaLowVramSettings(pretrained_model_name_or_path="models/sd15.safetensors"),
                dataset_dir=reviewed.dataset_dir,
                require_2p5d=True,
            )
            self.assertTrue((root / "config" / "kohya" / "phase35_hero" / "train_low_vram.toml").is_file())
            final_readiness = check_training_readiness(
                settings,
                "phase35_hero",
                min_images=1,
                dataset_dir=reviewed.dataset_dir,
                require_2p5d=True,
            )
            self.assertTrue(final_readiness.ready)


def create_test_video(path: Path) -> None:
    completed = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=320x240:rate=4:duration=3",
            "-c:v",
            "mpeg4",
            "-pix_fmt",
            "yuv420p",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr)


def resolve_output(root: Path, manifest: dict, key: str) -> Path:
    return root / manifest["outputs"][key]


def write_settings(root: Path):
    config = root / "config" / "local_6gb.json"
    config.parent.mkdir(parents=True)
    config.write_text(
        json.dumps(
            {
                "runtime": {
                    "name": "test_6gb",
                    "max_vram_gb": 6.0,
                    "target_gpu_utilization": 0.8,
                    "target_gpu_temp_c": 60,
                },
                "assets": {"raw_dir": "assets/raw", "processed_dir": "assets/processed"},
                "datasets": {"lora_dir": "datasets/lora"},
                "models": {"wd14_dir": "models/wd14"},
                "asset_types": {"image_extensions": [".png", ".jpg"], "video_extensions": [".mp4"]},
            }
        ),
        encoding="utf-8",
    )
    return load_settings(config)


if __name__ == "__main__":
    unittest.main()
