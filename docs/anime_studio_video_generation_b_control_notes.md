# Anime Studio Video Generation B-Control Notes

Date: 2026-08-16

このメモは、動画生成テストから見えた制約と、AI Anime Studio に **B-control** を導入する理由を整理したものです。

## 現時点の整理

これまでの短尺動画テストは、主に **A mode** で進めていました。

```text
A. still image generation + zoom / pan / cut
```

A mode でできること:

- LoRAベースの静止画生成
- FFmpegベースの動画化
- ズーム / パン / カットによるPV風編集
- ショット単位の簡易映像テスト

一方で、次のような自然な中割変化は弱いままでした。

```text
left angle
  ↓
intermediate
  ↓
front angle
```

## 判明した制約

- 単純なFFmpeg変形では顔向きや体の向きは変えられない
- txt2imgの複数枚生成だけでは角度制御が不安定
- 画像ブレンドでは本当の45度中割にならない
- img2img だけでは「角度変化」と「同一性維持」を両立しにくい

## 結論

自然なキャラクター動作には、prompt だけでなく **structured control data** が必要です。

そのため今後の動画生成は、A mode に加えて **B-control** を扱います。

```text
B. ControlNet / OpenPose / Reference / IPAdapter / AnimateDiff style control
```

## B-control が受け持つもの

- face direction
- body angle
- pose target
- motion continuity
- camera-work consistency
- lighting consistency
- reference image based identity preservation

## 現在の実装対応

この段階では、B-control の**軽量実装**として次を追加しました。

1. `storyboard export-comfyui --b-control`
   - Shot / Camera / Lighting / Motion cue / Selected Result をもとに
   - `b_control_manifest.json` を生成
   - ComfyUI workflow の `meta` と prompt に B-control 情報を差し込む

2. `manifests/storyboards/<story_id>/b_control_manifest.json`
   - shotごとの face direction
   - camera distance / angle
   - lighting direction
   - motion intents
   - reference images
   - OpenPose / IPAdapter / ControlNet / AnimateDiff 向け hint

3. `edit_timeline_manifest.json` への参照追加
   - Timeline側からも B-control manifest をたどれるようにする

## 実装上の位置づけ

いまの B-control は **最終的な ControlNet 実行エンジンそのもの** ではありません。

先に次を固定するための段階です。

- Shotごとの制御情報 schema
- ComfyUI export 時の metadata 受け渡し
- motion dataset との接続点
- 将来の Dashboard / Launcher から扱うための台帳

## 関連する manifest

- `ShotManifest`
- `b_control_manifest.json`
- `phase6_manifest.json`
- `motion_dataset_manifest.json`
- `edit_timeline_manifest.json`

## 次の強化候補

- 実ControlNetノードへの直接入力
- OpenPose guide画像の自動生成
- face turn transition 専用の中割生成workflow
- motion dataset と B-control を使った連続生成評価
