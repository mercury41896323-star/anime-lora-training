# Phase 3.5 Video To Training

Phase 3.5 の最初の実用ラインとして、**動画読込から LoRA 学習直前の readiness まで** を一気に通す smoke workflow を追加します。

このラインは、次の課題に対応するための入口です。

- `sample_yonagi` のような実機テストで、画像の手動登録効率が悪かった
- 動画から代表フレームを取り出して学習準備に流したい
- Character Sheet や 2.5D に進む前に、まず動画ベースの最小学習ラインを持ちたい

## できること

1. 動画を CharacterProfile に紐づけて登録
2. 動画からフレーム抽出
3. 抽出フレームに auto tag を付与
4. caption を生成
5. LoRA dataset を構築
6. Kohya low-VRAM config を生成
7. readiness を確認

まだ行わないこと:

- Shot Detector / Splitter
- 類似フレーム除外
- Character Sheet Draft Generator
- reviewed / master の再Import
- 2.5D 定義の生成

## 推奨コマンド

```powershell
anime-studio training video-smoke `
  --character-id sample_yonagi `
  --video assets/raw/sample_yonagi_scene01.mp4 `
  --pretrained-model C:\models\sd15.safetensors `
  --kohya-root C:\tools\sd-scripts `
  --fps 1.0 `
  --min-images 10 `
  --source-label "phase3 baseline"
```

console script を使う場合:

```powershell
anime-video-training `
  --character-id sample_yonagi `
  --video assets/raw/sample_yonagi_scene01.mp4 `
  --pretrained-model C:\models\sd15.safetensors `
  --kohya-root C:\tools\sd-scripts `
  --fps 1.0 `
  --min-images 10 `
  --source-label "phase3 baseline"
```

## 生成されるもの

```text
assets/processed/characters/<character_id>/sources/video/
assets/processed/characters/<character_id>/video_sources.json
assets/processed/characters/<character_id>/frames/<video_id>/
manifests/training/<character_id>/video_training_smoke.json
datasets/lora/<character_id>/
config/kohya/<character_id>/
manifests/training/<character_id>/training_readiness.json
```

## 再実行時のコツ

同じ動画を再利用したい場合は `--reuse-import` を付けます。

```powershell
anime-studio training video-smoke `
  --character-id sample_yonagi `
  --video assets/raw/sample_yonagi_scene01.mp4 `
  --pretrained-model C:\models\sd15.safetensors `
  --kohya-root C:\tools\sd-scripts `
  --reuse-import
```

すでにフレーム抽出済みで、タグ・dataset・Kohya 設定だけやり直したい場合は `--skip-extract` を付けます。

```powershell
anime-studio training video-smoke `
  --character-id sample_yonagi `
  --video assets/raw/sample_yonagi_scene01.mp4 `
  --pretrained-model C:\models\sd15.safetensors `
  --kohya-root C:\tools\sd-scripts `
  --reuse-import `
  --skip-extract
```

## 今の評価ポイント

この smoke workflow の評価は、まだ「動画生成品質」そのものではありません。
まずは次を見ます。

- 動画を CharacterProfile 配下で追跡できるか
- フレーム抽出から dataset まで止まらず進むか
- readiness が通るだけの画像枚数と caption を作れるか
- Phase 3 の画像登録方式より準備が早いか

## 次の実装候補

1. `video_sources.json` から Shot 分割対象を選択する
2. 類似フレーム除外を入れる
3. 顔角度 / 表情 / 全身の優先抽出を入れる
4. Character Sheet Draft Generator へつなぐ
5. Character Master Asset と 2.5D 定義へ進める
