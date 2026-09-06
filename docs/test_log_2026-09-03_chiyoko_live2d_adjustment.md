# Chiyoko Live2D Adjustment Package Test

> This initial test has been superseded by the semantic head correction in
> `docs/test_log_2026-09-05_chiyoko_live2d_semantic_head.md`. In the current
> model, `hair_back` is also inside `head_rotation`, and all six head parts use
> non-overlapping masks.

## Environment

- Character: `chiyoko`
- Source: approved Simple 2.5D Rig
- Canvas: `512x768`
- Live2D Cubism Editor: `5.3.00` FREE版
- GPU: NVIDIA GeForce RTX 3050 6GB
- Cubism OpenGL renderer: `NVIDIA GeForce RTX 3050/PCIe/SSE2`

## Generated Package

- ArtMesh guides: 12
- Rotation / Warp deformers: 20
- Parameter bindings: 8
- Pivot preview: `assets/processed/characters/chiyoko/simple_2p5d_rig/live2d_adjustment_preview.png`
- Adjustment manifest: `assets/processed/characters/chiyoko/simple_2p5d_rig/live2d_adjustment.json`
- Updated bridge: `assets/processed/characters/chiyoko/simple_2p5d_rig/live2d_bridge.json`
- Cubism import PSD: `assets/processed/characters/chiyoko/simple_2p5d_rig/chiyoko_live2d_import.psd`
- Saved Cubism model: `assets/processed/characters/chiyoko/simple_2p5d_rig/chiyoko_live2d_rig.cmo3`

## Pivot Review

- Head rotation: neck base
- Left / right arm rotation: shoulder joints
- Body rotation: upper torso
- Hip rotation: pelvis center
- Left / right leg rotation: hip joints
- Mesh density: higher for hair, face, eyes, mouth, dress body, arms, and legs than the original two-triangle draft

## Result

- CLI generation: passed
- Preview rendering: passed
- JSON overrides for later pivot and mesh-density changes: supported
- Cubism import package status: `cubism_import_package_ready`
- Cubism PSD import: passed, 12 ArtMesh layers recognized and rendered
- Head rotation deformer: passed, `eyes` / `mouth` / `hair_front` / `face` / `head` grouped as children
- Body isolation at this revision: passed, `right_arm` / `left_arm` / `torso` / `hips` / `right_leg` / `left_leg` / `hair_back` remain outside the head deformer; the later semantic correction moves `hair_back` inside `head_rotation`
- Head crop correction: passed, `head` Alpha bounds are `(197, 61, 298, 169)` and `torso` starts at `y=168`; the collar remains with the body instead of the rotating head
- PSD layer trim: passed, each Cubism layer uses its Alpha bounding box instead of the full `512x768` canvas
- Parameter binding: passed, standard `ParamAngleZ` keyforms at `-30.0` / `0.0` / `30.0` drive deformer angles `-12.0` / `0.0` / `12.0` degrees
- Actual deformation: passed, the head alone rotates at `12.0` degrees while the torso and collar remain stationary
- Neutral-state save: passed, `ParamAngleZ` and deformer angle returned to `0.0`; `.cmo3` saved as 415,744 bytes
- Save verification: passed, Cubism log recorded `Verify after save : SUCCESS` at `2026-09-04 20:14:44 JST`
- Rotation evidence: `docs/evidence/chiyoko_live2d_head_rotation_12deg.png`
- Neutral hierarchy evidence: `docs/evidence/chiyoko_live2d_head_hierarchy_neutral.png`
- ArtMesh bounds evidence: `docs/evidence/chiyoko_live2d_head_artmesh_bounds.png`

## Runtime Findings

- The first launch selected the Intel UHD Graphics OpenGL renderer and failed with `GL_OUT_OF_MEMORY` during repeated rendering.
- Windows graphics preference was set to high performance for `CubismEditor5.exe`, bundled `java.exe`, and bundled `javaw.exe`.
- After restarting, the Cubism log confirmed the NVIDIA RTX 3050 renderer and the same model completed import, deformation, and save successfully.
- A PSD written with `pytoshop` exposed layer names but rendered blank in Cubism. The compatible test PSD was rebuilt with `psd-tools 1.19.0` using RGBA pixel layers without layer masks.
- Full-canvas PSD layers caused Cubism to create oversized ArtMeshes even when PNG Alpha was correct. The exporter now crops each PSD layer to its Alpha bounds and restores the original canvas position with layer offsets.

## Remaining Manual Work

The `.cmo3` draft now contains a working head rotation axis and standard `ParamAngleZ` keyforms. Remaining manual work is to refine vertices around hair tips and the dress hem, set clipping, add eye and mouth deformation, and export `.moc3` after animation checks.
