# Phase 6 Completion Design

Phase 6は、ショット制作後の音声、口パク、効果音、モーションをShot単位で管理し、Unity Timelineや編集工程へ渡せる状態にする段階です。
現時点では重いAI生成ではなく、RTX 3050 6GB環境でも安定して扱える軽量JSON台帳とUnity向けmanifestを中心に進めます。

## 現在できていること

- `voice_cues.json`: Shot単位の台詞、話者、音声asset参照を管理する。
- `lip_sync_plan.json`: text placeholderまたはWAV RMS解析から仮viseme timingを作る。
- `sfx_cues.json`: SFX cue、タグ、Asset Library候補を保存する。
- `sfx_asset_review.json`: SFX候補をレビューし、採用候補を見える化する。
- `motion_cues.json`: キャラクター、カメラなどのmotion cueをShot単位で管理する。
- `motion_clip_plan.json`: motion cueからUnity AnimationClip向けkeyframe planを作る。
- `phase6_manifest.json`: voice、lip-sync、SFX、motionをShot単位で統合する。
- Unity sample: `phase6_manifest.json` をTimeline上のAudioTrack、SignalTrack、AnimationTrackへ仮配置する。

## 完了条件

Phase 6を完了とみなす条件は次の通りです。

1. `phase6_manifest.json` が採用済みShot、voice、lip-sync、SFX、motionを一貫した順序で出力できる。
2. SFXは自動候補のままではなく、レビュー後に採用済みassetを `sfx_cues.json` へ反映できる。
3. motion cueはUnity側だけで解釈せず、Python側でも `motion_clip_plan.json` として事前確認できる。
4. Unity importerは `phase6_manifest.json` と補助manifestを読んで、Timeline上に仮配置できる。
5. すべての処理がGPUなしで検証でき、6GB VRAM環境の生成処理をブロックしない。

## manifest責務

| manifest | 役割 | 作成者 | 利用者 |
| --- | --- | --- | --- |
| `voice_cues.json` | 台詞と音声assetの台帳 | `phase6_pipeline voice` | lip-sync、Phase6 export、Unity |
| `lip_sync_plan.json` | 口パク用viseme timing | `phase6_pipeline lip-sync` | Phase6 export、Unity SignalTrack |
| `sfx_cues.json` | SFX cueと採用asset | `phase6_pipeline sfx` / `sfx_review select` | Phase6 export、Unity AudioTrack |
| `sfx_asset_review.json` | SFX候補の確認用manifest | `sfx_review review` | 人間、将来のShotEditor |
| `motion_cues.json` | motion intentの台帳 | `phase6_pipeline motion` | motion clip plan、Phase6 export |
| `motion_clip_plan.json` | AnimationClip生成前のkeyframe設計図 | `motion_clip_plan` | Unity importer、編集確認 |
| `phase6_manifest.json` | 編集/Unity向け統合manifest | `phase6_pipeline export` | Unity、Phase7 |

## 次に実装する小単位

### 1. Phase6 exportへ補助manifest参照を足す

`phase6_manifest.json` に `supplemental_manifests` を追加し、`sfx_asset_review.json` と `motion_clip_plan.json` の場所を記録します。
これによりUnity側やPhase7側が、統合manifestだけを入口にして補助情報へ辿れるようになります。

想定フィールド:

```json
{
  "supplemental_manifests": {
    "sfx_asset_review": "manifests/storyboards/pilot_scene/sfx_asset_review.json",
    "motion_clip_plan": "manifests/storyboards/pilot_scene/motion_clip_plan.json"
  }
}
```

### 2. Unity importerへmotion clip plan読込を足す

現在のUnity側は `motion_cues` から簡易AnimationClipを生成しています。
次は `motion_clip_plan.json` が存在する場合、Python側で作ったkeyframe planを優先し、存在しない場合は従来の簡易生成へfallbackします。

### 3. ShotEditor向けレビュー表示を設計する

ShotEditor画面に次の軽量表示を追加します。

- SFX候補: `needs_selection` / `ready` / `missing_candidates`
- motion plan: target、preset、duration、keyframe count
- voice/lip-sync: audio asset有無、provider、fallback理由

## 実装順序

1. `phase6_manifest.json` に補助manifest参照を追加する。
2. `motion_clip_plan.json` のschemaをUnity側で読める形に固定する。
3. Unity側に `MotionClipPlan` 用のScriptableObjectまたは内部DTOを追加する。
4. Unity Timeline Builderでkeyframe planをAnimationClipへ反映する。
5. ShotEditorにPhase6 status summaryを表示する。
6. Docsとテストを更新する。

## 検証方針

- Python側は `unittest` でmanifest内容、fallback、エラー処理を確認する。
- Unity側はC#構文の静的確認に加え、JSON field名と既存sample classの整合をテストする。
- GPUやComfyUIを使う検証はPhase6完了条件に含めない。

## 設計判断

- Phase6では「実生成」より「Shotごとの制作指示と採用状態」を優先する。
- SFXやmotionは自動化しても、あとで人間が差し替えられる形を維持する。
- Unity依存の処理をPython側に寄せすぎず、Pythonはmanifest、Unityはasset生成という責務分離を保つ。
