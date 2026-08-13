# Storyboard / Shot Management

Phase 4に入るための最小Storyboard / Shot管理です。

## Storyboardを作る

```powershell
python -m anime_studio.cli storyboard init --id pilot_scene --title "Pilot Scene"
```

出力先:

```text
storyboards/pilot_scene/storyboard.json
```

## Shotを追加する

```powershell
python -m anime_studio.cli storyboard add-shot --story-id pilot_scene --shot-id shot_001 --title "Opening close-up" --character-id sample_hero --prompt "sample_hero, close-up, soft light" --duration 2.5 --camera "close-up" --lighting "soft light"
```

Shotには次の情報を保存できます。

- `shot_id`
- `order`
- `title`
- `character_id`
- `prompt`
- `duration_seconds`
- `camera`
- `lighting`
- `notes`

## Shot一覧

```powershell
python -m anime_studio.cli storyboard list --story-id pilot_scene
```

JSONで確認する場合:

```powershell
python -m anime_studio.cli storyboard list --story-id pilot_scene --json
```

## 次の拡張候補

- ShotごとのComfyUI workflow生成
- Shotごとの生成結果リンク
- カメラ・ライティング・構図プリセット
- Unity Timeline向けmanifest出力
