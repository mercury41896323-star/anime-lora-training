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
| Phase 3.5 | Asset Acquisition & Character Consistency | 進行中 | Video Importer、video-to-training smoke、Character Bootstrap、video learning analysis を追加。次は Shot 分割と Sampler 強化 |
| Phase 4 | ショット制作 | 完了寄り | Storyboard、ShotEditor、camera/lighting、draft生成、結果採用管理、Unity selected shots連携を作成済み |
| Phase 5 | 自動化 | 完了寄り | Shot Suggestion AI、RenderQueue、Asset Library連携、ショット単位生成/管理を作成済み |
| Phase 6 | 拡張 | 完了寄り | voice、lip-sync、SFX、motion、Unity Timeline仮配置、SFX候補採用、motion clip planまで到達 |
| Phase 7 | 編集/Timeline | 完了寄り | edit timeline manifest、Unity importer、Timeline保護つき再生成、FFmpeg/EDL/FCPXML export、preview plan、revision採用、readiness表示を作成済み |
| Training Start | ローカル学習開始準備 | 実施済み | training readiness check、sample training smoke、短時間LoRA学習と結果確認まで実施 |

## Phase 3.5で最初に作ったもの

1. `src/anime_studio/video_importer.py`
   - 動画を CharacterProfile 配下の Source Asset として取り込み、`video_sources.json` を書く。
2. `src/anime_studio/video_training_pipeline.py`
   - 動画登録、フレーム抽出、dataset build、Kohya config、readiness を一本で通す。
3. `src/anime_studio/character_bootstrap.py`
   - 動画を入口に CharacterProfile を新規作成または更新し、bootstrap manifest を残す。
4. `src/anime_studio/video_analysis.py`
   - 抽出済みフレームから sequence manifest、learning asset manifest、storyboard draft を作る。
5. `tests/test_video_importer.py`
   - 動画取込と pending pipeline 状態の manifest 生成を確認する。
6. `tests/test_video_training_pipeline.py`
   - 既存フレーム再利用時の video-to-training smoke を確認する。
7. `tests/test_character_bootstrap.py`
   - 動画から CharacterProfile を起こす流れを確認する。
8. `tests/test_video_analysis.py`
   - sequence / learning asset / storyboard draft 生成を確認する。
9. `docs/phase3_5_video_importer.md`
   - 動画入口の使い方と制約を整理する。
10. `docs/phase3_5_video_to_training.md`
   - 動画から学習準備までの最小ラインを整理する。
11. `docs/phase3_5_character_bootstrap_and_video_analysis.md`
   - Character Bootstrap と Video Analysis の使い方を整理する。
12. `docs/phase_3_5_asset_acquisition_character_consistency.md`
   - Phase 3.5 の親設計を実装状況に合わせて更新する。

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

1. 60〜300秒動画で `anime-character-bootstrap` を実行する。
2. `training video-smoke` で学習準備まで通す。
3. `anime-video-analysis` で sequence / learning asset / storyboard draft を生成する。
4. sequence 結果を見て Shot Detector / Splitter の初期ルールを決める。
5. 類似フレーム除外つき Sampler を追加する。
6. Character Sheet Draft Generator の最小テンプレートを定義する。
7. 外部補正後の reviewed / master 管理方式を固める。
8. 同じ約2秒動画で Before / After 比較条件を固定する。

## 設計方針

- 生成AIやGPU処理を増やす前に、入力素材の台帳と品質基準を安定させる。
- JSON manifestは後から人間が編集できる形に保つ。
- Pythonは設計図と検証、UnityはTimeline asset生成、ComfyUIは画像生成という責務を分ける。
- 自動化しても、最終的な採用・差し替え・修正ができる余地を残す。
- LoRAをシステムの中心ではなく、キャラクター再現手段の1つとして扱う。
- 2.5DはLoRAの代替ではなく、キャラクター同一性を補強する control layer として扱う。