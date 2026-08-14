using System;
using System.Collections.Generic;
using System.IO;
using UnityEditor;
using UnityEngine;
using UnityEngine.Playables;
using UnityEngine.Timeline;

namespace AIAnimeStudio.Editor
{
    public static class Phase6TimelineBuilder
    {
        [MenuItem("AI Anime Studio/Create Timeline From Phase 6 Library")]
        public static void CreateFromMenu()
        {
            Phase6StoryboardLibrary library = Selection.activeObject as Phase6StoryboardLibrary;
            if (library == null)
            {
                string libraryPath = EditorUtility.OpenFilePanel(
                    "Select Phase6StoryboardLibrary asset",
                    Application.dataPath,
                    "asset"
                );
                if (string.IsNullOrEmpty(libraryPath))
                {
                    return;
                }

                libraryPath = ToAssetPath(libraryPath);
                library = AssetDatabase.LoadAssetAtPath<Phase6StoryboardLibrary>(libraryPath);
            }

            if (library == null)
            {
                EditorUtility.DisplayDialog(
                    "AI Anime Studio",
                    "Phase6StoryboardLibrary asset could not be loaded.",
                    "OK"
                );
                return;
            }

            PlayableDirector director = CreateTimeline(library);
            Selection.activeObject = director.gameObject;
            EditorGUIUtility.PingObject(director.gameObject);
        }

        public static PlayableDirector CreateTimeline(Phase6StoryboardLibrary library)
        {
            if (library == null)
            {
                throw new ArgumentNullException(nameof(library));
            }

            string storyId = SafeFileName(string.IsNullOrEmpty(library.storyId) ? "storyboard" : library.storyId);
            string timelineFolder = EnsureAssetFolder("Assets/AIAnimeStudio/Timelines/" + storyId);
            string animationFolder = EnsureAssetFolder(timelineFolder + "/Phase6Animations");
            string signalFolder = EnsureAssetFolder(timelineFolder + "/Phase6Signals");
            string rootName = storyId + "_Phase6_Timeline";
            GameObject root = new GameObject(rootName);
            PlayableDirector director = root.AddComponent<PlayableDirector>();
            TimelineAsset timeline = ScriptableObject.CreateInstance<TimelineAsset>();
            string timelinePath = AssetDatabase.GenerateUniqueAssetPath(
                timelineFolder + "/" + SafeFileName(rootName) + ".playable"
            );

            AssetDatabase.CreateAsset(timeline, timelinePath);

            AudioTrack voiceTrack = timeline.CreateTrack<AudioTrack>(null, "Phase6_Voice_AudioTrack");
            AudioTrack sfxTrack = timeline.CreateTrack<AudioTrack>(null, "Phase6_SFX_AudioTrack");
            SignalTrack lipSyncTrack = timeline.CreateTrack<SignalTrack>(null, "Phase6_LipSync_SignalTrack");
            Dictionary<string, AnimationTrack> motionTracks = new Dictionary<string, AnimationTrack>();
            Dictionary<string, GameObject> motionTargets = new Dictionary<string, GameObject>();

            double shotCursor = 0.0;
            foreach (Phase6ShotClip shot in OrderedShots(library.shots))
            {
                double shotStart = shotCursor;
                double shotDuration = ShotDuration(shot);
                AddVoiceCues(voiceTrack, shot, shotStart);
                AddSfxCues(sfxTrack, shot, shotStart);
                AddLipSyncSignals(lipSyncTrack, shot, shotStart, signalFolder);
                AddMotionCues(
                    timeline,
                    director,
                    root.transform,
                    shot,
                    shotStart,
                    animationFolder,
                    motionTracks,
                    motionTargets
                );
                shotCursor += shotDuration;
            }

            director.playableAsset = timeline;
            director.timeUpdateMode = DirectorUpdateMode.GameTime;
            EditorUtility.SetDirty(timeline);
            EditorUtility.SetDirty(director);
            AssetDatabase.SaveAssets();
            AssetDatabase.Refresh();
            return director;
        }

