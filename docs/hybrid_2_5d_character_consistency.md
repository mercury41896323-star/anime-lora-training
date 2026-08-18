# Hybrid 2.5D Character Consistency Memo

## Purpose

AnimeStudioで画像学習からキャラクター画像生成、動画生成までを行う際、静止画では顔や輪郭線が維持できていても、動画生成段階で顔・目・髪・線・衣装の細部が潰れる問題がある。

この問題に対して、2.5Dを完成映像として直接使うのではなく、生成時の構造制御と学習データ整理のための中間表現として導入する価値がある。

## Design principle

見た目と動きを分離する。

### Appearance

- Character LoRA
- Face Reference
- Hair Reference
- Clothes Reference
- Line / color identity

### Motion / Structure

- Pose
- Depth
- Character Mask
- Part Masks
- Camera
- Timing
- Motion Library

2.5Dは主にMotion / Structure側の制御情報として扱う。

## Target architecture

```text
Character Library
      |
      +-- LoRA
      +-- Face Reference
      +-- Hair Reference
      +-- Clothes Reference
      +-- Character / Part Masks
      |
      v
2.5D Guide
Pose / Depth / Mask / Camera / Timing
      |
      v
Video Generation
      |
      v
Face / Detail Correction Pass
      |
      v
Final Animation
```

## Why 2.5D is useful

2.5Dを導入する目的は、LoRAそのものを2.5D化して学習することではない。

生成時にAIが毎フレーム推測しなければならない情報を減らし、キャラクター固有の外見と、時間方向の動きを別々に拘束することが主目的となる。

特に以下の維持を狙う。

- 顔の位置と大きさ
- 目・輪郭の安定
- 髪型と前後関係
- 腕・身体の位置
- 衣装シルエット
- キャラクター全体の奥行き
- フレーム間のポーズ整合性

## Relation to training data

2.5D解析は学習データの構造化にも利用する。

```text
Capture
  +-- Character
  +-- Face
  +-- Hair
  +-- Body
  +-- Arms
  +-- Clothes
  +-- Background
  +-- Pose
  +-- Depth
  +-- Motion hint
```

これにより、キャラクター固有情報と、そのフレーム固有のポーズ・背景・カメラ条件を分離しやすくする。

## PySceneDetect pipeline connection

現在のPySceneDetect PoCから次の流れへ接続する。

```text
MP4
 -> PySceneDetect
 -> Scene Captures
 -> Best Capture Selection
 -> Capture Analyzer
 -> Character / Face / Hair / Clothes / Pose / Depth / Mask
 -> Asset Library
 -> LoRA Dataset
 -> 2.5D Guide
 -> Video Generation
```

Best Captureでは単純な画質だけではなく、学習価値と構造情報量も評価する。

想定スコア:

- technical_score
- character_visibility_score
- training_value_score
- diversity_score
- occlusion_penalty
- redundancy_penalty

## Asset Library and Sequence Library

AnimeStudioでは、シーン分割後の素材を単純にバラバラのAssetとして保存するだけではなく、元動画の順序・タイミング・前後関係も保持する。

基本方針:

> Asset Library = 再利用可能な部品
>
> Sequence Library = 元動画の設計図

### Asset Library

再利用可能な制作要素を保存する。

```text
Asset Library
  +-- Characters
  +-- Motions
  +-- Backgrounds
  +-- Cameras
  +-- Poses
  +-- References
  +-- 2.5D Guides
```

Asset Libraryは、別シーン・別作品・別キャラクターへの再利用を目的とする。

### Sequence Library

元動画の構成そのものを保存する。

```text
Sequence
  +-- Scene 001
  |    +-- Character refs
  |    +-- Motion refs
  |    +-- Background refs
  |    +-- Camera refs
  |    +-- Duration
  |    +-- Timing
  |    +-- 2.5D Guide refs
  |
  +-- Scene 002
  +-- Scene 003
  +-- ...
```

Sequence Libraryには最低限、次を保持する。

