# Unity Phase 6 Timeline Importer

`phase6_manifest.json` をUnityへ読み込み、Timeline上に音声、口パクSignal、効果音、モーションの仮Trackを配置するサンプルです。

## 対象ファイル

```text
integrations/unity/Assets/AIAnimeStudio/Runtime/Phase6StoryboardLibrary.cs
integrations/unity/Assets/AIAnimeStudio/Editor/Phase6ManifestImporter.cs
integrations/unity/Assets/AIAnimeStudio/Editor/Phase6TimelineBuilder.cs
```

Unity Project側では `integrations/unity/Assets/AIAnimeStudio` を `Assets/AIAnimeStudio` に置いて使います。

## 入力manifest

```text
manifests/storyboards/<story_id>/phase6_manifest.json
```

作成例:

```powershell
python -m anime_studio.phase6_pipeline export --story-id pilot_scene
```

## Unity側の手順

1. `AI Anime Studio > Import Phase 6 Manifest` を実行する。
2. `phase6_manifest.json` を選ぶ。
3. `Assets/AIAnimeStudio/Storyboards/<story_id>/Phase6StoryboardLibrary.asset` が作られる。
4. `Phase6StoryboardLibrary.asset` を選択する。
5. `AI Anime Studio > Create Timeline From Phase 6 Library` を実行する。
6. `Assets/AIAnimeStudio/Timelines/<story_id>/` にTimeline asset、仮AnimationClip、SignalAssetが作られる。

## Timelineに配置されるもの

- `Phase6_Voice_AudioTrack`: voice cueをAudioClipとして配置します。音声assetが未指定・未発見でもplaceholder clipを置きます。
- `Phase6_SFX_AudioTrack`: SFX cueをAudioClipとして配置します。
- `Phase6_LipSync_SignalTrack`: viseme cueを `SignalEmitter` として配置します。
- `Phase6_Motion_<target>`: motion cueを簡易AnimationClipとして配置します。

## 現時点の位置づけ

これは本格的な音声解析やモーション生成ではなく、Phase 6の軽量プロトタイプです。
目的は、Shot単位で決めた音声・口パク・効果音・動きがUnity Timeline上で時間配置できることを確認することです。
