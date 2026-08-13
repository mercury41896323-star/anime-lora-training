from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from anime_studio.character_profile import create_character_profile
from anime_studio.phase6_pipeline import (
    add_motion_cue,
    add_sfx_cue,
    add_voice_cue,
    build_lip_sync_plan,
    export_phase6_manifest,
)
from anime_studio.settings import load_settings
from anime_studio.storyboard import add_shot, create_storyboard


class Phase6PipelineTest(unittest.TestCase):
    def test_writes_voice_lipsync_sfx_motion_and_export_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = write_settings(root)
            create_character_profile(settings, "sample_hero", "Sample Hero")
            create_storyboard(settings, "pilot_scene", "Pilot Scene")
            add_shot(
                settings=settings,
                story_id="pilot_scene",
                shot_id="shot_001",
                title="Opening",
                character_id="sample_hero",
                duration_seconds=3.0,
            )

            voice = add_voice_cue(
                settings=settings,
                story_id="pilot_scene",
                shot_id="shot_001",
                text="ありがとう",
                speaker="Sample Hero",
                emotion="soft",
                voice_asset_path="assets/audio/voice/shot_001.wav",
            )
            sfx = add_sfx_cue(
                settings=settings,
                story_id="pilot_scene",
                shot_id="shot_001",
                label="soft wind",
                asset_path="assets/audio/sfx/wind.wav",
                tags=["ambience", "wind"],
            )
            motion = add_motion_cue(
                settings=settings,
                story_id="pilot_scene",
                shot_id="shot_001",
                target="sample_hero",
                motion="small nod",
                source="motion_library",
            )
            lip_sync = build_lip_sync_plan(settings, "pilot_scene")
            exported = export_phase6_manifest(settings, "pilot_scene")

            voice_manifest = json.loads(voice.manifest_path.read_text(encoding="utf-8"))
            sfx_manifest = json.loads(sfx.manifest_path.read_text(encoding="utf-8"))
            motion_manifest = json.loads(motion.manifest_path.read_text(encoding="utf-8"))
            lip_manifest = json.loads(lip_sync.manifest_path.read_text(encoding="utf-8"))
            phase6_manifest = json.loads(exported.manifest_path.read_text(encoding="utf-8"))

            self.assertEqual(voice_manifest["manifest_type"], "storyboard_voice_cues")
            self.assertEqual(voice_manifest["items"][0]["voice_asset_path"], "assets/audio/voice/shot_001.wav")
            self.assertEqual(sfx_manifest["items"][0]["tags"], ["ambience", "wind"])
            self.assertEqual(motion_manifest["items"][0]["motion"], "small nod")
            self.assertEqual(lip_manifest["manifest_type"], "storyboard_lip_sync_plan")
            self.assertGreater(len(lip_manifest["items"][0]["visemes"]), 1)
            self.assertEqual(exported.shot_count, 1)
            self.assertEqual(exported.voice_count, 1)
            self.assertEqual(exported.lip_sync_count, 1)
            self.assertEqual(exported.sfx_count, 1)
            self.assertEqual(exported.motion_count, 1)
            self.assertEqual(phase6_manifest["manifest_type"], "storyboard_phase6_manifest")
            self.assertEqual(phase6_manifest["shots"][0]["voice_cues"][0]["text"], "ありがとう")
            self.assertEqual(phase6_manifest["shots"][0]["sfx_cues"][0]["label"], "soft wind")
            self.assertEqual(phase6_manifest["shots"][0]["motion_cues"][0]["target"], "sample_hero")

    def test_rejects_cues_for_unknown_shot(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = write_settings(root)
            create_storyboard(settings, "pilot_scene", "Pilot Scene")

            with self.assertRaises(ValueError):
                add_voice_cue(
                    settings=settings,
                    story_id="pilot_scene",
                    shot_id="missing_shot",
                    text="hello",
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
                    "video_extensions": [".mp4"],
                },
            }
        ),
        encoding="utf-8",
    )
    return load_settings(config_path)


if __name__ == "__main__":
    unittest.main()
