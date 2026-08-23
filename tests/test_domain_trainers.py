from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from anime_studio.b_control import load_learned_domain_models
from anime_studio.character_profile import create_character_profile, load_character_profile
from anime_studio.domain_trainers import train_all_domain_models, train_domain_model
from anime_studio.settings import load_settings


class DomainTrainerTest(unittest.TestCase):
    def test_trains_all_domain_priors_and_links_character_profile(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = write_settings(root)
            create_character_profile(settings, "trainer_hero", "Trainer Hero")
            write_domain_entries(root)

            result = train_all_domain_models(settings, "trainer_hero", "scene01")
            profile = load_character_profile(settings, "trainer_hero")
            loaded = load_learned_domain_models(settings, "trainer_hero")

            self.assertEqual(len(result.results), 4)
            self.assertTrue(all(item.trained for item in result.results))
            self.assertEqual(set(profile.domain_models), {"motion", "camera", "background", "lighting"})
            self.assertEqual(set(loaded), {"motion", "camera", "background", "lighting"})
            self.assertEqual(
                loaded["camera"]["priors"]["recommended_camera_distance"],
                "close_up",
            )
            motion_model = json.loads(
                next(item.model_path for item in result.results if item.domain == "motion").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(motion_model["model_kind"], "motion_transition_prior")
            self.assertEqual(motion_model["average_transition_seconds"], 1.0)

    def test_writes_needs_data_model_for_empty_domain_dataset(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = write_settings(root)
            create_character_profile(settings, "empty_hero", "Empty Hero")
            entries = root / "datasets" / "video_learning" / "empty_hero" / "scene01" / "motion" / "entries.jsonl"
            entries.parent.mkdir(parents=True)
            entries.write_text("", encoding="utf-8")

            result = train_domain_model(settings, "empty_hero", "scene01", "motion")
            model = json.loads(result.model_path.read_text(encoding="utf-8"))
            self.assertFalse(result.trained)
            self.assertEqual(model["status"], "needs_data")


def write_domain_entries(root: Path) -> None:
    dataset_root = root / "datasets" / "video_learning" / "trainer_hero" / "scene01"
    values = {
        "motion": [
            {
                "entry_id": "motion_000001",
                "start_seconds": 0.0,
                "end_seconds": 1.0,
                "from_state": {"face_angle": "front", "expression": "neutral", "body_framing": "portrait"},
                "to_state": {"face_angle": "side", "expression": "smile", "body_framing": "portrait"},
            }
        ],
        "camera": [
            {"camera_distance": "close_up", "face_angle": "front", "shot_boundary_reason": "tag_change"},
            {"camera_distance": "close_up", "face_angle": "side", "shot_boundary_reason": "duration"},
            {"camera_distance": "medium", "face_angle": "front", "shot_boundary_reason": "duration"},
        ],
        "background": [
            {"background_tags": ["city_background", "night"], "requires_character_segmentation": True},
            {"background_tags": ["city_background", "rain"], "requires_character_segmentation": True},
        ],
        "lighting": [
            {"shot_id": "shot_001", "lighting_tags": ["night", "rim_light"]},
            {"shot_id": "shot_001", "lighting_tags": ["night", "cool_light"]},
        ],
    }
    for domain, entries in values.items():
        path = dataset_root / domain / "entries.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "\n".join(json.dumps(item) for item in entries) + "\n",
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
