# ComfyUI Workflow Templates

このドキュメントは、LoRA manifestを使ってComfyUI workflow templateへLoRA参照を差し込むための最小手順をまとめます。

## 目的

- 登録済みLoRAをComfyUI workflowへ手作業で写さずに反映する
- RTX 3050 6GB VRAMでも確認しやすい512x512の軽量workflowから始める
- ComfyUI側で使う`lora_name`、weight、positive prompt tagをmanifestから揃える

## 付属テンプレート

最初の付属テンプレートは次のファイルです。

```text
templates/comfyui/sd15_lora_txt2img_512.json
```

このテンプレートはStable Diffusion 1.5系のtxt2img確認用です。ComfyUIの`LoraLoader`、`KSampler`、`VAEDecode`、`SaveImage`を使う最小構成にしています。

## テンプレート一覧

```powershell
python -m anime_studio.cli comfyui list-templates
```

## workflow export

`--template`を省略すると付属テンプレートを使います。

```powershell
python -m anime_studio.cli comfyui export-workflow --character-id sample_hero
```

任意のテンプレートを指定することもできます。

```powershell
python -m anime_studio.cli comfyui export-workflow --character-id sample_hero --template templates/comfyui/sd15_lora_txt2img_512.json
```

出力先:

```text
outputs/comfyui/sample_hero/sd15_lora_txt2img_512_with_lora.json
```

## 置換される主な値

- `{{character_id}}`
- `{{display_name}}`
- `{{positive_prompt_tags}}`
- `{{artifact_id}}`
- `{{prompt_tag}}`
- `{{lora_name}}`
- `{{lora_model_path}}`
- `{{lora_weight}}`
- `{{clip_weight}}`

`LoraLoader`ノードには`lora_name`、`strength_model`、`strength_clip`も自動設定されます。

## 注意

ComfyUIで実行する前に、manifest内のLoRAファイルがComfyUIの`models/loras`から参照できる状態になっているか確認してください。

## 次の手順

export済みworkflowは、軽量キューからComfyUI APIへ送れます。

```powershell
python -m anime_studio.cli comfyui queue-submit --workflow outputs/comfyui/sample_hero/sd15_lora_txt2img_512_with_lora.json
```

詳しくは`docs/comfyui_queue.md`を参照してください。
