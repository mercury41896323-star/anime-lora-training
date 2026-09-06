from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw
from psd_tools import PSDImage
from psd_tools.api.layers import PixelLayer

from .character_profile import validate_character_id
from .lora_registry import project_relative_path, utc_timestamp
from .settings import AppSettings, load_settings
from .simple_2p5d_rig import read_json, write_json


MESH_DENSITY = {
    "hair_back": (7, 7),
    "head": (6, 6),
    "face": (6, 6),
    "eyes": (6, 3),
    "mouth": (5, 3),
    "hair_front": (7, 6),
    "torso": (5, 7),
    "left_arm": (3, 8),
    "right_arm": (3, 8),
    "hips": (5, 4),
    "left_leg": (3, 8),
    "right_leg": (3, 8),
}

POSE_PRESETS: dict[str, dict[str, float]] = {
    "relaxed_standing": {
        "body": 2.0,
        "head": -4.0,
        "left_arm": -6.0,
        "right_arm": 7.0,
        "hips": -1.0,
        "left_leg": 2.0,
        "right_leg": -2.0,
    },
    "small_step": {
        "body": -1.5,
        "head": 3.0,
        "left_arm": 4.0,
        "right_arm": -4.0,
        "hips": 1.0,
        "left_leg": -3.0,
        "right_leg": 3.0,
    },
}


@dataclass(frozen=True)
class Live2DAdjustmentResult:
    adjustment_path: Path
    preview_path: Path
    cubism_psd_path: Path
    bridge_path: Path
    art_mesh_count: int
    deformer_count: int
    pose_preview_paths: tuple[Path, ...]


def build_live2d_adjustment_package(
    settings: AppSettings,
    character_id: str,
    overrides: str | Path | dict[str, Any] | None = None,
) -> Live2DAdjustmentResult:
    validate_character_id(character_id)
    rig_dir = settings.assets.processed / "characters" / character_id / "simple_2p5d_rig"
    rig_path = rig_dir / "simple_2p5d_rig.json"
    bridge_path = rig_dir / "live2d_bridge.json"
    rig = read_json(rig_path)
    bridge = read_json(bridge_path)
    if not rig:
        raise FileNotFoundError(f"Simple 2.5D rig does not exist: {rig_path}")
    if not bridge:
        raise FileNotFoundError(f"Live2D bridge does not exist: {bridge_path}")

    override_data = load_overrides(overrides)
    part_overrides = dict(override_data.get("parts", {}))
    art_meshes: list[dict[str, Any]] = []
    pivots: dict[str, dict[str, float]] = {}
    for part in rig.get("parts", []):
        part_id = str(part.get("part_id", ""))
        if not part_id:
            continue
        part_override = dict(part_overrides.get(part_id, {}))
        bounds = mesh_bounds(dict(part.get("mesh", {})))
        pivot = recommended_pivot(part_id, bounds)
        pivot.update(normalize_pivot(dict(part_override.get("pivot", {})), pivot))
        columns, rows = MESH_DENSITY.get(part_id, (4, 4))
        columns = int(part_override.get("columns", columns))
        rows = int(part_override.get("rows", rows))
        mesh = build_grid_mesh(bounds, columns, rows)
        deformers = deformer_ids(part_id)
        pivots[part_id] = pivot
        art_meshes.append(
            {
                "part_id": part_id,
                "art_mesh_id": f"ArtMesh_{part_id}",
                "texture": str(part.get("transparent_image", "")),
                "mask": str(part.get("mask_image", "")),
                "parent_part": str(part.get("parent_id", "root")),
                "z_order": int(part.get("z_order", 0)),
                "pivot": pivot,
                "rotation_deformer": deformers[0],
                "warp_deformer": deformers[1],
                "mesh": mesh,
            }
        )

    deformers = build_deformers(pivots)
    parameter_bindings = build_parameter_bindings()
    preview_path = rig_dir / "live2d_adjustment_preview.png"
    render_preview(settings, rig, art_meshes, preview_path)
    pose_tests = []
    pose_preview_paths = []
    for preset_id, rotations in POSE_PRESETS.items():
        pose_preview_path = rig_dir / f"live2d_pose_test_{preset_id}.png"
        render_pose_test(settings, art_meshes, rotations, pose_preview_path)
        pose_preview_paths.append(pose_preview_path)
        pose_tests.append(
            {
                "preset_id": preset_id,
                "rotations_degrees": rotations,
                "preview": project_relative_path(settings, pose_preview_path),
                "purpose": "Static pivot and part-separation review before Cubism keyform authoring.",
            }
        )
    cubism_psd_path = rig_dir / f"{character_id}_live2d_import.psd"
    build_cubism_import_psd(settings, art_meshes, cubism_psd_path)
    adjustment_path = rig_dir / "live2d_adjustment.json"
    payload = {
        "schema_version": 1,
        "manifest_type": "live2d_adjustment_package",
        "generated_at": utc_timestamp(),
        "character_id": character_id,
        "source_rig": project_relative_path(settings, rig_path),
        "coordinate_system": rig.get("coordinate_system", {}),
        "art_meshes": art_meshes,
        "deformers": deformers,
        "parameter_bindings": parameter_bindings,
        "pose_tests": pose_tests,
        "preview": project_relative_path(settings, preview_path),
        "cubism_import_psd": project_relative_path(settings, cubism_psd_path),
        "cubism_import_order": [
            "Import transparent part textures in z-order.",
            "Create rotation deformers from root to limbs.",
            "Create warp deformers and assign each ArtMesh.",
            "Set pivot coordinates using the normalized reference canvas.",
            "Create parameter keyforms, then refine mesh vertices in Cubism Editor.",
        ],
        "manual_adjustment_required": [
            "Refine ArtMesh vertices around hair tips, eyes, mouth, dress hem, elbows, knees, and shoes.",
            "Tune warp strength and clipping after importing into Cubism Editor.",
            "Confirm all pivots against the final separated source artwork.",
        ],
    }
    write_json(adjustment_path, payload)
    bridge["adjustment_package"] = project_relative_path(settings, adjustment_path)
    bridge["adjustment_preview"] = project_relative_path(settings, preview_path)
    bridge["cubism_import_psd"] = project_relative_path(settings, cubism_psd_path)
    bridge["deformers"] = deformers
    bridge["parameter_bindings"] = parameter_bindings
    bridge["pose_tests"] = pose_tests
    bridge["adjusted_art_meshes"] = art_meshes
    bridge["status"] = "cubism_import_package_ready"
    write_json(bridge_path, bridge)
    return Live2DAdjustmentResult(
        adjustment_path=adjustment_path,
        preview_path=preview_path,
        cubism_psd_path=cubism_psd_path,
        bridge_path=bridge_path,
        art_mesh_count=len(art_meshes),
        deformer_count=len(deformers),
        pose_preview_paths=tuple(pose_preview_paths),
    )


