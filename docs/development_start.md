# Development Start

This repository starts with a small, local-first Python prototype before adding heavy AI integrations.

## Initial Scope

- Keep RTX 3050 6GB VRAM as the baseline.
- Prefer SD 1.5-era settings, 512px drafts, batch size 1, and fp16 defaults.
- Avoid requiring GPU access for project-management commands.
- Treat `assets/raw` as the input area and `assets/processed` as generated output.

## First Prototype

The first executable tool scans `assets/raw` and writes an inventory JSON file to `assets/processed/inventory.json`.

```powershell
.\scripts\run_inventory.ps1
```

This gives the project a minimal working loop:

1. Place images or videos in `assets/raw`.
2. Run the inventory script.
3. Confirm that lightweight project metadata appears in `assets/processed`.

## Near-Term Next Steps

- Expand frame extraction with FFmpeg/OpenCV quality controls.
- Add validation for character profile fields.
- Add WD14 tagging as an optional module.
- Add Kohya_ss config generation for low-VRAM LoRA training.
