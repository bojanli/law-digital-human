using System;
using System.Collections;
using System.Runtime.InteropServices;
using UnityEngine;
using UnityEngine.Networking;

public class WebBridge : MonoBehaviour
{
    [SerializeField] private Animator animator;
    [SerializeField] private AudioSource audioSource;
    [SerializeField] private bool verboseLogging = true;
    [SerializeField] private bool enableEditorHotkeys = true;
    [Header("Lip Sync (Simple Volume Drive)")]
    [SerializeField] private bool enableLipSync = true;
    [SerializeField] private SkinnedMeshRenderer lipSyncFaceRenderer;
    [SerializeField] private int mouthOpenBlendShapeIndex = -1;
    [SerializeField] private string mouthOpenBlendShapeName = "MouthOpen";
    [SerializeField, Range(0f, 0.2f)] private float lipSyncSilenceThreshold = 0.01f;
    [SerializeField, Range(0.02f, 0.6f)] private float lipSyncMaxRms = 0.12f;
    [SerializeField, Range(1f, 40f)] private float lipSyncSmoothing = 16f;
    [SerializeField, Range(0.5f, 2.5f)] private float lipSyncGamma = 1.2f;
    [SerializeField] private bool autoFindMouthBlendShape = true;

#if UNITY_WEBGL && !UNITY_EDITOR
    [DllImport("__Internal")]
    private static extern void UnityToWeb(string message);
#endif

    [Serializable]
    private class CommandPayload
    {
        public string emotionTag;
        public string gestureTag;
        public string audioUrl;
        public string subtitleText;
    }

    [Serializable]
    private class WebCommand
    {
        public string source;
        public string target;
        public string command;
        public CommandPayload payload;
    }

    [Serializable]
    private class UnityEventMessage
    {
        public string source = "unity-avatar";
        public string target = "law-web";
        public string @event;
    }

    private Coroutine playRoutine;
    private bool wasPlaying;
    private float currentMouthWeight;
    private readonly float[] audioSamples = new float[256];

    private void Awake()
    {
        if (audioSource == null)
        {
            audioSource = GetComponent<AudioSource>();
        }
        ResolveLipSyncTarget();
        Log($"Awake done. AnimatorBound={animator != null}, AudioSourceBound={audioSource != null}");
    }

    private void Start()
    {
        Log("Start -> send OnAvatarReady");
        SendEventToWeb("OnAvatarReady");
    }

    private void Update()
    {
        if (audioSource == null)
        {
            return;
        }

        if (wasPlaying && !audioSource.isPlaying)
        {
            wasPlaying = false;
            SetMouthWeight(0f);
            Log("Audio finished -> send OnPlayFinished");
            SendEventToWeb("OnPlayFinished");
        }

        UpdateLipSync();

#if UNITY_EDITOR
        if (enableEditorHotkeys)
        {
            // Gesture quick test: 1/2/3/4 -> idle/explain/point/confirm
            if (Input.GetKeyDown(KeyCode.Alpha1)) ApplyGesture("idle");
            if (Input.GetKeyDown(KeyCode.Alpha2)) ApplyGesture("explain");
            if (Input.GetKeyDown(KeyCode.Alpha3)) ApplyGesture("point");
            if (Input.GetKeyDown(KeyCode.Alpha4)) ApplyGesture("confirm");
            // Emotion quick test: Q/W/E/R -> calm/supportive/serious/warning
            if (Input.GetKeyDown(KeyCode.Q)) ApplyEmotion("calm");
            if (Input.GetKeyDown(KeyCode.W)) ApplyEmotion("supportive");
            if (Input.GetKeyDown(KeyCode.E)) ApplyEmotion("serious");
            if (Input.GetKeyDown(KeyCode.R)) ApplyEmotion("warning");
            if (Input.GetKeyDown(KeyCode.S)) StopAudio();
        }
#endif
    }

    public void OnWebCommand(string json)
    {
        if (string.IsNullOrWhiteSpace(json))
        {
            Log("OnWebCommand received empty json.");
            return;
        }

        WebCommand cmd;
        try
        {
            cmd = JsonUtility.FromJson<WebCommand>(json);
        }
        catch (Exception e)
        {
            Debug.LogWarning($"[WebBridge] Invalid command json: {e.Message}");
            return;
        }

        if (cmd == null || string.IsNullOrWhiteSpace(cmd.command))
        {
            return;
        }

        Log(
            $"OnWebCommand cmd={cmd.command}, emotion={cmd.payload?.emotionTag}, gesture={cmd.payload?.gestureTag}, " +
            $"audioUrl={(string.IsNullOrWhiteSpace(cmd.payload?.audioUrl) ? "<empty>" : "<set>")}"
        );

        switch (cmd.command)
        {
            case "Avatar.SetEmotion":
                ApplyEmotion(cmd.payload?.emotionTag);
                break;
            case "Avatar.SetGesture":
                ApplyGesture(cmd.payload?.gestureTag);
                break;
            case "Avatar.Play":
                PlayAudio(cmd.payload?.audioUrl);
                break;
            case "Avatar.Stop":
                StopAudio();
                break;
            default:
                Log($"Unknown command: {cmd.command}");
                break;
        }
    }

