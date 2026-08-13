# Unity Selected Shots Importer

`selected_shots.json` を Unity 側で読み、採用済み Shot を `SelectedShotLibrary` ScriptableObject として取り込む最小サンプルです。

この段階では Timeline を自動生成しません。まずは、AI Anime Studio が出力した Shot 順・採用画像・尺・カメラ・ライティング情報を Unity Project 内で参照できる状態にします。

## 使い方

1. `integrations/unity/Assets/AIAnimeStudio` を Unity Project の `Assets/AIAnimeStudio` へコピーします。
2. Unity メニューから `AI Anime Studio > Import Selected Shots Manifest` を選びます。
3. AI Anime Studio 側で出力した `manifests/storyboards/<story_id>/selected_shots.json` を選択します。
4. `Assets/AIAnimeStudio/Storyboards/<story_id>/SelectedShotLibrary.asset` が作成されます。

## 取り込む内容

- Shot ID / 並び順 / タイトル / キャラクターID
- 採用済み生成結果のパス
- Unity向け `timeline_clip_name` / `addressable_key`
- 尺、seed、width、height、steps
- prompt / negative prompt
- カメラワークとライティングの要約
- 画像ファイルが見つかった場合の `Texture2D` プレビュー参照

## 低VRAM開発での位置づけ

ComfyUIで大量生成せず、まず採用済みの軽いShot単位manifestだけをUnityへ渡します。Unity側では画像参照と順序を確認するだけなので、RTX 3050 6GB 環境でも制作の足場として扱いやすい構成です。

## 次の拡張候補

- `SelectedShotLibrary` から Timeline Clip を自動配置する
- Shotごとの仮カメラ GameObject を生成する
- ライティング情報から Light プリセットを作る
