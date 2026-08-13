using System;
using System.Collections.Generic;
using System.IO;
using UnityEditor;
using UnityEngine;
using UnityEngine.Playables;
using UnityEngine.Timeline;

namespace AIAnimeStudio.Editor
{
    public static class SelectedShotsTimelineBuilder
    {
        [MenuItem("AI Anime Studio/Create Timeline From Selected Shot Library")]
        public static void CreateFromMenu()
        {
            SelectedShotLibrary library = Selection.activeObject as SelectedShotLibrary;
            if (library == null)
            {
                string libraryPath = EditorUtility.OpenFilePanel(
                    "Select SelectedShotLibrary asset",
                    Application.dataPath,
                    "asset"
                );
                if (string.IsNullOrEmpty(libraryPath))
                {
                    return;
                }

                libraryPath = ToAssetPath(libraryPath);
                library = AssetDatabase.LoadAssetAtPath<SelectedShotLibrary>(libraryPath);
            }

            if (library == null)
            {
                EditorUtility.DisplayDialog(
                    "AI Anime Studio",
                    "SelectedShotLibrary asset could not be loaded.",
                    "OK"
                );
                return;
            }

            PlayableDirector director = CreateTimeline(library);
            Selection.activeObject = director.gameObject;
            EditorGUIUtility.PingObject(director.gameObject);
        }

        public static PlayableDirector CreateTimeline(SelectedShotLibrary library)
        {
            if (library == null)
            {
                throw new ArgumentNullException(nameof(library));
            }

            string storyId = SafeFileName(string.IsNullOrEmpty(library.storyId) ? "storyboard" : library.storyId);
            string timelineFolder = EnsureAssetFolder("Assets/AIAnimeStudio/Timelines/" + storyId);
            string rootName = storyId + "_Timeline";
            GameObject root = new GameObject(rootName);
            PlayableDirector director = root.AddComponent<PlayableDirector>();
            TimelineAsset timeline = ScriptableObject.CreateInstance<TimelineAsset>();
            string timelinePath = AssetDatabase.GenerateUniqueAssetPath(
                timelineFolder + "/" + SafeFileName(rootName) + ".playable"
            );

            AssetDatabase.CreateAsset(timeline, timelinePath);

            double cursorSeconds = 0.0;
            int visualIndex = 0;
            foreach (SelectedShotClip shot in OrderedShots(library.shots))
            {
                GameObject shotObject = CreateShotPreviewObject(shot, root.transform, visualIndex);
                ActivationTrack track = timeline.CreateTrack<ActivationTrack>(
                    null,
                    string.IsNullOrEmpty(shot.timelineClipName) ? string.Format("{0:000}_{1}", shot.order, shot.shotId) : shot.timelineClipName
                );
                TimelineClip clip = track.CreateDefaultClip();
                clip.displayName = string.IsNullOrEmpty(shot.title) ? shot.timelineClipName : shot.title;
                clip.start = cursorSeconds;
                clip.duration = ShotDuration(shot);
                director.SetGenericBinding(track, shotObject);
                cursorSeconds += clip.duration;
                visualIndex++;
            }

            director.playableAsset = timeline;
            director.timeUpdateMode = DirectorUpdateMode.GameTime;
            EditorUtility.SetDirty(timeline);
            EditorUtility.SetDirty(director);
            AssetDatabase.SaveAssets();
            AssetDatabase.Refresh();
            return director;
        }

        private static GameObject CreateShotPreviewObject(SelectedShotClip shot, Transform parent, int visualIndex)
        {
            string objectName = string.IsNullOrEmpty(shot.timelineClipName)
                ? string.Format("{0:000}_{1}", shot.order, shot.shotId)
                : shot.timelineClipName;
            GameObject shotObject = new GameObject(objectName);
            shotObject.transform.SetParent(parent);
            shotObject.transform.localPosition = new Vector3(0f, 0f, visualIndex * 0.01f);
            shotObject.transform.localRotation = Quaternion.identity;
            shotObject.transform.localScale = Vector3.one;

            if (shot.previewImage != null)
            {
                SpriteRenderer renderer = shotObject.AddComponent<SpriteRenderer>();
                renderer.sprite = Sprite.Create(
                    shot.previewImage,
                    new Rect(0f, 0f, shot.previewImage.width, shot.previewImage.height),
                    new Vector2(0.5f, 0.5f),
                    100f
                );
                renderer.sortingOrder = visualIndex;
            }
            else
            {
                TextMesh label = shotObject.AddComponent<TextMesh>();
                label.text = string.IsNullOrEmpty(shot.title) ? objectName : shot.title;
                label.characterSize = 0.2f;
                label.anchor = TextAnchor.MiddleCenter;
            }

            shotObject.SetActive(false);
            return shotObject;
        }

        private static List<SelectedShotClip> OrderedShots(List<SelectedShotClip> shots)
        {
            List<SelectedShotClip> ordered = new List<SelectedShotClip>(shots ?? new List<SelectedShotClip>());
            ordered.Sort((left, right) => left.order.CompareTo(right.order));
            return ordered;
        }

        private static double ShotDuration(SelectedShotClip shot)
        {
            return shot.durationSeconds > 0f ? shot.durationSeconds : 1.0;
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
