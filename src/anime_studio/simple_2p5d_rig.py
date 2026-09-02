from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, replace
import json
from pathlib import Path
import shutil
from statistics import median
from typing import Any

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps

from .character_2p5d_definition import generate_character_2p5d_definition
from .character_master_asset import import_character_master_asset
from .character_profile import (
    character_profile_path,
    create_character_profile,
    default_character_profile_data,
    link_character_simple_rig,
    load_character_profile,
    save_character_profile,
    validate_character_id,
)
from .lora_registry import project_relative_path, utc_timestamp
from .settings import AppSettings, load_settings


RIG_MANIFEST_TYPE = "simple_2p5d_rig"
CONTROL_BUNDLE_TYPE = "simple_2p5d_control_bundle"
PIPELINE_MANIFEST_TYPE = "simple_2p5d_rig_pipeline"
TEMPLATE_ID = "simple_2p5d_v1"


PART_SPECS = (
    ("hair_back", "root", 0, (0.05, 0.00, 0.95, 0.26), (0.50, 0.18)),
    ("head", "root", 10, (0.12, 0.00, 0.88, 0.28), (0.50, 0.25)),
    ("face", "head", 20, (0.22, 0.05, 0.78, 0.25), (0.50, 0.24)),
    ("eyes", "face", 30, (0.28, 0.11, 0.72, 0.17), (0.50, 0.14)),
    ("mouth", "face", 31, (0.38, 0.18, 0.62, 0.23), (0.50, 0.20)),
    ("hair_front", "head", 40, (0.12, 0.00, 0.88, 0.18), (0.50, 0.14)),
    ("torso", "root", 15, (0.18, 0.24, 0.82, 0.58), (0.50, 0.33)),
    ("left_arm", "torso", 18, (0.00, 0.25, 0.38, 0.67), (0.28, 0.30)),
    ("right_arm", "torso", 18, (0.62, 0.25, 1.00, 0.67), (0.72, 0.30)),
    ("hips", "torso", 16, (0.22, 0.52, 0.78, 0.70), (0.50, 0.58)),
    ("left_leg", "hips", 12, (0.12, 0.62, 0.52, 1.00), (0.38, 0.66)),
    ("right_leg", "hips", 12, (0.48, 0.62, 0.88, 1.00), (0.62, 0.66)),
)


@dataclass(frozen=True)
class Simple2p5DRigResult:
    pipeline_manifest_path: Path
    master_manifest_path: Path
    definition_path: Path
    rig_path: Path
    control_bundle_path: Path
    workflow_path: Path
    live2d_bridge_path: Path
    primary_reference_path: Path
    part_count: int
    workflow_ready: bool


