from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any

from .lora_registry import utc_timestamp
from .settings import AppSettings
from .storyboard import Shot, get_storyboard_path, load_storyboard


@dataclass(frozen=True)
class CameraWork:
    shot_id: str
    framing: str = ""
    movement: str = ""
    lens_mm: int | None = None
    angle: str = ""
    focus: str = ""
    notes: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class LightingSetup:
    shot_id: str
    key_light: str = ""
    fill_light: str = ""
    rim_light: str = ""
    mood: str = ""
    time_of_day: str = ""
    color_palette: str = ""
    notes: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class ProductionManifestResult:
    manifest_path: Path
    item_count: int


@dataclass(frozen=True)
class DraftGenerationPlanResult:
    plan_path: Path
    draft_count: int
    skipped_count: int


def set_camera_work(
    settings: AppSettings,
    story_id: str,
    shot_id: str,
    framing: str = "",
    movement: str = "",
    lens_mm: int | None = None,
    angle: str = "",
    focus: str = "",
    notes: str = "",
) -> ProductionManifestResult:
    find_shot(settings, story_id, shot_id)
    if lens_mm is not None and lens_mm <= 0:
        raise ValueError("lens_mm must be a positive integer.")
    path = get_camera_work_path(settings, story_id)
    items = load_camera_work(path)
    timestamp = utc_timestamp()
    updated = CameraWork(
        shot_id=shot_id,
        framing=framing,
        movement=movement,
        lens_mm=lens_mm,
        angle=angle,
        focus=focus,
        notes=notes,
        updated_at=timestamp,
    )
    merged = upsert_by_shot_id(items, updated)
    write_production_manifest(path, "storyboard_camera_work", story_id, merged)
    return ProductionManifestResult(manifest_path=path, item_count=len(merged))


def set_lighting_setup(
    settings: AppSettings,
    story_id: str,
    shot_id: str,
    key_light: str = "",
    fill_light: str = "",
    rim_light: str = "",
    mood: str = "",
    time_of_day: str = "",
    color_palette: str = "",
    notes: str = "",
) -> ProductionManifestResult:
    find_shot(settings, story_id, shot_id)
    path = get_lighting_setup_path(settings, story_id)
    items = load_lighting_setups(path)
    timestamp = utc_timestamp()
    updated = LightingSetup(
        shot_id=shot_id,
        key_light=key_light,
        fill_light=fill_light,
        rim_light=rim_light,
        mood=mood,
        time_of_day=time_of_day,
        color_palette=color_palette,
        notes=notes,
        updated_at=timestamp,
    )
    merged = upsert_by_shot_id(items, updated)
    write_production_manifest(path, "storyboard_lighting_setups", story_id, merged)
    return ProductionManifestResult(manifest_path=path, item_count=len(merged))


def build_draft_generation_plan(
    settings: AppSettings,
    story_id: str,
    output_path: str | Path | None = None,
    default_width: int = 512,
    default_height: int = 512,
    default_steps: int = 20,
) -> DraftGenerationPlanResult:
    storyboard = load_storyboard(settings, story_id)
    camera_by_shot = load_camera_work_map(settings, story_id)
    lighting_by_shot = load_lighting_setup_map(settings, story_id)
    drafts: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for shot in sorted(storyboard.shots, key=lambda item: item.order):
        if not shot.character_id:
            skipped.append(
                {
                    "shot_id": shot.shot_id,
                    "order": shot.order,
                    "reason": "character_id is required for LoRA draft generation.",
                }
            )
            continue
        camera = camera_by_shot.get(shot.shot_id)
        lighting = lighting_by_shot.get(shot.shot_id)
        drafts.append(
            render_draft_entry(
                story_id=story_id,
                shot=shot,
                camera=camera,
                lighting=lighting,
                default_width=default_width,
                default_height=default_height,
                default_steps=default_steps,
            )
        )

    plan_path = normalize_draft_plan_path(settings, story_id, output_path)
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "manifest_type": "storyboard_draft_generation_plan",
                "generated_at": utc_timestamp(),
                "story": {
                    "story_id": storyboard.story_id,
                    "title": storyboard.title,
                },
                "defaults": {
                    "width": default_width,
                    "height": default_height,
                    "steps": default_steps,
                    "batch_size": 1,
                    "profile": "RTX 3050 6GB low VRAM draft",
                },
                "counts": {
                    "shot_count": len(storyboard.shots),
                    "draft_count": len(drafts),
                    "skipped_count": len(skipped),
                },
                "drafts": drafts,
                "skipped_shots": skipped,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return DraftGenerationPlanResult(
        plan_path=plan_path,
        draft_count=len(drafts),
        skipped_count=len(skipped),
    )


def render_draft_entry(
    story_id: str,
    shot: Shot,
    camera: CameraWork | None,
    lighting: LightingSetup | None,
    default_width: int,
    default_height: int,
    default_steps: int,
) -> dict[str, Any]:
    return {
        "shot_id": shot.shot_id,
        "order": shot.order,
        "title": shot.title,
        "character_id": shot.character_id,
        "prompt": build_production_prompt(shot, camera, lighting),
        "negative_prompt": shot.negative_prompt,
        "generation": {
            "seed": shot.seed,
            "width": shot.width or default_width,
            "height": shot.height or default_height,
            "steps": shot.steps or default_steps,
            "batch_size": 1,
        },
        "camera_work": asdict(camera) if camera else {},
        "lighting_setup": asdict(lighting) if lighting else {},
        "targets": {
            "workflow_path": f"outputs/comfyui/storyboards/{story_id}/{shot.order:03d}_{shot.shot_id}.json",
            "expected_output_prefix": f"anime_studio/storyboards/{story_id}/{shot.order:03d}_{shot.shot_id}",
        },
    }


