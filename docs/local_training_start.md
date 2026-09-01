# Local Training Start

Phase 7の編集handoffが安定した後、最初のローカルLoRA学習へ入るための手順です。
RTX 3050 6GB VRAMを前提に、いきなり長時間学習を回さず、まず「学習起動直前まで」を安全に確認します。

## 前提

- CharacterProfileが1人分ある。
- 学習用画像が `assets/processed/characters/<character_id>/sources/image/` または `frames/` にある。
- 自動タグ付け後に、必要なら `.tags.json` を手動修正できる。
- Kohya_ss / sd-scriptsの場所と、SD1.5系base modelの場所を把握している。
- 素材の作成者・ライセンス・学習利用可否を確認できる。

## 0. 素材利用権の確認

確認できた場合だけ、確認者名をCharacterProfileへ記録します。

```powershell
python -m anime_studio.cli character confirm-source-rights `
  --id sample_hero `
  --reviewer "自分の名前" `
  --notes "自作素材" `
  --confirm
```

未確認のままでもローカル生成テストはできますが、LoRA学習readinessは`source_rights_unconfirmed`で停止します。

## 1. 学習準備チェック

```powershell
python -m anime_studio.training_readiness readiness --character-id sample_hero
```

または統合CLI:

```powershell
python -m anime_studio.cli training readiness --character-id sample_hero
```

出力:

```text
manifests/training/sample_hero/training_readiness.json
```

このmanifestには、画像枚数、caption、tag record、dataset、Kohya設定の不足がまとまります。

## 2. Smoke workflow

1キャラだけで、次の処理を一気通しします。

1. baseline auto tag
2. final caption生成
3. LoRA dataset生成
4. Kohya低VRAMconfig生成
5. readiness再確認

```powershell
python -m anime_studio.training_readiness smoke `
  --character-id sample_hero `
  --pretrained-model C:\models\sd15.safetensors `
  --kohya-root C:\tools\kohya_ss `
  --min-images 1
```

統合CLI:

```powershell
python -m anime_studio.cli training smoke `
  --character-id sample_hero `
  --pretrained-model C:\models\sd15.safetensors `
  --kohya-root C:\tools\kohya_ss `
  --min-images 1
```

出力:

```text
manifests/training/sample_hero/sample_training_smoke.json
config/kohya/sample_hero/
datasets/lora/sample_hero/
```

このsmoke workflowは、Kohya学習そのものは起動しません。
生成された `run_train.ps1` を人間が確認してから、最初の短い学習を開始します。

新しく生成した`run_train.ps1`はconsole、GPU、終了コードを`outputs/logs/<character_id>/`へ保存します。終了後は`docs/training_diagnostics.md`の手順でOOM、NaN、loss、温度を確認します。

## 3. Video to Training Smoke

Phase 3.5 の入口として、動画読込から学習準備までを一気に通す workflow も使えます。

```powershell
python -m anime_studio.cli training video-smoke `
  --character-id sample_yonagi `
  --video assets/raw/sample_yonagi_scene01.mp4 `
  --pretrained-model C:\models\sd15.safetensors `
  --kohya-root C:\tools\sd-scripts `
  --fps 1.0 `
  --min-images 10 `
  --source-label "phase3 baseline"
```

この workflow では次をまとめて行います。

1. 動画を CharacterProfile に紐づけて登録
2. フレーム抽出
3. auto tag
4. final caption
5. dataset build
6. Kohya low-VRAM config
7. readiness check

出力:

```text
assets/processed/characters/sample_yonagi/sources/video/
assets/processed/characters/sample_yonagi/video_sources.json
assets/processed/characters/sample_yonagi/frames/<video_id>/
manifests/training/sample_yonagi/video_training_smoke.json
```

すでに同じ動画を登録済みなら `--reuse-import`、フレーム抽出を飛ばしたいなら `--skip-extract` を使えます。

## 4. 最初の推奨条件

- 画像枚数: 20〜50枚
- 解像度: 512
- batch size: 1
- network dim: 16
- network alpha: 8
- mixed precision: fp16
- optimizer: AdamW8bit
- epoch: 最初は短め

## 5. 開始前チェック

- `training_readiness.json` の `ready` が `true`
- 動画由来画像は`video_<video_id>_reviewed` datasetを使用している
- `dataset.toml`が同じreviewed datasetを参照している
- captionが空ではない
- trigger tagがcaptionに含まれている
- `dataset.toml` の画像フォルダが存在する
- `train_low_vram.toml` のbase model pathが正しい
- `run_train.ps1` のKohya pathが正しい

## 次に作る候補

- 複数LoRAの比較画像を同一seedで自動生成する。
- 学習停止条件と過学習候補の診断を追加する。
