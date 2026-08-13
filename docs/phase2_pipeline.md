# Phase 2 Pipeline

Phase 2 connects character management, frame preparation, tagging, and LoRA dataset export.

This is still a lightweight local workflow. WD14 tagging is not bundled yet; the current tag step writes manual baseline captions so the dataset format can be tested before adding model-heavy dependencies.

## Minimal Flow

Create a character profile:

```powershell
python -m anime_studio.cli character init --id sample_hero --name "Sample Hero" --trigger-tag sample_hero
```

Register an image or video:

```powershell
python -m anime_studio.cli character register-asset --id sample_hero --source assets/raw/sample.png
```

Prepare caption sidecars:

```powershell
python -m anime_studio.cli tags --character-id sample_hero --extra-tag anime_style
```

Build a LoRA dataset:

```powershell
python -m anime_studio.cli dataset build-lora --character-id sample_hero
```

The generated dataset is written under:

```text
datasets/lora/sample_hero/
```

## WD14 Plan

The current tagger is intentionally dependency-free. A later WD14 module should replace or extend the caption sidecar step while keeping the same output format: one image file paired with one `.txt` caption file.
