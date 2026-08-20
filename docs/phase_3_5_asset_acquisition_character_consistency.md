# Phase 3.5: Asset Acquisition & Character Consistency

> 状態: **設計確定 / Step 1 着手**
>
> Phase 3 の実機テスト結果を受け、Phase 4 の本格テストへ進む前に、キャラクター素材の取得効率と同一性を改善するための中間フェーズとして追加する。

## 背景

Phase 3 では、キャラクター画像を学習し、ComfyUIで中割画像を生成して、それらを連結した約2秒の動画を作るところまで実機テストを行った。

このテストから、次の課題が確認された。

- 中割画像ごとにキャラクターデザインが崩れ、同一性が弱い
- 顔・頭・顎などの位置にばらつきがあり、動画でガタついて見える
- 動きの変化が小さい一方で、生成品質が安定しない
- 学習用画像を個別に準備・登録する作業効率が悪い
- LoRAだけにキャラクターの見た目・角度・形状・動きを担わせるのは負担が大きい

このため、ShotEditor / Timeline の本格品質テストより先に、入力素材・学習効率・キャラクター同一性を改善する。

---

## Phase 3.5 の目的

**動画・既存画像から効率よく高品質なキャラクター基準資料を作り、外部ツールでの補正を再取り込みし、LoRAと2.5Dの両方で利用できる Character Master Asset を構築する。**

Phase 3.5 は既存Phase 1〜7を破棄するものではない。Phase 3とPhase 4の間に追加し、既存のCharacterProfile、Asset Library、ComfyUI、Storyboard、ShotEditor、Unity Timelineへ接続する。

## 現在の着手範囲

最初の実装は **Step 1: Video Importer** に絞る。

この段階で入れるもの:

- 動画を CharacterProfile 配下の `sources/video/` へ登録する
- `video_sources.json` を作り、後続の Shot 分割対象を明示する
- `shot_detection`, `frame_sampling`, `character_sheet` の pending 状態を記録する
- 既存の Phase 1〜7 CLI を壊さず、Phase 3.5 の入口だけを追加する
- 動画から学習準備までを一気通しする `training video-smoke` を追加する

この段階ではまだ行わないもの:

- ffprobe による詳細 metadata 抽出
- Shot Detector / Splitter
- 類似フレーム除外
- Character Sheet Draft Generator
- reviewed / master 再Import

---

## 全体フロー

```text
Video / Existing Images
        ↓
1. Video Importer
        ↓
2. Shot Detector / Splitter
        ↓
3. Frame Sampler
        ↓
4. Character Asset Classifier
        ↓
5. Character Sheet Draft Generator
        ↓
6. Character Sheet Completeness Check
        ↓
7. External Review / Correction
   Gemini等の外部ツール、人間による修正
        ↓
8. Reviewed Character Sheet Re-Import
        ↓
9. Character Master Asset
        ↓
   +-------------------+
   ↓                   ↓
LoRA Dataset      2.5D Definition
   ↓                   ↓
Character LoRA    Shape / Position Control
   +---------+---------+
             ↓
      Controlled Generation
             ↓
       ComfyUI Test
             ↓
  Same 2-second Video Test
             ↓
     Before / After比較
```

---

# 1. Video Importer

動画を学習素材・解析素材としてAI Anime Studioへ登録する。

想定入力:

- mp4
- mov
- その他FFmpegで扱える一般的な動画形式

動画そのものを直接1つのLoRA素材として扱うのではなく、Shot・フレーム・Motion・Directionへ分解するためのSource Assetとして保存する。

初期実装済み範囲:

- `src/anime_studio/video_importer.py`
- `tests/test_video_importer.py`
- `docs/phase3_5_video_importer.md`

保存先:

```text
assets/processed/characters/<character_id>/sources/video/
assets/processed/characters/<character_id>/video_sources.json
```

---

## 1.5. Video To Training Smoke

