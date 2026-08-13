# Unity Selected Shots Importer

`selected_shots.json` を Unity 側で読み、採用済み Shot を `SelectedShotLibrary` ScriptableObject として取り込む最小サンプルです。

この段階では Timeline を自動生成しません。まずは、AI Anime Studio が出力した Shot 順・採用画像・尺・カメラ・ライティング情報を Unity Project 内で参照できる状態にします。

## 使い方

1. `integrations/unity/Assets/AIAnimeStudio` を Unity Project の `Assets/AIAnimeStudio` へコピーします。
2. Unity メニューから `AI Anime Studio > Import Selected Shots Manifest` を選びます。
3. AI Anime Studio 側で出力した `manifests/storyboards/<story_id>/selected_shots.json` を選択します。
4. `Assets/AIAnimeStudio/Storyboards/<story_id>/SelectedShotLibrary.asset` が作成されます。
5. `SelectedShotLibrary.asset` を選択した状態で `AI Anime Studio > Create Timeline From Selected Shot Library` を選びます。
6. `Assets/AIAnimeStudio/Timelines/<story_id>/` に Timeline asset が作成され、Scene に `PlayableDirector` 付きの親Objectが配置されます。

Timeline生成には Unity の Timeline package が必要です。

## 取り込む内容

- Shot ID / 並び順 / タイトル / キャラクターID
- 採用済み生成結果のパス
- Unity向け `timeline_clip_name` / `addressable_key`
- 尺、seed、width、height、steps
- prompt / negative prompt
- カメラワークとライティングの要約
- 画像ファイルが見つかった場合の `Texture2D` プレビュー参照

## Timeline生成

`Create Timeline From Selected Shot Library` は、Shot順に `ActivationTrack` を作り、各Shotの `durationSeconds` に合わせてClipを自動配置します。

画像プレビューがあるShotは `SpriteRenderer` 付きの子Objectとして配置されます。画像がないShotは、タイトルだけの簡易 `TextMesh` を置きます。

この実装は「編集開始用の仮Timeline」を作るためのものです。正式なカメラ演出やUnity Timelineの最終編集は、この仮配置を土台に調整します。

## 低VRAM開発での位置づけ

ComfyUIで大量生成せず、まず採用済みの軽いShot単位manifestだけをUnityへ渡します。Unity側では画像参照と順序を確認するだけなので、RTX 3050 6GB 環境でも制作の足場として扱いやすい構成です。

## 次の拡張候補

- Shotごとの仮カメラ GameObject を生成する
- ライティング情報から Light プリセットを作る
- Timeline Clip にShotメモやpromptを表示する
