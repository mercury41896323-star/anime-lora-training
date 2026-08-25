# Simple 2.5D Rig Pipeline

## 目的

Character SheetとCharacterProfileを、LoRAだけに依存しない軽量な同一性制御へ変換します。出力は固定Crop、Character Master Asset、2.5D Definition、簡易Rig、Mask、Depth、Pose、透明パーツ、簡易Mesh、ComfyUI API workflow、Live2D連携manifestです。

## Character Sheet Template v1

組込みテンプレートIDは`simple_2p5d_v1`です。1347x1168前後の横長シートを基準に、正規化座標で35領域を定義しています。

- メインポートレート
- 正面・側面・背面の三面図
- 正面・45度・横・見上げ・見下ろし・後頭部
- 12表情
- 立ち・歩き・振り返り・座り・ストレッチ
- 服装3種
- カラーパレット
- ロケーション・ライティング参考

Cropは固定座標の初期値です。異なるシートレイアウトでは`character_sheet_importer`のカスタムJSONを使用し、人間が全Cropを確認します。

正面全身Cropは、そのままControlNetへ引き伸ばしません。前景bboxを抽出して512x768のキャンバスへ中央配置し、頭上約8%と足元の安全余白を確保します。これにより、細長い三面図Cropでも頭部・足先が画面外へ切れにくくなります。

## Character Profile Template v1

`templates/character_profiles/character_profile_template_v1.json`は次を保存します。

- 人物属性、性格、役割
- 顔・目・髪・シルエット・変更禁止要素
- 標準衣装、衣装差分、アクセサリー、靴
- 三面図、顔角度、表情、ポーズ、照明の必要coverage
- 髪・目・肌・衣装・アクセントのpalette
- 2.5Dパーツ、Live2D互換parameter候補
- 学習枚数、caption、negative tag、rights確認
- LoRA・OpenPose・Depthの生成時strength

## 実行

```powershell
anime-simple-2p5d `
  --character-id hiiragi_yukikaze `
  --display-name "柊 雪風" `
  --sheet "C:\Users\pfsgs\Desktop\動画学習用データ\柊雪.png" `
  --profile-overrides examples\characters\hiiragi_yukikaze_profile_v1.json `
  --comfyui-input-dir "C:\Users\pfsgs\AppData\Local\Comfy-Desktop\ComfyUI-Shared\input"
```

LoRAとControlNetを配置した後は実際のComfyUIファイル名も渡します。

```powershell
anime-simple-2p5d `
  --character-id hiiragi_yukikaze `
  --display-name "柊 雪風" `
  --sheet "C:\path\to\character_sheet.png" `
  --profile-overrides examples\characters\hiiragi_yukikaze_profile_v1.json `
  --comfyui-input-dir "C:\path\to\ComfyUI-Shared\input" `
  --lora-name "hiiragi_yukikaze.safetensors" `
  --openpose-controlnet "control_v11p_sd15_openpose_fp16.safetensors" `
  --depth-controlnet "control_v11f1p_sd15_depth_fp16.safetensors"
