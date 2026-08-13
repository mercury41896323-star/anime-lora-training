from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path

from .character_profile import load_character_profile, validate_character_id
from .dataset_builder import build_lora_dataset
from .settings import AppSettings


@dataclass(frozen=True)
class KohyaLowVramSettings:
    pretrained_model_name_or_path: str
    kohya_root: str = "."
    resolution: int = 512
    repeats: int = 10
    train_batch_size: int = 1
    network_dim: int = 16
    network_alpha: int = 8
    learning_rate: str = "1e-4"
    max_train_epochs: int = 10
    save_every_n_epochs: int = 1
    mixed_precision: str = "fp16"
    save_precision: str = "fp16"
    optimizer_type: str = "AdamW8bit"
    lr_scheduler: str = "constant"
    seed: int = 42


@dataclass(frozen=True)
class KohyaConfigResult:
    character_id: str
    config_dir: Path
    dataset_config: Path
    training_config: Path
    run_script: Path
    dataset_image_count: int
    command: list[str]


def generate_kohya_low_vram_config(
    settings: AppSettings,
    character_id: str,
    kohya_settings: KohyaLowVramSettings,
) -> KohyaConfigResult:
    validate_character_id(character_id)
    profile = load_character_profile(settings, character_id)
    dataset = build_lora_dataset(settings, character_id)

    config_dir = settings.project_root / "config" / "kohya" / character_id
    config_dir.mkdir(parents=True, exist_ok=True)

    output_dir = settings.project_root / "outputs" / "lora" / character_id
    logging_dir = settings.project_root / "outputs" / "logs" / character_id
    output_name = f"{character_id}_lora"

    dataset_config = config_dir / "dataset.toml"
    training_config = config_dir / "train_low_vram.toml"
    run_script = config_dir / "run_train.ps1"

    dataset_config.write_text(
        render_dataset_toml(
            image_dir=dataset.dataset_dir / "images",
            class_tokens=" ".join(profile.trigger_tags),
            repeats=kohya_settings.repeats,
            resolution=kohya_settings.resolution,
            batch_size=kohya_settings.train_batch_size,
        ),
        encoding="utf-8",
    )

    command = build_train_command(
        kohya_root=Path(kohya_settings.kohya_root),
        pretrained_model_name_or_path=kohya_settings.pretrained_model_name_or_path,
        dataset_config=dataset_config,
        output_dir=output_dir,
        logging_dir=logging_dir,
        output_name=output_name,
        kohya_settings=kohya_settings,
    )

    training_payload = {
        "character_id": character_id,
        "dataset_image_count": dataset.image_count,
        "dataset_config": str(dataset_config),
        "output_dir": str(output_dir),
        "logging_dir": str(logging_dir),
        "output_name": output_name,
        "sd_scripts_entrypoint": "train_network.py",
        "low_vram_settings": asdict(kohya_settings),
        "command": command,
    }
    training_config.write_text(
        render_training_toml(training_payload),
        encoding="utf-8",
    )
    run_script.write_text(render_powershell_script(command), encoding="utf-8")

    return KohyaConfigResult(
        character_id=character_id,
        config_dir=config_dir,
        dataset_config=dataset_config,
        training_config=training_config,
        run_script=run_script,
        dataset_image_count=dataset.image_count,
        command=command,
    )


def render_dataset_toml(
    image_dir: Path,
    class_tokens: str,
    repeats: int,
    resolution: int,
    batch_size: int,
) -> str:
    return "\n".join(
        [
            "[general]",
            "enable_bucket = true",
            "bucket_no_upscale = true",
            "shuffle_caption = true",
            "caption_extension = '.txt'",
            "keep_tokens = 1",
            "",
            "[[datasets]]",
            f"resolution = {resolution}",
            f"batch_size = {batch_size}",
            "",
            "  [[datasets.subsets]]",
            f"  image_dir = {toml_quote(str(image_dir))}",
            f"  class_tokens = {toml_quote(class_tokens)}",
            f"  num_repeats = {repeats}",
            "",
        ]
    )


def build_train_command(
    kohya_root: Path,
    pretrained_model_name_or_path: str,
    dataset_config: Path,
    output_dir: Path,
    logging_dir: Path,
    output_name: str,
    kohya_settings: KohyaLowVramSettings,
) -> list[str]:
    train_script = kohya_root / "train_network.py"
    return [
        "accelerate",
        "launch",
        "--num_cpu_threads_per_process",
        "1",
        str(train_script),
        "--pretrained_model_name_or_path",
        pretrained_model_name_or_path,
        "--dataset_config",
        str(dataset_config),
        "--output_dir",
        str(output_dir),
        "--logging_dir",
        str(logging_dir),
        "--output_name",
        output_name,
        "--save_model_as",
        "safetensors",
        "--save_precision",
        kohya_settings.save_precision,
        "--network_module",
        "networks.lora",
        "--network_dim",
        str(kohya_settings.network_dim),
        "--network_alpha",
        str(kohya_settings.network_alpha),
        "--learning_rate",
        kohya_settings.learning_rate,
        "--optimizer_type",
        kohya_settings.optimizer_type,
        "--lr_scheduler",
        kohya_settings.lr_scheduler,
        "--max_train_epochs",
        str(kohya_settings.max_train_epochs),
        "--save_every_n_epochs",
        str(kohya_settings.save_every_n_epochs),
        "--mixed_precision",
        kohya_settings.mixed_precision,
        "--train_batch_size",
        str(kohya_settings.train_batch_size),
        "--seed",
        str(kohya_settings.seed),
        "--cache_latents",
        "--gradient_checkpointing",
        "--sdpa",
    ]


def render_training_toml(payload: dict[str, object]) -> str:
    lines = ["[kohya]", "profile = 'low_vram_rtx3050_6gb'"]
    scalar_keys = [
        "character_id",
        "dataset_image_count",
        "dataset_config",
        "output_dir",
        "logging_dir",
        "output_name",
        "sd_scripts_entrypoint",
    ]
    for key in scalar_keys:
        value = payload[key]
        lines.append(f"{key} = {toml_value(value)}")

    lines.extend(["", "[low_vram_settings]"])
    for key, value in payload["low_vram_settings"].items():
        lines.append(f"{key} = {toml_value(value)}")

    lines.extend(["", "[command]", f"argv_json = {toml_quote(json.dumps(payload['command']))}", ""])
    return "\n".join(lines)


def render_powershell_script(command: list[str]) -> str:
    quoted = "& " + " ".join(powershell_quote(part) for part in command)
    return "\n".join(
        [
            "$ErrorActionPreference = \"Stop\"",
            "",
            "# Review train_low_vram.toml before running this script.",
            quoted,
            "",
        ]
    )


def toml_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return toml_quote(str(value))


def toml_quote(value: str) -> str:
    return "'" + value.replace("'", "\\'") + "'"


def powershell_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"
