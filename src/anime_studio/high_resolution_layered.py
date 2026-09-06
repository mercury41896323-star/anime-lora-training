from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import shutil
from typing import Any
import zlib

import numpy as np
from PIL import Image, ImageChops, ImageFilter, ImageOps
from psd_tools import PSDImage
from psd_tools.api.layers import PixelLayer

from .character_profile import validate_character_id
from .lora_registry import project_relative_path, utc_timestamp
from .settings import AppSettings, load_settings
from .simple_2p5d_rig import read_json, write_json


DEFAULT_TARGET_SIZE = (2048, 3072)
DEFAULT_GENERATION_LIMIT = 768
DEFAULT_OVERLAP_PIXELS = 12
PART_PROMPTS = {
    "hair_back": "back hair, clean anime hair strands, consistent silhouette",
    "head": "neck and head base, clean skin shading, consistent anatomy",
    "face": "anime face, preserve facial identity, clean line art",
    "eyes": "matching anime eyes, symmetric pupils, detailed irises",
    "mouth": "small anime mouth, clean lips, matching expression",
    "hair_front": "front hair and bangs, detailed strands, matching hairstyle",
    "torso": "upper body and costume, clean folds, consistent proportions",
    "left_arm": "left arm and hand, correct anatomy, matching costume",
    "right_arm": "right arm and hand, correct anatomy, matching costume",
    "hips": "waist, hips and costume transition, clean fabric folds",
    "left_leg": "left leg and foot, correct anatomy, matching footwear",
    "right_leg": "right leg and foot, correct anatomy, matching footwear",
}


@dataclass(frozen=True)
class LayeredPrepareResult:
    manifest_path: Path
    workflow_paths: tuple[Path, ...]
    draft_composite_path: Path
    draft_psd_path: Path
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class LayeredAssembleResult:
    manifest_path: Path
    composite_path: Path
    seam_mask_path: Path
    cubism_psd_path: Path
    part_count: int
    fallback_count: int


