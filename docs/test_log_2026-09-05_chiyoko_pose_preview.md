# Chiyoko Static Posing Test

## Scope

- Character: `chiyoko`
- Source: corrected 12-part Simple 2.5D Rig
- Test type: static part rotation before Cubism body keyform authoring
- Canvas: `512x768`

## Generated Poses

- `relaxed_standing`: small body, head, shoulder, hip, and leg rotations
- `small_step`: conservative walking offset within the current one-piece limb limits
- Machine-readable rotations are stored in `live2d_adjustment.json` and `live2d_bridge.json`.

## Result

- Head parts move together around the corrected neck pivot.
- Torso, arms, hips, and legs follow the intended parent transform chain.
- `relaxed_standing` is usable as a low-motion draft.
- The original wide `small_step` test exposed visible gaps at the shoulders, skirt, and hip boundaries.
- The stored `small_step` preset was reduced to conservative angles and now serves as a safe-limit test.

## Current Limit

The source rig has one ArtMesh per whole arm and whole leg. Large gestures cannot bend elbows or knees and expose seams because hidden joint-overlap artwork does not exist. Production posing therefore requires upper/lower limb separation, shoulder and hip overlap layers, and Cubism Warp Deformer refinement.

## Verification

- Targeted Live2D adjustment test: passed
- Full test suite: 90 passed
- Both pose previews generated at `512x768`
- Visual review: low-angle pose passed; wide-angle pose rejected and reduced
