from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
import re
import shutil

from PIL import Image

from .character_profile import (
    character_profile_path,
    create_character_profile,
    load_character_profile,
    save_character_profile,
    validate_character_id,
)
from .lora_registry import project_relative_path, utc_timestamp
from .settings import AppSettings, load_settings
from .tagger import ImageTagRecord, dedupe_tags, infer_filename_tags, save_tag_record


IMPORT_MANIFEST_TYPE = "character_sheet_import"
SHEET_ID_PATTERN = re.compile(r"[^a-z0-9_-]+")


@dataclass(frozen=True)
class TemplateRegion:
    section_id: str
    title: str
    left: float
    top: float
    right: float
    bottom: float
    tags: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ImportedSheetSection:
    section_id: str
    title: str
    image_path: str
    caption_path: str
    tag_record_path: str
    crop_box: dict[str, int]
    width: int
    height: int
    tags: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CharacterSheetImportResult:
    manifest_path: Path
    character_id: str
    sheet_id: str
    section_count: int
    asset_dir: Path


DEFAULT_TEMPLATE_V1 = (
    TemplateRegion("main_portrait", "Main Portrait", 0.00, 0.00, 0.40, 0.50, ["portrait", "front", "identity_anchor"]),
    TemplateRegion("turnaround_front", "Turnaround Front", 0.40, 0.00, 0.60, 0.28, ["turnaround", "front"]),
    TemplateRegion("turnaround_side", "Turnaround Side", 0.60, 0.00, 0.80, 0.28, ["turnaround", "side"]),
    TemplateRegion("turnaround_back", "Turnaround Back", 0.80, 0.00, 1.00, 0.28, ["turnaround", "back_view"]),
    TemplateRegion("face_angle_front", "Face Angle Front", 0.40, 0.28, 0.56, 0.50, ["face_angle", "front"]),
    TemplateRegion("face_angle_45", "Face Angle 45", 0.56, 0.28, 0.72, 0.50, ["face_angle", "three_quarter", "45_degree"]),
    TemplateRegion("face_angle_side", "Face Angle Side", 0.72, 0.28, 0.88, 0.50, ["face_angle", "side"]),
    TemplateRegion("expressions", "Expressions", 0.00, 0.50, 0.50, 0.82, ["expression_sheet"]),
    TemplateRegion("pose_reference", "Pose Reference", 0.50, 0.50, 1.00, 0.82, ["pose", "full_body"]),
    TemplateRegion("color_palette", "Color Palette", 0.00, 0.82, 0.24, 1.00, ["color_palette"]),
    TemplateRegion("character_metadata", "Character Metadata", 0.24, 0.82, 0.50, 1.00, ["metadata"]),
)


