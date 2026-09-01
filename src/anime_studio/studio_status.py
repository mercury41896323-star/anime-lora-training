from __future__ import annotations

from dataclasses import asdict, dataclass
from html import escape
import json
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen
import webbrowser

from .lora_registry import project_relative_path, utc_timestamp
from .settings import AppSettings, load_settings


@dataclass(frozen=True)
class StudioStatusResult:
    json_path: Path
    html_path: Path
    overall_status: str
    blocking_count: int
    warning_count: int


def build_studio_status(
    settings: AppSettings,
    output_dir: str | Path | None = None,
    comfyui_url: str = "http://127.0.0.1:8188",
    probe_live: bool = True,
) -> StudioStatusResult:
    target_dir = normalize_output_dir(settings, output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    system_checks = collect_system_checks(settings, comfyui_url, probe_live)
    characters = collect_character_statuses(settings)
    stories = collect_story_statuses(settings)
    queue_status = collect_queue_status(settings)
    blocking_count = sum(item["status"] == "blocked" for item in system_checks)
    warning_count = sum(item["status"] == "warning" for item in system_checks)
    warning_count += sum(item["status"] != "ready" for item in characters)
    warning_count += sum(item["status"] != "ready" for item in stories)
    warning_count += queue_status["status"] == "warning"
    if blocking_count:
        overall_status = "blocked"
    elif not characters and not stories:
        overall_status = "empty"
    elif any(item["generation_ready"] for item in characters) or any(item["timeline_ready"] for item in stories):
        overall_status = "operational"
    else:
        overall_status = "needs_attention"
    payload = {
        "schema_version": 1,
        "manifest_type": "anime_studio_status",
        "generated_at": utc_timestamp(),
        "overall_status": overall_status,
        "runtime_profile": asdict(settings.runtime),
        "summary": {
            "blocking_count": blocking_count,
            "warning_count": warning_count,
            "character_count": len(characters),
            "generation_ready_characters": sum(item["generation_ready"] for item in characters),
            "training_ready_characters": sum(item["training_ready"] for item in characters),
            "story_count": len(stories),
            "timeline_ready_stories": sum(item["timeline_ready"] for item in stories),
            "queue_active_jobs": queue_status["pending_count"] + queue_status["submitted_count"],
            "queue_failed_jobs": queue_status["failed_count"],
        },
        "system_checks": system_checks,
        "characters": characters,
        "stories": stories,
        "comfyui_queue": queue_status,
    }
    json_path = target_dir / "anime_studio_status.json"
    html_path = target_dir / "anime_studio_status.html"
    write_json(json_path, payload)
    html_path.write_text(render_status_html(payload), encoding="utf-8")
    return StudioStatusResult(json_path, html_path, overall_status, blocking_count, warning_count)


def collect_system_checks(
    settings: AppSettings,
    comfyui_url: str,
    probe_live: bool,
) -> list[dict[str, str]]:
    checks = [
        check(
            "python",
            "Python",
            "ready" if sys.version_info >= (3, 10) else "blocked",
            f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "Python 3.10以上を使用してください。",
        ),
        check(
            "runtime_profile",
            "低VRAM設定",
            "ready" if settings.runtime.max_vram_gb <= 6.0 else "warning",
            f"{settings.runtime.name} / {settings.runtime.max_vram_gb:.1f} GB",
            "RTX 3050では6GB以下のprofileを使用してください。",
        ),
    ]
    for executable, label in (("git", "Git"), ("ffmpeg", "FFmpeg"), ("ffprobe", "FFprobe")):
        path = shutil.which(executable)
        checks.append(
            check(
                executable,
                label,
                "ready" if path else "warning",
                path or "未検出",
                f"{label}をPATHへ追加してください。",
            )
        )
    if not probe_live:
        checks.extend(
            (
                check("gpu", "NVIDIA GPU", "warning", "ライブ確認を省略", "--no-liveを外して再実行してください。"),
                check("comfyui", "ComfyUI API", "warning", "ライブ確認を省略", "ComfyUI起動後に再確認してください。"),
            )
        )
        return checks
    checks.append(probe_nvidia_gpu())
    checks.append(probe_comfyui(comfyui_url))
    checks.append(probe_comfyui_nodes(comfyui_url, require_ipadapter=workflow_uses_ipadapter(settings)))
    return checks


def probe_nvidia_gpu() -> dict[str, str]:
    executable = shutil.which("nvidia-smi")
    if not executable:
        return check("gpu", "NVIDIA GPU", "warning", "nvidia-smi未検出", "NVIDIAドライバーを確認してください。")
    try:
        result = subprocess.run(
            [executable, "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return check("gpu", "NVIDIA GPU", "warning", str(exc), "nvidia-smiを手動確認してください。")
    detail = result.stdout.strip()
    if not detail:
        return check("gpu", "NVIDIA GPU", "warning", "GPU情報を取得できませんでした", "nvidia-smiを手動確認してください。")
    return check("gpu", "NVIDIA GPU", "ready", detail, "")


def probe_comfyui(base_url: str) -> dict[str, str]:
    try:
        with urlopen(base_url.rstrip("/") + "/system_stats", timeout=3) as response:
            payload = json.loads(response.read().decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("ComfyUI system_stats did not return a JSON object.")
    except (OSError, URLError, ValueError) as exc:
        return check("comfyui", "ComfyUI API", "warning", str(exc), "ComfyUIを低VRAMモードで起動してください。")
    system = dict(payload.get("system", {}))
    devices = list(payload.get("devices", []))
    device = str(dict(devices[0]).get("name", "GPU不明")) if devices else "GPU未検出"
    detail = f"ComfyUI {system.get('comfyui_version', 'unknown')} / {device}"
    return check("comfyui", "ComfyUI API", "ready", detail, "")


def probe_comfyui_nodes(base_url: str, require_ipadapter: bool = False) -> dict[str, str]:
    required = {
        "CheckpointLoaderSimple",
        "LoraLoader",
        "ControlNetLoader",
        "ControlNetApplyAdvanced",
        "KSampler",
        "VAEDecode",
        "LoadImage",
        "LoadImageMask",
        "FeatherMask",
        "ImageCompositeMasked",
        "SaveImage",
    }
    if require_ipadapter:
        required.update(("IPAdapterUnifiedLoader", "IPAdapterAdvanced", "IPAdapterModelLoader", "CLIPVisionLoader"))
    try:
        with urlopen(base_url.rstrip("/") + "/object_info", timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("ComfyUI object_info did not return a JSON object.")
    except (OSError, URLError, ValueError) as exc:
        return check("comfyui_nodes", "ComfyUI必須Node", "warning", str(exc), "ComfyUIのNode一覧を確認してください。")
    missing = sorted(required - set(payload))
    if missing:
        return check(
            "comfyui_nodes",
            "ComfyUI必須Node",
            "blocked",
            "不足: " + ", ".join(missing),
            "ComfyUI本体を更新し、不足Nodeを導入してください。",
        )
    if require_ipadapter:
        ipadapter_files = object_info_choices(payload, "IPAdapterModelLoader", "ipadapter_file")
        clip_vision_files = object_info_choices(payload, "CLIPVisionLoader", "clip_name")
        model_issues: list[str] = []
        if not any("plus-face_sd15" in name.lower() for name in ipadapter_files):
            model_issues.append("ip-adapter-plus-face_sd15")
        if not any("vit-h-14" in name.lower() and "s32b-b79k" in name.lower() for name in clip_vision_files):
            model_issues.append("CLIP-ViT-H-14")
        if model_issues:
            return check(
                "comfyui_nodes",
                "ComfyUI必須Node",
                "blocked",
                "IPAdapter model不足: " + ", ".join(model_issues),
                "公式SD1.5 IPAdapter Plus FaceとCLIP Visionを配置し、ComfyUIを再起動してください。",
            )
    suffix = " / IPAdapter有効" if require_ipadapter else ""
    return check("comfyui_nodes", "ComfyUI必須Node", "ready", f"{len(required)}種類を確認{suffix}", "")


def object_info_choices(payload: dict[str, Any], node_name: str, input_name: str) -> list[str]:
    node = mapping(payload.get(node_name))
    required = mapping(mapping(node.get("input")).get("required"))
    raw = required.get(input_name, [])
    if not isinstance(raw, list) or not raw or not isinstance(raw[0], list):
        return []
    return [str(value) for value in raw[0]]


def workflow_uses_ipadapter(settings: AppSettings) -> bool:
    workflow_root = settings.project_root / "outputs" / "comfyui"
    if not workflow_root.is_dir():
        return False
    for workflow_path in workflow_root.rglob("*.json"):
        workflow = read_json(workflow_path)
        if any(
            isinstance(node, dict) and str(node.get("class_type", "")).startswith("IPAdapter")
            for node in workflow.values()
        ):
            return True
    return False


def collect_character_statuses(settings: AppSettings) -> list[dict[str, Any]]:
    root = settings.assets.processed / "characters"
    if not root.is_dir():
        return []
    results: list[dict[str, Any]] = []
    for profile_path in sorted(root.glob("*/profile.json")):
        character_id = profile_path.parent.name
        profile = read_json(profile_path)
        manifest_root = settings.project_root / "manifests" / "characters" / character_id
        review = read_json(manifest_root / "simple_2p5d_review.json")
        generation = read_json(manifest_root / "simple_2p5d_generation_readiness.json")
        training_path = settings.project_root / "manifests" / "training" / character_id / "training_readiness.json"
        training = read_json(training_path)
        diagnostics = read_json(training_path.parent / "training_diagnostics.json")
        diagnostics_status = str(diagnostics.get("status", "not_run"))
        definition_path = manifest_root / "character_2p5d_definition.json"
        workflow_path = settings.project_root / "outputs" / "comfyui" / character_id / "simple_2p5d_control_workflow.json"
        workflow = read_json(workflow_path)
        clean_review = collect_clean_frame_review_status(manifest_root / "video_analysis")
        dataset_root = settings.datasets.lora / character_id
        training_counts = mapping(training.get("counts"))
        generation_counts = mapping(generation.get("counts"))
        image_count = safe_int(training_counts.get("image_count"), count_images(settings, dataset_root))
        review_approved = str(review.get("status", "")) == "approved"
        generation_ready = bool(generation.get("ready", False))
        training_ready = bool(training.get("ready", False))
        profile_training = mapping(mapping(profile.get("profile_data")).get("training"))
        source_rights_confirmed = bool(profile_training.get("source_rights_confirmed", False))
        face_repair_enabled = any(
            isinstance(node, dict) and node.get("class_type") == "ImageCompositeMasked"
            for node in workflow.values()
        )
        ipadapter_enabled = any(
            isinstance(node, dict) and str(node.get("class_type", "")).startswith("IPAdapter")
            for node in workflow.values()
        )
        next_actions: list[str] = []
        if not definition_path.is_file():
            next_actions.append("Character 2.5D Definitionを生成")
        if not review_approved:
            next_actions.append("Simple 2.5D Rigを確認・承認")
        if not generation_ready:
            next_actions.append("LoRA・ControlNet・ComfyUI入力を確認")
        elif not face_repair_enabled:
            next_actions.append("Simple 2.5D workflowを更新してFace Repairを有効化")
        if not training_path.is_file():
            next_actions.append("学習readinessを実行")
        if image_count < 20:
            next_actions.append("学習画像を20枚以上へ増やす")
        if not source_rights_confirmed:
            next_actions.append("学習・配布前に素材の利用権を確認")
        if clean_review["pending_count"]:
            next_actions.append(f"Clean Frameを確認（{clean_review['pending_count']}動画）")
        if diagnostics_status == "failed":
            next_actions.append("学習diagnosticsの問題を修正して再実行")
        if generation_ready and face_repair_enabled and training_ready and source_rights_confirmed and not clean_review["pending_count"] and diagnostics_status != "failed":
            status = "ready"
        elif generation_ready or training_ready:
            status = "warning"
        else:
            status = "needs_attention"
        results.append(
            {
                "character_id": character_id,
                "status": status,
                "profile": project_relative_path(settings, profile_path),
                "definition_2p5d": definition_path.is_file(),
                "rig_review_approved": review_approved,
                "generation_ready": generation_ready,
                "face_repair_enabled": face_repair_enabled,
                "ipadapter_enabled": ipadapter_enabled,
                "training_ready": training_ready,
                "source_rights_confirmed": source_rights_confirmed,
                "training_image_count": image_count,
                "generation_issue_count": safe_int(generation_counts.get("issue_count"), 0),
                "training_issue_count": safe_int(training_counts.get("issue_count"), 0),
                "training_diagnostics_status": diagnostics_status,
                "clean_frame_review": clean_review,
                "next_actions": next_actions,
            }
        )
    return results


def collect_story_statuses(settings: AppSettings) -> list[dict[str, Any]]:
    root = settings.project_root / "storyboards"
    if not root.is_dir():
        return []
    results: list[dict[str, Any]] = []
    for storyboard_path in sorted(root.glob("*/storyboard.json")):
        story_id = storyboard_path.parent.name
        manifest_root = settings.project_root / "manifests" / "storyboards" / story_id
        selected = read_json(manifest_root / "selected_shots.json")
        phase6 = read_json(manifest_root / "phase6_manifest.json")
        timeline = read_json(manifest_root / "edit_timeline_manifest.json")
        shot_results = read_json(storyboard_path.parent / "shot_results.json")
        selected_count = list_count(selected.get("shots", selected.get("selected_shots", [])))
        result_count = list_count(shot_results.get("results", []))
        timeline_shot_count = list_count(timeline.get("shots", []))
        timeline_ready = bool(timeline) and selected_count > 0 and timeline_shot_count == selected_count
        next_actions: list[str] = []
        if result_count == 0:
            next_actions.append("Shotを生成して結果を紐付け")
        if selected_count == 0:
            next_actions.append("採用Shotを選択")
        if not phase6:
            next_actions.append("Voice・LipSync・SFX・Motion manifestを生成")
        if not timeline:
            next_actions.append("Edit Timeline manifestを生成")
        elif timeline_shot_count != selected_count:
            next_actions.append("採用Shot変更後にEdit Timeline manifestを再生成")
        results.append(
            {
                "story_id": story_id,
                "status": "ready" if timeline_ready else "needs_attention",
                "storyboard": project_relative_path(settings, storyboard_path),
                "result_count": result_count,
                "selected_shot_count": selected_count,
                "phase6_ready": bool(phase6),
                "timeline_ready": timeline_ready,
                "timeline_shot_count": timeline_shot_count,
                "next_actions": next_actions,
            }
        )
    return results


def collect_queue_status(settings: AppSettings) -> dict[str, Any]:
    queue_path = settings.project_root / "queues" / "comfyui" / "jobs.json"
    queue = read_json(queue_path)
    jobs = queue.get("jobs", [])
    if not isinstance(jobs, list):
        jobs = []
    counts = {status: 0 for status in ("pending", "submitted", "completed", "failed", "dry_run")}
    for raw_job in jobs:
        if not isinstance(raw_job, dict):
            continue
        status = str(raw_job.get("status", "unknown"))
        counts[status] = counts.get(status, 0) + 1
    failed_jobs = [
        {
            "job_id": str(job.get("job_id", "")),
            "workflow_path": str(job.get("workflow_path", "")),
            "error": str(job.get("error", "")),
        }
        for job in jobs
        if isinstance(job, dict) and str(job.get("status", "")) == "failed"
    ]
    return {
        "status": "warning" if counts["failed"] else "ready",
        "queue_path": project_relative_path(settings, queue_path),
        "job_count": len(jobs),
        "pending_count": counts["pending"],
        "submitted_count": counts["submitted"],
        "completed_count": counts["completed"],
        "failed_count": counts["failed"],
        "dry_run_count": counts["dry_run"],
        "failed_jobs": failed_jobs[-5:],
        "next_actions": ["失敗Jobのerrorとworkflowを確認"] if failed_jobs else [],
    }


def collect_clean_frame_review_status(analysis_dir: Path) -> dict[str, int]:
    if not analysis_dir.is_dir():
        return {"video_count": 0, "completed_count": 0, "pending_count": 0}
    clean_manifests = list(analysis_dir.glob("*_clean_frames.json"))
    completed_count = 0
    for clean_manifest in clean_manifests:
        video_id = clean_manifest.name.removesuffix("_clean_frames.json")
        review = read_json(analysis_dir / f"{video_id}_clean_frame_review.json")
        completed_count += str(review.get("status", "")) == "completed"
    return {
        "video_count": len(clean_manifests),
        "completed_count": completed_count,
        "pending_count": len(clean_manifests) - completed_count,
    }


def render_status_html(payload: dict[str, Any]) -> str:
    summary = dict(payload["summary"])
    system_cards = "".join(render_check_card(item) for item in payload["system_checks"])
    character_cards = "".join(render_character_card(item) for item in payload["characters"]) or empty_card("キャラクター未登録")
    story_cards = "".join(render_story_card(item) for item in payload["stories"]) or empty_card("Storyboard未登録")
    queue_card = render_queue_card(dict(payload["comfyui_queue"]))
    return f"""<!doctype html>
<html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Anime Studio Status</title><style>
:root{{--bg:#11151d;--panel:#1b2230;--text:#eef3ff;--muted:#9eabc1;--ready:#54d68b;--warn:#f4c95d;--blocked:#ff6b6b}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font-family:"Segoe UI","Yu Gothic UI",sans-serif}}
main{{max-width:1200px;margin:auto;padding:28px}}h1{{margin:0 0 6px}}h2{{margin-top:30px}}.muted{{color:var(--muted)}}
.summary,.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:14px}}.card{{background:var(--panel);border:1px solid #303a4d;border-radius:14px;padding:16px}}
.value{{font-size:28px;font-weight:700}}.badge{{display:inline-block;border-radius:999px;padding:4px 9px;font-size:12px;font-weight:700}}
.ready{{color:var(--ready)}}.warning,.needs_attention,.empty{{color:var(--warn)}}.blocked{{color:var(--blocked)}}ul{{padding-left:20px}}code{{word-break:break-all}}
</style></head><body><main>
<h1>Anime Studio 制作ステータス</h1><div class="muted">更新: {escape(str(payload['generated_at']))} / 状態: <b class="{escape(str(payload['overall_status']))}">{escape(str(payload['overall_status']))}</b></div>
<h2>概要</h2><div class="summary">
{summary_card('キャラクター', summary['character_count'])}{summary_card('生成可能', summary['generation_ready_characters'])}
{summary_card('Storyboard', summary['story_count'])}{summary_card('Timeline準備済み', summary['timeline_ready_stories'])}
{summary_card('Queue実行中', summary['queue_active_jobs'])}{summary_card('Queue失敗', summary['queue_failed_jobs'])}
{summary_card('要確認', summary['warning_count'])}{summary_card('停止要因', summary['blocking_count'])}
</div><h2>環境</h2><div class="grid">{system_cards}</div>
<h2>キャラクター</h2><div class="grid">{character_cards}</div>
<h2>Storyboard / 編集</h2><div class="grid">{story_cards}</div>
<h2>ComfyUI Queue</h2><div class="grid">{queue_card}</div>
</main></body></html>"""


def render_check_card(item: dict[str, Any]) -> str:
    action = f"<p class='muted'>{escape(str(item['action']))}</p>" if item.get("action") and item["status"] != "ready" else ""
    return f"<section class='card'><span class='badge {escape(item['status'])}'>{escape(item['status'])}</span><h3>{escape(item['label'])}</h3><code>{escape(item['detail'])}</code>{action}</section>"


def render_character_card(item: dict[str, Any]) -> str:
    facts = [
        f"2.5D: {'済' if item['definition_2p5d'] else '未'}",
        f"Rig承認: {'済' if item['rig_review_approved'] else '未'}",
        f"生成: {'可能' if item['generation_ready'] else '未準備'}",
        f"Face Repair: {'有効' if item['face_repair_enabled'] else '未設定'}",
        f"IPAdapter: {'有効' if item['ipadapter_enabled'] else '任意・未使用'}",
        f"学習: {'可能' if item['training_ready'] else '未準備'}",
        f"学習画像: {item['training_image_count']}枚",
        f"学習診断: {item['training_diagnostics_status']}",
        f"素材利用権: {'確認済み' if item['source_rights_confirmed'] else '未確認'}",
        f"Clean Frame確認待ち: {item['clean_frame_review']['pending_count']}動画",
    ]
    return status_card(item["character_id"], item["status"], facts, item["next_actions"])


def render_story_card(item: dict[str, Any]) -> str:
    facts = [
        f"結果: {item['result_count']}件",
        f"採用Shot: {item['selected_shot_count']}件",
        f"Phase 6: {'済' if item['phase6_ready'] else '未'}",
        f"Timeline: {'準備済み' if item['timeline_ready'] else '未準備'}",
        f"Timeline Shot: {item['timeline_shot_count']}件",
    ]
    return status_card(item["story_id"], item["status"], facts, item["next_actions"])


def render_queue_card(item: dict[str, Any]) -> str:
    facts = [
        f"待機: {item['pending_count']}件",
        f"実行中: {item['submitted_count']}件",
        f"完了: {item['completed_count']}件",
        f"失敗: {item['failed_count']}件",
    ]
    return status_card("ComfyUI生成Job", item["status"], facts, item["next_actions"])


def status_card(title: str, status: str, facts: list[str], actions: list[str]) -> str:
    fact_html = "".join(f"<li>{escape(value)}</li>" for value in facts)
    action_html = "".join(f"<li>{escape(value)}</li>" for value in actions) or "<li>追加作業なし</li>"
    return f"<section class='card'><span class='badge {escape(status)}'>{escape(status)}</span><h3>{escape(title)}</h3><ul>{fact_html}</ul><div class='muted'>次の作業</div><ul>{action_html}</ul></section>"


def summary_card(label: str, value: Any) -> str:
    return f"<section class='card'><div class='muted'>{escape(label)}</div><div class='value'>{escape(str(value))}</div></section>"


def empty_card(label: str) -> str:
    return f"<section class='card empty'>{escape(label)}</section>"


def check(check_id: str, label: str, status: str, detail: str, action: str) -> dict[str, str]:
    return {"id": check_id, "label": label, "status": status, "detail": detail, "action": action}


def count_images(settings: AppSettings, root: Path) -> int:
    if not root.is_dir():
        return 0
    return sum(path.suffix.lower() in settings.image_extensions for path in root.rglob("*") if path.is_file())


def list_count(value: Any) -> int:
    return len(value) if isinstance(value, list) else 0


def mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalize_output_dir(settings: AppSettings, output_dir: str | Path | None) -> Path:
    if output_dir in (None, ""):
        return settings.project_root / "outputs" / "status"
    path = Path(output_dir)
    return path if path.is_absolute() else settings.project_root / path


def open_studio_dashboard(path: Path) -> bool:
    return webbrowser.open(path.resolve().as_uri())


def build_parser():
    import argparse

    parser = argparse.ArgumentParser(description="Build an Anime Studio environment and production readiness dashboard.")
    parser.add_argument("--config", default="config/local_6gb.json")
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--comfyui-url", default="http://127.0.0.1:8188")
    parser.add_argument("--no-live", action="store_true")
    parser.add_argument("--open", action="store_true", help="Open the generated dashboard in the default browser.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = build_studio_status(
        load_settings(args.config),
        output_dir=args.output_dir,
        comfyui_url=args.comfyui_url,
        probe_live=not args.no_live,
    )
    print(f"Status JSON: {result.json_path}")
    print(f"Status dashboard: {result.html_path}")
    print(f"Overall: {result.overall_status}")
    print(f"Blocking: {result.blocking_count}")
    print(f"Warnings: {result.warning_count}")
    if args.open:
        open_studio_dashboard(result.html_path)
    return 1 if result.blocking_count else 0
