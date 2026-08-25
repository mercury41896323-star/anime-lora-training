# Simple 2.5Dローカル生成テストログ（2026-08-25）

## 目的

Character Sheetから生成したCrop、Mask、Depth、Poseと既存LoRAを使い、RTX 3050 6GB環境でComfyUI API workflowを実行できることを確認する。全身の頭部・足先が画面内に収まり、人間承認後に生成readinessが通ることも確認する。

## 確認環境

- OS: Windows 10
- GPU: NVIDIA GeForce RTX 3050 6GB
- ComfyUI: 0.33.4
- ComfyUI Python: 3.13.12
- ComfyUI PyTorch: 2.12.1+cu130
- 起動設定: `--lowvram --preview-method none --cache-none`
- Checkpoint: `sd15.safetensors`
- LoRA: `sample_hiiragi_lora.safetensors`
- ControlNet: OpenPose FP16 + Depth FP16

## 対象

- Character ID: `hiiragi_yukikaze`
- Character Sheet: `柊雪.png`
- 解像度: 512x768
- Sampling: 20 steps、DPM++ 2M Karras、CFG 6.5

## 構図補正

最初の生成では全身Cropが縦方向いっぱいに伸び、頭部が画面外へ切れた。次の補正を追加した。

1. 正面全身の前景bboxを抽出する。
2. 512x768キャンバスへ中央配置する。
3. 頭上約8%、足元にも安全余白を確保する。
4. 正条件へ単独、全身、頭部・足先表示を追加する。
5. 負条件へ複数人物、複製、キャラクターシート、画面外Cropを追加する。
6. OpenPose強度を1.0、Depth強度を0.65へ調整する。
7. 512x768と上下左右5%以上の余白を自動承認条件にする。

## 実行結果

- ComfyUI APIへのworkflow投入: 成功
- 最終Prompt ID: `09f196f5-eb1b-4e07-ad72-c7880d66af15`
- ComfyUI状態: `success`
- 最終出力: `simple_2p5d/hiiragi_yukikaze_00003_.png`
- 単独キャラクター: 確認
- 頭部表示: 確認
- 足先表示: 確認
- 512x768 Pose / Depth / Mask: 確認

関連テスト:

```text
tests.test_simple_2p5d_rig
tests.test_simple_2p5d_management

Ran 2 tests
OK
```

## ReviewとReadiness

- Review status: `approved`
- Reviewer: `pfsgs`
- Readiness: `True`
- Issues: 0
- Warning: source rights未確認

## 現時点の制約

- PoseとDepthは決定論的な簡易Draftであり、DWPoseや学習済みDepth推定ほど正確ではない。
- 単独全身構図は改善したが、衣装、顔、背景の完全一致はLoRA品質と追加identity controlに依存する。
- 承認は現在のRig署名に対して有効。Master、Definition、Rigを再生成すると再承認が必要になる。
- 学習や配布へ進む前に、Character SheetとLoRA素材の利用権を確認する。

## 判定

Simple 2.5D Rig Pipelineは、RTX 3050 6GB環境でCharacter Sheet読込からControlNet補助画像、ComfyUI API生成、人間承認、最終readinessまで実行可能。次の品質改善はReference/IP-Adapter等のidentity control追加、または専用LoRA再学習で行う。
