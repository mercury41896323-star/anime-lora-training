# Roadmap Status

このメモは、現在の実装地点と次に進むべき場所を短く確認するための作業用ステータスです。
READMEの大枠ロードマップを、現在の実装状況に合わせて更新視点で整理します。

## 現在地

現在は **Phase 6: 拡張** の後半です。
Phase 4とPhase 5の最小実装は通過済みで、Phase 6では音声、口パク、SFX、motionをShot単位で管理し、Unity Timelineへ渡す流れを作っています。

Phase 7へ入る前に、Phase 6の補助manifestを統合し、編集用Timeline manifestの設計を固める段階です。

## Phase別ステータス

| Phase | 名前 | 状態 | メモ |
| --- | --- | --- | --- |
| Phase 1 | 基盤構築 | 完了 | 6GB VRAM前提の最小Python構成、config、inventory CLIを作成済み |
| Phase 2 | キャラクター管理 | 完了 | CharacterProfile、asset登録、tag、dataset生成の入口を作成済み |
| Phase 3 | LoRA学習 | 完了寄り | Kohya低VRAM設定、LoRA結果登録、manifest、ComfyUI workflow exportを作成済み |
| Phase 4 | ショット制作 | 完了寄り | Storyboard、ShotEditor、camera/lighting、draft生成、結果採用管理、Unity selected shots連携を作成済み |
| Phase 5 | 自動化 | 完了寄り | Shot Suggestion AI、RenderQueue、Asset Library連携、ショット単位生成/管理を作成済み |
| Phase 6 | 拡張 | 進行中 | voice、lip-sync、SFX、motion、Unity Timeline仮配置、SFX候補採用、motion clip planまで到達 |
| Phase 7 | 編集/Timeline | 設計中 | edit timeline manifest、Unity編集Timeline生成、外部編集ツール連携の入口を設計中 |

## Phase 6で残っていること

1. `phase6_manifest.json` に補助manifest参照を追加する。
2. Unity Timeline Builderで `motion_clip_plan.json` を優先利用する。
3. ShotEditorにPhase6 status summaryを表示する。
4. voice/SFXのasset存在チェックとfallback理由を見える化する。
5. Docs上のPhase 6完了条件をREADMEへ反映する。

## Phase 7で最初に作るもの

1. `timeline_manifest.py`
   - `selected_shots.json` と `phase6_manifest.json` を読み、`edit_timeline_manifest.json` を作る。
2. `tests/test_timeline_manifest.py`
   - Shot順、clip時間、track分割、fallbackを確認する。
3. `docs/phase7_timeline_editing_design.md`
   - Phase 7の編集manifest、track設計、Unity連携方針を管理する。
4. Unity importer sample
   - Python側manifestが固まってから、Unity ScriptableObject化に進む。

## 直近の推奨タスク

優先順は次の通りです。

1. Phase6 manifestへ `supplemental_manifests` を追加する。
2. `timeline_manifest.py` の最小プロトタイプを作る。
3. `edit_timeline_manifest.json` をUnityに読み込むImporterを作る。
4. Unity Timeline Builderでvideo/audio/signal/animation trackを統合生成する。
5. READMEのロードマップ表記を現在地に合わせて更新する。

## 設計方針

- 生成AIやGPU処理を増やす前に、制作情報の台帳と採用状態を安定させる。
- JSON manifestは後から人間が編集できる形に保つ。
- Pythonは設計図と検証、UnityはTimeline asset生成、ComfyUIは画像生成という責務を分ける。
- 自動化しても、最終的な採用・差し替え・修正ができる余地を残す。
