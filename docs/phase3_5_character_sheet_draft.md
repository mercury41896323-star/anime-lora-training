# Phase 3.5 Character Sheet Draft

Phase 3.5 の次の小ステップとして、`video-analysis` の結果から **Character Sheet の下書き** を出せるようにしました。

この機能は、まだ完成版のキャラクターシートを自動生成するものではありません。
今は **候補フレームの整理** と **不足領域の見える化** に集中しています。

## 1. できること

`anime-character-sheet-draft` は、次の2つの manifest を読みます。

- `video_analysis/<video_id>_sequences.json`
- `video_analysis/<video_id>_learning_assets.json`

そこから、次の情報を持つ draft を生成します。

- Main Portrait 候補
- Face Angles 候補
- Expressions 候補
- Full Body / Pose 候補
- 不足している section の一覧
- sequence reference 一覧
- Completeness manifest

## 2. 使い方

先に `video-analysis` を通しておきます。

```powershell
anime-video-analysis `
  --character-id sample_yonagi `
  --video assets/raw/episode01.mp4 `
  --fps 1.0 `
  --sequence-seconds 12 `
  --sample-every 3 `
  --source-label "episode01"
```

そのあとで draft を作ります。

```powershell
anime-character-sheet-draft `
  --character-id sample_yonagi `
  --video-id episode01
```

候補数を増減したい場合:

```powershell
anime-character-sheet-draft `
  --character-id sample_yonagi `
  --video-id episode01 `
  --max-face-angles 8 `
  --max-expression-frames 8 `
  --max-full-body-frames 10
```

## 3. 生成されるもの

```text
manifests/characters/<character_id>/character_sheet/<video_id>_draft.json
manifests/characters/<character_id>/character_sheet/<video_id>_completeness.json
```

## 4. 何が入るか

### draft

- section ごとの候補 frame
- frame の source sequence
- timestamp
- なぜ候補に選ばれたかの簡単な理由
- sequence 参照一覧

### completeness

- required section の ready 数
- section ごとの status
- 次にやるべき review 作業
- Phase 3.5 のこの段階で ready 扱いにできるか

## 5. いまの制約

- 顔向き・表情・全身 / バストアップ分類は heuristic のため、人間の確認が必要
- Back View / Costume Detail / Hair Detail / Color Palette は自動で埋めない
- 外部レビュー後の画像は `anime-character-master` で reviewed / masterとして再取込可能

## 6. この機能の意味

この段階の目的は、

```text
動画
↓
フレーム抽出
↓
sequence / learning asset
↓
character sheet draft
↓
missing section の把握
```

までをつなげることです。

これで、60〜300秒動画を使ったときに

- どのフレームが identity 基準に使えそうか
- どの角度や表情が不足しているか
- 次に Shot Detector / Classifier / 外部補正のどこを入れるべきか

を判断しやすくなります。
