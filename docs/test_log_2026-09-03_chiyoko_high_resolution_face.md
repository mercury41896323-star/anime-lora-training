# Chiyoko High-Resolution Face Reference Test

## Input

- Character id: `chiyoko`
- Display name: `Chiyoko`
- Character sheet: `百城千世子.jpg`
- Identity source: `sample_chiyoko011~028.png`
- Identity crop: `0,0.04,0.166667,0.333333`（表情11、見出し文字を除外）
- LoRA: `sample_chiyoko_lora.safetensors`
- ControlNet: SD1.5 OpenPose FP16 + Depth FP16
- Identity control: IPAdapter Plus Face, weight `0.55`
- Runtime: RTX 3050 6GB, LOW_VRAM

## Result

- 35 character-sheet regions: generated
- Simple 2.5D rig parts: 12
- High-resolution identity reference: generated
- Aligned face repair reference: generated
- ComfyUI prompt id: `209fc229-3fbd-49ce-80f4-9184e5963b0f`
- Output: `simple_2p5d/chiyoko_face_repaired_00003_.png`
- ComfyUI execution: success
- Execution time: 17.61 seconds
- Head and feet framing: passed
- Face and hair identity: improved over the full-body-only reference
- Shoulder seam after mask adjustment: resolved
- Source rights: confirmed by `pfsgs`
- Rig review: `approved`
- Generation readiness: `True`, issues `0`

## Notes

The source-rights record reflects the user's explicit confirmation for the attached Chiyoko material. The generated data, source copies, manifests, queue state, and images remain ignored by Git.
