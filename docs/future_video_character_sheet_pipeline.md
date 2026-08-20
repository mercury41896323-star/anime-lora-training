# 将来改修案: Character Sheet / Video Analysis Pipeline

> 状態: **一部実装済み / 将来改修継続**
>
> この文書は、実キャラクター生成テストで得られた課題を踏まえて、AI Anime Studio の次期改修方針を整理した設計メモです。
>
> 2026年8月20日時点では、Video Importer / Shot Detector / Frame Sampler / Asset Classifier / Character Sheet Draft / reviewed-master 再取込 / 2.5D Definition に加えて、**Character Sheet Importer** と **Dataset Builder v2 の初期実装**が追加されています。将来改修として残っている中心課題は、高精度な Character Sheet region detection、motion dataset、より強い shot boundary 判定、高精度分類です。

## 背景

現在のキャラクター生成フローでは、画像を1枚ずつ登録し、タグ付け・Dataset化・LoRA学習へ進む方式を中心にしています。

実キャラクター生成テストの結果、この方式は次の点で効率が悪いことが分かりました。

- 学習素材の登録作業が多い
- 似た画像を大量に管理しやすい
- キャラクター設定画に含まれる複数の情報を1枚の画像としてしか扱えない
- 動画素材をキャラクター、モーション、Shot、演出へ横断的に再利用できていない
- LoRAがシステムの中心になりすぎている

今後は、**大量の素材を手作業で登録する方式から、まとまった素材を自動分解して学習可能な単位へ変換する方式**へ移行します。

---

## 基本方針

新しい入力の中心を次の2種類にします。

1. **Character Sheet**
2. **Video**

通常の個別画像登録は補助的な入力方法として残します。

```text
AI Anime Studio
    |
    +-- Character Sheet
    |      |
    |      +-- Sheet Analyzer
    |      +-- Region Extractor
    |      +-- Auto Tagger
    |
    +-- Video
           |
           +-- Shot Detector
           +-- Video Splitter
           +-- Frame Sampler

              ↓
         Asset Classifier
              ↓
 Character / Expression / Pose
 Motion / Shot / Direction
              ↓
          Asset Library
              ↓
     Purpose-specific Training
```

---

# 1. Character Sheet Importer

## 目的

1枚のキャラクター設定シートから複数の学習素材を自動的に取り出し、CharacterProfileとAsset Libraryへ登録します。

例えば1枚の設定シートに次の情報が含まれている場合、それぞれを別素材として扱います。

- メインポートレート
- 正面
- 側面
- 背面
- 顔角度
- 表情
- ポーズ
- 衣装
- 髪型
- カラーパレット
- キャラクターメタデータ

## Character Sheet Template v1

標準テンプレートとして次の構造を定義します。

```text
[A] Main Portrait

[B] Turnaround
    - Front
    - Side
    - Back

[C] Face Angles
    - Front
    - 45 degree
    - Side
    - Up
    - Down
    - Back

[D] Expressions

[E] Pose Reference

[F] Costume Variations

[G] Hair Variations

[H] Color Palette

[I] Character Metadata
```

## 処理フロー

```text
Character Sheet
      ↓
Template Detection
      ↓
Region Extraction
      ↓
Automatic Crop
      ↓
Asset Classification
      ↓
Automatic Tagging
      ↓
CharacterProfile Registration
      ↓
Dataset Builder
```

テンプレートの座標を固定または半固定にすることで、毎回AIに「どこに何があるか」を推測させる必要を減らし、処理速度と安定性を上げます。

## 実装状況

- **初期実装済み**
- `src/anime_studio/character_sheet_importer.py`
- fixed normalized crop region を使う lightweight importer
- `--template-json` で region を差し替え可能

---

# 2. Video Importer

## 目的

mp4などの動画素材をAI Anime Studioへ登録し、後続の解析処理の入口とします。

動画をそのまま1つの学習素材として扱うのではなく、後段でShot単位・フレーム単位・モーション単位に分解します。

## 実装状況

- **初期実装済み**
- `src/anime_studio/video_importer.py`
- `src/anime_studio/video_training_pipeline.py`
- `src/anime_studio/video_phase35_pipeline.py`

---

# 3. Shot Detector / Video Splitter

## 目的

動画をShot単位へ自動分割します。

```text
Video
  ↓
Scene Change Detection
  ↓
Shot 001
Shot 002
Shot 003
...
```

最初の実装では、映像の切り替わり検出を中心とした軽量な方式を優先します。

## 実装状況

- **初期実装済み**
- `src/anime_studio/video_shot_pipeline.py`
- tag変化と最大長を使った軽量 rule-based 分割

---

# 4. Frame Sampler

## 目的

分割したShotから学習に必要な代表フレームだけを抽出します。

全フレームを保存すると、ほぼ同じ画像が大量にDatasetへ入るため、類似フレームを除外します。

想定処理:

- 一定間隔サンプリング
- 類似画像除外
- 表情変化の大きいフレームを優先
- ポーズ変化の大きいフレームを優先
- Shot開始 / 中間 / 終了フレームを候補化

## 実装状況

