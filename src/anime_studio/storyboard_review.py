from __future__ import annotations

from dataclasses import dataclass
from html import escape
import json
import os
from pathlib import Path
from typing import Any

from .lora_registry import utc_timestamp
from .settings import AppSettings
from .storyboard import Shot, get_storyboard_path, load_storyboard
from .storyboard_results import get_shot_results_path, read_shot_results_manifest


SHOT_RESULT_DECISIONS = {"candidate", "selected", "rejected"}


@dataclass(frozen=True)
class ShotResultDecision:
    result_id: str
    shot_id: str
    decision: str
    decision_notes: str
    decided_at: str


@dataclass(frozen=True)
class StoryboardPreviewResult:
    preview_path: Path
    result_count: int
    selected_count: int


def set_shot_result_decision(
    settings: AppSettings,
    story_id: str,
    result_id: str,
    decision: str,
    notes: str = "",
) -> ShotResultDecision:
    validate_result_decision(decision)
    load_storyboard(settings, story_id)
    manifest_path = get_shot_results_path(settings, story_id)
    manifest = read_shot_results_manifest(manifest_path)
    results = [dict(item) for item in manifest.get("results", [])]
    target = next((item for item in results if item.get("result_id") == result_id), None)
    if target is None:
        raise ValueError(f"Storyboard shot result not found: {result_id}")

    timestamp = utc_timestamp()
    target_shot_id = str(target.get("shot_id", ""))
    for item in results:
        if item.get("result_id") == result_id:
            item["decision"] = decision
            item["decision_notes"] = notes
            item["decided_at"] = timestamp
            continue
        if decision == "selected" and item.get("shot_id") == target_shot_id and item.get("decision") == "selected":
            item["decision"] = "candidate"
            item["decision_notes"] = "Replaced by another selected result."
            item["decided_at"] = timestamp

    write_raw_results_manifest(manifest_path, story_id, results)
    return ShotResultDecision(
        result_id=result_id,
        shot_id=target_shot_id,
        decision=decision,
        decision_notes=notes,
        decided_at=timestamp,
    )


def write_storyboard_preview(
    settings: AppSettings,
    story_id: str,
    output_path: str | Path | None = None,
) -> StoryboardPreviewResult:
    storyboard = load_storyboard(settings, story_id)
    results = read_raw_shot_results(settings, story_id)
    preview_path = normalize_preview_path(settings, story_id, output_path)
    preview_path.parent.mkdir(parents=True, exist_ok=True)
    preview_path.write_text(
        render_storyboard_preview_html(settings, preview_path, storyboard.title, storyboard.shots, results),
        encoding="utf-8",
    )
    return StoryboardPreviewResult(
        preview_path=preview_path,
        result_count=len(results),
        selected_count=sum(1 for result in results if result_decision(result) == "selected"),
    )


def read_raw_shot_results(settings: AppSettings, story_id: str) -> list[dict[str, Any]]:
    manifest = read_shot_results_manifest(get_shot_results_path(settings, story_id))
    return [dict(item) for item in manifest.get("results", [])]


