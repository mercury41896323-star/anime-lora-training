# Training Diagnostics

Kohya学習のconsole log、GPU情報、終了コードを解析し、失敗原因と次の作業をmanifestへまとめます。

## 自動保存

新しく生成した`config/kohya/<character_id>/run_train.ps1`は、次を`outputs/logs/<character_id>/`へ保存します。

- `kohya_<run_id>.log`: console出力
- `gpu_<run_id>.csv`: 学習開始・終了時のVRAM、使用率、温度
- `training_result_<run_id>.json`: 開始・終了時刻と終了コード

## 診断

```powershell
anime-training-diagnostics `
  --character-id sample_yonagi `
  --result-log "outputs\logs\sample_yonagi\training_result_20260825_120000.json"
```

result JSONにconsole / GPUログの場所が保存されているため、通常はこれだけで解析できます。古いログでは`--console-log`と`--gpu-log`を追加指定します。

出力:

```text
manifests/training/sample_yonagi/training_diagnostics.json
```

検出対象:

- lossの最初・最後・最小・最大と増減傾向
- 観測epoch
- GPUメモリ、使用率、温度の最大値
- CUDA out of memory
- NaN loss
- Python traceback
- 非0終了コード

lossの低下だけで品質は保証できません。登録後に同一seed・同一promptの比較画像を作り、顔、髪、衣装、過学習を人が確認します。