```

RTX 3050 6GB環境では、ComfyUI作者が公開しているFP16 safetensors版を使用します。2026-08-23のローカル確認では、両モデルをComfyUI標準`ControlNetLoader`が認識しています。

## 生成順序

1. CharacterProfile v1を作成または更新
2. 35領域をCropして分類captionを作成
3. Character Master Assetを作成
4. Character 2.5D Definitionを作成
5. 正面全身Cropから12パーツのMaskと透明PNGを作成
6. パーツ前後関係を簡易Depth PNGに変換
7. 正面全身のbboxからPose補助PNGを作成
8. LoRA + OpenPose ControlNet + Depth ControlNet workflowを出力
9. Live2D Cubismへ移すためのArtMesh・parameter対応表を出力

生成workflowは`solo`、`single subject`、`head fully visible`、`feet fully visible`を正条件に含め、複数人物、キャラクターシート、頭部・足先Cropを負条件へ入れます。OpenPoseを1.0、Depthを0.65の初期強度として、全身構図を優先します。

外部IP-Adapterがない環境でも同一性を補強するため、正面全身の`reference.png`を標準VAEでlatentへ変換し、denoise 0.65のimg2img初期値として使います。LoRAだけで生成するより、顔、衣装、シルエット、白背景を維持しやすい軽量構成です。

## 制約

- Maskは背景色差と身体ゾーンによる簡易Draftであり、髪・顔・腕を意味的に分割するAI segmentationではありません。
- Poseは正面全身bboxから作る近似骨格です。実運用ではOpenPose/DWPoseで再生成します。
- Meshは四角形2三角のDraftです。Live2D CubismでArtMesh、deformer、pivot、clippingを調整します。
- workflowはControlNet modelと学習済みLoRAの実ファイル名が揃うまで`needs_models`です。
- Character Sheet由来の文字・背景参考画像を、そのままキャラクターLoRA datasetへ混入させません。

## Reviewと生成ゲート

自動生成直後のRigは`pending_review`です。ファイルが存在するだけでは本番生成へ進めません。

```powershell
anime-simple-2p5d-manage inspect --character-id hiiragi_yukikaze
```

確認対象:

- 35領域Cropの位置とキャラクター同一性
- 12パーツMaskと透明PNG
- 前後関係を表すDepth
- 骨格位置を表すPose
- 四角Meshのpivotと親子関係
- Live2D ArtMesh・parameter対応

人間が確認した後だけ承認します。

自動検査ではSilhouetteが512x768であることと、前景bboxが上下左右それぞれ5%以上の余白を持つことも確認します。頭部・足先・身体がキャンバス端へ接触している場合は承認を停止します。

```powershell
anime-simple-2p5d-manage approve `
  --character-id hiiragi_yukikaze `
  --reviewer "reviewer_name" `
  --notes "Crop、Mask、Depth、Poseを確認"
```

承認時はRig・Definition・Master AssetのSHA256署名を保存します。これらが再生成された場合、状態は自動的に`pending_review`へ戻ります。LoRA選択やControlNetファイル名の変更だけではRig承認を失効しません。

## LoRAの明示選択

似たファイル名からLoRAを自動推測しません。対象ファイル、trigger tag、確認者を明示します。

```powershell
anime-simple-2p5d-manage bind-lora `
  --character-id hiiragi_yukikaze `
  --lora-name "sample_hiiragi_lora.safetensors" `
  --trigger-tag "sample_hiiragi" `
  --comfyui-lora-dir "C:\Users\pfsgs\AppData\Local\Comfy-Desktop\ComfyUI-Shared\models\loras" `
  --reviewer "reviewer_name"
```

この操作は生成workflowへの明示的な紐付けです。そのLoRAが当該CharacterProfileから学習されたと自動認定する処理ではありません。

## 最終Readiness

```powershell
anime-simple-2p5d-manage readiness `
  --character-id hiiragi_yukikaze `
  --comfyui-controlnet-dir "C:\Users\pfsgs\AppData\Local\Comfy-Desktop\ComfyUI-Shared\models\controlnet" `
  --comfyui-lora-dir "C:\Users\pfsgs\AppData\Local\Comfy-Desktop\ComfyUI-Shared\models\loras" `
  --comfyui-input-dir "C:\Users\pfsgs\AppData\Local\Comfy-Desktop\ComfyUI-Shared\input"
```

`Ready: True`の条件:

1. Rig reviewが`approved`
2. 明示選択したLoRAがComfyUI models内に存在
3. OpenPose・Depth ControlNetが存在
4. reference・pose・depth・maskがComfyUI input内に存在
5. API workflowが存在

状態遷移は`built -> pending_review -> approved -> lora_bound -> generation_ready`です。

2026-08-25のRTX 3050 6GB実機結果は`docs/test_log_2026-08-25_simple_2p5d_local_generation.md`を参照してください。
