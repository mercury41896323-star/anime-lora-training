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
6. Reference-guided video A/B test
7. Part Mask: Hair / Body / Arms / Clothes
8. Motion Library
9. 2.5D Rig Editor

## Current decision

Hybrid 2.5DはAnimeStudioの有力な開発候補として保持する。

ただし、最初から完全な2.5Dキャラクターシステムを構築しない。

まずは `Reference + Face protection + Pose + Depth + Mask` を動画生成時の制御として追加し、キャラクター一貫性と線・顔ディテールの改善効果をA/Bテストする。