        private static void AddVoiceCues(AudioTrack track, Phase6ShotClip shot, double shotStart)
        {
            foreach (Phase6VoiceCue cue in shot.voiceCues ?? new List<Phase6VoiceCue>())
            {
                TimelineClip clip = track.CreateClip<AudioPlayableAsset>();
                AudioPlayableAsset asset = clip.asset as AudioPlayableAsset;
                if (asset != null)
                {
                    asset.clip = cue.audioClip;
                }

                clip.displayName = HasText(cue.speaker) ? "Voice_" + cue.speaker : "Voice_" + cue.cueId;
                clip.start = shotStart + Math.Max(0f, cue.startSeconds);
                clip.duration = CueDuration(cue.durationSeconds, cue.audioClip);
            }
        }

        private static void AddSfxCues(AudioTrack track, Phase6ShotClip shot, double shotStart)
        {
            foreach (Phase6SfxCue cue in shot.sfxCues ?? new List<Phase6SfxCue>())
            {
                TimelineClip clip = track.CreateClip<AudioPlayableAsset>();
                AudioPlayableAsset asset = clip.asset as AudioPlayableAsset;
                if (asset != null)
                {
                    asset.clip = cue.audioClip;
                }

                clip.displayName = HasText(cue.label) ? "SFX_" + cue.label : "SFX_" + cue.cueId;
                clip.start = shotStart + Math.Max(0f, cue.startSeconds);
                clip.duration = CueDuration(cue.durationSeconds, cue.audioClip);
            }
        }

        private static void AddLipSyncSignals(
            SignalTrack track,
            Phase6ShotClip shot,
            double shotStart,
            string signalFolder
        )
        {
            foreach (Phase6LipSyncCue cue in shot.lipSyncCues ?? new List<Phase6LipSyncCue>())
            {
                foreach (Phase6VisemeCue viseme in cue.visemes ?? new List<Phase6VisemeCue>())
                {
                    double signalTime = shotStart + Math.Max(0f, cue.startSeconds) + Math.Max(0f, viseme.timeSeconds);
                    SignalEmitter emitter = track.CreateMarker<SignalEmitter>(signalTime);
                    emitter.asset = CreateSignalAsset(signalFolder, shot, cue, viseme);
                    emitter.emitOnce = true;
                    emitter.retroactive = false;
                }
            }
        }

        private static void AddMotionCues(
            TimelineAsset timeline,
            PlayableDirector director,
            Transform root,
            Phase6ShotClip shot,
            double shotStart,
            string animationFolder,
            Dictionary<string, AnimationTrack> motionTracks,
            Dictionary<string, GameObject> motionTargets
        )
        {
            foreach (Phase6MotionCue cue in shot.motionCues ?? new List<Phase6MotionCue>())
            {
                string targetKey = SafeFileName(string.IsNullOrEmpty(cue.target) ? "motion_target" : cue.target);
                if (!motionTargets.TryGetValue(targetKey, out GameObject targetObject))
                {
                    targetObject = new GameObject("Phase6MotionTarget_" + targetKey);
                    targetObject.transform.SetParent(root);
                    targetObject.transform.localPosition = Vector3.zero;
                    targetObject.transform.localRotation = Quaternion.identity;
                    targetObject.transform.localScale = Vector3.one;
                    targetObject.AddComponent<Animator>();
                    motionTargets[targetKey] = targetObject;
                }

                if (!motionTracks.TryGetValue(targetKey, out AnimationTrack motionTrack))
                {
                    motionTrack = timeline.CreateTrack<AnimationTrack>(null, "Phase6_Motion_" + targetKey);
                    director.SetGenericBinding(motionTrack, targetObject.GetComponent<Animator>());
                    motionTracks[targetKey] = motionTrack;
                }

                AnimationClip animationClip = BuildMotionClip(cue);
                string animationPath = AssetDatabase.GenerateUniqueAssetPath(
                    animationFolder + "/" + SafeFileName("Phase6Motion_" + cue.cueId) + ".anim"
                );
                AssetDatabase.CreateAsset(animationClip, animationPath);

                TimelineClip timelineClip = motionTrack.CreateClip<AnimationPlayableAsset>();
                AnimationPlayableAsset playableAsset = timelineClip.asset as AnimationPlayableAsset;
                if (playableAsset != null)
                {
                    playableAsset.clip = animationClip;
                }

                timelineClip.displayName = "Motion_" + cue.motion;
                timelineClip.start = shotStart + Math.Max(0f, cue.startSeconds);
                timelineClip.duration = Math.Max(0.1f, cue.durationSeconds);
            }
        }

