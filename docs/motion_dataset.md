# Motion Dataset

`motion dataset` は、Storyboard の採用済みShot・Phase 6 motion cue・B-control 情報から、将来のモーション学習や連続生成検証に使う台帳を作るための dataset です。

## コマンド

```powershell
anime-studio dataset build-motion --story-id pilot_scene
```

## 出力

標準では次を出力します。

```text
datasets/motion/<story-id>/
  assets/
  captions/
  entries.jsonl
  transitions.jsonl

manifests/storyboards/<story-id>/motion_dataset_manifest.json
```

## entries

各 `motion cue` ごとに次のような情報を持ちます。

- shot id
- character id
- target
- motion
- duration / intensity
- selected result asset
- camera / lighting
- B-control hints
- caption tags

## transitions

隣接する採用済みShotを比較し、次の変化を記録します。

- face direction
- camera angle
- lighting direction
- from / to asset
- B-control が必要かどうか

これにより、単独の動きだけでなく、**ショット間の連続性** も dataset として確認できます。

## 目的

- motion cue の棚卸し
- face turn などの transition 管理
- B-control 要件の蓄積
- 将来の motion generation / in-between generation の入力整理
