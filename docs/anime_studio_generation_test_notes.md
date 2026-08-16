# Anime Studio LoRA Generation Test Notes

Date: 2026-08-16

This note records the current ComfyUI generation test results for the Anime Studio / anime-lora-training project.

## Current test environment

- Project: `anime-lora-training`
- ComfyUI Desktop is running locally at `http://127.0.0.1:8188`
- ComfyUI Desktop model folder used in this test:
  - Checkpoints: `%LOCALAPPDATA%/Comfy-Desktop/ComfyUI-Shared/models/checkpoints`
  - LoRAs: `%LOCALAPPDATA%/Comfy-Desktop/ComfyUI-Shared/models/loras`
  - Output: `%LOCALAPPDATA%/Comfy-Desktop/ComfyUI-Shared/output/anime_studio/<character_id>`
- Checkpoint recognized by ComfyUI:
  - `sd15.safetensors`
- LoRAs recognized by ComfyUI:
  - `sample_yonagi_lora.safetensors`
  - `sample_akira_lora.safetensors`
  - `sample_chiyoko_lora.safetensors`
  - `sample_hiiragi_lora.safetensors`

## Important workflow finding

The API workflow exported as `sd15_lora_txt2img_512_with_lora.json` failed when submitted directly to ComfyUI because the top-level `meta` field was included.

Temporary workaround:

1. Export the workflow with `anime-studio comfyui export-workflow --character-id <character_id>`.
2. Remove the top-level `meta` field.
3. Save as `sd15_lora_txt2img_512_with_lora_api_clean.json`.
4. Submit the clean JSON with `anime-studio comfyui queue-submit`.

Future improvement:

- `queue-submit` should automatically strip non-node metadata before sending to ComfyUI, or `export-workflow` should avoid writing `meta` into API-submitted workflow JSON.

## Character generation results

### sample_yonagi

Result:

- Character likeness appeared.
- Hair, color, and face atmosphere were close to the training data.
- No major image collapse.
- Some text-like artifacts and watermark-like traces remained.

Assessment:

- Character reproduction is mostly successful.
- Main issue is text / watermark artifact handling.

Future improvement:

- Use WD14 or another analysis step to detect tags such as `text`, `watermark`, `signature`, `logo`, and `letters`.
- Filter or flag source images with visible text/watermarks before training.
- Add optional cleanup or inpaint workflow for text/watermark residue.

### sample_akira

Result:

- Color reproduction was acceptable.
- Design reproduction was weak compared with the training data.
- Increasing LoRA strength caused larger visual collapse.
- Lowering LoRA strength improved stability slightly but still did not fully match the training data.

Assessment:

- `sample_akira` appears to be a character-specific training/caption quality issue rather than a global pipeline failure.
- Prompt tuning alone is probably not enough.

Likely causes:

- Training images may have too much variation.
- Captions may not describe character-specific design features strongly enough.
- Some inconsistent or low-quality images may be mixed into the dataset.
- The LoRA may contain unstable character information: enough to affect color, but not enough to stabilize design.

Future improvement:

- Review `sample_akira` source images.
- Remove images with inconsistent design, poor quality, visible text, watermark, or unwanted background influence.
- Add better tags for hair, eyes, face shape, clothing, and distinctive character features.
- Rebuild captions with WD14 plus manual correction.
- Retrain and test LoRA strength in the 0.65 to 0.85 range.

### sample_chiyoko

Result:

- Design and color were good.
- Output was close to the training data.
- Mouth shape needed prompt control.
- Adding `closed mouth`, `gentle expression`, and smile-related prompts improved the result.

Assessment:

- `sample_chiyoko` is a successful or near-successful character.
- Remaining issues are mostly expression-level prompt control, not dataset-level failure.

Useful prompts tested:

- `sample_chiyoko, sample_chiyoko, 1girl, upper body, simple background, looking at viewer, closed mouth, gentle expression`
- `sample_chiyoko, sample_chiyoko, 1girl, bust up, head fully visible, simple background, looking at viewer, closed mouth, natural smile, gentle expression`
- `sample_chiyoko, sample_chiyoko, 1girl, bust up, head fully visible, simple background, looking at viewer, closed mouth, soft smile, cheerful expression`
- `sample_chiyoko, sample_chiyoko, 1girl, bust up, head fully visible, simple background, looking at viewer, closed mouth, elegant smile, calm expression`

