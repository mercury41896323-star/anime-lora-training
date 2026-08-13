from __future__ import annotations

from dataclasses import asdict, dataclass
import argparse
import json
from pathlib import Path
from typing import Any

from .lora_registry import utc_timestamp
from .settings import AppSettings
from .storyboard import Shot, get_storyboard_path, load_storyboard
from .storyboard_production import (
    CameraWork,
    LightingSetup,
    build_production_prompt,
    load_camera_work_map,
    load_lighting_setup_map,
)
from .storyboard_results import ShotResult, list_shot_results


DEFAULT_DRAFT_WIDTH = 512
DEFAULT_DRAFT_HEIGHT = 512
DEFAULT_DRAFT_STEPS = 20
LOW_VRAM_MAX_PIXELS = 640 * 640
LOW_VRAM_MAX_STEPS = 24


@dataclass(frozen=True)
class ShotSuggestion:
    shot_id: str
    order: int
    title: str
    readiness_score: int
    risk_level: str
    missing: list[str]
    quality_flags: list[str]
    prompt: str
    prompt_additions: list[str]
    recommended_generation: dict[str, int | None]
    selected_result_id: str = ""
    suggestions: list[str] | None = None


@dataclass(frozen=True)
class ShotSuggestionReport:
    manifest_path: Path
    shot_count: int
    ready_count: int
    needs_attention_count: int
    blocked_count: int


def build_shot_suggestion_report(
    settings: AppSettings,
    story_id: str,
    output_path: str | Path | None = None,
) -> ShotSuggestionReport:
    storyboard = load_storyboard(settings, story_id)
    camera_by_shot = load_camera_work_map(settings, story_id)
    lighting_by_shot = load_lighting_setup_map(settings, story_id)
    results_by_shot = group_results_by_shot(list_shot_results(settings, story_id))
    suggestions = [
        suggest_shot(
            shot=shot,
            camera=camera_by_shot.get(shot.shot_id),
            lighting=lighting_by_shot.get(shot.shot_id),
            results=results_by_shot.get(shot.shot_id, []),
        )
        for shot in sorted(storyboard.shots, key=lambda item: item.order)
    ]
    ready_count = sum(1 for item in suggestions if item.risk_level == "ready")
    needs_attention_count = sum(1 for item in suggestions if item.risk_level == "needs_attention")
    blocked_count = sum(1 for item in suggestions if item.risk_level == "blocked")
    manifest_path = normalize_suggestion_report_path(settings, story_id, output_path)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "manifest_type": "storyboard_shot_suggestions",
                "generated_at": utc_timestamp(),
                "story": {
                    "story_id": storyboard.story_id,
                    "title": storyboard.title,
                },
                "policy": {
                    "profile": "RTX 3050 6GB low VRAM draft",
                    "default_width": DEFAULT_DRAFT_WIDTH,
                    "default_height": DEFAULT_DRAFT_HEIGHT,
                    "default_steps": DEFAULT_DRAFT_STEPS,
                    "max_pixels_before_warning": LOW_VRAM_MAX_PIXELS,
                    "max_steps_before_warning": LOW_VRAM_MAX_STEPS,
                },
                "summary": {
                    "shot_count": len(suggestions),
                    "ready_count": ready_count,
                    "needs_attention_count": needs_attention_count,
                    "blocked_count": blocked_count,
                },
                "shots": [asdict(item) for item in suggestions],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return ShotSuggestionReport(
        manifest_path=manifest_path,
        shot_count=len(suggestions),
        ready_count=ready_count,
        needs_attention_count=needs_attention_count,
        blocked_count=blocked_count,
    )


