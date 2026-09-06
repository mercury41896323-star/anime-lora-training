from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
from typing import Any
import zlib

from PIL import Image, ImageOps

from .character_profile import character_profile_path, validate_character_id
from .comfyui_queue import DEFAULT_COMFYUI_BASE_URL, enqueue_comfyui_workflow
from .lora_registry import project_relative_path, utc_timestamp
from .settings import AppSettings, BerniniLowVramSettings
from .storyboard import Shot, load_storyboard
from .storyboard_production import (
    build_production_prompt,
    load_camera_work_map,
    load_lighting_setup_map,
)


DEFAULT_NEGATIVE_PROMPT = (
    "blurry, low quality, distorted, deformed, flicker, identity drift, "
    "inconsistent face, inconsistent outfit, watermark, text"
)


@dataclass(frozen=True)
class BerniniSegment:
    index: int
    start_seconds: float
    requested_duration_seconds: float
    generated_duration_seconds: float
    frame_count: int
    seed: int
    workflow_path: str
    output_prefix: str
    queued_job_id: str = ""


@dataclass(frozen=True)
class BerniniExportResult:
    manifest_path: Path
    export_dir: Path
    reference_source: Path
    comfyui_reference: Path
    requested_duration_seconds: float
    segments: list[BerniniSegment]


@dataclass(frozen=True)
class BerniniAssemblyResult:
    manifest_path: Path
    concat_path: Path
    output_path: Path
    requested_duration_seconds: float
    input_videos: list[Path]
    command: list[str]