def build_simple_2p5d_rig_pipeline(
    settings: AppSettings,
    character_id: str,
    sheet_image: str | Path,
    display_name: str = "",
    profile_overrides: str | Path | dict[str, Any] | None = None,
    identity_reference_image: str | Path | None = None,
    identity_crop: tuple[float, float, float, float] | None = None,
    source_id: str = "external_sheet",
    comfyui_input_dir: str | Path | None = None,
    checkpoint_name: str = "sd15.safetensors",
    lora_name: str = "{{lora_name}}",
    openpose_controlnet_name: str = "{{openpose_controlnet_name}}",
    depth_controlnet_name: str = "{{depth_controlnet_name}}",
    enable_ipadapter: bool = False,
    ipadapter_preset: str = "PLUS FACE (portraits)",
    ipadapter_weight: float = 0.55,
) -> Simple2p5DRigResult:
    validate_character_id(character_id)
    source_path = Path(sheet_image)
    if not source_path.is_file():
        raise FileNotFoundError(f"Character sheet source does not exist: {source_path}")
    identity_source_path = Path(identity_reference_image) if identity_reference_image else None
    if identity_source_path is not None and not identity_source_path.is_file():
        raise FileNotFoundError(f"Identity reference source does not exist: {identity_source_path}")

    ensure_profile(settings, character_id, display_name or character_id)
    update_profile(settings, character_id, profile_overrides)
    profile = load_character_profile(settings, character_id)
    identity_trigger = str(
        profile.profile_data.get("training", {}).get("identity_trigger") or character_id
    )
    master = import_character_master_asset(
        settings=settings,
        character_id=character_id,
        video_id=source_id,
        master_image=source_path,
        notes="Simple 2.5D Rig Pipeline master source",
        import_sections=True,
        template=TEMPLATE_ID,
    )
    definition = generate_character_2p5d_definition(settings, character_id, master.manifest_path)
    section_manifest = read_json(master.section_manifest_path)
    sections = {
        str(item.get("section_id", "")): dict(item)
        for item in section_manifest.get("sections", [])
        if item.get("section_id")
    }
    primary = select_primary_reference(settings, sections)
    rig_dir = settings.assets.processed / "characters" / character_id / "simple_2p5d_rig"
    rig_dir.mkdir(parents=True, exist_ok=True)
    rig_assets = generate_rig_assets(
        settings,
        character_id,
        primary,
        rig_dir,
        identity_source=identity_source_path,
        identity_crop=identity_crop,
    )
    clean_reference = Path(rig_assets["reference"])

    rig_path = rig_dir / "simple_2p5d_rig.json"
    rig_payload = build_rig_payload(settings, character_id, clean_reference, rig_assets)
    write_json(rig_path, rig_payload)

    live2d_path = rig_dir / "live2d_bridge.json"
    write_json(live2d_path, build_live2d_bridge(settings, character_id, rig_path, rig_assets))

    input_refs, copied_to_comfyui = prepare_comfyui_inputs(
        settings,
        character_id,
        clean_reference,
        rig_assets,
        comfyui_input_dir,
    )
    workflow_path = settings.project_root / "outputs" / "comfyui" / character_id / "simple_2p5d_control_workflow.json"
    workflow_path.parent.mkdir(parents=True, exist_ok=True)
    workflow = build_comfyui_workflow(
        character_id=character_id,
        input_refs=input_refs,
        checkpoint_name=checkpoint_name,
        lora_name=lora_name,
        trigger_tag=identity_trigger,
        openpose_controlnet_name=openpose_controlnet_name,
        depth_controlnet_name=depth_controlnet_name,
        enable_ipadapter=enable_ipadapter,
        ipadapter_preset=ipadapter_preset,
        ipadapter_weight=ipadapter_weight,
    )
    write_json(workflow_path, workflow)
    readiness = {
        "comfyui_inputs": copied_to_comfyui,
        "lora": not lora_name.startswith("{{"),
        "openpose_controlnet": not openpose_controlnet_name.startswith("{{"),
        "depth_controlnet": not depth_controlnet_name.startswith("{{"),
    }
    workflow_ready = all(readiness.values())

    control_bundle_path = rig_dir / "control_bundle.json"
    control_bundle = build_control_bundle(
        settings=settings,
        character_id=character_id,
        definition_path=definition.manifest_path,
        rig_path=rig_path,
        primary=clean_reference,
        rig_assets=rig_assets,
        input_refs=input_refs,
        workflow_path=workflow_path,
        workflow_ready=workflow_ready,
        checkpoint_name=checkpoint_name,
        lora_name=lora_name,
        trigger_tag=identity_trigger,
        openpose_controlnet_name=openpose_controlnet_name,
        depth_controlnet_name=depth_controlnet_name,
        enable_ipadapter=enable_ipadapter,
        ipadapter_preset=ipadapter_preset,
        ipadapter_weight=ipadapter_weight,
        readiness=readiness,
    )
    write_json(control_bundle_path, control_bundle)
    link_character_simple_rig(settings, character_id, rig_path, control_bundle_path)
    attach_rig_binding_to_definition(
        settings,
        definition.manifest_path,
        rig_path,
        control_bundle_path,
        rig_assets,
        workflow_path,
    )

    pipeline_path = settings.project_root / "manifests" / "characters" / character_id / "simple_2p5d_pipeline.json"
    pipeline_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(
        pipeline_path,
        {
            "schema_version": 1,
            "manifest_type": PIPELINE_MANIFEST_TYPE,
            "generated_at": utc_timestamp(),
            "character_id": character_id,
            "template": TEMPLATE_ID,
            "steps": [
                {"step": 1, "name": "character_sheet_template", "status": "completed"},
                {"step": 2, "name": "crop_and_classify", "status": "completed", "section_count": len(sections)},
                {"step": 3, "name": "character_master_asset", "status": "completed"},
                {"step": 4, "name": "simple_2p5d_rig_json", "status": "completed"},
                {"step": 5, "name": "part_masks", "status": "completed", "part_count": len(rig_assets["parts"])},
                {"step": 6, "name": "depth_helper", "status": "completed"},
                {"step": 7, "name": "pose_helper", "status": "completed"},
                {"step": 8, "name": "comfyui_export", "status": "completed"},
                {"step": 9, "name": "lora_controlnet_2p5d_generation", "status": generation_readiness_status(readiness)},
            ],
            "paths": {
                "profile": project_relative_path(settings, character_profile_path(settings, character_id)),
                "master_asset": project_relative_path(settings, master.manifest_path),
                "definition_2p5d": project_relative_path(settings, definition.manifest_path),
                "rig": project_relative_path(settings, rig_path),
                "control_bundle": project_relative_path(settings, control_bundle_path),
                "comfyui_workflow": project_relative_path(settings, workflow_path),
                "live2d_bridge": project_relative_path(settings, live2d_path),
            },
            "workflow_ready": workflow_ready,
            "manual_review": [
                "Review every crop before using it as training data.",
                "Simple masks and mesh zones are deterministic drafts, not semantic segmentation.",
                "Adjust pivots and deformers in Live2D Cubism before production use.",
            ],
        },
    )
    return Simple2p5DRigResult(
        pipeline_manifest_path=pipeline_path,
        master_manifest_path=master.manifest_path,
        definition_path=definition.manifest_path,
        rig_path=rig_path,
        control_bundle_path=control_bundle_path,
        workflow_path=workflow_path,
        live2d_bridge_path=live2d_path,
        primary_reference_path=clean_reference,
        part_count=len(rig_assets["parts"]),
        workflow_ready=workflow_ready,
    )


def ensure_profile(settings: AppSettings, character_id: str, display_name: str) -> None:
    path = character_profile_path(settings, character_id)
    if not path.exists():
        create_character_profile(settings, character_id, display_name, [character_id])


def update_profile(
    settings: AppSettings,
    character_id: str,
    overrides: str | Path | dict[str, Any] | None,
) -> None:
    profile = load_character_profile(settings, character_id)
    values = load_overrides(overrides)
    merged = deep_merge(default_character_profile_data(), profile.profile_data)
    merged = deep_merge(merged, values)
    training = dict(merged.get("training", {}))
    training["identity_trigger"] = training.get("identity_trigger") or character_id
    merged["training"] = training
    save_character_profile(
        settings,
        replace(
            profile,
            profile_schema_version=1,
            profile_template="character_profile_v1",
            profile_data=merged,
        ),
    )


def load_overrides(value: str | Path | dict[str, Any] | None) -> dict[str, Any]:
    if value in (None, ""):
        return {}
    if isinstance(value, dict):
        return value
    data = json.loads(Path(value).read_text(encoding="utf-8-sig"))
    return dict(data.get("profile_data", data))


