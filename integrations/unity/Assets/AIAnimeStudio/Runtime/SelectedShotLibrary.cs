using System;
using System.Collections.Generic;
using UnityEngine;

namespace AIAnimeStudio
{
    [CreateAssetMenu(menuName = "AI Anime Studio/Selected Shot Library", fileName = "SelectedShotLibrary")]
    public sealed class SelectedShotLibrary : ScriptableObject
    {
        public string manifestPath = "";
        public string storyId = "";
        public string title = "";
        public string importedAt = "";
        public List<SelectedShotClip> shots = new List<SelectedShotClip>();
    }

    [Serializable]
    public sealed class SelectedShotClip
    {
        public string shotId = "";
        public int order;
        public string title = "";
        public string characterId = "";
        public float durationSeconds;
        public string sourcePath = "";
        public string importedAssetPath = "";
        public Texture2D previewImage;
        public string timelineClipName = "";
        public string addressableKey = "";
        public string prompt = "";
        public string negativePrompt = "";
        public int seed;
        public int width;
        public int height;
        public int steps;
        public string camera = "";
        public string lighting = "";
        public string cameraWork = "";
        public string lightingSetup = "";
    }
}
