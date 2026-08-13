# Unity Selected Shots Importer

フェーズ5の入口として、`selected_shots.json` を Unity で読む最小 importer サンプルを追加しています。

## 目的

フェーズ4で採用した Shot だけを Unity 側へ渡し、次の制作作業に使える軽量な `SelectedShotLibrary` として管理します。

## 配置

```text
integrations/unity/Assets/AIAnimeStudio/Runtime/SelectedShotLibrary.cs
integrations/unity/Assets/AIAnimeStudio/Editor/SelectedShotsManifestImporter.cs
```

Unity Project へは `integrations/unity/Assets/AIAnimeStudio` を `Assets/AIAnimeStudio` としてコピーします。

## 読み込むファイル

```text
manifests/storyboards/<story_id>/selected_shots.json
```

このファイルは次のコマンドで作成します。

```powershell
python -m anime_studio.storyboard_cli export-selected --story-id pilot_scene
```

## Unityでの操作

1. Unityメニューで `AI Anime Studio > Import Selected Shots Manifest` を選択します。
2. `selected_shots.json` を選びます。
3. `Assets/AIAnimeStudio/Storyboards/<story_id>/SelectedShotLibrary.asset` が作成されます。
4. 採用済み画像が見つかる場合は `Assets/AIAnimeStudio/ImportedShots/<story_id>/` にコピーされます。

## 生成される情報

`SelectedShotLibrary` には、Shotごとに次の情報を保存します。

- Shot ID、順番、タイトル、キャラクターID
- 採用済み結果の元パスとUnity内コピー先
- `timeline_clip_name` と `addressable_key`
- duration、seed、width、height、steps
- prompt、negative prompt
- カメラワーク要約
- ライティング要約
- 画像の場合の `Texture2D` プレビュー参照

## まだ作らないもの

このサンプルでは、まだ Unity Timeline の自動生成やカメラ/ライト GameObject の生成は行いません。
まずは `selected_shots.json` を安全に読んで、Unity側でShot一覧を確認できる状態を作るところまです。