def import_character_sheet(
    settings: AppSettings,
    character_id: str,
    source_image: str | Path,
    source_label: str = "",
    display_name: str = "",
    template: str = "v1",
    template_json: str | Path | None = None,
    allow_create_profile: bool = True,
) -> CharacterSheetImportResult:
    validate_character_id(character_id)
    source_path = Path(source_image)
    if not source_path.is_file():
        raise FileNotFoundError(f"Character sheet source does not exist: {source_path}")

    ensure_character_profile(settings, character_id, display_name, allow_create_profile)
    sheet_id = build_sheet_id(source_path, source_label)
    asset_dir = settings.assets.processed / "characters" / character_id / "character_sheet" / "source" / sheet_id
    asset_dir.mkdir(parents=True, exist_ok=True)

    copied_source = asset_dir / source_path.name
    if not copied_source.exists() or copied_source.resolve() != source_path.resolve():
        shutil.copy2(source_path, copied_source)

    regions = load_template_regions(template, template_json)
    imported_sections: list[ImportedSheetSection] = []
    with Image.open(copied_source) as image:
        width, height = image.size
        for region in regions:
            crop_box = calculate_crop_box(region, width, height)
            section_image = image.crop((crop_box["left"], crop_box["top"], crop_box["right"], crop_box["bottom"]))
            section_path = asset_dir / f"{region.section_id}.png"
            section_image.save(section_path)

            tags = build_section_tags(character_id, source_path, region)
            tag_record_path = section_path.with_suffix(".tags.json")
            save_tag_record(
                tag_record_path,
                ImageTagRecord(
                    image_path=str(section_path),
                    provider=f"character_sheet_template:{template}",
                    auto_tags=tags,
                ),
            )
            caption_path = section_path.with_suffix(".txt")
            caption_path.write_text(", ".join(tags) + "\n", encoding="utf-8")
            imported_sections.append(
                ImportedSheetSection(
                    section_id=region.section_id,
                    title=region.title,
                    image_path=project_relative_path(settings, section_path),
                    caption_path=project_relative_path(settings, caption_path),
                    tag_record_path=project_relative_path(settings, tag_record_path),
                    crop_box=crop_box,
                    width=section_image.width,
                    height=section_image.height,
                    tags=tags,
                )
            )

    manifest_path = settings.project_root / "manifests" / "characters" / character_id / "character_sheet" / f"{sheet_id}_import.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "manifest_type": IMPORT_MANIFEST_TYPE,
                "generated_at": utc_timestamp(),
                "character_id": character_id,
                "sheet_id": sheet_id,
                "template": template,
                "source_label": source_label,
                "source_image": project_relative_path(settings, copied_source),
                "sections": [asdict(section) for section in imported_sections],
                "notes": [
                    "Template v1 uses fixed normalized crop regions as a lightweight importer.",
                    "Use reviewed/master re-import to replace weak auto-crops later.",
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    attach_import_note_to_profile(settings, character_id, sheet_id, copied_source)
    return CharacterSheetImportResult(
        manifest_path=manifest_path,
        character_id=character_id,
        sheet_id=sheet_id,
        section_count=len(imported_sections),
        asset_dir=asset_dir,
    )


def ensure_character_profile(
    settings: AppSettings,
    character_id: str,
    display_name: str,
    allow_create_profile: bool,
) -> None:
    profile_path = character_profile_path(settings, character_id)
    if profile_path.exists():
        return
    if not allow_create_profile:
        raise FileNotFoundError(f"Character profile does not exist: {profile_path}")
    create_character_profile(
        settings=settings,
        character_id=character_id,
        display_name=display_name or character_id,
        trigger_tags=[character_id],
    )


def load_template_regions(template: str, template_json: str | Path | None) -> list[TemplateRegion]:
    if template_json not in (None, ""):
        data = json.loads(Path(template_json).read_text(encoding="utf-8"))
        values = data.get("regions", data)
        return [
            TemplateRegion(
                section_id=str(item["section_id"]),
                title=str(item.get("title", item["section_id"])),
                left=float(item["left"]),
                top=float(item["top"]),
                right=float(item["right"]),
                bottom=float(item["bottom"]),
                tags=[str(tag) for tag in item.get("tags", [])],
            )
            for item in values
        ]
    if template != "v1":
        raise ValueError(f"Unsupported character sheet template: {template}")
    return list(DEFAULT_TEMPLATE_V1)


def calculate_crop_box(region: TemplateRegion, width: int, height: int) -> dict[str, int]:
    left = clamp_coordinate(int(round(region.left * width)), 0, max(0, width - 1))
    top = clamp_coordinate(int(round(region.top * height)), 0, max(0, height - 1))
    right = clamp_coordinate(int(round(region.right * width)), left + 1, width)
    bottom = clamp_coordinate(int(round(region.bottom * height)), top + 1, height)
    return {
        "left": left,
        "top": top,
        "right": right,
        "bottom": bottom,
    }


def clamp_coordinate(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(value, maximum))


def build_section_tags(character_id: str, source_image: Path, region: TemplateRegion) -> list[str]:
    return dedupe_tags(
        [
            character_id,
            "character_sheet",
            region.section_id,
            *region.tags,
            *infer_filename_tags(source_image),
        ]
    )


def build_sheet_id(source_path: Path, source_label: str) -> str:
    raw = source_label.strip().lower() or source_path.stem.lower()
    normalized = SHEET_ID_PATTERN.sub("_", raw).strip("_")
    return normalized or "character_sheet"


def attach_import_note_to_profile(settings: AppSettings, character_id: str, sheet_id: str, source_path: Path) -> None:
    profile = load_character_profile(settings, character_id)
    note = f"character sheet imported: {sheet_id}, source={source_path.name}"
    if note in profile.source_notes:
        return
    updated_profile = type(profile)(
        character_id=profile.character_id,
        display_name=profile.display_name,
        trigger_tags=profile.trigger_tags,
        appearance_notes=profile.appearance_notes,
        source_notes=f"{profile.source_notes}\n{note}".strip(),
        lora_files=profile.lora_files,
        lora_artifacts=profile.lora_artifacts,
    )
    save_character_profile(settings, updated_profile)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="anime-character-sheet-import",
        description="Import one character sheet image into fixed template crops, tags, and manifests.",
    )
    parser.add_argument("--config", default="config/local_6gb.json", help="Path to the local runtime profile.")
    parser.add_argument("--character-id", required=True, help="Character id.")
    parser.add_argument("--source", required=True, help="Character sheet image path.")
    parser.add_argument("--label", default="", help="Optional stable sheet label.")
    parser.add_argument("--display-name", default="", help="Display name used only when auto-creating the profile.")
    parser.add_argument("--template", default="v1", help="Template id. Default: v1.")
    parser.add_argument("--template-json", default=None, help="Optional JSON file with normalized crop regions.")
    parser.add_argument("--no-create-profile", action="store_true", help="Fail when the character profile does not exist.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    settings = load_settings(args.config)
    result = import_character_sheet(
        settings=settings,
        character_id=args.character_id,
        source_image=args.source,
        source_label=args.label,
        display_name=args.display_name,
        template=args.template,
        template_json=args.template_json,
        allow_create_profile=not args.no_create_profile,
    )
    print(f"Character sheet import manifest: {result.manifest_path}")
    print(f"Character: {result.character_id}")
    print(f"Sheet id: {result.sheet_id}")
    print(f"Sections: {result.section_count}")
    print(f"Assets: {result.asset_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())