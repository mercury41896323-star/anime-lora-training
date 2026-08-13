# Phase 3 LoRA Training Configs

Phase 3の最初の実装では、Kohya_ss / sd-scriptsでLoRA学習を始める前に確認できる、低VRAM向け設定ファイル生成を追加します。

この段階では学習処理そのものは自動起動しません。RTX 3050 6GB VRAM環境で安全に進めるため、まず設定、データセット、実行コマンドをファイルとして出力し、人間が確認してから実行します。

## Generate Configs

キャラクター素材を登録し、タグを生成・調整したあとで次を実行します。

```powershell
python -m anime_studio.cli lora kohya-config --character-id sample_hero --pretrained-model models/sd15.safetensors --kohya-root C:/tools/sd-scripts
```

生成されるファイル:

```text
config/kohya/sample_hero/dataset.toml
config/kohya/sample_hero/train_low_vram.toml
config/kohya/sample_hero/run_train.ps1
```

`dataset.toml`は学習画像フォルダ、caption拡張子、bucket設定、repeats、batch sizeを管理します。

`train_low_vram.toml`はこのプロジェクト側で確認するための設定メモです。実際のsd-scripts実行に渡すコマンド引数もJSON文字列として保存します。

`run_train.ps1`はPowerShellから手動実行するためのラッパーです。

## Low-VRAM Defaults

- Stable Diffusion 1.5系を想定
- 解像度は512
- batch sizeは1
- mixed precisionはfp16
- LoRA rankは16、alphaは8
- optimizerはAdamW8bit
- schedulerはconstant
- latent cacheを有効化
- gradient checkpointingを有効化
- sdpaを有効化

## Before Training

実行前に次を確認します。

- `--pretrained-model`が実在するモデルパス、または利用可能なモデルIDを指している
- `dataset.toml`の`image_dir`に学習画像が入っている
- `.txt` captionに不要タグや誤タグが残っていない
- `output_dir`と`logging_dir`の保存先が意図通り
- 6GB VRAMで不安定な場合は`network_dim`、`resolution`、`epochs`を下げる

## Next Step

次は、生成済みLoRA設定と学習結果をCharacterProfileへ紐づける管理ファイルを追加します。