def suggest_shot(
    shot: Shot,
    camera: CameraWork | None = None,
    lighting: LightingSetup | None = None,
    results: list[ShotResult] | None = None,
) -> ShotSuggestion:
    related_results = results or []
    selected_result = next((result for result in related_results if result.decision == "selected"), None)
    missing = collect_missing_items(shot, camera, lighting)
    quality_flags = collect_quality_flags(shot, selected_result)
    score = readiness_score(missing, quality_flags)
    risk_level = classify_risk_level(shot, score)
    additions = prompt_additions(camera, lighting)
    return ShotSuggestion(
        shot_id=shot.shot_id,
        order=shot.order,
        title=shot.title,
        readiness_score=score,
        risk_level=risk_level,
        missing=missing,
        quality_flags=quality_flags,
        prompt=build_production_prompt(shot, camera, lighting),
        prompt_additions=additions,
        recommended_generation=recommended_generation(shot),
        selected_result_id=selected_result.result_id if selected_result else "",
        suggestions=build_action_suggestions(
            shot=shot,
            missing=missing,
            quality_flags=quality_flags,
            prompt_additions=additions,
        ),
    )


def collect_missing_items(
    shot: Shot,
    camera: CameraWork | None,
    lighting: LightingSetup | None,
) -> list[str]:
    missing: list[str] = []
    if not shot.character_id:
        missing.append("character_id")
    if not shot.prompt.strip():
        missing.append("prompt")
    if not has_camera_context(shot, camera):
        missing.append("camera_work")
    if not has_lighting_context(shot, lighting):
        missing.append("lighting_setup")
    return missing


def collect_quality_flags(shot: Shot, selected_result: ShotResult | None) -> list[str]:
    flags: list[str] = []
    width = shot.width or DEFAULT_DRAFT_WIDTH
    height = shot.height or DEFAULT_DRAFT_HEIGHT
    steps = shot.steps or DEFAULT_DRAFT_STEPS
    if width * height > LOW_VRAM_MAX_PIXELS:
        flags.append("large_resolution_for_6gb")
    if steps > LOW_VRAM_MAX_STEPS:
        flags.append("high_steps_for_6gb")
    if steps < 12:
        flags.append("low_steps")
    if not shot.negative_prompt.strip():
        flags.append("missing_negative_prompt")
    if shot.seed is None:
        flags.append("missing_seed")
    if selected_result is None:
        flags.append("missing_selected_result")
    if shot.duration_seconds < 1.0:
        flags.append("very_short_duration")
    if shot.duration_seconds > 8.0:
        flags.append("long_duration")
    return flags


def readiness_score(missing: list[str], quality_flags: list[str]) -> int:
    score = 100
    penalties = {
        "character_id": 35,
        "prompt": 20,
        "camera_work": 10,
        "lighting_setup": 10,
        "large_resolution_for_6gb": 18,
        "high_steps_for_6gb": 12,
        "low_steps": 8,
        "missing_negative_prompt": 5,
        "missing_seed": 5,
        "missing_selected_result": 8,
        "very_short_duration": 5,
        "long_duration": 5,
    }
    for item in [*missing, *quality_flags]:
        score -= penalties.get(item, 0)
    return max(0, min(100, score))


def classify_risk_level(shot: Shot, score: int) -> str:
    if not shot.character_id:
        return "blocked"
    if score >= 80:
        return "ready"
    return "needs_attention"


def prompt_additions(camera: CameraWork | None, lighting: LightingSetup | None) -> list[str]:
    additions: list[str] = []
    if camera is not None:
        additions.extend(
            item
            for item in [
                camera.framing,
                camera.movement,
                f"{camera.lens_mm}mm lens" if camera.lens_mm else "",
                camera.angle,
                camera.focus,
            ]
            if item
        )
    if lighting is not None:
        additions.extend(
            item
            for item in [
                lighting.key_light,
                lighting.fill_light,
                lighting.rim_light,
                lighting.mood,
                lighting.time_of_day,
                lighting.color_palette,
            ]
            if item
        )
    return unique_strings(additions)


def recommended_generation(shot: Shot) -> dict[str, int | None]:
    return {
        "seed": shot.seed,
        "width": shot.width or DEFAULT_DRAFT_WIDTH,
        "height": shot.height or DEFAULT_DRAFT_HEIGHT,
        "steps": shot.steps or DEFAULT_DRAFT_STEPS,
        "batch_size": 1,
    }