### sample_hiiragi

Result:

- Best reproduction among the tested characters.
- High similarity to training data.
- Low collapse.
- Color and design were both stable.

Assessment:

- `sample_hiiragi` should be treated as the current success baseline character.
- Use it as a reference when testing future workflow changes.

## Overall conclusion

The Anime Studio LoRA training and ComfyUI generation flow works.

The current character quality ranking from this test is:

1. `sample_hiiragi` - best reproduction, least collapse
2. `sample_chiyoko` - good reproduction, expression tuning needed
3. `sample_yonagi` - good character reproduction, text/watermark artifacts remain
4. `sample_akira` - color is close, but design reproduction is weak and unstable

This suggests that the pipeline itself is functioning, but output quality strongly depends on each character dataset and caption quality.

## Future system improvements

Priority improvements for Anime Studio:

1. Add ComfyUI UI workflow export
   - Current API workflow is hard for beginners to understand.
   - Need a visible node-based workflow for ComfyUI drag-and-drop use.

2. Clean API workflow submission
   - Remove or ignore top-level `meta` before submitting to ComfyUI.

3. Add WD14 tagging pipeline
   - Use WD14 to detect hair, eyes, clothing, expression, pose, and unwanted tags.
   - Add manual tag correction.
   - Use final captions for better LoRA training.

4. Add text/watermark detection
   - Detect `text`, `watermark`, `signature`, `logo`, `letters`, and related artifacts.
   - Exclude or flag those images before training.

5. Add character quality report
   - After training, generate a simple report per character:
     - dataset image count
     - caption count
     - suspicious tags
     - LoRA generation test status
     - reproduction score notes

6. Revisit `sample_akira`
   - Treat as a dataset/caption improvement target.
   - Rebuild captions and retrain after WD14/manual tag improvements.

---

## 追加メモ: Anime Studio 開発順位と将来設計

Date: 2026-08-16 update

この章は、今後の `anime-lora-training` / `AI Anime Studio` の開発優先順位と、画像自動学習・動画学習・統合UI化の設計メモを整理したもの。

## 開発順位

現時点の優先順位は以下とする。

1. **WD14 tags auto の本格実装**
   - 現在の `baseline tags auto` は正常に動作しているが、ファイル名ベースの簡易タグ付けである。
   - 次段階では、WD14で画像内容から髪色・髪型・服装・表情などをタグ化する。

2. **Video Analysis Pipeline**
   - 動画ファイルからフレームを抽出し、キャラクター・表情・ポーズ・カメラワーク・ライティング・ショット構造を解析する。
   - 解析結果を `CharacterProfile` / `Dataset` / `ShotManifest` に反映する。

3. **AI Anime Studio Launcher / Dashboard**
   - コマンドを打たなくても操作できる画面を作る。
   - 複数のツールに分かれている操作を、最終的には1つの画面で扱えるようにする。

## 画像自動学習: 現状と実装したい方向

現状の `auto tag` はファイル名からのタグ付けになっている。

### baseline tags auto（現状）

- ファイル名ベース。
- 正常に動作している。
- ただし、髪色・髪型・服装・表情などの画像内容は見ていないため、簡易版として扱う。

### wd14 tags auto（実装したい）

- 画像内容ベース。
- 髪色・髪型・服装・表情などを画像から推定してタグ化する。
- 学習データのcaption品質を上げるための中核機能にする。

## タグ付けパイプライン（実装イメージ）

```text
キャラクター画像
  │
  ▼
Tag Provider
  │
  ├─ baseline
  │   └─ ファイル名ベース
  │
  ├─ WD14
  │   └─ 髪色・髪型・服装・表情などを画像から推定
  │
  └─ manual
      └─ 人間が追加・修正
  │
  ▼
.tags.json
  │
  ▼
.txt caption
```

### タグの役割

- `auto_tags`
  - AIが付けたタグ。
  - baselineまたはWD14などのTag Providerで生成する。

- `manual_tags`
  - 人が追加したタグ。
  - キャラクター固有の特徴や、AIが見落とした特徴を補う。

- `rejected_tags`
  - 消したいタグ。
  - 誤検出されたタグや、学習に入れたくないタグを除外する。

