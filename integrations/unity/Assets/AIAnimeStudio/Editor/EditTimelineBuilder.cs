using System;
using System.Collections.Generic;
using System.IO;
using UnityEditor;
using UnityEngine;
using UnityEngine.Playables;
using UnityEngine.Timeline;

namespace AIAnimeStudio.Editor
{
    public static class EditTimelineBuilder
    {
        [MenuItem("AI Anime Studio/Create Timeline From Edit Timeline Library")]
        public static void CreateFromMenu()
        {
            EditTimelineLibrary library = Selection.activeObject as EditTimelineLibrary;
            if (library == null)
            {
                string libraryPath = EditorUtility.OpenFilePanel(
                    "Select EditTimelineLibrary asset",
                    Application.dataPath,
                    "asset"
                );
                if (string.IsNullOrEmpty(libraryPath))
                {
                    return;
                }

                libraryPath = ToAssetPath(libraryPath);
                library = AssetDatabase.LoadAssetAtPath<EditTimelineLibrary>(libraryPath);
            }

            if (library == null)
            {
                EditorUtility.DisplayDialog(
                    "AI Anime Studio",
                    "EditTimelineLibrary asset could not be loaded.",
                    "OK"
                );
                return;
            }

            PlayableDirector director = CreateTimeline(library);
            Selection.activeObject = director.gameObject;
            EditorGUIUtility.PingObject(director.gameObject);
        }

        public static PlayableDirector CreateTimeline(EditTimelineLibrary library)
        {
            if (library == null)
            {
                throw new ArgumentNullException(nameof(library));
            }

            string storyId = SafeFileName(string.IsNullOrEmpty(library.storyId) ? "storyboard" : library.storyId);
            string timelineFolder = EnsureAssetFolder("Assets/AIAnimeStudio/Timelines/" + storyId);
            string animationFolder = EnsureAssetFolder(timelineFolder + "/EditAnimations");
            string signalFolder = EnsureAssetFolder(timelineFolder + "/EditSignals");
            string rootName = storyId + "_Edit_Timeline";
            GameObject root = new GameObject(rootName);
            PlayableDirector director = root.AddComponent<PlayableDirector>();
            TimelineAsset timeline = ScriptableObject.CreateInstance<TimelineAsset>();
            string timelinePath = AssetDatabase.GenerateUniqueAssetPath(
                timelineFolder + "/" + SafeFileName(rootName) + ".playable"
            );
            AssetDatabase.CreateAsset(timeline, timelinePath);

            foreach (EditTimelineTrack track in OrderedTracks(library.tracks))
            {
                if (track.trackType == "video")
                {
                    AddVideoClips(timeline, director, root.transform, track);
                }
                else if (track.trackType == "audio")
                {
                    AddAudioTrack(timeline, track);
                }
                else if (track.trackType == "signal")
                {
                    AddSignalTrack(timeline, track, signalFolder);
                }
                else if (track.trackType == "animation")
                {
                    AddAnimationTrack(timeline, director, root.transform, track, animationFolder);
                }
            }

            director.playableAsset = timeline;
            director.timeUpdateMode = DirectorUpdateMode.GameTime;
            EditorUtility.SetDirty(timeline);
            EditorUtility.SetDirty(director);
            AssetDatabase.SaveAssets();
            AssetDatabase.Refresh();
            return director;
        }

        private static void AddVideoClips(
            TimelineAsset timeline,
            PlayableDirector director,
            Transform root,
            EditTimelineTrack track
        )
        {
            int visualIndex = 0;
            foreach (EditTimelineClip clip in OrderedClips(track.clips))
            {
                GameObject shotObject = CreateVideoPreviewObject(clip, root, visualIndex);
                ActivationTrack activationTrack = timeline.CreateTrack<ActivationTrack>(
                    null,
                    SafeFileName(track.trackId + "_" + clip.clipId)
                );
                TimelineClip timelineClip = activationTrack.CreateDefaultClip();
                timelineClip.displayName = ClipDisplayName(clip);
                timelineClip.start = Math.Max(0f, clip.startSeconds);
                timelineClip.duration = ClipDuration(clip);
                director.SetGenericBinding(activationTrack, shotObject);
                visualIndex++;
            }
        }

        private static void AddAudioTrack(TimelineAsset timeline, EditTimelineTrack track)
        {
            AudioTrack audioTrack = timeline.CreateTrack<AudioTrack>(null, SafeFileName(track.trackId));
            foreach (EditTimelineClip clip in OrderedClips(track.clips))
            {
                TimelineClip timelineClip = audioTrack.CreateClip<AudioPlayableAsset>();
                AudioPlayableAsset playableAsset = timelineClip.asset as AudioPlayableAsset;
                if (playableAsset != null)
                {
                    playableAsset.clip = clip.audioClip;
                }

                timelineClip.displayName = ClipDisplayName(clip);
                timelineClip.start = Math.Max(0f, clip.startSeconds);
                timelineClip.duration = ClipDuration(clip);
            }
        }