def load_overrides(value: str | Path | dict[str, Any] | None) -> dict[str, Any]:
    if value in (None, ""):
        return {}
    if isinstance(value, dict):
        return value
    return dict(json.loads(Path(value).read_text(encoding="utf-8-sig")))


def mesh_bounds(mesh: dict[str, Any]) -> tuple[float, float, float, float]:
    vertices = [item for item in mesh.get("vertices", []) if isinstance(item, list) and len(item) >= 2]
    if not vertices:
        raise ValueError("ArtMesh source has no vertices.")
    xs = [float(item[0]) for item in vertices]
    ys = [float(item[1]) for item in vertices]
    return min(xs), min(ys), max(xs), max(ys)


def recommended_pivot(part_id: str, bounds: tuple[float, float, float, float]) -> dict[str, float]:
    left, top, right, bottom = bounds
    width = right - left
    height = bottom - top
    if part_id == "head":
        x, y = left + width * 0.5, top + height * 0.5
    elif part_id in {"hair_back", "face", "eyes", "mouth", "hair_front"}:
        x, y = left + width * 0.5, top + height * 0.86
    elif part_id == "left_arm":
        x, y = right - width * 0.08, top + height * 0.06
    elif part_id == "right_arm":
        x, y = left + width * 0.08, top + height * 0.06
    elif part_id == "torso":
        x, y = left + width * 0.5, top + height * 0.16
    elif part_id == "hips":
        x, y = left + width * 0.5, top + height * 0.18
    else:
        x, y = left + width * 0.5, top + height * 0.05
    return {"x": round(x, 6), "y": round(y, 6)}


def normalize_pivot(value: dict[str, Any], fallback: dict[str, float]) -> dict[str, float]:
    return {
        "x": round(float(value.get("x", fallback["x"])), 6),
        "y": round(float(value.get("y", fallback["y"])), 6),
    }


