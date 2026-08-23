# Phase 3.5 Video Pipeline

60〜300秒の動画をそのまま扱うための **Phase 3.5 end-to-end pipeline** を追加しました。

この段階の目的は、動画をまとめて取り込み、学習準備・Shot分割・重複除外・分類・Character Sheet下書きまでを一気に通せるようにすることです。

## 1. できること

`anime-video-phase35` は次を順番に実行します。

1. 動画を CharacterProfile に紐づける
2. 動画から一定 fps でフレーム抽出する
3. 抽出フレームをタグ付けして画像解析する
4. Shot Detector / Splitter を行う
5. 類似フレーム除外つき Frame Sampler を行う
6. 顔角度 / 表情 / 全身の分類を行う
7. 字幕safe-area Cropと文字系タグ除外でclean frame datasetを作る
8. 実体PNGつきCharacter Sheet Draftとreview checklistを生成する
9. reviewed / master があれば再取込する
10. CharacterProfileまたはCharacter Master Assetから2.5D Definitionを生成する
11. character・motion・camera・background・lighting datasetを保存する
12. readyな2.5D Definitionがある場合だけKohya低VRAM設定を生成する
13. readiness を確認する
14. B-control export時にDefinitionを生成・動画制御へ渡す

## 2. 60〜300秒動画への最適化

この段階では、重い動画をそのまま処理しやすくするために次を入れています。

- `ffprobe` があれば動画長を読む
- `target_max_frames` を超えないように `effective_fps` を自動で下げる
- 長すぎるShotを避けるために `max_shot_seconds` で仮分割する
- Shot単位で代表フレームを選び、重複寄りのフレームを落とす
- sampled frame 専用の軽量 dataset を別に書き出す
- clean frame datasetだけを最終Kohya設定へ渡す
- 2.5D Definition完成前は最終Kohya設定を生成しない

## 3. 実行例

```powershell
anime-video-phase35 `
  --character-id sample_yonagi `
  --name "Sample Yonagi" `
  --video assets/raw/episode01.mp4 `
  --pretrained-model C:/Users/pfsgs/Documents/models/sd15/v1-5-pruned-emaonly.safetensors `
  --kohya-root C:/Users/pfsgs/Documents/sd-scripts `
  --requested-fps 2.0 `
  --target-max-frames 240 `
  --provider baseline `
  --source-label "episode01"
```

reviewed / master まで続ける場合:

```powershell
anime-video-phase35 `
  --character-id sample_yonagi `
  --name "Sample Yonagi" `
  --video assets/raw/episode01.mp4 `
  --pretrained-model C:/Users/pfsgs/Documents/models/sd15/v1-5-pruned-emaonly.safetensors `
  --kohya-root C:/Users/pfsgs/Documents/sd-scripts `
  --reviewed-image assets/raw/reviewed_sheet.png `
  --master-image assets/raw/master_sheet.png
```

## 4. 個別コマンド

- `anime-video-shot detect`
- `anime-video-shot sample`
- `anime-video-shot classify`
- `anime-character-sheet-draft`
- `anime-video-clean-frames`
- `anime-video-domain-datasets`
- `anime-character-master`
- `anime-character-2p5d`

## 5. 生成される主な manifest

```text
manifests/characters/<character_id>/phase3_5_video_pipeline.json
manifests/characters/<character_id>/video_analysis/<video_id>_shots.json
manifests/characters/<character_id>/video_analysis/<video_id>_sampled_frames.json
manifests/characters/<character_id>/video_analysis/<video_id>_classifications.json
manifests/characters/<character_id>/video_analysis/<video_id>_clean_frames.json
manifests/characters/<character_id>/character_sheet/<video_id>_draft.json
manifests/characters/<character_id>/character_sheet/<video_id>_review.json
manifests/characters/<character_id>/character_sheet/<video_id>_completeness.json
manifests/characters/<character_id>/character_sheet/character_master_asset.json
manifests/characters/<character_id>/character_2p5d_definition.json
datasets/video_learning/<character_id>/<video_id>/video_learning_bundle.json
```

## 6. いまの制約

- Shot分割は軽量な tag / duration ベースの仮実装
- 顔角度 / 表情 / 全身分類は heuristic ルールベース
- 2.5D Definition は実画像anchorを持つcontrol manifestであり、rigそのものではない
- reviewed / master の品質判断は人間前提
- 文字除外はsafe-area Cropとタグ除外であり、OCR完全保証ではない
- motion / camera / background / lighting はdataset保存までで、専用trainerは未実装

## 7. 次の強化候補

- 画像内容ベースの Shot boundary 精度向上
- WD14や外部分類器と連動した分類精度向上
- OCR providerの追加と中央字幕・看板文字の自動検出
- Character Master Asset からの Dataset Builder v2
