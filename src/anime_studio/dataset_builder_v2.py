from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
import shutil
from typing import Iterable

from .character_profile import validate_character_id
from .lora_registry import project_relative_path, utc_timestamp
from .settings import AppSettings, load_settings
from .tagger import dedupe_tags
from .video_shot_pipeline import classification_manifest_path, sampled_manifest_path


DATASET_BUNDLE_MANIFEST_TYPE = "purpose_dataset_bundle"
DATASET_MANIFEST_TYPE = "purpose_dataset_manifest"


@dataclass(frozen=True)
class DatasetSourceAsset:
    dataset_kind: str
    source_path: str
    source_type: str
    origin_id: str
    tags: list[str] = field(default_factory=list)
    reason: str = ""


@dataclass(frozen=True)
class PurposeDatasetSummary:
    dataset_kind: str
    dataset_dir: str
    image_count: int
    manifest_path: str


@dataclass(frozen=True)
class DatasetBuilderV2Result:
    manifest_path: Path
    character_id: str
    video_id: str
    dataset_count: int
    total_images: int


CHARACTER_SECTION_IDS = {
    "main_portrait",
    "turnaround_front",
    "turnaround_side",
    "turnaround_back",
    "face_angle_front",
    "face_angle_45",
    "face_angle_side",
    "pose_reference",
}

EXPRESSION_SECTION_IDS = {
    "expressions",
}


