# Chiyoko Bernini-R 1.3B Low-VRAM Test Log

## Scope

- Character: `chiyoko`
- GPU: NVIDIA GeForce RTX 3050 6GB
- System RAM: 32GB
- Renderer: `bernini_r_1.3B-Q4_K_M.gguf`
- Text encoder: `umt5-xxl-encoder-Q5_K_M.gguf`
- VAE: `wan_2.1_vae.safetensors`
- Output profile: 512 x 320, 12 fps, 16 steps, CPU VAE

## Result

- ComfyUI prompt ID: `f7119010-a59b-4651-acb3-bd2657bc03fe`
- AnimeStudio queue job: `segment_001-08410562`
- Queue status: `completed`
- ComfyUI execution time: 143.45 seconds
- Output: H.264 MP4, 512 x 320, 12 fps, 13 frames, 1.083 seconds
- Result import: one video imported into the Chiyoko character asset registry
- Final CPU assembly: H.264 MP4, 512 x 320, 12 fps, 12 frames, exactly 1.000 seconds
- GPU out-of-memory error: none

The selected Character Master portrait remained recognizable in the inspected middle frame. This is a technical smoke-test pass, not final motion or composition approval.

## Windows note

The first launch used the default CP932 console and a non-ASCII custom-node log message terminated the worker. Relaunching ComfyUI with `PYTHONUTF8=1` and `PYTHONIOENCODING=utf-8` resolved the issue.

## Evidence paths

- Generation plan: `outputs/comfyui/bernini/bernini_chiyoko_smoke/shot_001/bernini_low_vram_plan.json`
- Imported results: `assets/processed/characters/chiyoko/generated/comfyui/segment_001-08410562/results.json`
- Preview frame: `outputs/comfyui/bernini/bernini_chiyoko_smoke/shot_001/preview_frame.png`
- Final video: `outputs/comfyui/bernini/bernini_chiyoko_smoke/shot_001/final_trimmed.mp4`
- Assembly manifest: `outputs/comfyui/bernini/bernini_chiyoko_smoke/shot_001/bernini_assembly.json`