def prepare_layered_character(
    settings: AppSettings,
    character_id: str,
    high_res_reference: str | Path | None = None,
    comfyui_input_dir: str | Path | None = None,
    target_width: int = DEFAULT_TARGET_SIZE[0],
    target_height: int = DEFAULT_TARGET_SIZE[1],
    generation_limit: int = DEFAULT_GENERATION_LIMIT,
    checkpoint_name: str = "sd15.safetensors",
    lora_name: str | None = None,
    trigger_tag: str | None = None,
    enable_ipadapter: bool = False,
    ipadapter_preset: str = "PLUS FACE (portraits)",
    ipadapter_weight: float = 0.55,
) -> LayeredPrepareResult:
    validate_character_id(character_id)
    validate_dimensions(target_width, target_height, generation_limit)
    rig_dir = settings.assets.processed / "characters" / character_id / "simple_2p5d_rig"
    rig_path = rig_dir / "simple_2p5d_rig.json"
    rig = read_json(rig_path)
    if not rig:
        raise FileNotFoundError(f"Simple 2.5D rig does not exist: {rig_path}")

    output_root = settings.assets.processed / "characters" / character_id / "high_resolution_layered"
    inputs_dir = output_root / "inputs"
    workflows_dir = output_root / "workflows"
    generated_dir = output_root / "generated"
    inputs_dir.mkdir(parents=True, exist_ok=True)
    workflows_dir.mkdir(parents=True, exist_ok=True)
    generated_dir.mkdir(parents=True, exist_ok=True)

    source_path = resolve_source_reference(settings, rig, high_res_reference)
    with Image.open(source_path) as source_image:
        source = fit_reference_to_canvas(source_image.convert("RGB"), (target_width, target_height))
        source_size = source_image.size
    reference_path = inputs_dir / "high_resolution_reference.png"
    source.save(reference_path)

    identity_source = rig_dir / "controls" / "identity_reference.png"
    identity_path = inputs_dir / "identity_reference.png"
    if identity_source.is_file():
        shutil.copy2(identity_source, identity_path)
    else:
        source.crop((0, 0, target_width, min(target_height, target_width))).resize((512, 512)).save(identity_path)

    workflow_paths: list[Path] = []
    part_entries: list[dict[str, Any]] = []
    for part in sorted(rig.get("parts", []), key=lambda item: int(item.get("z_order", 0))):
        entry, workflow_path = prepare_part(
            settings=settings,
            character_id=character_id,
            output_root=output_root,
            inputs_dir=inputs_dir,
            workflows_dir=workflows_dir,
            source=source,
            part=dict(part),
            generation_limit=generation_limit,
            comfyui_input_dir=comfyui_input_dir,
            checkpoint_name=checkpoint_name,
            lora_name=lora_name or f"{character_id}.safetensors",
            trigger_tag=trigger_tag or character_id,
            identity_path=identity_path,
            enable_ipadapter=enable_ipadapter,
            ipadapter_preset=ipadapter_preset,
            ipadapter_weight=ipadapter_weight,
        )
        workflow_paths.append(workflow_path)
        part_entries.append(entry)

    warnings = build_source_warnings(source_size, (target_width, target_height), part_entries)
    manifest_path = output_root / "layered_character_manifest.json"
    manifest = {
        "schema_version": 1,
        "manifest_type": "high_resolution_layered_character",
        "generated_at": utc_timestamp(),
        "character_id": character_id,
        "status": "prepared",
        "source_rig": project_relative_path(settings, rig_path),
        "source_reference": project_relative_path(settings, source_path),
        "prepared_reference": project_relative_path(settings, reference_path),
        "source_size": list(source_size),
        "target_size": [target_width, target_height],
        "generation_limit": generation_limit,
        "low_vram_strategy": "sequential_part_generation",
        "comfyui_inputs_copied": comfyui_input_dir not in (None, ""),
        "identity_control": {
            "ipadapter_enabled": enable_ipadapter,
            "preset": ipadapter_preset,
            "weight": ipadapter_weight,
        },
        "parts": part_entries,
        "generated_results_dir": project_relative_path(settings, generated_dir),
        "assembly": {
            "transparent_parts_dir": project_relative_path(settings, output_root / "transparent_parts"),
            "composite": project_relative_path(settings, output_root / "layered_composite.png"),
            "seam_mask": project_relative_path(settings, output_root / "seam_repair_mask.png"),
            "cubism_psd": project_relative_path(settings, output_root / f"{character_id}_highres_cubism.psd"),
        },
        "quality_warnings": warnings,
        "quality_review": {
            "status": "not_ready",
            "required": True,
            "notes": [],
        },
        "steps": [
            {"name": "part_workflows", "status": "completed"},
            {"name": "comfyui_part_generation", "status": "pending"},
            {"name": "transparentize", "status": "pending"},
            {"name": "high_resolution_composite", "status": "pending"},
            {"name": "seam_repair", "status": "pending"},
            {"name": "cubism_psd", "status": "pending"},
        ],
    }
    write_json(manifest_path, manifest)
    attach_to_live2d_bridge(settings, rig_dir, manifest_path)
    draft = assemble_layered_character(
        settings,
        character_id,
        generated_dir=generated_dir,
        allow_source_fallback=True,
        output_prefix="draft_",
    )
    manifest = read_json(manifest_path)
    manifest["status"] = "prepared"
    manifest["steps"][1]["status"] = "pending"
    manifest["draft_outputs"] = {
        "composite": project_relative_path(settings, draft.composite_path),
        "cubism_psd": project_relative_path(settings, draft.cubism_psd_path),
    }
    write_json(manifest_path, manifest)
    return LayeredPrepareResult(
        manifest_path=manifest_path,
        workflow_paths=tuple(workflow_paths),
        draft_composite_path=draft.composite_path,
        draft_psd_path=draft.cubism_psd_path,
        warnings=tuple(warnings),
    )


