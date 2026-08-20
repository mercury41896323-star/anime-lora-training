from __future__ import annotations

from pathlib import Path
import json
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from anime_studio.character_2p5d_definition import generate_character_2p5d_definition
from anime_studio.character_master_asset import import_character_master_asset
from anime_studio.character_profile import create_character_profile
from anime_studio.settings import load_settings


class CharacterMasterAssetTest(unittest.TestCase):
    def test_imports_reviewed_master_and_generates_definition(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = write_settings(root)
            create_character_profile(settings, "sample_yonagi", "Sample Yonagi", trigger_tags=["sample_yonagi"])
            write_phase35_manifests(root)

            reviewed = root / "reviewed_sheet.png"
            master = root / "master_sheet.png"
            reviewed.write_bytes(b"reviewed")
            master.write_bytes(b"master")

            master_result = import_character_master_asset(
                settings=settings,
                character_id="sample_yonagi",
                video_id="scene01",
                reviewed_image=reviewed,
                master_image=master,
                notes="manual clean up complete",
            )
            definition = generate_character_2p5d_definition(
                settings=settings,
                character_id="sample_yonagi",
            )

            master_manifest = json.loads(master_result.manifest_path.read_text(encoding="utf-8"))
            definition_manifest = json.loads(definition.manifest_path.read_text(encoding="utf-8"))

            self.assertEqual(master_manifest["manifest_type"], "character_master_asset")
            self.assertEqual(definition_manifest["manifest_type"], "character_2p5d_definition")
            self.assertTrue(master_result.reviewed_asset_path.exists())
            self.assertTrue(master_result.master_asset_path.exists())
            self.assertEqual(definition_manifest["video_id"], "scene01")
            self.assertEqual(definition_manifest["view_anchors"][0]["view"], "front")


def write_phase35_manifests(root: Path) -> None:
    manifest_dir = root / "manifests" / "characters" / "sample_yonagi" / "character_sheet"
    analysis_dir = root / "manifests" / "characters" / "sample_yonagi" / "video_analysis"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    analysis_dir.mkdir(parents=True, exist_ok=True)
    (manifest_dir / "scene01_draft.json").write_text(
        json.dumps({"manifest_type": "character_sheet_draft", "character_id": "sample_yonagi", "video_id": "scene01"}) + "\n",
        encoding="utf-8",
    )
    (manifest_dir / "scene01_completeness.json").write_text(
        json.dumps(
            {
                "manifest_type": "character_sheet_completeness",
                "character_id": "sample_yonagi",
                "video_id": "scene01",
                "statuses": {
                    "main_portrait": "ready",
                    "face_angles": "ready",
                    "expressions": "needs_review",
                    "full_body": "ready",
                    "back_view": "missing",
                    "costume_detail": "missing",
                },
                "phase35_ready": False,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (analysis_dir / "scene01_classifications.json").write_text(
        json.dumps({"manifest_type": "video_frame_classification_manifest", "character_id": "sample_yonagi", "video_id": "scene01"}) + "\n",
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
