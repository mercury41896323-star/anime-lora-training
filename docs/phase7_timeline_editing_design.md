# Phase 7 Timeline Editing Design

Phase 7は、Phase 4〜6で作ったShot、生成結果、音声、SFX、口パク、モーションを編集用Timelineへ組み上げる段階です。
ここでは本格的な動画編集ソフト連携より先に、Unity Timelineと軽量JSON manifestを中心に、低リスクな編集パイプラインを作ります。

## 目的

- 採用済みShot結果だけを編集ラインへ並べる。
- voice、SFX、lip-sync signal、motion clipを同じ時間軸で扱う。
- Unity Timelineでプレビューできる状態を作る。
- 後からPremiere、DaVinci Resolve、FFmpeg concatなどへ拡張できる中立的なEdit Decision Listを持つ。

## 入力

Phase 7の入口は次のmanifestです。

- `manifests/storyboards/<story_id>/selected_shots.json`
- `manifests/storyboards/<story_id>/phase6_manifest.json`
- `manifests/storyboards/<story_id>/motion_clip_plan.json`
- `manifests/storyboards/<story_id>/sfx_asset_review.json`

必須入力は `selected_shots.json` と `phase6_manifest.json` です。
補助manifestが存在しない場合は、Phase6 manifest内のcue情報だけでfallbackします。

## 出力

最初に作る出力は `edit_timeline_manifest.json` です。

```text
manifests/storyboards/<story_id>/edit_timeline_manifest.json
```

想定schema:

```json
{
  "schema_version": 1,
  "manifest_type": "storyboard_edit_timeline",
  "story": {
    "story_id": "pilot_scene",
    "title": "Pilot Scene"
  },
  "settings": {
    "frame_rate": 24,
    "timeline_unit": "seconds"
  },
  "tracks": [
    {
      "track_id": "video_main",
      "track_type": "video",
      "clips": []
    },
    {
      "track_id": "voice_main",
      "track_type": "audio",
      "clips": []
    },
    {
      "track_id": "sfx_main",
      "track_type": "audio",
      "clips": []
    },
    {
      "track_id": "lip_sync_signals",
      "track_type": "signal",
      "clips": []
    },
    {
      "track_id": "motion_sample_hero",
      "track_type": "animation",
      "clips": []
    }
  ]
}
```

## track設計

| track | 内容 | 初期実装 |
| --- | --- | --- |
| `video_main` | 採用済みShot画像/動画 | selected result pathをclip化 |
| `voice_main` | 台詞/ナレーション | voice cueをclip化 |
| `sfx_main` | 効果音 | 採用済みSFX assetをclip化 |
| `lip_sync_signals` | 口パクmarker | viseme cueをmarker化 |
| `motion_<target>` | キャラ/カメラmotion | motion clip planをclip化 |
| `notes` | 制作メモ | 後続候補 |

## 時間計算

Phase 7ではShot順に `timeline_start_seconds` を割り当てます。

1. Storyboard order順にShotを並べる。
2. 各Shotの `duration_seconds` を使ってcursorを進める。
3. cueの `start_seconds` はShot内相対時間として扱う。
4. Timeline上の絶対時間は `shot_start_seconds + cue.start_seconds` にする。
5. durationが未指定または0の場合は、Shot durationまたは1秒へfallbackする。

## Edit clip共通フィールド

すべてのtrack clipは次の共通形を持ちます。

```json
{
  "clip_id": "video_shot_001",
  "shot_id": "shot_001",
  "source_type": "selected_shot",
  "source_path": "assets/processed/...",
  "start_seconds": 0.0,
  "duration_seconds": 3.0,
  "metadata": {}
}
```

## 実装モジュール案

### `timeline_manifest.py`

Python側で `edit_timeline_manifest.json` を作るモジュールです。

想定API:

```python
build_edit_timeline_manifest(settings, story_id, frame_rate=24)
```

責務:

- selected shotsを読む。
- phase6 manifestを読む。
- motion clip planを読む。
- trackごとにclipを組み立てる。
- Unity/編集ツールに依存しないJSONを出す。

### Unity `EditTimelineManifestImporter`

Unity側で `edit_timeline_manifest.json` を読み、ScriptableObject化します。

責務:

- JSONをUnity assetに変換する。
- video/audio/animation/signal clipの参照を保持する。
- assetが見つからない場合もplaceholderとして保持する。

### Unity `EditTimelineBuilder`

ScriptableObjectからTimelineAssetを作ります。

責務:

- `video_main` をActivationTrackまたはPlayableTrackへ仮配置する。
- `voice_main` / `sfx_main` をAudioTrackへ配置する。
- `lip_sync_signals` をSignalTrackへ配置する。
- `motion_<target>` をAnimationTrackへ配置する。

## 最小プロトタイプ

最初の実装では、次だけを扱います。

1. `selected_shots.json` からvideo clipを作る。
2. `phase6_manifest.json` からvoice/SFX/lip-sync/motion clipを作る。
3. `motion_clip_plan.json` があればmotion keyframe情報をmetadataへ入れる。
4. `edit_timeline_manifest.json` を出す。
5. Pythonテストでtrack数、clip数、時間計算を確認する。

Unity側の実asset生成は、Python側manifestが固まった後に進めます。

## 実装済みの最小範囲

Phase 7の最小プロトタイプとして、次を実装済みです。

- `src/anime_studio/timeline_manifest.py`: `edit_timeline_manifest.json` を生成する。
- `tests/test_timeline_manifest.py`: 採用済みShotだけが出ること、track分割、時間計算、補助manifest参照を検証する。
- `integrations/unity/Assets/AIAnimeStudio/Runtime/EditTimelineLibrary.cs`: Unity側で編集Timeline manifestを保持する。
- `integrations/unity/Assets/AIAnimeStudio/Editor/EditTimelineManifestImporter.cs`: `edit_timeline_manifest.json` をUnity assetへ変換する。
- `integrations/unity/Assets/AIAnimeStudio/Editor/EditTimelineBuilder.cs`: video/audio/signal/animation trackをTimelineへ仮配置する。

## Phase 7完了条件

- Storyboardの採用済みShotだけがTimeline manifestへ出る。
- Shot durationに沿ってclipの開始時間が連続する。
- 音声、SFX、口パク、motionがShot内相対時間からTimeline絶対時間へ変換される。
- Unity側でTimelineを再生成しても、既存manifestを壊さない。
- GPUを使わずに全体の構造検証ができる。

## 後続拡張

- FFmpeg用concat list/export。
- Premiere/DaVinci向けEDL/XML書き出し。
- Shotごとの編集メモ、NG理由、差し替え履歴。
- 音量、フェード、BGM track、環境音track。
- Unity RecorderやComfyUI render queueとの連携。
