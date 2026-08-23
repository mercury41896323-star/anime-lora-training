from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any

from .character_profile import validate_character_id
from .lora_registry import project_relative_path, utc_timestamp
from .settings import AppSettings, load_settings
from .video_frame_cleaner import clean_frame_manifest_path
from .video_shot_pipeline import classification_manifest_path, shot_manifest_path


DOMAIN_BUNDLE_MANIFEST_TYPE = "video_learning_domain_bundle"
DOMAIN_NAMES = ("character", "motion", "camera", "background", "lighting")


@dataclass(frozen=True)
class DomainDatasetSummary:
    domain: str
    dataset_dir: str
    manifest_path: str
    entry_count: int
    learning_status: str
    model_training_implemented: bool


@dataclass(frozen=True)
class VideoDomainDatasetResult:
    manifest_path: Path
    dataset_root: Path
    character_id: str
    video_id: str
    datasets: list[DomainDatasetSummary]


def build_video_domain_datasets(
    settings: AppSettings,
    character_id: str,
    video_id: str,
) -> VideoDomainDatasetResult:
    validate_character_id(character_id)
    clean_manifest = load_required_json(clean_frame_manifest_path(settings, character_id, video_id))
    classification_manifest = load_optional_json(
        classification_manifest_path(settings, character_id, video_id)
    )
    shot_manifest = load_optional_json(shot_manifest_path(settings, character_id, video_id))
    classifications = {
        normalize_path(str(item.get("frame_path", ""))): dict(item)
        for item in classification_manifest.get("classifications", [])
    }
    clean_frames = [
        dict(item)
        for item in clean_manifest.get("frames", [])
        if item.get("status") == "review_candidate" and item.get("output_path")
    ]
    dataset_root = settings.project_root / "datasets" / "video_learning" / character_id / video_id
    domain_entries = {
        "character": build_character_entries(clean_frames, classifications),
        "motion": build_motion_entries(clean_frames, classifications),
        "camera": build_camera_entries(clean_frames, classifications, shot_manifest),
        "background": build_background_entries(clean_frames),
        "lighting": build_lighting_entries(clean_frames),
    }
    summaries: list[DomainDatasetSummary] = []
    for domain in DOMAIN_NAMES:
        entries = domain_entries[domain]
        domain_dir = dataset_root / domain
        domain_dir.mkdir(parents=True, exist_ok=True)
        entries_path = domain_dir / "entries.jsonl"
        write_jsonl(entries_path, entries)
        manifest_path = domain_dir / "manifest.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "manifest_type": "video_learning_domain_dataset",
                    "generated_at": utc_timestamp(),
                    "character_id": character_id,
                    "video_id": video_id,
                    "domain": domain,
                    "entry_count": len(entries),
                    "entries": project_relative_path(settings, entries_path),
                    "learning_status": "dataset_ready" if entries else "needs_data",
                    "model_training_implemented": True,
                    "training_role": domain_training_role(domain),
                    "limitations": domain_limitations(domain),
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        summaries.append(
            DomainDatasetSummary(
                domain=domain,
                dataset_dir=project_relative_path(settings, domain_dir),
                manifest_path=project_relative_path(settings, manifest_path),
                entry_count=len(entries),
                learning_status="dataset_ready" if entries else "needs_data",
                model_training_implemented=True,
            )
        )

    bundle_path = dataset_root / "video_learning_bundle.json"
    bundle_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "manifest_type": DOMAIN_BUNDLE_MANIFEST_TYPE,
                "generated_at": utc_timestamp(),
                "character_id": character_id,
                "video_id": video_id,
                "source_manifests": {
                    "clean_frames": project_relative_path(
                        settings, clean_frame_manifest_path(settings, character_id, video_id)
                    ),
                    "classifications": optional_relative_path(
                        settings, classification_manifest_path(settings, character_id, video_id)
                    ),
                    "shots": optional_relative_path(
                        settings, shot_manifest_path(settings, character_id, video_id)
                    ),
                },
                "datasets": [asdict(summary) for summary in summaries],
                "learning_architecture": {
                    "primary_control": "character_2p5d_definition",
                    "lora_role": "residual completion over 2.5D animation",
                    "domains": list(DOMAIN_NAMES),
                },
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return VideoDomainDatasetResult(bundle_path, dataset_root, character_id, video_id, summaries)


