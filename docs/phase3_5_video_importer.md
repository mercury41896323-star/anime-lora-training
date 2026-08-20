# Phase 3.5 Video Importer

Phase 3.5 の最初の薄い実装として、動画をキャラクター単位で取り込む入口を追加します。

この段階ではまだ Shot 分割や Character Sheet 生成は行いません。
まずは **動画を CharacterProfile に紐づく Source Asset として安全に保管し、後続処理の台帳を作る** ことに集中します。

## 目的

- `sample_yonagi` のような実機テスト結果を、画像単位ではなく動画単位でも管理できるようにする
- Shot Detector / Frame Sampler / Character Sheet Draft Generator の前段に、安定した入力台帳を置く
- Phase 3 の LoRA 学習結果と、Phase 3.5 の動画解析素材を同じ CharacterProfile 配下で追跡できるようにする

## 追加されたもの

- `src/anime_studio/video_importer.py`
- `tests/test_video_importer.py`
- `anime-video-import` console script

## 使い方

```powershell
anime-video-import --character-id sample_yonagi --source assets/raw/sample_yonagi_scene01.mp4 --source-label "phase3 baseline"
```

または module 直実行:

```powershell
python -m anime_studio.video_importer --character-id sample_yonagi --source assets/raw/sample_yonagi_scene01.mp4 --source-label "phase3 baseline"
```

## 出力

動画本体は次へコピーされます。

```text
assets/processed/characters/sample_yonagi/sources/video/
```

動画台帳は次へ保存されます。

```text
assets/processed/characters/sample_yonagi/video_sources.json
```

manifest には次を記録します。

- `video_id`
- 元動画パス
- 保存先パス
- source label
- size bytes
- `shot_detection`, `frame_sampling`, `character_sheet` の pending 状態

## 再利用

同じ動画で再実行したい場合は `--reuse-existing` を使えます。

```powershell
anime-video-import --character-id sample_yonagi --source assets/raw/sample_yonagi_scene01.mp4 --source-label "phase3 baseline" --reuse-existing
```

## この次のライン

Video Importer だけで止めず、そのまま **動画読込から学習準備まで** を通したい場合は `training video-smoke` を使います。

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

詳しくは `docs/phase3_5_video_to_training.md` を参照してください。

## 現時点の制約

- FFprobe による duration / fps / codec 取得はまだ未実装
- Shot 分割はまだ未実装
- フレーム抽出はまだ一定fpsの単純抽出
- 類似フレーム除外はまだ未実装
- Character Sheet Draft 生成はまだ未実装

## 次の実装候補

1. `video_sources.json` から Shot 分割対象を選ぶ CLI
2. 軽量な Shot Detector / Splitter
3. Shot 単位の代表フレーム抽出
4. Character Sheet Draft Generator の最小テンプレート
5. 類似フレーム除外と顔角度優先抽出
