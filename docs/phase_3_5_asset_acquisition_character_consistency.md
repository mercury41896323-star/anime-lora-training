# Phase 3.5: Asset Acquisition & Character Consistency

> 状態: **初期実装入り / Step 4 付近**
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

現在は **Step 4: Shot Detector / Frame Sampler / Character Sheet Draft の初期実装** まで進めている。

この段階で入っているもの:

- 動画を CharacterProfile 配下の `sources/video/` へ登録する
- `video_sources.json` を作り、後続の Shot 分割対象を明示する
- `training video-smoke` で動画から学習準備までを一気通しする
- 動画を入口に CharacterProfile を新規作成または更新する
- 抽出済みフレームから sequence manifest、learning asset manifest、storyboard draft を作る
- Shot Detector / Splitter の軽量初期版を入れる
- 類似フレーム除外つき sampled dataset を作る
- 顔角度 / 表情 / 全身の heuristic 分類を行う
- Character Sheet Draft / Completeness を作る
- reviewed / master sheet の再取込を行う
- Character Master Asset から 2.5D Definition manifest を作る
- 60〜300秒動画向けの adaptive fps を入れる

この段階でまだ弱いもの:

- Shot boundary の精度はまだ軽量 rule-based
- 類似度判定は tag / file-size ベースの簡易版
- 顔角度 / 表情 / 全身分類は heuristic
- 2.5D Definition は control manifest であり rig ではない
- Character Master Asset からの Dataset Builder v2 はまだ未実装

---

## 全体フロー

```text
Video / Existing Images
        ↓
1. Character Bootstrap
        ↓
2. Video Importer
        ↓
3. Video To Training Smoke
        ↓
4. Video Analysis
        ↓
5. Shot Detector / Splitter
        ↓
6. Frame Sampler
        ↓
7. Character Asset Classifier
        ↓
8. Character Sheet Draft Generator
        ↓
9. Character Sheet Completeness Check
        ↓
10. External Review / Correction
        ↓
11. Reviewed Character Sheet Re-Import
        ↓
12. Character Master Asset
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

# 1. Character Bootstrap

動画を入口にして CharacterProfile を新規作成または更新する。

初期実装済み範囲:

- `src/anime_studio/character_bootstrap.py`
- `tests/test_character_bootstrap.py`
- `anime-character-bootstrap`

---

# 2. Video Importer

動画を学習素材・解析素材としてAI Anime Studioへ登録する。

初期実装済み範囲:

- `src/anime_studio/video_importer.py`
- `tests/test_video_importer.py`
- `docs/phase3_5_video_importer.md`

---

# 3. Video To Training Smoke

動画から LoRA 学習準備までを一気通しする最小ライン。

初期実装済み範囲:

- `src/anime_studio/video_training_pipeline.py`
- `tests/test_video_training_pipeline.py`
- `docs/phase3_5_video_to_training.md`
- `anime-studio training video-smoke`
- `anime-video-training`

---

# 4. Video Analysis

抽出済みフレームから、学習解析結果・learning asset candidate・sequence manifest・storyboard draft を作る。

初期実装済み範囲:

- `src/anime_studio/video_analysis.py`
- `tests/test_video_analysis.py`
- `anime-video-analysis`
- `docs/phase3_5_character_bootstrap_and_video_analysis.md`

---

# 5. Shot Detector / Splitter

動画をShot単位へ自動分割する。

初期実装済み範囲:

- `src/anime_studio/video_shot_pipeline.py`
- `tests/test_video_shot_pipeline.py`
- `anime-video-shot detect`

現在は tag 変化と最大長による軽量分割を行う。

---

# 6. Frame Sampler

各Shotから代表フレームを抽出し、類似寄りのフレームを減らす。

初期実装済み範囲:

- `src/anime_studio/video_shot_pipeline.py`
- `anime-video-shot sample`

現在は start / middle / end を優先し、tag 類似度と file size 差を使って軽量に重複を抑える。

---

# 7. Character Asset Classifier

抽出フレームを用途別に分類する。

初期実装済み範囲:

- `src/anime_studio/video_shot_pipeline.py`
- `anime-video-shot classify`

現在は次を出す。

- Face Angle
- Expression
- Full Body / Upper Body / Portrait

---

# 8. Character Sheet Draft Generator

分類や解析結果をもとに Character Sheet Draft を生成する。

初期実装済み範囲:

- `src/anime_studio/character_sheet_draft.py`
- `tests/test_character_sheet_draft.py`
- `docs/phase3_5_character_sheet_draft.md`
- `anime-character-sheet-draft`

---

# 9. Character Sheet Completeness Check

Draft生成後、何が不足しているかを可視化する。

初期実装済み範囲:

- `character_sheet/<video_id>_completeness.json`

---

# 10. External Review / Correction

Character Sheet Draftは最終正解としない。

この工程自体は人間・外部ツール前提で残す。

---

# 11. Reviewed Character Sheet Re-Import

外部で補正したCharacter Sheetを再読み込みできるようにする。

初期実装済み範囲:

- `src/anime_studio/character_master_asset.py`
- `tests/test_character_master_asset.py`
- `anime-character-master`

---

# 12. Character Master Asset

採用済みCharacter Sheet、metadata、Completeness情報、CharacterProfileとの紐付けを統合した基準Assetを作る。

初期実装済み範囲:

- `character_master_asset.json`

---

# 13. Dataset Builder v2

Character Master Assetと動画から抽出した高品質フレームを使い、目的別にDatasetを構築する。

現時点ではまだ未実装。

---

# 14. 2.5D Character Definition

Character Master Assetから2.5D用の基準情報を作る。

初期実装済み範囲:

- `src/anime_studio/character_2p5d_definition.py`
- `anime-character-2p5d`

これは現時点では、layer / control hint / view anchor を持つ軽量 control manifest である。

---

# 15. 60〜300秒動画向け解析最適化

初期実装済み範囲:

- `ffprobe` があれば duration を読む
- `target_max_frames` を超えない `effective_fps` を自動計算する
- `anime-video-phase35` で end-to-end に実行する

---

# 16. End-to-End Pipeline

現在は Phase 3.5 を一気に通す入口も入っている。

初期実装済み範囲:

- `src/anime_studio/video_phase35_pipeline.py`
- `docs/phase3_5_video_phase35_pipeline.md`
- `anime-video-phase35`

---

# ShotEditor / Timelineとの関係

Phase 4〜7の開発を破棄・停止するわけではない。

Phase 3.5実装中でも、低品質素材やダミー素材を使った機能テストは継続できる。

---

# 推奨実装順

1. `anime-video-phase35` で 60〜300秒動画を通す
2. Shot boundary と sampled frame を人間が確認する
3. reviewed / master sheet を取り込む
4. `anime-character-2p5d` を生成する
5. Character Master Asset ベースの Dataset Builder v2 へ進む
6. LoRA再学習
7. 同条件2秒動画の Before / After 比較

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
