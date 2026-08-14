# Local Training Start

Phase 7の編集handoffが安定した後、最初のローカルLoRA学習へ入るための手順です。
RTX 3050 6GB VRAMを前提に、いきなり長時間学習を回さず、まず「学習起動直前まで」を安全に確認します。

## 前提

- CharacterProfileが1人分ある。
- 学習用画像が `assets/processed/characters/<character_id>/sources/image/` または `frames/` にある。
- 自動タグ付け後に、必要なら `.tags.json` を手動修正できる。
- Kohya_ss / sd-scriptsの場所と、SD1.5系base modelの場所を把握している。

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

## 3. 最初の推奨条件

- 画像枚数: 20〜50枚
- 解像度: 512
- batch size: 1
- network dim: 16
- network alpha: 8
- mixed precision: fp16
- optimizer: AdamW8bit
- epoch: 最初は短め

## 4. 開始前チェック

- `training_readiness.json` の `ready` が `true`
- captionが空ではない
- trigger tagがcaptionに含まれている
- `dataset.toml` の画像フォルダが存在する
- `train_low_vram.toml` のbase model pathが正しい
- `run_train.ps1` のKohya pathが正しい

## 次に作る候補

- 学習ログをCharacterProfileへ自動紐づけする。
- 最初のサンプル生成結果をLoRA artifactへ記録する。
- 失敗時のVRAM/設定診断を追加する。
