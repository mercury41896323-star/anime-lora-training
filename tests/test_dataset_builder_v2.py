from __future__ import annotations

from pathlib import Path
import json
import sys
import tempfile
import unittest

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from anime_studio.character_profile import create_character_profile
from anime_studio.character_master_asset import import_character_master_asset
from anime_studio.character_sheet_importer import import_character_sheet
from anime_studio.dataset_builder_v2 import build_purpose_datasets_v2
from anime_studio.settings import load_settings


class DatasetBuilderV2Test(unittest.TestCase):
    def test_builds_purpose_specific_datasets(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = write_settings(root)
            create_character_profile(settings, "sample_yonagi", "Sample Yonagi", trigger_tags=["sample_yonagi"])

            sheet_source = root / "assets" / "raw" / "yonagi_sheet.png"
            sheet_source.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (1200, 1000), color=(180, 120, 220)).save(sheet_source)
            sheet_result = import_character_sheet(
                settings=settings,
                character_id="sample_yonagi",
                source_image=sheet_source,
                source_label="yonagi_sheet_v1",
            )

            write_phase35_manifests(root)
            reviewed = root / "reviewed_sheet.png"
            master = root / "master_sheet.png"
            Image.new("RGB", (1200, 1000), color=(220, 160, 180)).save(reviewed)
            Image.new("RGB", (1200, 1000), color=(160, 220, 180)).save(master)
            import_character_master_asset(
                settings=settings,
                character_id="sample_yonagi",
                video_id="scene01",
                reviewed_image=reviewed,
                master_image=master,
            )

            result = build_purpose_datasets_v2(
                settings=settings,
                character_id="sample_yonagi",
                video_id="scene01",
                sheet_id=sheet_result.sheet_id,
            )
            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))

            self.assertEqual(manifest["manifest_type"], "purpose_dataset_bundle")
            self.assertEqual(result.dataset_count, 4)
            self.assertGreater(result.total_images, 0)
            self.assertTrue((root / "datasets" / "v2" / "sample_yonagi" / "character" / "manifest.json").exists())
            self.assertTrue((root / "datasets" / "v2" / "sample_yonagi" / "expression" / "manifest.json").exists())


def write_phase35_manifests(root: Path) -> None:
    sheet_dir = root / "manifests" / "characters" / "sample_yonagi" / "character_sheet"
    analysis_dir = root / "manifests" / "characters" / "sample_yonagi" / "video_analysis"
    processed_frame_dir = root / "assets" / "processed" / "characters" / "sample_yonagi" / "frames" / "scene01"
    sheet_dir.mkdir(parents=True, exist_ok=True)
    analysis_dir.mkdir(parents=True, exist_ok=True)
    processed_frame_dir.mkdir(parents=True, exist_ok=True)

    frame_one = processed_frame_dir / "frame_000001.png"
    frame_two = processed_frame_dir / "frame_000002.png"
    Image.new("RGB", (512, 512), color=(120, 120, 120)).save(frame_one)
    Image.new("RGB", (512, 512), color=(140, 140, 140)).save(frame_two)

    (sheet_dir / "scene01_draft.json").write_text(
        json.dumps({"manifest_type": "character_sheet_draft", "character_id": "sample_yonagi", "video_id": "scene01"}) + "\n",
        encoding="utf-8",
    )
    (sheet_dir / "scene01_completeness.json").write_text(
        json.dumps(
            {
                "manifest_type": "character_sheet_completeness",
                "character_id": "sample_yonagi",
                "video_id": "scene01",
                "statuses": {
                    "main_portrait": "ready",
                    "face_angles": "ready",
                    "expressions": "ready",
                    "full_body": "ready",
                },
                "phase35_ready": True,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (analysis_dir / "scene01_sampled_frames.json").write_text(
        json.dumps(
            {
                "manifest_type": "video_sampled_frame_manifest",
                "character_id": "sample_yonagi",
                "video_id": "scene01",
                "frames": [
                    {
                        "shot_id": "shot_001",
                        "frame_path": "assets/processed/characters/sample_yonagi/frames/scene01/frame_000001.png",
                        "frame_index": 1,
                        "timestamp_seconds": 0.0,
                        "role": "start",
                        "similarity_score": 0.0,
                        "tags": ["front", "portrait", "smile"],
                    },
                    {
                        "shot_id": "shot_001",
                        "frame_path": "assets/processed/characters/sample_yonagi/frames/scene01/frame_000002.png",
                        "frame_index": 2,
                        "timestamp_seconds": 1.0,
                        "role": "end",
                        "similarity_score": 0.2,
                        "tags": ["side", "full_body", "serious"],
                    },
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (analysis_dir / "scene01_classifications.json").write_text(
        json.dumps(
            {
                "manifest_type": "video_frame_classification_manifest",
                "character_id": "sample_yonagi",
                "video_id": "scene01",
                "classifications": [
                    {
                        "frame_path": "assets/processed/characters/sample_yonagi/frames/scene01/frame_000001.png",
                        "shot_id": "shot_001",
                        "face_angle": "front",
                        "expression": "smile",
                        "body_framing": "portrait",
                        "tags": ["front", "portrait", "smile"],
                    },
                    {
                        "frame_path": "assets/processed/characters/sample_yonagi/frames/scene01/frame_000002.png",
                        "shot_id": "shot_001",
                        "face_angle": "side",
                        "expression": "serious",
                        "body_framing": "full_body",
                        "tags": ["side", "full_body", "serious"],
                    },
                ],
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