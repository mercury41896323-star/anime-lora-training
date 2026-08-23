from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from anime_studio.settings import load_settings
from anime_studio.video_domain_datasets import build_video_domain_datasets


class VideoDomainDatasetTest(unittest.TestCase):
    def test_saves_character_motion_camera_background_and_lighting_datasets(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = write_settings(root)
            write_manifests(root)

            result = build_video_domain_datasets(settings, "domain_hero", "scene01")
            bundle = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            summaries = {item.domain: item for item in result.datasets}

            self.assertEqual(bundle["manifest_type"], "video_learning_domain_bundle")
            self.assertEqual(
                set(summaries),
                {"character", "motion", "camera", "background", "lighting"},
            )
            self.assertEqual(summaries["character"].entry_count, 3)
            self.assertEqual(summaries["motion"].entry_count, 2)
            self.assertTrue(summaries["motion"].model_training_implemented)
            for summary in summaries.values():
                self.assertTrue((root / summary.manifest_path).exists())


def write_manifests(root: Path) -> None:
    manifest_dir = root / "manifests" / "characters" / "domain_hero" / "video_analysis"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    frames = []
    classifications = []
    for index, (angle, expression, framing) in enumerate(
        [
            ("front", "neutral", "portrait"),
            ("three_quarter", "smile", "upper_body"),
            ("side", "serious", "full_body"),
        ],
        start=1,
    ):
        source = f"assets/processed/characters/domain_hero/frames/scene01/frame_{index:06d}.png"
        output = f"datasets/lora/domain_hero/video_scene01_clean/images/{index:04d}.png"
        frames.append(
            {
                "source_frame_path": source,
                "output_path": output,
                "shot_id": "shot_001",
                "frame_index": index,
                "timestamp_seconds": float(index - 1),
                "status": "review_candidate",
                "tags": ["domain_hero", "night", "rim_light", "city_background"],
            }
        )
        classifications.append(
            {
                "frame_path": source,
                "shot_id": "shot_001",
                "face_angle": angle,
                "expression": expression,
                "body_framing": framing,
            }
        )
    (manifest_dir / "scene01_clean_frames.json").write_text(
        json.dumps({"manifest_type": "video_clean_frame_manifest", "frames": frames}) + "\n",
        encoding="utf-8",
    )
    (manifest_dir / "scene01_classifications.json").write_text(
        json.dumps({"manifest_type": "video_frame_classification_manifest", "classifications": classifications}) + "\n",
        encoding="utf-8",
    )
    (manifest_dir / "scene01_shots.json").write_text(
        json.dumps(
            {
                "manifest_type": "video_shot_manifest",
                "shots": [{"shot_id": "shot_001", "boundary_reason": "tag_change"}],
            }
        )
        + "\n",
        encoding="utf-8",
    )


def write_settings(root: Path):
    config_dir = root / "config"
    config_dir.mkdir(parents=True)
    config_path = config_dir / "local_6gb.json"
    config_path.write_text(
        json.dumps(
            {
                "runtime": {"name": "test", "max_vram_gb": 6.0, "target_gpu_utilization": 0.8, "target_gpu_temp_c": 60},
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
