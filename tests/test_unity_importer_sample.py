from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class UnityImporterSampleTest(unittest.TestCase):
    def test_unity_importer_reads_selected_shots_manifest_shape(self) -> None:
        runtime = ROOT / "integrations" / "unity" / "Assets" / "AIAnimeStudio" / "Runtime" / "SelectedShotLibrary.cs"
        editor = ROOT / "integrations" / "unity" / "Assets" / "AIAnimeStudio" / "Editor" / "SelectedShotsManifestImporter.cs"

        runtime_text = runtime.read_text(encoding="utf-8")
        editor_text = editor.read_text(encoding="utf-8")

        self.assertIn("public sealed class SelectedShotLibrary", runtime_text)
        self.assertIn("public sealed class SelectedShotClip", runtime_text)
        self.assertIn("public static SelectedShotLibrary ImportManifest", editor_text)
        self.assertIn("selected_result", editor_text)
        self.assertIn("stored_path", editor_text)
        self.assertIn("timeline_clip_name", editor_text)
        self.assertIn("addressable_key", editor_text)
        self.assertIn("camera_work", editor_text)
        self.assertIn("lighting_setup", editor_text)
        self.assertIn("Assets/AIAnimeStudio/Storyboards/", editor_text)
        self.assertIn("Assets/AIAnimeStudio/ImportedShots/", editor_text)


if __name__ == "__main__":
    unittest.main()
