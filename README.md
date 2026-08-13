# AI Anime Studio

AIを活用したアニメーション制作支援・学習・生成環境を構築するプロジェクトです。

## プロジェクトの目的

アニメ映像から **陰影・質感・画面構成・カメラワーク・タイミング** などの表現要素を学習・整理し、Unityを中心とした制作環境で再構成・生成できる仕組みを作ります。

単純な動画生成ツールではなく、アニメ制作に必要な素材・キャラクター・カメラ・ライティング・ショット情報を一貫して管理し、少ない計算資源でも段階的に制作できることを重視します。

## 現在のステータス

**Project Restart - Phase 1 基盤構築開始**

最初の実装として、RTX 3050 6GB VRAM環境を前提にした軽量なプロジェクト骨格と、GPUを使わずに動作確認できる素材インベントリ生成CLIを追加しました。

現在は次の入口も追加済みです。

- CharacterProfile JSONの作成
- FFmpegによるフレーム抽出コマンドの事前確認
- キャラクター素材登録
- 手動タグsidecarの作成
- LoRA学習用データセット生成

## まず動かすもの

この段階では重いAIモデルやGPU処理は使いません。まず素材置き場を確認し、プロジェクトがローカルで動くことを検証します。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:PYTHONPATH = "src"
python -m anime_studio.cli inventory --pretty
```

PowerShell用の簡易スクリプトも用意しています。

```powershell
.\scripts\run_inventory.ps1
```

実行すると `assets/raw` を走査し、`assets/processed/inventory.json` に素材一覧を出力します。

## 開発方針

- 目的は「AIを使ったアニメ制作」に集中する
- RTX 3050 6GB VRAMを前提として、軽量・省VRAMな構成を優先する
- GPU使用率は原則80%以下を目安とする
- GPU温度は60℃程度を目安として運用する
- まず小さく動くプロトタイプを作り、段階的に機能を追加する
- キャラクターの一貫性と映像表現の再現性を重視する
- 自動化できる作業は自動化し、制作判断そのものをAI任せにしすぎない
- プロジェクトの目的から外れる機能は追加しない

## 想定環境

- OS: Windows
- GPU: NVIDIA GeForce RTX 3050 6GB VRAM
- ゲームエンジン / 制作基盤: Unity
- 画像生成: Stable Diffusion 1.5
- ノードベース生成: ComfyUI
- LoRA学習: Kohya_ss
- タグ付け: WD14
- 画像理解・タグ補助: Llama-3-Vision
- 制御: ControlNet
- 動画・画像処理: FFmpeg / OpenCV

## 初期構成

```text
anime-lora-training/
├─ README.md
├─ pyproject.toml
├─ requirements.txt
├─ requirements-dev.txt
├─ config/
│  └─ local_6gb.json
├─ docs/
│  ├─ development_start.md
│  ├─ character_profiles.md
│  └─ phase2_pipeline.md
├─ scripts/
│  └─ run_inventory.ps1
├─ src/
│  └─ anime_studio/
│     ├─ __init__.py
│     ├─ asset_inventory.py
│     ├─ character_manager.py
│     ├─ character_profile.py
│     ├─ cli.py
│     ├─ dataset_builder.py
│     ├─ frame_extraction.py
│     ├─ tagger.py
│     └─ settings.py
├─ assets/
│  ├─ raw/
│  └─ processed/
└─ tests/
   ├─ test_asset_inventory.py
   ├─ test_character_manager.py
   ├─ test_character_profile.py
   ├─ test_frame_extraction.py
   └─ test_tagger_and_dataset.py