- `final_tags`
  - 学習に使う最終タグ。
  - `auto_tags`、`manual_tags`、`rejected_tags` を反映してcaptionに出力する。

## 動画学習機能未実装: Video Analysis Pipeline

現状では、動画から演出・ショット・動きの特徴を学習する本格的な `Video Analysis Pipeline` は未実装。

実装イメージは以下。

```text
動画ファイル
assets/raw/video
  │
  ▼
FFmpeg Frame Extraction
動画から画像を切り出す
  │
  ▼
Frame Selection
使えるフレームを選ぶ
  │
  ▼
Video Analysis
  │
  ├─ キャラクター検出
  ├─ 表情検出
  ├─ ポーズ検出
  ├─ カメラワーク解析
  ├─ ライティング解析
  └─ ショット構造解析
  │
  ▼
VideoAnalysisManifest
  │
  ▼
CharacterProfile / Dataset / ShotManifest に反映
```

### Video Analysis Pipeline の目的

- 動画から使えるフレームを自動抽出する。
- キャラクター単位で学習素材を整理する。
- 表情・ポーズ・構図・カメラワーク・ライティングを解析する。
- 画像学習だけでなく、将来的なショット提案・動画生成・編集支援につなげる。

## 動画生成機能の最小実装メモ

動画生成機能は未実装または最小限の検討段階。

最小実装では、まず以下のようなコマ送り動画に近い形から始める案がある。

1. 画像生成でキーフレームを作る。
2. 複数のキーフレームを並べる。
3. 必要に応じて補間・簡易モーションを加える。
4. FFmpegで短い動画として出力する。

未整理の論点:

- コマの生成をどの単位で行うか。
- 同一キャラの一貫性をどう保つか。
- 画像生成結果を動画化するときに、ちらつきや破綻をどう抑えるか。
- 将来的にComfyUI、動画生成モデル、Unity Timelineのどれを主軸にするか。

## 画面表示用UI・パッケージ化の将来設計

最終的には、現在のようにPowerShellや複数ツールを行き来する状態ではなく、AI Anime Studioの画面から一通り操作できる形を目指す。

```text
ユーザー
  │
  ▼
AI Anime Studio UI
人が操作する画面
  │
  ├─ キャラ登録
  ├─ 画像登録
  ├─ 動画登録
  ├─ タグ確認
  ├─ LoRA学習
  ├─ 画像生成
  ├─ 動画生成
  ├─ 編集
  └─ 出力
  │
  ▼
内部データ層 A
機械が処理しやすい共通データ
  │
  ├─ CharacterProfile
  ├─ AssetManifest
  ├─ TagManifest
  ├─ DatasetManifest
  ├─ TrainingManifest
  ├─ LoRAManifest
  ├─ GenerationManifest
  ├─ VideoManifest
  └─ EditTimelineManifest
  │
  ▼
外部ツール連携
  │
  ├─ sd-scripts / Kohya_ss
  ├─ ComfyUI
  ├─ FFmpeg
  ├─ WD14
  ├─ Video Analysis
  └─ Unity / Timeline
```

### 設計方針

- **内部データ層 A** を本体にする。
  - `CharacterProfile`、`DatasetManifest`、`LoRAManifest` など、機械が処理しやすい共通データで管理する。

- **画面表示用UI** は、内部データを人間が理解しやすく操作するための見える化レイヤーにする。
  - 例: ComfyUI UI workflow、将来のAI Anime Studio Dashboard。

- ComfyUI、Kohya_ss、FFmpeg、WD14、Unityなどは外部ツール連携として扱う。
  - AI Anime Studioは、それらをまとめて操作する司令塔にする。

### UI化で優先したい操作

1. キャラクター登録。
2. 画像・動画素材の登録。
3. 自動タグ付けと手動タグ修正。
4. LoRA学習。
5. ComfyUIでの画像生成。
6. 動画生成・編集。
7. 最終出力。

## 次回以降の実装候補まとめ

次回以降は以下を順番に進める。

1. `wd14 tags auto` の本格実装。
2. text / watermark / logo 検出と学習データ除外。
3. `export-workflow` または `queue-submit` の `meta` 自動除去。
4. ComfyUI画面表示用 `export-ui-workflow`。
5. `sample_akira` のデータ・caption見直しと再学習。
6. `Video Analysis Pipeline`。
7. `AI Anime Studio Launcher / Dashboard`。