def build_grid_mesh(
    bounds: tuple[float, float, float, float],
    columns: int,
    rows: int,
) -> dict[str, Any]:
    columns = max(2, min(16, columns))
    rows = max(2, min(16, rows))
    left, top, right, bottom = bounds
    vertices = [
        [
            round(left + (right - left) * column / (columns - 1), 6),
            round(top + (bottom - top) * row / (rows - 1), 6),
        ]
        for row in range(rows)
        for column in range(columns)
    ]
    triangles: list[list[int]] = []
    for row in range(rows - 1):
        for column in range(columns - 1):
            top_left = row * columns + column
            top_right = top_left + 1
            bottom_left = top_left + columns
            bottom_right = bottom_left + 1
            triangles.extend(([top_left, bottom_left, bottom_right], [top_left, bottom_right, top_right]))
    return {
        "type": "grid",
        "columns": columns,
        "rows": rows,
        "vertices": vertices,
        "triangles": triangles,
    }


def deformer_ids(part_id: str) -> tuple[str, str]:
    groups = {
        "hair_back": ("Rotation_Head", "Warp_HairBack"),
        "head": ("Rotation_Head", "Warp_Head"),
        "face": ("Rotation_Head", "Warp_Face"),
        "eyes": ("Rotation_Head", "Warp_Eyes"),
        "mouth": ("Rotation_Head", "Warp_Mouth"),
        "hair_front": ("Rotation_Head", "Warp_HairFront"),
        "torso": ("Rotation_Body", "Warp_Body"),
        "left_arm": ("Rotation_LeftArm", "Warp_LeftArm"),
        "right_arm": ("Rotation_RightArm", "Warp_RightArm"),
        "hips": ("Rotation_Hips", "Warp_Hips"),
        "left_leg": ("Rotation_LeftLeg", "Warp_LeftLeg"),
        "right_leg": ("Rotation_RightLeg", "Warp_RightLeg"),
    }
    return groups.get(part_id, ("Rotation_Root", f"Warp_{part_id}"))


def build_deformers(pivots: dict[str, dict[str, float]]) -> list[dict[str, Any]]:
    head_pivot = pivots.get("head", {"x": 0.5, "y": 0.25})
    body_pivot = pivots.get("torso", {"x": 0.5, "y": 0.33})
    hip_pivot = pivots.get("hips", {"x": 0.5, "y": 0.58})
    return [
        {"id": "Rotation_Root", "type": "rotation", "parent": "", "pivot": {"x": 0.5, "y": 0.5}},
        {"id": "Rotation_Body", "type": "rotation", "parent": "Rotation_Root", "pivot": body_pivot},
        {"id": "Warp_Body", "type": "warp", "parent": "Rotation_Body", "divisions": [3, 5]},
        {"id": "Rotation_Head", "type": "rotation", "parent": "Warp_Body", "pivot": head_pivot},
        {"id": "Warp_Head", "type": "warp", "parent": "Rotation_Head", "divisions": [5, 5]},
        {"id": "Warp_Face", "type": "warp", "parent": "Warp_Head", "divisions": [5, 5]},
        {"id": "Warp_Eyes", "type": "warp", "parent": "Warp_Face", "divisions": [5, 2]},
        {"id": "Warp_Mouth", "type": "warp", "parent": "Warp_Face", "divisions": [4, 2]},
        {"id": "Warp_HairBack", "type": "warp", "parent": "Rotation_Head", "divisions": [6, 6]},
        {"id": "Warp_HairFront", "type": "warp", "parent": "Warp_Head", "divisions": [6, 5]},
        {"id": "Rotation_LeftArm", "type": "rotation", "parent": "Warp_Body", "pivot": pivots.get("left_arm", body_pivot)},
        {"id": "Warp_LeftArm", "type": "warp", "parent": "Rotation_LeftArm", "divisions": [2, 6]},
        {"id": "Rotation_RightArm", "type": "rotation", "parent": "Warp_Body", "pivot": pivots.get("right_arm", body_pivot)},
        {"id": "Warp_RightArm", "type": "warp", "parent": "Rotation_RightArm", "divisions": [2, 6]},
        {"id": "Rotation_Hips", "type": "rotation", "parent": "Warp_Body", "pivot": hip_pivot},
        {"id": "Warp_Hips", "type": "warp", "parent": "Rotation_Hips", "divisions": [4, 3]},
        {"id": "Rotation_LeftLeg", "type": "rotation", "parent": "Rotation_Hips", "pivot": pivots.get("left_leg", hip_pivot)},
        {"id": "Warp_LeftLeg", "type": "warp", "parent": "Rotation_LeftLeg", "divisions": [2, 6]},
        {"id": "Rotation_RightLeg", "type": "rotation", "parent": "Rotation_Hips", "pivot": pivots.get("right_leg", hip_pivot)},
        {"id": "Warp_RightLeg", "type": "warp", "parent": "Rotation_RightLeg", "divisions": [2, 6]},
    ]


