from __future__ import annotations

from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from anime_studio.comfyui_queue import (
    enqueue_comfyui_workflow,
    list_comfyui_jobs,
    refresh_comfyui_job,
    submit_comfyui_job,
)
from anime_studio.settings import load_settings


class ComfyUIQueueTest(unittest.TestCase):
    def test_enqueue_and_dry_run_submission(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = write_settings(root)
            workflow_path = write_workflow(root)

            enqueued = enqueue_comfyui_workflow(settings, workflow_path)
            submitted = submit_comfyui_job(
                settings,
                job_id=enqueued.job["job_id"],
                dry_run=True,
            )

            jobs = list_comfyui_jobs(settings)
            self.assertEqual(len(jobs), 1)
            self.assertEqual(submitted.job["status"], "dry_run")
            self.assertEqual(submitted.job["workflow_path"], "outputs/comfyui/sample/workflow.json")
            self.assertEqual(submitted.job["response"]["prompt"]["1"]["class_type"], "SaveImage")

    def test_submit_and_refresh_with_fake_comfyui_server(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = write_settings(root)
            workflow_path = write_workflow(root)
            server = FakeComfyServer()
            server.start()
            try:
                submitted = submit_comfyui_job(
                    settings,
                    workflow_path=workflow_path,
                    base_url=server.base_url,
                )
                refreshed = refresh_comfyui_job(
                    settings,
                    job_id=submitted.job["job_id"],
                )
            finally:
                server.stop()

            self.assertEqual(server.received_payload["prompt"]["1"]["class_type"], "SaveImage")
            self.assertEqual(submitted.job["status"], "submitted")
            self.assertEqual(submitted.job["prompt_id"], "prompt-test-1")
            self.assertEqual(submitted.job["queue_number"], 1)
            self.assertEqual(refreshed.job["status"], "completed")


class FakeComfyServer:
    def __init__(self) -> None:
        self.received_payload: dict[str, object] = {}
        self.server = HTTPServer(("127.0.0.1", 0), self.build_handler())
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        host, port = self.server.server_address
        return f"http://{host}:{port}"

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.server.shutdown()
        self.thread.join(timeout=5)
        self.server.server_close()

    def build_handler(self):
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length", "0"))
                owner.received_payload = json.loads(self.rfile.read(length).decode("utf-8"))
                self.send_json({"prompt_id": "prompt-test-1", "number": 1, "node_errors": {}})

            def do_GET(self) -> None:
                if self.path == "/history/prompt-test-1":
                    self.send_json({"prompt-test-1": {"outputs": {"1": {"images": []}}}})
                    return
                self.send_json({})

            def log_message(self, format: str, *args) -> None:
                return

            def send_json(self, payload: dict[str, object]) -> None:
                body = json.dumps(payload).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        return Handler


def write_workflow(root: Path) -> Path:
    workflow_path = root / "outputs" / "comfyui" / "sample" / "workflow.json"
    workflow_path.parent.mkdir(parents=True)
    workflow_path.write_text(
        json.dumps({"1": {"class_type": "SaveImage", "inputs": {"images": []}}}),
        encoding="utf-8",
    )
    return workflow_path


def write_settings(root: Path):
    config_dir = root / "config"
    config_dir.mkdir(parents=True)
    config_path = config_dir / "local_6gb.json"
    config_path.write_text(
        json.dumps(
            {
                "runtime": {
                    "name": "test",
                    "max_vram_gb": 6.0,
                    "target_gpu_utilization": 0.8,
                    "target_gpu_temp_c": 60,
                },
                "assets": {
                    "raw_dir": "assets/raw",
                    "processed_dir": "assets/processed",
                },
                "datasets": {
                    "lora_dir": "datasets/lora",
                },
                "models": {
                    "wd14_dir": "models/wd14",
                },
                "asset_types": {
                    "image_extensions": [".png"],
                    "video_extensions": [".mp4"],
                },
            }
        ),
        encoding="utf-8",
    )
    return load_settings(config_path)


if __name__ == "__main__":
    unittest.main()
