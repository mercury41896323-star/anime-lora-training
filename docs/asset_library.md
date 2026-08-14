# Asset Library

CharacterProfileに紐づいた素材やComfyUI生成結果を横断して見るための、薄いAsset Library CLIです。

## 一覧

```powershell
python -m anime_studio.cli library list
```

キャラクター、素材種別、由来で絞り込めます。

```powershell
python -m anime_studio.cli library list --character-id sample_hero
python -m anime_studio.cli library list --kind image
python -m anime_studio.cli library list --source comfyui_result
python -m anime_studio.cli library list --query smile
```

SFX素材を登録している場合は、Phase 6のSFX cue作成時に候補検索にも使われます。
`kind` は `sfx`、`audio`、または既存分類に合わせた `other` を使えます。

```powershell
python -m anime_studio.cli library list --kind sfx --query wind
```

JSONとして確認する場合:

```powershell
python -m anime_studio.cli library list --json
```

## index出力

Unityや後続ツールから読みやすい軽量indexを書き出します。

```powershell
python -m anime_studio.cli library index
```

出力先:

```text
assets/processed/library_index.json
```

## 含まれる情報

- `character_id`
- `display_name`
- `kind`
- `source`
- `stored_path`
- `original_path`
- `size_bytes`
- `exists`
- `metadata`

この段階では検索用DBは作らず、各キャラクターの`assets.json`を読み取るだけにしています。
