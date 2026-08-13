# Storyboard / Shot Management

Storyboard は、キャラクター・LoRA・ComfyUI workflow・生成結果を「カット単位」でつなぐための軽量な制作台帳です。
まだ映像編集ツールではなく、RTX 3050 6GB 環境でも扱いやすい最小構成を目指します。

## Storyboard を作る

```powershell
python -m anime_studio.cli storyboard init --id pilot_scene --title "Pilot Scene"
```

出力先:

```text
storyboards/pilot_scene/storyboard.json
```

## Shot を追加する

```powershell
python -m anime_studio.cli storyboard add-shot --story-id pilot_scene --shot-id shot_001 --title "Opening close-up" --character-id sample_hero --prompt "sample_hero, close-up, soft light" --duration 2.5 --camera "close-up" --lighting "soft light"
```

Shot には次の情報を保存します。

- `shot_id`
- `order`
- `title`
- `character_id`
- `prompt`
- `duration_seconds`
- `camera`
- `lighting`
- `notes`

## Shot を一覧する

```powershell
python -m anime_studio.cli storyboard list --story-id pilot_scene
```

JSON で確認する場合:

```powershell
python -m anime_studio.cli storyboard list --story-id pilot_scene --json
```

## Storyboard から ComfyUI workflow を生成する

各 Shot の `character_id` を使い、登録済み LoRA manifest から ComfyUI workflow を 1 Shot につき 1 つ生成します。
Shot の `prompt`、`camera`、`lighting` は positive prompt に追記されます。

```powershell
python -m anime_studio.cli storyboard export-comfyui --story-id pilot_scene
```

出力先:

```text
outputs/comfyui/storyboards/pilot_scene/001_shot_001.json
outputs/comfyui/storyboards/pilot_scene/storyboard_workflows.json
```

`character_id` が未設定の Shot や、LoRA が未登録の Shot はスキップされ、`storyboard_workflows.json` の `skipped_shots` に理由が残ります。

## 生成と同時にキュー登録する

ComfyUI API へ投げる前段のローカルキューへ、生成済み workflow をまとめて登録できます。

```powershell
python -m anime_studio.cli storyboard export-comfyui --story-id pilot_scene --queue
```

キュー:

```text
queues/comfyui/jobs.json
```

実際に ComfyUI API へ送信する場合は、既存の queue コマンドを使います。

```powershell
python -m anime_studio.cli comfyui queue-submit --job-id <job_id>
```

## Shot へ生成結果を紐づける

手動で画像や動画を Shot に紐づける場合:

```powershell
python -m anime_studio.storyboard_cli link-result --story-id pilot_scene --shot-id shot_001 --result outputs/manual/opening.png
```

ComfyUI から取り込んだ結果を、workflow metadata の `story_id` / `shot_id` を使って自動で紐づける場合:

```powershell
python -m anime_studio.storyboard_cli link-comfyui-results --job-id <job_id>
```

出力先:

```text
storyboards/pilot_scene/shot_results.json
```

同じ結果を再登録しようとした場合は重複としてスキップされます。

## Shot の生成結果を一覧する

```powershell
python -m anime_studio.storyboard_cli results --story-id pilot_scene
```

特定 Shot だけ見る場合:

```powershell
python -m anime_studio.storyboard_cli results --story-id pilot_scene --shot-id shot_001
```

JSON で確認する場合:

```powershell
python -m anime_studio.storyboard_cli results --story-id pilot_scene --json
```

## 次の拡張候補

- Shot ごとの採用結果フラグ
- Shot ごとの negative prompt
- Shot ごとの seed / width / height / steps
- Shot 生成結果のプレビューHTML
- Unity Timeline 向け manifest 出力