def export_bernini_low_vram_shot(
    settings: AppSettings,
    story_id: str,
    shot_id: str,
    duration_seconds: float | None = None,
    max_duration_seconds: float | None = None,
    reference_image: str | Path | None = None,
    comfyui_input_dir: str | Path | None = None,
    output_dir: str | Path | None = None,
    enqueue: bool = False,
    base_url: str = DEFAULT_COMFYUI_BASE_URL,
    queue_path: str | Path | None = None,
) -> BerniniExportResult:
    profile = settings.bernini_low_vram
    validate_low_vram_profile(settings, profile)
    storyboard = load_storyboard(settings, story_id)
    shot = next((item for item in storyboard.shots if item.shot_id == shot_id), None)
    if shot is None:
        raise ValueError(f"Storyboard shot not found: {shot_id}")
    if not shot.character_id:
        raise ValueError(f"Shot character_id is required: {shot_id}")
    validate_character_id(shot.character_id)

    requested_duration = float(duration_seconds if duration_seconds is not None else shot.duration_seconds)
    hard_limit = profile.max_duration_seconds
    selected_limit = hard_limit if max_duration_seconds is None else float(max_duration_seconds)
    if selected_limit <= 0 or selected_limit > hard_limit:
        raise ValueError(f"max_duration_seconds must be greater than 0 and no more than {hard_limit}.")
    if requested_duration <= 0:
        raise ValueError("duration_seconds must be greater than 0.")
    if requested_duration > selected_limit:
        raise ValueError(
            f"Requested duration {requested_duration:g}s exceeds the low-VRAM limit {selected_limit:g}s."
        )

    resolved_output_dir = normalize_output_dir(settings, story_id, shot_id, output_dir)
    resolved_output_dir.mkdir(parents=True, exist_ok=True)
    source_reference = resolve_identity_reference(settings, shot.character_id, reference_image)
    prepared_reference = prepare_reference_image(source_reference, resolved_output_dir / "reference.png")
    resolved_input_dir = resolve_comfyui_input_dir(comfyui_input_dir)
    comfyui_reference = copy_reference_to_comfyui_input(
        prepared_reference,
        resolved_input_dir,
        shot.character_id,
        story_id,
        shot_id,
    )
    comfyui_reference_name = comfyui_reference.relative_to(resolved_input_dir).as_posix()

    camera = load_camera_work_map(settings, story_id).get(shot_id)
    lighting = load_lighting_setup_map(settings, story_id).get(shot_id)
    prompt = build_bernini_prompt(shot, camera, lighting)
    negative_prompt = merge_prompt_parts(DEFAULT_NEGATIVE_PROMPT, shot.negative_prompt)
    segment_specs = build_segment_specs(requested_duration, profile)
    segments: list[BerniniSegment] = []
    for spec in segment_specs:
        output_prefix = (
            f"anime_studio/bernini/{story_id}/{shot.order:03d}_{shot_id}/"
            f"segment_{spec['index']:03d}"
        )
        workflow = build_bernini_r2v_workflow(
            profile=profile,
            reference_image=comfyui_reference_name,
            prompt=prompt,
            negative_prompt=negative_prompt,
            frame_count=int(spec["frame_count"]),
            seed=stable_segment_seed(story_id, shot_id, int(spec["index"])),
            output_prefix=output_prefix,
        )
        workflow["meta"] = {
            "provider": "bernini_r_1p3b_low_vram",
            "story_id": story_id,
            "shot_id": shot_id,
            "character_id": shot.character_id,
            "segment_index": spec["index"],
            "requested_duration_seconds": spec["requested_duration_seconds"],
            "generated_duration_seconds": spec["generated_duration_seconds"],
            "trim_final_video_to_seconds": requested_duration,
            "reference_source": project_relative_path(settings, source_reference),
            "comfyui_reference": comfyui_reference_name,
            "low_vram": True,
        }
        workflow_path = resolved_output_dir / f"segment_{spec['index']:03d}.json"
        workflow_path.write_text(
            json.dumps(workflow, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        queued_job_id = ""
        if enqueue:
            queued = enqueue_comfyui_workflow(
                settings=settings,
                workflow_path=workflow_path,
                base_url=base_url,
                queue_path=queue_path,
            )
            queued_job_id = str(queued.job["job_id"])
        segments.append(
            BerniniSegment(
                index=int(spec["index"]),
                start_seconds=float(spec["start_seconds"]),
                requested_duration_seconds=float(spec["requested_duration_seconds"]),
                generated_duration_seconds=float(spec["generated_duration_seconds"]),
                frame_count=int(spec["frame_count"]),
                seed=stable_segment_seed(story_id, shot_id, int(spec["index"])),
                workflow_path=project_relative_path(settings, workflow_path),
                output_prefix=output_prefix,
                queued_job_id=queued_job_id,
            )
        )

    manifest_path = resolved_output_dir / "bernini_low_vram_plan.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "manifest_type": "bernini_low_vram_generation_plan",
                "created_at": utc_timestamp(),
                "provider": "bernini_r_1p3b_low_vram",
                "story_id": story_id,
                "shot_id": shot_id,
                "character_id": shot.character_id,
                "requested_duration_seconds": requested_duration,
                "maximum_duration_seconds": selected_limit,
                "segment_count": len(segments),
                "reference": {
                    "source": project_relative_path(settings, source_reference),
                    "prepared": project_relative_path(settings, prepared_reference),
                    "comfyui_input": comfyui_reference_name,
                },
                "runtime_limits": {
                    "max_vram_gb": profile.max_vram_gb,
                    "max_ram_gb": profile.max_ram_gb,
                    "width": profile.width,
                    "height": profile.height,
                    "fps": profile.fps,
                    "steps": profile.steps,
                    "segment_duration_seconds": profile.segment_duration_seconds,
                    "vae_tile_size": profile.vae_tile_size,
                    "vae_temporal_size": profile.vae_temporal_size,
                    "batch_size": 1,
                },
                "model_files": {
                    "renderer": profile.renderer_model,
                    "text_encoder": profile.text_encoder,
                    "vae": profile.vae,
                },
                "generation_strategy": [
                    "Use the approved Character Master / 2.5D identity image as Bernini reference.",
                    "Generate short segments sequentially so model weights and VAE do not stay resident together.",
                    "Decode with spatial and temporal VAE tiling on CPU.",
                    "Concatenate segments and trim to requested_duration_seconds after generation.",
                    "Run frame interpolation, upscale, and face repair as separate post-processing jobs.",
                ],
                "quality_notes": [
                    "The existing SD1.5 LoRA is used to prepare approved reference frames; it is not loaded into Bernini-R.",
                    "Independent segments can drift at boundaries and require review before adoption.",
                ],
                "segments": [asdict(item) for item in segments],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return BerniniExportResult(
        manifest_path=manifest_path,
        export_dir=resolved_output_dir,
        reference_source=source_reference,
        comfyui_reference=comfyui_reference,
        requested_duration_seconds=requested_duration,
        segments=segments,
    )


def assemble_bernini_segments(
    settings: AppSettings,
    plan_path: str | Path,
    output_path: str | Path | None = None,
    ffmpeg_path: str = "ffmpeg",
) -> BerniniAssemblyResult:
    resolved_plan = normalize_project_path(settings, plan_path)
    if not resolved_plan.is_file():
        raise FileNotFoundError(f"Bernini generation plan not found: {resolved_plan}")
    plan = json.loads(resolved_plan.read_text(encoding="utf-8-sig"))
    if plan.get("manifest_type") != "bernini_low_vram_generation_plan":
        raise ValueError(f"Not a Bernini low-VRAM generation plan: {resolved_plan}")

    character_id = str(plan.get("character_id", ""))
    requested_duration = float(plan.get("requested_duration_seconds", 0))
    segments = list(plan.get("segments", []))
    if not character_id or requested_duration <= 0 or not segments:
        raise ValueError("Bernini plan is missing character, duration, or segment data.")

    input_videos = [
        resolve_imported_segment_video(settings, character_id, dict(segment))
        for segment in sorted(segments, key=lambda item: int(item.get("index", 0)))
    ]
    concat_path = resolved_plan.parent / "bernini_segments.ffconcat"
    concat_path.write_text(
        "ffconcat version 1.0\n"
        + "".join(f"file '{escape_ffconcat_path(path)}'\n" for path in input_videos),
        encoding="utf-8",
    )
    resolved_output = (
        resolved_plan.parent / "final_trimmed.mp4"
        if output_path is None
        else normalize_project_path(settings, output_path)
    )
    resolved_output.parent.mkdir(parents=True, exist_ok=True)
    command = build_bernini_assembly_command(
        ffmpeg_path=ffmpeg_path,
        concat_path=concat_path,
        output_path=resolved_output,
        duration_seconds=requested_duration,
    )
    if shutil.which(ffmpeg_path) is None and not Path(ffmpeg_path).is_file():
        raise FileNotFoundError(f"FFmpeg executable not found: {ffmpeg_path}")
    creation_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        creationflags=creation_flags,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "unknown FFmpeg error"
        raise RuntimeError(f"Bernini segment assembly failed: {detail}")

    manifest_path = resolved_plan.parent / "bernini_assembly.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "manifest_type": "bernini_low_vram_assembly",
                "created_at": utc_timestamp(),
                "source_plan": project_relative_path(settings, resolved_plan),
                "requested_duration_seconds": requested_duration,
                "input_videos": [project_relative_path(settings, path) for path in input_videos],
                "concat_file": project_relative_path(settings, concat_path),
                "output_video": project_relative_path(settings, resolved_output),
                "processor": "ffmpeg_cpu",
                "command": command,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return BerniniAssemblyResult(
        manifest_path=manifest_path,
        concat_path=concat_path,
        output_path=resolved_output,
        requested_duration_seconds=requested_duration,
        input_videos=input_videos,
        command=command,
    )


def resolve_imported_segment_video(
    settings: AppSettings,
    character_id: str,
    segment: dict[str, Any],
) -> Path:
    job_ids = [str(segment.get("queued_job_id", ""))]
    workflow_path = str(segment.get("workflow_path", ""))
    queue_path = settings.project_root / "queues" / "comfyui" / "jobs.json"
    if queue_path.is_file() and workflow_path:
        queue = json.loads(queue_path.read_text(encoding="utf-8-sig"))
        job_ids.extend(
            str(job.get("job_id", ""))
            for job in reversed(list(queue.get("jobs", [])))
            if str(job.get("workflow_path", "")) == workflow_path
        )
    for job_id in dict.fromkeys(value for value in job_ids if value):
        result_path = (
            settings.assets.processed
            / "characters"
            / character_id
            / "generated"
            / "comfyui"
            / job_id
            / "results.json"
        )
        if not result_path.is_file():
            continue
        result = json.loads(result_path.read_text(encoding="utf-8-sig"))
        for item in result.get("results", []):
            if str(item.get("kind", "")) != "video":
                continue
            candidate = normalize_project_path(settings, str(item.get("stored_path", "")))
            if candidate.is_file():
                return candidate
    raise FileNotFoundError(
        f"Imported Bernini video is missing for segment {segment.get('index')}. "
        "Refresh and import each completed ComfyUI job before assembly."
    )


def build_bernini_assembly_command(
    ffmpeg_path: str,
    concat_path: Path,
    output_path: Path,
    duration_seconds: float,
) -> list[str]:
    return [
        ffmpeg_path,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_path),
        "-t",
        f"{duration_seconds:g}",
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        str(output_path),
    ]


def escape_ffconcat_path(path: Path) -> str:
    return str(path.resolve()).replace("\\", "/").replace("'", "'\\''")


def validate_low_vram_profile(settings: AppSettings, profile: BerniniLowVramSettings) -> None:
    if not profile.enabled:
        raise ValueError("Bernini low-VRAM generation is disabled in the active config.")
    if profile.max_vram_gb > settings.runtime.max_vram_gb:
        raise ValueError("Bernini max_vram_gb exceeds the active runtime VRAM limit.")
    if profile.width % 16 or profile.height % 16:
        raise ValueError("Bernini width and height must be multiples of 16.")
    if profile.width > 512 or profile.height > 512:
        raise ValueError("The safe 6GB profile limits each dimension to 512 pixels.")
    if profile.fps <= 0 or profile.steps <= 0 or profile.segment_duration_seconds <= 0:
        raise ValueError("Bernini fps, steps, and segment duration must be positive.")


def build_segment_specs(
    requested_duration_seconds: float,
    profile: BerniniLowVramSettings,
) -> list[dict[str, float | int]]:
    segment_count = max(1, math.ceil(requested_duration_seconds / profile.segment_duration_seconds))
    segment_duration = requested_duration_seconds / segment_count
    specs: list[dict[str, float | int]] = []
    for index in range(1, segment_count + 1):
        frame_count = compatible_frame_count(segment_duration, profile.fps)
        specs.append(
            {
                "index": index,
                "start_seconds": round((index - 1) * segment_duration, 6),
                "requested_duration_seconds": round(segment_duration, 6),
                "generated_duration_seconds": round(frame_count / profile.fps, 6),
                "frame_count": frame_count,
            }
        )
    return specs


def compatible_frame_count(duration_seconds: float, fps: int) -> int:
    target = max(1, math.ceil(duration_seconds * fps))
    return max(5, 1 + 4 * math.ceil(max(0, target - 1) / 4))


def build_bernini_r2v_workflow(
    profile: BerniniLowVramSettings,
    reference_image: str,
    prompt: str,
    negative_prompt: str,
    frame_count: int,
    seed: int,
    output_prefix: str,
) -> dict[str, Any]:
    return {
        "1": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": profile.renderer_model}},
        "2": {"class_type": "BerniniRApplyPatches", "inputs": {"model": ["1", 0]}},
        "3": {
            "class_type": "CLIPLoaderGGUF",
            "inputs": {"clip_name": profile.text_encoder, "type": "wan"},
        },
        "4": {"class_type": "VAELoader", "inputs": {"vae_name": profile.vae}},
        "5": {"class_type": "LoadImage", "inputs": {"image": reference_image}},
        "6": {
            "class_type": "VAEEncodeTiled",
            "inputs": {
                "pixels": ["5", 0],
                "vae": ["4", 0],
                "tile_size": profile.vae_tile_size,
                "overlap": 32,
                "temporal_size": profile.vae_temporal_size,
                "temporal_overlap": 4,
            },
        },
        "7": {
            "class_type": "BerniniRSourceStream",
            "inputs": {"model": ["2", 0], "source_latent": ["6", 0], "source_id": 1},
        },
        "8": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["3", 0], "text": prompt}},
        "9": {
            "class_type": "CLIPTextEncode",
            "inputs": {"clip": ["3", 0], "text": negative_prompt},
        },
        "10": {
            "class_type": "EmptyHunyuanLatentVideo",
            "inputs": {
                "width": profile.width,
                "height": profile.height,
                "length": frame_count,
                "batch_size": 1,
            },
        },
        "11": {
            "class_type": "BerniniRGuider",
            "inputs": {
                "model": ["7", 0],
                "positive": ["8", 0],
                "negative": ["9", 0],
                "mode": "auto",
                "omega_V": 1.25,
                "omega_I": 4.5,
                "omega_TI": 4.0,
                "eta": 0.5,
                "momentum": 0.0,
                "norm_threshold": 50.0,
                "omega_scale": 0.8,
                "boundary": 0.875,
            },
        },
        "12": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
        "13": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
        "14": {
            "class_type": "BasicScheduler",
            "inputs": {
                "model": ["7", 0],
                "scheduler": "simple",
                "steps": profile.steps,
                "denoise": 1.0,
            },
        },
        "15": {
            "class_type": "SamplerCustomAdvanced",
            "inputs": {
                "noise": ["12", 0],
                "guider": ["11", 0],
                "sampler": ["13", 0],
                "sigmas": ["14", 0],
                "latent_image": ["10", 0],
            },
        },
        "16": {
            "class_type": "VAEDecodeTiled",
            "inputs": {
                "samples": ["15", 0],
                "vae": ["4", 0],
                "tile_size": profile.vae_tile_size,
                "overlap": 32,
                "temporal_size": profile.vae_temporal_size,
                "temporal_overlap": 4,
            },
        },
        "17": {
            "class_type": "BerniniRSaveVideo",
            "inputs": {
                "images": ["16", 0],
                "format": "mp4",
                "fps": float(profile.fps),
                "filename_prefix": output_prefix,
            },
        },
    }


