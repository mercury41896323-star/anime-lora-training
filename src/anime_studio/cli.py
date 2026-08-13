from __future__ import annotations

import argparse
import json
from pathlib import Path

from .asset_inventory import collect_asset_inventory
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

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
