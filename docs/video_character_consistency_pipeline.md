# Video Character Consistency Pipeline

動画由来LoRAの品質とキャラクター同一性を上げるため、Phase 3.5の6工程を一本につなぎます。

## 実装した流れ

1. `anime-video-clean-frames` が sampled frame を読み、字幕が出やすい上端4%・下端18%を除外して512x512へCropします。
2. `anime-character-sheet-draft` が clean frame と顔角度・表情・全身分類を優先し、無文字の固定レイアウトDraft PNGを作ります。
3. `<video_id>_review.json` の確認項目に沿って人間が確認し、reviewed / master PNGを作ります。
4. `anime-character-master` がreviewed / masterを保存し、master sheetを固定領域へ分割してCharacter Master Assetを作ります。
5. `anime-character-2p5d` がCharacterProfileまたはMaster各領域の実画像パスを持つ2.5D Definitionを生成します。
6. readyな2.5D Definitionの後にだけ、補完用LoRA設定を生成します。
7. StoryboardのComfyUI exportで `--b-control` を付けると、2.5D Definitionのview anchor・identity referenceをworkflowと動画制御情報へ自動注入します。

## 一括実行

```powershell
anime-video-phase35 `
  --character-id your_character `
  --name "Your Character" `
  --video assets/raw/your_character_source.mp4 `
  --pretrained-model C:/Users/pfsgs/Documents/models/sd15/v1-5-pruned-emaonly.safetensors `
  --kohya-root C:/Users/pfsgs/Documents/sd-scripts `
  --requested-fps 2.0 `
  --target-max-frames 240 `
  --clean-width 512 `
  --clean-height 512 `
  --top-trim 0.04 `
  --bottom-trim 0.18
```

この実行ではraw抽出フレームからclean候補まで作りますが、Kohya設定はまだ生成しません。`anime-clean-frame-review`で採用したreviewed clean datasetと、reviewed/masterまたは外部画像によるreadyな2.5D Definitionがそろった後に生成します。

## 人間による確認

生成物:

```text
assets/processed/characters/<character_id>/character_sheet/draft/<video_id>_draft_sheet.png
manifests/characters/<character_id>/character_sheet/<video_id>_review.json
```

確認内容:

- 字幕、ロゴ、透かし、吹き出しが残っていない
- 顔、髪、衣装、体格が同一人物として安定している
- 正面、斜め、横顔、表情、全身の情報が矛盾していない
- 崩れ、遮蔽、別キャラクター混入のある画像を置き換えた

確認後、Draft PNGを画像編集ソフトで修正し、reviewedとmasterを作ります。Draft PNG自体にはラベル文字を描かないため、固定領域をそのまま再取込できます。

## reviewed / masterの登録

```powershell
anime-character-master `
  --character-id your_character `
  --video-id your_video_id `
  --reviewed-image assets/processed/characters/your_character/character_sheet/reviewed/your_character_reviewed.png `
  --master-image assets/processed/characters/your_character/character_sheet/master/your_character_master.png `
  --notes "identity and text review complete"

anime-character-2p5d --character-id your_character
```

## 生成・動画制御へ渡す

StoryboardのShotに同じ `character_id` を設定し、B-control exportを実行します。

```powershell
anime-studio storyboard export-comfyui `
  --story-id your_story `
  --b-control
```

出力workflowには次が追加されます。

- Shotの顔向きに合う2.5D view anchor
- Character Master由来のidentity reference images
- IP-Adapter用の参照画像一覧
- ControlNet / camera / lighting情報
- AnimateDiff等へ渡す `video_control` 定義

## 品質上の注意

`anime-video-clean-frames` は軽量なsafe-area Cropと文字系タグ除外です。OCRで完全保証する処理ではないため、manifestの `ocr_verified` は `false` のままです。学習開始前の目視確認は必須です。
