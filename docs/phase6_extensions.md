# Phase 6 Extensions

Phase 6では、ショット制作の後段として音声、リップシンク、効果音、モーションを扱います。
現時点ではRTX 3050 6GB環境でも安全に扱えるように、重いAI生成処理ではなく、Shot単位の軽量cue台帳から開始します。

## 目的

- AI音声や録音済み音声をShotへ紐づける。
- 音声cueから仮の口パクタイミングを作る。
- 効果音cueをShot単位で管理する。
- キャラクターやカメラ向けのmotion cueをShot単位で管理する。
- Unityや編集ツールが読みやすい統合manifestを書き出す。

## 音声cueを追加する

```powershell
python -m anime_studio.phase6_pipeline voice --story-id pilot_scene --shot-id shot_001 --text "ありがとう" --speaker "Sample Hero" --emotion "soft" --voice-asset assets/audio/voice/shot_001.wav
```

出力:

```text
storyboards/pilot_scene/voice_cues.json
```

## 効果音cueを追加する

```powershell
python -m anime_studio.phase6_pipeline sfx --story-id pilot_scene --shot-id shot_001 --label "soft wind" --asset assets/audio/sfx/wind.wav --tags ambience,wind
```

出力:

```text
storyboards/pilot_scene/sfx_cues.json
```

`--tags` を省略した場合は、`label` と `asset` のファイル名から `wind`、`ambience`、`footstep`、`impact` などの軽量タグを自動推定します。
また、Asset Libraryに `kind: sfx` / `audio` / `other` の素材が登録されている場合、SFX cueへ `asset_library_candidates` として候補を保存します。

```powershell
python -m anime_studio.phase6_pipeline sfx --story-id pilot_scene --shot-id shot_001 --label "soft wind"
```

検索語を手動で変えたい場合:

```powershell
python -m anime_studio.phase6_pipeline sfx --story-id pilot_scene --shot-id shot_001 --label "soft wind" --asset-query "wind ambience" --asset-limit 5
```

## 効果音候補をレビュー・採用する

自動保存された `asset_library_candidates` は、すぐに確定せずレビュー用manifestへまとめられます。

```powershell
python -m anime_studio.sfx_review review --story-id pilot_scene
```

出力:

```text
manifests/storyboards/pilot_scene/sfx_asset_review.json
```

候補を採用する場合:

```powershell
python -m anime_studio.sfx_review select --story-id pilot_scene --cue-id sfx_shot_001_soft_wind --candidate-index 0
```

## モーションcueを追加する

```powershell
python -m anime_studio.phase6_pipeline motion --story-id pilot_scene --shot-id shot_001 --target sample_hero --motion "small nod" --source motion_library
```

出力:

```text
storyboards/pilot_scene/motion_cues.json
```

## motion cueからAnimationClip設計図を作る

`motion_cues.json` からUnity AnimationClip向けの軽量なkeyframe planを生成します。
実際のUnity assetを直接作る前に、Shot単位の動き、対象track、仮keyframeを確認できます。

```powershell
python -m anime_studio.motion_clip_plan --story-id pilot_scene
```

出力:

```text
manifests/storyboards/pilot_scene/motion_clip_plan.json
```

## 口パク計画を作る

音声cueの `text` と `duration_seconds` から、仮のvisemeタイミングを生成します。
これは本格的な音声解析ではなく、Unity上で確認するためのplaceholderです。

```powershell
python -m anime_studio.phase6_pipeline lip-sync --story-id pilot_scene
```

出力:

```text
storyboards/pilot_scene/lip_sync_plan.json
```

## 実音声WAVから口パク計画を作る

録音済み、または生成済みの `.wav` 音声が `voice_asset_path` に紐づいている場合は、軽量なWAV RMS解析providerを使えます。
GPUや外部AIモデルは使わず、音声の長さと音量変化から仮のviseme timingを作ります。

```powershell
python -m anime_studio.phase6_pipeline lip-sync --story-id pilot_scene --provider wav-rms
```

出力される `lip_sync_plan.json` には、`method: wav_rms_viseme_timing`、`provider: wav-rms`、`analysis.sample_rate`、`analysis.window_count` などが入ります。
`.wav` が見つからない場合や未対応形式の場合は、従来のテキストplaceholderへ安全にfallbackします。

## Unity / 編集用manifestへ統合する

```powershell
python -m anime_studio.phase6_pipeline export --story-id pilot_scene
```

出力:

```text
manifests/storyboards/pilot_scene/phase6_manifest.json
```

このmanifestには、Shotごとに次の情報がまとまります。

- 採用済みShot結果
- voice cues
- lip-sync cues
- SFX cues
- motion cues
- Unity Timeline向けtrack hint

## Unity Timeline連携

`phase6_manifest.json` をUnity側で読み込み、`AudioTrack`、`SignalTrack`、`AnimationTrack` へ仮配置するサンプルを追加しています。
詳しくは `docs/unity_phase6_timeline.md` を参照してください。

## 次の拡張候補

- motion clip planをUnity Timeline Builder側のAnimationClip生成へ接続する。
