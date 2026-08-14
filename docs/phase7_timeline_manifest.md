# Phase 7 Timeline Manifest

Phase 7では、採用済みShot、Phase 6 cue、motion clip planをまとめて、Unityや編集工程が読みやすい `edit_timeline_manifest.json` を生成します。
目的は、生成済み素材を同じ時間軸に並べ、Unity Timeline上でプレビューできる状態を作ることです。

## 入力

```text
manifests/storyboards/<story_id>/selected_shots.json
manifests/storyboards/<story_id>/phase6_manifest.json
manifests/storyboards/<story_id>/motion_clip_plan.json
```

`selected_shots.json` が存在しないShotは、編集Timelineには出力されません。
これは、候補生成結果ではなく「採用済み結果だけ」を編集へ渡すためです。

## 生成コマンド

```powershell
python -m anime_studio.timeline_manifest --story-id pilot_scene
```

出力:

```text
manifests/storyboards/pilot_scene/edit_timeline_manifest.json
```

frame rateを指定する場合:

```powershell
python -m anime_studio.timeline_manifest --story-id pilot_scene --frame-rate 24
```

## 出力されるtrack

| track | 内容 |
| --- | --- |
| `video_main` | 採用済みShot結果 |
| `voice_main` | voice cue |
| `sfx_main` | SFX cue |
| `lip_sync_signals` | viseme marker |
| `Phase6_Motion_<target>` | motion clip planまたはmotion cue |

すべてのclipは `start_seconds` と `duration_seconds` を持ちます。
Shot内のcue timingは、Timeline全体の絶対時間へ変換されます。

## Unity側の使い方

Unity Projectへ `integrations/unity/Assets/AIAnimeStudio` をコピーして使います。

1. `AI Anime Studio > Import Edit Timeline Manifest` を実行する。
2. `edit_timeline_manifest.json` を選択する。
3. `Assets/AIAnimeStudio/Storyboards/<story_id>/EditTimelineLibrary.asset` が作成される。
4. `EditTimelineLibrary.asset` を選択する。
5. `AI Anime Studio > Create Timeline From Edit Timeline Library` を実行する。
6. `Assets/AIAnimeStudio/Timelines/<story_id>/` にTimeline asset、SignalAsset、AnimationClipが作成される。

## 現在の完成範囲

- 採用済みShotだけを `video_main` へ出力する。
- voice/SFXをAudioTrack用clipとして出力する。
- lip-sync visemeをSignalTrack用markerとして出力する。
- motion clip planをAnimationTrack用clipとして出力する。
- Unity importer / Timeline Builderの軽量サンプルを用意する。

## 制限

- Unity側のvideo clipは、最初は画像previewまたはplaceholder GameObjectとして扱います。
- 外部編集ソフト向けEDL/XML書き出しは未実装です。
- 音量フェード、BGM専用track、複数レイヤー合成は後続拡張です。

## 次の拡張候補

- Unity Timeline上のclip再生成時に既存編集を保護する。
- FFmpeg concat / EDL / XML exportを追加する。
- BGM、環境音、音量automationを追加する。
- ShotEditorにTimeline readinessを表示する。
