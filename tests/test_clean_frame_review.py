from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from anime_studio.character_profile import confirm_character_source_rights, create_character_profile
from anime_studio.clean_frame_review import build_clean_frame_review, finalize_clean_frame_review, parse_frame_indices
from anime_studio.cli import build_parser
from anime_studio.kohya_config import KohyaLowVramSettings, generate_kohya_low_vram_config
from anime_studio.settings import load_settings
from anime_studio.training_readiness import check_training_readiness


class CleanFrameReviewTest(unittest.TestCase):
    def test_main_cli_accepts_reviewed_dataset_for_kohya(self) -> None:
        args = build_parser().parse_args(
            [
                "lora",
                "kohya-config",
                "--character-id",
                "review_hero",
                "--pretrained-model",
                "model.safetensors",
                "--dataset-dir",
                "datasets/lora/review_hero/video_scene01_reviewed",
                "--require-2p5d",
            ]
        )

        self.assertTrue(args.require_2p5d)
        self.assertTrue(args.dataset_dir.endswith("video_scene01_reviewed"))
        readiness_args = build_parser().parse_args(
            [
                "training",
                "readiness",
                "--character-id",
                "review_hero",
                "--dataset-dir",
                args.dataset_dir,
                "--require-2p5d",
            ]
        )
        self.assertTrue(readiness_args.require_2p5d)
        self.assertEqual(readiness_args.dataset_dir, args.dataset_dir)

    def test_builds_gallery_and_reviewed_training_dataset(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = write_settings(root)
            create_character_profile(settings, "review_hero", "Review Hero")
            confirm_character_source_rights(settings, "review_hero", "test reviewer")
            write_ready_definition(root)
            clean_dataset = write_clean_manifest(root)

            before = check_training_readiness(
                settings,
                "review_hero",
                min_images=1,
                dataset_dir=clean_dataset,
                require_2p5d=True,
            )
            before_payload = json.loads(before.manifest_path.read_text(encoding="utf-8"))
            self.assertFalse(before.ready)
            self.assertIn("clean_frame_review_required", {item["code"] for item in before_payload["issues"]})

            prepared = build_clean_frame_review(settings, "review_hero", "scene01")
            finalized = finalize_clean_frame_review(
                settings,
                "review_hero",
                "scene01",
                parse_frame_indices("1"),
                "test reviewer",
                "face and body are clear",
            )
            generate_kohya_low_vram_config(
                settings,
                "review_hero",
                KohyaLowVramSettings(pretrained_model_name_or_path="models/sd15.safetensors"),
                dataset_dir=finalized.dataset_dir,
                require_2p5d=True,
            )
            after = check_training_readiness(
                settings,
                "review_hero",
                min_images=1,
                dataset_dir=finalized.dataset_dir,
                require_2p5d=True,
            )

            self.assertEqual(prepared.candidate_count, 2)
            self.assertIn("Frame 1", prepared.gallery_path.read_text(encoding="utf-8"))
            self.assertEqual(finalized.accepted_count, 1)
            self.assertEqual(finalized.rejected_count, 1)
            self.assertTrue((finalized.dataset_dir / "images" / "0001_frame_000001.png").is_file())
            self.assertTrue(after.ready)


def write_clean_manifest(root: Path) -> Path:
    dataset_dir = root / "datasets" / "lora" / "review_hero" / "video_scene01_clean"
    images_dir = dataset_dir / "images"
    images_dir.mkdir(parents=True)
    frames = []
    for index in (1, 2):
        image = images_dir / f"{index:04d}_frame_{index:06d}.png"
        Image.new("RGB", (128, 128), color=(80 * index, 60, 100)).save(image)
        caption = image.with_suffix(".txt")
        caption.write_text("review_hero, front, full_body\n", encoding="utf-8")
        frames.append(
            {
                "frame_index": index,
                "shot_id": "shot_001",
                "timestamp_seconds": float(index - 1),
                "output_path": image.relative_to(root).as_posix(),
                "caption_path": caption.relative_to(root).as_posix(),
                "status": "review_candidate",
            }
        )
    metadata = {"human_review_required": True, "review_completed": False, "image_count": 2}
    (dataset_dir / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    manifest = root / "manifests" / "characters" / "review_hero" / "video_analysis" / "scene01_clean_frames.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({"frames": frames}), encoding="utf-8")
    return dataset_dir


def write_ready_definition(root: Path) -> None:
    path = root / "manifests" / "characters" / "review_hero" / "character_2p5d_definition.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"definition_status": "ready"}), encoding="utf-8")


def write_settings(root: Path):
    config = root / "config" / "local_6gb.json"
    config.parent.mkdir(parents=True)
    config.write_text(
        json.dumps(
            {
                "runtime": {"name": "test", "max_vram_gb": 6, "target_gpu_utilization": 0.8, "target_gpu_temp_c": 60},
                "assets": {"raw_dir": "assets/raw", "processed_dir": "assets/processed"},
                "datasets": {"lora_dir": "datasets/lora"},
                "models": {"wd14_dir": "models/wd14"},
                "asset_types": {"image_extensions": [".png"], "video_extensions": [".mp4"]},
            }
        ),
        encoding="utf-8",
    )
    return load_settings(config)


if __name__ == "__main__":
    unittest.main()