def deep_merge(base: dict[str, Any], update: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in update.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(dict(result[key]), value)
        else:
            result[key] = value
    return result


def select_primary_reference(settings: AppSettings, sections: dict[str, dict[str, Any]]) -> Path:
    for section_id in ("turnaround_front", "pose_standing", "main_portrait"):
        value = str(sections.get(section_id, {}).get("image_path", ""))
        if value:
            path = resolve_project_path(settings, value)
            if path.is_file():
                return path
    raise ValueError("No front or standing reference crop is available for rig generation.")


def generate_rig_assets(
    settings: AppSettings,
    character_id: str,
    primary: Path,
    rig_dir: Path,
    identity_source: Path | None = None,
    identity_crop: tuple[float, float, float, float] | None = None,
) -> dict[str, Any]:
    masks_dir = rig_dir / "masks"
    parts_dir = rig_dir / "transparent_parts"
    controls_dir = rig_dir / "controls"
    masks_dir.mkdir(parents=True, exist_ok=True)
    parts_dir.mkdir(parents=True, exist_ok=True)
    controls_dir.mkdir(parents=True, exist_ok=True)

    with Image.open(primary) as source:
        image = source.convert("RGBA")
    silhouette = build_foreground_mask(image.convert("RGB"))
    image, silhouette = compose_full_body_reference(image, silhouette)
    silhouette_path = masks_dir / "silhouette.png"
    silhouette.save(silhouette_path)
    reference_path = controls_dir / "reference.png"
    reference = Image.new("RGB", image.size, (255, 255, 255))
    reference.paste(image.convert("RGB"), mask=silhouette)
    reference.save(reference_path)
    identity_source_crop_path = controls_dir / "identity_source_crop.png"
    identity_source_image = load_identity_source(identity_source, identity_crop)
    identity_reference_path = controls_dir / "identity_reference.png"
    if identity_source_image is None:
        identity_reference = build_ipadapter_identity_reference(image, silhouette)
    else:
        identity_source_image.save(identity_source_crop_path)
        identity_reference = ImageOps.fit(
            identity_source_image,
            (512, 512),
            method=Image.Resampling.LANCZOS,
            centering=(0.5, 0.45),
        )
    identity_reference.save(identity_reference_path)
    part_masks = build_part_masks(silhouette)
    part_records: list[dict[str, Any]] = []
    for part_id, parent_id, z_order, _, pivot in PART_SPECS:
        mask = part_masks[part_id]
        mask_path = masks_dir / f"{part_id}.png"
        rgba_path = parts_dir / f"{part_id}.png"
        mask.save(mask_path)
        transparent = image.copy()
        transparent.putalpha(mask)
        transparent.save(rgba_path)
        part_records.append(
            build_part_record(
                settings,
                part_id,
                parent_id,
                z_order,
                pivot,
                mask,
                mask_path,
                rgba_path,
            )
        )

    depth_path = controls_dir / "depth.png"
    build_depth_image(silhouette, part_masks).save(depth_path)
    pose_path = controls_dir / "pose.png"
    build_pose_image(silhouette).save(pose_path)
    face_repair_mask_path = controls_dir / "face_repair_mask.png"
    face_repair_mask = build_face_repair_mask(silhouette)
    face_repair_mask.save(face_repair_mask_path)
    face_reference_path = controls_dir / "face_reference.png"
    build_face_reference(reference, identity_reference, face_repair_mask).save(face_reference_path)
    return {
        "reference": reference_path,
        "identity_reference": identity_reference_path,
        "identity_source_crop": identity_source_crop_path if identity_source_image is not None else None,
        "face_reference": face_reference_path,
        "silhouette": silhouette_path,
        "depth": depth_path,
        "pose": pose_path,
        "face_repair_mask": face_repair_mask_path,
        "parts": part_records,
    }


def load_identity_source(
    source_path: Path | None,
    normalized_crop: tuple[float, float, float, float] | None,
) -> Image.Image | None:
    if source_path is None:
        return None
    with Image.open(source_path) as source:
        image = source.convert("RGB")
    if normalized_crop is None:
        return image
    left, top, right, bottom = normalized_crop
    if not (0.0 <= left < right <= 1.0 and 0.0 <= top < bottom <= 1.0):
        raise ValueError("Identity crop values must satisfy 0 <= left < right <= 1 and 0 <= top < bottom <= 1.")
    crop_box = (
        int(round(left * image.width)),
        int(round(top * image.height)),
        int(round(right * image.width)),
        int(round(bottom * image.height)),
    )
    return image.crop(crop_box)


def build_face_reference(
    reference: Image.Image,
    identity_reference: Image.Image,
    face_mask: Image.Image,
) -> Image.Image:
    destination = reference.convert("RGB").copy()
    destination_box = face_mask.getbbox()
    if destination_box is None:
        return destination
    source = identity_reference.convert("RGB")
    source_mask = build_foreground_mask(source)
    source_box = source_mask.getbbox()
    if source_box is None:
        return destination
    source_left, source_top, source_right, source_bottom = source_box
    source_width = max(1, source_right - source_left)
    head_bottom = min(source_bottom, source_top + int(round(source_width * 1.08)))
    head_crop = source.crop((source_left, source_top, source_right, head_bottom))
    target_size = (destination_box[2] - destination_box[0], destination_box[3] - destination_box[1])
    aligned_head = ImageOps.fit(head_crop, target_size, method=Image.Resampling.LANCZOS, centering=(0.5, 0.45))
    destination.paste(aligned_head, destination_box, face_mask.crop(destination_box))
    return destination


def compose_full_body_reference(
    image: Image.Image,
    silhouette: Image.Image,
    canvas_size: tuple[int, int] = (512, 768),
    horizontal_occupancy: float = 0.72,
    vertical_occupancy: float = 0.82,
    top_margin: float = 0.08,
) -> tuple[Image.Image, Image.Image]:
    bounds = silhouette.getbbox()
    if bounds is None:
        raise ValueError("Cannot compose a full-body reference from an empty silhouette.")

    canvas_width, canvas_height = canvas_size
    cropped_image = image.crop(bounds)
    cropped_mask = silhouette.crop(bounds)
    scale = min(
        canvas_width * horizontal_occupancy / cropped_image.width,
        canvas_height * vertical_occupancy / cropped_image.height,
    )
    target_size = (
        max(1, int(round(cropped_image.width * scale))),
        max(1, int(round(cropped_image.height * scale))),
    )
    resized_image = cropped_image.resize(target_size, Image.Resampling.LANCZOS)
    resized_mask = cropped_mask.resize(target_size, Image.Resampling.LANCZOS)
    left = (canvas_width - target_size[0]) // 2
    top = max(0, int(round(canvas_height * top_margin)))
    if top + target_size[1] > canvas_height:
        top = canvas_height - target_size[1]

    composed_image = Image.new("RGBA", canvas_size, (255, 255, 255, 0))
    composed_mask = Image.new("L", canvas_size, 0)
    composed_image.paste(resized_image, (left, top), resized_mask)
    composed_mask.paste(resized_mask, (left, top))
    return composed_image, composed_mask


def build_foreground_mask(image: Image.Image) -> Image.Image:
    rgb = image.convert("RGB")
    width, height = rgb.size
    pixels = rgb.load()
    step_x = max(1, width // 32)
    step_y = max(1, height // 32)
    border: list[tuple[int, int, int]] = []
    for x in range(0, width, step_x):
        border.extend((pixels[x, 0], pixels[x, height - 1]))
    for y in range(0, height, step_y):
        border.extend((pixels[0, y], pixels[width - 1, y]))
    background = tuple(int(median(channel)) for channel in zip(*border))
    background_luma = sum(background) / 3.0
    values: list[int] = []
    for y in range(height):
        for x in range(width):
            red, green, blue = pixels[x, y]
            distance = abs(red - background[0]) + abs(green - background[1]) + abs(blue - background[2])
            luma = (red + green + blue) / 3.0
            foreground = distance >= 48 or luma < background_luma - 22
            values.append(255 if foreground else 0)
    mask = Image.new("L", rgb.size)
    mask.putdata(values)
    return fill_mask_holes(retain_largest_component(mask.filter(ImageFilter.MedianFilter(3))))


def retain_largest_component(mask: Image.Image) -> Image.Image:
    width, height = mask.size
    source = mask.load()
    seen = bytearray(width * height)
    largest: list[tuple[int, int]] = []
    for y in range(height):
        for x in range(width):
            index = y * width + x
            if seen[index] or source[x, y] == 0:
                continue
            seen[index] = 1
            stack = [(x, y)]
            component: list[tuple[int, int]] = []
            while stack:
                current_x, current_y = stack.pop()
                component.append((current_x, current_y))
                for next_x, next_y in (
                    (current_x - 1, current_y),
                    (current_x + 1, current_y),
                    (current_x, current_y - 1),
                    (current_x, current_y + 1),
                ):
                    if not (0 <= next_x < width and 0 <= next_y < height):
                        continue
                    next_index = next_y * width + next_x
                    if seen[next_index] or source[next_x, next_y] == 0:
                        continue
                    seen[next_index] = 1
                    stack.append((next_x, next_y))
            if len(component) > len(largest):
                largest = component
    result = Image.new("L", mask.size, 0)
    output = result.load()
    for x, y in largest:
        output[x, y] = 255
    return result


def fill_mask_holes(mask: Image.Image) -> Image.Image:
    width, height = mask.size
    source = mask.load()
    exterior = bytearray(width * height)
    stack: list[tuple[int, int]] = []
    for x in range(width):
        stack.extend(((x, 0), (x, height - 1)))
    for y in range(height):
        stack.extend(((0, y), (width - 1, y)))
    while stack:
        x, y = stack.pop()
        index = y * width + x
        if exterior[index] or source[x, y] != 0:
            continue
        exterior[index] = 1
        for next_x, next_y in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if 0 <= next_x < width and 0 <= next_y < height:
                stack.append((next_x, next_y))
    result = mask.copy()
    output = result.load()
    visited = bytearray(exterior)
    maximum_hole_size = max(4, int(width * height * 0.02))
    for y in range(height):
        for x in range(width):
            index = y * width + x
            if visited[index] or source[x, y] != 0:
                continue
            visited[index] = 1
            stack = [(x, y)]
            hole: list[tuple[int, int]] = []
            while stack:
                current_x, current_y = stack.pop()
                hole.append((current_x, current_y))
                for next_x, next_y in (
                    (current_x - 1, current_y),
                    (current_x + 1, current_y),
                    (current_x, current_y - 1),
                    (current_x, current_y + 1),
                ):
                    if not (0 <= next_x < width and 0 <= next_y < height):
                        continue
                    next_index = next_y * width + next_x
                    if visited[next_index] or source[next_x, next_y] != 0:
                        continue
                    visited[next_index] = 1
                    stack.append((next_x, next_y))
            if len(hole) <= maximum_hole_size:
                for hole_x, hole_y in hole:
                    output[hole_x, hole_y] = 255
    return result


def build_part_masks(silhouette: Image.Image) -> dict[str, Image.Image]:
    bbox = silhouette.getbbox() or (0, 0, silhouette.width, silhouette.height)
    left, top, right, bottom = bbox
    width = max(1, right - left)
    height = max(1, bottom - top)
    result: dict[str, Image.Image] = {}
    for part_id, _, _, zone, _ in PART_SPECS:
        zone_mask = Image.new("L", silhouette.size, 0)
        draw = ImageDraw.Draw(zone_mask)
        draw.rectangle(
            (
                int(left + zone[0] * width),
                int(top + zone[1] * height),
                int(left + zone[2] * width),
                int(top + zone[3] * height),
            ),
            fill=255,
        )
        result[part_id] = ImageChops.multiply(silhouette, zone_mask)
    return result


def build_face_repair_mask(silhouette: Image.Image) -> Image.Image:
    bbox = silhouette.getbbox()
    if bbox is None:
        raise ValueError("Cannot build a face repair mask from an empty silhouette.")
    left, top, right, bottom = bbox
    width = max(1, right - left)
    height = max(1, bottom - top)
    region = Image.new("L", silhouette.size, 0)
    draw = ImageDraw.Draw(region)
    draw.rectangle(
        (
            int(left + width * 0.10),
            top,
            int(right - width * 0.10),
            int(top + height * 0.16),
        ),
        fill=255,
    )
    mask = ImageChops.multiply(silhouette, region)
    return mask.filter(ImageFilter.MaxFilter(9))


def build_ipadapter_identity_reference(
    image: Image.Image,
    silhouette: Image.Image,
    output_size: int = 512,
) -> Image.Image:
    bbox = silhouette.getbbox()
    if bbox is None:
        raise ValueError("Cannot build an IPAdapter identity reference from an empty silhouette.")
    left, top, right, bottom = bbox
    subject_width = max(1, right - left)
    subject_height = max(1, bottom - top)
    crop_size = min(
        image.width,
        image.height,
        max(subject_width * 1.45, subject_height * 0.42),
    )
    crop_size = max(1, int(round(crop_size)))
    center_x = (left + right) / 2
    crop_left = int(round(center_x - crop_size / 2))
    crop_top = int(round(top - subject_height * 0.04))
    crop_left = max(0, min(image.width - crop_size, crop_left))
    crop_top = max(0, min(image.height - crop_size, crop_top))
    crop_box = (crop_left, crop_top, crop_left + crop_size, crop_top + crop_size)
    cropped_image = image.convert("RGBA").crop(crop_box)
    cropped_mask = silhouette.convert("L").crop(crop_box)
    canvas = Image.new("RGB", cropped_image.size, (255, 255, 255))
    canvas.paste(cropped_image.convert("RGB"), mask=cropped_mask)
    return canvas.resize((output_size, output_size), Image.Resampling.LANCZOS)


def build_part_record(
    settings: AppSettings,
    part_id: str,
    parent_id: str,
    z_order: int,
    pivot: tuple[float, float],
    mask: Image.Image,
    mask_path: Path,
    rgba_path: Path,
) -> dict[str, Any]:
    bbox = mask.getbbox() or (0, 0, mask.width, mask.height)
    left, top, right, bottom = bbox
    vertices = [
        [round(left / mask.width, 6), round(top / mask.height, 6)],
        [round(right / mask.width, 6), round(top / mask.height, 6)],
        [round(right / mask.width, 6), round(bottom / mask.height, 6)],
        [round(left / mask.width, 6), round(bottom / mask.height, 6)],
    ]
    return {
        "part_id": part_id,
        "parent_id": parent_id,
        "z_order": z_order,
        "pivot": {"x": pivot[0], "y": pivot[1]},
        "mask_image": project_relative_path(settings, mask_path),
        "transparent_image": project_relative_path(settings, rgba_path),
        "mesh": {"type": "quad", "vertices": vertices, "triangles": [[0, 1, 2], [0, 2, 3]]},
        "manual_review_required": True,
    }


def build_depth_image(silhouette: Image.Image, part_masks: dict[str, Image.Image]) -> Image.Image:
    depth = Image.new("L", silhouette.size, 0)
    depth_values = {
        "hair_back": 110,
        "left_leg": 125,
        "right_leg": 125,
        "hips": 140,
        "torso": 155,
        "left_arm": 165,
        "right_arm": 165,
        "head": 180,
        "face": 195,
        "hair_front": 205,
        "eyes": 220,
        "mouth": 215,
    }
    for part_id, value in depth_values.items():
        layer = Image.new("L", silhouette.size, value)
        depth.paste(layer, mask=part_masks[part_id])
    return depth


def build_pose_image(silhouette: Image.Image) -> Image.Image:
    pose = Image.new("RGB", silhouette.size, (0, 0, 0))
    bbox = silhouette.getbbox() or (0, 0, silhouette.width, silhouette.height)
    left, top, right, bottom = bbox
    width = right - left
    height = bottom - top
    point = lambda x, y: (int(left + x * width), int(top + y * height))
    joints = {
        "head": point(0.50, 0.10),
        "neck": point(0.50, 0.23),
        "left_shoulder": point(0.32, 0.28),
        "right_shoulder": point(0.68, 0.28),
        "left_elbow": point(0.24, 0.45),
        "right_elbow": point(0.76, 0.45),
        "left_wrist": point(0.22, 0.62),
        "right_wrist": point(0.78, 0.62),
        "hips": point(0.50, 0.60),
        "left_knee": point(0.40, 0.78),
        "right_knee": point(0.60, 0.78),
        "left_ankle": point(0.38, 0.98),
        "right_ankle": point(0.62, 0.98),
    }
    limbs = [
        ("head", "neck", (255, 0, 0)),
        ("neck", "left_shoulder", (255, 128, 0)),
        ("neck", "right_shoulder", (255, 255, 0)),
        ("left_shoulder", "left_elbow", (128, 255, 0)),
        ("left_elbow", "left_wrist", (0, 255, 0)),
        ("right_shoulder", "right_elbow", (0, 255, 128)),
        ("right_elbow", "right_wrist", (0, 255, 255)),
        ("neck", "hips", (0, 128, 255)),
        ("hips", "left_knee", (0, 0, 255)),
        ("left_knee", "left_ankle", (128, 0, 255)),
        ("hips", "right_knee", (255, 0, 255)),
        ("right_knee", "right_ankle", (255, 0, 128)),
    ]
    draw = ImageDraw.Draw(pose)
    line_width = max(2, min(silhouette.size) // 80)
    for start, end, color in limbs:
        draw.line((joints[start], joints[end]), fill=color, width=line_width)
    radius = max(2, line_width)
    for coordinate in joints.values():
        draw.ellipse(
            (coordinate[0] - radius, coordinate[1] - radius, coordinate[0] + radius, coordinate[1] + radius),
            fill=(255, 255, 255),
        )
    return pose


def build_rig_payload(
    settings: AppSettings,
    character_id: str,
    primary: Path,
    rig_assets: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "manifest_type": RIG_MANIFEST_TYPE,
        "generated_at": utc_timestamp(),
        "character_id": character_id,
        "template": "simple_2p5d_rig_v1",
        "coordinate_system": {"origin": "top_left", "x": "right", "y": "down", "normalized": True},
        "primary_reference": project_relative_path(settings, primary),
        "silhouette_mask": project_relative_path(settings, rig_assets["silhouette"]),
        "controls": {
            "depth": project_relative_path(settings, rig_assets["depth"]),
            "pose": project_relative_path(settings, rig_assets["pose"]),
        },
        "parameters": [
            {"id": "ParamAngleX", "min": -30, "default": 0, "max": 30},
            {"id": "ParamAngleY", "min": -30, "default": 0, "max": 30},
            {"id": "ParamAngleZ", "min": -30, "default": 0, "max": 30},
            {"id": "ParamBodyAngleX", "min": -10, "default": 0, "max": 10},
            {"id": "ParamEyeLOpen", "min": 0, "default": 1, "max": 1},
            {"id": "ParamEyeROpen", "min": 0, "default": 1, "max": 1},
            {"id": "ParamMouthOpenY", "min": 0, "default": 0, "max": 1},
            {"id": "ParamBreath", "min": 0, "default": 0, "max": 1},
        ],
        "parts": rig_assets["parts"],
        "production_status": "draft_requires_manual_review",
    }


def build_live2d_bridge(
    settings: AppSettings,
    character_id: str,
    rig_path: Path,
    rig_assets: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "manifest_type": "live2d_bridge",
        "character_id": character_id,
        "source_rig": project_relative_path(settings, rig_path),
        "art_meshes": [
            {
                "part_id": item["part_id"],
                "suggested_artmesh_id": f"ArtMesh_{item['part_id']}",
                "texture": item["transparent_image"],
                "mask": item["mask_image"],
                "parent": item["parent_id"],
                "z_order": item["z_order"],
                "pivot": item["pivot"],
            }
            for item in rig_assets["parts"]
        ],
        "parameter_map": {
            "head_yaw": "ParamAngleX",
            "head_pitch": "ParamAngleY",
            "head_roll": "ParamAngleZ",
            "body_yaw": "ParamBodyAngleX",
            "left_eye_open": "ParamEyeLOpen",
            "right_eye_open": "ParamEyeROpen",
            "mouth_open": "ParamMouthOpenY",
            "breath": "ParamBreath",
        },
        "notes": [
            "This bridge does not create a Cubism moc3 file.",
            "Import transparent textures, then adjust ArtMesh, deformers, pivots, and clipping manually in Live2D Cubism.",
        ],
    }


def prepare_comfyui_inputs(
    settings: AppSettings,
    character_id: str,
    primary: Path,
    rig_assets: dict[str, Any],
    comfyui_input_dir: str | Path | None,
) -> tuple[dict[str, str], bool]:
    sources = {
        "reference": primary,
        "identity_reference": Path(rig_assets["identity_reference"]),
        "face_reference": Path(rig_assets["face_reference"]),
        "pose": Path(rig_assets["pose"]),
        "depth": Path(rig_assets["depth"]),
        "mask": Path(rig_assets["silhouette"]),
        "face_repair_mask": Path(rig_assets["face_repair_mask"]),
    }
    if comfyui_input_dir in (None, ""):
        return {key: project_relative_path(settings, value) for key, value in sources.items()}, False
    target_root = Path(comfyui_input_dir) / "anime_studio" / character_id
    target_root.mkdir(parents=True, exist_ok=True)
    references: dict[str, str] = {}
    for key, source in sources.items():
        target = target_root / f"{key}{source.suffix.lower()}"
        shutil.copy2(source, target)
        references[key] = f"anime_studio/{character_id}/{target.name}"
    return references, True


def build_comfyui_workflow(
    character_id: str,
    input_refs: dict[str, str],
    checkpoint_name: str,
    lora_name: str,
    openpose_controlnet_name: str,
    depth_controlnet_name: str,
    trigger_tag: str | None = None,
    enable_ipadapter: bool = False,
    ipadapter_preset: str = "PLUS FACE (portraits)",
    ipadapter_weight: float = 0.55,
) -> dict[str, Any]:
    positive_trigger = trigger_tag or character_id
    workflow: dict[str, Any] = {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": checkpoint_name}},
        "2": {
            "class_type": "LoraLoader",
            "inputs": {"model": ["1", 0], "clip": ["1", 1], "lora_name": lora_name, "strength_model": 0.7, "strength_clip": 0.7},
        },
        "3": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "clip": ["2", 1],
                "text": (
                    f"{positive_trigger}, anime character, preserve master identity, 2.5D controlled pose, "
                    "solo, 1girl, single subject, one character only, full body, head fully visible, "
                    "feet fully visible, centered composition, generous headroom, plain background"
                ),
            },
        },
        "4": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "clip": ["2", 1],
                "text": (
                    "low quality, inconsistent face, different character, extra limbs, text, watermark, "
                    "cropped head, cropped feet, out of frame, multiple people, duplicate, clones, lineup, "
                    "character sheet, turnaround sheet, reference sheet, split screen"
                ),
            },
        },
        "5": {"class_type": "LoadImage", "inputs": {"image": input_refs["pose"]}},
        "6": {"class_type": "ControlNetLoader", "inputs": {"control_net_name": openpose_controlnet_name}},
        "7": {
            "class_type": "ControlNetApplyAdvanced",
            "inputs": {
                "positive": ["3", 0], "negative": ["4", 0], "control_net": ["6", 0], "image": ["5", 0],
                "strength": 1.0, "start_percent": 0.0, "end_percent": 0.9,
            },
        },
        "8": {"class_type": "LoadImage", "inputs": {"image": input_refs["depth"]}},
        "9": {"class_type": "ControlNetLoader", "inputs": {"control_net_name": depth_controlnet_name}},
        "10": {
            "class_type": "ControlNetApplyAdvanced",
            "inputs": {
                "positive": ["7", 0], "negative": ["7", 1], "control_net": ["9", 0], "image": ["8", 0],
                "strength": 0.65, "start_percent": 0.0, "end_percent": 0.8,
            },
        },
        "11": {"class_type": "LoadImage", "inputs": {"image": input_refs["reference"]}},
        "12": {
            "class_type": "VAEEncode",
            "inputs": {"pixels": ["11", 0], "vae": ["1", 2]},
        },
        "13": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["20", 0] if enable_ipadapter else ["2", 0],
                "positive": ["10", 0], "negative": ["10", 1], "latent_image": ["12", 0],
                "seed": 1, "steps": 20, "cfg": 6.5, "sampler_name": "dpmpp_2m", "scheduler": "karras", "denoise": 0.65,
            },
        },
        "14": {"class_type": "VAEDecode", "inputs": {"samples": ["13", 0], "vae": ["1", 2]}},
        "15": {
            "class_type": "LoadImageMask",
            "inputs": {"image": input_refs["face_repair_mask"], "channel": "red"},
        },
        "22": {"class_type": "LoadImage", "inputs": {"image": input_refs.get("face_reference", input_refs["reference"])}},
        "16": {
            "class_type": "FeatherMask",
            "inputs": {"mask": ["15", 0], "left": 12, "top": 12, "right": 12, "bottom": 12},
        },
        "17": {
            "class_type": "ImageCompositeMasked",
            "inputs": {
                "destination": ["14", 0], "source": ["22", 0], "x": 0, "y": 0,
                "resize_source": False, "mask": ["16", 0],
            },
        },
        "18": {
            "class_type": "SaveImage",
            "inputs": {"images": ["17", 0], "filename_prefix": f"simple_2p5d/{character_id}_face_repaired"},
        },
    }
    if enable_ipadapter:
        workflow["21"] = {
            "class_type": "LoadImage",
            "inputs": {"image": input_refs.get("identity_reference", input_refs["reference"])},
        }
        workflow["19"] = {
            "class_type": "IPAdapterUnifiedLoader",
            "inputs": {"model": ["2", 0], "preset": ipadapter_preset},
        }
        workflow["20"] = {
            "class_type": "IPAdapterAdvanced",
            "inputs": {
                "model": ["19", 0],
                "ipadapter": ["19", 1],
                "image": ["21", 0],
                "weight": ipadapter_weight,
                "weight_type": "linear",
                "combine_embeds": "average",
                "start_at": 0.0,
                "end_at": 0.85,
                "embeds_scaling": "V only",
            },
        }
    return workflow