def prepare_part(
    settings: AppSettings,
    character_id: str,
    output_root: Path,
    inputs_dir: Path,
    workflows_dir: Path,
    source: Image.Image,
    part: dict[str, Any],
    generation_limit: int,
    comfyui_input_dir: str | Path | None,
    checkpoint_name: str,
    lora_name: str,
    trigger_tag: str,
    identity_path: Path,
    enable_ipadapter: bool,
    ipadapter_preset: str,
    ipadapter_weight: float,
) -> tuple[dict[str, Any], Path]:
    part_id = str(part.get("part_id", ""))
    mask_path = resolve_project_path(settings, str(part.get("mask_image", "")))
    if not mask_path.is_file():
        raise FileNotFoundError(f"Part mask does not exist: {mask_path}")
    with Image.open(mask_path) as mask_image:
        mask = mask_image.convert("L").resize(source.size, Image.Resampling.NEAREST)
    bounds = mask.getbbox()
    if bounds is None:
        raise ValueError(f"Part mask is empty: {part_id}")
    padded_bounds = pad_bounds(bounds, source.size, ratio=0.16)
    source_crop = source.crop(padded_bounds)
    mask_crop = mask.crop(padded_bounds)
    generation_size = fit_generation_size(source_crop.size, generation_limit)
    source_crop = source_crop.resize(generation_size, Image.Resampling.LANCZOS)
    mask_crop = mask_crop.resize(generation_size, Image.Resampling.NEAREST)
    base_path = inputs_dir / f"{part_id}_reference.png"
    part_mask_path = inputs_dir / f"{part_id}_mask.png"
    source_crop.save(base_path)
    mask_crop.save(part_mask_path)

    input_refs, copied = copy_comfyui_inputs(
        character_id,
        comfyui_input_dir,
        {"reference": base_path, "mask": part_mask_path, "identity": identity_path},
    )
    workflow = build_part_workflow(
        character_id=character_id,
        part_id=part_id,
        input_refs=input_refs,
        checkpoint_name=checkpoint_name,
        lora_name=lora_name,
        trigger_tag=trigger_tag,
        enable_ipadapter=enable_ipadapter,
        ipadapter_preset=ipadapter_preset,
        ipadapter_weight=ipadapter_weight,
    )
    workflow_path = workflows_dir / f"{part_id}.json"
    write_json(workflow_path, workflow)
    return (
        {
            "part_id": part_id,
            "parent_id": str(part.get("parent_id", "root")),
            "z_order": int(part.get("z_order", 0)),
            "target_bounds": list(padded_bounds),
            "generation_size": list(generation_size),
            "reference_input": project_relative_path(settings, base_path),
            "mask_input": project_relative_path(settings, part_mask_path),
            "workflow": project_relative_path(settings, workflow_path),
            "comfyui_inputs_copied": copied,
            "expected_result": f"{part_id}.png",
            "prompt": PART_PROMPTS.get(part_id, f"{part_id}, clean anime character part"),
        },
        workflow_path,
    )