動画から LoRA 学習準備までを一気通しする最小ライン。

初期実装済み範囲:

- `src/anime_studio/video_training_pipeline.py`
- `tests/test_video_training_pipeline.py`
- `docs/phase3_5_video_to_training.md`
- `anime-studio training video-smoke`

役割:

- Video Importer を起点にする
- 既存の frame extraction を再利用する
- 既存の auto tag / dataset / Kohya config / readiness を再利用する
- Character Sheet や 2.5D に進む前の、動画ベース学習ラインの最小実験を可能にする

このラインはまだ、

- 類似フレーム除外
- Shot単位代表抽出
- 顔角度優先抽出
- Character Sheet Draft 生成

には対応していない。

---

# 2. Shot Detector / Splitter

動画をShot単位へ自動分割する。

初期実装は軽量なScene Change Detectionを優先する。

```text
Video
 ↓
Shot 001
Shot 002
Shot 003
...
```

既存の動画分割検証で得た知見を活用し、過剰分割やフェードのみのShotを減らす。

---

# 3. Frame Sampler

各Shotから代表フレームを抽出する。

目的は全フレームを学習へ投入することではなく、**情報量の高いフレームを少数選ぶこと**。

候補選択基準:

- Shot開始 / 中間 / 終了
- 顔角度の変化
- 表情変化
- ポーズ変化
- 全身が見えるフレーム
- ブラーが少ないフレーム
- 類似度の高い重複フレームを除外

---

# 4. Character Asset Classifier

抽出フレームや既存画像を用途別に分類する。

```text
Extracted Asset
 ↓
Character Asset Classifier
 ↓
- Identity
- Face Angle
- Expression
- Full Body
- Pose
- Costume
- Hair
- Motion Reference
```

将来的にはMotion / Shot / Direction Dataset Builderとも共有する。

---

# 5. Character Sheet Draft Generator

分類された代表フレームから、Character Sheet Template v1に沿ったDraftを自動生成する。

主な領域:

- Main Portrait
- Front
- Side
- Back
- Face Angles
- Expressions
- Full Body
- Pose Reference
- Costume
- Hair
- Color Palette
- Metadata

動画に存在しない角度や表情を無理に推測して埋めず、Missingとして残す。

---

# 6. Character Sheet Completeness Check

Draft生成後、キャラクター基準資料として何が不足しているかを可視化する。

例:

```text
Front        OK
Left Side    OK
Right Side   OK
Back         Missing
Full Body    OK
Expressions  7/10
Costume      OK
Hair Detail  Needs Review
```

目的は、不足部分だけを外部AI・追加画像・手動作成で補えるようにすること。

---

# 7. External Review / Correction

Character Sheet Draftは最終正解としない。

動画由来素材には、圧縮、ブラー、作画揺れ、遮蔽、極端な角度などが含まれるため、Gemini等の外部ツールや人間による補正工程を正式なワークフローとして認める。

主な補正対象:

- 顔の左右差
- 髪型・髪束
- 衣装ディテール
- 手足
- 色
- 線画
- 正面 / 側面 / 背面の整合性
- 身体比率

外部ツールは交換可能とし、特定サービスへの依存は避ける。

---

# 8. Reviewed Character Sheet Re-Import

外部で補正したCharacter SheetをAI Anime Studioへ再読み込みできるようにする。

推奨管理:

```text
character_sheet/
├─ source/
│  └─ video_extracted_draft.png
├─ reviewed/
│  └─ character_sheet_reviewed_v1.png
└─ master/
   └─ character_sheet_master_v1.png
```

sourceは自動生成原本、reviewedは外部補正版、masterはAI Anime Studioで正式採用した基準資料とする。

原本を上書きせずrevisionを保持する。

---

# 9. Character Master Asset

採用済みCharacter Sheet、各Crop、metadata、Completeness情報、CharacterProfileとの紐付けを統合した基準Assetを作る。

