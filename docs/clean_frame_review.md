# Clean Frame Review

動画から自動抽出・Cropした画像を、LoRA学習へ入れる前に人が確認する工程です。

## 1. 確認画面を作る

Phase 3.5実行後に表示された`video_id`を指定します。

```powershell
anime-clean-frame-review prepare `
  --character-id sample_yonagi `
  --video-id episode01 `
  --open
```

ブラウザーへ番号付き画像一覧が表示されます。顔崩れ、文字、透かし、別キャラクター、強い遮蔽がある画像は採用しません。

## 2. 採用画像を確定する

採用するFrame番号だけを指定します。連番は`5-8`のように書けます。

```powershell
anime-clean-frame-review finalize `
  --character-id sample_yonagi `
  --video-id episode01 `
  --accept "1,3,5-8" `
  --reviewer "自分の名前" `
  --notes "文字なし、顔と全身を確認" `
  --confirm
```

出力:

```text
datasets/lora/sample_yonagi/video_episode01_reviewed/
manifests/characters/sample_yonagi/video_analysis/episode01_clean_frame_review.json
```

## 3. Kohya設定を再生成する

Kohya設定のdataset pathは、必ず`video_<video_id>_reviewed`を指定して再生成します。readinessは、未確認datasetや別datasetを参照する古いKohya設定を停止します。

```powershell
anime-studio lora kohya-config `
  --character-id sample_yonagi `
  --pretrained-model "C:\Users\pfsgs\Documents\models\sd15\v1-5-pruned-emaonly.safetensors" `
  --kohya-root "C:\Users\pfsgs\Documents\sd-scripts" `
  --dataset-dir "datasets\lora\sample_yonagi\video_episode01_reviewed" `
  --require-2p5d
```

続いて同じdatasetを指定してtraining readinessを確認します。

```powershell
anime-studio training readiness `
  --character-id sample_yonagi `
  --dataset-dir "datasets\lora\sample_yonagi\video_episode01_reviewed" `
  --require-2p5d `
  --min-images 20
```

この工程は画像内容の自動採点ではありません。最終採用は人が行い、確認者と時刻をmanifestへ残します。