        private static void AddSignalTrack(TimelineAsset timeline, EditTimelineTrack track, string signalFolder)
        {
            SignalTrack signalTrack = timeline.CreateTrack<SignalTrack>(null, SafeFileName(track.trackId));
            foreach (EditTimelineClip clip in OrderedClips(track.clips))
            {
                SignalEmitter emitter = signalTrack.CreateMarker<SignalEmitter>(Math.Max(0f, clip.startSeconds));
                emitter.asset = CreateSignalAsset(signalFolder, clip);
                emitter.emitOnce = true;
                emitter.retroactive = false;
            }
        }

        private static void AddAnimationTrack(
            TimelineAsset timeline,
            PlayableDirector director,
            Transform root,
            EditTimelineTrack track,
            string animationFolder
        )
        {
            GameObject targetObject = new GameObject(SafeFileName(track.trackId));
            targetObject.transform.SetParent(root);
            targetObject.transform.localPosition = Vector3.zero;
            targetObject.transform.localRotation = Quaternion.identity;
            targetObject.transform.localScale = Vector3.one;
            Animator animator = targetObject.AddComponent<Animator>();
            AnimationTrack animationTrack = timeline.CreateTrack<AnimationTrack>(null, SafeFileName(track.trackId));
            director.SetGenericBinding(animationTrack, animator);

            foreach (EditTimelineClip clip in OrderedClips(track.clips))
            {
                AnimationClip animationClip = BuildAnimationClip(clip);
                string animationPath = AssetDatabase.GenerateUniqueAssetPath(
                    animationFolder + "/" + SafeFileName(clip.clipId) + ".anim"
                );
                AssetDatabase.CreateAsset(animationClip, animationPath);
                TimelineClip timelineClip = animationTrack.CreateClip<AnimationPlayableAsset>();
                AnimationPlayableAsset playableAsset = timelineClip.asset as AnimationPlayableAsset;
                if (playableAsset != null)
                {
                    playableAsset.clip = animationClip;
                }

                timelineClip.displayName = ClipDisplayName(clip);
                timelineClip.start = Math.Max(0f, clip.startSeconds);
                timelineClip.duration = ClipDuration(clip);
            }
        }

        private static GameObject CreateVideoPreviewObject(EditTimelineClip clip, Transform root, int visualIndex)
        {
            GameObject shotObject = new GameObject(SafeFileName(ClipDisplayName(clip)));
            shotObject.transform.SetParent(root);
            shotObject.transform.localPosition = new Vector3(0f, 0f, visualIndex * 0.01f);
            shotObject.transform.localRotation = Quaternion.identity;
            shotObject.transform.localScale = Vector3.one;

            if (clip.previewImage != null)
            {
                SpriteRenderer renderer = shotObject.AddComponent<SpriteRenderer>();
                renderer.sprite = Sprite.Create(
                    clip.previewImage,
                    new Rect(0f, 0f, clip.previewImage.width, clip.previewImage.height),
                    new Vector2(0.5f, 0.5f),
                    100f
                );
                renderer.sortingOrder = visualIndex;
            }
            else
            {
                TextMesh label = shotObject.AddComponent<TextMesh>();
                label.text = ClipDisplayName(clip);
                label.characterSize = 0.2f;
                label.anchor = TextAnchor.MiddleCenter;
            }

            shotObject.SetActive(false);
            return shotObject;
        }

        private static AnimationClip BuildAnimationClip(EditTimelineClip clip)
        {
            MotionPlanClip plan = clip.metadata != null ? clip.metadata.motionPlan : null;
            List<MotionPlanKeyframe> keyframes = plan != null ? plan.keyframes : null;
            float duration = Mathf.Max(0.1f, clip.durationSeconds);
            AnimationClip animationClip = new AnimationClip();
            animationClip.frameRate = plan != null && plan.frameRate > 0 ? plan.frameRate : 24f;
            animationClip.wrapMode = WrapMode.Once;

            if (keyframes == null || keyframes.Count == 0)
            {
                SetLinearCurve(animationClip, "localPosition.x", 0f, 0f, duration);
                SetLinearCurve(animationClip, "localPosition.y", 0f, 0f, duration);
                SetLinearCurve(animationClip, "localPosition.z", 0f, 0f, duration);
                SetLinearCurve(animationClip, "localEulerAnglesRaw.z", 0f, 4f, duration);
                return animationClip;
            }

            SetKeyframeCurve(animationClip, keyframes, "localPosition.x", item => item.localPosition.x);
            SetKeyframeCurve(animationClip, keyframes, "localPosition.y", item => item.localPosition.y);
            SetKeyframeCurve(animationClip, keyframes, "localPosition.z", item => item.localPosition.z);
            SetKeyframeCurve(animationClip, keyframes, "localEulerAnglesRaw.x", item => item.localEuler.x);
            SetKeyframeCurve(animationClip, keyframes, "localEulerAnglesRaw.y", item => item.localEuler.y);
            SetKeyframeCurve(animationClip, keyframes, "localEulerAnglesRaw.z", item => item.localEuler.z);
            SetKeyframeCurve(animationClip, keyframes, "localScale.x", item => item.localScale.x);
            SetKeyframeCurve(animationClip, keyframes, "localScale.y", item => item.localScale.y);
            SetKeyframeCurve(animationClip, keyframes, "localScale.z", item => item.localScale.z);
            return animationClip;
        }

