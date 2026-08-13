# ComfyUI Queue

export済みworkflowをComfyUI APIへ送るための、軽量なローカルキューです。

## 目的

- ComfyUIへ送るworkflowを`queues/comfyui/jobs.json`で記録する
- `POST /prompt`への送信結果として`prompt_id`を保存する
- `GET /history/{prompt_id}`で完了状態を確認する
- RTX 3050 6GB VRAM環境でも、1件ずつ安全に送れる運用を基本にする

## 1. workflowを作る

```powershell
python -m anime_studio.cli comfyui export-workflow --character-id sample_hero
```

出力例:

```text
outputs/comfyui/sample_hero/sd15_lora_txt2img_512_with_lora.json
```

## 2. キューへ追加する

```powershell
python -m anime_studio.cli comfyui queue-add --workflow outputs/comfyui/sample_hero/sd15_lora_txt2img_512_with_lora.json
```

キューは既定で次の場所に保存されます。

```text
queues/comfyui/jobs.json
```

## 3. ComfyUIへ送る

ComfyUIをローカルで起動してから実行します。既定URLは`http://127.0.0.1:8188`です。

```powershell
python -m anime_studio.cli comfyui queue-submit
```

workflowをキュー追加と同時に送ることもできます。

```powershell
python -m anime_studio.cli comfyui queue-submit --workflow outputs/comfyui/sample_hero/sd15_lora_txt2img_512_with_lora.json
```

別のComfyUI URLを使う場合:

```powershell
python -m anime_studio.cli comfyui queue-submit --base-url http://127.0.0.1:8188
```

APIへ送らずpayloadだけ記録する場合:

```powershell
python -m anime_studio.cli comfyui queue-submit --workflow outputs/comfyui/sample_hero/sd15_lora_txt2img_512_with_lora.json --dry-run
```

## 4. キューを確認する

```powershell
python -m anime_studio.cli comfyui queue-list
```

## 5. 完了状態を確認する

`queue-submit`で表示された`job_id`を使います。

```powershell
python -m anime_studio.cli comfyui queue-refresh --job-id <job_id>
```

`prompt_id`がComfyUI履歴に見つかると、ローカルキューのstatusが`completed`になります。

## 状態

- `pending`: まだComfyUIへ送っていない
- `submitted`: ComfyUIへ送信済み
- `completed`: ComfyUI履歴で完了を確認済み
- `failed`: 送信または確認でエラー
- `dry_run`: APIへ送らずpayloadだけ記録済み

## 注意

ComfyUIで実行する前に、workflow内のcheckpoint名とLoRA名がComfyUI側から参照できることを確認してください。
