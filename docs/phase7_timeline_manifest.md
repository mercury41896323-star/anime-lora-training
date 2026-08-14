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

## Unity再生成保護

Timeline Builderは、既存のTimeline assetを上書きせず、毎回次のようなrevisionフォルダへ新規生成します。

```text
Assets/AIAnimeStudio/Timelines/<story_id>/Revision_001_YYYYMMDD_HHMMSS/
```

生成後、`EditTimelineLibrary.asset` には次の情報が保存されます。

- `preserveExistingTimelineEdits`: 既存編集を守る保護モード。
- `timelineRevision`: 最後に生成したrevision番号。
- `lastGeneratedTimelineAssetPath`: 最後に作成したTimeline asset。
- `lastGeneratedRevisionFolder`: 最後に作成したrevisionフォルダ。

各revisionには `timeline_build_report.json` も出力されます。
これにより、手で調整した古いTimelineを残したまま、新しいmanifestから別Timelineを作れます。

## 外部編集export

`edit_timeline_manifest.json` から、軽量な編集受け渡しファイルを生成できます。

```powershell
python -m anime_studio.edit_export --story-id pilot_scene
```

出力:

```text
manifests/storyboards/pilot_scene/edit_exports/
```

生成されるファイル:

| file | 内容 |
| --- | --- |
| `ffmpeg_concat.txt` | FFmpeg concat demuxer向けの素材リスト |
| `timeline.edl` | CMX 3600風の簡易EDL |
| `timeline.fcpxml` | FCPXML風の簡易XML |
| `edit_export_manifest.json` | export結果の台帳 |

形式を絞る場合:

```powershell
python -m anime_studio.edit_export --story-id pilot_scene --formats ffmpeg,edl
```

## Preview movie

FFmpeg concat exportから、preview movie用の実行planを生成できます。
標準ではFFmpegを実行せず、コマンドとmanifestだけを書きます。

```powershell
python -m anime_studio.edit_preview --story-id pilot_scene
```

統合CLI:

```powershell
python -m anime_studio.cli edit preview-movie --story-id pilot_scene
```

出力:

```text
manifests/storyboards/pilot_scene/preview_movie_plan.json
outputs/previews/pilot_scene/preview.mp4
```

実際にFFmpegを実行する場合:

```powershell
python -m anime_studio.cli edit preview-movie --story-id pilot_scene --run
```

## Timeline revision review / adopt

Unity側で生成されたrevisionフォルダを確認し、採用revisionをmanifestへ記録できます。

```powershell
python -m anime_studio.cli edit revision-review --story-id pilot_scene
python -m anime_studio.cli edit revision-adopt --story-id pilot_scene
```

出力:

```text
manifests/storyboards/pilot_scene/timeline_revision_review.json
manifests/storyboards/pilot_scene/selected_timeline_revision.json
```

## 現在の完成範囲

- 採用済みShotだけを `video_main` へ出力する。
- voice/SFXをAudioTrack用clipとして出力する。
- lip-sync visemeをSignalTrack用markerとして出力する。
- motion clip planをAnimationTrack用clipとして出力する。
- Unity importer / Timeline Builderの軽量サンプルを用意する。
- Unity Timeline再生成時に既存Timelineを上書きしないrevision方式を用意する。
- FFmpeg concat / EDL / FCPXMLの軽量exportを用意する。
- FFmpeg preview movie planを生成する。
- Timeline revisionのreview/adopt manifestを生成する。
- ShotEditorにTimeline Readinessを表示する。

## 制限

- Unity側のvideo clipは、最初は画像previewまたはplaceholder GameObjectとして扱います。
- EDL/FCPXMLは初期の受け渡し用で、編集ソフト固有機能の完全対応ではありません。
- 音量フェード、BGM専用track、複数レイヤー合成は後続拡張です。

## 次の拡張候補

- Timeline revisionの差分表示をより詳細化する。
- FFmpeg preview movieに音声mixを追加する。
- BGM、環境音、音量automationを追加する。
- ローカルLoRA学習の最初の短時間runへ進む。