```

## 最小プロトタイプ

### Asset Inventory CLI

`assets/raw` に置いた画像・動画・その他ファイルを分類し、軽量なJSONとして出力します。

目的:

- Asset Pipelineの入口を作る
- GPUなしで動作確認できる状態にする
- 将来のフレーム抽出、タグ付け、CharacterProfile生成へつなげる

対応拡張子は `config/local_6gb.json` で管理します。

### CharacterProfile CLI

キャラクターの一貫性を保つため、最初に小さなJSONプロファイルを作成できます。

```powershell
python -m anime_studio.cli character init --id sample_hero --name "Sample Hero" --trigger-tag sample_hero
```

出力先:

```text
assets/processed/characters/sample_hero/profile.json
```

### Frame Extraction CLI

動画からのフレーム抽出はFFmpeg連携を前提にします。まずは`--dry-run`で実行予定コマンドだけ確認できます。

```powershell
python -m anime_studio.cli frames --video assets/raw/sample.mp4 --character-id sample_hero --fps 1 --dry-run
```

### Character Asset / Dataset CLI

キャラクターごとに素材を登録し、手動タグのsidecarを作り、LoRA学習用データセットへまとめます。

```powershell
python -m anime_studio.cli character register-asset --id sample_hero --source assets/raw/sample.png
python -m anime_studio.cli tags --character-id sample_hero --extra-tag anime_style
python -m anime_studio.cli dataset build-lora --character-id sample_hero
```

WD14本体はまだ同梱していません。まずは同じ`.txt` caption形式でパイプラインを固定し、後からWD14出力へ差し替えます。

## 6GB VRAM向け初期設定

`config/local_6gb.json` では、低VRAM環境向けに以下を初期値としています。

- SD 1.5系を優先
- ドラフト解像度は512x512
- バッチサイズは1
- fp16を前提
- LoRA学習ではgradient checkpointingとlatent cacheを使う方針

この設定はまだ実際の生成・学習を起動しません。今後ComfyUIやKohya_ss連携を追加するときの共通設定として使います。

## システム構成

### Character Manager

キャラクター素材を管理する中核モジュール。

- キャラクター画像・動画素材の登録
- 動画からのフレーム抽出
- キャラクター単位での素材整理
- キャラクター設定・特徴量の管理
- LoRA学習用データへの連携

### Tagger

学習素材の自動タグ付けを担当します。

- WD14によるアニメ画像タグ付け
- Llama-3-Visionによる補助的な画像理解
- キャラクター・衣装・表情・構図などのメタデータ整理
- 学習データセット作成の効率化

### LoRA Trainer

キャラクターや画風などをLoRAとして学習するためのモジュール。

- Kohya_ssとの連携
- キャラクターLoRA
- 画風・質感LoRA
- 学習パラメータ管理
- VRAM 6GB環境を考慮した学習設定

### Asset Pipeline

画像・動画・音声・学習データなどの素材を一元管理するパイプライン。

### Asset Library

制作で利用する素材を検索・再利用するためのライブラリ。

対象例:

- キャラクター
- 背景
- 小物
- エフェクト
- ポーズ
- カメラワーク
- ライティング
- 表情
- アニメーション素材

### CharacterProfile

キャラクターの外見・設定・LoRA・衣装・表情などを一つのプロファイルとして管理します。

キャラクターの一貫性を維持するための重要な基盤とします。

### Shot Suggestion AI

シーンやストーリー情報から、ショット構成を提案する支援モジュール。

- カメラ位置
- カメラ距離
- 構図
- カメラ移動
- キャラクター配置
- ライティング
- ショットのタイミング

などを制作補助情報として提示します。

### Storyboard

シーンをショット単位で整理し、映像全体の流れを確認するための機能。

### ShotEditor

各ショットについて、カメラ・キャラクター・背景・ライティング・タイミングなどを編集するためのUIを想定します。

### Draft

本制作前の低コストなプレビュー生成を行う機能。

6GB VRAM環境でも確認しやすい軽量なプレビューを優先します。

### RenderQueue

複数ショットの生成・レンダリングを順番に処理するためのキュー管理機能。

## 映像表現の学習

本プロジェクトでは、単に画像を生成するだけではなく、アニメ映像から以下の要素を分析・整理することを目標とします。

- 陰影
- 質感
- 色調
- 構図
- カメラワーク
- カメラ移動
- ショットサイズ
- キャラクター配置
- ライティング
- 動きのタイミング
- カット間のつながり

これらを再利用可能な制作知識としてAsset Library等に蓄積します。

## 出力

制作目的に応じて以下の映像形式を想定します。

- 横動画
- 縦動画

最初からすべての形式に対応するのではなく、基本的なショット生成・編集・レンダリングを安定させた後に拡張します。

## 将来拡張

コア機能が安定した後、必要に応じて以下を追加します。

- AI音声プラグイン
- AIリップシンク
- 効果音生成
- 効果音の自動タグ付け
- モーションライブラリ
- モーションのミックス
- ライティング設計ライブラリ
- カメラモーションライブラリ

これらはコアとなるアニメ制作パイプラインを完成させた後に検討します。

## 初期ロードマップ

### Phase 1: 基盤構築

1. 開発環境の整理
2. Unityプロジェクト構築
3. Python / AIツール環境構築
4. ComfyUI環境構築
5. 基本的なAsset管理

### Phase 2: キャラクター管理

1. Character Manager
2. CharacterProfile
3. 動画フレーム抽出
4. WD14タグ付け
5. 学習データセット生成

現在は、1-3と5の最小実装が入り、4は手動タグsidecar方式で入口を用意しています。

### Phase 3: LoRA学習

1. Kohya_ss連携
2. キャラクターLoRA学習
3. 学習結果の管理
4. ComfyUIからのLoRA利用

### Phase 4: ショット制作

1. Storyboard
2. ShotEditor
3. カメラワーク管理
4. ライティング管理
5. Draft生成

### Phase 5: 自動化

1. Shot Suggestion AI
2. RenderQueue
3. Asset Library連携
4. ショット単位の生成・管理

### Phase 6: 拡張

1. AI音声
2. リップシンク
3. 効果音
4. モーション関連機能

## 重要な制約

このプロジェクトでは、利用可能なPC性能を考慮し、**RTX 3050 6GB VRAMで実用的に動作すること**を重要な基準とします。

高性能GPUを前提とした構成をそのまま採用するのではなく、解像度・バッチサイズ・モデルサイズ・生成方法などを調整しながら、限られたVRAMで制作パイプラインを成立させます。