        private static AnimationClip BuildMotionClip(Phase6MotionCue cue)
        {
            float duration = Mathf.Max(0.1f, cue.durationSeconds);
            float intensity = Mathf.Max(0.1f, cue.intensity);
            string motion = CombinedLower(cue.motion, cue.notes);
            Vector3 endPosition = Vector3.zero;
            Vector3 endEuler = Vector3.zero;

            if (ContainsAny(motion, "nod", "bow", "うなず"))
            {
                endEuler.x = 8f * intensity;
            }
            else if (ContainsAny(motion, "shake", "head shake"))
            {
                endEuler.y = 10f * intensity;
            }
            else if (ContainsAny(motion, "step", "walk", "move"))
            {
                endPosition.x = 0.35f * intensity;
            }
            else if (ContainsAny(motion, "jump", "hop"))
            {
                endPosition.y = 0.35f * intensity;
            }
            else
            {
                endEuler.z = 4f * intensity;
            }

            AnimationClip animationClip = new AnimationClip();
            animationClip.frameRate = 24f;
            animationClip.wrapMode = WrapMode.Once;
            SetLinearCurve(animationClip, "localPosition.x", 0f, endPosition.x, duration);
            SetLinearCurve(animationClip, "localPosition.y", 0f, endPosition.y, duration);
            SetLinearCurve(animationClip, "localPosition.z", 0f, endPosition.z, duration);
            SetLinearCurve(animationClip, "localEulerAnglesRaw.x", 0f, endEuler.x, duration);
            SetLinearCurve(animationClip, "localEulerAnglesRaw.y", 0f, endEuler.y, duration);
            SetLinearCurve(animationClip, "localEulerAnglesRaw.z", 0f, endEuler.z, duration);
            return animationClip;
        }

        private static SignalAsset CreateSignalAsset(
            string signalFolder,
            Phase6ShotClip shot,
            Phase6LipSyncCue cue,
            Phase6VisemeCue viseme
        )
        {
            string signalName = SafeFileName("LipSync_" + shot.shotId + "_" + cue.cueId + "_" + viseme.mouth);
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

        private static void SetLinearCurve(AnimationClip animationClip, string propertyName, float start, float end, float duration)
        {
            AnimationCurve curve = AnimationCurve.Linear(0f, start, duration, end);
            animationClip.SetCurve("", typeof(Transform), propertyName, curve);
        }

        private static double CueDuration(float configuredDuration, AudioClip audioClip)
        {
            if (configuredDuration > 0f)
            {
                return configuredDuration;
            }

            if (audioClip != null && audioClip.length > 0f)
            {
                return audioClip.length;
            }

            return 1.0;
        }

        private static List<Phase6ShotClip> OrderedShots(List<Phase6ShotClip> shots)
        {
            List<Phase6ShotClip> ordered = new List<Phase6ShotClip>(shots ?? new List<Phase6ShotClip>());
            ordered.Sort((left, right) => left.order.CompareTo(right.order));
            return ordered;
        }

        private static double ShotDuration(Phase6ShotClip shot)
        {
            return shot.durationSeconds > 0f ? shot.durationSeconds : 1.0;
        }

        private static bool HasText(string value)
        {
            return !string.IsNullOrEmpty(value);
        }

        private static bool ContainsAny(string source, params string[] values)
        {
            foreach (string value in values)
            {
                if (source.Contains(value.ToLowerInvariant()))
                {
                    return true;
                }
            }

            return false;
        }

        private static string CombinedLower(params string[] values)
        {
            if (values == null)
            {
                return "";
            }

            return string.Join(" ", values).ToLowerInvariant();
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
