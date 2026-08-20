# Character Sheet Importer + Dataset Builder v2

Phase 3.5 の次段として、`future_video_character_sheet_pipeline.md` にあった **Character Sheet Importer** と **Dataset Builder v2** の初期実装を追加しました。

## 1. 追加されたコマンド

### Character Sheet Importer

```powershell
anime-character-sheet-import `
  --character-id sample_yonagi `
  --source assets/raw/sample_yonagi_sheet.png `
  --label sample_yonagi_sheet_v1 `
  --display-name "Sample Yonagi"
```

このコマンドは次を行います。

- CharacterProfile が無ければ作成する
- 設定シート画像を `character_sheet/source/<sheet_id>/` へ取り込む
- Template v1 の固定領域で crop する
- 各 crop に `.tags.json` と `.txt` を付ける
- `*_import.json` manifest を書く

### Dataset Builder v2

```powershell
anime-dataset-builder-v2 `
  --character-id sample_yonagi `
  --video-id scene01 `
  --sheet-id sample_yonagi_sheet_v1
```

このコマンドは次を使って、用途別 dataset を出力します。

- imported character sheet regions
- reviewed / master character sheet
- sampled / classified video frames

## 2. Template v1 の考え方

Template v1 は **軽量で固定領域ベース** の importer です。

自動で高精度に領域検出するのではなく、次のような標準配置を前提に、最初の運用ラインを作ります。

- Main Portrait
- Turnaround Front / Side / Back
- Face Angle Front / 45 / Side
- Expressions
- Pose Reference
- Color Palette
- Character Metadata

必要なら `--template-json` で normalized crop region を差し替えできます。

## 3. Dataset Builder v2 が出すもの

初期実装では次の4系統を出します。

- `character`
- `expression`
- `shot`
- `direction`

出力先:

```text
datasets/v2/<character_id>/character/
datasets/v2/<character_id>/expression/
datasets/v2/<character_id>/shot/
datasets/v2/<character_id>/direction/
```

各 dataset には次が入ります。

- `images/`
- `manifest.json`
- 各画像の `.txt` caption

## 4. 現時点の制約

- Character Sheet Importer は fixed template crop の軽量版
- 自動 crop 精度は sheet レイアウトに依存する
- Dataset Builder v2 の `motion` dataset はまだ未実装
- video sample の分類は Phase 3.5 の heuristic classifier 依存

## 5. 推奨の使い方

1. `anime-video-phase35` で動画側の初期解析を通す
2. `anime-character-sheet-import` で設定シートを取り込む
3. reviewed / master を `anime-character-master` へ入れる
4. `anime-dataset-builder-v2` で用途別 dataset を作る
5. その後に Character consistency 改善用の再学習や 2.5D 制御へ進む