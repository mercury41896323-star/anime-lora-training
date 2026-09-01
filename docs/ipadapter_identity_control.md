# IPAdapter Identity Control

Simple 2.5D workflowは、LoRA・OpenPose・Depth・Reference Latent・Face Repairに加えて、任意でIPAdapter Plus Faceを使用できます。IPAdapterを使わない既存workflowはそのまま動作します。

## 目的

- LoRAだけでは崩れやすい髪型、輪郭、目元、配色を参照画像から補強する。
- 2.5DのPose / Depth制御と、キャラクター同一性制御を分離する。
- RTX 3050 6GBではFaceID / InsightFaceを避け、ComfyUIのlowvram offloadを使う。
- 最終段では承認済みReferenceのFace Repairを残し、顔の破綻を抑える。

## 必要なComfyUI構成

1. `ComfyUI/custom_nodes/ComfyUI_IPAdapter_plus`
2. `models/clip_vision/CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors`
3. `models/ipadapter/ip-adapter-plus-face_sd15.safetensors`
4. ComfyUIの再起動

Comfy Desktopの標準配置なら、次のスクリプトで取得できます。CLIP Visionが約2.5GBあるため、完了まで待ってから再起動してください。

```powershell
.\scripts\setup_comfyui_ipadapter.ps1
```

モデル名はUnified Loaderが検出できる公式名を使用します。FaceIDモデルと`insightface`はこの軽量構成では不要です。

## 有効化

既存のSimple 2.5D rigを保ったままworkflowだけ更新します。

```powershell
anime-simple-2p5d-manage refresh-workflow `
  --character-id hiiragi_yukikaze `
  --comfyui-input-dir "$env:LOCALAPPDATA\Comfy-Desktop\ComfyUI-Shared\input" `
  --enable-ipadapter `
  --ipadapter-weight 0.55
```

`IPAdapterUnifiedLoader`をLoRAの後へ、`IPAdapterAdvanced`をKSamplerの前へ挿入します。既定presetは`PLUS FACE (portraits)`、weightは`0.55`、適用終了は`0.85`です。

Simple 2.5D Rigは全身Referenceとは別に、顔・髪・肩を含む512x512 `identity_reference.png`を自動生成します。IPAdapterだけがこの正方形画像を使うため、CLIP Visionの中央Cropで顔が外れる問題を避けます。

## 無効化

```powershell
anime-simple-2p5d-manage refresh-workflow `
  --character-id hiiragi_yukikaze `
  --comfyui-input-dir "$env:LOCALAPPDATA\Comfy-Desktop\ComfyUI-Shared\input" `
  --no-enable-ipadapter
```

## 6GB VRAM向け調整

- 最初はweight `0.45`〜`0.60`で確認する。
- ポーズが参照画像へ引っ張られすぎる場合はweightを下げる。
- identityが弱い場合はweightを少し上げ、LoRA強度は一度に変更しない。
- OOM時はComfyUIを`--lowvram --preview-method none --cache-none`で起動し、他のGPUアプリを終了する。
- Face Repairは最後に承認済み顔を合成するため、IPAdapterと併用しても残す。

`anime-studio status --open`は、IPAdapter入りworkflowが存在する場合だけ拡張Nodeと2つのモデルを必須項目として確認します。

RTX 3050 6GB実機結果は`docs/test_log_2026-09-01_ipadapter_identity.md`を参照してください。
