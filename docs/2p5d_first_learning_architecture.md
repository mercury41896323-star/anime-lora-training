# 2.5D-First Learning Architecture

AI Anime Studioの学習設計を、LoRA中心から **2.5Dを基準にLoRAが補完する構成** へ変更します。

## 基本方針

- CharacterProfileをキャラクター情報の共通入口にする。
- 動画は標準の学習ソースとして読み込み、Shot・画像・時間変化を解析する。
- 外部で用意した画像もCharacterProfileへ登録すれば、動画なしで2.5D Definitionを作れる。
- 2.5D Definitionをキャラクター同一性、形状、向き、部位、アニメーション制御の基準にする。
- LoRAは2.5Dで不足する質感、細部、描画表現、中間フレーム、動きの連続性を補完する。
- readyな2.5D Definitionがない場合、最終Kohya設定の生成を停止する。

## 新しい処理順

1. 動画読込
2. 画像・Shot・時間変化解析
3. Character Sheet Draft作成と人間によるreviewed/master化
4. CharacterProfileまたはCharacter Master Assetから2.5Dマッピングを生成
5. 2.5D Definitionを参照する補完用LoRA設定を生成して学習
6. character・motion・camera・background・lightingのdatasetと各種assetを保存

実装上は、解析後に各領域datasetを先に保存できます。ただしLoRAの最終設定は2.5D Definition完成後にのみ生成されます。

## CharacterProfileを共通入口にする

CharacterProfileには次を保存します。

- `source_assets`: 動画、外部画像、設定資料などの登録済み素材
- `definition_2p5d`: 現在採用している2.5D Definition
- `learning_strategy`: `2p5d_base_lora_completion`
- LoRA設定と学習結果

外部画像から開始する場合:

```powershell
anime-studio character init --id external_hero --name "External Hero"
anime-studio character register-asset --id external_hero --source assets/raw/external_hero_front.png
anime-studio character register-asset --id external_hero --source assets/raw/external_hero_side.png
anime-character-2p5d --character-id external_hero
```

画像の隣に同名の `.txt` を用意し、`front`、`three_quarter`、`side`、`back`、`full_body`、`expression` などを入れると2.5D view anchorへ分類しやすくなります。

## 動画由来の領域別dataset

`anime-video-domain-datasets` は次を保存します。

```text
datasets/video_learning/<character_id>/<video_id>/
├─ character/
├─ motion/
├─ camera/
├─ background/
├─ lighting/
└─ video_learning_bundle.json
```

- `character`: 2.5D identity mappingとLoRA補完に使うclean frame
- `motion`: 同じShot内の連続フレームと状態変化
- `camera`: 距離、顔向き、Shot境界などの構図情報
- `background`: 背景候補と背景タグ。現状は人物segment前の候補dataset
- `lighting`: 光、影、時間帯、色温度などのタグ

character LoRAに加えて、motion・camera・background・lightingも学習用dataset台帳と専用providerまで実装しています。

4領域ともCPU軽量baseline trainerを利用でき、さらにニューラルproviderを追加済みです。Camera / Relightingは小型PyTorch adapter、BackgroundはKohya LoRA、Motionは公式AnimateDiff trainer用ジョブとして準備します。学習済みdescriptorはCharacterProfileとB-controlへ登録できます。詳細は`docs/domain_trainers.md`と`docs/neural_trainers.md`を参照してください。

## 2.5DとLoRAの役割

| 領域 | 2.5D | LoRA |
|---|---|---|
| キャラクター同一性 | 主制御 | 細部補完 |
| 顔・髪・衣装形状 | anchorとlayer基準 | 描画表現補完 |
| ポーズ・向き | view/body control | 崩れと中間表現補完 |
| アニメーション | keyframeと部位移動 | in-betweenと質感連続性補完 |
| カメラ・ライティング | B-control値 | 出力表現の適応 |

## 学習ゲート

最終Kohya設定を生成する条件:

- CharacterProfileが存在する
- clean datasetが存在する
- `character_2p5d_definition.json` の `definition_status` が `ready`
- caption数と最低画像数を満たす

条件を満たさない場合はLoRA学習を開始せず、Character Sheetまたは外部参照画像の追加へ戻ります。

## 生成ゲート

学習ゲートと生成ゲートは分離します。LoRA学習が完了していても、Simple 2.5D Rigの人間Review、LoRAとtrigger tagの明示選択、ControlNetモデル、ComfyUI入力画像が揃うまで生成workflowをreadyとして扱いません。

- Rig再生成時は既存承認を失効する
- LoRA名の曖昧一致や自動推測をしない
- LoRAの学習所有情報と生成用bindingを分離する
- Local testではrights未確認をwarning、本学習・配布前には確認必須とする
- Live2D bridgeはArtMesh対応表であり、Cubismのmoc3自動生成とは区別する

詳細な操作は`docs/simple_2p5d_rig_pipeline.md`を参照してください。
