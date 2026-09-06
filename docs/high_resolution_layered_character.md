# High Resolution Layered Character Generator

`anime-highres-layered`は、Simple 2.5D Rigを高解像度のレイヤー素材へ作り直す補助パイプラインです。全身を一度に生成せず、パーツを最大768pxで順番に処理するため、RTX 3050 6GB環境でもVRAM使用量を抑えられます。

## 処理順序

1. 高解像度の正面全身画像を読み込む
2. 既存Rigの12パーツMaskから余白つきCropを作る
3. パーツごとのComfyUI API workflowを作る
4. 生成結果へMaskを適用して透明PNGにする
5. 2048x3072キャンバスへz-order順に合成する
6. パーツ境界へ元画像を使ったSeam Repairレイヤーを重ねる
7. 12パーツと`seam_repair`を含むCubism用PSDを出力する

## 準備

正面全身が大きく描かれた画像を別途用意します。推奨は`2048x3072`以上です。小さなキャラクターシートを拡大しても新しいディテールは増えません。

```powershell
anime-highres-layered prepare `
  --character-id chiyoko `
  --high-res-reference "C:\path\to\chiyoko_fullbody_2048x3072.png" `
  --comfyui-input-dir "$env:LOCALAPPDATA\Comfy-Desktop\ComfyUI-Shared\input" `
  --checkpoint "sd15.safetensors" `
  --lora-name "sample_chiyoko_lora.safetensors" `
  --trigger-tag "sample_chiyoko" `
  --enable-ipadapter
```

`high_resolution_layered/workflows`へ12個のworkflowが作られます。各workflowは同じLoRAと任意のIPAdapter参照を使い、対象パーツだけをInpaintします。IPAdapterは明示的に`--enable-ipadapter`を指定した場合だけ追加されます。

## ComfyUI生成結果

workflowを1つずつComfyUIへ送り、生成結果を次のフォルダへ保存します。

```text
assets/processed/characters/chiyoko/high_resolution_layered/generated
```

ファイル名は`face.png`のようなパーツID、またはComfyUI標準の`chiyoko_face_00001_.png`形式を使用できます。

## 合成とCubism PSD

```powershell
anime-highres-layered assemble --character-id chiyoko
```

出力:

- `layered_composite.png`: Seam Repair済みの高解像度合成
- `seam_repair_mask.png`: 修復対象となったパーツ境界
- `transparent_parts/*.png`: Mask適用済みの透明パーツ
- `chiyoko_highres_cubism.psd`: 12パーツとSeam Repairレイヤーを保持したPSD
- `layered_character_manifest.json`: workflow、Crop、配置、生成状態の管理情報

## Draftと品質判定

`prepare`直後にも元画像を使った`draft_layered_composite.png`と`draft_chiyoko_highres_cubism.psd`を生成します。これは接続確認用で、ComfyUIによる高精細化済み成果物ではありません。

元画像が目標解像度より小さい場合、manifestへ警告を記録します。Chiyokoの現在のRig参照は`512x768`のため、2048x3072出力は動作確認用です。本番品質には別途、高解像度の正面全身画像が必要です。

## 制約

- 完全に独立したパーツ生成ではなく、同じ全身参照をInpaintすることで体格・衣装・光源を揃えます。
- Seam Repairは元画像を境界へ合成する軽量方式です。大きく異なる生成結果では追加のInpaint確認が必要です。
- 腕と脚は現状一体型です。大きなポーズには上腕・前腕・手、太腿・膝下・足への追加分割が必要です。