def build_control_bundle(
    settings: AppSettings,
    character_id: str,
    definition_path: Path,
    rig_path: Path,
    primary: Path,
    rig_assets: dict[str, Any],
    input_refs: dict[str, str],
    workflow_path: Path,
    workflow_ready: bool,
    checkpoint_name: str,
    lora_name: str,
    trigger_tag: str,
    openpose_controlnet_name: str,
    depth_controlnet_name: str,
    enable_ipadapter: bool,
    ipadapter_preset: str,
    ipadapter_weight: float,
    readiness: dict[str, bool],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "manifest_type": CONTROL_BUNDLE_TYPE,
        "generated_at": utc_timestamp(),
        "character_id": character_id,
        "definition_2p5d": project_relative_path(settings, definition_path),
        "rig": project_relative_path(settings, rig_path),
        "primary_reference": project_relative_path(settings, primary),
        "identity_reference": project_relative_path(settings, rig_assets["identity_reference"]),
        "transparent_parts": [item["transparent_image"] for item in rig_assets["parts"]],
        "control_images": {
            "silhouette_mask": project_relative_path(settings, rig_assets["silhouette"]),
            "depth": project_relative_path(settings, rig_assets["depth"]),
            "pose": project_relative_path(settings, rig_assets["pose"]),
            "face_repair_mask": project_relative_path(settings, rig_assets["face_repair_mask"]),
            "face_reference": project_relative_path(settings, rig_assets["face_reference"]),
            "identity_reference": project_relative_path(settings, rig_assets["identity_reference"]),
            "comfyui_inputs": input_refs,
        },
        "generation_stack": {
            "checkpoint": checkpoint_name,
            "identity": {
                "provider": "character_lora",
                "model": lora_name,
                "trigger_tag": trigger_tag,
                "strength": 0.7,
            },
            "reference_adapter": {
                "provider": "ipadapter_plus" if enable_ipadapter else "disabled",
                "enabled": enable_ipadapter,
                "preset": ipadapter_preset,
                "weight": ipadapter_weight,
                "end_percent": 0.85,
                "image": input_refs["identity_reference"],
            },
            "reference_latent": {"provider": "vae_encode", "image": input_refs["reference"], "denoise": 0.65},
            "face_repair": {
                "provider": "reference_face_composite",
                "mask": input_refs["face_repair_mask"],
                "image": input_refs["face_reference"],
                "feather_pixels": 12,
            },
            "pose": {"provider": "controlnet_openpose", "model": openpose_controlnet_name, "strength": 1.0},
            "depth": {"provider": "controlnet_depth", "model": depth_controlnet_name, "strength": 0.65},
            "shape": {"provider": "simple_2p5d_rig", "role": "identity and silhouette anchor"},
        },
        "workflow": project_relative_path(settings, workflow_path),
        "workflow_ready": workflow_ready,
        "readiness": readiness,
        "readiness_issues": build_readiness_issues(readiness),
    }


