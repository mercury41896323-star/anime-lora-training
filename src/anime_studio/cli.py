from __future__ import annotations

import argparse
import json
from pathlib import Path

from .asset_inventory import collect_asset_inventory
from .character_profile import create_character_profile
from .frame_extraction import build_frame_extraction_plan, extract_frames
from .settings import load_settings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="anime-studio",
        description="Small local tools for the AI Anime Studio prototype.",
    )
    parser.add_argument(
        "--config",
        default="config/local_6gb.json",
        help="Path to the local runtime profile.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)
    inventory = subparsers.add_parser(
        "inventory",
        help="Scan raw assets and write a lightweight inventory JSON.",
    )
    inventory.add_argument(
        "--output",
        default="assets/processed/inventory.json",
        help="Where to write the generated inventory JSON.",
    )
    inventory.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON output.",
    )

    character = subparsers.add_parser(
        "character",
        help="Create and manage lightweight character metadata.",
    )
    character_subparsers = character.add_subparsers(dest="character_command", required=True)
    character_init = character_subparsers.add_parser(
        "init",
        help="Create a CharacterProfile JSON file.",
    )
    character_init.add_argument("--id", required=True, help="Stable character id.")
    character_init.add_argument("--name", required=True, help="Human-readable character name.")
    character_init.add_argument(
        "--trigger-tag",
        action="append",
        default=None,
        help="Training or generation trigger tag. Can be passed more than once.",
    )

    frames = subparsers.add_parser(
        "frames",
        help="Prepare or run lightweight video frame extraction.",
    )
    frames.add_argument("--video", required=True, help="Source video path.")
    frames.add_argument("--character-id", required=True, help="Character id for output grouping.")
    frames.add_argument("--fps", type=float, default=1.0, help="Frames per second to extract.")
    frames.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the ffmpeg command without running it.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    settings = load_settings(args.config)

    if args.command == "inventory":
        inventory = collect_asset_inventory(settings)
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(
                inventory,
                ensure_ascii=False,
                indent=2 if args.pretty else None,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"Wrote inventory: {output_path}")
        print(
            "Assets: "
            f"{inventory['counts']['image']} images, "
            f"{inventory['counts']['video']} videos, "
            f"{inventory['counts']['other']} other"
        )
        return 0

    if args.command == "character" and args.character_command == "init":
        profile_path = create_character_profile(
            settings=settings,
            character_id=args.id,
            display_name=args.name,
            trigger_tags=args.trigger_tag,
        )
        print(f"Wrote character profile: {profile_path}")
        return 0

    if args.command == "frames":
        plan = build_frame_extraction_plan(
            settings=settings,
            video_path=args.video,
            character_id=args.character_id,
            fps=args.fps,
        )
        print(" ".join(plan.command))
        if args.dry_run:
            return 0
        return extract_frames(plan)

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
