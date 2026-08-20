# Roadmap Status

このメモは、現在の実装地点と次に進むべき場所を短く確認するための作業用ステータスです。
READMEの大枠ロードマップを、現在の実装状況に合わせて更新視点で整理します。

## 現在地

現在は **Phase 3.5: Asset Acquisition & Character Consistency** の初期実装が大きくそろった段階です。

`sample_yonagi` で Phase 3 の実機テストを行い、LoRA + ComfyUI から約2秒の動画生成までは到達しました。
一方で、**学習素材の準備効率** と **キャラクター同一性の維持** に課題が残ったため、Phase 4〜7 の本格品質調整を深掘りする前に、動画読込・代表フレーム抽出・Character Sheet・2.5D基準づくりを挟む方針へ切り替えています。

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
| Phase 3.5 | Asset Acquisition & Character Consistency | 実装拡張中 | Video Importer、video-to-training smoke、Character Bootstrap、video learning analysis、Shot Detector、dedup sampler、分類、character sheet draft、reviewed/master import、2.5D definition を追加 |
| Phase 4 | ショット制作 | 完了寄り | Storyboard、ShotEditor、camera/lighting、draft生成、結果採用管理、Unity selected shots連携を作成済み |
| Phase 5 | 自動化 | 完了寄り | Shot Suggestion AI、RenderQueue、Asset Library連携、ショット単位生成/管理を作成済み |
| Phase 6 | 拡張 | 完了寄り | voice、lip-sync、SFX、motion、Unity Timeline仮配置、SFX候補採用、motion clip planまで到達 |
| Phase 7 | 編集/Timeline | 完了寄り | edit timeline manifest、Unity importer、Timeline保護つき再生成、FFmpeg/EDL/FCPXML export、preview plan、revision採用、readiness表示を作成済み |
| Training Start | ローカル学習開始準備 | 実施済み | training readiness check、sample training smoke、短時間LoRA学習と結果確認まで実施 |

## Phase 3.5で現在入っているもの

1. `src/anime_studio/video_importer.py`
   - 動画を CharacterProfile 配下の Source Asset として取り込み、`video_sources.json` を書く。
2. `src/anime_studio/video_training_pipeline.py`
   - 動画登録、フレーム抽出、dataset build、Kohya config、readiness を一本で通す。
3. `src/anime_studio/character_bootstrap.py`
   - 動画を入口に CharacterProfile を新規作成または更新し、bootstrap manifest を残す。
4. `src/anime_studio/video_analysis.py`
   - 抽出済みフレームから sequence manifest、learning asset manifest、storyboard draft を作る。
5. `src/anime_studio/video_shot_pipeline.py`
   - Shot Detector / Splitter、類似フレーム除外つき sampler、顔角度 / 表情 / 全身分類、sampled dataset 出力を行う。
6. `src/anime_studio/character_sheet_draft.py`
   - video analysis / sampled result から character sheet draft と completeness manifest を作る。
7. `src/anime_studio/character_master_asset.py`
   - reviewed / master sheet を再取込し、Character Master Asset manifest を作る。
8. `src/anime_studio/character_2p5d_definition.py`
   - Character Master Asset から軽量 2.5D Definition manifest を作る。
9. `src/anime_studio/video_phase35_pipeline.py`
   - 60〜300秒動画向けの end-to-end Phase 3.5 パイプラインをまとめて実行する。
10. `tests/test_video_shot_pipeline.py`
   - Shot分割、sampled frame、分類の流れを確認する。
11. `tests/test_character_master_asset.py`
   - reviewed/master import と 2.5D definition 生成を確認する。
12. `docs/phase3_5_video_phase35_pipeline.md`
   - end-to-end パイプラインの使い方と制約を整理する。

## 直近の推奨タスク

優先順は次の通りです。

1. 60〜300秒動画で `anime-video-phase35` を実行する。
2. `video_shot_pipeline` の出力を見て Shot boundary の閾値を調整する。
3. sampled dataset と通常 dataset の学習結果を比較する。
4. reviewed / master sheet を実際に取り込み、`anime-character-2p5d` を生成する。
5. Character Master Asset から Dataset Builder v2 を作る。
6. 既存の約2秒動画と同条件で Before / After 比較を行う。

## 設計方針

- 生成AIやGPU処理を増やす前に、入力素材の台帳と品質基準を安定させる。
- JSON manifestは後から人間が編集できる形に保つ。
- Pythonは設計図と検証、UnityはTimeline asset生成、ComfyUIは画像生成という責務を分ける。
- 自動化しても、最終的な採用・差し替え・修正ができる余地を残す。
- LoRAをシステムの中心ではなく、キャラクター再現手段の1つとして扱う。
- 2.5DはLoRAの代替ではなく、キャラクター同一性を補強する control layer として扱う。
