from __future__ import annotations

import argparse
import json

from .settings import load_settings
from .storyboard import add_shot, create_storyboard, list_storyboard_shots
from .storyboard_results import (
    link_comfyui_results_to_storyboard,
    link_shot_result,
    list_shot_results,
)
from .storyboard_editor import write_storyboard_editor
from .storyboard_editor_manifest import export_selected_shot_manifest
from .storyboard_production import (
    build_draft_generation_plan,
    set_camera_work,
    set_lighting_setup,
)
from .storyboard_review import (
    set_shot_result_decision,
    write_storyboard_preview,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="anime-storyboard",
        description="Lightweight storyboard result management commands.",
    )
    parser.add_argument(
        "--config",
        default="config/local_6gb.json",
        help="Path to the local runtime profile.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser(
        "init",
        help="Create a storyboard JSON file.",
    )
    init.add_argument("--id", required=True, help="Stable story id.")
    init.add_argument("--title", required=True, help="Storyboard title.")

    add = subparsers.add_parser(
        "add-shot",
        help="Append a shot with optional generation settings.",
    )
    add.add_argument("--story-id", required=True, help="Storyboard id.")
    add.add_argument("--shot-id", required=True, help="Stable shot id.")
    add.add_argument("--title", required=True, help="Shot title.")
    add.add_argument("--character-id", default="", help="Optional character id.")
    add.add_argument("--prompt", default="", help="Draft generation prompt.")
    add.add_argument("--negative-prompt", default="", help="Shot-specific negative prompt.")
    add.add_argument("--duration", type=float, default=3.0, help="Shot duration in seconds.")
    add.add_argument("--camera", default="", help="Camera note.")
    add.add_argument("--lighting", default="", help="Lighting note.")
    add.add_argument("--seed", type=int, default=None, help="Optional fixed generation seed.")
    add.add_argument("--width", type=int, default=None, help="Optional generated image width.")
    add.add_argument("--height", type=int, default=None, help="Optional generated image height.")
    add.add_argument("--steps", type=int, default=None, help="Optional sampler steps.")
    add.add_argument("--notes", default="", help="Shot notes.")

    list_shots = subparsers.add_parser(
        "list",
        help="List shots in a storyboard.",
    )
    list_shots.add_argument("--story-id", required=True, help="Storyboard id.")
    list_shots.add_argument("--json", action="store_true", help="Print full JSON records.")

    camera = subparsers.add_parser(
        "camera",
        help="Set camera work notes for a storyboard shot.",
    )
    camera.add_argument("--story-id", required=True, help="Storyboard id.")
    camera.add_argument("--shot-id", required=True, help="Shot id.")
    camera.add_argument("--framing", default="", help="Framing note, such as close-up or wide shot.")
    camera.add_argument("--movement", default="", help="Camera movement note.")
    camera.add_argument("--lens-mm", type=int, default=None, help="Optional lens focal length.")
    camera.add_argument("--angle", default="", help="Camera angle note.")
    camera.add_argument("--focus", default="", help="Focus or depth-of-field note.")
    camera.add_argument("--notes", default="", help="Production notes.")

    lighting = subparsers.add_parser(
        "lighting",
        help="Set lighting notes for a storyboard shot.",
    )
    lighting.add_argument("--story-id", required=True, help="Storyboard id.")
    lighting.add_argument("--shot-id", required=True, help="Shot id.")
    lighting.add_argument("--key-light", default="", help="Key light note.")
    lighting.add_argument("--fill-light", default="", help="Fill light note.")
    lighting.add_argument("--rim-light", default="", help="Rim light note.")
    lighting.add_argument("--mood", default="", help="Mood note.")
    lighting.add_argument("--time-of-day", default="", help="Time-of-day note.")
    lighting.add_argument("--color-palette", default="", help="Color palette note.")
    lighting.add_argument("--notes", default="", help="Production notes.")

    link_result = subparsers.add_parser(
        "link-result",
        help="Link a generated asset to a storyboard shot.",
    )
    link_result.add_argument("--story-id", required=True, help="Storyboard id.")
    link_result.add_argument("--shot-id", required=True, help="Shot id.")
    link_result.add_argument("--result", required=True, help="Generated result path.")
    link_result.add_argument("--kind", default="image", help="Result kind.")
    link_result.add_argument("--source", default="manual", help="Result source.")
    link_result.add_argument(
        "--source-reference",
        default="",
        help="Original source reference, such as a ComfyUI output reference.",
    )

    link_comfyui = subparsers.add_parser(
        "link-comfyui-results",
        help="Link imported ComfyUI results using storyboard workflow metadata.",
    )
    link_comfyui.add_argument("--job-id", required=True, help="ComfyUI queue job id.")
    link_comfyui.add_argument(
        "--queue",
        default=None,
        help="Queue JSON path. Defaults to queues/comfyui/jobs.json.",
    )
    link_comfyui.add_argument(
        "--results-manifest",
        default=None,
        help="Imported ComfyUI results manifest.",
    )

    results = subparsers.add_parser(
        "results",
        help="List generated results linked to storyboard shots.",
    )
    results.add_argument("--story-id", required=True, help="Storyboard id.")
    results.add_argument("--shot-id", default=None, help="Optional shot id filter.")
    results.add_argument("--json", action="store_true", help="Print full JSON records.")

    decide = subparsers.add_parser(
        "decide-result",
        help="Mark a linked shot result as candidate, selected, or rejected.",
    )
    decide.add_argument("--story-id", required=True, help="Storyboard id.")
    decide.add_argument("--result-id", required=True, help="Shot result id.")
    decide.add_argument(
        "--decision",
        required=True,
        choices=["candidate", "selected", "rejected"],
        help="Decision state for the result.",
    )
    decide.add_argument("--notes", default="", help="Decision notes.")

    preview = subparsers.add_parser(
        "preview",
        help="Write a lightweight HTML preview for a storyboard.",
    )
    preview.add_argument("--story-id", required=True, help="Storyboard id.")
    preview.add_argument(
        "--output",
        default=None,
        help="Preview HTML output path. Defaults to storyboards/<story-id>/preview.html.",
    )

    export_selected = subparsers.add_parser(
        "export-selected",
        help="Export selected shot results for Unity and editing tools.",
    )
    export_selected.add_argument("--story-id", required=True, help="Storyboard id.")
    export_selected.add_argument(
        "--output",
        default=None,
        help="Manifest output path. Defaults to manifests/storyboards/<story-id>/selected_shots.json.",
    )

    draft_plan = subparsers.add_parser(
        "draft-plan",
        help="Write a low-VRAM draft generation plan for storyboard shots.",
    )
    draft_plan.add_argument("--story-id", required=True, help="Storyboard id.")
    draft_plan.add_argument("--output", default=None, help="Draft plan output path.")
    draft_plan.add_argument("--default-width", type=int, default=512, help="Default draft width.")
    draft_plan.add_argument("--default-height", type=int, default=512, help="Default draft height.")
    draft_plan.add_argument("--default-steps", type=int, default=20, help="Default sampler steps.")

    editor = subparsers.add_parser(
        "editor",
        help="Write a lightweight HTML ShotEditor for a storyboard.",
    )
    editor.add_argument("--story-id", required=True, help="Storyboard id.")
    editor.add_argument(
        "--output",
        default=None,
        help="Editor HTML output path. Defaults to storyboards/<story-id>/editor.html.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    settings = load_settings(args.config)

    if args.command == "init":
        storyboard_path = create_storyboard(settings=settings, story_id=args.id, title=args.title)
        print(f"Wrote storyboard: {storyboard_path}")
        return 0

    if args.command == "add-shot":
        storyboard_path = add_shot(
            settings=settings,
            story_id=args.story_id,
            shot_id=args.shot_id,
            title=args.title,
            character_id=args.character_id,
            prompt=args.prompt,
            negative_prompt=args.negative_prompt,
            duration_seconds=args.duration,
            camera=args.camera,
            lighting=args.lighting,
            seed=args.seed,
            width=args.width,
            height=args.height,
            steps=args.steps,
            notes=args.notes,
        )
        print(f"Updated storyboard: {storyboard_path}")
        return 0

    if args.command == "list":
        shots = list_storyboard_shots(settings=settings, story_id=args.story_id)
        if args.json:
            print(json.dumps([shot.__dict__ for shot in shots], ensure_ascii=False, indent=2))
            return 0
        if not shots:
            print("No storyboard shots.")
            return 0
        for shot in shots:
            print(f"{shot.order}. {shot.shot_id}: {shot.title} / {shot.character_id} / {shot.duration_seconds}s")
        return 0

    if args.command == "camera":
        result = set_camera_work(
            settings=settings,
            story_id=args.story_id,
            shot_id=args.shot_id,
            framing=args.framing,
            movement=args.movement,
            lens_mm=args.lens_mm,
            angle=args.angle,
            focus=args.focus,
            notes=args.notes,
        )
        print(f"Wrote camera work: {result.manifest_path}")
        print(f"Camera work items: {result.item_count}")
        return 0

    if args.command == "lighting":
        result = set_lighting_setup(
            settings=settings,
            story_id=args.story_id,
            shot_id=args.shot_id,
            key_light=args.key_light,
            fill_light=args.fill_light,
            rim_light=args.rim_light,
            mood=args.mood,
            time_of_day=args.time_of_day,
            color_palette=args.color_palette,
            notes=args.notes,
        )
        print(f"Wrote lighting setup: {result.manifest_path}")
        print(f"Lighting setup items: {result.item_count}")
        return 0

    if args.command == "link-result":
        result = link_shot_result(
            settings=settings,
            story_id=args.story_id,
            shot_id=args.shot_id,
            result_path=args.result,
            kind=args.kind,
            source=args.source,
            source_reference=args.source_reference,
        )
        print(f"Linked shot result: {result.linked[0].result_id}")
        print(f"Shot results manifest: {result.manifest_path}")
        return 0

    if args.command == "link-comfyui-results":
        result = link_comfyui_results_to_storyboard(
            settings=settings,
            job_id=args.job_id,
            queue_path=args.queue,
            results_manifest_path=args.results_manifest,
        )
        print(f"Linked ComfyUI shot results: {len(result.linked)}")
        print(f"Skipped duplicates: {result.skipped_count}")
        print(f"Shot results manifest: {result.manifest_path}")
        return 0

    if args.command == "results":
        results = list_shot_results(
            settings=settings,
            story_id=args.story_id,
            shot_id=args.shot_id,
        )
        if args.json:
            print(json.dumps([result.__dict__ for result in results], ensure_ascii=False, indent=2))
            return 0
        if not results:
            print("No storyboard shot results.")
            return 0
        for result in results:
            print(f"{result.order}. {result.shot_id}: {result.kind} / {result.source} / {result.stored_path}")
        return 0

    if args.command == "decide-result":
        result = set_shot_result_decision(
            settings=settings,
            story_id=args.story_id,
            result_id=args.result_id,
            decision=args.decision,
            notes=args.notes,
        )
        print(f"Updated shot result decision: {result.result_id}")
        print(f"Decision: {result.decision}")
        return 0

    if args.command == "preview":
        result = write_storyboard_preview(
            settings=settings,
            story_id=args.story_id,
            output_path=args.output,
        )
        print(f"Wrote storyboard preview: {result.preview_path}")
        print(f"Results: {result.result_count}")
        print(f"Selected: {result.selected_count}")
        return 0

    if args.command == "export-selected":
        result = export_selected_shot_manifest(
            settings=settings,
            story_id=args.story_id,
            output_path=args.output,
        )
        print(f"Wrote selected shot manifest: {result.manifest_path}")
        print(f"Selected shots: {result.selected_shot_count}")
        print(f"Missing shots: {result.missing_shot_count}")
        return 0

    if args.command == "draft-plan":
        result = build_draft_generation_plan(
            settings=settings,
            story_id=args.story_id,
            output_path=args.output,
            default_width=args.default_width,
            default_height=args.default_height,
            default_steps=args.default_steps,
        )
        print(f"Wrote draft generation plan: {result.plan_path}")
        print(f"Drafts: {result.draft_count}")
        print(f"Skipped shots: {result.skipped_count}")
        return 0

    if args.command == "editor":
        result = write_storyboard_editor(
            settings=settings,
            story_id=args.story_id,
            output_path=args.output,
        )
        print(f"Wrote storyboard editor: {result.editor_path}")
        print(f"Shots: {result.shot_count}")
        print(f"Selected: {result.selected_count}")
        print(f"Missing: {result.missing_count}")
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