def build_bernini_prompt(shot: Shot, camera: Any = None, lighting: Any = None) -> str:
    production = build_production_prompt(shot, camera, lighting)
    return merge_prompt_parts(
        "animate the reference character while preserving the exact face, hairstyle, outfit, and color design",
        production,
        "stable character identity across every frame, coherent anime motion",
    )


def merge_prompt_parts(*parts: str) -> str:
    merged: list[str] = []
    for part in parts:
        value = str(part).strip().strip(",")
        if value and value not in merged:
            merged.append(value)
    return ", ".join(merged)


def resolve_identity_reference(
    settings: AppSettings,
    character_id: str,
    reference_image: str | Path | None,
) -> Path:
    if reference_image is not None:
        path = normalize_project_path(settings, reference_image)
        if not path.is_file():
            raise FileNotFoundError(f"Bernini reference image not found: {path}")
        return path

    definition_path = (
        settings.project_root / "manifests" / "characters" / character_id / "character_2p5d_definition.json"
    )
    candidates: list[str] = []
    if definition_path.is_file():
        definition = json.loads(definition_path.read_text(encoding="utf-8-sig"))
        binding = dict(definition.get("generation_binding", {}))
        video_control = dict(binding.get("video_control", {}))
        candidates.extend(str(value) for value in video_control.get("identity_anchor_images", []))
        candidates.extend(str(value) for value in definition.get("identity_reference_images", []))

    master_path = (
        settings.project_root
        / "manifests"
        / "characters"
        / character_id
        / "character_sheet"
        / "character_master_asset.json"
    )
    if master_path.is_file():
        master = json.loads(master_path.read_text(encoding="utf-8-sig"))
        paths = dict(master.get("paths", {}))
        candidates.extend(
            str(paths.get(key, ""))
            for key in ("definition_source_image", "master_image", "reviewed_image")
        )

    profile_path = character_profile_path(settings, character_id)
    if not profile_path.is_file():
        raise FileNotFoundError(f"Character profile does not exist: {profile_path}")

    existing = [normalize_project_path(settings, value) for value in candidates if value]
    existing = [path for path in existing if path.is_file()]
    if not existing:
        raise FileNotFoundError(
            f"No approved Character Master or 2.5D identity reference found for: {character_id}"
        )
    return sorted(existing, key=reference_priority)[0]


