# Chiyoko Live2D Semantic Head Correction Test

## Corrected Issues

- Replaced duplicate rectangular head layers with six pairwise-disjoint masks.
- Assigned `hair_back`, `head`, `face`, `eyes`, `mouth`, and `hair_front` to one `head_rotation` deformer.
- Moved the rotation pivot from the face center to the neck base without moving child ArtMeshes.
- Rebuilt the Cubism import PSD with Alpha-trimmed layers.

## Automated Verification

- Targeted tests: 3 passed
- Full test suite: 90 passed
- Dependency check: no broken requirements
- All six head masks are non-empty.
- Every pair of head masks has zero overlapping pixels.
- The union of all six masks exactly reconstructs the complete head region.
- `Warp_HairBack` and `Warp_Head` are direct children of `Rotation_Head` in the generated design.
- `Warp_Face`, `Warp_Eyes`, `Warp_Mouth`, and `Warp_HairFront` retain their intended nested hierarchy.

## Cubism Verification

- Editor: Live2D Cubism Editor 5.3.00 FREE
- Head hierarchy: six head parts under `head_rotation`
- Pivot: neck base
- Parameter: `ParamAngleZ`
- Keyforms: `-30 / 0 / 30`
- Observed angles: approximately `+11.7 / 0 / -12.4` degrees
- Body isolation: torso, arms, hips, and legs remain stationary during head rotation
- Saved model: `assets/processed/characters/chiyoko/simple_2p5d_rig/chiyoko_live2d_rig.cmo3`
- Saved model SHA256: `A335FEB6E162D4CF22868B326E8673DFAD3395A1683EA63E0963614C556A0E5F`
- Previous model backup: `assets/processed/characters/chiyoko/simple_2p5d_rig/chiyoko_live2d_rig.before_semantic_parts.cmo3`

## Evidence

- Separated parts: `docs/evidence/chiyoko_live2d_semantic_parts.png`
- Neutral hierarchy and pivot: `docs/evidence/chiyoko_live2d_semantic_head_neutral.png`
- Left rotation: `docs/evidence/chiyoko_live2d_semantic_head_left.png`
- Right rotation: `docs/evidence/chiyoko_live2d_semantic_head_right.png`