def write_raw_results_manifest(path: Path, story_id: str, results: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "manifest_type": "storyboard_shot_results",
                "story_id": story_id,
                "updated_at": utc_timestamp(),
                "results": results,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def render_storyboard_preview_html(
    settings: AppSettings,
    preview_path: Path,
    title: str,
    shots: list[Shot],
    results: list[dict[str, Any]],
) -> str:
    results_by_shot: dict[str, list[dict[str, Any]]] = {}
    for result in results:
        results_by_shot.setdefault(str(result.get("shot_id", "")), []).append(result)
    shot_sections = "\n".join(
        render_shot_section(settings, preview_path, shot, results_by_shot.get(shot.shot_id, []))
        for shot in sorted(shots, key=lambda item: item.order)
    )
    return f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)} - Storyboard Preview</title>
  <style>
    :root {{ color-scheme: dark; --bg: #111318; --panel: #1b1f2a; --muted: #9aa4b2; --text: #edf2f7; --selected: #44d17d; --rejected: #ff6b6b; --candidate: #8fb3ff; }}
    body {{ margin: 0; font-family: system-ui, sans-serif; background: var(--bg); color: var(--text); }}
    header {{ padding: 28px; border-bottom: 1px solid #2a3140; }}
    main {{ padding: 24px; display: grid; gap: 18px; }}
    .shot {{ background: var(--panel); border: 1px solid #2a3140; border-radius: 14px; padding: 18px; }}
    .results {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 14px; margin-top: 14px; }}
    .card {{ border: 1px solid #333b4f; border-radius: 12px; overflow: hidden; background: #121722; }}
    .card.selected {{ border-color: var(--selected); box-shadow: 0 0 0 1px var(--selected); }}
    .card.rejected {{ opacity: 0.48; border-color: var(--rejected); }}
    .thumb {{ width: 100%; max-height: 260px; object-fit: contain; background: #080a0f; display: block; }}
    .placeholder {{ padding: 32px 14px; color: var(--muted); word-break: break-all; }}
    .body {{ padding: 12px; }}
    .meta {{ color: var(--muted); font-size: 13px; }}
    .badge {{ display: inline-block; padding: 3px 8px; border-radius: 999px; font-size: 12px; background: #263044; color: var(--candidate); }}
    .badge.selected {{ color: #001b0a; background: var(--selected); }}
    .badge.rejected {{ color: #2b0000; background: var(--rejected); }}
    code {{ color: #cbd5e1; word-break: break-all; }}
  </style>
</head>
<body>
  <header><div class="meta">Storyboard Preview</div><h1>{escape(title)}</h1></header>
  <main>{shot_sections}</main>
</body>
</html>
"""


def render_shot_section(
    settings: AppSettings,
    preview_path: Path,
    shot: Shot,
    results: list[dict[str, Any]],
) -> str:
    cards = "\n".join(render_result_card(settings, preview_path, result) for result in results)
    if not cards:
        cards = '<div class="placeholder">No linked results yet.</div>'
    return f"""<section class="shot">
  <div class="meta">#{shot.order:03d} / {escape(shot.shot_id)} / {escape(shot.character_id)}</div>
  <h2>{escape(shot.title)}</h2>
  <div class="meta">{escape(shot.prompt)}</div>
  <div class="results">{cards}</div>
</section>"""


def render_result_card(settings: AppSettings, preview_path: Path, result: dict[str, Any]) -> str:
    decision = result_decision(result)
    preview = render_result_preview(settings, preview_path, result)
    return f"""<article class="card {escape(decision)}">
  {preview}
  <div class="body">
    <span class="badge {escape(decision)}">{escape(decision)}</span>
    <p><code>{escape(str(result.get("result_id", "")))}</code></p>
    <p class="meta">{escape(str(result.get("source", "")))} / {escape(str(result.get("kind", "")))}</p>
    <p class="meta">{escape(str(result.get("decision_notes", "")))}</p>
  </div>
</article>"""


def render_result_preview(settings: AppSettings, preview_path: Path, result: dict[str, Any]) -> str:
    stored_path = str(result.get("stored_path", ""))
    kind = str(result.get("kind", ""))
    if kind == "image" and stored_path and not stored_path.startswith("output:"):
        src = result_preview_src(settings, preview_path, stored_path)
        return f'<img class="thumb" src="{escape(src)}" alt="{escape(str(result.get("result_id", "")))}">'
    label = stored_path or str(result.get("source_reference", "")) or str(result.get("result_id", ""))
    return f'<div class="placeholder">{escape(label)}</div>'


def result_preview_src(settings: AppSettings, preview_path: Path, stored_path: str) -> str:
    path = Path(stored_path)
    if not path.is_absolute():
        path = settings.project_root / path
    return os.path.relpath(path, preview_path.parent).replace("\\", "/")


def normalize_preview_path(settings: AppSettings, story_id: str, output_path: str | Path | None) -> Path:
    if output_path is None:
        return get_storyboard_path(settings, story_id).parent / "preview.html"
    path = Path(output_path)
    if not path.is_absolute():
        path = settings.project_root / path
    return path


def result_decision(result: dict[str, Any]) -> str:
    decision = str(result.get("decision", "candidate"))
    return decision if decision in SHOT_RESULT_DECISIONS else "candidate"


def validate_result_decision(decision: str) -> None:
    if decision not in SHOT_RESULT_DECISIONS:
        allowed = ", ".join(sorted(SHOT_RESULT_DECISIONS))
        raise ValueError(f"decision must be one of: {allowed}")
