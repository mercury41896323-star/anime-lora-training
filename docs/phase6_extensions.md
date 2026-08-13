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

## モーションcueを追加する

```powershell
python -m anime_studio.phase6_pipeline motion --story-id pilot_scene --shot-id shot_001 --target sample_hero --motion "small nod" --source motion_library
```

出力:

```text
storyboards/pilot_scene/motion_cues.json
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

## 次の拡張候補

- Unity importerで `phase6_manifest.json` を読み、AudioTrack / SignalTrack / AnimationTrackへ仮配置する。
- 実音声ファイルから口パクを解析するproviderを追加する。
- SFX素材の自動タグ付けとAsset Library検索へ接続する。
- motion cueをUnity TimelineのAnimationClipへ変換する。
