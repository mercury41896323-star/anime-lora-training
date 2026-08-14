using System;
using System.Collections.Generic;
using UnityEngine;

namespace AIAnimeStudio
{
    [CreateAssetMenu(menuName = "AI Anime Studio/Edit Timeline Library", fileName = "EditTimelineLibrary")]
    public sealed class EditTimelineLibrary : ScriptableObject
    {
        public string manifestPath = "";
        public string storyId = "";
        public string title = "";
        public string importedAt = "";
        public int frameRate = 24;
        public float durationSeconds;
        public bool preserveExistingTimelineEdits = true;
        public int timelineRevision;
        public string lastGeneratedTimelineAssetPath = "";
        public string lastGeneratedRevisionFolder = "";
        public List<EditTimelineTrack> tracks = new List<EditTimelineTrack>();
    }

    [Serializable]
    public sealed class EditTimelineTrack
    {
        public string trackId = "";
        public string trackType = "";
        public int order;
        public List<EditTimelineClip> clips = new List<EditTimelineClip>();
    }

    [Serializable]
    public sealed class EditTimelineClip
    {
        public string clipId = "";
        public string shotId = "";
        public string sourceType = "";
        public string sourcePath = "";
        public string importedAssetPath = "";
        public Texture2D previewImage;
        public AudioClip audioClip;
        public float startSeconds;
        public float durationSeconds;
        public EditTimelineClipMetadata metadata = new EditTimelineClipMetadata();
    }

    [Serializable]
    public sealed class EditTimelineClipMetadata
    {
        public string title = "";
        public string resultId = "";
        public string timelineClipName = "";
        public string addressableKey = "";
        public string kind = "";
        public string cueId = "";
        public string speaker = "";
        public string text = "";
        public string emotion = "";
        public string label = "";
        public float volume = 1f;
        public string assetSource = "";
        public bool exists;
        public string target = "";
        public string motion = "";
        public string source = "";
        public float intensity = 1f;
        public string mouth = "";
        public string method = "";
        public MotionPlanClip motionPlan = new MotionPlanClip();
    }

    [Serializable]
    public sealed class MotionPlanClip
    {
        public string clipId = "";
        public string cueId = "";
        public string shotId = "";
        public string target = "";
        public string trackName = "";
        public string motion = "";
        public string source = "";
        public string preset = "";
        public int frameRate = 24;
        public float startSeconds;
        public float durationSeconds;
        public float intensity = 1f;
        public List<MotionPlanKeyframe> keyframes = new List<MotionPlanKeyframe>();
    }

    [Serializable]
    public sealed class MotionPlanKeyframe
    {
        public float timeSeconds;
        public Vector3 localPosition = Vector3.zero;
        public Vector3 localEuler = Vector3.zero;
        public Vector3 localScale = Vector3.one;
    }
}