def build_part_workflow(
    character_id: str,
    part_id: str,
    input_refs: dict[str, str],
    checkpoint_name: str,
    lora_name: str,
    trigger_tag: str,
    enable_ipadapter: bool,
    ipadapter_preset: str,
    ipadapter_weight: float,
) -> dict[str, Any]:
    model_ref = ["14", 0] if enable_ipadapter else ["2", 0]
    workflow: dict[str, Any] = {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": checkpoint_name}},
        "2": {
            "class_type": "LoraLoader",
            "inputs": {
                "model": ["1", 0],
                "clip": ["1", 1],
                "lora_name": lora_name,
                "strength_model": 0.7,
                "strength_clip": 0.7,
            },
        },
        "3": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "clip": ["2", 1],
                "text": f"{trigger_tag}, {PART_PROMPTS.get(part_id, part_id)}, same character, high detail, clean line art",
            },
        },
        "4": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "clip": ["2", 1],
                "text": "low quality, blurry, mismatched character, extra limbs, duplicate parts, text, watermark, background detail",
            },
        },
        "5": {"class_type": "LoadImage", "inputs": {"image": input_refs["reference"]}},
        "6": {"class_type": "VAEEncode", "inputs": {"pixels": ["5", 0], "vae": ["1", 2]}},
        "7": {"class_type": "LoadImageMask", "inputs": {"image": input_refs["mask"], "channel": "red"}},
        "8": {"class_type": "SetLatentNoiseMask", "inputs": {"samples": ["6", 0], "mask": ["7", 0]}},
        "9": {
            "class_type": "KSampler",
            "inputs": {
                "model": model_ref,
                "positive": ["3", 0],
                "negative": ["4", 0],
                "latent_image": ["8", 0],
                "seed": zlib.crc32(f"{character_id}:{part_id}".encode("utf-8")),
                "steps": 20,
                "cfg": 6.0,
                "sampler_name": "dpmpp_2m",
                "scheduler": "karras",
                "denoise": 0.55,
            },
        },
        "10": {"class_type": "VAEDecode", "inputs": {"samples": ["9", 0], "vae": ["1", 2]}},
        "11": {
            "class_type": "SaveImage",
            "inputs": {"images": ["10", 0], "filename_prefix": f"highres_layered/{character_id}_{part_id}"},
        },
    }
    if enable_ipadapter:
        workflow["12"] = {"class_type": "LoadImage", "inputs": {"image": input_refs["identity"]}}
        workflow["13"] = {
            "class_type": "IPAdapterUnifiedLoader",
            "inputs": {"model": ["2", 0], "preset": ipadapter_preset},
        }
        workflow["14"] = {
            "class_type": "IPAdapterAdvanced",
            "inputs": {
                "model": ["13", 0],
                "ipadapter": ["13", 1],
                "image": ["12", 0],
                "weight": ipadapter_weight,
                "weight_type": "linear",
                "combine_embeds": "average",
                "start_at": 0.0,
                "end_at": 0.85,
                "embeds_scaling": "V only",
            },
        }
    return workflow