def build_purpose_datasets_v2(
    settings: AppSettings,
    character_id: str,
    video_id: str,
    sheet_id: str = "",
    include_character_sheet: bool = True,
    include_master_asset: bool = True,
    include_video_samples: bool = True,
) -> DatasetBuilderV2Result:
    validate_character_id(character_id)

    master_manifest = load_optional_json(character_master_asset_manifest_path(settings, character_id))
    sheet_import_manifest = (
        load_optional_json(find_sheet_import_manifest(settings, character_id, sheet_id))
        if include_character_sheet
        else {}
    )
    sampled_manifest = (
        load_optional_json(sampled_manifest_path(settings, character_id, video_id))
        if include_video_samples
        else {}
    )
    classification_manifest = (
        load_optional_json(classification_manifest_path(settings, character_id, video_id))
        if include_video_samples
        else {}
    )

    datasets: dict[str, list[DatasetSourceAsset]] = {
        "character": [],
        "expression": [],
        "shot": [],
        "direction": [],
    }
    add_sources(datasets["character"], gather_master_asset_sources(settings, character_id, master_manifest) if include_master_asset else [])
    add_sources(datasets["character"], gather_character_sheet_sources(sheet_import_manifest, CHARACTER_SECTION_IDS, "character", "character_sheet_region"))
    add_sources(datasets["expression"], gather_character_sheet_sources(sheet_import_manifest, EXPRESSION_SECTION_IDS, "expression", "character_sheet_region"))

    classifications = list(classification_manifest.get("classifications", []))
    for item in classifications:
        source_path = str(item.get("frame_path", ""))
        if not source_path:
            continue
        base_tags = [
            character_id,
            *[str(tag) for tag in item.get("tags", [])],
            str(item.get("face_angle", "unknown")),
            str(item.get("expression", "unknown")),
            str(item.get("body_framing", "unknown")),
        ]
        shot_id = str(item.get("shot_id", ""))
        datasets["shot"].append(
            DatasetSourceAsset(
                dataset_kind="shot",
                source_path=source_path,
                source_type="video_sample",
                origin_id=shot_id or "shot",
                tags=dedupe_tags([*base_tags, "shot_reference"]),
                reason="Sampled frame classified for framing and shot reference.",
            )
        )
        datasets["direction"].append(
            DatasetSourceAsset(
                dataset_kind="direction",
                source_path=source_path,
                source_type="video_sample",
                origin_id=shot_id or "direction",
                tags=dedupe_tags([*base_tags, "direction_reference"]),
                reason="Sampled frame classified for emotion and direction reference.",
            )
        )
        if str(item.get("face_angle", "unknown")) != "unknown" or str(item.get("body_framing", "unknown")) != "unknown":
            datasets["character"].append(
                DatasetSourceAsset(
                    dataset_kind="character",
                    source_path=source_path,
                    source_type="video_sample",
                    origin_id=shot_id or "character",
                    tags=dedupe_tags([*base_tags, "character_reference"]),
                    reason="Sampled frame classified as a reusable character reference.",
                )
            )
        if str(item.get("expression", "unknown")) != "unknown":
            datasets["expression"].append(
                DatasetSourceAsset(
                    dataset_kind="expression",
                    source_path=source_path,
                    source_type="video_sample",
                    origin_id=shot_id or "expression",
                    tags=dedupe_tags([*base_tags, "expression_reference"]),
                    reason="Sampled frame classified as an expression reference.",
                )
            )

    summaries: list[PurposeDatasetSummary] = []
    total_images = 0
    for dataset_kind, sources in datasets.items():
        summary = export_purpose_dataset(settings, character_id, dataset_kind, sources)
        summaries.append(summary)
        total_images += summary.image_count
    motion_summary = export_motion_dataset(
        settings,
        character_id,
        gather_motion_pairs(sampled_manifest),
    )
    summaries.append(motion_summary)
    total_images += motion_summary.image_count

    manifest_path = settings.project_root / "manifests" / "characters" / character_id / "dataset_builder_v2.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "manifest_type": DATASET_BUNDLE_MANIFEST_TYPE,
                "generated_at": utc_timestamp(),
                "character_id": character_id,
                "video_id": video_id,
                "inputs": {
                    "character_master_asset": optional_relative_path(settings, character_master_asset_manifest_path(settings, character_id)),
                    "character_sheet_import": optional_relative_path(settings, find_sheet_import_manifest(settings, character_id, sheet_id)),
                    "sampled_manifest": optional_relative_path(settings, sampled_manifest_path(settings, character_id, video_id)),
                    "classification_manifest": optional_relative_path(settings, classification_manifest_path(settings, character_id, video_id)),
                },
                "datasets": [asdict(summary) for summary in summaries],
                "notes": [
                    "Dataset Builder v2 groups assets by purpose instead of sending everything into a single LoRA dataset.",
                    "Motion entries preserve consecutive frame pairs within each detected shot.",
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return DatasetBuilderV2Result(
        manifest_path=manifest_path,
        character_id=character_id,
        video_id=video_id,
        dataset_count=len(summaries),
        total_images=total_images,
    )


def gather_master_asset_sources(
    settings: AppSettings,
    character_id: str,
    manifest: dict[str, object],
) -> list[DatasetSourceAsset]:
    if not manifest:
        return []
    paths = dict(manifest.get("paths", {}))
    result: list[DatasetSourceAsset] = []
    for key, extra_tags in {
        "reviewed_image": ["reviewed_sheet", "character_sheet"],
        "master_image": ["master_sheet", "character_sheet", "identity_anchor"],
    }.items():
        source_path = str(paths.get(key, ""))
        if not source_path:
            continue
        result.append(
            DatasetSourceAsset(
                dataset_kind="character",
                source_path=source_path,
                source_type="master_asset",
                origin_id=key,
                tags=dedupe_tags([character_id, *extra_tags]),
                reason="Human-reviewed character sheet asset promoted into purpose-specific datasets.",
            )
        )
    return result


def gather_character_sheet_sources(
    manifest: dict[str, object],
    section_ids: set[str],
    dataset_kind: str,
    source_type: str,
) -> list[DatasetSourceAsset]:
    if not manifest:
        return []
    result: list[DatasetSourceAsset] = []
    for item in manifest.get("sections", []):
        section_id = str(item.get("section_id", ""))
        if section_id not in section_ids:
            continue
        source_path = str(item.get("image_path", ""))
        if not source_path:
            continue
        result.append(
            DatasetSourceAsset(
                dataset_kind=dataset_kind,
                source_path=source_path,
                source_type=source_type,
                origin_id=section_id,
                tags=dedupe_tags([str(tag) for tag in item.get("tags", [])]),
                reason="Character sheet region exported from the fixed template importer.",
            )
        )
    return result


def export_purpose_dataset(
    settings: AppSettings,
    character_id: str,
    dataset_kind: str,
    sources: list[DatasetSourceAsset],
) -> PurposeDatasetSummary:
    dataset_dir = settings.project_root / "datasets" / "v2" / character_id / dataset_kind
    images_dir = dataset_dir / "images"
    reset_generated_images(images_dir)
    exported_entries: list[dict[str, object]] = []
    seen_sources: set[str] = set()
    for index, source in enumerate(sources, start=1):
        if source.source_path in seen_sources:
            continue
        seen_sources.add(source.source_path)
        source_path = resolve_project_path(settings, source.source_path)
        if not source_path.exists() or not source_path.is_file():
            continue
        destination = images_dir / f"{index:03d}_{dataset_kind}_{source.origin_id}{source_path.suffix}"
        if destination.resolve() != source_path.resolve():
            shutil.copy2(source_path, destination)
        caption_path = destination.with_suffix(".txt")
        caption_path.write_text(", ".join(dedupe_tags(source.tags)) + "\n", encoding="utf-8")
        exported_entries.append(
            {
                "source_path": project_relative_path(settings, source_path),
                "image_path": project_relative_path(settings, destination),
                "caption_path": project_relative_path(settings, caption_path),
                "source_type": source.source_type,
                "origin_id": source.origin_id,
                "tags": dedupe_tags(source.tags),
                "reason": source.reason,
            }
        )
    manifest_path = dataset_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "manifest_type": DATASET_MANIFEST_TYPE,
                "generated_at": utc_timestamp(),
                "character_id": character_id,
                "dataset_kind": dataset_kind,
                "image_count": len(exported_entries),
                "entries": exported_entries,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return PurposeDatasetSummary(
        dataset_kind=dataset_kind,
        dataset_dir=project_relative_path(settings, dataset_dir),
        image_count=len(exported_entries),
        manifest_path=project_relative_path(settings, manifest_path),
    )


def gather_motion_pairs(sampled_manifest: dict[str, object]) -> list[tuple[dict[str, object], dict[str, object]]]:
    grouped: dict[str, list[dict[str, object]]] = {}
    for raw_item in sampled_manifest.get("frames", []):
        item = dict(raw_item)
        shot_id = str(item.get("shot_id", "unknown"))
        grouped.setdefault(shot_id, []).append(item)
    pairs: list[tuple[dict[str, object], dict[str, object]]] = []
    for shot_id in sorted(grouped):
        ordered = sorted(
            grouped[shot_id],
            key=lambda item: (
                float(item.get("timestamp_seconds", 0.0) or 0.0),
                int(item.get("frame_index", 0) or 0),
            ),
        )
        pairs.extend(zip(ordered, ordered[1:]))
    return pairs


def export_motion_dataset(
    settings: AppSettings,
    character_id: str,
    pairs: list[tuple[dict[str, object], dict[str, object]]],
) -> PurposeDatasetSummary:
    dataset_dir = settings.project_root / "datasets" / "v2" / character_id / "motion"
    images_dir = dataset_dir / "images"
    reset_generated_images(images_dir)
    entries: list[dict[str, object]] = []
    exported_images: set[str] = set()
    for index, (start, end) in enumerate(pairs, start=1):
        start_path = resolve_project_path(settings, str(start.get("frame_path", "")))
        end_path = resolve_project_path(settings, str(end.get("frame_path", "")))
        if not start_path.is_file() or not end_path.is_file():
            continue
        shot_id = str(start.get("shot_id", "unknown"))
        start_output = images_dir / f"{index:03d}_motion_{shot_id}_from{start_path.suffix}"
        end_output = images_dir / f"{index:03d}_motion_{shot_id}_to{end_path.suffix}"
        motion_tags = dedupe_tags(
            [
                character_id,
                "motion_reference",
                *[str(tag) for tag in start.get("tags", [])],
                *[str(tag) for tag in end.get("tags", [])],
            ]
        )
        for source, destination, role in (
            (start_path, start_output, "motion_start"),
            (end_path, end_output, "motion_end"),
        ):
            if destination.resolve() != source.resolve():
                shutil.copy2(source, destination)
            destination.with_suffix(".txt").write_text(
                ", ".join(dedupe_tags([*motion_tags, role])) + "\n",
                encoding="utf-8",
            )
            exported_images.add(project_relative_path(settings, destination))
        entries.append(
            {
                "pair_id": f"motion_{index:06d}",
                "shot_id": shot_id,
                "from_image": project_relative_path(settings, start_output),
                "to_image": project_relative_path(settings, end_output),
                "start_seconds": float(start.get("timestamp_seconds", 0.0) or 0.0),
                "end_seconds": float(end.get("timestamp_seconds", 0.0) or 0.0),
                "tags": motion_tags,
                "training_role": "2p5d_motion_transition_and_lora_inbetween_completion",
            }
        )
    manifest_path = dataset_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "manifest_type": DATASET_MANIFEST_TYPE,
                "generated_at": utc_timestamp(),
                "character_id": character_id,
                "dataset_kind": "motion",
                "pair_count": len(entries),
                "image_count": len(exported_images),
                "entries": entries,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return PurposeDatasetSummary(
        dataset_kind="motion",
        dataset_dir=project_relative_path(settings, dataset_dir),
        image_count=len(exported_images),
        manifest_path=project_relative_path(settings, manifest_path),
    )


def reset_generated_images(images_dir: Path) -> None:
    images_dir.mkdir(parents=True, exist_ok=True)
    for path in images_dir.iterdir():
        if path.is_file():
            path.unlink()


def add_sources(target: list[DatasetSourceAsset], values: Iterable[DatasetSourceAsset]) -> None:
    target.extend(values)


def character_master_asset_manifest_path(settings: AppSettings, character_id: str) -> Path:
    return settings.project_root / "manifests" / "characters" / character_id / "character_sheet" / "character_master_asset.json"


def find_sheet_import_manifest(settings: AppSettings, character_id: str, sheet_id: str) -> Path | None:
    manifest_dir = settings.project_root / "manifests" / "characters" / character_id / "character_sheet"
    if sheet_id.strip():
        path = manifest_dir / f"{sheet_id}_import.json"
        return path if path.exists() else None
    candidates = sorted(manifest_dir.glob("*_import.json"))
    return candidates[-1] if candidates else None


def load_optional_json(path: Path | None) -> dict[str, object]:
    if path is None or not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_project_path(settings: AppSettings, value: str | Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = settings.project_root / path
    return path


def optional_relative_path(settings: AppSettings, path: Path | None) -> str:
    if path is None or not path.exists():
        return ""
    return project_relative_path(settings, path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="anime-dataset-builder-v2",
        description="Build purpose-specific datasets from character sheets, master assets, and classified video samples.",
    )
    parser.add_argument("--config", default="config/local_6gb.json", help="Path to the local runtime profile.")
    parser.add_argument("--character-id", required=True, help="Character id.")
    parser.add_argument("--video-id", required=True, help="Video id used for sampled/classified frames.")
    parser.add_argument("--sheet-id", default="", help="Optional imported character sheet id.")
    parser.add_argument("--no-character-sheet", action="store_true", help="Do not use imported character sheet regions.")
    parser.add_argument("--no-master-asset", action="store_true", help="Do not use reviewed/master assets.")
    parser.add_argument("--no-video-samples", action="store_true", help="Do not use sampled/classified video frames.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    settings = load_settings(args.config)
    result = build_purpose_datasets_v2(
        settings=settings,
        character_id=args.character_id,
        video_id=args.video_id,
        sheet_id=args.sheet_id,
        include_character_sheet=not args.no_character_sheet,
        include_master_asset=not args.no_master_asset,
        include_video_samples=not args.no_video_samples,
    )
    print(f"Dataset Builder v2 manifest: {result.manifest_path}")
    print(f"Character: {result.character_id}")
    print(f"Video id: {result.video_id}")
    print(f"Datasets: {result.dataset_count}")
    print(f"Total images: {result.total_images}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
