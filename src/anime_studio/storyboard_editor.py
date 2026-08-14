from __future__ import annotations

from dataclasses import dataclass
from html import escape
import json
import os
from pathlib import Path
from typing import Any

from .settings import AppSettings
from .storyboard import Shot, get_storyboard_path, load_storyboard
from .storyboard_production import CameraWork, LightingSetup, load_camera_work_map, load_lighting_setup_map
from .storyboard_review import read_raw_shot_results, result_decision
from .storyboard_suggestions import normalize_suggestion_report_path


@dataclass(frozen=True)
class StoryboardEditorResult:
    editor_path: Path
    shot_count: int
    selected_count: int
    missing_count: int


def write_storyboard_editor(
    settings: AppSettings,
    story_id: str,
    output_path: str | Path | None = None,
) -> StoryboardEditorResult:
    storyboard = load_storyboard(settings, story_id)
    results = read_raw_shot_results(settings, story_id)
    camera_by_shot = load_camera_work_map(settings, story_id)
    lighting_by_shot = load_lighting_setup_map(settings, story_id)
    suggestions_by_shot = load_suggestion_map(settings, story_id)
    timeline_readiness = load_timeline_readiness(settings, story_id)
    editor_path = normalize_editor_path(settings, story_id, output_path)
    editor_path.parent.mkdir(parents=True, exist_ok=True)
    selected_count = sum(1 for result in results if result_decision(result) == "selected")
    missing_count = sum(
        1
        for shot in storyboard.shots
        if not any(result_decision(result) == "selected" and result.get("shot_id") == shot.shot_id for result in results)
    )
    editor_path.write_text(
        render_storyboard_editor_html(
            settings,
            editor_path,
            storyboard.title,
            storyboard.shots,
            results,
            camera_by_shot,
            lighting_by_shot,
            suggestions_by_shot,
            timeline_readiness,
        ),
        encoding="utf-8",
    )
    return StoryboardEditorResult(
        editor_path=editor_path,
        shot_count=len(storyboard.shots),
        selected_count=selected_count,
        missing_count=missing_count,
    )


