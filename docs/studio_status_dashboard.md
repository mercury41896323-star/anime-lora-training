# Anime Studio Status Dashboard

制作環境、キャラクター、Storyboard / Timelineの準備状況を1画面で確認するための軽量ダッシュボードです。

## 起動

PowerShellでプロジェクトのフォルダーを開き、次を実行します。

```powershell
.\.venv\Scripts\anime-studio.exe status --open
```

または次の補助スクリプトを実行します。

```powershell
.\scripts\open_studio_status.ps1
```

ComfyUIを起動してから実行すると、GPUとComfyUI APIも確認します。ComfyUIを起動していない状態でファイルだけ確認する場合は、`--no-live`を付けます。

```powershell
.\.venv\Scripts\anime-studio.exe status --no-live --open
```

## 出力

- `outputs/status/anime_studio_status.html`: 人が確認する画面
- `outputs/status/anime_studio_status.json`: 自動処理や将来のUIが読むデータ

## 表示内容

- Python、Git、FFmpeg、NVIDIA GPU、ComfyUIの検出状態
- Simple 2.5D workflowに必要なComfyUI Node 11種類
- IPAdapter入りworkflowがある場合の拡張Node、Plus Face model、CLIP Vision model
- RTX 3050 6GB向け低VRAM設定
- CharacterProfile、2.5D Definition、Rig承認、生成readiness
- LoRA学習readiness、画像数、素材利用権確認
- 動画ごとのClean Frame人間確認待ち
- Shot結果、採用Shot、Phase 6、Edit Timelineの準備状況
- 次に行う作業

`warning`は制作を完全には止めません。`blocked`が表示された場合は、停止要因を解消してから重い生成や学習を開始します。
