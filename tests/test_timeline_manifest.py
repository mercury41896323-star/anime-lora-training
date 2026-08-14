from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from anime_studio.motion_clip_plan import build_motion_clip_plan
from anime_studio.phase6_pipeline import add_motion_cue, add_sfx_cue, add_voice_cue, build_lip_sync_plan, export_phase6_manifest
from anime_studio.settings import load_settings
from anime_studio.storyboard import add_shot, create_storyboard
from anime_studio.storyboard_editor_manifest import export_selected_shot_manifest
from anime_studio.storyboard_results import link_shot_result, set_shot_result_decision
from anime_studio.timeline_manifest import build_edit_timeline_manifest


class TimelineManifestTest(unittest.TestCase):
    def test_builds_edit_timeline_from_selected_shots_and_phase6_cues(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = write_settings(root)
            create_storyboard(settings, "pilot_scene", "Pilot Scene")
            add_shot(settings, "pilot_scene", "shot_001", "Opening", character_id="sample_hero", duration_seconds=3.0)
            add_shot(settings, "pilot_scene", "shot_002", "Reaction", character_id="sample_hero", duration_seconds=2.0)
            selected_image = root / "outputs" / "manual" / "opening.png"
            selected_image.parent.mkdir(parents=True)
            selected_image.write_bytes(b"image")
            voice_file = root / "assets" / "audio" / "voice" / "opening.wav"
            sfx_file = root / "assets" / "audio" / "sfx" / "wind.wav"
            voice_file.parent.mkdir(parents=True)
            sfx_file.parent.mkdir(parents=True)
            voice_file.write_bytes(b"voice")
            sfx_file.write_bytes(b"sfx")
            linked = link_shot_result(settings, "pilot_scene", "shot_001", selected_image)
            set_shot_result_decision(settings, "pilot_scene", linked.linked[0].result_id, "selected")
            export_selected_shot_manifest(settings, "pilot_scene")
            add_voice_cue(
                settings=settings,
                story_id="pilot_scene",
                shot_id="shot_001",
                text="hello",
                voice_asset_path="assets/audio/voice/opening.wav",
                duration_seconds=1.2,
            )
            add_sfx_cue(
                settings=settings,
                story_id="pilot_scene",
                shot_id="shot_001",
                label="soft wind",
                asset_path="assets/audio/sfx/wind.wav",
                start_seconds=0.5,
                duration_seconds=1.0,
            )
            add_motion_cue(
                settings=settings,
                story_id="pilot_scene",
                shot_id="shot_001",
                target="sample_hero",
                motion="small nod",
                duration_seconds=0.8,
            )
            build_lip_sync_plan(settings, "pilot_scene")
            export_phase6_manifest(settings, "pilot_scene")
            build_motion_clip_plan(settings, "pilot_scene")

            result = build_edit_timeline_manifest(settings, "pilot_scene", frame_rate=24)

            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            tracks = {track["track_id"]: track for track in manifest["tracks"]}
            self.assertEqual(manifest["manifest_type"], "storyboard_edit_timeline")
            self.assertEqual(manifest["counts"]["shot_count"], 1)
            self.assertEqual(result.duration_seconds, 3.0)
            self.assertIn("video_main", tracks)
            self.assertIn("voice_main", tracks)
            self.assertIn("sfx_main", tracks)
            self.assertIn("lip_sync_signals", tracks)
            self.assertIn("Phase6_Motion_sample_hero", tracks)
            self.assertEqual(tracks["video_main"]["clips"][0]["source_path"], "outputs/manual/opening.png")
            self.assertEqual(tracks["video_main"]["clips"][0]["duration_seconds"], 3.0)
            self.assertEqual(tracks["voice_main"]["clips"][0]["metadata"]["exists"], True)
            self.assertEqual(tracks["sfx_main"]["clips"][0]["start_seconds"], 0.5)
            self.assertEqual(tracks["sfx_main"]["clips"][0]["metadata"]["exists"], True)
            self.assertEqual(tracks["Phase6_Motion_sample_hero"]["clips"][0]["metadata"]["motion_plan"]["preset"], "head_nod")
            self.assertEqual(
                manifest["source_manifests"]["phase6"],
                "manifests/storyboards/pilot_scene/phase6_manifest.json",
            )

    def test_phase6_manifest_points_to_phase7_supplemental_manifests(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = write_settings(root)
            create_storyboard(settings, "pilot_scene", "Pilot Scene")
            add_shot(settings, "pilot_scene", "shot_001", "Opening")

            exported = export_phase6_manifest(settings, "pilot_scene")

            manifest = json.loads(exported.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(
                manifest["supplemental_manifests"]["edit_timeline"],
                "manifests/storyboards/pilot_scene/edit_timeline_manifest.json",
            )
            self.assertEqual(
                manifest["supplemental_manifests"]["motion_clip_plan"],
                "manifests/storyboards/pilot_scene/motion_clip_plan.json",
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
