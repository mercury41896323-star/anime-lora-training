# High Resolution Layered Character Generator Test

## Environment

- Character: `chiyoko`
- Target canvas: `2048x3072`
- Maximum per-part generation size: `768px`
- Strategy: sequential part generation for RTX 3050 6GB
- Identity control: optional IPAdapter Plus Face enabled for this preparation test

## Verified Outputs

- Part workflows: 12
- Draft composite: `2048x3072`
- Cubism PSD: `2048x3072`
- Cubism PSD layers: 13
- Layer composition: 12 character parts plus `seam_repair`
- Face workflow: LoRA, masked latent Inpaint, optional IPAdapter, and SaveImage nodes generated
- Live2D bridge: high-resolution layered manifest reference attached

## Automated Verification

- Targeted high-resolution layered tests: 3 passed
- Full regression suite: 93 passed
- Python dependency check: passed
- Transparent part import: passed
- z-order composite: passed
- Seam mask generation: passed
- Cubism PSD layer export: passed

## Live ComfyUI Retest

- ComfyUI API: online at `127.0.0.1:8188`
- GPU mode: RTX 3050 6GB / low VRAM
- Required nodes: Checkpoint, LoRA, masked latent, IPAdapter, and SaveImage recognized
- Required models: SD 1.5 checkpoint, Chiyoko LoRA, CLIP Vision, and IPAdapter Plus Face recognized
- Part generation: 12 of 12 completed successfully
- Final composite: `2048x3072`
- Cubism PSD: `2048x3072`, 13 layers
- Source fallback: none

## Quality Gate

The structural test passed, but the visual quality gate failed. The generated result is not approved for production or Cubism deformation work.

- The current Chiyoko Rig reference is only `512x768` and is enlarged to `2048x3072`.
- Face, eyes, and mouth remain soft and partially distorted because the source contains insufficient detail.
- Current arm, leg, torso, and skirt masks are coarse body zones rather than precise semantic part masks.
- Several generated parts contain neighboring body regions, causing gaps, overlap, and visible seams during assembly.
- White or colored edge contamination remains around some transparent parts.

Production retesting requires a standalone front full-body reference at approximately `2048x3072`, followed by accurate semantic masks and upper/lower limb separation. The manifest now stops at `assembled_pending_review`; assembly completion no longer implies visual approval.