    private void ApplyEmotion(string emotion)
    {
        if (animator == null)
        {
            return;
        }

        var value = emotion switch
        {
            "supportive" => 1,
            "serious" => 2,
            "warning" => 3,
            _ => 0
        };

        if (HasParameter(animator, "Emotion", AnimatorControllerParameterType.Int))
        {
            animator.SetInteger("Emotion", value);
            Log($"ApplyEmotion emotion={emotion ?? "<null>"} -> Emotion={value}");
        }
        else
        {
            Log("Animator missing int parameter: Emotion");
        }
    }

    private void ApplyGesture(string gesture)
    {
        if (animator == null)
        {
            return;
        }

        var value = gesture switch
        {
            "explain" => 1,
            "point" => 2,
            "confirm" => 3,
            _ => 0
        };

        if (HasParameter(animator, "Gesture", AnimatorControllerParameterType.Int))
        {
            animator.SetInteger("Gesture", value);
            Log($"ApplyGesture gesture={gesture ?? "<null>"} -> Gesture={value}");
        }
        else
        {
            Log("Animator missing int parameter: Gesture");
        }
    }

    private void PlayAudio(string url)
    {
        if (string.IsNullOrWhiteSpace(url) || audioSource == null)
        {
            Log($"PlayAudio skipped. UrlEmpty={string.IsNullOrWhiteSpace(url)}, AudioSourceNull={audioSource == null}");
            return;
        }

        if (playRoutine != null)
        {
            StopCoroutine(playRoutine);
        }
        playRoutine = StartCoroutine(PlayAudioRoutine(url));
        currentMouthWeight = 0f;
        Log("PlayAudio started coroutine.");
    }

    private IEnumerator PlayAudioRoutine(string url)
    {
        audioSource.Stop();
        audioSource.clip = null;
        wasPlaying = false;

        using var req = UnityWebRequestMultimedia.GetAudioClip(url, AudioType.UNKNOWN);
        yield return req.SendWebRequest();

        if (req.result != UnityWebRequest.Result.Success)
        {
            Debug.LogWarning($"[WebBridge] Audio load failed: {req.error} ({url})");
            yield break;
        }

        var clip = DownloadHandlerAudioClip.GetContent(req);
        if (clip == null)
        {
            Debug.LogWarning("[WebBridge] Audio clip is null.");
            yield break;
        }

        audioSource.clip = clip;
        audioSource.Play();
        wasPlaying = true;
        currentMouthWeight = 0f;
        Log("PlayAudioRoutine success. AudioSource is playing.");
    }

    private void StopAudio()
    {
        if (playRoutine != null)
        {
            StopCoroutine(playRoutine);
            playRoutine = null;
        }

        if (audioSource != null)
        {
            audioSource.Stop();
            audioSource.clip = null;
        }
        wasPlaying = false;
        SetMouthWeight(0f);
        Log("StopAudio invoked.");
    }

    private void UpdateLipSync()
    {
        if (!enableLipSync || audioSource == null || lipSyncFaceRenderer == null || mouthOpenBlendShapeIndex < 0)
        {
            return;
        }

        float targetWeight = 0f;
        if (audioSource.isPlaying)
        {
            targetWeight = EstimateMouthWeight();
        }

        var lerpT = 1f - Mathf.Exp(-lipSyncSmoothing * Time.deltaTime);
        currentMouthWeight = Mathf.Lerp(currentMouthWeight, targetWeight, lerpT);
        SetMouthWeight(currentMouthWeight);
    }

    private float EstimateMouthWeight()
    {
        audioSource.GetOutputData(audioSamples, 0);

        var sum = 0f;
        for (var i = 0; i < audioSamples.Length; i++)
        {
            var s = audioSamples[i];
            sum += s * s;
        }

        var rms = Mathf.Sqrt(sum / audioSamples.Length);
        var normalized = Mathf.InverseLerp(lipSyncSilenceThreshold, lipSyncMaxRms, rms);
        normalized = Mathf.Clamp01(normalized);
        normalized = Mathf.Pow(normalized, lipSyncGamma);
        return normalized * 100f;
    }

