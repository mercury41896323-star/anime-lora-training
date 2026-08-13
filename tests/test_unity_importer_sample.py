from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class UnityImporterSampleTest(unittest.TestCase):
    def test_unity_importer_reads_selected_shots_manifest_shape(self) -> None:
        runtime = ROOT / "integrations" / "unity" / "Assets" / "AIAnimeStudio" / "Runtime" / "SelectedShotLibrary.cs"
        editor = ROOT / "integrations" / "unity" / "Assets" / "AIAnimeStudio" / "Editor" / "SelectedShotsManifestImporter.cs"
        timeline = ROOT / "integrations" / "unity" / "Assets" / "AIAnimeStudio" / "Editor" / "SelectedShotsTimelineBuilder.cs"

        runtime_text = runtime.read_text(encoding="utf-8")
        editor_text = editor.read_text(encoding="utf-8")
        timeline_text = timeline.read_text(encoding="utf-8")

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


if __name__ == "__main__":
    unittest.main()
