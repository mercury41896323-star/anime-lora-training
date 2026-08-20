# Phase 3.5 Character Bootstrap And Video Analysis

Phase 3.5 の次の実装として、次の4つを前へ進めました。

- 動画読込
- 学習解析
- アセット / シーケンスの作成
- キャラクタープロフィールの作成

この段階では、まだ 2.5D の自動定義生成までは行いません。
ただし、その前段として必要な **動画素材 -> 解析結果 -> learning asset candidate -> sequence / storyboard draft** の流れを作ります。

## 1. Character Bootstrap

動画を入口にして、CharacterProfile を新規作成または更新できます。

```powershell
anime-character-bootstrap `
  --character-id sample_yonagi `
  --name "Sample Yonagi" `
  --video assets/raw/episode01.mp4 `
  --trigger-tag sample_yonagi `
  --source-label "episode01" `
  --source-notes "long-form reference clip"
```

生成されるもの:

```text
assets/processed/characters/<character_id>/profile.json
assets/processed/characters/<character_id>/video_sources.json
manifests/characters/<character_id>/character_bootstrap.json
```

役割:

- CharacterProfile を作る
- 既存 profile があれば source note を追記する
- 動画を Source Asset として紐づける

## 2. Video Analysis

フレーム抽出済み動画から、学習解析結果を作ります。

```powershell
anime-video-analysis `
  --character-id sample_yonagi `
  --video assets/raw/episode01.mp4 `
  --fps 1.0 `
  --sequence-seconds 12 `
  --sample-every 3 `
  --source-label "episode01"
```

まだフレームがない場合は `--auto-extract` を付けられます。

```powershell
anime-video-analysis `
  --character-id sample_yonagi `
  --video assets/raw/episode01.mp4 `
  --fps 1.0 `
  --sequence-seconds 12 `
  --sample-every 3 `
  --source-label "episode01" `
  --auto-extract
```

生成されるもの:

```text
manifests/characters/<character_id>/video_analysis/<video_id>_analysis.json
manifests/characters/<character_id>/video_analysis/<video_id>_sequences.json
manifests/characters/<character_id>/video_analysis/<video_id>_learning_assets.json
storyboards/<story_id>/storyboard.json
```

## 3. 何を解析しているか

この段階の解析は、まだ AI による画像理解ではありません。

今は軽量に次を作ります。

- 一定秒数ごとの sequence bucket
- 各 sequence の start / middle / end keyframe
- 一定間隔の sampled learning frame
- sequence ごとの storyboard draft

つまり、

```text
動画
↓
フレーム列
↓
sequence 分割
↓
keyframe / sampled frame
↓
learning asset candidate
↓
storyboard draft
```

までをつなげています。

## 4. 現時点の制約

- Shot Detector / Splitter はまだ未実装
- sequence は現状「一定秒数ごと」の仮分割
- 類似フレーム除外はまだ未実装
- 顔角度 / 表情 / 全身の画像理解分類はまだ未実装
- Character Sheet Draft Generator はまだ未実装
- 2.5D 定義の自動生成はまだ未実装

## 5. 次に進む順番

1. 60〜300秒動画で Character Bootstrap を行う
2. `video-smoke` で学習準備まで通す
3. `video-analysis` で sequence / learning asset を作る
4. Shot Detector / Splitter を実装する
5. 類似フレーム除外つき Frame Sampler を入れる
6. Character Sheet Draft Generator へ進む
7. Character Master Asset と 2.5D 定義へ進む