def generation_readiness_status(readiness: dict[str, bool]) -> str:
    if all(readiness.values()):
        return "ready"
    missing = [key for key, ready in readiness.items() if not ready]
    if missing == ["lora"]:
        return "needs_lora"
    return "needs_" + "_and_".join(missing)


def build_readiness_issues(readiness: dict[str, bool]) -> list[str]:
    messages = {
        "comfyui_inputs": "Copy control images to the ComfyUI input directory or pass --comfyui-input-dir.",
        "lora": "Set the trained character LoRA filename with --lora-name.",
        "openpose_controlnet": "Set the installed OpenPose ControlNet filename with --openpose-controlnet.",
        "depth_controlnet": "Set the installed Depth ControlNet filename with --depth-controlnet.",
    }
    return [messages[key] for key, ready in readiness.items() if not ready]


def attach_rig_binding_to_definition(
    settings: AppSettings,
    definition_path: Path,
    rig_path: Path,
    control_bundle_path: Path,
    rig_assets: dict[str, Any],
    workflow_path: Path,
) -> None:
    definition = read_json(definition_path)
    definition["simple_2p5d_rig"] = {
        "rig_manifest": project_relative_path(settings, rig_path),
        "control_bundle": project_relative_path(settings, control_bundle_path),
        "silhouette_mask": project_relative_path(settings, rig_assets["silhouette"]),
        "depth_image": project_relative_path(settings, rig_assets["depth"]),
        "pose_image": project_relative_path(settings, rig_assets["pose"]),
        "transparent_parts": [item["transparent_image"] for item in rig_assets["parts"]],
    }
    generation_binding = dict(definition.get("generation_binding", {}))
    comfyui = dict(generation_binding.get("comfyui", {}))
    comfyui.update(
        {
            "simple_2p5d_control_bundle": project_relative_path(settings, control_bundle_path),
            "simple_2p5d_workflow": project_relative_path(settings, workflow_path),
            "control_images": {
                "pose": project_relative_path(settings, rig_assets["pose"]),
                "depth": project_relative_path(settings, rig_assets["depth"]),
                "mask": project_relative_path(settings, rig_assets["silhouette"]),
            },
        }
    )
    generation_binding["comfyui"] = comfyui
    generation_binding["live2d"] = {
        "source_rig": project_relative_path(settings, rig_path),
        "status": "draft_bridge_ready",
    }
    definition["generation_binding"] = generation_binding
    write_json(definition_path, definition)


