using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
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
            string animationFolder = EnsureAssetFolder(timelineFolder + "/CameraAnimations");
            EnsureCinemachineBrain(root.transform);

            AssetDatabase.CreateAsset(timeline, timelinePath);

            double cursorSeconds = 0.0;
            int visualIndex = 0;
            foreach (SelectedShotClip shot in OrderedShots(library.shots))
            {
                GameObject shotObject = CreateShotPreviewObject(shot, root.transform, visualIndex);
                GameObject cameraObject = CreateShotCameraRig(shot, shotObject.transform);
                CreateShotLightingRig(shot, shotObject.transform);
                double shotStartSeconds = cursorSeconds;
                double shotDurationSeconds = ShotDuration(shot);
                ActivationTrack track = timeline.CreateTrack<ActivationTrack>(
                    null,
                    string.IsNullOrEmpty(shot.timelineClipName) ? string.Format("{0:000}_{1}", shot.order, shot.shotId) : shot.timelineClipName
                );
                TimelineClip clip = track.CreateDefaultClip();
                clip.displayName = string.IsNullOrEmpty(shot.title) ? shot.timelineClipName : shot.title;
                clip.start = shotStartSeconds;
                clip.duration = shotDurationSeconds;
                director.SetGenericBinding(track, shotObject);
                CreateCameraMovementTrack(
                    timeline,
                    director,
                    shot,
                    cameraObject,
                    animationFolder,
                    shotStartSeconds,
                    shotDurationSeconds
                );
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

        private static GameObject CreateShotCameraRig(SelectedShotClip shot, Transform parent)
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
            cameraObject.AddComponent<Animator>();

            GameObject virtualCameraObject = CreateCinemachineVirtualCamera(
                shot,
                parent,
                cameraObject.transform,
                camera.fieldOfView
            );
            return virtualCameraObject != null ? virtualCameraObject : cameraObject;
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

        private static GameObject CreateCinemachineVirtualCamera(
            SelectedShotClip shot,
            Transform parent,
            Transform sourceTransform,
            float fieldOfView
        )
        {
            Type virtualCameraType = FindCinemachineType(
                "Unity.Cinemachine.CinemachineCamera, Unity.Cinemachine",
                "Cinemachine.CinemachineVirtualCamera, Cinemachine"
            );
            if (virtualCameraType == null)
            {
                return null;
            }

            GameObject virtualCameraObject = new GameObject("VirtualCamera_" + SafeFileName(ShotObjectName(shot)));
            virtualCameraObject.transform.SetParent(parent);
            virtualCameraObject.transform.localPosition = sourceTransform.localPosition;
            virtualCameraObject.transform.localRotation = sourceTransform.localRotation;
            virtualCameraObject.transform.localScale = Vector3.one;

            Component virtualCamera = virtualCameraObject.AddComponent(virtualCameraType);
            virtualCameraObject.AddComponent<Animator>();
            SetCinemachinePriority(virtualCamera, shot.order);
            SetCinemachineFieldOfView(virtualCamera, fieldOfView);
            return virtualCameraObject;
        }

        private static void EnsureCinemachineBrain(Transform parent)
        {
            Type brainType = FindCinemachineType(
                "Unity.Cinemachine.CinemachineBrain, Unity.Cinemachine",
                "Cinemachine.CinemachineBrain, Cinemachine"
            );
            if (brainType == null)
            {
                return;
            }

            Camera mainCamera = Camera.main;
            GameObject brainObject;
            if (mainCamera != null)
            {
                brainObject = mainCamera.gameObject;
            }
            else
            {
                brainObject = new GameObject("Cinemachine_Brain_Camera");
                brainObject.transform.SetParent(parent);
                brainObject.transform.localPosition = new Vector3(0f, 1.5f, -6f);
                brainObject.transform.localRotation = Quaternion.Euler(10f, 0f, 0f);
                brainObject.transform.localScale = Vector3.one;
                mainCamera = brainObject.AddComponent<Camera>();
                mainCamera.depth = -100;
            }

            if (brainObject.GetComponent(brainType) == null)
            {
                brainObject.AddComponent(brainType);
            }
        }

        private static Type FindCinemachineType(params string[] typeNames)
        {
            foreach (string typeName in typeNames)
            {
                Type type = Type.GetType(typeName);
                if (type != null)
                {
                    return type;
                }
            }

            foreach (Assembly assembly in AppDomain.CurrentDomain.GetAssemblies())
            {
                foreach (string typeName in typeNames)
                {
                    string shortTypeName = typeName.Split(',')[0].Trim();
                    Type type = assembly.GetType(shortTypeName);
                    if (type != null)
                    {
                        return type;
                    }
                }
            }

            return null;
        }

        private static void SetCinemachinePriority(Component virtualCamera, int priority)
        {
            const BindingFlags bindingFlags = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance;
            Type type = virtualCamera.GetType();
            PropertyInfo priorityProperty = type.GetProperty("Priority", bindingFlags);
            if (priorityProperty != null && priorityProperty.CanWrite && priorityProperty.PropertyType == typeof(int))
            {
                priorityProperty.SetValue(virtualCamera, priority, null);
                return;
            }

            FieldInfo priorityField = type.GetField("m_Priority", bindingFlags);
            if (priorityField != null && priorityField.FieldType == typeof(int))
            {
                priorityField.SetValue(virtualCamera, priority);
            }
        }

        private static void SetCinemachineFieldOfView(Component virtualCamera, float fieldOfView)
        {
            const BindingFlags bindingFlags = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance;
            Type type = virtualCamera.GetType();
            FieldInfo lensField = type.GetField("m_Lens", bindingFlags);
            if (lensField == null)
            {
                return;
            }

            object lens = lensField.GetValue(virtualCamera);
            if (lens == null)
            {
                return;
            }

            Type lensType = lens.GetType();
            PropertyInfo fieldOfViewProperty = lensType.GetProperty("FieldOfView", bindingFlags);
            if (fieldOfViewProperty != null && fieldOfViewProperty.CanWrite)
            {
                fieldOfViewProperty.SetValue(lens, fieldOfView, null);
                lensField.SetValue(virtualCamera, lens);
                return;
            }

            FieldInfo fieldOfViewField = lensType.GetField("m_FieldOfView", bindingFlags);
            if (fieldOfViewField != null)
            {
                fieldOfViewField.SetValue(lens, fieldOfView);
                lensField.SetValue(virtualCamera, lens);
            }
        }

        private static void CreateCameraMovementTrack(
            TimelineAsset timeline,
            PlayableDirector director,
            SelectedShotClip shot,
            GameObject cameraObject,
            string animationFolder,
            double startSeconds,
            double durationSeconds
        )
        {
            if (!HasCameraMovement(shot))
            {
                return;
            }

            AnimationClip animationClip = BuildCameraMovementClip(shot, cameraObject.transform, durationSeconds);
            string animationPath = AssetDatabase.GenerateUniqueAssetPath(
                animationFolder + "/" + SafeFileName("CameraMove_" + ShotObjectName(shot)) + ".anim"
            );
            AssetDatabase.CreateAsset(animationClip, animationPath);

            AnimationTrack animationTrack = timeline.CreateTrack<AnimationTrack>(
                null,
                "CameraMove_" + ShotObjectName(shot)
            );
            TimelineClip movementClip = animationTrack.CreateClip<AnimationPlayableAsset>();
            AnimationPlayableAsset playableAsset = movementClip.asset as AnimationPlayableAsset;
            if (playableAsset != null)
            {
                playableAsset.clip = animationClip;
            }

            movementClip.displayName = "camera movement";
            movementClip.start = startSeconds;
            movementClip.duration = durationSeconds;
            director.SetGenericBinding(animationTrack, cameraObject.GetComponent<Animator>());
        }

        private static AnimationClip BuildCameraMovementClip(
            SelectedShotClip shot,
            Transform cameraTransform,
            double durationSeconds
        )
        {
            float duration = Mathf.Max(0.1f, (float)durationSeconds);
            Vector3 startPosition = cameraTransform.localPosition;
            Vector3 endPosition = CameraMovementEndPosition(shot, startPosition);
            Vector3 startEuler = cameraTransform.localEulerAngles;
            Vector3 endEuler = CameraMovementEndEuler(shot, startEuler);

            AnimationClip animationClip = new AnimationClip();
            animationClip.frameRate = 24f;
            animationClip.wrapMode = WrapMode.Once;
            SetLinearCurve(animationClip, "localPosition.x", startPosition.x, endPosition.x, duration);
            SetLinearCurve(animationClip, "localPosition.y", startPosition.y, endPosition.y, duration);
            SetLinearCurve(animationClip, "localPosition.z", startPosition.z, endPosition.z, duration);
            SetLinearCurve(animationClip, "localEulerAnglesRaw.x", startEuler.x, endEuler.x, duration);
            SetLinearCurve(animationClip, "localEulerAnglesRaw.y", startEuler.y, endEuler.y, duration);
            SetLinearCurve(animationClip, "localEulerAnglesRaw.z", startEuler.z, endEuler.z, duration);
            return animationClip;
        }

        private static void SetLinearCurve(AnimationClip animationClip, string propertyName, float start, float end, float duration)
        {
            AnimationCurve curve = AnimationCurve.Linear(0f, start, duration, end);
            animationClip.SetCurve("", typeof(Transform), propertyName, curve);
        }

        private static bool HasCameraMovement(SelectedShotClip shot)
        {
            string movement = CombinedLower(shot.cameraMovement, shot.cameraWork, shot.camera);
            return HasText(movement) && !ContainsAny(movement, "static", "locked", "fixed", "none", "still");
        }

        private static Vector3 CameraMovementEndPosition(SelectedShotClip shot, Vector3 startPosition)
        {
            string movement = CombinedLower(shot.cameraMovement, shot.cameraWork, shot.camera);
            Vector3 endPosition = startPosition;

            if (ContainsAny(movement, "dolly in", "push in", "track in", "move in", "zoom in"))
            {
                endPosition.z += 0.9f;
            }
            else if (ContainsAny(movement, "dolly out", "pull back", "track out", "move out", "zoom out"))
            {
                endPosition.z -= 0.9f;
            }

            if (ContainsAny(movement, "truck left", "slide left", "move left"))
            {
                endPosition.x -= 0.7f;
            }
            else if (ContainsAny(movement, "truck right", "slide right", "move right"))
            {
                endPosition.x += 0.7f;
            }

            if (ContainsAny(movement, "crane up", "rise", "move up"))
            {
                endPosition.y += 0.5f;
            }
            else if (ContainsAny(movement, "crane down", "fall", "move down"))
            {
                endPosition.y -= 0.5f;
            }

            return endPosition;
        }

        private static Vector3 CameraMovementEndEuler(SelectedShotClip shot, Vector3 startEuler)
        {
            string movement = CombinedLower(shot.cameraMovement, shot.cameraWork, shot.camera);
            Vector3 endEuler = startEuler;

            if (ContainsAny(movement, "pan left"))
            {
                endEuler.y -= 8f;
            }
            else if (ContainsAny(movement, "pan right"))
            {
                endEuler.y += 8f;
            }

            if (ContainsAny(movement, "tilt up"))
            {
                endEuler.x -= 6f;
            }
            else if (ContainsAny(movement, "tilt down"))
            {
                endEuler.x += 6f;
            }

            if (ContainsAny(movement, "roll left"))
            {
                endEuler.z += 4f;
            }
            else if (ContainsAny(movement, "roll right"))
            {
                endEuler.z -= 4f;
            }

            return endEuler;
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
