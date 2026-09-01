from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from anime_studio.settings import load_settings
from anime_studio.training_diagnostics import analyze_training_run


class TrainingDiagnosticsTest(unittest.TestCase):
    def test_summarizes_successful_training(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = write_settings(root)
            console = root / "logs" / "kohya.log"
            console.parent.mkdir(parents=True)
            console.write_text("epoch 1/3 loss=0.82\nepoch 2/3 loss=0.55\nepoch 3/3 loss=0.41\n", encoding="utf-8")
            gpu = root / "logs" / "gpu.csv"
            gpu.write_text(
                "stage,timestamp,name,memory_used_mib,memory_total_mib,utilization_percent,temperature_c\n"
                "start,2026-08-25,NVIDIA RTX 3050,500,6144,10,40\n"
                "end,2026-08-25,NVIDIA RTX 3050,4300,6144,80,58\n",
                encoding="utf-8",
            )
            result_log = root / "logs" / "result.json"
            result_log.write_text(
                json.dumps(
                    {
                        "exit_code": 0,
                        "started_at": "a",
                        "ended_at": "b",
                        "console_log": str(console),
                        "gpu_log": str(gpu),
                    }
                ),
                encoding="utf-8",
            )

            result = analyze_training_run(settings, "sample_hero", result_log=result_log)
            payload = json.loads(result.manifest_path.read_text(encoding="utf-8"))

            self.assertEqual(result.status, "completed")
            self.assertEqual(payload["loss"]["trend"], "decreasing")
            self.assertEqual(payload["gpu"]["max_memory_used_mib"], 4300.0)
            self.assertEqual(payload["gpu"]["max_temperature_c"], 58.0)

    def test_detects_oom_nan_and_hot_gpu(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = write_settings(root)
            console = root / "kohya.log"
            console.write_text("epoch 1/3 loss=nan\nRuntimeError: CUDA out of memory\n", encoding="utf-8")
            gpu = root / "gpu.csv"
            gpu.write_text(
                "stage,timestamp,name,memory_used_mib,memory_total_mib,utilization_percent,temperature_c\n"
                "end,2026-08-25,NVIDIA RTX 3050,6100,6144,99,72\n",
                encoding="utf-8",
            )
            result_log = root / "result.json"
            result_log.write_text(json.dumps({"exit_code": 1}), encoding="utf-8")

            result = analyze_training_run(settings, "sample_hero", console, gpu, result_log)
            payload = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            codes = {item["code"] for item in payload["issues"]}

            self.assertEqual(result.status, "failed")
            self.assertIn("cuda_out_of_memory", codes)
            self.assertIn("nan_loss", codes)
            self.assertIn("gpu_temperature_high", codes)
            self.assertIn("nonzero_exit", codes)


def write_settings(root: Path):
    config = root / "config" / "local_6gb.json"
    config.parent.mkdir(parents=True)
    config.write_text(
        json.dumps(
            {
                "runtime": {"name": "test", "max_vram_gb": 6, "target_gpu_utilization": 0.8, "target_gpu_temp_c": 60},
                "assets": {"raw_dir": "assets/raw", "processed_dir": "assets/processed"},
                "datasets": {"lora_dir": "datasets/lora"},
                "models": {"wd14_dir": "models/wd14"},
                "asset_types": {"image_extensions": [".png"], "video_extensions": [".mp4"]},
            }
        ),
        encoding="utf-8",
    )
    return load_settings(config)


if __name__ == "__main__":
    unittest.main()
