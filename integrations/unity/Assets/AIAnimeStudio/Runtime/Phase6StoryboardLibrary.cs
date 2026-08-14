using System;
using System.Collections.Generic;
using UnityEngine;

namespace AIAnimeStudio
{
    [CreateAssetMenu(menuName = "AI Anime Studio/Phase 6 Storyboard Library", fileName = "Phase6StoryboardLibrary")]
    public sealed class Phase6StoryboardLibrary : ScriptableObject
    {
        public string manifestPath = "";
        public string storyId = "";
        public string title = "";
        public string importedAt = "";
        public List<Phase6ShotClip> shots = new List<Phase6ShotClip>();
    }

    [Serializable]
    public sealed class Phase6ShotClip
    {
        public string shotId = "";
        public int order;
        public string title = "";
        public float durationSeconds;
        public string selectedResultPath = "";
        public List<Phase6VoiceCue> voiceCues = new List<Phase6VoiceCue>();
        public List<Phase6LipSyncCue> lipSyncCues = new List<Phase6LipSyncCue>();
        public List<Phase6SfxCue> sfxCues = new List<Phase6SfxCue>();
        public List<Phase6MotionCue> motionCues = new List<Phase6MotionCue>();
    }

    [Serializable]
    public sealed class Phase6VoiceCue
    {
        public string cueId = "";
        public string shotId = "";
        public string characterId = "";
        public string speaker = "";
        public string text = "";
        public string language = "";
        public string emotion = "";
        public string voiceAssetPath = "";
        public string importedAssetPath = "";
        public AudioClip audioClip;
        public float startSeconds;
        public float durationSeconds;
        public string notes = "";
    }

    [Serializable]
    public sealed class Phase6LipSyncCue
    {
        public string cueId = "";
        public string shotId = "";
        public string voiceCueId = "";
        public string method = "";
        public string text = "";
        public float startSeconds;
        public float durationSeconds;
        public List<Phase6VisemeCue> visemes = new List<Phase6VisemeCue>();
    }

    [Serializable]
    public sealed class Phase6VisemeCue
    {
        public float timeSeconds;
        public string mouth = "";
    }

    [Serializable]
    public sealed class Phase6SfxCue
    {
        public string cueId = "";
        public string shotId = "";
        public string label = "";
        public string assetPath = "";
        public string importedAssetPath = "";
        public AudioClip audioClip;
        public float startSeconds;
        public float durationSeconds;
        public float volume = 1f;
        public List<string> tags = new List<string>();
        public string notes = "";
    }

    [Serializable]
    public sealed class Phase6MotionCue
    {
        public string cueId = "";
        public string shotId = "";
        public string target = "";
        public string motion = "";
        public string source = "";
        public float startSeconds;
        public float durationSeconds;
        public float intensity = 1f;
        public string notes = "";
    }
}