def build_production_prompt(
    shot: Shot,
    camera: CameraWork | None = None,
    lighting: LightingSetup | None = None,
) -> str:
    parts = [
        shot.prompt.strip() or shot.title.strip(),
        shot.camera.strip(),
        shot.lighting.strip(),
        camera_prompt(camera),
        lighting_prompt(lighting),
    ]
    merged: list[str] = []
    for part in parts:
        if part and part not in merged:
            merged.append(part)
    return ", ".join(merged)


def camera_prompt(camera: CameraWork | None) -> str:
    if camera is None:
        return ""
    parts = [
        camera.framing,
        camera.movement,
        f"{camera.lens_mm}mm lens" if camera.lens_mm else "",
        camera.angle,
        camera.focus,
    ]
    return ", ".join(part for part in parts if part)


def lighting_prompt(lighting: LightingSetup | None) -> str:
    if lighting is None:
        return ""
    parts = [
        lighting.key_light,
        lighting.fill_light,
        lighting.rim_light,
        lighting.mood,
        lighting.time_of_day,
        lighting.color_palette,
    ]
    return ", ".join(part for part in parts if part)


def load_camera_work_map(settings: AppSettings, story_id: str) -> dict[str, CameraWork]:
    return {item.shot_id: item for item in load_camera_work(get_camera_work_path(settings, story_id))}


def load_lighting_setup_map(settings: AppSettings, story_id: str) -> dict[str, LightingSetup]:
    return {item.shot_id: item for item in load_lighting_setups(get_lighting_setup_path(settings, story_id))}


def load_camera_work(path: Path) -> list[CameraWork]:
    data = read_production_manifest(path, "storyboard_camera_work")
    return [camera_work_from_dict(item) for item in data.get("items", [])]


def load_lighting_setups(path: Path) -> list[LightingSetup]:
    data = read_production_manifest(path, "storyboard_lighting_setups")
    return [lighting_setup_from_dict(item) for item in data.get("items", [])]


def read_production_manifest(path: Path, manifest_type: str) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": 1, "manifest_type": manifest_type, "items": []}
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    data.setdefault("schema_version", 1)
    data.setdefault("manifest_type", manifest_type)
    data.setdefault("items", [])
    return data


def write_production_manifest(
    path: Path,
    manifest_type: str,
    story_id: str,
    items: list[CameraWork] | list[LightingSetup],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "manifest_type": manifest_type,
                "story_id": story_id,
                "updated_at": utc_timestamp(),
                "items": [asdict(item) for item in sorted(items, key=lambda value: value.shot_id)],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def upsert_by_shot_id(items: list[Any], updated: Any) -> list[Any]:
    return [item for item in items if item.shot_id != updated.shot_id] + [updated]


def find_shot(settings: AppSettings, story_id: str, shot_id: str) -> Shot:
    storyboard = load_storyboard(settings, story_id)
    for shot in storyboard.shots:
        if shot.shot_id == shot_id:
            return shot
    raise ValueError(f"Storyboard shot not found: {shot_id}")


def camera_work_from_dict(data: dict[str, Any]) -> CameraWork:
    return CameraWork(
        shot_id=str(data["shot_id"]),
        framing=str(data.get("framing", "")),
        movement=str(data.get("movement", "")),
        lens_mm=optional_int(data.get("lens_mm")),
        angle=str(data.get("angle", "")),
        focus=str(data.get("focus", "")),
        notes=str(data.get("notes", "")),
        updated_at=str(data.get("updated_at", "")),
    )


def lighting_setup_from_dict(data: dict[str, Any]) -> LightingSetup:
    return LightingSetup(
        shot_id=str(data["shot_id"]),
        key_light=str(data.get("key_light", "")),
        fill_light=str(data.get("fill_light", "")),
        rim_light=str(data.get("rim_light", "")),
        mood=str(data.get("mood", "")),
        time_of_day=str(data.get("time_of_day", "")),
        color_palette=str(data.get("color_palette", "")),
        notes=str(data.get("notes", "")),
        updated_at=str(data.get("updated_at", "")),
    )


def optional_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def get_camera_work_path(settings: AppSettings, story_id: str) -> Path:
    return get_storyboard_path(settings, story_id).parent / "camera_work.json"


def get_lighting_setup_path(settings: AppSettings, story_id: str) -> Path:
    return get_storyboard_path(settings, story_id).parent / "lighting_setups.json"


def normalize_draft_plan_path(settings: AppSettings, story_id: str, output_path: str | Path | None) -> Path:
    if output_path is None:
        return get_storyboard_path(settings, story_id).parent / "draft_generation_plan.json"
    path = Path(output_path)
    if not path.is_absolute():
        path = settings.project_root / path
    return path
