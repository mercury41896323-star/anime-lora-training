using System;
using System.Collections.Generic;
using System.IO;
using UnityEditor;
using UnityEngine;

namespace AIAnimeStudio.Editor
{
    public static class Phase6ManifestImporter
    {
        [MenuItem("AI Anime Studio/Import Phase 6 Manifest")]
        public static void ImportFromMenu()
        {
            string manifestPath = EditorUtility.OpenFilePanel(
                "Import phase6_manifest.json",
                "",
                "json"
            );
            if (string.IsNullOrEmpty(manifestPath))
            {
                return;
            }

            Phase6StoryboardLibrary library = ImportManifest(manifestPath);
            Selection.activeObject = library;
            EditorGUIUtility.PingObject(library);
        }

        public static Phase6StoryboardLibrary ImportManifest(string manifestPath)
        {
            string json = File.ReadAllText(manifestPath);
            Phase6Manifest manifest = JsonUtility.FromJson<Phase6Manifest>(json);
            if (manifest == null || manifest.story == null)
            {
                throw new InvalidDataException("phase6_manifest.json could not be parsed.");
            }

            string storyId = SafeFileName(manifest.story.story_id);
            string libraryFolder = EnsureAssetFolder("Assets/AIAnimeStudio/Storyboards/" + storyId);
            string audioFolder = EnsureAssetFolder("Assets/AIAnimeStudio/ImportedAudio/" + storyId);
            string animeStudioRoot = FindAnimeStudioRoot(manifestPath);
            Phase6StoryboardLibrary library = ScriptableObject.CreateInstance<Phase6StoryboardLibrary>();
            library.manifestPath = manifestPath;
            library.storyId = manifest.story.story_id;
            library.title = manifest.story.title;
            library.importedAt = DateTime.UtcNow.ToString("o");
            library.shots = new List<Phase6ShotClip>();

            foreach (Phase6ShotEntry shot in manifest.shots)
            {
                library.shots.Add(BuildShotClip(animeStudioRoot, audioFolder, shot));
            }

            string libraryPath = libraryFolder + "/Phase6StoryboardLibrary.asset";
            Phase6StoryboardLibrary existing = AssetDatabase.LoadAssetAtPath<Phase6StoryboardLibrary>(libraryPath);
            if (existing != null)
            {
                existing.manifestPath = library.manifestPath;
                existing.storyId = library.storyId;
                existing.title = library.title;
                existing.importedAt = library.importedAt;
                existing.shots = library.shots;
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

        private static Phase6ShotClip BuildShotClip(string animeStudioRoot, string audioFolder, Phase6ShotEntry shot)
        {
            Phase6ShotClip clip = new Phase6ShotClip();
            clip.shotId = shot.shot_id;
            clip.order = shot.order;
            clip.title = shot.title;
            clip.durationSeconds = shot.duration_seconds;
            clip.selectedResultPath = shot.selected_result != null ? shot.selected_result.stored_path : "";
            clip.voiceCues = BuildVoiceCues(animeStudioRoot, audioFolder, shot.voice_cues);
            clip.lipSyncCues = BuildLipSyncCues(shot.lip_sync_cues);
            clip.sfxCues = BuildSfxCues(animeStudioRoot, audioFolder, shot.sfx_cues);
            clip.motionCues = BuildMotionCues(shot.motion_cues);
            return clip;
        }

        private static List<Phase6VoiceCue> BuildVoiceCues(
            string animeStudioRoot,
            string audioFolder,
            List<VoiceCueBlock> cues
        )
        {
            List<Phase6VoiceCue> result = new List<Phase6VoiceCue>();
            foreach (VoiceCueBlock cue in cues ?? new List<VoiceCueBlock>())
            {
                Phase6VoiceCue item = new Phase6VoiceCue();
                item.cueId = cue.cue_id;
                item.shotId = cue.shot_id;
                item.characterId = cue.character_id;
                item.speaker = cue.speaker;
                item.text = cue.text;
                item.language = cue.language;
                item.emotion = cue.emotion;
                item.voiceAssetPath = cue.voice_asset_path;
                item.importedAssetPath = CopyAudioAsset(animeStudioRoot, audioFolder, cue.cue_id, cue.voice_asset_path);
                item.audioClip = LoadAudioClip(item.importedAssetPath);
                item.startSeconds = cue.start_seconds;
                item.durationSeconds = cue.duration_seconds;
                item.notes = cue.notes;
                result.Add(item);
            }

            return result;
        }

        private static List<Phase6LipSyncCue> BuildLipSyncCues(List<LipSyncCueBlock> cues)
        {
            List<Phase6LipSyncCue> result = new List<Phase6LipSyncCue>();
            foreach (LipSyncCueBlock cue in cues ?? new List<LipSyncCueBlock>())
            {
                Phase6LipSyncCue item = new Phase6LipSyncCue();
                item.cueId = cue.cue_id;
                item.shotId = cue.shot_id;
                item.voiceCueId = cue.voice_cue_id;
                item.method = cue.method;
                item.text = cue.text;
                item.startSeconds = cue.start_seconds;
                item.durationSeconds = cue.duration_seconds;
                item.visemes = new List<Phase6VisemeCue>();
                foreach (VisemeBlock viseme in cue.visemes ?? new List<VisemeBlock>())
                {
                    item.visemes.Add(new Phase6VisemeCue
                    {
                        timeSeconds = viseme.time_seconds,
                        mouth = viseme.mouth
                    });
                }

                result.Add(item);
            }

            return result;
        }

        private static List<Phase6SfxCue> BuildSfxCues(
            string animeStudioRoot,
            string audioFolder,
            List<SfxCueBlock> cues
        )
        {
            List<Phase6SfxCue> result = new List<Phase6SfxCue>();
            foreach (SfxCueBlock cue in cues ?? new List<SfxCueBlock>())
            {
                Phase6SfxCue item = new Phase6SfxCue();
                item.cueId = cue.cue_id;
                item.shotId = cue.shot_id;
                item.label = cue.label;
                item.assetPath = cue.asset_path;
                item.importedAssetPath = CopyAudioAsset(animeStudioRoot, audioFolder, cue.cue_id, cue.asset_path);
                item.audioClip = LoadAudioClip(item.importedAssetPath);
                item.startSeconds = cue.start_seconds;
                item.durationSeconds = cue.duration_seconds;
                item.volume = cue.volume;
                item.tags = cue.tags ?? new List<string>();
                item.notes = cue.notes;
                result.Add(item);
            }

            return result;
        }

        private static List<Phase6MotionCue> BuildMotionCues(List<MotionCueBlock> cues)
        {
            List<Phase6MotionCue> result = new List<Phase6MotionCue>();
            foreach (MotionCueBlock cue in cues ?? new List<MotionCueBlock>())
            {
                result.Add(new Phase6MotionCue
                {
                    cueId = cue.cue_id,
                    shotId = cue.shot_id,
                    target = cue.target,
                    motion = cue.motion,
                    source = cue.source,
                    startSeconds = cue.start_seconds,
                    durationSeconds = cue.duration_seconds,
                    intensity = cue.intensity,
                    notes = cue.notes
                });
            }

            return result;
        }

        private static string CopyAudioAsset(string animeStudioRoot, string audioFolder, string cueId, string sourcePath)
        {
            if (string.IsNullOrEmpty(sourcePath))
            {
                return "";
            }

            string resolvedSourcePath = ResolveSourcePath(animeStudioRoot, sourcePath);
            if (!File.Exists(resolvedSourcePath))
            {
                Debug.LogWarning("AI Anime Studio audio asset was not found: " + resolvedSourcePath);
                return "";
            }

            string extension = Path.GetExtension(resolvedSourcePath).ToLowerInvariant();
            if (extension != ".wav" && extension != ".mp3" && extension != ".ogg" && extension != ".aiff")
            {
                Debug.LogWarning("AI Anime Studio audio asset type may not be supported by Unity: " + resolvedSourcePath);
            }

            string assetFileName = SafeFileName(cueId) + extension;
            string targetAssetPath = audioFolder + "/" + assetFileName;
            string targetFullPath = Path.GetFullPath(targetAssetPath);
            Directory.CreateDirectory(Path.GetDirectoryName(targetFullPath));
            File.Copy(resolvedSourcePath, targetFullPath, true);
            AssetDatabase.ImportAsset(targetAssetPath);
            return targetAssetPath;
        }

        private static AudioClip LoadAudioClip(string assetPath)
        {
            if (string.IsNullOrEmpty(assetPath))
            {
                return null;
            }

            return AssetDatabase.LoadAssetAtPath<AudioClip>(assetPath);
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
        private sealed class Phase6Manifest
        {
            public int schema_version;
            public string manifest_type = "";
            public string generated_at = "";
            public StoryBlock story;
            public CountBlock counts;
            public List<Phase6ShotEntry> shots = new List<Phase6ShotEntry>();
        }

        [Serializable]
        private sealed class StoryBlock
        {
            public string story_id = "";
            public string title = "";
        }

        [Serializable]
        private sealed class CountBlock
        {
            public int shot_count;
            public int voice_count;
            public int lip_sync_count;
            public int sfx_count;
            public int motion_count;
        }

        [Serializable]
        private sealed class Phase6ShotEntry
        {
            public string shot_id = "";
            public int order;
            public string title = "";
            public float duration_seconds;
            public SelectedResultBlock selected_result;
            public List<VoiceCueBlock> voice_cues = new List<VoiceCueBlock>();
            public List<LipSyncCueBlock> lip_sync_cues = new List<LipSyncCueBlock>();
            public List<SfxCueBlock> sfx_cues = new List<SfxCueBlock>();
            public List<MotionCueBlock> motion_cues = new List<MotionCueBlock>();
        }

        [Serializable]
        private sealed class SelectedResultBlock
        {
            public string stored_path = "";
        }

        [Serializable]
        private sealed class VoiceCueBlock
        {
            public string cue_id = "";
            public string shot_id = "";
            public string character_id = "";
            public string speaker = "";
            public string text = "";
            public string language = "";
            public string emotion = "";
            public string voice_asset_path = "";
            public float start_seconds;
            public float duration_seconds;
            public string notes = "";
        }

        [Serializable]
        private sealed class LipSyncCueBlock
        {
            public string cue_id = "";
            public string shot_id = "";
            public string voice_cue_id = "";
            public string method = "";
            public string text = "";
            public float start_seconds;
            public float duration_seconds;
            public List<VisemeBlock> visemes = new List<VisemeBlock>();
        }

        [Serializable]
        private sealed class VisemeBlock
        {
            public float time_seconds;
            public string mouth = "";
        }

        [Serializable]
        private sealed class SfxCueBlock
        {
            public string cue_id = "";
            public string shot_id = "";
            public string label = "";
            public string asset_path = "";
            public float start_seconds;
            public float duration_seconds;
            public float volume = 1f;
            public List<string> tags = new List<string>();
            public string notes = "";
        }

        [Serializable]
        private sealed class MotionCueBlock
        {
            public string cue_id = "";
            public string shot_id = "";
            public string target = "";
            public string motion = "";
            public string source = "";
            public float start_seconds;
            public float duration_seconds;
            public float intensity = 1f;
            public string notes = "";
        }
    }
}