- scene order
- start / end time
- duration
- Character Asset参照
- Motion Asset参照
- Background Asset参照
- Camera / Shot Asset参照
- Pose / Depth / Mask参照
- 前後Sceneとのcontinuity情報

これによりPySceneDetectでSceneを分割しても、元動画が一連の映像であったという情報を失わない。

### Continuity across scene boundaries

MotionはScene境界で完全に切断しない。

各Sceneについて、可能であれば次を保存する。

```text
Scene N
  end_pose
  end_velocity
  end_direction
  end_character_state
      |
      v
Transition / overlap frames
      |
      v
Scene N+1
  start_pose
  start_velocity
  start_direction
  start_character_state
```

必要に応じてScene境界の前後数フレームをoverlap情報として保持し、再生成時の動き・姿勢・キャラクター状態の連続性に利用する。

### Reconstruction modes

Sequence Libraryを使うことで、ユーザーがSceneごとにAssetを手動選択しなくても元動画の構造を再利用できるようにする。

#### Reproduction mode

元Sequenceをそのまま読み込み、Scene順、Motion、Camera、Timing、Backgroundなどを自動適用する。

```text
Original Sequence
      +
Character / Style
      |
      v
Automatic scene reconstruction
```

#### Replacement mode

Sequenceを維持したまま、一部のAssetだけ差し替える。

例:

- キャラクターだけ変更
- 背景だけ変更
- Motionだけ変更
- Cameraだけ変更
- Style / LoRAだけ変更

#### Remix mode

Asset Libraryから部品を選び、新しいSequenceを構築する。

### Target hierarchy

```text
Project
  |
  v
Source Video
  |
  v
Sequence Library
  |
  +-- Scene / Shot
        |
        +-- Asset references
        |     +-- Character
        |     +-- Motion
        |     +-- Background
        |     +-- Camera
        |
        +-- 2.5D Guide
        +-- Timing
        +-- Continuity
```

この二層構造により、AnimeStudioは「素材を学習して再利用する機能」と「読み込んだ動画を一連の構成として再現する機能」を両立する。

## A/B validation before full implementation

本格的な2.5D Editorを作る前に、同一キャラクター・同一モーション・同一秒数で比較する。

### A: Current pipeline

```text
Character LoRA
+ Image-to-Video
```

### B: Hybrid 2.5D pipeline

```text
Character LoRA
+ Reference Image
+ Face Reference
+ Pose
+ Depth
+ Character Mask
```

### Evaluation

- 顔の一致度
- 目の形
- 顔輪郭
- 髪型
- 衣装
- 線の保持
- 手の崩れ
- フレーム間ちらつき
- 小さい顔でのディテール保持

Bで明確な改善が確認できた場合、Part Maskと2.5D Rigへ段階的に拡張する。

## Development priority

1. Best Capture Selection
2. Capture Analyzer
3. Character / Face Mask
4. Pose extraction
5. Depth estimation
6. Asset Library schema
7. Sequence Library / sequence manifest schema
8. Scene continuity metadata
9. Reference-guided video A/B test
10. Part Mask: Hair / Body / Arms / Clothes
11. Motion Library
12. 2.5D Rig Editor

## Current decision

Hybrid 2.5DはAnimeStudioの有力な開発候補として保持する。

また、動画学習・動画再現では `Asset Library = 部品` と `Sequence Library = 元動画の設計図` を分離して管理する方針を採用候補とする。

シーン分割は解析単位として利用するが、元動画のScene順、Timing、Camera、Motion continuityをSequence Libraryに保持し、再現時にユーザーが各Assetを一つずつ選ばなくても元Sequenceを自動再構成できる設計を目指す。

2.5Dについては、最初から完全な2.5Dキャラクターシステムを構築しない。

まずは `Reference + Face protection + Pose + Depth + Mask` を動画生成時の制御として追加し、キャラクター一貫性と線・顔ディテールの改善効果をA/Bテストする。