def build_action_suggestions(
    shot: Shot,
    missing: list[str],
    quality_flags: list[str],
    prompt_additions: list[str],
) -> list[str]:
    actions: list[str] = []
    if "character_id" in missing:
        actions.append("Set character_id before LoRA-based draft generation.")
    if "prompt" in missing:
        actions.append("Add a concise positive prompt; the shot title is only a fallback.")
    if "camera_work" in missing:
        actions.append("Add framing or movement notes for clearer shot direction.")
    if "lighting_setup" in missing:
        actions.append("Add mood, key light, or time-of-day notes for visual consistency.")
    if "large_resolution_for_6gb" in quality_flags:
        actions.append("Use 512x512 or 640x384 drafts first on 6GB VRAM.")
    if "high_steps_for_6gb" in quality_flags:
        actions.append("Keep draft steps near 20-24 for faster low-VRAM iteration.")
    if "low_steps" in quality_flags:
        actions.append("Raise steps to at least 12 for a more readable draft.")
    if "missing_negative_prompt" in quality_flags:
        actions.append("Add a small negative prompt such as blurry, low quality, bad anatomy.")
    if "missing_seed" in quality_flags:
        actions.append("Set a seed when comparing iterations for the same shot.")
    if "missing_selected_result" in quality_flags:
        actions.append("Generate or select a result before exporting the final edit manifest.")
    if prompt_additions:
        actions.append("Review prompt_additions and merge useful camera/lighting terms into the prompt.")
    if not actions:
        actions.append("Shot is ready for the next draft batch.")
    return actions


def has_camera_context(shot: Shot, camera: CameraWork | None) -> bool:
    if shot.camera.strip():
        return True
    if camera is None:
        return False
    return any([camera.framing, camera.movement, camera.lens_mm, camera.angle, camera.focus])


def has_lighting_context(shot: Shot, lighting: LightingSetup | None) -> bool:
    if shot.lighting.strip():
        return True
    if lighting is None:
        return False
    return any(
        [
            lighting.key_light,
            lighting.fill_light,
            lighting.rim_light,
            lighting.mood,
            lighting.time_of_day,
            lighting.color_palette,
        ]
    )


def group_results_by_shot(results: list[ShotResult]) -> dict[str, list[ShotResult]]:
    grouped: dict[str, list[ShotResult]] = {}
    for result in results:
        grouped.setdefault(result.shot_id, []).append(result)
    return grouped


def normalize_suggestion_report_path(
    settings: AppSettings,
    story_id: str,
    output_path: str | Path | None,
) -> Path:
    if output_path is None:
        return get_storyboard_path(settings, story_id).parent / "shot_suggestions.json"
    path = Path(output_path)
    if not path.is_absolute():
        path = settings.project_root / path
    return path


def unique_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        normalized = value.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        unique.append(normalized)
    return unique


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="anime-storyboard-suggestions",
        description="Write lightweight Phase 5 shot suggestions for a storyboard.",
    )
    parser.add_argument(
        "--config",
        default="config/local_6gb.json",
        help="Path to the local runtime profile.",
    )
    parser.add_argument("--story-id", required=True, help="Storyboard id.")
    parser.add_argument("--output", default=None, help="Suggestion report output path.")
    return parser


def main(argv: list[str] | None = None) -> int:
    from .settings import load_settings

    parser = build_parser()
    args = parser.parse_args(argv)
    settings = load_settings(args.config)
    result = build_shot_suggestion_report(
        settings=settings,
        story_id=args.story_id,
        output_path=args.output,
    )
    print(f"Wrote shot suggestions: {result.manifest_path}")
    print(f"Shots: {result.shot_count}")
    print(f"Ready: {result.ready_count}")
    print(f"Needs attention: {result.needs_attention_count}")
    print(f"Blocked: {result.blocked_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