Character Master Assetを、以降のキャラクター再現のSingle Source of Truthとして扱う。

---

# 10. Dataset Builder v2

Character Master Assetと動画から抽出した高品質フレームを使い、目的別にDatasetを構築する。

Character LoRAにはキャラクター同一性に必要な素材だけを入れ、重複フレームや品質の低いフレームを減らす。

将来的には以下へ拡張する。

- Character Dataset
- Motion Dataset
- Shot Dataset
- Direction Dataset

---

# 11. 2.5D Character Definition

LoRAだけでキャラクターの形状・位置・角度を安定させようとせず、Character Master Assetから2.5D用の基準情報を作る。

役割分担:

```text
LoRA
  = 見た目、質感、キャラクターらしさ

2.5D
  = 頭身、顔位置、目鼻位置、体型、髪シルエットなどの形状基準

ControlNet等のControl
  = ポーズ、構図、向き
```

2.5Dの具体的な技術方式は、このPhaseの前半テスト結果を見て選定する。特定方式を先に固定しない。

---

# 12. 再学習・再生成テスト

Phase 3で作成した約2秒動画をベースラインとして保存し、Phase 3.5改修後に同条件で再生成する。

比較項目:

- 顔の同一性
- 髪型の同一性
- 衣装の同一性
- 頭身・身体比率
- 頭 / 顎 / 顔位置のフレーム間ガタつき
- 角度変化の自然さ
- 動きの自然さ
- 学習素材準備時間
- 手動登録回数
- Datasetの画像枚数と重複率
- LoRA学習時間

品質だけでなく、**学習・素材準備の効率改善も評価する**。

---

# ShotEditor / Timelineとの関係

Phase 4〜7の開発を破棄・停止するわけではない。

Phase 3.5実装中でも、低品質素材やダミー素材を使った機能テストは継続できる。

```text
Shot作成
 ↓
候補登録
 ↓
selected / rejected
 ↓
Timeline manifest
 ↓
Unity / FFmpeg
```

ただし、ShotEditorやTimelineの**本格的な品質評価・UI最適化・演出自動化の作り込み**は、Phase 3.5でキャラクター生成品質が一定水準に達した後に行う。

---

# 推奨実装順

1. Video Importer
2. Video To Training Smoke
3. Shot Detector / Splitter
4. Frame Sampler
5. Character Asset Classifier
6. Character Sheet Draft Generator
7. Character Sheet Completeness Check
8. Reviewed Character Sheet Re-Import
9. Character Master Asset
10. Dataset Builder v2
11. 2.5D Character Definition
12. LoRA再学習
13. 同条件2秒動画のBefore / After比較

---

# Phase 3.5 完了条件

Phase 3.5は「各機能のコードが存在する」だけでは完了としない。

以下を満たした時点を完了とする。

1. 1本の動画と既存画像からCharacter Sheet Draftを生成できる。
2. 不足情報をCompleteness Checkで確認できる。
3. 外部ツールで補正したCharacter Sheetを再Importできる。
4. Character Master Assetを作成できる。
5. Character Master AssetからLoRA用Datasetと2.5D用基準情報を作成できる。
6. Phase 3と同条件の約2秒動画を再生成できる。
7. ベースラインと比較し、キャラクター同一性が改善している。
8. 学習素材準備・登録の作業量がPhase 3方式より減っている。

---

# 設計原則

- 自動生成結果を最終正解にしない。
- 人間による採用・修正・差し替えを残す。
- 外部AIでの補正を正式なワークフローとして扱う。
- 外部サービス固有の形式へ依存しない。
- source / reviewed / masterを分離し、原本を失わない。
- 動画から全フレームを無条件に学習させない。
- LoRAをシステムの中心ではなく、キャラクター再現手段の1つとして扱う。
- 2.5DはLoRAの代替ではなく、キャラクター同一性を補強するControl Layerとして扱う。
- Phase 4〜7との互換性を維持する。