from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class UnityImporterSampleTest(unittest.TestCase):
    def test_unity_importer_reads_selected_shots_manifest_shape(self) -> None:
        runtime = ROOT / "integrations" / "unity" / "Assets" / "AIAnimeStudio" / "Runtime" / "SelectedShotLibrary.cs"
        phase6_runtime = ROOT / "integrations" / "unity" / "Assets" / "AIAnimeStudio" / "Runtime" / "Phase6StoryboardLibrary.cs"
        editor = ROOT / "integrations" / "unity" / "Assets" / "AIAnimeStudio" / "Editor" / "SelectedShotsManifestImporter.cs"
        timeline = ROOT / "integrations" / "unity" / "Assets" / "AIAnimeStudio" / "Editor" / "SelectedShotsTimelineBuilder.cs"
        phase6_importer = ROOT / "integrations" / "unity" / "Assets" / "AIAnimeStudio" / "Editor" / "Phase6ManifestImporter.cs"
        phase6_timeline = ROOT / "integrations" / "unity" / "Assets" / "AIAnimeStudio" / "Editor" / "Phase6TimelineBuilder.cs"

        runtime_text = runtime.read_text(encoding="utf-8")
        phase6_runtime_text = phase6_runtime.read_text(encoding="utf-8")
        editor_text = editor.read_text(encoding="utf-8")
        timeline_text = timeline.read_text(encoding="utf-8")
        phase6_importer_text = phase6_importer.read_text(encoding="utf-8")
        phase6_timeline_text = phase6_timeline.read_text(encoding="utf-8")

        self.assertIn("public sealed class SelectedShotLibrary", runtime_text)
        self.assertIn("public sealed class SelectedShotClip", runtime_text)
        self.assertIn("public static SelectedShotLibrary ImportManifest", editor_text)
        self.assertIn("selected_result", editor_text)
        self.assertIn("stored_path", editor_text)
        self.assertIn("timeline_clip_name", editor_text)
        self.assertIn("addressable_key", editor_text)
        self.assertIn("camera_work", editor_text)
        self.assertIn("lighting_setup", editor_text)
        self.assertIn("cameraLensMm", runtime_text)
        self.assertIn("lightingColorPalette", runtime_text)
        self.assertIn("clip.cameraFraming = shot.camera_work.framing", editor_text)
        self.assertIn("clip.lightingKeyLight = shot.lighting_setup.key_light", editor_text)
        self.assertIn("Assets/AIAnimeStudio/Storyboards/", editor_text)
        self.assertIn("Assets/AIAnimeStudio/ImportedShots/", editor_text)
        self.assertIn("public static PlayableDirector CreateTimeline", timeline_text)
        self.assertIn("TimelineAsset", timeline_text)
        self.assertIn("ActivationTrack", timeline_text)
        self.assertIn("CreateDefaultClip", timeline_text)
        self.assertIn("CreateShotCameraRig", timeline_text)
        self.assertIn("CreateShotLightingRig", timeline_text)
        self.assertIn("CreateCinemachineVirtualCamera", timeline_text)
        self.assertIn("EnsureCinemachineBrain", timeline_text)
        self.assertIn("FindCinemachineType", timeline_text)
        self.assertIn("CinemachineCamera", timeline_text)
        self.assertIn("CinemachineVirtualCamera", timeline_text)
        self.assertIn("VirtualCamera_", timeline_text)
        self.assertIn("CreateCameraMovementTrack", timeline_text)
        self.assertIn("BuildCameraMovementClip", timeline_text)
        self.assertIn("AnimationTrack", timeline_text)
        self.assertIn("AnimationPlayableAsset", timeline_text)
        self.assertIn("CameraMove_", timeline_text)
        self.assertIn("cameraMovement", runtime_text)
        self.assertIn("LensToFieldOfView", timeline_text)
        self.assertIn("LightType.Directional", timeline_text)
        self.assertIn("durationSeconds", timeline_text)
        self.assertIn("Assets/AIAnimeStudio/Timelines/", timeline_text)
        self.assertIn("public sealed class Phase6StoryboardLibrary", phase6_runtime_text)
        self.assertIn("public sealed class Phase6VoiceCue", phase6_runtime_text)
        self.assertIn("public sealed class Phase6LipSyncCue", phase6_runtime_text)
        self.assertIn("public sealed class Phase6SfxCue", phase6_runtime_text)
        self.assertIn("public sealed class Phase6MotionCue", phase6_runtime_text)
        self.assertIn("public static Phase6StoryboardLibrary ImportManifest", phase6_importer_text)
        self.assertIn("phase6_manifest.json", phase6_importer_text)
        self.assertIn("voice_cues", phase6_importer_text)
        self.assertIn("lip_sync_cues", phase6_importer_text)
        self.assertIn("sfx_cues", phase6_importer_text)
        self.assertIn("motion_cues", phase6_importer_text)
        self.assertIn("Assets/AIAnimeStudio/ImportedAudio/", phase6_importer_text)
        self.assertIn("public static PlayableDirector CreateTimeline", phase6_timeline_text)
        self.assertIn("Phase6_Voice_AudioTrack", phase6_timeline_text)
        self.assertIn("Phase6_SFX_AudioTrack", phase6_timeline_text)
        self.assertIn("Phase6_LipSync_SignalTrack", phase6_timeline_text)
        self.assertIn("AudioTrack", phase6_timeline_text)
        self.assertIn("SignalTrack", phase6_timeline_text)
        self.assertIn("AnimationTrack", phase6_timeline_text)
        self.assertIn("CreateClip<AudioPlayableAsset>", phase6_timeline_text)
        self.assertIn("CreateMarker<SignalEmitter>", phase6_timeline_text)
        self.assertIn("CreateTrack<AnimationTrack>", phase6_timeline_text)
        self.assertIn("Phase6MotionTarget_", phase6_timeline_text)
        self.assertIn("Phase6Animations", phase6_timeline_text)
        self.assertIn("Phase6Signals", phase6_timeline_text)


if __name__ == "__main__":
    unittest.main()
