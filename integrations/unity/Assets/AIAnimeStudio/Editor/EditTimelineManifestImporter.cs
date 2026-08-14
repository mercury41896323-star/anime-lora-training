using System;
using System.Collections.Generic;
using System.IO;
using UnityEditor;
using UnityEngine;

namespace AIAnimeStudio.Editor
{
    public static class EditTimelineManifestImporter
    {
        [MenuItem("AI Anime Studio/Import Edit Timeline Manifest")]
        public static void ImportFromMenu()
        {
            string manifestPath = EditorUtility.OpenFilePanel(
                "Import edit_timeline_manifest.json",
                "",
                "json"
            );
            if (string.IsNullOrEmpty(manifestPath))
            {
                return;
            }

            EditTimelineLibrary library = ImportManifest(manifestPath);
            Selection.activeObject = library;
            EditorGUIUtility.PingObject(library);
        }

        public static EditTimelineLibrary ImportManifest(string manifestPath)
        {
            string json = File.ReadAllText(manifestPath);
            EditTimelineManifest manifest = JsonUtility.FromJson<EditTimelineManifest>(json);
            if (manifest == null || manifest.story == null)
            {
                throw new InvalidDataException("edit_timeline_manifest.json could not be parsed.");
            }

            string storyId = SafeFileName(manifest.story.story_id);
            string libraryFolder = EnsureAssetFolder("Assets/AIAnimeStudio/Storyboards/" + storyId);
            string importedVisualFolder = EnsureAssetFolder("Assets/AIAnimeStudio/ImportedTimelineVisuals/" + storyId);
            string importedAudioFolder = EnsureAssetFolder("Assets/AIAnimeStudio/ImportedTimelineAudio/" + storyId);
            string animeStudioRoot = FindAnimeStudioRoot(manifestPath);
            EditTimelineLibrary library = ScriptableObject.CreateInstance<EditTimelineLibrary>();
            library.manifestPath = manifestPath;
            library.storyId = manifest.story.story_id;
            library.title = manifest.story.title;
            library.importedAt = DateTime.UtcNow.ToString("o");
            library.frameRate = manifest.settings != null && manifest.settings.frame_rate > 0 ? manifest.settings.frame_rate : 24;
            library.durationSeconds = manifest.duration_seconds;
            library.tracks = new List<EditTimelineTrack>();

            foreach (EditTimelineTrackBlock trackBlock in manifest.tracks ?? new List<EditTimelineTrackBlock>())
            {
                EditTimelineTrack track = new EditTimelineTrack();
                track.trackId = trackBlock.track_id;
                track.trackType = trackBlock.track_type;
                track.order = trackBlock.order;
                track.clips = new List<EditTimelineClip>();
                foreach (EditTimelineClipBlock clipBlock in trackBlock.clips ?? new List<EditTimelineClipBlock>())
                {
                    track.clips.Add(BuildClip(animeStudioRoot, importedVisualFolder, importedAudioFolder, track.trackType, clipBlock));
                }

                library.tracks.Add(track);
            }

            string libraryPath = libraryFolder + "/EditTimelineLibrary.asset";
            EditTimelineLibrary existing = AssetDatabase.LoadAssetAtPath<EditTimelineLibrary>(libraryPath);
            if (existing != null)
            {
                existing.manifestPath = library.manifestPath;
                existing.storyId = library.storyId;
                existing.title = library.title;
                existing.importedAt = library.importedAt;
                existing.frameRate = library.frameRate;
                existing.durationSeconds = library.durationSeconds;
                existing.tracks = library.tracks;
                EditorUtility.SetDirty(existing);
                AssetDatabase.SaveAssets();
                AssetDatabase.Refresh();
                return existing;
            }

            AssetDatabase.CreateAsset(library, libraryPath);
            AssetDatabase.SaveAssets();
            AssetDatabase.Refresh();
            return library;
        }

