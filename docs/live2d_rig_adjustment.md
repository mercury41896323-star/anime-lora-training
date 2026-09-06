# Live2D Rig Adjustment Package

`anime-live2d-adjust`はSimple 2.5D Rigから、Cubism Editorで調整するためのArtMesh、Deformer、pivot、parameter keyform案を生成します。

```powershell
anime-live2d-adjust --character-id chiyoko
```

出力:

- `live2d_adjustment.json`: 高密度Grid ArtMesh、Deformer階層、回転軸、parameter binding
- `live2d_adjustment_preview.png`: ArtMesh範囲とpivot位置の確認画像
- `live2d_pose_test_relaxed_standing.png`: 自然立ちの静的回転テスト
- `live2d_pose_test_small_step.png`: 一歩踏み出す静的回転テスト
- `live2d_bridge.json`: 調整パッケージへの参照を追加したLive2D bridge
- `<character_id>_live2d_import.psd`: 各透明パーツを実画素範囲へ切り詰めたCubism取込用PSD

## 調整値の上書き

数値はJSONで後から変更できます。

```json
{
  "parts": {
    "head": {
      "pivot": {"x": 0.5, "y": 0.285},
      "columns": 8,
      "rows": 8
    },
    "left_arm": {
      "pivot": {"x": 0.445, "y": 0.3}
    }
  }
}
```

```powershell
anime-live2d-adjust `
  --character-id chiyoko `
  --overrides "C:\path\to\chiyoko_live2d_overrides.json"
```

この出力はCubismの`.cmo3`や`.moc3`そのものではありません。透明パーツをCubism Editorへ読み込み、ArtMesh頂点、clipping、warp強度、回転軸を最終調整するための取込設計です。

Cubism用PSDは透明なキャンバス全体をレイヤー範囲にせず、各パーツのAlpha境界で物理的にCropします。これにより`face`や`head`のArtMeshが全画面・バストアップ範囲になることを防ぎます。

頭部は`hair_back`、`head`（首・頭部基部）、`face`、`eyes`、`mouth`、`hair_front`の6領域へ分けます。同じ頭部画像を矩形で重ねる方式は使わず、6マスクは相互に非重複で、合成すると元の頭部全体を復元します。`eyes`と`mouth`は顔内の位置に加えて明度・色差で抽出し、残りを前髪、顔、首、後髪へ割り当てます。

## Cubism実機確認

ChiyokoではCubism Editor 5.3.00 FREE版へ12パーツをPSDとして読み込み、頭部6パーツすべてを`head_rotation`へ格納しました。標準の`ParamAngleZ`に`-30 / 0 / 30`の3点キーを作り、約`+12 / 0 / -12`度を割り当てています。腕、胴体、腰、脚は頭部デフォーマの外に維持されます。結果は`docs/test_log_2026-09-05_chiyoko_live2d_semantic_head.md`を参照してください。

ポージング確認用の2枚は、Cubismへキーを作る前に肩・腰・股関節のpivotとパーツ境界を確認する静的プレビューです。自然立ちと小さな歩行姿勢を合成し、腕や脚が胴体から大きく離れない低角度で検査します。画像に破綻がある場合はCubismのキー作成へ進まず、Maskまたはpivotを調整します。

RTX 3050搭載PCでCubismがIntel内蔵GPUを選ぶ場合は、Windowsの「グラフィック」設定で次の3ファイルを「高パフォーマンス」に設定してCubismを再起動します。

- `C:\Program Files\Live2D Cubism 5.3\CubismEditor5.exe`
- `C:\Program Files\Live2D Cubism 5.3\app\jre\bin\java.exe`
- `C:\Program Files\Live2D Cubism 5.3\app\jre\bin\javaw.exe`

Cubismのログに`Vendor : NVIDIA Corporation`と`Renderer : NVIDIA GeForce RTX 3050/PCIe/SSE2`が出れば切替済みです。