def assemble_layered_character(
    settings: AppSettings,
    character_id: str,
    generated_dir: str | Path | None = None,
    allow_source_fallback: bool = False,
    overlap_pixels: int = DEFAULT_OVERLAP_PIXELS,
    output_prefix: str = "",
) -> LayeredAssembleResult:
    validate_character_id(character_id)
    output_root = settings.assets.processed / "characters" / character_id / "high_resolution_layered"
    manifest_path = output_root / "layered_character_manifest.json"
    manifest = read_json(manifest_path)
    if not manifest:
        raise FileNotFoundError(f"Layered character manifest does not exist: {manifest_path}")
    target_size = tuple(int(value) for value in manifest["target_size"])
    result_dir = Path(generated_dir) if generated_dir else output_root / "generated"
    transparent_dir = output_root / f"{output_prefix}transparent_parts"
    transparent_dir.mkdir(parents=True, exist_ok=True)
    composite = Image.new("RGBA", target_size, (0, 0, 0, 0))
    seam_mask = Image.new("L", target_size, 0)
    silhouette_union = Image.new("L", target_size, 0)
    layers: list[tuple[int, str, Image.Image]] = []
    fallback_parts: list[str] = []

    for part in sorted(manifest["parts"], key=lambda item: int(item["z_order"])):
        part_id = str(part["part_id"])
        generated_path = locate_generated_part(result_dir, part_id)
        if generated_path is None:
            if not allow_source_fallback:
                raise FileNotFoundError(f"Generated part result is missing: {result_dir / (part_id + '.png')}")
            generated_path = resolve_project_path(settings, str(part["reference_input"]))
            fallback_parts.append(part_id)
        mask_path = resolve_project_path(settings, str(part["mask_input"]))
        bounds = tuple(int(value) for value in part["target_bounds"])
        target_crop_size = (bounds[2] - bounds[0], bounds[3] - bounds[1])
        with Image.open(generated_path) as generated_image:
            generated = generated_image.convert("RGBA").resize(target_crop_size, Image.Resampling.LANCZOS)
        with Image.open(mask_path) as mask_image:
            mask = mask_image.convert("L").resize(target_crop_size, Image.Resampling.NEAREST)
        expanded_mask = expand_and_feather_mask(mask, overlap_pixels)
        generated = remove_white_matte(generated, expanded_mask)
        full_layer = Image.new("RGBA", target_size, (0, 0, 0, 0))
        full_layer.alpha_composite(generated, (bounds[0], bounds[1]))
        full_part_mask = Image.new("L", target_size, 0)
        full_part_mask.paste(mask, (bounds[0], bounds[1]))
        silhouette_union = ImageChops.lighter(silhouette_union, full_part_mask)
        part_path = transparent_dir / f"{part_id}.png"
        full_layer.save(part_path)
        composite.alpha_composite(full_layer)
        layers.append((int(part["z_order"]), part_id, full_layer))
        boundary = build_boundary_mask(mask, max(3, overlap_pixels // 2))
        full_boundary = Image.new("L", target_size, 0)
        full_boundary.paste(boundary, (bounds[0], bounds[1]))
        seam_mask = ImageChops.lighter(seam_mask, full_boundary)

    silhouette_boundary = build_boundary_mask(silhouette_union, max(3, overlap_pixels // 2))
    seam_mask = ImageChops.subtract(seam_mask, silhouette_boundary)
    seam_mask = ImageChops.multiply(seam_mask, silhouette_union)
    reference_path = resolve_project_path(settings, str(manifest["prepared_reference"]))
    with Image.open(reference_path) as source_image:
        seam_source = source_image.convert("RGBA").resize(target_size, Image.Resampling.LANCZOS)
    seam_mask = seam_mask.filter(ImageFilter.GaussianBlur(radius=max(2, overlap_pixels // 3)))
    seam_layer = Image.new("RGBA", target_size, (0, 0, 0, 0))
    seam_layer.paste(seam_source, (0, 0), seam_mask)
    repaired = composite.copy()
    repaired.alpha_composite(seam_layer)

    composite_path = output_root / f"{output_prefix}layered_composite.png"
    seam_mask_path = output_root / f"{output_prefix}seam_repair_mask.png"
    cubism_psd_path = output_root / f"{output_prefix}{character_id}_highres_cubism.psd"
    repaired.save(composite_path)
    seam_mask.save(seam_mask_path)
    build_layered_psd(target_size, layers, seam_layer, cubism_psd_path)

    if not output_prefix:
        manifest["status"] = "draft_assembled" if fallback_parts else "assembled_pending_review"
        for index, step in enumerate(manifest["steps"][1:], start=1):
            step["status"] = "pending" if fallback_parts and index == 1 else "completed"
        manifest["quality_review"] = {
            "status": "not_ready" if fallback_parts else "pending_review",
            "required": True,
            "notes": [],
        }
        manifest["assembly"].update(
            {
                "composite": project_relative_path(settings, composite_path),
                "seam_mask": project_relative_path(settings, seam_mask_path),
                "cubism_psd": project_relative_path(settings, cubism_psd_path),
                "part_count": len(layers),
                "fallback_parts": fallback_parts,
                "seam_repair": "reference_guided_boundary_blend",
            }
        )
        write_json(manifest_path, manifest)
    return LayeredAssembleResult(
        manifest_path=manifest_path,
        composite_path=composite_path,
        seam_mask_path=seam_mask_path,
        cubism_psd_path=cubism_psd_path,
        part_count=len(layers),
        fallback_count=len(fallback_parts),
    )


def build_layered_psd(
    canvas_size: tuple[int, int],
    layers: list[tuple[int, str, Image.Image]],
    seam_layer: Image.Image,
    output_path: Path,
) -> None:
    psd = PSDImage.new("RGBA", canvas_size, (0, 0, 0, 0))
    for _, part_id, image in sorted(layers, key=lambda item: item[0]):
        append_cropped_psd_layer(psd, image, part_id)
    append_cropped_psd_layer(psd, seam_layer, "seam_repair")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    psd.save(output_path)


def append_cropped_psd_layer(psd: PSDImage, image: Image.Image, name: str) -> None:
    bounds = image.getchannel("A").getbbox()
    if bounds is None:
        return
    psd.append(PixelLayer.frompil(image.crop(bounds), parent=psd, name=name, top=bounds[1], left=bounds[0]))


def copy_comfyui_inputs(
    character_id: str,
    comfyui_input_dir: str | Path | None,
    sources: dict[str, Path],
) -> tuple[dict[str, str], bool]:
    if comfyui_input_dir in (None, ""):
        return {key: str(path) for key, path in sources.items()}, False
    target_dir = Path(comfyui_input_dir) / "anime_studio" / character_id / "highres_layered"
    target_dir.mkdir(parents=True, exist_ok=True)
    refs: dict[str, str] = {}
    for key, source in sources.items():
        target = target_dir / source.name
        shutil.copy2(source, target)
        refs[key] = f"anime_studio/{character_id}/highres_layered/{target.name}"
    return refs, True


def resolve_source_reference(settings: AppSettings, rig: dict[str, Any], value: str | Path | None) -> Path:
    if value not in (None, ""):
        path = Path(value)
    else:
        path = resolve_project_path(settings, str(rig.get("primary_reference", "")))
    if not path.is_file():
        raise FileNotFoundError(f"High-resolution reference does not exist: {path}")
    return path.resolve()


def resolve_project_path(settings: AppSettings, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else settings.project_root / path


def validate_dimensions(width: int, height: int, generation_limit: int) -> None:
    if width < 512 or height < 512:
        raise ValueError("High-resolution target must be at least 512x512.")
    if generation_limit < 256 or generation_limit > 1024:
        raise ValueError("Generation limit must be between 256 and 1024 pixels.")


def fit_reference_to_canvas(image: Image.Image, canvas_size: tuple[int, int]) -> Image.Image:
    fitted = ImageOps.contain(image, canvas_size, Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", canvas_size, (255, 255, 255))
    left = (canvas_size[0] - fitted.width) // 2
    top = (canvas_size[1] - fitted.height) // 2
    canvas.paste(fitted, (left, top))
    return canvas


def pad_bounds(
    bounds: tuple[int, int, int, int],
    canvas_size: tuple[int, int],
    ratio: float,
) -> tuple[int, int, int, int]:
    left, top, right, bottom = bounds
    padding = max(8, int(max(right - left, bottom - top) * ratio))
    return (
        max(0, left - padding),
        max(0, top - padding),
        min(canvas_size[0], right + padding),
        min(canvas_size[1], bottom + padding),
    )


def fit_generation_size(size: tuple[int, int], limit: int) -> tuple[int, int]:
    minimum_detail = 256
    scale = min(limit / max(size), max(1.0, minimum_detail / min(size)))
    width = max(64, int(round(size[0] * scale / 64)) * 64)
    height = max(64, int(round(size[1] * scale / 64)) * 64)
    return min(limit, width), min(limit, height)


def expand_and_feather_mask(mask: Image.Image, pixels: int) -> Image.Image:
    softened = mask.filter(ImageFilter.GaussianBlur(radius=max(1, pixels / 3)))
    return ImageChops.darker(mask, softened)


def remove_white_matte(image: Image.Image, alpha: Image.Image) -> Image.Image:
    rgb = np.asarray(image.convert("RGB"), dtype=np.float32)
    alpha_values = np.asarray(alpha.convert("L"), dtype=np.float32) / 255.0
    safe_alpha = np.maximum(alpha_values, 1.0 / 255.0)
    foreground = (rgb - 255.0 * (1.0 - alpha_values[..., None])) / safe_alpha[..., None]
    foreground = np.clip(foreground, 0.0, 255.0).astype(np.uint8)
    foreground[alpha_values == 0] = 0
    rgba = np.dstack((foreground, np.asarray(alpha, dtype=np.uint8)))
    return Image.fromarray(rgba, mode="RGBA")


def build_boundary_mask(mask: Image.Image, pixels: int) -> Image.Image:
    size = max(3, pixels * 2 + 1)
    outer = mask.filter(ImageFilter.MaxFilter(size=size))
    inner = mask.filter(ImageFilter.MinFilter(size=size))
    return ImageChops.subtract(outer, inner)


def locate_generated_part(directory: Path, part_id: str) -> Path | None:
    direct = directory / f"{part_id}.png"
    if direct.is_file():
        return direct
    matches = sorted(directory.glob(f"*_{part_id}_*.png"), key=lambda path: path.stat().st_mtime, reverse=True)
    return matches[0] if matches else None


def build_source_warnings(
    source_size: tuple[int, int],
    target_size: tuple[int, int],
    parts: list[dict[str, Any]],
) -> list[str]:
    warnings = []
    if source_size[0] < target_size[0] or source_size[1] < target_size[1]:
        warnings.append(
            f"Source {source_size[0]}x{source_size[1]} is smaller than target {target_size[0]}x{target_size[1]}; detail cannot be recovered by resizing."
        )
    estimated_source_sizes = [
        min(
            (item["target_bounds"][2] - item["target_bounds"][0]) * source_size[0] / target_size[0],
            (item["target_bounds"][3] - item["target_bounds"][1]) * source_size[1] / target_size[1],
        )
        for item in parts
    ]
    smallest = min(estimated_source_sizes) if estimated_source_sizes else 0
    if smallest < 256:
        warnings.append("One or more source parts are very small; provide separate high-resolution full-body and face references.")
    return warnings


def attach_to_live2d_bridge(settings: AppSettings, rig_dir: Path, manifest_path: Path) -> None:
    bridge_path = rig_dir / "live2d_bridge.json"
    bridge = read_json(bridge_path)
    if not bridge:
        return
    bridge["high_resolution_layered_manifest"] = project_relative_path(settings, manifest_path)
    write_json(bridge_path, bridge)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="anime-highres-layered",
        description="Prepare sequential ComfyUI part generation and assemble a high-resolution layered Cubism PSD.",
    )
    parser.add_argument("--config", default="config/local_6gb.json")
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare = subparsers.add_parser("prepare", help="Create part inputs, workflows, and a source-based draft.")
    prepare.add_argument("--character-id", required=True)
    prepare.add_argument("--high-res-reference")
    prepare.add_argument("--comfyui-input-dir")
    prepare.add_argument("--target-width", type=int, default=DEFAULT_TARGET_SIZE[0])
    prepare.add_argument("--target-height", type=int, default=DEFAULT_TARGET_SIZE[1])
    prepare.add_argument("--generation-limit", type=int, default=DEFAULT_GENERATION_LIMIT)
    prepare.add_argument("--checkpoint", default="sd15.safetensors")
    prepare.add_argument("--lora-name")
    prepare.add_argument("--trigger-tag")
    prepare.add_argument("--enable-ipadapter", action="store_true")
    prepare.add_argument("--ipadapter-preset", default="PLUS FACE (portraits)")
    prepare.add_argument("--ipadapter-weight", type=float, default=0.55)
    assemble = subparsers.add_parser("assemble", help="Transparentize generated parts, repair seams, and export PSD.")
    assemble.add_argument("--character-id", required=True)
    assemble.add_argument("--generated-dir")
    assemble.add_argument("--allow-source-fallback", action="store_true")
    assemble.add_argument("--overlap-pixels", type=int, default=DEFAULT_OVERLAP_PIXELS)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = load_settings(args.config)
    if args.command == "prepare":
        result = prepare_layered_character(
            settings=settings,
            character_id=args.character_id,
            high_res_reference=args.high_res_reference,
            comfyui_input_dir=args.comfyui_input_dir,
            target_width=args.target_width,
            target_height=args.target_height,
            generation_limit=args.generation_limit,
            checkpoint_name=args.checkpoint,
            lora_name=args.lora_name,
            trigger_tag=args.trigger_tag,
            enable_ipadapter=args.enable_ipadapter,
            ipadapter_preset=args.ipadapter_preset,
            ipadapter_weight=args.ipadapter_weight,
        )
        print(f"Layered manifest: {result.manifest_path}")
        print(f"Part workflows: {len(result.workflow_paths)}")
        print(f"Draft composite: {result.draft_composite_path}")
        print(f"Draft Cubism PSD: {result.draft_psd_path}")
        for warning in result.warnings:
            print(f"Warning: {warning}")
        return 0
    result = assemble_layered_character(
        settings=settings,
        character_id=args.character_id,
        generated_dir=args.generated_dir,
        allow_source_fallback=args.allow_source_fallback,
        overlap_pixels=args.overlap_pixels,
    )
    print(f"Composite: {result.composite_path}")
    print(f"Seam mask: {result.seam_mask_path}")
    print(f"Cubism PSD: {result.cubism_psd_path}")
    print(f"Parts: {result.part_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