        private static EditTimelineClip BuildClip(
            string animeStudioRoot,
            string importedVisualFolder,
            string importedAudioFolder,
            string trackType,
            EditTimelineClipBlock clipBlock
        )
        {
            EditTimelineClip clip = new EditTimelineClip();
            clip.clipId = clipBlock.clip_id;
            clip.shotId = clipBlock.shot_id;
            clip.sourceType = clipBlock.source_type;
            clip.sourcePath = clipBlock.source_path;
            clip.startSeconds = clipBlock.start_seconds;
            clip.durationSeconds = clipBlock.duration_seconds;
            clip.metadata = BuildMetadata(clipBlock.metadata);

            if (trackType == "video")
            {
                clip.importedAssetPath = CopySourceAsset(animeStudioRoot, importedVisualFolder, clip.clipId, clip.sourcePath);
                clip.previewImage = LoadPreviewImage(clip.importedAssetPath);
            }
            else if (trackType == "audio")
            {
                clip.importedAssetPath = CopySourceAsset(animeStudioRoot, importedAudioFolder, clip.clipId, clip.sourcePath);
                clip.audioClip = LoadAudioClip(clip.importedAssetPath);
            }

            return clip;
        }

        private static EditTimelineClipMetadata BuildMetadata(EditTimelineMetadataBlock block)
        {
            EditTimelineClipMetadata metadata = new EditTimelineClipMetadata();
            if (block == null)
            {
                return metadata;
            }

            metadata.title = block.title;
            metadata.resultId = block.result_id;
            metadata.timelineClipName = block.timeline_clip_name;
            metadata.addressableKey = block.addressable_key;
            metadata.kind = block.kind;
            metadata.cueId = block.cue_id;
            metadata.speaker = block.speaker;
            metadata.text = block.text;
            metadata.emotion = block.emotion;
            metadata.label = block.label;
            metadata.volume = block.volume;
            metadata.assetSource = block.asset_source;
            metadata.exists = block.exists;
            metadata.target = block.target;
            metadata.motion = block.motion;
            metadata.source = block.source;
            metadata.intensity = block.intensity;
            metadata.mouth = block.mouth;
            metadata.method = block.method;
            metadata.motionPlan = BuildMotionPlan(block.motion_plan);
            return metadata;
        }

        private static MotionPlanClip BuildMotionPlan(MotionPlanClipBlock block)
        {
            MotionPlanClip motionPlan = new MotionPlanClip();
            if (block == null)
            {
                return motionPlan;
            }

            motionPlan.clipId = block.clip_id;
            motionPlan.cueId = block.cue_id;
            motionPlan.shotId = block.shot_id;
            motionPlan.target = block.target;
            motionPlan.trackName = block.track_name;
            motionPlan.motion = block.motion;
            motionPlan.source = block.source;
            motionPlan.preset = block.preset;
            motionPlan.frameRate = block.frame_rate > 0 ? block.frame_rate : 24;
            motionPlan.startSeconds = block.start_seconds;
            motionPlan.durationSeconds = block.duration_seconds;
            motionPlan.intensity = block.intensity;
            motionPlan.keyframes = new List<MotionPlanKeyframe>();
            foreach (MotionPlanKeyframeBlock keyframe in block.keyframes ?? new List<MotionPlanKeyframeBlock>())
            {
                motionPlan.keyframes.Add(new MotionPlanKeyframe
                {
                    timeSeconds = keyframe.time_seconds,
                    localPosition = ToVector3(keyframe.local_position, Vector3.zero),
                    localEuler = ToVector3(keyframe.local_euler, Vector3.zero),
                    localScale = ToVector3(keyframe.local_scale, Vector3.one)
                });
            }

            return motionPlan;
        }

        private static string CopySourceAsset(string animeStudioRoot, string importedFolder, string clipId, string sourcePath)
        {
            if (string.IsNullOrEmpty(sourcePath))
            {
                return "";
            }

            string resolvedSourcePath = ResolveSourcePath(animeStudioRoot, sourcePath);
            if (!File.Exists(resolvedSourcePath))
            {
                Debug.LogWarning("AI Anime Studio timeline source asset was not found: " + resolvedSourcePath);
                return "";
            }

            string extension = Path.GetExtension(resolvedSourcePath);
            string assetFileName = SafeFileName(clipId) + extension;
            string targetAssetPath = importedFolder + "/" + assetFileName;
            string targetFullPath = Path.GetFullPath(targetAssetPath);
            Directory.CreateDirectory(Path.GetDirectoryName(targetFullPath));
            File.Copy(resolvedSourcePath, targetFullPath, true);
            AssetDatabase.ImportAsset(targetAssetPath);
            return targetAssetPath;
        }