- **初期実装済み**
- `src/anime_studio/video_shot_pipeline.py`
- start / middle / end 優先 + tag 類似度 / file size 差分による軽量除外
- `effective_fps` による 60〜300秒動画の入力最適化あり

---

# 5. Asset Classifier

## 目的

Character Sheetや動画から抽出した素材を、用途別に分類します。

```text
Extracted Asset
      ↓
Asset Classifier
      ↓
+ Character
+ Expression
+ Pose
+ Motion
+ Shot
+ Direction
```

これにより、1つの動画を1種類の学習だけに使用せず、複数の目的で再利用できるようにします。

## 実装状況

- **初期実装済み**
- `src/anime_studio/video_shot_pipeline.py`
- 現在は次を heuristic に分類
  - Face Angle
  - Expression
  - Full Body / Upper Body / Portrait

---

# 6. Training Dataset Builder v2

## 目的

すべての素材を1つのLoRA Datasetへ入れるのではなく、学習目的ごとにDatasetを作ります。

### Character Dataset

対象:

- 顔
- 髪型
- 衣装
- 表情
- 顔角度
- 全身

主用途:

- Character LoRA
- Character consistency

### Motion Dataset

対象:

- 歩く
- 振り返る
- 座る
- 手を動かす
- 視線移動
- 身体の時間変化

主用途:

- Motion Library
- 将来のMotion Generation

### Shot Dataset

対象:

- Close-up
- Medium Shot
- Long Shot
- Pan
- Tilt
- Dolly
- Tracking
- Camera angle

主用途:

- Shot Library
- Shot Suggestion

### Direction Dataset

対象:

- 感情
- カットタイミング
- ライティング
- 構図
- カメラ
- Shotの組み合わせ
- 演出の時間変化

主用途:

- Direction Library
- 演出提案
- Storyboard / Shot Suggestion AI

## 実装状況

- **初期実装済み**
- `src/anime_studio/dataset_builder_v2.py`
- `character / expression / shot / direction` の4系統を出力
- `motion` dataset は未実装

---

# 動画素材の再利用方針

1本の動画から、用途別に複数のDatasetを作ります。

```text
Video
  |
  +-- Character Dataset
  |     + face
  |     + costume
  |     + expression
  |     + angle
  |
  +-- Motion Dataset
  |     + walk
  |     + turn
  |     + sit
  |     + gesture
  |
  +-- Shot Dataset
  |     + framing
  |     + camera move
  |     + duration
  |
  +-- Direction Dataset
        + emotion
        + timing
        + lighting
        + composition
```

---

# Asset Library中心設計への変更

今後はLoRAをシステムの中心には置きません。

現在の考え方:

```text
Character
   ↓
Images
   ↓
LoRA
   ↓
ComfyUI
```

将来の考え方:

```text
             Character
                 ↓
        CharacterProfile
                 ↓
            Asset Library
       +---------+---------+
       ↓         ↓         ↓
     Image     Motion     Style
       ↓         ↓         ↓
     LoRA     Motion DB   Style DB
       +---------+---------+
                 ↓
                Shot
                 ↓
               Video
```

**LoRAはキャラクター再現手段の1つ**として扱い、キャラクター・モーション・Shot・演出の各AssetをAsset Libraryで統合管理します。

---

# 推奨実装順

## Step 1: Character Sheet Importer

最優先。

Character Sheet Template v1を定義し、1枚の設定シートから次を自動化します。

```text
Import
 ↓
Crop
 ↓
Classify
 ↓
Tag
 ↓
CharacterProfile
 ↓
Dataset
```

## Step 2: Video Importer

動画をAssetとして登録する入口を作ります。

## Step 3: Shot Detector / Video Splitter

動画をShot単位へ自動分割します。

## Step 4: Frame Sampler

重複フレームを減らし、代表フレームだけを抽出します。

## Step 5: Asset Classifier

Character / Expression / Pose / Motion / Shot / Directionへ分類します。

## Step 6: Training Dataset Builder v2

目的別Dataset生成へ変更します。

---

# 将来の理想フロー

```text
Character Sheet 1枚
        +
Reference Video
        ↓
   AI Anime Studio
        ↓
Automatic Analysis
        ↓
+ Character
+ Expression
+ Pose
+ Motion
+ Shot
+ Direction
        ↓
     Asset Library
        ↓
Purpose-specific Training
        ↓
Character Generation
Shot Generation
Motion Generation
Direction Suggestion
        ↓
Storyboard
        ↓
Unity Timeline
        ↓
Final Video
```

---

# 現在の位置づけ

この文書に記載している内容は、**一部がPhase 3.5〜その次段として初期実装済みで、残りが将来改修として継続中**です。

現在実装済みの詳細は `docs/phase_3_5_asset_acquisition_character_consistency.md`、`docs/phase3_6_character_sheet_importer_and_dataset_builder_v2.md`、`docs/roadmap_status.md` を基準に確認します。

既存のPhase 1〜7を破棄するのではなく、既存のCharacterProfile、Asset Library、Storyboard、Shot Suggestion、ComfyUI、Unity Timeline、FFmpeg exportへ接続する新しい入力・解析パイプラインとして段階的に強化します。