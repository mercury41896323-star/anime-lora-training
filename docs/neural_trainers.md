# Neural Domain Trainers

動画解析datasetから、Motion・Background・Camera・Lightingのニューラル学習ジョブを準備します。重い処理を勝手に開始せず、`prepare`、学習、`register`の3段階に分けています。

## Provider一覧

| Domain | Provider | 学習方式 | RTX 3050 6GB |
|---|---|---|---|
| motion | `animatediff_motion_module_job` | 公式AnimateDiff用CSV/YAML/起動script | 設定生成のみ。学習は安全停止 |
| background | `background_lora` | Kohya sd-scripts SD1.5 LoRA | 人物除去済み画像があれば実行候補 |
| camera | `camera_trajectory_adapter` | repo内の小型PyTorch MLP | 実行可能 |
| lighting | `relighting_provider` | RGB統計からlighting tagを推定する小型PyTorch MLP | 実行可能 |

`relighting_provider`は画像を直接描き直す拡散Relightingモデルではありません。B-controlへ照明条件を渡す軽量condition providerです。画像変換型へ進む場合は、source/targetのペア画像を用意してControlNet等へ置き換えます。

## 追加依存

通常のCLI環境を壊さないため、PyTorch依存を分離しています。

```powershell
pip install -r requirements-neural.txt
```

CUDA版PyTorchはPC環境に合う公式手順を優先してください。

## Camera / Relighting

準備:

```powershell
anime-neural-trainer prepare --character-id your_character --video-id your_video --domain camera
anime-neural-trainer prepare --character-id your_character --video-id your_video --domain lighting
```

生成された`models/neural/<character>/<video>/<domain>/run_train.ps1`を実行します。weight生成後に登録します。

```powershell
anime-neural-trainer register --character-id your_character --video-id your_video --domain camera
anime-neural-trainer register --character-id your_character --video-id your_video --domain lighting
```

## Background LoRA

背景datasetの各entryに、人間が確認した人物除去済み画像の`segmented_image_path`が必要です。元画像をそのまま使うとキャラクターを背景LoRAへ混入させるため、既定では停止します。

```powershell
anime-neural-trainer prepare `
  --character-id your_character `
  --video-id your_video `
  --domain background `
  --pretrained-model "C:\path\to\sd15" `
  --trainer-root "C:\path\to\sd-scripts"
```

動作確認だけで未segmentation画像を許可する場合は`--allow-unsegmented-background`を追加できます。本学習には推奨しません。

## AnimateDiff Motion

公式trainerが要求するMP4とCSV形式に合わせてmotion module学習設定を作ります。公式reference trainerにはMotionLoRA専用の公開学習recipeがないため、現時点ではMotionLoRA互換weightの生成完了とは扱いません。

```powershell
anime-neural-trainer prepare `
  --character-id your_character `
  --video-id your_video `
  --domain motion `
  --source-video "C:\path\to\source.mp4" `
  --pretrained-model "C:\path\to\stable-diffusion-v1-5" `
  --trainer-root "C:\path\to\AnimateDiff"
```

公式AnimateDiffのmotion moduleは大きく、RTX 3050 6GB向けの安全範囲を超えるため、現在のruntime profileでは`blocked`になります。生成YAMLは256px、8 frames、batch 1、gradient checkpointingの低負荷寄りですが、12GB以上の別GPUまたはクラウド環境で検証してください。

## 登録とB-control

`register`はweightの存在を確認してから`model_descriptor.json`をCharacterProfileの`domain_models`へ登録します。StoryboardのB-control exportはprovider名、weightパス、runtime contract、互換性情報を`learned_domain_models`として参照します。