        private static Texture2D LoadPreviewImage(string assetPath)
        {
            if (string.IsNullOrEmpty(assetPath))
            {
                return null;
            }

            string extension = Path.GetExtension(assetPath).ToLowerInvariant();
            if (extension != ".png" && extension != ".jpg" && extension != ".jpeg")
            {
                return null;
            }

            return AssetDatabase.LoadAssetAtPath<Texture2D>(assetPath);
        }

        private static AudioClip LoadAudioClip(string assetPath)
        {
            if (string.IsNullOrEmpty(assetPath))
            {
                return null;
            }

            return AssetDatabase.LoadAssetAtPath<AudioClip>(assetPath);
        }

        private static Vector3 ToVector3(List<float> values, Vector3 fallback)
        {
            if (values == null || values.Count < 3)
            {
                return fallback;
            }

            return new Vector3(values[0], values[1], values[2]);
        }

        private static string ResolveSourcePath(string animeStudioRoot, string sourcePath)
        {
            if (Path.IsPathRooted(sourcePath))
            {
                return sourcePath;
            }

            string normalized = sourcePath.Replace('/', Path.DirectorySeparatorChar);
            return Path.GetFullPath(Path.Combine(animeStudioRoot, normalized));
        }

        private static string FindAnimeStudioRoot(string manifestPath)
        {
            DirectoryInfo directory = new DirectoryInfo(Path.GetDirectoryName(manifestPath));
            while (directory != null)
            {
                bool hasManifestRoot = Directory.Exists(Path.Combine(directory.FullName, "manifests"));
                bool hasProjectShape =
                    Directory.Exists(Path.Combine(directory.FullName, "outputs")) ||
                    Directory.Exists(Path.Combine(directory.FullName, "assets")) ||
                    Directory.Exists(Path.Combine(directory.FullName, "storyboards"));
                if (hasManifestRoot && hasProjectShape)
                {
                    return directory.FullName;
                }

                directory = directory.Parent;
            }

            return Path.GetDirectoryName(manifestPath);
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

        [Serializable]
        private sealed class EditTimelineManifest
        {
            public int schema_version;
            public string manifest_type = "";
            public string generated_at = "";
            public StoryBlock story;
            public SettingsBlock settings;
            public float duration_seconds;
            public List<EditTimelineTrackBlock> tracks = new List<EditTimelineTrackBlock>();
        }

        [Serializable]
        private sealed class StoryBlock
        {
            public string story_id = "";
            public string title = "";
        }

        [Serializable]
        private sealed class SettingsBlock
        {
            public int frame_rate = 24;
            public string timeline_unit = "";
        }

        [Serializable]
        private sealed class EditTimelineTrackBlock
        {
            public string track_id = "";
            public string track_type = "";
            public int order;
            public List<EditTimelineClipBlock> clips = new List<EditTimelineClipBlock>();
        }

        [Serializable]
        private sealed class EditTimelineClipBlock
        {
            public string clip_id = "";
            public string shot_id = "";
            public string source_type = "";
            public string source_path = "";
            public float start_seconds;
            public float duration_seconds;
            public EditTimelineMetadataBlock metadata;
        }

        [Serializable]
        private sealed class EditTimelineMetadataBlock
        {
            public string title = "";
            public string result_id = "";
            public string timeline_clip_name = "";
            public string addressable_key = "";
            public string kind = "";
            public string cue_id = "";
            public string speaker = "";
            public string text = "";
            public string emotion = "";
            public string label = "";
            public float volume = 1f;
            public string asset_source = "";
            public bool exists;
            public string target = "";
            public string motion = "";
            public string source = "";
            public float intensity = 1f;
            public string mouth = "";
            public string method = "";
            public MotionPlanClipBlock motion_plan;
        }

        [Serializable]
        private sealed class MotionPlanClipBlock
        {
            public string clip_id = "";
            public string cue_id = "";
            public string shot_id = "";
            public string target = "";
            public string track_name = "";
            public string motion = "";
            public string source = "";
            public string preset = "";
            public int frame_rate = 24;
            public float start_seconds;
            public float duration_seconds;
            public float intensity = 1f;
            public List<MotionPlanKeyframeBlock> keyframes = new List<MotionPlanKeyframeBlock>();
        }

        [Serializable]
        private sealed class MotionPlanKeyframeBlock
        {
            public float time_seconds;
            public List<float> local_position = new List<float>();
            public List<float> local_euler = new List<float>();
            public List<float> local_scale = new List<float>();
        }
    }
}