def build_parameter_bindings() -> list[dict[str, Any]]:
    return [
        {
            "parameter": "ParamAngleX",
            "target": "Warp_Head",
            "keyforms": [
                {"value": -30, "translate_x": -0.025, "scale_x": 0.92},
                {"value": 0, "translate_x": 0.0, "scale_x": 1.0},
                {"value": 30, "translate_x": 0.025, "scale_x": 0.92},
            ],
        },
        {
            "parameter": "ParamAngleY",
            "target": "Warp_Head",
            "keyforms": [
                {"value": -30, "translate_y": 0.018, "scale_y": 0.94},
                {"value": 0, "translate_y": 0.0, "scale_y": 1.0},
                {"value": 30, "translate_y": -0.018, "scale_y": 0.96},
            ],
        },
        {
            "parameter": "ParamAngleZ",
            "target": "Rotation_Head",
            "keyforms": [
                {"value": -30, "rotation_degrees": -15},
                {"value": 0, "rotation_degrees": 0},
                {"value": 30, "rotation_degrees": 15},
            ],
        },
        {
            "parameter": "ParamBodyAngleX",
            "target": "Warp_Body",
            "keyforms": [
                {"value": -10, "translate_x": -0.015, "skew_x": -0.02},
                {"value": 0, "translate_x": 0.0, "skew_x": 0.0},
                {"value": 10, "translate_x": 0.015, "skew_x": 0.02},
            ],
        },
        {"parameter": "ParamEyeLOpen", "target": "Warp_Eyes", "range": [0, 1]},
        {"parameter": "ParamEyeROpen", "target": "Warp_Eyes", "range": [0, 1]},
        {"parameter": "ParamMouthOpenY", "target": "Warp_Mouth", "range": [0, 1]},
        {"parameter": "ParamBreath", "target": "Warp_Body", "range": [0, 1], "scale_y": [1.0, 1.015]},
    ]


def render_preview(
    settings: AppSettings,
    rig: dict[str, Any],
    art_meshes: list[dict[str, Any]],
    output_path: Path,
) -> None:
    reference_path = Path(str(rig.get("primary_reference", "")))
    if not reference_path.is_absolute():
        reference_path = settings.project_root / reference_path
    with Image.open(reference_path) as source:
        image = source.convert("RGB")
    draw = ImageDraw.Draw(image)
    colors = [(255, 64, 64), (64, 160, 255), (80, 220, 120), (255, 180, 40)]
    for index, part in enumerate(art_meshes):
        vertices = part["mesh"]["vertices"]
        xs = [vertex[0] for vertex in vertices]
        ys = [vertex[1] for vertex in vertices]
        box = (
            int(min(xs) * image.width),
            int(min(ys) * image.height),
            int(max(xs) * image.width),
            int(max(ys) * image.height),
        )
        color = colors[index % len(colors)]
        draw.rectangle(box, outline=color, width=2)
        pivot = part["pivot"]
        pivot_x = int(float(pivot["x"]) * image.width)
        pivot_y = int(float(pivot["y"]) * image.height)
        draw.line((pivot_x - 7, pivot_y, pivot_x + 7, pivot_y), fill=color, width=2)
        draw.line((pivot_x, pivot_y - 7, pivot_x, pivot_y + 7), fill=color, width=2)
        draw.text((box[0] + 2, box[1] + 2), str(part["part_id"]), fill=color)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path)


