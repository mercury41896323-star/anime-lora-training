# Bernini-R 1.3B Low-VRAM Generation

## Purpose

This path animates an approved AnimeStudio character reference with Bernini-R 1.3B while keeping peak GPU use suitable for the RTX 3050 6GB target. It is an opt-in video renderer and does not replace the existing SD1.5 LoRA, Simple 2.5D, or AnimateDiff paths.

## Hybrid production order

1. Build and review the CharacterProfile, Character Sheet, Character Master Asset, and Simple 2.5D definition.
2. Use SD1.5 LoRA and 2.5D controls to prepare a high-quality approved identity frame when necessary.
3. Animate the approved frame with Bernini-R 1.3B Q4 in short sequential segments.
4. Import each generated video segment back into the character asset registry.
5. Concatenate and trim the segments to the requested duration.
6. Run interpolation, per-frame upscale, face repair, and final editing as separate jobs.

The SD1.5 LoRA cannot be loaded directly into the Wan2.1-based Bernini renderer. Its role is to improve the reference frame and other reusable character assets before video generation.

## Safe 6GB profile

The default profile in `config/local_6gb.json` uses:

- Bernini-R 1.3B Q4 renderer
- UMT5 Q5 GGUF text encoder
- 512 x 320 output
- 12 fps
- 16 sampling steps
- 1.25-second generation segments
- one segment at a time
- CPU VAE with 256-pixel spatial tiles and 8-frame temporal tiles
- a 30-second hard limit per Shot

The output may be slightly longer than requested because compatible frame counts are rounded up. The plan records the exact requested duration so the final combined video can be trimmed accurately.

## Export a Shot

The Shot must have a `character_id`. AnimeStudio selects the preferred identity image from the Character 2.5D Definition or Character Master Asset and copies a prepared version into the ComfyUI input folder.

```powershell
anime-studio comfyui export-bernini `
  --story-id pilot_scene `
  --shot-id shot_001 `
  --duration 10 `
  --queue
```

The command writes one API workflow per short segment plus `bernini_low_vram_plan.json`. The configured maximum can only be lowered from the command line:

```powershell
anime-studio comfyui export-bernini `
  --story-id pilot_scene `
  --shot-id shot_001 `
  --duration 8 `
  --max-duration 10
```

After every queued segment is complete, refresh and import its result. Then join the imported videos and trim the final file to the exact requested duration with CPU FFmpeg processing:

```powershell
anime-studio comfyui assemble-bernini `
  --plan outputs/comfyui/bernini/pilot_scene/shot_001/bernini_low_vram_plan.json
```

The default final file is `final_trimmed.mp4` next to the plan. This stage does not load an AI model or consume significant VRAM.

## Required ComfyUI components

- `ComfyUI-BerniniR`
- `ComfyUI-GGUF`
- `bernini_r_1.3B-Q4_K_M.gguf`
- `umt5-xxl-encoder-Q5_K_M.gguf`
- `wan_2.1_vae.safetensors`

Recommended ComfyUI startup arguments are recorded in `config/local_6gb.json`. If the safe profile still runs out of memory, use ComfyUI `--novram` as a fallback and shorten the segment duration before increasing resolution.

On Japanese Windows, set UTF-8 mode before launching ComfyUI. This prevents a custom-node log message from terminating a worker when the console uses CP932:

```powershell
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
python main.py --listen 127.0.0.1 --port 8188 `
  --cpu-vae --cache-none --disable-smart-memory `
  --reserve-vram 0.75 --preview-method none
```

## Quality limitations

- Short segments reduce peak memory but can introduce visual drift at boundaries.
- Bernini-R 1.3B is less capable than the 14B model on complex human motion.
- Upscaling improves delivery resolution but does not restore details absent from the generated frames.
- Every segment needs visual review before it is adopted as a Shot result.
- The RTX 3050 6GB smoke test is recorded in `docs/test_log_2026-09-06_chiyoko_bernini_low_vram.md`.