def render_storyboard_editor_html(
    settings: AppSettings,
    editor_path: Path,
    title: str,
    shots: list[Shot],
    results: list[dict[str, Any]],
    camera_by_shot: dict[str, CameraWork] | None = None,
    lighting_by_shot: dict[str, LightingSetup] | None = None,
    suggestions_by_shot: dict[str, dict[str, Any]] | None = None,
    timeline_readiness: dict[str, Any] | None = None,
) -> str:
    camera_by_shot = camera_by_shot or {}
    lighting_by_shot = lighting_by_shot or {}
    suggestions_by_shot = suggestions_by_shot or {}
    timeline_readiness = timeline_readiness or {}
    results_by_shot: dict[str, list[dict[str, Any]]] = {}
    for result in results:
        results_by_shot.setdefault(str(result.get("shot_id", "")), []).append(result)
    selected_count = sum(1 for result in results if result_decision(result) == "selected")
    missing_count = sum(
        1
        for shot in shots
        if not any(result_decision(result) == "selected" for result in results_by_shot.get(shot.shot_id, []))
    )
    shot_sections = "\n".join(
        render_shot_editor_section(
            settings,
            editor_path,
            shot,
            results_by_shot.get(shot.shot_id, []),
            camera_by_shot.get(shot.shot_id),
            lighting_by_shot.get(shot.shot_id),
            suggestions_by_shot.get(shot.shot_id),
            timeline_readiness,
        )
        for shot in sorted(shots, key=lambda item: item.order)
    )
    timeline_block = render_timeline_readiness_block(timeline_readiness)
    return f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)} - Shot Editor</title>
  <style>
    :root {{ color-scheme: dark; --bg: #0f1117; --panel: #181c27; --card: #10141d; --line: #2a3140; --muted: #9aa4b2; --text: #edf2f7; --selected: #44d17d; --warn: #ffd166; --rejected: #ff6b6b; }}
    body {{ margin: 0; font-family: system-ui, sans-serif; background: var(--bg); color: var(--text); }}
    header {{ padding: 28px; border-bottom: 1px solid var(--line); }}
    main {{ display: grid; gap: 18px; padding: 24px; }}
    .summary {{ display: flex; flex-wrap: wrap; gap: 10px; margin-top: 10px; }}
    .pill {{ border: 1px solid var(--line); border-radius: 999px; padding: 6px 10px; color: var(--muted); }}
    .shot {{ display: grid; gap: 14px; background: var(--panel); border: 1px solid var(--line); border-radius: 16px; padding: 18px; }}
    .shot.missing {{ border-color: var(--warn); }}
    .suggestion {{ border-color: #3b82f6; }}
    .suggestion.ready {{ border-color: var(--selected); }}
    .suggestion.needs_attention {{ border-color: var(--warn); }}
    .suggestion.blocked {{ border-color: var(--rejected); }}
    .tag-list {{ display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }}
    .grid {{ display: grid; grid-template-columns: minmax(220px, 0.8fr) minmax(240px, 1.2fr); gap: 14px; }}
    .box {{ background: var(--card); border: 1px solid var(--line); border-radius: 12px; padding: 12px; }}
    .muted {{ color: var(--muted); font-size: 13px; }}
    .thumb {{ width: 100%; max-height: 280px; object-fit: contain; background: #080a0f; border-radius: 10px; }}
    .badge {{ display: inline-block; padding: 3px 8px; border-radius: 999px; background: #263044; color: var(--muted); font-size: 12px; }}
    .badge.selected {{ background: var(--selected); color: #001b0a; }}
    .badge.rejected {{ background: var(--rejected); color: #2b0000; }}
    .badge.ready {{ background: var(--selected); color: #001b0a; }}
    .badge.needs_attention {{ background: var(--warn); color: #2b1d00; }}
    .badge.blocked {{ background: var(--rejected); color: #2b0000; }}
    code {{ color: #cbd5e1; word-break: break-all; }}
    @media (max-width: 760px) {{ .grid {{ grid-template-columns: 1fr; }} }}
  </style>
</head>
<body>
  <header>
    <div class="muted">AI Anime Studio / Shot Editor</div>
    <h1>{escape(title)}</h1>
    <div class="summary">
      <span class="pill">shots: {len(shots)}</span>
      <span class="pill">selected: {selected_count}</span>
      <span class="pill">missing: {missing_count}</span>
    </div>
    {timeline_block}
  </header>
  <main>{shot_sections}</main>
</body>
</html>
"""


def render_shot_editor_section(
    settings: AppSettings,
    editor_path: Path,
    shot: Shot,
    results: list[dict[str, Any]],
    camera: CameraWork | None = None,
    lighting: LightingSetup | None = None,
    suggestion: dict[str, Any] | None = None,
    timeline_readiness: dict[str, Any] | None = None,
) -> str:
    selected = next((result for result in results if result_decision(result) == "selected"), None)
    status = "selected" if selected else "missing"
    timeline_status = shot_timeline_status(shot.shot_id, timeline_readiness or {})
    result_cards = "\n".join(render_editor_result_card(settings, editor_path, result) for result in results)
    if not result_cards:
        result_cards = '<p class="muted">No generated results linked yet.</p>'
    selected_block = render_selected_block(settings, editor_path, selected)
    params = render_shot_params(shot, camera, lighting)
    suggestion_block = render_suggestion_block(suggestion)
    return f"""<section class="shot {status}">
  <div>
    <div class="muted">#{shot.order:03d} / {escape(shot.shot_id)} / {escape(status)}</div>
    <h2>{escape(shot.title)}</h2>
    {timeline_status}
  </div>
  <div class="grid">
    <div class="box">{params}</div>
    <div class="box">{selected_block}</div>
  </div>
  {suggestion_block}
  <div class="box">
    <div class="muted">All linked results</div>
    {result_cards}
  </div>
</section>"""


def load_timeline_readiness(settings: AppSettings, story_id: str) -> dict[str, Any]:
    base = settings.project_root / "manifests" / "storyboards" / story_id
    edit_manifest_path = base / "edit_timeline_manifest.json"
    export_manifest_path = base / "edit_exports" / "edit_export_manifest.json"
    revision_review_path = base / "timeline_revision_review.json"
    selected_revision_path = base / "selected_timeline_revision.json"
    edit_manifest = read_json_if_exists(edit_manifest_path)
    video_shot_ids = {
        str(clip.get("shot_id", ""))
        for track in edit_manifest.get("tracks", [])
        if track.get("track_type") == "video"
        for clip in track.get("clips", [])
    }
    return {
        "edit_manifest_exists": edit_manifest_path.exists(),
        "edit_manifest_path": str(edit_manifest_path),
        "edit_clip_count": int(edit_manifest.get("counts", {}).get("clip_count", 0)) if edit_manifest else 0,
        "video_shot_ids": sorted(value for value in video_shot_ids if value),
        "export_manifest_exists": export_manifest_path.exists(),
        "export_manifest_path": str(export_manifest_path),
        "revision_review_exists": revision_review_path.exists(),
        "revision_review_path": str(revision_review_path),
        "selected_revision_exists": selected_revision_path.exists(),
        "selected_revision_path": str(selected_revision_path),
    }


def read_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def render_timeline_readiness_block(readiness: dict[str, Any]) -> str:
    edit_status = "ready" if readiness.get("edit_manifest_exists") else "needs_attention"
    export_status = "ready" if readiness.get("export_manifest_exists") else "needs_attention"
    revision_status = "ready" if readiness.get("selected_revision_exists") else "needs_attention"
    return f"""<div class="box timeline-readiness">
      <div class="muted">Timeline Readiness</div>
      <p>
        <span class="badge {edit_status}">edit manifest</span>
        <span class="badge {export_status}">external export</span>
        <span class="badge {revision_status}">adopted revision</span>
      </p>
      <p class="muted">timeline clips: {escape(str(readiness.get('edit_clip_count', 0)))}</p>
    </div>"""


def shot_timeline_status(shot_id: str, readiness: dict[str, Any]) -> str:
    if not readiness.get("edit_manifest_exists"):
        return '<span class="badge needs_attention">timeline manifest missing</span>'
    if shot_id in set(readiness.get("video_shot_ids", [])):
        return '<span class="badge ready">timeline ready</span>'
    return '<span class="badge needs_attention">not in timeline</span>'


def load_suggestion_map(settings: AppSettings, story_id: str) -> dict[str, dict[str, Any]]:
    path = normalize_suggestion_report_path(settings, story_id, None)
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    return {str(item.get("shot_id", "")): dict(item) for item in data.get("shots", [])}


def render_suggestion_block(suggestion: dict[str, Any] | None) -> str:
    if suggestion is None:
        return ""
    risk_level = str(suggestion.get("risk_level", "needs_attention"))
    readiness_score = escape(str(suggestion.get("readiness_score", "")))
    missing = render_tag_list("missing", suggestion.get("missing", []))
    quality_flags = render_tag_list("quality flags", suggestion.get("quality_flags", []))
    prompt_additions = render_tag_list("prompt additions", suggestion.get("prompt_additions", []))
    actions = render_action_list(suggestion.get("suggestions", []))
    return f"""<div class="box suggestion {escape(risk_level)}">
    <div class="muted">Shot Suggestion AI</div>
    <p><span class="badge {escape(risk_level)}">{escape(risk_level)}</span> readiness: {readiness_score}</p>
    {missing}
    {quality_flags}
    {prompt_additions}
    {actions}
  </div>"""


def render_tag_list(label: str, values: object) -> str:
    if not isinstance(values, list) or not values:
        return ""
    tags = "".join(f'<span class="badge">{escape(str(value))}</span>' for value in values)
    return f'<div><div class="muted">{escape(label)}</div><div class="tag-list">{tags}</div></div>'


def render_action_list(values: object) -> str:
    if not isinstance(values, list) or not values:
        return ""
    items = "".join(f"<li>{escape(str(value))}</li>" for value in values)
    return f"<div><div class=\"muted\">suggestions</div><ul>{items}</ul></div>"


def render_shot_params(shot: Shot, camera: CameraWork | None = None, lighting: LightingSetup | None = None) -> str:
    rows = [
        ("character", shot.character_id),
        ("duration", f"{shot.duration_seconds}s"),
        ("prompt", shot.prompt),
        ("negative", shot.negative_prompt),
        ("camera", shot.camera),
        ("lighting", shot.lighting),
        ("camera work", render_camera_work(camera)),
        ("lighting setup", render_lighting_setup(lighting)),
        ("seed", str(shot.seed or "")),
        ("size", render_size(shot)),
        ("steps", str(shot.steps or "")),
        ("notes", shot.notes),
    ]
    items = "\n".join(f"<dt>{escape(label)}</dt><dd>{escape(value)}</dd>" for label, value in rows if value)
    if not items:
        items = "<dd>No shot parameters yet.</dd>"
    return f"<dl>{items}</dl>"


def render_camera_work(camera: CameraWork | None) -> str:
    if camera is None:
        return ""
    parts = [
        camera.framing,
        camera.movement,
        f"{camera.lens_mm}mm lens" if camera.lens_mm else "",
        camera.angle,
        camera.focus,
        camera.notes,
    ]
    return ", ".join(part for part in parts if part)


def render_lighting_setup(lighting: LightingSetup | None) -> str:
    if lighting is None:
        return ""
    parts = [
        lighting.key_light,
        lighting.fill_light,
        lighting.rim_light,
        lighting.mood,
        lighting.time_of_day,
        lighting.color_palette,
        lighting.notes,
    ]
    return ", ".join(part for part in parts if part)


def render_selected_block(settings: AppSettings, editor_path: Path, result: dict[str, Any] | None) -> str:
    if result is None:
        return '<span class="badge">missing selected result</span><p class="muted">Select a candidate before exporting to Unity/editor manifest.</p>'
    preview = render_editor_preview(settings, editor_path, result)
    return f"""<span class="badge selected">selected</span>
{preview}
<p><code>{escape(str(result.get("result_id", "")))}</code></p>
<p class="muted">{escape(str(result.get("decision_notes", "")))}</p>"""


def render_editor_result_card(settings: AppSettings, editor_path: Path, result: dict[str, Any]) -> str:
    decision = result_decision(result)
    return f"""<p>
  <span class="badge {escape(decision)}">{escape(decision)}</span>
  <code>{escape(str(result.get("result_id", "")))}</code>
  <span class="muted">{escape(str(result.get("stored_path", "")))}</span>
</p>"""


def render_editor_preview(settings: AppSettings, editor_path: Path, result: dict[str, Any]) -> str:
    stored_path = str(result.get("stored_path", ""))
    if str(result.get("kind", "")) == "image" and stored_path and not stored_path.startswith("output:"):
        path = Path(stored_path)
        if not path.is_absolute():
            path = settings.project_root / path
        src = os.path.relpath(path, editor_path.parent).replace("\\", "/")
        return f'<img class="thumb" src="{escape(src)}" alt="{escape(str(result.get("result_id", "")))}">'
    label = stored_path or str(result.get("source_reference", "")) or str(result.get("result_id", ""))
    return f'<p class="muted">{escape(label)}</p>'


def render_size(shot: Shot) -> str:
    if shot.width is None and shot.height is None:
        return ""
    return f"{shot.width or '?'}x{shot.height or '?'}"


def normalize_editor_path(settings: AppSettings, story_id: str, output_path: str | Path | None) -> Path:
    if output_path is None:
        return get_storyboard_path(settings, story_id).parent / "editor.html"
    path = Path(output_path)
    if not path.is_absolute():
        path = settings.project_root / path
    return path
