from __future__ import annotations

import json
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from anime_studio.training_runner import run_kohya_training


class TrainingRunnerTests(TestCase):
    def make_settings(self, root: Path):
        from anime_studio.settings import load_settings
        config = root / "local_6gb.json"
        config.write_text(
            json.dumps(
                {
                    "runtime": {
                        "name": "test",
                        "max_vram_gb": 6,
                        "target_gpu_utilization": 90,
                        "target_gpu_temp_c": 85,
                    },
                    "assets": {"raw_dir": "assets/raw", "processed_dir": "assets/processed"},
                    "datasets": {"lora_dir": "datasets/lora"},
                    "models": {"wd14_dir": "models/wd14"},
                    "asset_types": {"image_extensions": [".png"], "video_extensions": [".mp4"]},
                }
            ),
            encoding="utf-8",
        )
        return load_settings(config)

    def test_requires_explicit_execute(self):
        root = Path(self._testMethodName)
        root.mkdir(exist_ok=True)
        try:
            settings = self.make_settings(root)
            with self.assertRaises(ValueError):
                run_kohya_training(settings, "sample", execute=False)
        finally:
            import shutil
            shutil.rmtree(root, ignore_errors=True)

    @patch("anime_studio.training_runner.subprocess.run")
    @patch("anime_studio.training_runner.check_training_readiness")
    def test_executes_run_script_after_readiness(self, readiness_mock, run_mock):
        root = Path(self._testMethodName)
        root.mkdir(exist_ok=True)
        try:
            settings = self.make_settings(root)
            script = root / "config" / "kohya" / "sample" / "run_train.ps1"
            script.parent.mkdir(parents=True)
            script.write_text("Write-Host test", encoding="utf-8")
            readiness_manifest = root / "manifests" / "training" / "sample" / "training_readiness.json"
            readiness_manifest.parent.mkdir(parents=True)
            readiness_mock.return_value = type("R", (), {"ready": True, "manifest_path": readiness_manifest})()
            run_mock.return_value.returncode = 0

            result = run_kohya_training(
                settings,
                "sample",
                execute=True,
                run_script=script,
            )

            self.assertEqual(result.status, "completed")
            run_mock.assert_called_once()
            payload = json.loads(result.result_manifest.read_text(encoding="utf-8"))
            self.assertEqual(payload["exit_code"], 0)
        finally:
            import shutil
            shutil.rmtree(root, ignore_errors=True)
