from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

from PIL import Image, ImageDraw
from psd_tools import PSDImage


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from anime_studio.live2d_adjustment import build_live2d_adjustment_package
from anime_studio.settings import load_settings


class Live2DAdjustmentTest(unittest.TestCase):
    def test_builds_dense_mesh_deformers_pivots_and_preview(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = write_settings(root)
            rig_dir = root / "assets" / "processed" / "characters" / "hero" / "simple_2p5d_rig"
            rig_dir.mkdir(parents=True)
            reference = rig_dir / "reference.png"
            image = Image.new("RGB", (512, 768), (255, 255, 255))
            draw = ImageDraw.Draw(image)
            draw.ellipse((190, 70, 320, 220), fill=(210, 190, 170))
            draw.rectangle((220, 210, 290, 520), fill=(60, 60, 70))
            image.save(reference)
            parts = [
                build_part("head", "root", 10, (0.35, 0.08, 0.65, 0.30)),
                build_part("torso", "root", 15, (0.38, 0.27, 0.62, 0.68)),
            ]
            write_part_image(root, "head", (190, 70, 321, 221), (210, 190, 170, 255))
            write_part_image(root, "torso", (220, 210, 291, 521), (60, 60, 70, 255))
            write_json(
                rig_dir / "simple_2p5d_rig.json",
                {
                    "character_id": "hero",
                    "primary_reference": reference.relative_to(root).as_posix(),
                    "coordinate_system": {"normalized": True, "origin": "top_left"},
                    "parts": parts,
                },
            )
            write_json(rig_dir / "live2d_bridge.json", {"character_id": "hero", "art_meshes": []})

            result = build_live2d_adjustment_package(
                settings,
                "hero",
                overrides={"parts": {"head": {"pivot": {"x": 0.51, "y": 0.29}, "columns": 8}}},
            )

            adjustment = json.loads(result.adjustment_path.read_text(encoding="utf-8"))
            bridge = json.loads(result.bridge_path.read_text(encoding="utf-8"))
            head = next(item for item in adjustment["art_meshes"] if item["part_id"] == "head")
            self.assertEqual(result.art_mesh_count, 2)
            self.assertEqual(result.deformer_count, 20)
            self.assertEqual(len(result.pose_preview_paths), 2)
            self.assertTrue(all(path.is_file() for path in result.pose_preview_paths))
            self.assertEqual(head["pivot"], {"x": 0.51, "y": 0.29})
            self.assertEqual(head["mesh"]["columns"], 8)
            self.assertGreater(len(head["mesh"]["triangles"]), 2)
            self.assertTrue(result.preview_path.is_file())
            self.assertTrue(result.cubism_psd_path.is_file())
            psd = PSDImage.open(result.cubism_psd_path)
            self.assertEqual(psd.size, (512, 768))
            self.assertEqual({layer.name: tuple(layer.bbox) for layer in psd}, {
                "head": (190, 70, 321, 221),
                "torso": (220, 210, 291, 521),
            })
            self.assertEqual(bridge["status"], "cubism_import_package_ready")
            self.assertTrue(bridge["cubism_import_psd"].endswith("hero_live2d_import.psd"))
            self.assertEqual(len(bridge["parameter_bindings"]), 8)
            self.assertEqual(
                [item["preset_id"] for item in adjustment["pose_tests"]],
                ["relaxed_standing", "small_step"],
            )
            self.assertEqual(bridge["pose_tests"], adjustment["pose_tests"])
            for preview_path in result.pose_preview_paths:
                with Image.open(preview_path) as pose_preview:
                    self.assertEqual(pose_preview.size, (512, 768))
            deformers = {item["id"]: item for item in adjustment["deformers"]}
            self.assertEqual(deformers["Warp_HairBack"]["parent"], "Rotation_Head")
            self.assertEqual(deformers["Warp_Head"]["parent"], "Rotation_Head")
            self.assertEqual(deformers["Warp_Face"]["parent"], "Warp_Head")
            self.assertEqual(deformers["Warp_Eyes"]["parent"], "Warp_Face")
            self.assertEqual(deformers["Warp_Mouth"]["parent"], "Warp_Face")
            self.assertEqual(deformers["Warp_HairFront"]["parent"], "Warp_Head")


def build_part(part_id: str, parent_id: str, z_order: int, bounds: tuple[float, float, float, float]) -> dict:
    left, top, right, bottom = bounds
    return {
        "part_id": part_id,
        "parent_id": parent_id,
        "z_order": z_order,
        "transparent_image": f"parts/{part_id}.png",
        "mask_image": f"masks/{part_id}.png",
        "mesh": {
            "vertices": [[left, top], [right, top], [right, bottom], [left, bottom]],
            "triangles": [[0, 1, 2], [0, 2, 3]],
        },
    }


def write_part_image(root: Path, part_id: str, bounds: tuple[int, int, int, int], color: tuple[int, int, int, int]) -> None:
    image_path = root / "parts" / f"{part_id}.png"
    mask_path = root / "masks" / f"{part_id}.png"
    image_path.parent.mkdir(parents=True, exist_ok=True)
    mask_path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGBA", (512, 768), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle((bounds[0], bounds[1], bounds[2] - 1, bounds[3] - 1), fill=color)
    image.save(image_path)
    image.getchannel("A").save(mask_path)


def write_settings(root: Path):
    config_dir = root / "config"
    config_dir.mkdir(parents=True)
    config_path = config_dir / "local_6gb.json"
    write_json(
        config_path,
        {
            "runtime": {"name": "test", "max_vram_gb": 6.0, "target_gpu_utilization": 0.8, "target_gpu_temp_c": 60},
            "assets": {"raw_dir": "assets/raw", "processed_dir": "assets/processed"},
            "datasets": {"lora_dir": "datasets/lora"},
            "models": {"wd14_dir": "models/wd14"},
            "asset_types": {"image_extensions": [".png"], "video_extensions": [".mp4"]},
        },
    )
    return load_settings(config_path)


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
