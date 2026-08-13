# Character Profiles

Character profiles are small JSON files that keep character identity stable before any LoRA training begins.

## Location

Profiles are written under:

```text
assets/processed/characters/<character_id>/profile.json
```

Generated frames for that character will later live beside the profile:

```text
assets/processed/characters/<character_id>/frames/
```

## Create a Profile

```powershell
python -m anime_studio.cli character init --id sample_hero --name "Sample Hero" --trigger-tag sample_hero
```

Keep `character_id` short, lowercase, and stable. It is intended for filenames, dataset paths, and future LoRA metadata.

## Plan Frame Extraction

```powershell
python -m anime_studio.cli frames --video assets/raw/sample.mp4 --character-id sample_hero --fps 1 --dry-run
```

Remove `--dry-run` after installing FFmpeg and confirming the command looks correct.

## Register an Asset

```powershell
python -m anime_studio.cli character register-asset --id sample_hero --source assets/raw/sample.png
```

Registered files are copied into the character workspace under `assets/processed/characters/<character_id>/sources/`.

## Editable Tags

```powershell
python -m anime_studio.cli tags auto --character-id sample_hero
python -m anime_studio.cli tags manual --character-id sample_hero --add-tag blue_hair
python -m anime_studio.cli tags finalize --character-id sample_hero
```

Auto tags are saved separately from manual edits so tags can be regenerated later without losing human corrections.

To use WD14 instead of the lightweight baseline provider:

```powershell
pip install -r requirements-wd14.txt
python -m anime_studio.cli tags auto --character-id sample_hero --provider wd14
```
