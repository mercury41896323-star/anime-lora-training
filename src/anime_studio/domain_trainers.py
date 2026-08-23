from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
import json
from pathlib import Path
from statistics import mean
from typing import Any, Callable

from .character_profile import link_character_domain_model, validate_character_id
from .lora_registry import project_relative_path, utc_timestamp
from .settings import AppSettings, load_settings


TRAINABLE_DOMAINS = ("motion", "camera", "background", "lighting")
TRAINER_BUNDLE_MANIFEST_TYPE = "domain_trainer_bundle"


@dataclass(frozen=True)
class DomainTrainerResult:
    domain: str
    provider: str
    trained: bool
    entry_count: int
    config_path: Path
    model_path: Path
    manifest_path: Path


@dataclass(frozen=True)
class DomainTrainerBundleResult:
    manifest_path: Path
    character_id: str
    video_id: str
    results: list[DomainTrainerResult]


def train_domain_model(
    settings: AppSettings,
    character_id: str,
    video_id: str,
    domain: str,
    provider: str = "baseline",
) -> DomainTrainerResult:
    validate_character_id(character_id)
    if domain not in TRAINABLE_DOMAINS:
        raise ValueError(f"Unsupported trainer domain: {domain}")
    if provider != "baseline":
        raise ValueError(f"Unsupported trainer provider: {provider}")

    dataset_dir = domain_dataset_dir(settings, character_id, video_id, domain)
    entries_path = dataset_dir / "entries.jsonl"
    if not entries_path.is_file():
        raise FileNotFoundError(f"Domain dataset entries do not exist: {entries_path}")
    entries = read_jsonl(entries_path)
    trainer_dir = settings.project_root / "models" / "domain" / character_id / video_id / domain
    trainer_dir.mkdir(parents=True, exist_ok=True)
    config_path = trainer_dir / "trainer_config.json"
    model_path = trainer_dir / "baseline_model.json"
    manifest_path = trainer_dir / "trainer_manifest.json"
    trainer = trainer_for_domain(domain)
    trained = bool(entries)

    config = {
        "schema_version": 1,
        "trainer_type": f"{domain}_trainer",
        "provider": provider,
        "device": "cpu",
        "low_vram": True,
        "character_id": character_id,
        "video_id": video_id,
        "domain": domain,
        "dataset_entries": project_relative_path(settings, entries_path),
        "entry_count": len(entries),
        "output_model": project_relative_path(settings, model_path),
        "future_provider_contract": future_provider_contract(domain),
    }
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    model = trainer(entries)
    model.update(
        {
            "schema_version": 1,
            "model_type": f"{domain}_baseline_prior",
            "provider": provider,
            "trained_at": utc_timestamp(),
            "character_id": character_id,
            "video_id": video_id,
            "domain": domain,
            "entry_count": len(entries),
            "status": "trained" if trained else "needs_data",
            "runtime": "cpu_lightweight",
        }
    )
    model_path.write_text(json.dumps(model, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "manifest_type": "domain_trainer_result",
                "generated_at": utc_timestamp(),
                "character_id": character_id,
                "video_id": video_id,
                "domain": domain,
                "provider": provider,
                "trained": trained,
                "entry_count": len(entries),
                "config": project_relative_path(settings, config_path),
                "model": project_relative_path(settings, model_path),
                "dataset": project_relative_path(settings, dataset_dir),
                "next_provider": future_provider_contract(domain),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    if trained:
        link_character_domain_model(settings, character_id, domain, model_path)
    return DomainTrainerResult(
        domain=domain,
        provider=provider,
        trained=trained,
        entry_count=len(entries),
        config_path=config_path,
        model_path=model_path,
        manifest_path=manifest_path,
    )


def train_all_domain_models(
    settings: AppSettings,
    character_id: str,
    video_id: str,
    provider: str = "baseline",
) -> DomainTrainerBundleResult:
    results = [
        train_domain_model(settings, character_id, video_id, domain, provider)
        for domain in TRAINABLE_DOMAINS
    ]
    manifest_path = (
        settings.project_root
        / "models"
        / "domain"
        / character_id
        / video_id
        / "domain_trainer_bundle.json"
    )
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "manifest_type": TRAINER_BUNDLE_MANIFEST_TYPE,
                "generated_at": utc_timestamp(),
                "character_id": character_id,
                "video_id": video_id,
                "provider": provider,
                "trained_count": sum(1 for result in results if result.trained),
                "results": [
                    {
                        **asdict(result),
                        "config_path": project_relative_path(settings, result.config_path),
                        "model_path": project_relative_path(settings, result.model_path),
                        "manifest_path": project_relative_path(settings, result.manifest_path),
                    }
                    for result in results
                ],
                "usage": {
                    "2p5d": "primary animation and identity control",
                    "domain_models": "motion, camera, background, and lighting priors",
                    "lora": "residual rendering and in-between completion",
                },
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return DomainTrainerBundleResult(manifest_path, character_id, video_id, results)


def train_motion_baseline(entries: list[dict[str, Any]]) -> dict[str, Any]:
    face_transitions: Counter[str] = Counter()
    expression_transitions: Counter[str] = Counter()
    body_transitions: Counter[str] = Counter()
    durations: list[float] = []
    for item in entries:
        start = dict(item.get("from_state") or {})
        end = dict(item.get("to_state") or {})
        face_transitions[f"{start.get('face_angle', 'unknown')}->{end.get('face_angle', 'unknown')}"] += 1
        expression_transitions[f"{start.get('expression', 'unknown')}->{end.get('expression', 'unknown')}"] += 1
        body_transitions[f"{start.get('body_framing', 'unknown')}->{end.get('body_framing', 'unknown')}"] += 1
        duration = float(item.get("end_seconds", 0.0) or 0.0) - float(item.get("start_seconds", 0.0) or 0.0)
        if duration >= 0:
            durations.append(duration)
    return {
        "model_kind": "motion_transition_prior",
        "face_transition_counts": dict(face_transitions.most_common()),
        "expression_transition_counts": dict(expression_transitions.most_common()),
        "body_transition_counts": dict(body_transitions.most_common()),
        "average_transition_seconds": round(mean(durations), 4) if durations else 0.0,
        "2p5d_binding": "use transitions as keyframe and in-between hints",
    }


def train_camera_baseline(entries: list[dict[str, Any]]) -> dict[str, Any]:
    distances = Counter(str(item.get("camera_distance", "unknown")) for item in entries)
    angles = Counter(str(item.get("face_angle", "unknown")) for item in entries)
    boundaries = Counter(str(item.get("shot_boundary_reason", "unknown")) for item in entries)
    return {
        "model_kind": "camera_composition_prior",
        "camera_distance_distribution": normalized_distribution(distances),
        "face_angle_distribution": normalized_distribution(angles),
        "shot_boundary_distribution": normalized_distribution(boundaries),
        "recommended_camera_distance": most_common_key(distances),
    }


def train_background_baseline(entries: list[dict[str, Any]]) -> dict[str, Any]:
    tags = Counter(
        str(tag)
        for item in entries
        for tag in item.get("background_tags", [])
        if str(tag)
    )
    segmentation_required = sum(
        1 for item in entries if bool(item.get("requires_character_segmentation", False))
    )
    return {
        "model_kind": "background_tag_prior",
        "background_tag_distribution": normalized_distribution(tags),
        "recommended_background_tags": [key for key, _ in tags.most_common(12)],
        "segmentation_required_ratio": round(segmentation_required / len(entries), 4)
        if entries
        else 0.0,
    }


def train_lighting_baseline(entries: list[dict[str, Any]]) -> dict[str, Any]:
    tags = Counter(
        str(tag)
        for item in entries
        for tag in item.get("lighting_tags", [])
        if str(tag)
    )
    by_shot: dict[str, Counter[str]] = defaultdict(Counter)
    for item in entries:
        shot_id = str(item.get("shot_id", "unknown"))
        for tag in item.get("lighting_tags", []):
            by_shot[shot_id][str(tag)] += 1
    return {
        "model_kind": "lighting_continuity_prior",
        "lighting_tag_distribution": normalized_distribution(tags),
        "recommended_lighting_tags": [key for key, _ in tags.most_common(8)],
        "shot_lighting_profiles": {
            shot_id: normalized_distribution(values) for shot_id, values in by_shot.items()
        },
    }


def trainer_for_domain(domain: str) -> Callable[[list[dict[str, Any]]], dict[str, Any]]:
    return {
        "motion": train_motion_baseline,
        "camera": train_camera_baseline,
        "background": train_background_baseline,
        "lighting": train_lighting_baseline,
    }[domain]


def normalized_distribution(counter: Counter[str]) -> dict[str, float]:
    total = sum(counter.values())
    if not total:
        return {}
    return {key: round(value / total, 4) for key, value in counter.most_common()}


def most_common_key(counter: Counter[str]) -> str:
    return counter.most_common(1)[0][0] if counter else "unknown"


def future_provider_contract(domain: str) -> dict[str, str]:
    return {
        "motion": {
            "target": "AnimateDiff Motion LoRA or temporal adapter",
            "input": "ordered frame pairs plus 2.5D state transitions",
        },
        "camera": {
            "target": "camera classifier or trajectory adapter",
            "input": "camera distance, face angle, and shot transition labels",
        },
        "background": {
            "target": "background LoRA or scene layout adapter",
            "input": "character-segmented background frames and tags",
        },
        "lighting": {
            "target": "lighting LoRA or relighting adapter",
            "input": "lighting tags, color metadata, and shot continuity groups",
        },
    }[domain]


def domain_dataset_dir(
    settings: AppSettings,
    character_id: str,
    video_id: str,
    domain: str,
) -> Path:
    return settings.project_root / "datasets" / "video_learning" / character_id / video_id / domain


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            entries.append(json.loads(line))
    return entries


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="anime-domain-trainer",
        description="Train lightweight motion, camera, background, and lighting domain priors.",
    )
    parser.add_argument("--config", default="config/local_6gb.json", help="Path to the local runtime profile.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    train = subparsers.add_parser("train", help="Train one domain model.")
    train.add_argument("--character-id", required=True, help="Character id.")
    train.add_argument("--video-id", required=True, help="Video id.")
    train.add_argument("--domain", required=True, choices=TRAINABLE_DOMAINS, help="Domain trainer.")
    train.add_argument("--provider", default="baseline", help="Trainer provider.")
    train_all = subparsers.add_parser("train-all", help="Train all four domain models.")
    train_all.add_argument("--character-id", required=True, help="Character id.")
    train_all.add_argument("--video-id", required=True, help="Video id.")
    train_all.add_argument("--provider", default="baseline", help="Trainer provider.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = load_settings(args.config)
    if args.command == "train":
        result = train_domain_model(
            settings, args.character_id, args.video_id, args.domain, args.provider
        )
        print(f"{result.domain} model: {result.model_path}")
        print(f"Trained: {result.trained}")
        return 0 if result.trained else 1
    result = train_all_domain_models(settings, args.character_id, args.video_id, args.provider)
    print(f"Domain trainer bundle: {result.manifest_path}")
    print(f"Trained: {sum(1 for item in result.results if item.trained)}/{len(result.results)}")
    return 0 if all(item.trained for item in result.results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