def reference_priority(path: Path) -> tuple[int, int, str]:
    name = path.stem.lower()
    priority = 0 if "main_portrait" in name else 1 if "face_angle_front" in name else 2
    return priority, path.stat().st_size, str(path)


def prepare_reference_image(source: Path, destination: Path, max_side: int = 512) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as opened:
        image = ImageOps.exif_transpose(opened).convert("RGB")
        image.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
        width = max(16, 16 * math.ceil(image.width / 16))
        height = max(16, 16 * math.ceil(image.height / 16))
        canvas = Image.new("RGB", (width, height), (255, 255, 255))
        canvas.paste(image, ((width - image.width) // 2, (height - image.height) // 2))
        canvas.save(destination, format="PNG")
    return destination


def resolve_comfyui_input_dir(value: str | Path | None) -> Path:
    candidates: list[Path] = []
    if value is not None:
        candidates.append(Path(value))
    env_path = os.environ.get("COMFYUI_INPUT_DIR", "")
    if env_path:
        candidates.append(Path(env_path))
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    if local_app_data:
        desktop = Path(local_app_data) / "Comfy-Desktop"
        candidates.extend(
            [
                desktop / "ComfyUI-Shared" / "input",
                desktop / "ComfyUI-Installs" / "ComfyUI" / "ComfyUI" / "input",
            ]
        )
    for candidate in candidates:
        if candidate.is_dir():
            return candidate.resolve()
    raise FileNotFoundError(
        "ComfyUI input directory was not found. Pass --comfyui-input-dir or set COMFYUI_INPUT_DIR."
    )


def copy_reference_to_comfyui_input(
    source: Path,
    input_dir: Path,
    character_id: str,
    story_id: str,
    shot_id: str,
) -> Path:
    destination = input_dir / "anime_studio" / "bernini" / character_id / story_id / shot_id / "reference.png"
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return destination


def stable_segment_seed(story_id: str, shot_id: str, index: int) -> int:
    return zlib.crc32(f"{story_id}:{shot_id}:bernini:{index}".encode("utf-8")) & 0xFFFFFFFF


def normalize_output_dir(
    settings: AppSettings,
    story_id: str,
    shot_id: str,
    output_dir: str | Path | None,
) -> Path:
    if output_dir is None:
        return settings.project_root / "outputs" / "comfyui" / "bernini" / story_id / shot_id
    return normalize_project_path(settings, output_dir)


def normalize_project_path(settings: AppSettings, path: str | Path) -> Path:
    resolved = Path(path)
    if not resolved.is_absolute():
        resolved = settings.project_root / resolved
    return resolved.resolve()
