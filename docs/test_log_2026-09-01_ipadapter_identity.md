# IPAdapter Identity実機テストログ 2026-09-01

## 対象環境

- GPU: NVIDIA GeForce RTX 3050 6GB
- ComfyUI: 0.33.4
- 起動: `--lowvram --preview-method none --cache-none`
- Checkpoint: SD1.5
- Character: `hiiragi_yukikaze`
- IPAdapter preset: `PLUS FACE (portraits)`
- IPAdapter weight: `0.55`

## 導入確認

- `ComfyUI_IPAdapter_plus` commit: `a0f451a5113cf9becb0847b92884cb10cbdec0ef`
- `IPAdapterUnifiedLoader`: 認識
- `IPAdapterAdvanced`: 認識
- `ip-adapter-plus-face_sd15.safetensors`: 認識
- `CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors`: 認識

## 1回目

- Prompt ID: `f464c1d2-85d6-4d1e-8e5d-5ff88e5c0adb`
- 結果: `success`
- 出力: `simple_2p5d/hiiragi_yukikaze_face_repaired_00003_.png`
- 最大VRAM: 5208 MiB
- 最大温度: 57℃
- 課題: 512x768全身ReferenceをIPAdapter側が中央正方形Cropした。

## 改善

Simple 2.5D Rigから、顔・髪・肩を含む512x512 `identity_reference.png`を自動生成するよう変更した。Reference LatentとFace Repairは従来の512x768全身Referenceを継続使用し、IPAdapterだけ正方形Identity Referenceを読む。

## 2回目

- Prompt ID: `5092a701-39bc-455e-9eb2-6ea8d1647e95`
- 結果: `success`
- 出力: `simple_2p5d/hiiragi_yukikaze_face_repaired_00004_.png`
- 実行時間: 20.77秒
- 最大VRAM: 5137 MiB
- 最大温度: 59℃
- 最大GPU使用率: 97%
- 中央Crop警告: なし
- 構図: 頭部・足先とも画面内
- 顔: 破綻なし

## 判定

RTX 3050 6GBで、LoRA + OpenPose + Depth + Reference Latent + IPAdapter Plus Face + 自動Face Repairを同時に実行できる。VRAMは6GB以内、温度は60℃未満で完走した。GPU使用率は瞬間的に目標80%を超えるため、連続生成時は温度と休止間隔を監視する。
