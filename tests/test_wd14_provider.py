from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from anime_studio.wd14_provider import load_selected_tags


class WD14ProviderTest(unittest.TestCase):
    def test_loads_selected_tags_csv(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "selected_tags.csv"
            path.write_text(
                "name,category\nblue_hair,0\nsample_character,4\nrating_safe,9\n",
                encoding="utf-8",
            )

            tags = load_selected_tags(path)

            self.assertEqual(tags[0].name, "blue hair")
            self.assertEqual(tags[0].category, "general")
            self.assertEqual(tags[1].category, "character")
            self.assertEqual(tags[2].category, "other")

    def test_missing_wd14_dependencies_raise_clear_error(self) -> None:
        import anime_studio.wd14_provider as wd14_provider

        with patch.dict("sys.modules", {"onnxruntime": None}):
            with self.assertRaisesRegex(RuntimeError, "WD14 tagging requires optional dependencies"):
                wd14_provider.generate_wd14_tags(Path("missing.png"), Path("models/wd14"))


if __name__ == "__main__":
    unittest.main()
