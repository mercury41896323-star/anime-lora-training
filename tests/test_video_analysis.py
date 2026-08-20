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
from anime_studio.video_analysis import analyze_video_learning


class VideoAnalysisTest(unittest.TestCase):
    def test_analyzes_frames_into_sequences_and_assets(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = write_settings(root)
            create_character_profile(settings, "sample_yonagi", "Sample Yonagi", trigger_tags=["sample_yonagi"])

            source_video = root / "assets" / "raw" / "scene01.mp4"
            source_video.parent.mkdir(parents=True)
            source_video.write_bytes(b"video")

            frame_dir = (
                root
                / "assets"
                / "processed"
                / "characters"
                / "sample_yonagi"
                / "frames"
                / "scene01"
            )
            frame_dir.mkdir(parents=True, exist_ok=True)
            for index in range(1, 7):
                (frame_dir / f"frame_{index:06d}.png").write_bytes(b"image")

            result = analyze_video_learning(
                settings=settings,
                character_id="sample_yonagi",
                video_path=source_video,
                fps=1.0,
                sequence_seconds=3.0,
                sample_every_n=2,
                auto_extract=False,
                reuse_import=True,
                source_label="scene01",
                create_storyboard_draft=True,
            )

            analysis = json.loads(result.analysis_manifest_path.read_text(encoding="utf-8"))
            sequences = json.loads(result.sequence_manifest_path.read_text(encoding="utf-8"))
            assets = json.loads(result.asset_manifest_path.read_text(encoding="utf-8"))

            self.assertEqual(result.sequence_count, 2)
            self.assertGreaterEqual(result.asset_count, 1)
            self.assertEqual(analysis["manifest_type"], "video_learning_analysis")
            self.assertEqual(sequences["manifest_type"], "video_sequence_manifest")
            self.assertEqual(assets["manifest_type"], "video_learning_asset_manifest")
            self.assertIsNotNone(result.storyboard_path)
            self.assertTrue(result.storyboard_path.exists())


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
