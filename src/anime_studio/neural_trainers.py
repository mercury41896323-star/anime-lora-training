from __future__ import annotations

import argparse
import csv
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import shutil
from typing import Any

from PIL import Image, ImageStat

from .character_profile import link_character_domain_model, validate_character_id
from .kohya_config import powershell_quote, render_dataset_toml
from .lora_registry import project_relative_path, utc_timestamp
from .settings import AppSettings, load_settings


NEURAL_PROVIDERS = {
    "motion": "animatediff_motion_module_job",
    "background": "background_lora",
    "camera": "camera_trajectory_adapter",
    "lighting": "relighting_provider",
}


@dataclass(frozen=True)
class NeuralTrainingJobResult:
    domain: str
    provider: str
    status: str
    ready: bool
    entry_count: int
    job_dir: Path
    config_path: Path
    manifest_path: Path
    run_script: Path
    model_descriptor: Path
    issues: list[str]


@dataclass(frozen=True)
class NeuralTrainingBundleResult:
    manifest_path: Path
    results: list[NeuralTrainingJobResult]


def prepare_neural_training_job(
    settings: AppSettings,
    character_id: str,
    video_id: str,
    domain: str,
    *,
    pretrained_model: str = "",
    trainer_root: str = "",
    source_video: str = "",
    allow_unsegmented_background: bool = False,
) -> NeuralTrainingJobResult:
    validate_character_id(character_id)
    if domain not in NEURAL_PROVIDERS:
        raise ValueError(f"Unsupported neural trainer domain: {domain}")
    entries_path = (
        settings.project_root
        / "datasets"
        / "video_learning"
        / character_id
        / video_id
        / domain
        / "entries.jsonl"
    )
    if not entries_path.is_file():
        raise FileNotFoundError(f"Domain dataset entries do not exist: {entries_path}")
    entries = read_jsonl(entries_path)
    provider = NEURAL_PROVIDERS[domain]
    job_dir = settings.project_root / "models" / "neural" / character_id / video_id / domain
    job_dir.mkdir(parents=True, exist_ok=True)
    config_path = job_dir / "trainer_config.json"
    manifest_path = job_dir / "trainer_manifest.json"
    run_script = job_dir / "run_train.ps1"
    model_descriptor = job_dir / "model_descriptor.json"

    if domain == "motion":
        payload, issues = prepare_animatediff_job(
            settings, job_dir, entries, pretrained_model, trainer_root, source_video
        )
    elif domain == "background":
        payload, issues = prepare_background_lora_job(
            settings,
            character_id,
            job_dir,
            entries,
            pretrained_model,
            trainer_root,
            allow_unsegmented_background,
        )
    else:
        payload, issues = prepare_compact_adapter_job(settings, job_dir, domain, entries)

    ready = bool(entries) and not issues
    status = "ready" if ready else "blocked"
    payload.update(
        {
            "schema_version": 1,
            "provider": provider,
            "domain": domain,
            "character_id": character_id,
            "video_id": video_id,
            "entry_count": len(entries),
            "status": status,
            "issues": issues,
            "low_vram_profile": settings.runtime.name,
            "max_vram_gb": settings.runtime.max_vram_gb,
        }
    )
    config_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    command = [str(part) for part in payload.get("command", [])]
    run_script.write_text(render_run_script(command, config_path, ready), encoding="utf-8")
    descriptor = {
        "schema_version": 1,
        "model_type": "neural_domain_provider",
        "model_kind": provider,
        "provider": provider,
        "domain": domain,
        "character_id": character_id,
        "video_id": video_id,
        "status": "prepared" if ready else "blocked",
        "training_config": project_relative_path(settings, config_path),
        "weights": project_relative_path(settings, job_dir / payload["output_weights"]),
        "runtime_contract": payload.get("runtime_contract", {}),
        "compatibility": payload.get("compatibility", {}),
    }
    model_descriptor.write_text(
        json.dumps(descriptor, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "manifest_type": "neural_training_job",
                "generated_at": utc_timestamp(),
                "domain": domain,
                "provider": provider,
                "status": status,
                "ready": ready,
                "entry_count": len(entries),
                "issues": issues,
                "config": project_relative_path(settings, config_path),
                "run_script": project_relative_path(settings, run_script),
                "model_descriptor": project_relative_path(settings, model_descriptor),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return NeuralTrainingJobResult(
        domain,
        provider,
        status,
        ready,
        len(entries),
        job_dir,
        config_path,
        manifest_path,
        run_script,
        model_descriptor,
        issues,
    )


def prepare_all_neural_training_jobs(
    settings: AppSettings,
    character_id: str,
    video_id: str,
    **kwargs: Any,
) -> NeuralTrainingBundleResult:
    results = [
        prepare_neural_training_job(settings, character_id, video_id, domain, **kwargs)
        for domain in NEURAL_PROVIDERS
    ]
    path = settings.project_root / "models" / "neural" / character_id / video_id / "bundle.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "manifest_type": "neural_training_bundle",
                "generated_at": utc_timestamp(),
                "ready_count": sum(1 for item in results if item.ready),
                "results": [
                    {
                        **asdict(item),
                        "job_dir": project_relative_path(settings, item.job_dir),
                        "config_path": project_relative_path(settings, item.config_path),
                        "manifest_path": project_relative_path(settings, item.manifest_path),
                        "run_script": project_relative_path(settings, item.run_script),
                        "model_descriptor": project_relative_path(settings, item.model_descriptor),
                    }
                    for item in results
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return NeuralTrainingBundleResult(path, results)


def prepare_animatediff_job(
    settings: AppSettings,
    job_dir: Path,
    entries: list[dict[str, Any]],
    pretrained_model: str,
    trainer_root: str,
    source_video: str,
) -> tuple[dict[str, Any], list[str]]:
    issues: list[str] = []
    video = resolve_optional_path(settings, source_video)
    trainer = resolve_optional_path(settings, trainer_root)
    model = resolve_optional_path(settings, pretrained_model)
    if video is None or not video.is_file() or video.suffix.lower() != ".mp4":
        issues.append("AnimateDiff公式datasetが読むMP4 source_videoを指定してください。")
    if trainer is None or not (trainer / "train.py").is_file():
        issues.append("公式guoyww/AnimateDiffのtrainer_rootを指定してください。")
    if model is None or not model.exists():
        issues.append("Stable Diffusion 1.5 pretrained_modelを指定してください。")
    if settings.runtime.max_vram_gb < 12:
        issues.append("AnimateDiff motion module/Motion LoRA本学習は6GB VRAMでは安全に実行できません。")

    csv_path = job_dir / "animatediff_dataset.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["videoid", "name", "page_dir"])
        writer.writeheader()
        writer.writerow(
            {
                "videoid": video.stem if video else "source_video",
                "name": build_motion_caption(entries),
                "page_dir": "local",
            }
        )
    yaml_path = job_dir / "animatediff_motion_lora.yaml"
    yaml_path.write_text(
        render_animatediff_yaml(
            csv_path,
            video.parent if video else job_dir,
            model or Path("MODEL_REQUIRED"),
            job_dir / "outputs",
        ),
        encoding="utf-8",
    )
    command = [
        "torchrun",
        "--nnodes=1",
        "--nproc_per_node=1",
        str((trainer / "train.py") if trainer else Path("ANIMATEDIFF_ROOT/train.py")),
        "--config",
        str(yaml_path),
    ]
    return {
        "trainer": "official_guoyww_animatediff",
        "dataset_csv": project_relative_path(settings, csv_path),
        "source_video": str(video or ""),
        "animatediff_config": project_relative_path(settings, yaml_path),
        "command": command,
        "output_weights": "outputs/latest_motion_module.ckpt",
        "runtime_contract": {"device": "cuda", "precision": "fp16", "sample_size": 256, "frames": 8},
        "compatibility": {
            "target": "AnimateDiff SD1.5 motion module",
            "motion_lora_status": "not_officially_exposed_by_reference_trainer",
            "note": "The official reference trainer exposes motion-module training, not a documented MotionLoRA training recipe.",
        },
    }, issues


def prepare_background_lora_job(
    settings: AppSettings,
    character_id: str,
    job_dir: Path,
    entries: list[dict[str, Any]],
    pretrained_model: str,
    trainer_root: str,
    allow_unsegmented: bool,
) -> tuple[dict[str, Any], list[str]]:
    issues: list[str] = []
    model = resolve_optional_path(settings, pretrained_model)
    trainer = resolve_optional_path(settings, trainer_root)
    if model is None or not model.exists():
        issues.append("Stable Diffusion 1.5 pretrained_modelを指定してください。")
    if trainer is None or not (trainer / "train_network.py").is_file():
        issues.append("kohya sd-scriptsのtrainer_rootを指定してください。")
    data_dir = job_dir / "training_data"
    data_dir.mkdir(parents=True, exist_ok=True)
    copied = 0
    blocked_unsegmented = 0
    for item in entries:
        segmented = str(item.get("segmented_image_path", ""))
        if bool(item.get("requires_character_segmentation", False)) and not segmented and not allow_unsegmented:
            blocked_unsegmented += 1
            continue
        source = resolve_optional_path(settings, segmented or str(item.get("image_path", "")))
        if source is None or not source.is_file():
            continue
        target = data_dir / f"background_{copied + 1:06d}{source.suffix.lower()}"
        shutil.copy2(source, target)
        tags = [str(value) for value in item.get("background_tags", []) if str(value)]
        target.with_suffix(".txt").write_text(", ".join(tags or ["anime background"]), encoding="utf-8")
        copied += 1
    if blocked_unsegmented:
        issues.append(f"{blocked_unsegmented}件に人物除去済みsegmented_image_pathがありません。")
    if copied == 0:
        issues.append("背景LoRAに使用できる画像がありません。")
    dataset_toml = job_dir / "dataset.toml"
    dataset_toml.write_text(render_dataset_toml(data_dir, "anime background", 5, 512, 1), encoding="utf-8")
    output_dir = job_dir / "outputs"
    command = [
        "accelerate", "launch", "--num_cpu_threads_per_process", "1",
        str((trainer / "train_network.py") if trainer else Path("SD_SCRIPTS_ROOT/train_network.py")),
        "--pretrained_model_name_or_path", str(model or "MODEL_REQUIRED"),
        "--dataset_config", str(dataset_toml),
        "--output_dir", str(output_dir),
        "--output_name", f"{character_id}_background_lora",
        "--save_model_as", "safetensors", "--network_module", "networks.lora",
        "--network_dim", "8", "--network_alpha", "4", "--learning_rate", "1e-4",
        "--optimizer_type", "AdamW8bit", "--max_train_epochs", "8",
        "--mixed_precision", "fp16", "--train_batch_size", "1",
        "--cache_latents", "--gradient_checkpointing", "--sdpa",
    ]
    return {
        "trainer": "kohya_sd_scripts",
        "dataset_config": project_relative_path(settings, dataset_toml),
        "prepared_image_count": copied,
        "command": command,
        "output_weights": f"outputs/{character_id}_background_lora.safetensors",
        "runtime_contract": {"device": "cuda", "precision": "fp16", "batch_size": 1, "rank": 8},
        "compatibility": {"target": "Stable Diffusion 1.5 LoRA", "format": "safetensors"},
    }, issues


def prepare_compact_adapter_job(
    settings: AppSettings,
    job_dir: Path,
    domain: str,
    entries: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[str]]:
    samples = build_camera_samples(entries) if domain == "camera" else build_lighting_samples(settings, entries)
    issues: list[str] = []
    if len(samples) < 2:
        issues.append("ニューラル学習には2件以上の有効sampleが必要です。")
    samples_path = job_dir / "training_samples.jsonl"
    write_jsonl(samples_path, samples)
    output_name = "camera_trajectory_adapter.pt" if domain == "camera" else "relighting_provider.pt"
    command = [
        "python", "-m", "anime_studio.compact_neural_trainer",
        "--domain", domain,
        "--samples", str(samples_path),
        "--output", str(job_dir / output_name),
        "--epochs", "120",
    ]
    return {
        "trainer": "anime_studio_compact_pytorch",
        "samples": project_relative_path(settings, samples_path),
        "sample_count": len(samples),
        "command": command,
        "output_weights": output_name,
        "runtime_contract": {"device": "cuda_or_cpu", "precision": "fp32", "max_vram_mb": 256},
        "compatibility": {
            "target": "Anime Studio B-control",
            "format": "PyTorch state_dict plus JSON metadata",
            "not_a_diffusers_adapter": True,
        },
    }, issues


def build_camera_samples(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    distances = ["unknown", "close_up", "medium", "full_body", "wide"]
    angles = ["unknown", "front", "side", "three_quarter", "up", "down", "back"]
    ordered = sorted(entries, key=lambda item: (str(item.get("shot_id", "")), float(item.get("timestamp_seconds", 0.0) or 0.0)))
    result: list[dict[str, Any]] = []
    for index, item in enumerate(ordered):
        next_item = ordered[min(index + 1, len(ordered) - 1)]
        result.append(
            {
                "id": str(item.get("entry_id", f"camera_{index + 1:06d}")),
                "features": one_hot(str(item.get("camera_distance", "unknown")), distances)
                + one_hot(str(item.get("face_angle", "unknown")), angles),
                "targets": one_hot(str(next_item.get("camera_distance", "unknown")), distances)
                + one_hot(str(next_item.get("face_angle", "unknown")), angles),
            }
        )
    return result


def build_lighting_samples(settings: AppSettings, entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    vocabulary = sorted({str(tag) for item in entries for tag in item.get("lighting_tags", []) if str(tag)})
    result: list[dict[str, Any]] = []
    for index, item in enumerate(entries):
        image_path = resolve_optional_path(settings, str(item.get("image_path", "")))
        if image_path is None or not image_path.is_file():
            continue
        with Image.open(image_path) as image:
            rgb = image.convert("RGB").resize((64, 64))
            stat = ImageStat.Stat(rgb)
            means = [round(value / 255.0, 6) for value in stat.mean]
            deviations = [round(value / 255.0, 6) for value in stat.stddev]
        tags = {str(tag) for tag in item.get("lighting_tags", [])}
        result.append(
            {
                "id": str(item.get("entry_id", f"lighting_{index + 1:06d}")),
                "features": means + deviations,
                "targets": [1.0 if tag in tags else 0.0 for tag in vocabulary],
                "target_labels": vocabulary,
            }
        )
    return result


def one_hot(value: str, vocabulary: list[str]) -> list[float]:
    normalized = value if value in vocabulary else "unknown"
    return [1.0 if item == normalized else 0.0 for item in vocabulary]


def build_motion_caption(entries: list[dict[str, Any]]) -> str:
    states = []
    for item in entries[:12]:
        start = dict(item.get("from_state") or {})
        end = dict(item.get("to_state") or {})
        states.append(f"{start.get('face_angle', 'unknown')} to {end.get('face_angle', 'unknown')}")
    return "anime character motion, " + ", ".join(dict.fromkeys(states))


def render_animatediff_yaml(csv_path: Path, video_folder: Path, model: Path, output_dir: Path) -> str:
    values = {
        "csv": str(csv_path).replace("\\", "/"),
        "video": str(video_folder).replace("\\", "/"),
        "model": str(model).replace("\\", "/"),
        "output": str(output_dir).replace("\\", "/"),
    }
    return f'''name: "anime_studio_motion"
use_wandb: false
launcher: "pytorch"
image_finetune: false
output_dir: "{values["output"]}"
pretrained_model_path: "{values["model"]}"
unet_additional_kwargs:
  use_motion_module: true
  motion_module_resolutions: [1, 2, 4, 8]
  motion_module_type: Vanilla
  motion_module_kwargs:
    num_attention_heads: 8
    num_transformer_block: 1
    attention_block_types: ["Temporal_Self", "Temporal_Self"]
    temporal_position_encoding: true
    temporal_position_encoding_max_len: 24
    temporal_attention_dim_div: 1
    zero_initialize: true
noise_scheduler_kwargs:
  num_train_timesteps: 1000
  beta_start: 0.00085
  beta_end: 0.012
  beta_schedule: "linear"
  steps_offset: 1
  clip_sample: false
train_data:
  csv_path: "{values["csv"]}"
  video_folder: "{values["video"]}"
  sample_size: 256
  sample_stride: 4
  sample_n_frames: 8
validation_data:
  prompts: ["anime character controlled motion"]
  num_inference_steps: 20
  guidance_scale: 7.5
trainable_modules: ["motion_modules."]
learning_rate: 1.e-5
train_batch_size: 1
gradient_accumulation_steps: 8
gradient_checkpointing: true
max_train_steps: 500
checkpointing_steps: 100
validation_steps: 500
global_seed: 42
mixed_precision_training: true
enable_xformers_memory_efficient_attention: true
is_debug: false
'''


def render_run_script(command: list[str], config_path: Path, ready: bool) -> str:
    lines = ["$ErrorActionPreference = \"Stop\"", f"$config = Get-Content {powershell_quote(str(config_path))} | ConvertFrom-Json"]
    if not ready:
        lines.extend(
            [
                "Write-Host 'Training job is blocked:' -ForegroundColor Yellow",
                "$config.issues | ForEach-Object { Write-Host ('- ' + $_) }",
                "exit 1",
            ]
        )
    else:
        lines.append("& " + " ".join(powershell_quote(value) for value in command))
    return "\n".join(lines) + "\n"


def mark_neural_job_trained(settings: AppSettings, character_id: str, video_id: str, domain: str) -> Path:
    job_dir = settings.project_root / "models" / "neural" / character_id / video_id / domain
    descriptor_path = job_dir / "model_descriptor.json"
    descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
    weights = settings.project_root / str(descriptor["weights"])
    if not weights.is_file():
        raise FileNotFoundError(f"Neural weights do not exist: {weights}")
    descriptor["status"] = "trained"
    descriptor["trained_at"] = utc_timestamp()
    descriptor_path.write_text(json.dumps(descriptor, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    link_character_domain_model(settings, character_id, domain, descriptor_path)
    return descriptor_path


def resolve_optional_path(settings: AppSettings, value: str) -> Path | None:
    if not value:
        return None
    path = Path(value)
    return path if path.is_absolute() else settings.project_root / path


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, values: list[dict[str, Any]]) -> None:
    path.write_text("\n".join(json.dumps(item, ensure_ascii=False) for item in values) + ("\n" if values else ""), encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="anime-neural-trainer", description="Prepare neural domain training jobs with RTX 3050 safety gates.")
    parser.add_argument("--config", default="config/local_6gb.json")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("prepare", "prepare-all"):
        command = subparsers.add_parser(name)
        command.add_argument("--character-id", required=True)
        command.add_argument("--video-id", required=True)
        if name == "prepare":
            command.add_argument("--domain", required=True, choices=tuple(NEURAL_PROVIDERS))
        command.add_argument("--pretrained-model", default="")
        command.add_argument("--trainer-root", default="")
        command.add_argument("--source-video", default="")
        command.add_argument("--allow-unsegmented-background", action="store_true")
    register = subparsers.add_parser("register")
    register.add_argument("--character-id", required=True)
    register.add_argument("--video-id", required=True)
    register.add_argument("--domain", required=True, choices=tuple(NEURAL_PROVIDERS))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = load_settings(args.config)
    if args.command == "register":
        path = mark_neural_job_trained(settings, args.character_id, args.video_id, args.domain)
        print(f"Registered neural model: {path}")
        return 0
    kwargs = {
        "pretrained_model": args.pretrained_model,
        "trainer_root": args.trainer_root,
        "source_video": args.source_video,
        "allow_unsegmented_background": args.allow_unsegmented_background,
    }
    if args.command == "prepare":
        result = prepare_neural_training_job(settings, args.character_id, args.video_id, args.domain, **kwargs)
        print(f"Neural training job: {result.manifest_path}")
        print(f"Ready: {result.ready}")
        return 0 if result.ready else 1
    result = prepare_all_neural_training_jobs(settings, args.character_id, args.video_id, **kwargs)
    print(f"Neural training bundle: {result.manifest_path}")
    print(f"Ready: {sum(1 for item in result.results if item.ready)}/{len(result.results)}")
    return 0 if all(item.ready for item in result.results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
