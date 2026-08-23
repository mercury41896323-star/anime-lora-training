# 動画学習環境テストログ（2026-08-23）

## 目的

RTX 3050 6GB環境で、動画読込から解析、2.5D Definition、LoRA学習、AnimateDiffドラフト生成へ進むためのローカル環境を確認する。

## 確認環境

- OS: Windows 10
- GPU: NVIDIA GeForce RTX 3050 6GB
- Anime Studio Python: 3.10.11
- FFmpeg / FFprobe: 9.0
- ComfyUI: 0.33.3
- ComfyUI Python: 3.13.12
- ComfyUI PyTorch: 2.12.1+cu130
- Kohya sd-scripts PyTorch: 2.6.0+cu124
- Kohya CUDA: 利用可能
- Stable Diffusion 1.5 model: 配置確認済み

## ComfyUI / AnimateDiff確認結果

- ComfyUI API `http://127.0.0.1:8188`への接続に成功した。
- RTX 3050をCUDAデバイスとして認識した。
- `--lowvram --preview-method none --cache-none`で起動した。
- ComfyUI-AnimateDiff-Evolvedを導入し、AnimateDiff関連ノード143個を認識した。
- ComfyUI-VideoHelperSuiteと`VHS_VideoCombine`を認識した。
- Motion Module `mm_sd_v15_v2.ckpt`を認識した。
- SD1.5 checkpoint `sd15.safetensors`を認識した。
- Anime Studioの既定ComfyUI URLから接続できることを確認した。

## 動画学習パイプライン確認結果

以下のテストを実行した。

```text
tests/test_video_importer.py
tests/test_video_shot_pipeline.py
tests/test_video_analysis.py
tests/test_video_frame_cleaner.py
tests/test_video_training_pipeline.py
tests/test_video_domain_datasets.py
tests/test_character_sheet_draft.py
tests/test_character_sheet_importer.py
tests/test_motion_dataset.py
tests/test_neural_trainers.py
tests/test_domain_trainers.py
tests/test_kohya_config.py
```

結果:

```text
17 passed in 0.74s
```

実装上は次の工程を利用できる。

1. 動画をキャラクター素材として登録
2. シーン分割と一定fpsでのフレーム抽出
3. 低品質・文字入り・類似フレームの整理
4. 顔角度、表情、全身、背景、カメラ、ライティングの解析
5. Character Sheet Draft生成
6. reviewed / master画像の再取込
7. Character Master Asset生成
8. 2.5D Definition生成
9. キャラクターLoRA datasetとKohya低VRAM設定の生成
10. 学習readiness確認

## 現時点の制約

- リポジトリ内に実テスト用動画はなく、実動画によるEnd-to-Endテストは未実施。
- Anime Studioの通常venvにはPyTorchが未導入。そのためCamera AdapterとRelighting Providerの実学習には`requirements-neural.txt`の導入が必要。
- AnimateDiff EvolvedとMotion Moduleはドラフト動画の生成用。Motion Module自体の学習環境ではない。
- AnimateDiff Motion Module学習はRTX 3050 6GBの安全範囲を超えるため、現在のruntime profileでは停止する設計。
- Background LoRA本学習には、人間が確認した人物除去済み画像が必要。
- Character Sheetのreviewed / master判定は人間による確認が必要。

## 現在可能な学習

- キャラクターLoRA: 実行可能
- Background LoRA: 人物除去済みdatasetを用意すれば実行候補
- Camera Trajectory Adapter: PyTorch追加後に実行可能
- Relighting Provider: PyTorch追加後に実行可能
- AnimateDiff Motion Module: 設定生成のみ。6GB環境での本学習は対象外

## 次回の実データテスト

sample_yonagiは使用せず、新しい60〜300秒の動画を1本使用する。

1. 元動画を登録する。
2. Phase 3.5 pipelineを低い抽出fpsで実行する。
3. 抽出画像と解析manifestを確認する。
4. Character Sheet Draftを確認してreviewed / master画像を作る。
5. Character Master Assetと2.5D Definitionを生成する。
6. LoRA datasetとKohya設定を生成する。
7. readinessが`Ready: True`になることを確認する。
8. 少ないepochでキャラクターLoRAを試験学習する。
9. AnimateDiffで低解像度・短尺のドラフトShotを生成する。
10. 採用候補Shotを2.5D方式へ渡して同一性と動きを評価する。

## 判定

動画の登録・解析・2.5D・キャラクターLoRA学習へ進むための基本環境は準備済み。実動画を使ったEnd-to-End検証、Anime Studio通常venvへのPyTorch追加、各専用trainerの実データ検証は未完了。
