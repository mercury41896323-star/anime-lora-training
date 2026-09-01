# Anime Studio Completion Audit Test Log

Date: 2026-08-25

## 対象

- Simple 2.5D Face Repair
- Studio Status Dashboard
- Dataset Builder v2 motion dataset
- Phase 3.5 end-to-end video pipeline
- Storyboard B-control / Simple 2.5D workflow連携
- ComfyUI Queue完了・失敗判定
- 学習用素材の利用権gate
- Kohya console / GPU / 終了コードdiagnostics

## 実機環境

- Python 3.10.11
- NVIDIA GeForce RTX 3050 6GB
- ComfyUI 0.33.4
- ComfyUI API: `http://127.0.0.1:8188`
- FFmpeg / FFprobe検出済み

## 検証結果

### 全自動テスト

```text
Ran 89 tests in 13.363s
OK
```

### Phase 3.5統合テスト

FFmpegで3秒の合成MP4を作り、次を一本で実行した。

1. CharacterProfile作成と動画登録
2. FFprobeと適応fps
3. フレーム抽出、タグ、Shot分割、類似除外
4. 顔角度・表情・構図分類
5. clean crop dataset
6. Character Sheet Draft
7. reviewed / master取込
8. 2.5D Definition
9. 5領域dataset
10. Kohya低VRAM設定
11. training readiness

初回は人間確認gateにより`ready = false`となることを確認した。その後、全候補をテスト用reviewerが採用し、reviewed dataset向けKohya設定を再生成すると`ready = true`になった。合成動画はテスト終了時に削除され、リポジトリへ残らない。

### ComfyUI Queue実機確認

送信済みJobを一括更新した。

```text
Refreshed: 5 / Failed: 0
```

模擬ComfyUI APIでは、正常履歴を`completed`、`execution_error`を`failed`としてNode番号と本文を保存できることを確認した。

### Studio Status実機確認

```text
Overall: operational
Blocking: 0
Warnings: 1
```

GPU、ComfyUI、Git、FFmpeg、FFprobeはready。`hiiragi_yukikaze`はSimple 2.5D生成とFace Repairが可能。残るwarningはLoRA学習画像と素材利用権の確認。

Simple 2.5D workflowに必要なComfyUI Nodeに加え、IPAdapter入りworkflowでは拡張Nodeと2つのモデルも検出する。2026-09-01にIPAdapter Plus Faceを導入し、Reference Latent + OpenPose + Depth + IPAdapter + Face Repairの同時生成をRTX 3050 6GBで完走した。

### Face Repair実機確認

- Prompt ID: `f1a40047-4a6c-4db2-9600-751dd495ce72`
- Output: `simple_2p5d/hiiragi_yukikaze_face_repaired_00002_.png`
- 承認済みReferenceと顔Maskを使い、ControlNet生成後に自動合成されることを確認した。

## 追加した安全策

- 古いDataset Builder v2画像を再実行時に除去し、学習混入を防止
- ComfyUI実行エラーを完了扱いしない
- B-control ShotはreadyなSimple 2.5D workflowを自動採用
- 通常結果とFace Repair結果を別名保存
- 学習用素材の利用権が未確認ならtraining readinessを停止
- clean frame未確認、またはKohya設定が別datasetを参照している場合はtraining readinessを停止
- CharacterProfileへ確認者、確認時刻、メモを保存
- `run_train.ps1`からconsole、GPU、終了結果を自動保存し、OOM / NaN / 高温 / loss傾向を診断
- IPAdapter用512x512 Identity Referenceを自動生成し、縦長全身Referenceの中央Cropを回避

## 現在の残課題

- 実写・アニメ本番動画60〜300秒でのPhase 3.5品質評価
- 本番60〜300秒動画でのClean Frame採用作業と画像品質評価
- AnimateDiff / Background LoRA等の外部ニューラル学習実行と品質比較
- 実Storyboardを使った複数Shot連続生成、採用、Timeline出力の実機評価

現時点で停止要因はなく、ローカル生成を継続可能。LoRA再学習は素材利用権確認と20枚以上のreview済み画像を用意した後に行う。

IPAdapter実機値とPrompt IDは`docs/test_log_2026-09-01_ipadapter_identity.md`を参照する。
