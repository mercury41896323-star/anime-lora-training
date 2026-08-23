from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from anime_studio.b_control import load_learned_domain_models
from anime_studio.character_profile import create_character_profile, load_character_profile
from anime_studio.neural_trainers import (
    mark_neural_job_trained,
    prepare_neural_training_job,
)
from anime_studio.settings import load_settings


class NeuralTrainerTest(unittest.TestCase):
    def test_prepares_camera_and_relighting_jobs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = write_settings(root)
            create_character_profile(settings, "neural_hero", "Neural Hero")
            write_camera_entries(root)
            write_lighting_entries(root)

            camera = prepare_neural_training_job(
                settings, "neural_hero", "scene01", "camera"
            )
            lighting = prepare_neural_training_job(
                settings, "neural_hero", "scene01", "lighting"
            )

            self.assertTrue(camera.ready)
            self.assertTrue(lighting.ready)
            camera_config = json.loads(camera.config_path.read_text(encoding="utf-8"))
            lighting_samples = [
                json.loads(line)
                for line in (lighting.job_dir / "training_samples.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            self.assertEqual(camera_config["provider"], "camera_trajectory_adapter")
            self.assertEqual(len(lighting_samples[0]["features"]), 6)
            self.assertEqual(lighting_samples[0]["target_labels"], ["rim_light", "warm_light"])

    def test_background_lora_requires_segmented_images(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = write_settings(root)
            create_character_profile(settings, "background_hero", "Background Hero")
            image = root / "frame.png"
            Image.new("RGB", (16, 16), (10, 20, 30)).save(image)
            write_entries(
                root,
                "background_hero",
                "scene01",
                "background",
                [
                    {
                        "image_path": str(image),
                        "background_tags": ["city", "night"],
                        "requires_character_segmentation": True,
                    }
                ],
            )

            result = prepare_neural_training_job(
                settings, "background_hero", "scene01", "background"
            )

            self.assertFalse(result.ready)
            self.assertTrue(any("segmented_image_path" in issue for issue in result.issues))
            self.assertIn("exit 1", result.run_script.read_text(encoding="utf-8"))

    def test_motion_job_generates_official_dataset_but_blocks_six_gb(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = write_settings(root)
            create_character_profile(settings, "motion_hero", "Motion Hero")
            write_entries(
                root,
                "motion_hero",
                "scene01",
                "motion",
                [
                    {
                        "from_state": {"face_angle": "front"},
                        "to_state": {"face_angle": "side"},
                    }
                ],
            )
            video = root / "source.mp4"
            video.write_bytes(b"test")
            trainer = root / "AnimateDiff"
            trainer.mkdir()
            (trainer / "train.py").write_text("", encoding="utf-8")
            model = root / "sd15"
            model.mkdir()

            result = prepare_neural_training_job(
                settings,
                "motion_hero",
                "scene01",
                "motion",
                pretrained_model=str(model),
                trainer_root=str(trainer),
                source_video=str(video),
            )

            self.assertFalse(result.ready)
            self.assertTrue(any("6GB VRAM" in issue for issue in result.issues))
            config = json.loads(result.config_path.read_text(encoding="utf-8"))
            self.assertEqual(config["provider"], "animatediff_motion_module_job")
            self.assertEqual(config["command"][0], "torchrun")
            csv_text = (result.job_dir / "animatediff_dataset.csv").read_text(encoding="utf-8")
            self.assertIn("videoid,name,page_dir", csv_text)
            self.assertIn("source", csv_text)

    def test_register_requires_weights_and_links_descriptor(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = write_settings(root)
            create_character_profile(settings, "register_hero", "Register Hero")
            write_camera_entries(root, "register_hero")
            result = prepare_neural_training_job(
                settings, "register_hero", "scene01", "camera"
            )
            descriptor = json.loads(result.model_descriptor.read_text(encoding="utf-8"))
            weights = root / descriptor["weights"]
            weights.write_bytes(b"weights")

            path = mark_neural_job_trained(
                settings, "register_hero", "scene01", "camera"
            )
            profile = load_character_profile(settings, "register_hero")
            learned = load_learned_domain_models(settings, "register_hero")

            self.assertEqual(profile.domain_models["camera"], path.relative_to(root).as_posix())
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["status"], "trained")
            self.assertEqual(learned["camera"]["weights"], descriptor["weights"])
            self.assertEqual(learned["camera"]["provider"], "camera_trajectory_adapter")


def write_camera_entries(root: Path, character_id: str = "neural_hero") -> None:
    write_entries(
        root,
        character_id,
        "scene01",
        "camera",
        [
            {"entry_id": "camera_1", "shot_id": "shot_1", "timestamp_seconds": 0.0, "camera_distance": "close_up", "face_angle": "front"},
            {"entry_id": "camera_2", "shot_id": "shot_1", "timestamp_seconds": 1.0, "camera_distance": "medium", "face_angle": "side"},
        ],
    )


def write_lighting_entries(root: Path) -> None:
    entries = []
    for index, color in enumerate(((255, 120, 40), (40, 80, 255)), 1):
        image = root / f"light_{index}.png"
        Image.new("RGB", (16, 16), color).save(image)
        entries.append(
            {
                "entry_id": f"lighting_{index}",
                "image_path": str(image),
                "lighting_tags": ["warm_light" if index == 1 else "rim_light"],
            }
        )
    write_entries(root, "neural_hero", "scene01", "lighting", entries)


def write_entries(
    root: Path,
    character_id: str,
    video_id: str,
    domain: str,
    entries: list[dict[str, object]],
) -> None:
    path = root / "datasets" / "video_learning" / character_id / video_id / domain / "entries.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(item) for item in entries) + "\n", encoding="utf-8")


def write_settings(root: Path):
    config_dir = root / "config"
    config_dir.mkdir(parents=True)
    config_path = config_dir / "local_6gb.json"
    config_path.write_text(
        json.dumps(
            {
                "runtime": {"name": "rtx3050_test", "max_vram_gb": 6.0, "target_gpu_utilization": 0.8, "target_gpu_temp_c": 60},
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
