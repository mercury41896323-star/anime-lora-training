# Roadmap Status

このメモは、現在の実装地点と次に進むべき場所を短く確認するための作業用ステータスです。
READMEの大枠ロードマップを、現在の実装状況に合わせて更新視点で整理します。

## 現在地

現在は **Phase 7: 編集/Timeline** の仕上げ完了寄りです。
Phase 4〜6で作った採用済みShot、音声、SFX、口パク、motionを `edit_timeline_manifest.json` に統合し、Unity Timelineへ保護つきrevision生成できる状態です。

さらに、FFmpeg concat、EDL、FCPXMLの軽量export、preview movie plan、Timeline revision review/adopt、ShotEditorのTimeline Readiness表示まで入りました。
次は **ローカルLoRA学習の最初の短いsmoke run** に進む段階です。

## Phase別ステータス

| Phase | 名前 | 状態 | メモ |
| --- | --- | --- | --- |
| Phase 1 | 基盤構築 | 完了 | 6GB VRAM前提の最小Python構成、config、inventory CLIを作成済み |
| Phase 2 | キャラクター管理 | 完了 | CharacterProfile、asset登録、tag、dataset生成の入口を作成済み |
| Phase 3 | LoRA学習 | 完了寄り | Kohya低VRAM設定、LoRA結果登録、manifest、ComfyUI workflow exportを作成済み |
| Phase 4 | ショット制作 | 完了寄り | Storyboard、ShotEditor、camera/lighting、draft生成、結果採用管理、Unity selected shots連携を作成済み |
| Phase 5 | 自動化 | 完了寄り | Shot Suggestion AI、RenderQueue、Asset Library連携、ショット単位生成/管理を作成済み |
| Phase 6 | 拡張 | 完了寄り | voice、lip-sync、SFX、motion、Unity Timeline仮配置、SFX候補採用、motion clip planまで到達 |
| Phase 7 | 編集/Timeline | 完了寄り | edit timeline manifest、Unity importer、Timeline保護つき再生成、FFmpeg/EDL/FCPXML export、preview plan、revision採用、readiness表示を作成済み |
| Training Start | ローカル学習開始準備 | 入口完成 | training readiness check、sample training smoke、開始手順docを作成済み |

## Phase 7でできていること

1. `timeline_manifest.py`
   - `selected_shots.json` と `phase6_manifest.json` を読み、`edit_timeline_manifest.json` を作る。
2. `tests/test_timeline_manifest.py`
   - Shot順、clip時間、track分割、Phase6補助manifest参照を確認する。
3. Unity `EditTimelineLibrary`
   - 編集Timeline用manifestをUnity ScriptableObjectとして保持する。
4. Unity `EditTimelineManifestImporter`
   - `edit_timeline_manifest.json` をUnity assetへ変換する。
5. Unity `EditTimelineBuilder`
   - video、audio、signal、animation trackをTimelineへ仮配置する。
6. Unity Timeline再生成保護
   - 既存Timelineを上書きせず、revisionフォルダへ新規生成する。
7. `edit_export.py`
   - FFmpeg concat、EDL、FCPXMLを書き出す。
8. `edit_preview.py`
   - FFmpeg preview movie planを生成し、必要なら実行する。
9. `timeline_revision.py`
   - Unity Timeline revisionのreview/adopt manifestを管理する。
10. ShotEditor Timeline Readiness
   - ShotEditor画面にTimeline manifest/export/revisionの状態を表示する。

## ローカル学習開始準備でできていること

1. `training_readiness.py`
   - CharacterProfile、画像枚数、caption、dataset、Kohya configを確認する。
2. `training smoke`
   - auto tag、caption、dataset、Kohya低VRAMconfig、readiness確認を学習起動直前まで通す。
3. `docs/local_training_start.md`
   - RTX 3050 6GB向けの最初の学習開始手順を整理する。

## 直近の推奨タスク

優先順は次の通りです。

1. サンプルキャラ1人でtraining smokeを実行する。
2. 最初の短時間LoRA学習を手動で開始する。
3. 学習ログと生成LoRAをCharacterProfileへ紐づける。
4. 学習後のサンプル生成をComfyUI workflowへ流す。
5. BGM、環境音、音量automationを追加する。

## 設計方針

- 生成AIやGPU処理を増やす前に、制作情報の台帳と採用状態を安定させる。
- JSON manifestは後から人間が編集できる形に保つ。
- Pythonは設計図と検証、UnityはTimeline asset生成、ComfyUIは画像生成という責務を分ける。
- 自動化しても、最終的な採用・差し替え・修正ができる余地を残す。