def render_pose_test(
    settings: AppSettings,
    art_meshes: list[dict[str, Any]],
    rotations: dict[str, float],
    output_path: Path,
) -> None:
    layers: list[tuple[int, str, Image.Image]] = []
    pivots = {str(item["part_id"]): dict(item["pivot"]) for item in art_meshes}
    canvas_size: tuple[int, int] | None = None
    for art_mesh in art_meshes:
        texture_path = Path(str(art_mesh.get("texture", "")))
        if not texture_path.is_absolute():
            texture_path = settings.project_root / texture_path
        with Image.open(texture_path) as source:
            layer = source.convert("RGBA")
        if canvas_size is None:
            canvas_size = layer.size
        elif layer.size != canvas_size:
            raise ValueError("All Live2D pose-test textures must use the same canvas size.")
        layers.append((int(art_mesh.get("z_order", 0)), str(art_mesh["part_id"]), layer))
    if canvas_size is None:
        raise ValueError("No Live2D textures are available for pose testing.")

    result = Image.new("RGBA", canvas_size, (255, 255, 255, 255))
    for _, part_id, layer in sorted(layers, key=lambda item: item[0]):
        for transform_id, pivot_part_id in pose_transform_chain(part_id):
            angle = float(rotations.get(transform_id, 0.0))
            if not angle:
                continue
            pivot = pivots[pivot_part_id]
            center = (float(pivot["x"]) * canvas_size[0], float(pivot["y"]) * canvas_size[1])
            layer = layer.rotate(angle, resample=Image.Resampling.BICUBIC, center=center, expand=False)
        result.alpha_composite(layer)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result.convert("RGB").save(output_path)


def pose_transform_chain(part_id: str) -> tuple[tuple[str, str], ...]:
    if part_id in {"hair_back", "head", "face", "eyes", "mouth", "hair_front"}:
        return (("head", "head"), ("body", "torso"))
    if part_id == "torso":
        return (("body", "torso"),)
    if part_id in {"left_arm", "right_arm"}:
        return ((part_id, part_id), ("body", "torso"))
    if part_id == "hips":
        return (("hips", "hips"), ("body", "torso"))
    if part_id in {"left_leg", "right_leg"}:
        return ((part_id, part_id), ("hips", "hips"), ("body", "torso"))
    return ()


def build_cubism_import_psd(
    settings: AppSettings,
    art_meshes: list[dict[str, Any]],
    output_path: Path,
) -> None:
    layers: list[tuple[int, str, Image.Image, tuple[int, int, int, int]]] = []
    canvas_size: tuple[int, int] | None = None
    for art_mesh in art_meshes:
        texture_path = Path(str(art_mesh.get("texture", "")))
        if not texture_path.is_absolute():
            texture_path = settings.project_root / texture_path
        if not texture_path.is_file():
            raise FileNotFoundError(f"Transparent Live2D texture does not exist: {texture_path}")
        with Image.open(texture_path) as source:
            image = source.convert("RGBA")
        if canvas_size is None:
            canvas_size = image.size
        elif image.size != canvas_size:
            raise ValueError("All Live2D textures must use the same canvas size.")
        bounds = image.getchannel("A").getbbox()
        if bounds is None:
            raise ValueError(f"Transparent Live2D texture is empty: {texture_path}")
        layers.append(
            (
                int(art_mesh.get("z_order", 0)),
                str(art_mesh.get("part_id", texture_path.stem)),
                image.crop(bounds),
                bounds,
            )
        )
    if canvas_size is None:
        raise ValueError("No Live2D textures are available for PSD export.")
    psd = PSDImage.new("RGBA", canvas_size, (0, 0, 0, 0))
    for _, part_id, image, bounds in sorted(layers, key=lambda item: item[0]):
        psd.append(
            PixelLayer.frompil(
                image,
                parent=psd,
                name=part_id,
                top=bounds[1],
                left=bounds[0],
            )
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    psd.save(output_path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="anime-live2d-adjust",
        description="Build editable ArtMesh, deformer, pivot, and parameter guidance for a Simple 2.5D rig.",
    )
    parser.add_argument("--config", default="config/local_6gb.json")
    parser.add_argument("--character-id", required=True)
    parser.add_argument("--overrides", default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = build_live2d_adjustment_package(
        settings=load_settings(args.config),
        character_id=args.character_id,
        overrides=args.overrides,
    )
    print(f"Adjustment package: {result.adjustment_path}")
    print(f"Pivot preview: {result.preview_path}")
    print(f"Cubism PSD: {result.cubism_psd_path}")
    print(f"Live2D bridge: {result.bridge_path}")
    print(f"ArtMeshes: {result.art_mesh_count}")
    print(f"Deformers: {result.deformer_count}")
    for pose_preview_path in result.pose_preview_paths:
        print(f"Pose preview: {pose_preview_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