def build_character_entries(
    frames: list[dict[str, Any]],
    classifications: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for item in frames:
        source = normalize_path(str(item.get("source_frame_path", "")))
        classification = classifications.get(source, {})
        entries.append(
            {
                "entry_id": f"character_{int(item.get('frame_index', len(entries) + 1)):06d}",
                "image_path": str(item.get("output_path", "")),
                "source_frame_path": source,
                "shot_id": str(item.get("shot_id", "")),
                "timestamp_seconds": float(item.get("timestamp_seconds", 0.0) or 0.0),
                "face_angle": str(classification.get("face_angle", "unknown")),
                "expression": str(classification.get("expression", "unknown")),
                "body_framing": str(classification.get("body_framing", "unknown")),
                "tags": list(item.get("tags", [])),
                "training_role": "2p5d_identity_and_lora_residual_reference",
            }
        )
    return entries


def build_motion_entries(
    frames: list[dict[str, Any]],
    classifications: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in frames:
        grouped.setdefault(str(item.get("shot_id", "unknown")), []).append(item)
    entries: list[dict[str, Any]] = []
    for shot_id, values in grouped.items():
        ordered = sorted(values, key=lambda item: float(item.get("timestamp_seconds", 0.0) or 0.0))
        for start, end in zip(ordered, ordered[1:]):
            start_class = classifications.get(
                normalize_path(str(start.get("source_frame_path", ""))), {}
            )
            end_class = classifications.get(
                normalize_path(str(end.get("source_frame_path", ""))), {}
            )
            entries.append(
                {
                    "entry_id": f"motion_{len(entries) + 1:06d}",
                    "shot_id": shot_id,
                    "from_image": str(start.get("output_path", "")),
                    "to_image": str(end.get("output_path", "")),
                    "start_seconds": float(start.get("timestamp_seconds", 0.0) or 0.0),
                    "end_seconds": float(end.get("timestamp_seconds", 0.0) or 0.0),
                    "from_state": compact_classification(start_class),
                    "to_state": compact_classification(end_class),
                    "training_role": "2p5d_motion_transition_and_lora_inbetween_completion",
                }
            )
    return entries


def build_camera_entries(
    frames: list[dict[str, Any]],
    classifications: dict[str, dict[str, Any]],
    shot_manifest: dict[str, Any],
) -> list[dict[str, Any]]:
    by_shot = {str(item.get("shot_id", "")): dict(item) for item in shot_manifest.get("shots", [])}
    entries: list[dict[str, Any]] = []
    for item in frames:
        source = normalize_path(str(item.get("source_frame_path", "")))
        classification = classifications.get(source, {})
        body_framing = str(classification.get("body_framing", "unknown"))
        entries.append(
            {
                "entry_id": f"camera_{len(entries) + 1:06d}",
                "image_path": str(item.get("output_path", "")),
                "shot_id": str(item.get("shot_id", "")),
                "timestamp_seconds": float(item.get("timestamp_seconds", 0.0) or 0.0),
                "camera_distance": camera_distance_from_body_framing(body_framing),
                "face_angle": str(classification.get("face_angle", "unknown")),
                "shot_boundary_reason": str(
                    by_shot.get(str(item.get("shot_id", "")), {}).get("boundary_reason", "")
                ),
                "training_role": "camera_composition_reference",
            }
        )
    return entries


def build_background_entries(frames: list[dict[str, Any]]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for item in frames:
        tags = [str(tag) for tag in item.get("tags", [])]
        entries.append(
            {
                "entry_id": f"background_{len(entries) + 1:06d}",
                "image_path": str(item.get("output_path", "")),
                "shot_id": str(item.get("shot_id", "")),
                "background_tags": [tag for tag in tags if not is_character_tag(tag)],
                "requires_character_segmentation": True,
                "training_role": "background_layout_and_style_reference",
            }
        )
    return entries


def build_lighting_entries(frames: list[dict[str, Any]]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for item in frames:
        tags = [str(tag) for tag in item.get("tags", [])]
        lighting_tags = [tag for tag in tags if is_lighting_tag(tag)]
        entries.append(
            {
                "entry_id": f"lighting_{len(entries) + 1:06d}",
                "image_path": str(item.get("output_path", "")),
                "shot_id": str(item.get("shot_id", "")),
                "timestamp_seconds": float(item.get("timestamp_seconds", 0.0) or 0.0),
                "lighting_tags": lighting_tags or ["unknown_lighting"],
                "training_role": "lighting_direction_color_and_continuity_reference",
            }
        )
    return entries


def compact_classification(value: dict[str, Any]) -> dict[str, str]:
    return {
        "face_angle": str(value.get("face_angle", "unknown")),
        "expression": str(value.get("expression", "unknown")),
        "body_framing": str(value.get("body_framing", "unknown")),
    }


def camera_distance_from_body_framing(value: str) -> str:
    return {
        "portrait": "close_up",
        "upper_body": "medium",
        "full_body": "full_body",
    }.get(value, "unknown")


def is_character_tag(value: str) -> bool:
    normalized = value.lower().replace(" ", "_")
    tokens = (
        "portrait",
        "face",
        "body",
        "hair",
        "eyes",
        "smile",
        "serious",
        "character",
        "front",
        "side",
    )
    return any(token in normalized for token in tokens)


def is_lighting_tag(value: str) -> bool:
    normalized = value.lower().replace(" ", "_")
    return any(
        token in normalized
        for token in (
            "light",
            "shadow",
            "backlit",
            "rim",
            "sunset",
            "night",
            "warm",
            "cool",
            "dramatic",
        )
    )


def domain_training_role(domain: str) -> str:
    return {
        "character": "2p5d identity mapping followed by LoRA residual completion",
        "motion": "2p5d keyframe transition and in-between reference",
        "camera": "shot composition and camera direction reference",
        "background": "background layout and style reference",
        "lighting": "lighting direction, palette, and continuity reference",
    }[domain]


def domain_limitations(domain: str) -> list[str]:
    if domain == "background":
        return ["Background LoRA remains blocked until reviewed segmented_image_path values are supplied."]
    if domain == "motion":
        return ["AnimateDiff job preparation is implemented, but its official training path is not safe on 6GB VRAM."]
    if domain in {"camera", "lighting"}:
        return ["Compact neural adapters use lightweight heuristic labels and require review before production use."]
    return ["LoRA training is generated only after a ready 2.5D definition exists."]


def write_jsonl(path: Path, entries: list[dict[str, Any]]) -> None:
    path.write_text(
        ("\n".join(json.dumps(item, ensure_ascii=False) for item in entries) + "\n")
        if entries
        else "",
        encoding="utf-8",
    )


def load_required_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"Required manifest does not exist: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def load_optional_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def optional_relative_path(settings: AppSettings, path: Path) -> str:
    return project_relative_path(settings, path) if path.exists() else ""


def normalize_path(value: str) -> str:
    return value.replace("\\", "/")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="anime-video-domain-datasets",
        description="Build character, motion, camera, background, and lighting datasets from video analysis.",
    )
    parser.add_argument("--config", default="config/local_6gb.json", help="Path to the local runtime profile.")
    parser.add_argument("--character-id", required=True, help="Character id.")
    parser.add_argument("--video-id", required=True, help="Imported video id.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = load_settings(args.config)
    result = build_video_domain_datasets(settings, args.character_id, args.video_id)
    print(f"Video learning bundle: {result.manifest_path}")
    for dataset in result.datasets:
        print(f"{dataset.domain}: {dataset.entry_count} entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
