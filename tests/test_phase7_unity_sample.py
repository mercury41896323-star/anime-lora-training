from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
UNITY_ROOT = ROOT / "integrations" / "unity" / "Assets" / "AIAnimeStudio"


class Phase7UnitySampleTest(unittest.TestCase):
    def test_edit_timeline_unity_sample_files_exist(self) -> None:
        expected = [
            UNITY_ROOT / "Runtime" / "EditTimelineLibrary.cs",
            UNITY_ROOT / "Editor" / "EditTimelineManifestImporter.cs",
            UNITY_ROOT / "Editor" / "EditTimelineBuilder.cs",
        ]

        for path in expected:
            self.assertTrue(path.exists(), f"Missing Unity sample file: {path}")

    def test_edit_timeline_importer_and_builder_wire_menu_items(self) -> None:
        importer = (UNITY_ROOT / "Editor" / "EditTimelineManifestImporter.cs").read_text(encoding="utf-8")
        builder = (UNITY_ROOT / "Editor" / "EditTimelineBuilder.cs").read_text(encoding="utf-8")
        runtime = (UNITY_ROOT / "Runtime" / "EditTimelineLibrary.cs").read_text(encoding="utf-8")

        self.assertIn("Import Edit Timeline Manifest", importer)
        self.assertIn("edit_timeline_manifest.json", importer)
        self.assertIn("EditTimelineLibrary", runtime)
        self.assertIn("Create Timeline From Edit Timeline Library", builder)
        self.assertIn("AudioTrack", builder)
        self.assertIn("SignalTrack", builder)
        self.assertIn("AnimationTrack", builder)
        self.assertIn("ActivationTrack", builder)
        self.assertIn("BuildAnimationClip", builder)
        self.assertIn("CreateProtectedRevisionFolder", builder)
        self.assertIn("timeline_build_report.json", builder)
        self.assertIn("preserveExistingTimelineEdits", runtime)
        self.assertIn("lastGeneratedTimelineAssetPath", runtime)


if __name__ == "__main__":
    unittest.main()