def resolve_project_path(settings: AppSettings, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else settings.project_root / path


def read_json(path: Path | None) -> dict[str, Any]:
    if path is None or not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_normalized_crop(value: str) -> tuple[float, float, float, float]:
    try:
        coordinates = tuple(float(item.strip()) for item in value.split(","))
    except ValueError as error:
        raise argparse.ArgumentTypeError("Identity crop must contain four decimal values.") from error
    if len(coordinates) != 4:
        raise argparse.ArgumentTypeError("Identity crop must be left,top,right,bottom.")
    left, top, right, bottom = coordinates
    if not (0.0 <= left < right <= 1.0 and 0.0 <= top < bottom <= 1.0):
        raise argparse.ArgumentTypeError("Identity crop values must be normalized between 0 and 1.")
    return left, top, right, bottom


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="anime-simple-2p5d",
        description="Build crops, a Character Master Asset, simple rig, masks, depth, pose, ComfyUI workflow, and Live2D bridge.",
    )
    parser.add_argument("--config", default="config/local_6gb.json")
    parser.add_argument("--character-id", required=True)
    parser.add_argument("--display-name", default="")
    parser.add_argument("--sheet", required=True)
    parser.add_argument("--profile-overrides", default=None)
    parser.add_argument("--identity-reference", default=None)
    parser.add_argument(
        "--identity-crop",
        type=parse_normalized_crop,
        default=None,
        help="Optional normalized left,top,right,bottom crop for a portrait inside an identity sheet.",
    )
    parser.add_argument("--source-id", default="external_sheet")
    parser.add_argument("--comfyui-input-dir", default=None)
    parser.add_argument("--checkpoint", default="sd15.safetensors")
    parser.add_argument("--lora-name", default="{{lora_name}}")
    parser.add_argument("--openpose-controlnet", default="{{openpose_controlnet_name}}")
    parser.add_argument("--depth-controlnet", default="{{depth_controlnet_name}}")
    parser.add_argument("--enable-ipadapter", action="store_true")
    parser.add_argument("--ipadapter-preset", default="PLUS FACE (portraits)")
    parser.add_argument("--ipadapter-weight", type=float, default=0.55)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = build_simple_2p5d_rig_pipeline(
        settings=load_settings(args.config),
        character_id=args.character_id,
        sheet_image=args.sheet,
        display_name=args.display_name,
        profile_overrides=args.profile_overrides,
        identity_reference_image=args.identity_reference,
        identity_crop=args.identity_crop,
        source_id=args.source_id,
        comfyui_input_dir=args.comfyui_input_dir,
        checkpoint_name=args.checkpoint,
        lora_name=args.lora_name,
        openpose_controlnet_name=args.openpose_controlnet,
        depth_controlnet_name=args.depth_controlnet,
        enable_ipadapter=args.enable_ipadapter,
        ipadapter_preset=args.ipadapter_preset,
        ipadapter_weight=args.ipadapter_weight,
    )
    print(f"Pipeline manifest: {result.pipeline_manifest_path}")
    print(f"Character master: {result.master_manifest_path}")
    print(f"2.5D definition: {result.definition_path}")
    print(f"Simple rig: {result.rig_path}")
    print(f"Control bundle: {result.control_bundle_path}")
    print(f"ComfyUI workflow: {result.workflow_path}")
    print(f"Live2D bridge: {result.live2d_bridge_path}")
    print(f"Parts: {result.part_count}")
    print(f"Workflow ready: {result.workflow_ready}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
