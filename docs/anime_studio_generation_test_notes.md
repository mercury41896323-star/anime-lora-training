# Anime Studio LoRA Generation Test Notes

Date: 2026-08-16

This note records the current ComfyUI generation test results for the Anime Studio / anime-lora-training project.

## Current test environment

- Project: `anime-lora-training`
- ComfyUI Desktop is running locally at `http://127.0.0.1:8188`
- ComfyUI Desktop model folder used in this test:
  - Checkpoints: `%LOCALAPPDATA%/Comfy-Desktop/ComfyUI-Shared/models/checkpoints`
  - LoRAs: `%LOCALAPPDATA%/Comfy-Desktop/ComfyUI-Shared/models/loras`
  - Output: `%LOCALAPPDATA%/Comfy-Desktop/ComfyUI-Shared/output/anime_studio/<character_id>`
- Checkpoint recognized by ComfyUI:
  - `sd15.safetensors`
- LoRAs recognized by ComfyUI:
  - `sample_yonagi_lora.safetensors`
  - `sample_akira_lora.safetensors`
  - `sample_chiyoko_lora.safetensors`
  - `sample_hiiragi_lora.safetensors`

## Important workflow finding

The API workflow exported as `sd15_lora_txt2img_512_with_lora.json` failed when submitted directly to ComfyUI because the top-level `meta` field was included.

Temporary workaround:

1. Export the workflow with `anime-studio comfyui export-workflow --character-id <character_id>`.
2. Remove the top-level `meta` field.
3. Save as `sd15_lora_txt2img_512_with_lora_api_clean.json`.
4. Submit the clean JSON with `anime-studio comfyui queue-submit`.

Future improvement:

- `queue-submit` should automatically strip non-node metadata before sending to ComfyUI, or `export-workflow` should avoid writing `meta` into API-submitted workflow JSON.

## Character generation results

### sample_yonagi

Result:

- Character likeness appeared.
- Hair, color, and face atmosphere were close to the training data.
- No major image collapse.
- Some text-like artifacts and watermark-like traces remained.

Assessment:

- Character reproduction is mostly successful.
- Main issue is text / watermark artifact handling.

Future improvement:

- Use WD14 or another analysis step to detect tags such as `text`, `watermark`, `signature`, `logo`, and `letters`.
- Filter or flag source images with visible text/watermarks before training.
- Add optional cleanup or inpaint workflow for text/watermark residue.

### sample_akira

Result:

- Color reproduction was acceptable.
- Design reproduction was weak compared with the training data.
- Increasing LoRA strength caused larger visual collapse.
- Lowering LoRA strength improved stability slightly but still did not fully match the training data.

Assessment:

- `sample_akira` appears to be a character-specific training/caption quality issue rather than a global pipeline failure.
- Prompt tuning alone is probably not enough.

Likely causes:

- Training images may have too much variation.
- Captions may not describe character-specific design features strongly enough.
- Some inconsistent or low-quality images may be mixed into the dataset.
- The LoRA may contain unstable character information: enough to affect color, but not enough to stabilize design.

Future improvement:

- Review `sample_akira` source images.
- Remove images with inconsistent design, poor quality, visible text, watermark, or unwanted background influence.
- Add better tags for hair, eyes, face shape, clothing, and distinctive character features.
- Rebuild captions with WD14 plus manual correction.
- Retrain and test LoRA strength in the 0.65 to 0.85 range.

### sample_chiyoko

Result:

- Design and color were good.
- Output was close to the training data.
- Mouth shape needed prompt control.
- Adding `closed mouth`, `gentle expression`, and smile-related prompts improved the result.

Assessment:

- `sample_chiyoko` is a successful or near-successful character.
- Remaining issues are mostly expression-level prompt control, not dataset-level failure.

Useful prompts tested:

- `sample_chiyoko, sample_chiyoko, 1girl, upper body, simple background, looking at viewer, closed mouth, gentle expression`
- `sample_chiyoko, sample_chiyoko, 1girl, bust up, head fully visible, simple background, looking at viewer, closed mouth, natural smile, gentle expression`
- `sample_chiyoko, sample_chiyoko, 1girl, bust up, head fully visible, simple background, looking at viewer, closed mouth, soft smile, cheerful expression`
- `sample_chiyoko, sample_chiyoko, 1girl, bust up, head fully visible, simple background, looking at viewer, closed mouth, elegant smile, calm expression`

### sample_hiiragi

Result:

- Best reproduction among the tested characters.
- High similarity to training data.
- Low collapse.
- Color and design were both stable.

Assessment:

- `sample_hiiragi` should be treated as the current success baseline character.
- Use it as a reference when testing future workflow changes.

## Overall conclusion

The Anime Studio LoRA training and ComfyUI generation flow works.

The current character quality ranking from this test is:

1. `sample_hiiragi` - best reproduction, least collapse
2. `sample_chiyoko` - good reproduction, expression tuning needed
3. `sample_yonagi` - good character reproduction, text/watermark artifacts remain
4. `sample_akira` - color is close, but design reproduction is weak and unstable

This suggests that the pipeline itself is functioning, but output quality strongly depends on each character dataset and caption quality.

## Future system improvements

Priority improvements for Anime Studio:

1. Add ComfyUI UI workflow export
   - Current API workflow is hard for beginners to understand.
   - Need a visible node-based workflow for ComfyUI drag-and-drop use.

2. Clean API workflow submission
   - Remove or ignore top-level `meta` before submitting to ComfyUI.

3. Add WD14 tagging pipeline
   - Use WD14 to detect hair, eyes, clothing, expression, pose, and unwanted tags.
   - Add manual tag correction.
   - Use final captions for better LoRA training.

4. Add text/watermark detection
   - Detect `text`, `watermark`, `signature`, `logo`, `letters`, and related artifacts.
   - Exclude or flag those images before training.

5. Add character quality report
   - After training, generate a simple report per character:
     - dataset image count
     - caption count
     - suspicious tags
     - LoRA generation test status
     - reproduction score notes

6. Revisit `sample_akira`
   - Treat as a dataset/caption improvement target.
   - Rebuild captions and retrain after WD14/manual tag improvements.
