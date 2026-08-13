from __future__ import annotations

import argparse
import json

from .settings import load_settings
from .storyboard_results import (
    link_comfyui_results_to_storyboard,
    link_shot_result,
    list_shot_results,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="anime-storyboard",
        description="Lightweight storyboard result management commands.",
    )
    parser.add_argument("--config", default="config/local_6gb.json", help="Path to the local runtime profile.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    link_result = subparsers.add_parser("link-result", help="Link a generated asset to a storyboard shot.")
    link_result.add_argument("--story-id", required=True, help="Storyboard id.")
    link_result.add_argument("--shot-id", required=True, help="Shot id.")
    link_result.add_argument("--result", required=True, help="Generated result path.")
    link_result.add_argument("--kind", default="image", help="Result kind.")
    link_result.add_argument("--source", default="manual", help="Result source.")
    link_result.add_argument("--source-reference", default="", help="Original source reference.")

    link_comfyui = subparsers.add_parser(
        "link-comfyui-results",
        help="Link imported ComfyUI results using storyboard workflow metadata.",
    )
    link_comfyui.add_argument("--job-id", required=True, help="ComfyUI queue job id.")
    link_comfyui.add_argument("--queue", default=None, help="Queue JSON path.")
    link_comfyui.add_argument("--results-manifest", default=None, help="Imported ComfyUI results manifest.")

    results = subparsers.add_parser("results", help="List generated results linked to storyboard shots.")
    results.add_argument("--story-id", required=True, help="Storyboard id.")
    results.add_argument("--shot-id", default=None, help="Optional shot id filter.")
    results.add_argument("--json", action="store_true", help="Print full JSON records.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    settings = load_settings(args.config)

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
        results = list_shot_results(settings=settings, story_id=args.story_id, shot_id=args.shot_id)
        if args.json:
            print(json.dumps([result.__dict__ for result in results], ensure_ascii=False, indent=2))
            return 0
        if not results:
            print("No storyboard shot results.")
            return 0
        for result in results:
            print(f"{result.order}. {result.shot_id}: {result.kind} / {result.source} / {result.stored_path}")
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
