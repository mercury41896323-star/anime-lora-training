from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

from PIL import Image, ImageDraw
from psd_tools import PSDImage


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from anime_studio.high_resolution_layered import (
    assemble_layered_character,
    build_part_workflow,
    prepare_layered_character,
    remove_white_matte,
)
from anime_studio.settings import load_settings


class HighResolutionLayeredTest(unittest.TestCase):
    def test_white_background_is_removed_from_transparent_edges(self) -> None:
        image = Image.new("RGB", (1, 1), (255, 191, 191))
        alpha = Image.new("L", (1, 1), 128)

        result = remove_white_matte(image, alpha)

        red, green, blue, result_alpha = result.getpixel((0, 0))
        self.assertEqual(result_alpha, 128)
        self.assertGreaterEqual(red, 254)
        self.assertLess(green, 140)
        self.assertLess(blue, 140)

    def test_ipadapter_remains_opt_in(self) -> None:
        workflow = build_part_workflow(
            character_id="hero",
            part_id="face",
            input_refs={"reference": "face.png", "mask": "face_mask.png", "identity": "identity.png"},
            checkpoint_name="sd15.safetensors",
            lora_name="hero.safetensors",
            trigger_tag="hero",
            enable_ipadapter=False,
            ipadapter_preset="PLUS FACE (portraits)",
            ipadapter_weight=0.55,
        )

        self.assertEqual(workflow["9"]["inputs"]["model"], ["2", 0])
        self.assertNotIn("12", workflow)
        self.assertNotIn("13", workflow)
        self.assertNotIn("14", workflow)

    def test_prepares_part_workflows_and_assembles_cubism_psd(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = write_settings(root)
            rig_dir = root / "assets" / "processed" / "characters" / "hero" / "simple_2p5d_rig"
            masks_dir = rig_dir / "masks"
            controls_dir = rig_dir / "controls"
            masks_dir.mkdir(parents=True)
            controls_dir.mkdir(parents=True)
            reference = Image.new("RGB", (512, 768), (250, 248, 245))
            draw = ImageDraw.Draw(reference)
            draw.ellipse((196, 80, 316, 210), fill=(220, 190, 170))
            draw.rectangle((205, 205, 307, 540), fill=(80, 90, 120))
            reference_path = controls_dir / "reference.png"
            reference.save(reference_path)
            reference.crop((128, 20, 384, 276)).resize((512, 512)).save(controls_dir / "identity_reference.png")

            parts = [
                make_part(root, rig_dir, "head", 10, (196, 80, 317, 211)),
                make_part(root, rig_dir, "torso", 15, (205, 205, 308, 541)),
            ]
            write_json(
                rig_dir / "simple_2p5d_rig.json",
                {
                    "character_id": "hero",
                    "primary_reference": reference_path.relative_to(root).as_posix(),
                    "parts": parts,
                },
            )
            write_json(rig_dir / "live2d_bridge.json", {"character_id": "hero"})
            comfyui_input = root / "comfyui_input"

            prepared = prepare_layered_character(
                settings=settings,
                character_id="hero",
                high_res_reference=reference_path,
                comfyui_input_dir=comfyui_input,
                target_width=512,
                target_height=768,
                generation_limit=512,
                lora_name="hero.safetensors",
                enable_ipadapter=True,
            )

            manifest = json.loads(prepared.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(len(prepared.workflow_paths), 2)
            self.assertTrue(prepared.draft_composite_path.is_file())
            self.assertTrue(prepared.draft_psd_path.is_file())
            self.assertEqual(manifest["status"], "prepared")
            self.assertEqual(manifest["low_vram_strategy"], "sequential_part_generation")
            self.assertTrue(manifest["identity_control"]["ipadapter_enabled"])
            self.assertTrue(all(item["comfyui_inputs_copied"] for item in manifest["parts"]))
            workflow = json.loads(prepared.workflow_paths[0].read_text(encoding="utf-8"))
            self.assertEqual(workflow["8"]["class_type"], "SetLatentNoiseMask")
            self.assertEqual(workflow["14"]["class_type"], "IPAdapterAdvanced")
            self.assertEqual(workflow["9"]["inputs"]["model"], ["14", 0])

            fallback = assemble_layered_character(settings, "hero", allow_source_fallback=True)
            self.assertEqual(fallback.fallback_count, 2)
            fallback_manifest = json.loads(fallback.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(fallback_manifest["status"], "draft_assembled")
            self.assertEqual(fallback_manifest["steps"][1]["status"], "pending")

            generated_dir = root / "generated"
            generated_dir.mkdir()
            for part in manifest["parts"]:
                source = root / part["reference_input"]
                shutil.copy2(source, generated_dir / part["expected_result"])
            assembled = assemble_layered_character(settings, "hero", generated_dir=generated_dir)

            self.assertEqual(assembled.part_count, 2)
            self.assertEqual(assembled.fallback_count, 0)
            self.assertTrue(assembled.composite_path.is_file())
            self.assertTrue(assembled.seam_mask_path.is_file())
            self.assertTrue(assembled.cubism_psd_path.is_file())
            with Image.open(assembled.composite_path) as composite:
                self.assertEqual(composite.size, (512, 768))
            with Image.open(assembled.seam_mask_path) as seam_mask:
                self.assertIsNotNone(seam_mask.getbbox())
            psd = PSDImage.open(assembled.cubism_psd_path)
            self.assertEqual(psd.size, (512, 768))
            self.assertEqual({layer.name for layer in psd}, {"head", "torso", "seam_repair"})
            final_manifest = json.loads(assembled.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(final_manifest["status"], "assembled_pending_review")
            self.assertEqual(final_manifest["quality_review"]["status"], "pending_review")
            self.assertTrue(final_manifest["quality_review"]["required"])
            self.assertTrue(all(step["status"] == "completed" for step in final_manifest["steps"]))
            bridge = json.loads((rig_dir / "live2d_bridge.json").read_text(encoding="utf-8"))
            self.assertTrue(bridge["high_resolution_layered_manifest"].endswith("layered_character_manifest.json"))


def make_part(
    root: Path,
    rig_dir: Path,
    part_id: str,
    z_order: int,
    bounds: tuple[int, int, int, int],
) -> dict:
    mask = Image.new("L", (512, 768), 0)
    ImageDraw.Draw(mask).rectangle((bounds[0], bounds[1], bounds[2] - 1, bounds[3] - 1), fill=255)
    mask_path = rig_dir / "masks" / f"{part_id}.png"
    mask.save(mask_path)
    return {
        "part_id": part_id,
        "parent_id": "root",
        "z_order": z_order,
        "mask_image": mask_path.relative_to(root).as_posix(),
    }


def write_settings(root: Path):
    config_path = root / "config" / "local_6gb.json"
    config_path.parent.mkdir(parents=True)
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
