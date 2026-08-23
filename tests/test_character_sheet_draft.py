from __future__ import annotations

from pathlib import Path
import json
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from anime_studio.character_profile import create_character_profile
from anime_studio.character_sheet_draft import generate_character_sheet_draft
from anime_studio.settings import load_settings
from anime_studio.video_analysis import analyze_video_learning


class CharacterSheetDraftTest(unittest.TestCase):
    def test_generates_draft_and_completeness_from_video_analysis(self) -> None:
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

            analysis_result = analyze_video_learning(
                settings=settings,
                character_id="sample_yonagi",
                video_path=source_video,
                fps=1.0,
                sequence_seconds=3.0,
                sample_every_n=2,
                auto_extract=False,
                reuse_import=True,
                source_label="scene01",
                create_storyboard_draft=False,
            )

            draft_result = generate_character_sheet_draft(
                settings=settings,
                character_id="sample_yonagi",
                video_id=analysis_result.video_id,
            )

            draft = json.loads(draft_result.draft_manifest_path.read_text(encoding="utf-8"))
            completeness = json.loads(
                draft_result.completeness_manifest_path.read_text(encoding="utf-8")
            )

            self.assertEqual(draft["manifest_type"], "character_sheet_draft")
            self.assertEqual(completeness["manifest_type"], "character_sheet_completeness")
            self.assertEqual(draft["character_id"], "sample_yonagi")
            self.assertEqual(draft["video_id"], "scene01")
            self.assertEqual(draft_result.section_count, 8)
            self.assertGreaterEqual(draft_result.ready_sections, 1)
            self.assertIn("main_portrait", completeness["statuses"])
            self.assertTrue(draft_result.draft_sheet_path.exists())
            self.assertTrue(draft_result.review_manifest_path.exists())
            self.assertEqual(draft["candidate_source"], "video_analysis")


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
