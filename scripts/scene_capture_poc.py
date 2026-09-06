from __future__ import annotations

import argparse
import json

from anime_studio.scene_capture import SceneCaptureConfig, analyze_and_capture_scenes


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Detect scenes with PySceneDetect and save representative captures."
    )
    parser.add_argument("--video", required=True, help="Source MP4/video path.")
    parser.add_argument("--output-dir", default=None, help="Optional output directory.")
    parser.add_argument(
        "--threshold",
        type=float,
        default=27.0,
        help="PySceneDetect ContentDetector threshold.",
    )
    parser.add_argument(
        "--images-per-scene",
        type=int,
        default=1,
        help="Representative captures to save from each scene.",
    )
    parser.add_argument(
        "--image-format",
        choices=["png", "jpg", "jpeg", "webp"],
        default="png",
        help="Capture image format.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = analyze_and_capture_scenes(
        video_path=args.video,
        output_dir=args.output_dir,
        config=SceneCaptureConfig(
            threshold=args.threshold,
            images_per_scene=args.images_per_scene,
            image_format=args.image_format,
        ),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
