using System;
using System.Collections.Generic;
using System.IO;
using UnityEditor;
using UnityEngine;

namespace AIAnimeStudio.Editor
{
    public static class SelectedShotsManifestImporter
    {
        [MenuItem("AI Anime Studio/Import Selected Shots Manifest")]
        public static void ImportFromMenu()
        {
            string manifestPath = EditorUtility.OpenFilePanel(
                "Import selected_shots.json",
                "",
                "json"
            );
            if (string.IsNullOrEmpty(manifestPath))
            {
                return;
            }

            SelectedShotLibrary library = ImportManifest(manifestPath);
            Selection.activeObject = library;
            EditorGUIUtility.PingObject(library);
        }

        public static SelectedShotLibrary ImportManifest(string manifestPath)
        {
            string json = File.ReadAllText(manifestPath);
            SelectedShotsManifest manifest = JsonUtility.FromJson<SelectedShotsManifest>(json);
            if (manifest == null || manifest.story == null)
            {
                throw new InvalidDataException("selected_shots.json could not be parsed.");
            }

            string storyId = SafeFileName(manifest.story.story_id);
            string libraryFolder = EnsureAssetFolder("Assets/AIAnimeStudio/Storyboards/" + storyId);
            string importedFolder = EnsureAssetFolder("Assets/AIAnimeStudio/ImportedShots/" + storyId);
            string animeStudioRoot = FindAnimeStudioRoot(manifestPath);
            SelectedShotLibrary library = ScriptableObject.CreateInstance<SelectedShotLibrary>();
            library.manifestPath = manifestPath;
            library.storyId = manifest.story.story_id;
            library.title = manifest.story.title;
            library.importedAt = DateTime.UtcNow.ToString("o");
            library.shots = new List<SelectedShotClip>();

            foreach (SelectedShotEntry shot in manifest.shots)
            {
                SelectedShotClip clip = BuildClip(shot);
                clip.importedAssetPath = CopySourceAsset(
                    animeStudioRoot,
                    importedFolder,
                    clip.timelineClipName,
                    clip.sourcePath
                );
                clip.previewImage = LoadPreviewImage(clip.importedAssetPath);
                library.shots.Add(clip);
            }

            string libraryPath = libraryFolder + "/SelectedShotLibrary.asset";
            SelectedShotLibrary existing = AssetDatabase.LoadAssetAtPath<SelectedShotLibrary>(libraryPath);
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

        private static SelectedShotClip BuildClip(SelectedShotEntry shot)
        {
            SelectedShotClip clip = new SelectedShotClip();
            clip.shotId = shot.shot_id;
            clip.order = shot.order;
            clip.title = shot.title;
            clip.characterId = shot.character_id;
            clip.durationSeconds = shot.duration_seconds;
            clip.sourcePath = shot.selected_result != null ? shot.selected_result.stored_path : "";
            clip.timelineClipName = shot.unity != null ? shot.unity.timeline_clip_name : "";
            clip.addressableKey = shot.unity != null ? shot.unity.addressable_key : "";
            clip.prompt = shot.prompt;
            clip.negativePrompt = shot.negative_prompt;
            clip.seed = shot.seed;
            clip.width = shot.width;
            clip.height = shot.height;
            clip.steps = shot.steps;
            clip.camera = shot.camera;
            clip.lighting = shot.lighting;
            clip.cameraWork = shot.camera_work != null ? shot.camera_work.ToSummary() : "";
            clip.lightingSetup = shot.lighting_setup != null ? shot.lighting_setup.ToSummary() : "";
            if (shot.camera_work != null)
            {
                clip.cameraFraming = shot.camera_work.framing;
                clip.cameraMovement = shot.camera_work.movement;
                clip.cameraLensMm = shot.camera_work.lens_mm;
                clip.cameraAngle = shot.camera_work.angle;
                clip.cameraFocus = shot.camera_work.focus;
                clip.cameraNotes = shot.camera_work.notes;
            }

            if (shot.lighting_setup != null)
            {
                clip.lightingKeyLight = shot.lighting_setup.key_light;
                clip.lightingFillLight = shot.lighting_setup.fill_light;
                clip.lightingRimLight = shot.lighting_setup.rim_light;
                clip.lightingMood = shot.lighting_setup.mood;
                clip.lightingTimeOfDay = shot.lighting_setup.time_of_day;
                clip.lightingColorPalette = shot.lighting_setup.color_palette;
                clip.lightingNotes = shot.lighting_setup.notes;
            }

            if (string.IsNullOrEmpty(clip.timelineClipName))
            {
                clip.timelineClipName = string.Format("{0:000}_{1}", clip.order, clip.shotId);
            }

            return clip;
        }

        private static string CopySourceAsset(
            string animeStudioRoot,
            string importedFolder,
            string timelineClipName,
            string sourcePath
        )
        {
            if (string.IsNullOrEmpty(sourcePath))
            {
                return "";
            }

            string resolvedSourcePath = ResolveSourcePath(animeStudioRoot, sourcePath);
            if (!File.Exists(resolvedSourcePath))
            {
                Debug.LogWarning("AI Anime Studio source asset was not found: " + resolvedSourcePath);
                return "";
            }

            string extension = Path.GetExtension(resolvedSourcePath);
            string assetFileName = SafeFileName(timelineClipName) + extension;
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
        private sealed class SelectedShotsManifest
        {
            public int schema_version;
            public string manifest_type = "";
            public string generated_at = "";
            public StoryBlock story;
            public CountBlock counts;
            public List<SelectedShotEntry> shots = new List<SelectedShotEntry>();
            public List<MissingShotEntry> missing_shots = new List<MissingShotEntry>();
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
            public int selected_shot_count;
            public int missing_shot_count;
        }

        [Serializable]
        private sealed class SelectedShotEntry
        {
            public string shot_id = "";
            public int order;
            public string title = "";
            public string character_id = "";
            public float duration_seconds;
            public string prompt = "";
            public string negative_prompt = "";
            public string camera = "";
            public string lighting = "";
            public int seed;
            public int width;
            public int height;
            public int steps;
            public string notes = "";
            public CameraWorkBlock camera_work;
            public LightingSetupBlock lighting_setup;
            public SelectedResultBlock selected_result;
            public UnityBlock unity;
        }

        [Serializable]
        private sealed class MissingShotEntry
        {
            public string shot_id = "";
            public int order;
            public string title = "";
            public string reason = "";
        }

        [Serializable]
        private sealed class SelectedResultBlock
        {
            public string result_id = "";
            public string kind = "";
            public string source = "";
            public string stored_path = "";
            public string source_reference = "";
            public string job_id = "";
            public string prompt_id = "";
            public string node_id = "";
            public string decision_notes = "";
            public string decided_at = "";
        }

        [Serializable]
        private sealed class UnityBlock
        {
            public string timeline_clip_name = "";
            public string asset_reference = "";
            public string addressable_key = "";
            public float duration_seconds;
            public int width;
            public int height;
        }

        [Serializable]
        private sealed class CameraWorkBlock
        {
            public string framing = "";
            public string movement = "";
            public int lens_mm;
            public string angle = "";
            public string focus = "";
            public string notes = "";

            public string ToSummary()
            {
                List<string> parts = new List<string>();
                AddIfPresent(parts, framing);
                AddIfPresent(parts, movement);
                if (lens_mm > 0)
                {
                    parts.Add(lens_mm + "mm lens");
                }
                AddIfPresent(parts, angle);
                AddIfPresent(parts, focus);
                AddIfPresent(parts, notes);
                return string.Join(", ", parts.ToArray());
            }
        }

        [Serializable]
        private sealed class LightingSetupBlock
        {
            public string key_light = "";
            public string fill_light = "";
            public string rim_light = "";
            public string mood = "";
            public string time_of_day = "";
            public string color_palette = "";
            public string notes = "";

            public string ToSummary()
            {
                List<string> parts = new List<string>();
                AddIfPresent(parts, key_light);
                AddIfPresent(parts, fill_light);
                AddIfPresent(parts, rim_light);
                AddIfPresent(parts, mood);
                AddIfPresent(parts, time_of_day);
                AddIfPresent(parts, color_palette);
                AddIfPresent(parts, notes);
                return string.Join(", ", parts.ToArray());
            }
        }

        private static void AddIfPresent(List<string> parts, string value)
        {
            if (!string.IsNullOrEmpty(value))
            {
                parts.Add(value);
            }
        }
    }
}
