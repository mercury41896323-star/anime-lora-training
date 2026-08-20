# Roadmap Status

このメモは、現在の実装地点と次に進むべき場所を短く確認するための作業用ステータスです。
READMEの大枠ロードマップを、現在の実装状況に合わせて更新視点で整理します。

## 現在地

現在は **Phase 3.5: Asset Acquisition & Character Consistency** の着手段階です。

`sample_yonagi` で Phase 3 の実機テストを行い、LoRA + ComfyUI から約2秒の動画生成までは到達しました。
一方で、**学習素材の準備効率** と **キャラクター同一性の維持** に課題が残ったため、Phase 4〜7 の本格品質調整を深掘りする前に、動画読込・代表フレーム抽出・Character Sheet・2.5D基準づくりを挟む方針へ切り替えます。

Phase 4〜7 の実装は引き続き保持します。今後は、

- Phase 1〜3 をベースラインとして残す
- Phase 3.5 で入力素材パイプラインを強化する
- Phase 4〜7 は低品質素材でも機能テストを継続する

という進め方を取ります。

## Phase別ステータス

| Phase | 名前 | 状態 | メモ |
| --- | --- | --- | --- |
| Phase 1 | 基盤構築 | 完了 | 6GB VRAM前提の最小Python構成、config、inventory CLIを作成済み |
| Phase 2 | キャラクター管理 | 完了 | CharacterProfile、asset登録、tag、dataset生成の入口を作成済み |
| Phase 3 | LoRA学習 | ベースライン完了 | Kohya低VRAM設定、LoRA結果登録、manifest、ComfyUI workflow export、短時間学習と動画生成の基準点を確保 |
| Phase 3.5 | Asset Acquisition & Character Consistency | 着手 | Video Importer から開始。動画読込、Shot分割、Frame Sampler、Character Sheet、外部補正再取込、2.5D基準へ進む |
| Phase 4 | ショット制作 | 完了寄り | Storyboard、ShotEditor、camera/lighting、draft生成、結果採用管理、Unity selected shots連携を作成済み |
| Phase 5 | 自動化 | 完了寄り | Shot Suggestion AI、RenderQueue、Asset Library連携、ショット単位生成/管理を作成済み |
| Phase 6 | 拡張 | 完了寄り | voice、lip-sync、SFX、motion、Unity Timeline仮配置、SFX候補採用、motion clip planまで到達 |
| Phase 7 | 編集/Timeline | 完了寄り | edit timeline manifest、Unity importer、Timeline保護つき再生成、FFmpeg/EDL/FCPXML export、preview plan、revision採用、readiness表示を作成済み |
| Training Start | ローカル学習開始準備 | 実施済み | training readiness check、sample training smoke、短時間LoRA学習と結果確認まで実施 |

## Phase 3.5で最初に作ったもの

1. `src/anime_studio/video_importer.py`
   - 動画を CharacterProfile 配下の Source Asset として取り込み、`video_sources.json` を書く。
2. `tests/test_video_importer.py`
   - 動画取込と pending pipeline 状態の manifest 生成を確認する。
3. `docs/phase3_5_video_importer.md`
   - 最初の使い方と制約を整理する。
4. `docs/phase_3_5_asset_acquisition_character_consistency.md`
   - Phase 3.5 の親設計を「実装前」から「Step 1着手」へ更新する。

## Phase 4〜7で維持していくもの

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

## 直近の推奨タスク

優先順は次の通りです。

1. `sample_yonagi` の基準動画を Phase 3.5 の Video Importer へ登録する。
2. 動画から Shot 分割の最小ルールを決める。
3. 代表フレーム抽出の基準を決める。
4. Character Sheet Draft Generator の最小テンプレートを定義する。
5. 外部補正後の reviewed / master 管理方式を固める。
6. 同じ約2秒動画で Before / After 比較条件を固定する。

## 設計方針

- 生成AIやGPU処理を増やす前に、入力素材の台帳と品質基準を安定させる。
- JSON manifestは後から人間が編集できる形に保つ。
- Pythonは設計図と検証、UnityはTimeline asset生成、ComfyUIは画像生成という責務を分ける。
- 自動化しても、最終的な採用・差し替え・修正ができる余地を残す。
- LoRAをシステムの中心ではなく、キャラクター再現手段の1つとして扱う。
- 2.5DはLoRAの代替ではなく、キャラクター同一性を補強する control layer として扱う。