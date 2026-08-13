from __future__ import annotations

from dataclasses import dataclass
import csv
from pathlib import Path
from typing import Sequence


DEFAULT_WD14_REPO_ID = "SmilingWolf/wd-swinv2-tagger-v3"
MODEL_FILENAME = "model.onnx"
LABEL_FILENAME = "selected_tags.csv"


@dataclass(frozen=True)
class WD14Config:
    repo_id: str = DEFAULT_WD14_REPO_ID
    model_filename: str = MODEL_FILENAME
    label_filename: str = LABEL_FILENAME
    general_threshold: float = 0.35
    character_threshold: float = 0.35


def generate_wd14_tags(
    image_path: Path,
    model_dir: Path,
    config: WD14Config = WD14Config(),
) -> list[str]:
    try:
        import numpy as np
        import onnxruntime as ort
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError(
            "WD14 tagging requires optional dependencies: "
            "onnxruntime, pillow, numpy, and huggingface_hub for model download."
        ) from exc

    model_path, label_path = ensure_model_files(model_dir, config)
    tags = load_selected_tags(label_path)
    image = prepare_image(image_path, np)

    session = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
    input_name = session.get_inputs()[0].name
    probabilities = session.run(None, {input_name: image})[0][0]

    selected: list[str] = []
    for tag, probability in zip(tags, probabilities):
        threshold = (
            config.character_threshold
            if tag.category == "character"
            else config.general_threshold
        )
        if probability >= threshold and tag.category in {"general", "character"}:
            selected.append(tag.name)
    return selected


def ensure_model_files(model_dir: Path, config: WD14Config) -> tuple[Path, Path]:
    model_dir.mkdir(parents=True, exist_ok=True)
    model_path = model_dir / config.model_filename
    label_path = model_dir / config.label_filename
    if model_path.exists() and label_path.exists():
        return model_path, label_path

    try:
        from huggingface_hub import hf_hub_download
    except ImportError as exc:
        raise RuntimeError(
            "WD14 model files are missing and huggingface_hub is not installed."
        ) from exc

    downloaded_model = hf_hub_download(
        repo_id=config.repo_id,
        filename=config.model_filename,
        local_dir=model_dir,
    )
    downloaded_labels = hf_hub_download(
        repo_id=config.repo_id,
        filename=config.label_filename,
        local_dir=model_dir,
    )
    return Path(downloaded_model), Path(downloaded_labels)


@dataclass(frozen=True)
class WD14Tag:
    name: str
    category: str


def load_selected_tags(label_path: Path) -> list[WD14Tag]:
    category_names = {
        "0": "general",
        "4": "character",
        "general": "general",
        "character": "character",
    }
    tags: list[WD14Tag] = []
    with label_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            name = (row.get("name") or row.get("tag") or "").replace("_", " ").strip()
            category = category_names.get((row.get("category") or "").strip(), "other")
            if name:
                tags.append(WD14Tag(name=name, category=category))
    return tags


def prepare_image(image_path: Path, np_module) -> object:
    from PIL import Image

    image = Image.open(image_path).convert("RGB")
    size = 448
    image.thumbnail((size, size))
    canvas = Image.new("RGB", (size, size), (255, 255, 255))
    left = (size - image.width) // 2
    top = (size - image.height) // 2
    canvas.paste(image, (left, top))
    array = np_module.asarray(canvas, dtype=np_module.float32)
    array = array[:, :, ::-1]
    return np_module.expand_dims(array, axis=0)


def available_wd14_providers() -> Sequence[str]:
    return ("wd14", "baseline")
