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
from anime_studio.video_shot_pipeline import (
    classify_sampled_frames,
    detect_video_shots,
    sample_shot_frames,
)


class VideoShotPipelineTest(unittest.TestCase):
    def test_detects_shots_samples_frames_and_classifies(self) -> None:
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
            first_tags = ["sample_yonagi", "front", "portrait", "smile"]
            second_tags = ["sample_yonagi", "side", "full_body", "serious"]
            for index in range(1, 5):
                write_frame(frame_dir / f"frame_{index:06d}.png", first_tags)
            for index in range(5, 9):
                write_frame(frame_dir / f"frame_{index:06d}.png", second_tags)

            shots = detect_video_shots(
                settings=settings,
                character_id="sample_yonagi",
                video_path=source_video,
                fps=1.0,
                source_label="scene01",
                auto_extract=False,
                reuse_import=True,
                min_shot_seconds=2.0,
                max_shot_seconds=10.0,
                tag_change_threshold=0.5,
                target_max_frames=240,
            )
            sampled = sample_shot_frames(
                settings=settings,
                character_id="sample_yonagi",
                video_id=shots.video_id,
                similarity_threshold=0.95,
                max_frames_per_shot=4,
                min_frame_gap=1,
            )
            classified = classify_sampled_frames(
                settings=settings,
                character_id="sample_yonagi",
                video_id=shots.video_id,
            )

            shot_manifest = json.loads(shots.manifest_path.read_text(encoding="utf-8"))
            sampled_manifest = json.loads(sampled.manifest_path.read_text(encoding="utf-8"))
            classification_manifest = json.loads(classified.manifest_path.read_text(encoding="utf-8"))

            self.assertEqual(shot_manifest["manifest_type"], "video_shot_manifest")
            self.assertEqual(len(shot_manifest["shots"]), 2)
            self.assertEqual(sampled_manifest["manifest_type"], "video_sampled_frame_manifest")
            self.assertGreaterEqual(len(sampled_manifest["frames"]), 4)
            self.assertEqual(classification_manifest["manifest_type"], "video_frame_classification_manifest")
            face_angles = {item["face_angle"] for item in classification_manifest["classifications"]}
            body_framings = {item["body_framing"] for item in classification_manifest["classifications"]}
            expressions = {item["expression"] for item in classification_manifest["classifications"]}
            self.assertIn("front", face_angles)
            self.assertIn("side", face_angles)
            self.assertIn("full_body", body_framings)
            self.assertIn("smile", expressions)


def write_frame(path: Path, tags: list[str]) -> None:
    path.write_bytes(b"image")
    path.with_suffix(".txt").write_text(", ".join(tags) + "\n", encoding="utf-8")



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