        private static void SetKeyframeCurve(
            AnimationClip animationClip,
            List<MotionPlanKeyframe> keyframes,
            string propertyName,
            Func<MotionPlanKeyframe, float> valueSelector
        )
        {
            Keyframe[] curveKeys = new Keyframe[keyframes.Count];
            for (int index = 0; index < keyframes.Count; index++)
            {
                MotionPlanKeyframe keyframe = keyframes[index];
                curveKeys[index] = new Keyframe(Mathf.Max(0f, keyframe.timeSeconds), valueSelector(keyframe));
            }

            animationClip.SetCurve("", typeof(Transform), propertyName, new AnimationCurve(curveKeys));
        }

        private static void SetLinearCurve(AnimationClip animationClip, string propertyName, float start, float end, float duration)
        {
            AnimationCurve curve = AnimationCurve.Linear(0f, start, duration, end);
            animationClip.SetCurve("", typeof(Transform), propertyName, curve);
        }

        private static SignalAsset CreateSignalAsset(string signalFolder, EditTimelineClip clip)
        {
            string signalName = SafeFileName(clip.clipId + "_" + clip.metadata.mouth);
            string signalPath = signalFolder + "/" + signalName + ".signal";
            SignalAsset existing = AssetDatabase.LoadAssetAtPath<SignalAsset>(signalPath);
            if (existing != null)
            {
                return existing;
            }

            SignalAsset signal = ScriptableObject.CreateInstance<SignalAsset>();
            AssetDatabase.CreateAsset(signal, signalPath);
            return signal;
        }

        private static List<EditTimelineTrack> OrderedTracks(List<EditTimelineTrack> tracks)
        {
            List<EditTimelineTrack> ordered = new List<EditTimelineTrack>(tracks ?? new List<EditTimelineTrack>());
            ordered.Sort((left, right) => left.order.CompareTo(right.order));
            return ordered;
        }

        private static List<EditTimelineClip> OrderedClips(List<EditTimelineClip> clips)
        {
            List<EditTimelineClip> ordered = new List<EditTimelineClip>(clips ?? new List<EditTimelineClip>());
            ordered.Sort((left, right) => left.startSeconds.CompareTo(right.startSeconds));
            return ordered;
        }

        private static string ClipDisplayName(EditTimelineClip clip)
        {
            if (clip.metadata != null)
            {
                if (!string.IsNullOrEmpty(clip.metadata.timelineClipName))
                {
                    return clip.metadata.timelineClipName;
                }

                if (!string.IsNullOrEmpty(clip.metadata.label))
                {
                    return clip.metadata.label;
                }

                if (!string.IsNullOrEmpty(clip.metadata.motion))
                {
                    return clip.metadata.motion;
                }

                if (!string.IsNullOrEmpty(clip.metadata.mouth))
                {
                    return "lip_" + clip.metadata.mouth;
                }
            }

            return string.IsNullOrEmpty(clip.clipId) ? "clip" : clip.clipId;
        }

        private static double ClipDuration(EditTimelineClip clip)
        {
            return clip.durationSeconds > 0f ? clip.durationSeconds : 1.0;
        }

        private static string EnsureAssetFolder(string assetFolder)
        {
            string[] parts = assetFolder.Split('/');
            string current = parts[0];
            for (int index = 1; index < parts.Length; index++)
            {
                string next = current + "/" + parts[index];
                if (!AssetDatabase.IsValidFolder(next))
                {
                    AssetDatabase.CreateFolder(current, parts[index]);
                }

                current = next;
            }

            return assetFolder;
        }

        private static string SafeFileName(string value)
        {
            if (string.IsNullOrEmpty(value))
            {
                return "untitled";
            }

            foreach (char invalid in Path.GetInvalidFileNameChars())
            {
                value = value.Replace(invalid, '_');
            }

            return value.Replace(' ', '_');
        }

        private static string ToAssetPath(string fullPath)
        {
            string normalizedFullPath = fullPath.Replace('\\', '/');
            string normalizedDataPath = Application.dataPath.Replace('\\', '/');
            if (normalizedFullPath.StartsWith(normalizedDataPath, StringComparison.Ordinal))
            {
                return "Assets" + normalizedFullPath.Substring(normalizedDataPath.Length);
            }

            return normalizedFullPath;
        }
    }
}
