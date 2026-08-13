# Storyboard / Shot Management

Storyboard は、キャラクター・LoRA・ComfyUI workflow・生成結果を「カット単位」でつなぐための軽量な制作台帳です。まだ映像編集ツールではなく、RTX 3050 6GB 環境でも扱いやすい最小構成を目指します。

## Storyboard を作る

```powershell
python -m anime_studio.storyboard_cli init --id pilot_scene --title "Pilot Scene"
```

出力先:

```text
storyboards/pilot_scene/storyboard.json
```

## Shot を追加する

```powershell
python -m anime_studio.storyboard_cli add-shot --story-id pilot_scene --shot-id shot_001 --title "Opening close-up" --character-id sample_hero --prompt "sample_hero, close-up, soft light" --duration 2.5 --camera "close-up" --lighting "soft light"
```

Shot ごとの生成条件を固定したい場合:

```powershell
python -m anime_studio.storyboard_cli add-shot --story-id pilot_scene --shot-id shot_002 --title "Reaction" --character-id sample_hero --prompt "surprised face" --negative-prompt "blurry, low quality" --seed 12345 --width 640 --height 384 --steps 18
```

Shot には次の情報を保存します。

- `shot_id`
- `order`
- `title`
- `character_id`
- `prompt`
- `negative_prompt`
- `duration_seconds`
- `camera`
- `lighting`
- `seed`
- `width`
- `height`
- `steps`
- `notes`

## Shot を一覧する

```powershell
python -m anime_studio.storyboard_cli list --story-id pilot_scene
```

JSON で確認する場合:

```powershell
python -m anime_studio.storyboard_cli list --story-id pilot_scene --json
```

## カメラワークを管理する

Shotごとの構図、カメラ移動、レンズ、角度、フォーカスを軽量JSONとして保存します。

```powershell
python -m anime_studio.storyboard_cli camera --story-id pilot_scene --shot-id shot_001 --framing "close-up" --movement "slow dolly in" --lens-mm 35 --angle "eye level" --focus "shallow depth of field"
```

出力先:

```text
storyboards/pilot_scene/camera_work.json
```

## ライティングを管理する

Shotごとのキーライト、フィルライト、リムライト、ムード、時間帯、色味を軽量JSONとして保存します。

```powershell
python -m anime_studio.storyboard_cli lighting --story-id pilot_scene --shot-id shot_001 --key-light "soft key light" --fill-light "low fill" --mood "warm hopeful mood" --time-of-day "morning" --color-palette "amber and blue"
```

出力先:

```text
storyboards/pilot_scene/lighting_setups.json
```

## Storyboard から ComfyUI workflow を生成する

各 Shot の `character_id` を使い、登録済み LoRA manifest から ComfyUI workflow を 1 Shot につき 1 つ生成します。
Shot の `prompt`、`camera`、`lighting` は positive prompt に追記されます。
`negative_prompt`、`seed`、`width`、`height`、`steps` が設定されている場合は、ComfyUI workflow の該当ノードにも反映されます。
`camera_work.json` と `lighting_setups.json` の内容も positive prompt と workflow metadata に反映されます。

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

出力先:

```text
outputs/comfyui/storyboards/pilot_scene/001_shot_001.json
outputs/comfyui/storyboards/pilot_scene/storyboard_workflows.json
queues/comfyui/jobs.json
```

実際に ComfyUI API へ送信する場合は、既存の queue コマンドを使います。

```powershell
python -m anime_studio.cli comfyui queue-submit --job-id <job_id>
```

## ドラフト生成計画を作る

実際にComfyUIへ投げる前に、Shotごとのprompt、negative prompt、seed、サイズ、steps、カメラ、ライティングをまとめたドラフト生成計画を作れます。
RTX 3050 6GB向けに、未指定のShotは `512x512 / steps 20 / batch 1` を既定値にします。

```powershell
python -m anime_studio.storyboard_cli draft-plan --story-id pilot_scene
```

出力先:

```text
storyboards/pilot_scene/draft_generation_plan.json
```

`character_id` がないShotは `skipped_shots` に残ります。

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

## Shot 結果を採用・保留・没にする

Shot result は次の 3 状態を持ちます。

- `candidate`: 候補
- `selected`: 採用
- `rejected`: 没

採用する場合:

```powershell
python -m anime_studio.storyboard_cli decide-result --story-id pilot_scene --result-id shot_001-xxxxxxxxxx --decision selected --notes "表情がよい"
```

没にする場合:

```powershell
python -m anime_studio.storyboard_cli decide-result --story-id pilot_scene --result-id shot_001-xxxxxxxxxx --decision rejected --notes "構図が弱い"
```

同じ Shot で別の結果を `selected` にすると、以前の採用結果は自動で `candidate` に戻ります。

## Shot の生成結果を一覧する

```powershell
python -m anime_studio.storyboard_cli results --story-id pilot_scene
```

特定 Shot だけを見る場合:

```powershell
python -m anime_studio.storyboard_cli results --story-id pilot_scene --shot-id shot_001
```

JSON で確認する場合:

```powershell
python -m anime_studio.storyboard_cli results --story-id pilot_scene --json
```

## Storyboard プレビュー HTML を作る

Shot ごとの候補・採用・没をブラウザで確認できる軽量 HTML を書き出します。

```powershell
python -m anime_studio.storyboard_cli preview --story-id pilot_scene
```

出力先:

```text
storyboards/pilot_scene/preview.html
```

## 採用済み Shot だけを Unity / 編集用 manifest へ出力する

`selected` になっている Shot result だけを、Shot 順に並べた軽量 JSON として書き出します。
Unity Timeline や外部編集ツールは、この manifest を読むことで「どの Shot にどの生成結果を使うか」を判断できます。
カメラワークとライティング台帳がある場合は、それらも各Shotに含まれます。

```powershell
python -m anime_studio.storyboard_cli export-selected --story-id pilot_scene
```

出力先:

```text
manifests/storyboards/pilot_scene/selected_shots.json
```

まだ採用結果がない Shot は `missing_shots` に残ります。

## 軽量 ShotEditor HTML を作る

Storyboard 全体の Shot 設定、候補、採用結果、未採用 Shot をブラウザで確認できる静的 HTML を書き出します。
カメラワークとライティングも同じ画面で確認できます。
編集そのものは JSON / CLI で行い、この HTML は確認用の薄いUIとして使います。

```powershell
python -m anime_studio.storyboard_cli editor --story-id pilot_scene
```

出力先:

```text
storyboards/pilot_scene/editor.html
```

## 次の拡張候補

- Unity 側 importer サンプル
- ShotEditor の簡易フォーム化
