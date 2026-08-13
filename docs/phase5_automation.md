# Phase 5 Automation

Phase 5では、ショット制作で増えていく判断とファイルを軽く自動整理することを目的にします。
Phase 6の音声・リップシンク・効果音へ進む前に、Storyboardから生成、確認、採用、Unity連携までの足場を安定させます。

## 実装済み

- Shot Suggestion AI: Storyboard、カメラワーク、ライティング、Shot結果を読み、生成前の準備状況を提案JSONにします。
- ShotEditor連携: 生成済み `shot_suggestions.json` がある場合、ShotEditor HTML上で各Shotの準備度と改善候補を確認できます。
- RenderQueue: export済みComfyUI workflowをローカルキューへ積み、ComfyUI APIへ送る入口を用意しています。
- Asset Library連携: CharacterProfile由来の素材を薄いCLIで一覧・検索できます。
- ショット単位の生成・管理: 生成結果の紐づけ、採用・没管理、preview、selected_shots manifest出力まで接続済みです。
- Unity連携: selected_shots manifestを読み、Timeline Clip、仮カメラ、仮ライト、簡易カメラ移動、任意Cinemachine Virtual Cameraを配置できます。

## Shot Suggestion AI

```powershell
python -m anime_studio.storyboard_suggestions --story-id pilot_scene
```

出力:

```text
storyboards/pilot_scene/shot_suggestions.json
```

レポートには次の情報が入ります。

- `readiness_score`: 生成・採用へ進める準備度。
- `risk_level`: `ready`、`needs_attention`、`blocked` の3段階。
- `missing`: 足りないStoryboard情報。
- `quality_flags`: 6GB VRAM環境で注意したい生成条件。
- `prompt_additions`: カメラワーク・ライティングからpromptへ追加しやすい語句。
- `suggestions`: 次に直す作業の短い提案。

## Phase 6へ入る前の残り候補

- RenderQueueの複数Shotバッチ確認ビューを追加する。
- 生成済み候補の品質メモを、採用判断と一緒に一覧できるようにする。
