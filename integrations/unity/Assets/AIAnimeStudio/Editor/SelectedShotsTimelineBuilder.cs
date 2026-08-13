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
                CreateShotCameraRig(shot, shotObject.transform);
                CreateShotLightingRig(shot, shotObject.transform);
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

        private static void CreateShotCameraRig(SelectedShotClip shot, Transform parent)
        {
            GameObject cameraObject = new GameObject("Camera_" + SafeFileName(ShotObjectName(shot)));
            cameraObject.transform.SetParent(parent);
            cameraObject.transform.localPosition = CameraPosition(shot);
            cameraObject.transform.localRotation = CameraRotation(shot);
            cameraObject.transform.localScale = Vector3.one;

            Camera camera = cameraObject.AddComponent<Camera>();
            camera.fieldOfView = LensToFieldOfView(shot.cameraLensMm);
            camera.nearClipPlane = 0.1f;
            camera.farClipPlane = 100f;
            camera.depth = shot.order;
        }

        private static void CreateShotLightingRig(SelectedShotClip shot, Transform parent)
        {
            GameObject lightingRoot = new GameObject("Lighting_" + SafeFileName(ShotObjectName(shot)));
            lightingRoot.transform.SetParent(parent);
            lightingRoot.transform.localPosition = Vector3.zero;
            lightingRoot.transform.localRotation = Quaternion.identity;
            lightingRoot.transform.localScale = Vector3.one;

            bool hasLighting = HasText(shot.lightingKeyLight) ||
                HasText(shot.lightingFillLight) ||
                HasText(shot.lightingRimLight) ||
                HasText(shot.lightingMood) ||
                HasText(shot.lightingTimeOfDay) ||
                HasText(shot.lightingColorPalette);

            CreateDirectionalLight(
                lightingRoot.transform,
                HasText(shot.lightingKeyLight) ? "KeyLight_" + SafeFileName(shot.lightingKeyLight) : "KeyLight_Default",
                new Vector3(50f, -30f, 0f),
                hasLighting ? KeyLightIntensity(shot) : 0.9f,
                LightingColor(shot)
            );

            if (HasText(shot.lightingFillLight))
            {
                CreateDirectionalLight(
                    lightingRoot.transform,
                    "FillLight_" + SafeFileName(shot.lightingFillLight),
                    new Vector3(20f, 45f, 0f),
                    0.35f,
                    LightingColor(shot)
                );
            }

            if (HasText(shot.lightingRimLight))
            {
                CreateDirectionalLight(
                    lightingRoot.transform,
                    "RimLight_" + SafeFileName(shot.lightingRimLight),
                    new Vector3(35f, 145f, 0f),
                    0.55f,
                    Color.white
                );
            }
        }

        private static Light CreateDirectionalLight(
            Transform parent,
            string lightName,
            Vector3 eulerAngles,
            float intensity,
            Color color
        )
        {
            GameObject lightObject = new GameObject(lightName);
            lightObject.transform.SetParent(parent);
            lightObject.transform.localPosition = Vector3.zero;
            lightObject.transform.localRotation = Quaternion.Euler(eulerAngles);
            lightObject.transform.localScale = Vector3.one;

            Light light = lightObject.AddComponent<Light>();
            light.type = LightType.Directional;
            light.intensity = intensity;
            light.color = color;
            return light;
        }

        private static Vector3 CameraPosition(SelectedShotClip shot)
        {
            string framing = CombinedLower(shot.cameraFraming, shot.cameraWork, shot.camera);
            float distance = 6f;
            float height = 1.5f;

            if (ContainsAny(framing, "close", "アップ", "寄り"))
            {
                distance = 2.5f;
                height = 1.35f;
            }
            else if (ContainsAny(framing, "medium", "waist", "bust", "ミディアム", "バスト", "腰"))
            {
                distance = 4f;
            }
            else if (ContainsAny(framing, "wide", "long", "establishing", "引き", "ロング"))
            {
                distance = 8f;
                height = 1.8f;
            }

            return new Vector3(0f, height, -distance);
        }

        private static Quaternion CameraRotation(SelectedShotClip shot)
        {
            string angle = CombinedLower(shot.cameraAngle, shot.cameraWork, shot.camera);
            float pitch = 10f;
            float yaw = 0f;
            float roll = 0f;

            if (ContainsAny(angle, "low", "ロー"))
            {
                pitch = -6f;
            }
            else if (ContainsAny(angle, "high", "俯瞰", "ハイ"))
            {
                pitch = 24f;
            }

            if (ContainsAny(angle, "side", "profile", "横"))
            {
                yaw = 22f;
            }

            if (ContainsAny(angle, "dutch", "tilt", "斜め"))
            {
                roll = 7f;
            }

            return Quaternion.Euler(pitch, yaw, roll);
        }

        private static float LensToFieldOfView(int lensMm)
        {
            if (lensMm <= 0)
            {
                return 50f;
            }

            float sensorHeightMm = 24f;
            float fieldOfView = 2f * Mathf.Atan(sensorHeightMm / (2f * lensMm)) * Mathf.Rad2Deg;
            return Mathf.Clamp(fieldOfView, 18f, 75f);
        }

        private static float KeyLightIntensity(SelectedShotClip shot)
        {
            string lighting = CombinedLower(
                shot.lightingKeyLight,
                shot.lightingMood,
                shot.lightingTimeOfDay,
                shot.lightingSetup,
                shot.lighting
            );
            if (ContainsAny(lighting, "night", "moon", "dark", "low key", "夜", "暗"))
            {
                return 0.55f;
            }

            if (ContainsAny(lighting, "bright", "day", "sun", "昼", "明る"))
            {
                return 1.2f;
            }

            return 0.9f;
        }

        private static Color LightingColor(SelectedShotClip shot)
        {
            string lighting = CombinedLower(
                shot.lightingColorPalette,
                shot.lightingMood,
                shot.lightingTimeOfDay,
                shot.lightingSetup,
                shot.lighting
            );
            if (ContainsAny(lighting, "blue", "cool", "moon", "night", "青", "寒色", "夜"))
            {
                return new Color(0.58f, 0.72f, 1f);
            }

            if (ContainsAny(lighting, "sunset", "gold", "orange", "warm", "夕", "朝", "暖色"))
            {
                return new Color(1f, 0.74f, 0.48f);
            }

            if (ContainsAny(lighting, "neon", "cyber", "magenta", "pink", "ネオン"))
            {
                return new Color(1f, 0.55f, 0.95f);
            }

            return Color.white;
        }

        private static string ShotObjectName(SelectedShotClip shot)
        {
            if (!string.IsNullOrEmpty(shot.timelineClipName))
            {
                return shot.timelineClipName;
            }

            return string.Format("{0:000}_{1}", shot.order, shot.shotId);
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
