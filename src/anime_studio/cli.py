from __future__ import annotations

import argparse
import json
from pathlib import Path

from .asset_inventory import collect_asset_inventory
from .character_manager import register_character_asset
from .character_profile import create_character_profile
from .dataset_builder import build_lora_dataset
from .frame_extraction import build_frame_extraction_plan, extract_frames
from .settings import load_settings
from .tagger import prepare_tag_sidecars


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
    character_register = character_subparsers.add_parser(
        "register-asset",
        help="Register an image or video under a character workspace.",
    )
    character_register.add_argument("--id", required=True, help="Stable character id.")
    character_register.add_argument("--source", required=True, help="Source asset path.")

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

    tags = subparsers.add_parser(
        "tags",
        help="Create caption sidecars for character images.",
    )
    tags.add_argument("--character-id", required=True, help="Character id to tag.")
    tags.add_argument(
        "--extra-tag",
        action="append",
        default=None,
        help="Additional manual tag. Can be passed more than once.",
    )
    tags.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing caption sidecars.",
    )

    dataset = subparsers.add_parser(
        "dataset",
        help="Build lightweight training datasets.",
    )
    dataset_subparsers = dataset.add_subparsers(dest="dataset_command", required=True)
    dataset_lora = dataset_subparsers.add_parser(
        "build-lora",
        help="Build a LoRA image/caption dataset for one character.",
    )
    dataset_lora.add_argument("--character-id", required=True, help="Character id to export.")
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

    if args.command == "character" and args.character_command == "register-asset":
        asset = register_character_asset(
            settings=settings,
            character_id=args.id,
            source_path=args.source,
        )
        print(f"Registered {asset.kind} asset: {asset.stored_path}")
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

    if args.command == "tags":
        result = prepare_tag_sidecars(
            settings=settings,
            character_id=args.character_id,
            extra_tags=args.extra_tag,
            overwrite=args.overwrite,
        )
        print(f"Wrote {len(result.files_written)} caption sidecars")
        return 0

    if args.command == "dataset" and args.dataset_command == "build-lora":
        result = build_lora_dataset(
            settings=settings,
            character_id=args.character_id,
        )
        print(
            f"Built dataset: {result.dataset_dir} "
            f"({result.image_count} images, {result.caption_count} captions)"
        )
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
