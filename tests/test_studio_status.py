from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from anime_studio.settings import load_settings
from anime_studio.studio_status import build_studio_status, probe_comfyui_nodes, workflow_uses_ipadapter


class StudioStatusTest(unittest.TestCase):
    def test_reports_unreachable_comfyui_node_probe_as_warning(self) -> None:
        result = probe_comfyui_nodes("http://127.0.0.1:1")

        self.assertEqual(result["status"], "warning")

    def test_builds_character_and_story_readiness_dashboard(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = write_settings(root)
            profile = root / "assets" / "processed" / "characters" / "hero" / "profile.json"
            write_json(
                profile,
                {"character_id": "hero", "profile_data": {"training": {"source_rights_confirmed": True}}},
            )
            character_manifests = root / "manifests" / "characters" / "hero"
            write_json(character_manifests / "character_2p5d_definition.json", {"manifest_type": "character_2p5d_definition"})
            write_json(character_manifests / "simple_2p5d_review.json", {"status": "approved"})
            write_json(character_manifests / "simple_2p5d_generation_readiness.json", {"ready": True})
            write_json(
                root / "outputs" / "comfyui" / "hero" / "simple_2p5d_control_workflow.json",
                {"17": {"class_type": "ImageCompositeMasked", "inputs": {}}},
            )
            write_json(
                root / "manifests" / "training" / "hero" / "training_readiness.json",
                {"ready": True, "counts": {"image_count": 20, "issue_count": 0}},
            )
            write_json(root / "manifests" / "training" / "hero" / "training_diagnostics.json", {"status": "completed"})
            image = root / "datasets" / "lora" / "hero" / "images" / "hero.png"
            image.parent.mkdir(parents=True)
            image.write_bytes(b"image")

            write_json(root / "storyboards" / "pilot" / "storyboard.json", {"story_id": "pilot"})
            write_json(root / "storyboards" / "pilot" / "shot_results.json", {"results": [{"result_id": "r1"}]})
            story_manifests = root / "manifests" / "storyboards" / "pilot"
            write_json(story_manifests / "selected_shots.json", {"shots": [{"shot_id": "s1"}]})
            write_json(story_manifests / "phase6_manifest.json", {"story_id": "pilot"})
            write_json(story_manifests / "edit_timeline_manifest.json", {"story_id": "pilot", "shots": [{"shot_id": "s1"}]})

            result = build_studio_status(settings, probe_live=False)
            payload = json.loads(result.json_path.read_text(encoding="utf-8"))
            html = result.html_path.read_text(encoding="utf-8")

            self.assertEqual(result.overall_status, "operational")
            self.assertEqual(payload["summary"]["character_count"], 1)
            self.assertEqual(payload["summary"]["generation_ready_characters"], 1)
            self.assertTrue(payload["characters"][0]["face_repair_enabled"])
            self.assertFalse(payload["characters"][0]["ipadapter_enabled"])
            self.assertEqual(payload["characters"][0]["training_diagnostics_status"], "completed")
            self.assertEqual(payload["characters"][0]["clean_frame_review"]["pending_count"], 0)
            self.assertEqual(payload["summary"]["training_ready_characters"], 1)
            self.assertEqual(payload["summary"]["timeline_ready_stories"], 1)
            self.assertEqual(payload["summary"]["queue_failed_jobs"], 0)
            self.assertIn("hero", html)
            self.assertIn("pilot", html)

    def test_reports_stale_timeline_and_missing_training_check(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = write_settings(root)
            write_json(root / "assets" / "processed" / "characters" / "hero" / "profile.json", {"character_id": "hero"})
            manifests = root / "manifests" / "characters" / "hero"
            write_json(manifests / "simple_2p5d_generation_readiness.json", {"ready": True})
            write_json(root / "storyboards" / "pilot" / "storyboard.json", {"story_id": "pilot"})
            story_manifests = root / "manifests" / "storyboards" / "pilot"
            write_json(story_manifests / "selected_shots.json", {"shots": [{"shot_id": "s1"}]})
            write_json(story_manifests / "edit_timeline_manifest.json", {"shots": []})
            write_json(
                root / "queues" / "comfyui" / "jobs.json",
                {"jobs": [{"job_id": "failed-1", "status": "failed", "workflow_path": "bad.json", "error": "bad node"}]},
            )

            result = build_studio_status(settings, probe_live=False)
            payload = json.loads(result.json_path.read_text(encoding="utf-8"))

            self.assertEqual(payload["characters"][0]["status"], "warning")
            self.assertEqual(payload["overall_status"], "operational")
            self.assertIn("学習readinessを実行", payload["characters"][0]["next_actions"])
            self.assertFalse(payload["stories"][0]["timeline_ready"])
            self.assertIn("再生成", payload["stories"][0]["next_actions"][-1])
            self.assertEqual(payload["comfyui_queue"]["failed_count"], 1)
            self.assertEqual(payload["comfyui_queue"]["failed_jobs"][0]["error"], "bad node")

    def test_detects_optional_ipadapter_workflow(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = write_settings(root)
            workflow_path = root / "outputs" / "comfyui" / "hero" / "workflow.json"
            write_json(workflow_path, {"19": {"class_type": "IPAdapterUnifiedLoader", "inputs": {}}})

            self.assertTrue(workflow_uses_ipadapter(settings))

    def test_tolerates_human_edited_invalid_shapes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = write_settings(root)
            write_json(root / "assets" / "processed" / "characters" / "hero" / "profile.json", {"profile_data": []})
            write_json(
                root / "manifests" / "characters" / "hero" / "simple_2p5d_generation_readiness.json",
                {"ready": True, "counts": {"issue_count": "invalid"}},
            )
            write_json(
                root / "manifests" / "characters" / "hero" / "video_analysis" / "scene01_clean_frames.json",
                {"frames": []},
            )
            queue_path = root / "queues" / "comfyui" / "jobs.json"
            queue_path.parent.mkdir(parents=True)
            queue_path.write_text("[]", encoding="utf-8")

            result = build_studio_status(settings, probe_live=False)
            payload = json.loads(result.json_path.read_text(encoding="utf-8"))

            self.assertEqual(payload["characters"][0]["generation_issue_count"], 0)
            self.assertEqual(payload["characters"][0]["clean_frame_review"]["pending_count"], 1)
            self.assertEqual(payload["comfyui_queue"]["job_count"], 0)


def write_settings(root: Path):
    config = root / "config" / "local_6gb.json"
    write_json(
        config,
        {
            "runtime": {"name": "test_6gb", "max_vram_gb": 6, "target_gpu_utilization": 0.8, "target_gpu_temp_c": 60},
            "assets": {"raw_dir": "assets/raw", "processed_dir": "assets/processed"},
            "datasets": {"lora_dir": "datasets/lora"},
            "models": {"wd14_dir": "models/wd14"},
            "asset_types": {"image_extensions": [".png"], "video_extensions": [".mp4"]},
        },
    )
    return load_settings(config)


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
