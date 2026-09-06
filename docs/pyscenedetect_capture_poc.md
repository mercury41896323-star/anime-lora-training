# PySceneDetect Capture PoC

## 目的

動画をPySceneDetectでショット/シーン単位に解析し、各シーンから代表キャプチャーを保存して、後段のCapture Analyzer / Asset Library / Dataset Builderへ渡すための最小PoCです。

この段階ではAIタグ付けは行いません。manifest内に以下の空スロットを用意し、次の開発で自動解析結果を書き込めるようにしています。

- characters
- hair
- body
- arms
- clothes
- background
- motion

## セットアップ

既存の仮想環境を有効化したあと、PySceneDetect用の任意依存を追加します。

```powershell
pip install -r requirements-scene.txt
$env:PYTHONPATH = "src"
```

PySceneDetect 0.7系と0.6系の両方を想定した互換処理を最小限入れています。

## 実行

```powershell
python scripts/scene_capture_poc.py --video assets/raw/sample.mp4
```

代表画像を3枚ずつ保存して比較する場合:

```powershell
python scripts/scene_capture_poc.py --video assets/raw/sample.mp4 --images-per-scene 3
```

ContentDetectorの感度を変更する場合:

```powershell
python scripts/scene_capture_poc.py --video assets/raw/sample.mp4 --threshold 24
```

## 出力

デフォルト出力先:

```text
assets/processed/scene_captures/<video-stem>/
```

内容:

```text
scene_captures/<video-stem>/
├─ <video>-Scene-001-01.png
├─ <video>-Scene-002-01.png
├─ ...
└─ scene_capture_manifest.json
```

manifestには、元動画、検出設定、シーン数、開始/終了フレーム、タイムコード、長さ、キャプチャーパス、将来の解析タグ用フィールドを保存します。

## 次のPoC

1. キャプチャーの類似度/ブレ判定で学習候補を絞る
2. キャラクター候補を検出してcharacter_idへ紐づける
3. hair/body/arms/clothes/backgroundを自動タグ付けする
4. 同一シーン内の連続フレームからmotion候補を抽出する
5. 採用キャプチャーを既存Dataset Builder / Asset Libraryへ登録する
