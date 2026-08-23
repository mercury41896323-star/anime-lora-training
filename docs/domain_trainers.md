# Domain Trainers

動画解析から保存したmotion・camera・background・lighting datasetを、2.5DアニメーションとB-controlで使える軽量modelへ変換します。

## 目的

RTX 3050 6GB環境でまず検証できるように、`baseline` providerはCPUだけで動く統計prior trainerです。重いニューラル学習を開始する前に、datasetの不足、タグの偏り、Shot間の連続性を確認できます。ニューラル版は`anime-neural-trainer`で別ジョブとして準備します。

## 一括学習

```powershell
anime-domain-trainer train-all `
  --character-id your_character `
  --video-id your_video_id
```

個別実行:

```powershell
anime-domain-trainer train --character-id your_character --video-id your_video_id --domain motion
anime-domain-trainer train --character-id your_character --video-id your_video_id --domain camera
anime-domain-trainer train --character-id your_character --video-id your_video_id --domain background
anime-domain-trainer train --character-id your_character --video-id your_video_id --domain lighting
```

## 各trainer

### Motion Trainer

- 顔向き、表情、body framingの遷移回数を学習
- 平均フレーム遷移時間を保存
- 2.5D keyframe間の動きとLoRA in-between補完に利用
- 公式AnimateDiff学習ジョブproviderへ接続済み

### Camera Trainer

- close-up、medium、full-body等の距離分布を学習
- 顔向きとShot境界傾向を保存
- Storyboard / B-controlのカメラ候補に利用
- 小型PyTorch camera trajectory adapterを実装済み

### Background Trainer

- 背景タグの頻度と推奨タグを学習
- 人物segmentationが必要な割合を保存
- 背景候補とscene styleのpriorとして利用
- 人物除去済み画像を入力にするKohya Background LoRA jobを実装済み

### Lighting Trainer

- light、shadow、rim、night、warm/cool等の分布を学習
- Shot単位のlighting profileを保存
- Shot間のライティング連続性に利用
- 画像の色統計とlighting tagを学習する軽量Relighting providerを実装済み

## 保存先

```text
models/domain/<character_id>/<video_id>/
├─ motion/
│  ├─ trainer_config.json
│  ├─ baseline_model.json
│  └─ trainer_manifest.json
├─ camera/
├─ background/
├─ lighting/
└─ domain_trainer_bundle.json
```

学習済みmodelはCharacterProfileの`domain_models`へ自動登録されます。StoryboardをB-controlでexportすると、2.5D Definitionと一緒に`learned_domain_models`としてworkflowへ渡されます。

## 現在の実装範囲

- baseline providerは実行可能なCPU軽量trainer
- datasetが空の場合は`needs_data` modelを生成して学習不足を可視化
- B-control / ComfyUI workflowへのmodel参照を実装
- Camera / Relightingはrepo内の小型PyTorch trainerでweight学習可能
- Background LoRAはKohya sd-scripts用の実行設定を生成可能
- AnimateDiffは公式trainer用dataset/configを生成するが、6GB VRAMでは安全停止する

詳細は`docs/neural_trainers.md`を参照してください。
