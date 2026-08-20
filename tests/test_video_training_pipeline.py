from __future__ import annotations

from pathlib import Path
import json
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from anime_studio.character_profile import create_character_profile
from anime_studio.settings import load_settings
from anime_studio.video_training_pipeline import run_video_training_smoke


class VideoTrainingPipelineTest(unittest.TestCase):
    def test_runs_video_to_training_smoke_with_existing_frames(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = write_settings(root)
            create_character_profile(settings, "sample_yonagi", "Sample Yonagi", trigger_tags=["sample_yonagi"])

            source_video = root / "assets" / "raw" / "scene 001.mp4"
            source_video.parent.mkdir(parents=True)
            source_video.write_bytes(b"video")

            frames_dir = (
                root
                / "assets"
                / "processed"
                / "characters"
                / "sample_yonagi"
                / "frames"
                / "scene_001"
            )
            frames_dir.mkdir(parents=True, exist_ok=True)
            (frames_dir / "frame_000001.png").write_bytes(b"image")
            (frames_dir / "frame_000002.png").write_bytes(b"image")

            result = run_video_training_smoke(
                settings=settings,
                character_id="sample_yonagi",
                video_path=str(source_video),
                pretrained_model="models/sd15.safetensors",
                kohya_root="C:/tools/sd-scripts",
                min_images=1,
                provider="baseline",
                source_label="baseline_clip",
                skip_extract=True,
            )

            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["manifest_type"], "phase3_5_video_to_training_smoke")
            self.assertEqual(manifest["video"]["video_id"], "scene_001")
            self.assertEqual(manifest["frame_extraction"]["status"], "skipped")
            self.assertTrue(result.ready)
            self.assertTrue((result.dataset_dir / "images").exists())
            self.assertTrue((result.kohya_config_dir / "dataset.toml").exists())


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
                    "video_extensions": [".mp4", ".mov"],
                },
            }
        ),
        encoding="utf-8",
    )
    return load_settings(config_path)


if __name__ == "__main__":
    unittest.main()