    private void SetMouthWeight(float weight)
    {
        if (lipSyncFaceRenderer == null || mouthOpenBlendShapeIndex < 0)
        {
            return;
        }
        var mesh = lipSyncFaceRenderer.sharedMesh;
        if (mesh == null || mouthOpenBlendShapeIndex >= mesh.blendShapeCount)
        {
            return;
        }
        lipSyncFaceRenderer.SetBlendShapeWeight(mouthOpenBlendShapeIndex, Mathf.Clamp(weight, 0f, 100f));
    }

    private void ResolveLipSyncTarget()
    {
        if (lipSyncFaceRenderer == null && animator != null)
        {
            lipSyncFaceRenderer = animator.GetComponentInChildren<SkinnedMeshRenderer>();
        }

        if (!autoFindMouthBlendShape || lipSyncFaceRenderer == null || mouthOpenBlendShapeIndex >= 0)
        {
            return;
        }

        var mesh = lipSyncFaceRenderer.sharedMesh;
        if (mesh == null)
        {
            return;
        }

        if (!string.IsNullOrWhiteSpace(mouthOpenBlendShapeName))
        {
            var byName = mesh.GetBlendShapeIndex(mouthOpenBlendShapeName);
            if (byName >= 0)
            {
                mouthOpenBlendShapeIndex = byName;
                Log($"LipSync blendShape resolved by name: {mouthOpenBlendShapeName} -> {byName}");
                return;
            }
        }

        for (var i = 0; i < mesh.blendShapeCount; i++)
        {
            var shapeName = mesh.GetBlendShapeName(i);
            var lower = shapeName.ToLowerInvariant();
            if (lower.Contains("mouth") || lower.Contains("jaw") || lower == "a" || lower == "aa")
            {
                mouthOpenBlendShapeIndex = i;
                Log($"LipSync blendShape auto-selected: {shapeName} -> {i}");
                return;
            }
        }
    }

    private static bool HasParameter(Animator target, string paramName, AnimatorControllerParameterType type)
    {
        if (target == null)
        {
            return false;
        }

        foreach (var p in target.parameters)
        {
            if (p.type == type && p.name == paramName)
            {
                return true;
            }
        }
        return false;
    }

    private void SendEventToWeb(string eventName)
    {
        var msg = new UnityEventMessage { @event = eventName };
        var json = JsonUtility.ToJson(msg);

#if UNITY_WEBGL && !UNITY_EDITOR
        UnityToWeb(json);
#else
        Debug.Log($"[WebBridge] {json}");
#endif
    }

    [ContextMenu("Debug/Emit OnAvatarReady")]
    private void DebugEmitReady() => SendEventToWeb("OnAvatarReady");

    [ContextMenu("Debug/Emit OnPlayFinished")]
    private void DebugEmitFinished() => SendEventToWeb("OnPlayFinished");

    [ContextMenu("Debug/Set Gesture Explain")]
    private void DebugGestureExplain() => ApplyGesture("explain");

    [ContextMenu("Debug/Set Emotion Serious")]
    private void DebugEmotionSerious() => ApplyEmotion("serious");

    [ContextMenu("Debug/LipSync Resolve Target")]
    private void DebugResolveLipSyncTarget() => ResolveLipSyncTarget();

    [ContextMenu("Debug/LipSync Mouth 100")]
    private void DebugSetMouthOpenMax() => SetMouthWeight(100f);

    [ContextMenu("Debug/LipSync Mouth 0")]
    private void DebugSetMouthOpenZero() => SetMouthWeight(0f);

    [ContextMenu("Debug/Validate Bridge Setup")]
    private void DebugValidateBridgeSetup()
    {
        Log($"Validate Animator={(animator != null)}, AudioSource={(audioSource != null)}");
        Log($"Validate AnimatorParam Emotion={HasParameter(animator, "Emotion", AnimatorControllerParameterType.Int)}");
        Log($"Validate AnimatorParam Gesture={HasParameter(animator, "Gesture", AnimatorControllerParameterType.Int)}");
        Log(
            "Validate LipSync " +
            $"enabled={enableLipSync}, renderer={(lipSyncFaceRenderer != null)}, " +
            $"index={mouthOpenBlendShapeIndex}, name={mouthOpenBlendShapeName}"
        );
    }

    private void Log(string message)
    {
        if (!verboseLogging)
        {
            return;
        }
        Debug.Log($"[WebBridge] {message}");
    }
}
