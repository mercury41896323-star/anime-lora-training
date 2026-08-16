# Anime Studio Video Generation B-Control Notes

Date: 2026-08-16

This note records the result of the current video generation test and the decision to include a future B-control implementation in AI Anime Studio.

## Current conclusion

The current `anime-lora-training` video test is mainly in **A mode**:

```text
A. Image generation + camera-work video
```

This means the current pipeline can already test:

- LoRA-based still image generation.
- FFmpeg-based MP4 output.
- Still image to video conversion.
- Smooth zoom, pan, and cut editing.
- Simple PV-like shot assembly from generated images.

However, the test showed that A mode alone is not enough for natural character motion, especially face direction changes such as:

```text
left angle
  ↓
intermediate in-between
  ↓
front angle
```

## Finding from the face-turn test

The following methods were tested or discussed:

1. **Single-image transform with FFmpeg**
   - Good for zoom and pan.
   - Cannot rotate the character's face or body.

2. **Multiple txt2img keyframes**
   - Can create different still images.
   - Angle control is unstable.
   - File names and actual face direction can mismatch.
   - Character design may collapse when the prompt strongly requests a side/profile angle.

3. **Blend-based in-between frame**
   - A 50:50 blend between left and front images did not create a real 45-degree in-between.
   - It only mixed pixels and often became visually close to the front image.

4. **img2img from a good base image**
   - Better at preserving character design.
   - But with low denoise, the face angle barely changes.
   - With high denoise, the face angle may change, but character design becomes unstable.

## Important limitation discovered

`img2img` alone is not enough to reliably create natural face-turn in-betweens while preserving character design.

```text
denoise low
  → character design is preserved
  → face angle remains almost unchanged

denoise high
  → face angle may change
  → character design may collapse
```

Therefore, natural in-between generation requires stronger control than prompt + img2img.

## Decision: add B-control implementation after the current test phase

After the current image/video test phase, AI Anime Studio should add **B mode**:

```text
B. ControlNet / OpenPose / Reference / IPAdapter / AnimateDiff style control
```

The purpose of B mode is to control:

- Face direction.
- Body angle.
- Pose.
- Character consistency across keyframes.
- In-between frame generation.
- Motion continuity.
- Camera-work consistency.
- Lighting consistency.

## Why B mode is needed

A mode is useful for early video testing:

```text
still image
  ↓
zoom / pan / cut
  ↓
short video test
```

But B mode is needed for actual anime-like motion:

```text
character pose / face angle / reference image
  ↓
controlled generation
  ↓
consistent keyframes
  ↓
in-between frames
  ↓
animation shot
```

## B mode should also help camera-work and lighting

B mode is not only for character movement.

It should also contribute to camera-work and lighting control.

### Camera-work contribution

Possible controls:

- Shot size: close-up, bust-up, upper body, full body.
- Camera angle: front, side, low angle, high angle, three-quarter view.
- Camera motion: zoom, pan, dolly, tilt.
- Character position in frame.
- Composition consistency between frames.

### Lighting contribution

Possible controls:

- Direction of light.
- Shadow position.
- Rim light / backlight.
- Dramatic anime-style lighting.
- Consistent lighting across sequential frames.
- Reuse of lighting tags or LightingManifest data.

## Future implementation image

The future B-control pipeline could look like this:

```text
CharacterProfile
  │
  ├─ character trigger tag
  ├─ LoRA reference
  ├─ reference images
  └─ design constraints

ShotManifest
  │
  ├─ camera angle
  ├─ camera distance
  ├─ pose target
  ├─ face direction
  ├─ lighting direction
  └─ motion intent

Control Inputs
  │
  ├─ OpenPose / pose map
  ├─ ControlNet guide
  ├─ IPAdapter / reference image
  ├─ depth / lineart / canny when needed
  └─ AnimateDiff or video model when available

ComfyUI Workflow
  │
  ▼
Controlled keyframes / in-betweens
  │
  ▼
VideoManifest / EditTimelineManifest
```

## Relationship with the current development order

The current development order remains:

1. **WD14 tags auto full implementation**
2. **Video Analysis Pipeline**
3. **AI Anime Studio Launcher / Dashboard**

B-control should be added as a future improvement after or alongside the video pipeline work.

Recommended placement:

```text
1. Complete image tagging and dataset quality improvements.
2. Build Video Analysis Pipeline.
3. Record camera, pose, face direction, and lighting information into manifests.
4. Add B-control workflow generation in ComfyUI.
5. Connect B-control outputs to VideoManifest / EditTimelineManifest.
6. Expose it later through AI Anime Studio Launcher / Dashboard.
```

## Short-term practical direction

For the current test phase, continue with A mode:

- Use successful still images.
- Add zoom / pan / cuts.
- Build simple PV-style test videos.
- Record where motion control fails.

After the test phase, use those findings to define B-control requirements.

## Development note

The current test shows that face-turn animation cannot be solved by prompt engineering alone.

The project should treat this as a system requirement:

```text
Natural character motion needs structured control data.
```

This should be reflected in future design for:

- `ShotManifest`
- `VideoManifest`
- `LightingManifest`
- `GenerationManifest`
- ComfyUI workflow export
- AI Anime Studio Dashboard controls
