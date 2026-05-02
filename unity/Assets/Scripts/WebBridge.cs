using System;
using System.Collections;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;
using UnityEngine;
using UnityEngine.Networking;
using UniVRM10;

[DefaultExecutionOrder(12000)]
public class WebBridge : MonoBehaviour
{
    private const string BaseLayerPrefix = "Base Layer.";
    private const string BuildVersion = "face-controller-webgl-lipsync-gesture-loop-2026-05-02";

    [SerializeField] private Animator characterAnimator;
    [SerializeField] private AudioSource audioSource;
    [SerializeField] private bool verboseLogging = true;
    [SerializeField] private bool enableEditorHotkeys = true;
    [Header("Expression (BlendShape Drive)")]
    [SerializeField] private bool enableExpressionBlendShapes = true;
    [SerializeField] private bool enableVrm10Expressions = false;
    [SerializeField] private SkinnedMeshRenderer faceRenderer;
    [SerializeField] private string[] emotionBlendShapes = { "Smile", "BrowDown", "BrowUp", "EyeSquint" };
    [SerializeField] private bool useLateUpdateExpressionReapply = true;
    [SerializeField] private bool debugBlendShapeWriterLogging = false;
    [Header("Lip Sync (Simple Volume Drive)")]
    [SerializeField] private bool enableLipSync = true;
    [SerializeField] private SkinnedMeshRenderer lipSyncFaceRenderer;
    [SerializeField] private int mouthOpenBlendShapeIndex = -1;
    [SerializeField] private string mouthOpenBlendShapeName = "MouthOpen";
    [SerializeField, Range(0f, 0.2f)] private float lipSyncSilenceThreshold = 0.01f;
    [SerializeField, Range(0.02f, 0.6f)] private float lipSyncMaxRms = 0.12f;
    [SerializeField, Range(40f, 400f)] private float lipSyncAttackSpeed = 220f;
    [SerializeField, Range(20f, 240f)] private float lipSyncReleaseSpeed = 95f;
    [SerializeField, Range(0.5f, 2.5f)] private float lipSyncGamma = 1.2f;
    [SerializeField, Range(128, 4096)] private int lipSyncAnalysisSamples = 1024;
    [SerializeField, Range(0f, 12f)] private float lipSyncMinOpenWhileSpeaking = 2f;
    [SerializeField, Range(2f, 9f)] private float lipSyncTalkCycleHz = 5.4f;
    [SerializeField, Range(0f, 1f)] private float lipSyncTalkPulseBlend = 0.6f;
    [SerializeField, Range(0f, 10f)] private float lipSyncFallbackMinOpen = 0f;
    [SerializeField, Range(28f, 35f)] private float lipSyncFallbackMaxOpen = 32f;
    [SerializeField, Range(5.5f, 6.5f)] private float lipSyncFallbackOpenCloseHz = 6f;
    [SerializeField, Range(0.8f, 1.5f)] private float lipSyncFallbackPauseIntervalMin = 0.8f;
    [SerializeField, Range(0.8f, 1.5f)] private float lipSyncFallbackPauseIntervalMax = 1.5f;
    [SerializeField, Range(0.1f, 0.2f)] private float lipSyncFallbackPauseDurationMin = 0.1f;
    [SerializeField, Range(0.1f, 0.2f)] private float lipSyncFallbackPauseDurationMax = 0.2f;
    [SerializeField, Range(5f, 40f)] private float lipSyncFallbackSmoothSpeed = 20f;
    [Header("Gesture Loop")]
    [SerializeField, Range(2.5f, 4f)] private float gestureReplayIntervalMin = 2.5f;
    [SerializeField, Range(2.5f, 4f)] private float gestureReplayIntervalMax = 4f;
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
    private class SimpleWebMessage
    {
        public string gesture;
        public string emotion;
        public string text;
        public string audioUrl;
        public string audio_url;
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
    private Coroutine stateDebugRoutine;
    private Coroutine returnToIdleRoutine;
    private bool wasPlaying;
    private bool lipSyncActive;
    private bool hasStartedAudio;
    private bool isSpeaking;
    private bool expressionMotionActive;
    private float lipSyncStartTime;
    private float lipSyncEndTime;
    private float currentMouthWeight;
    private float targetMouthWeight;
    private string currentSpeechText = "";
    private bool lastEstimatedMouthWasFallback;
    private float nextFallbackMouthPauseTime = -1f;
    private float fallbackMouthPauseEndTime = -1f;
    private float lastGestureLoopReplayTime = -999f;
    private float nextGestureLoopReplayInterval = 3f;
    private readonly float[] audioSamples = new float[256];
    private float[] clipAnalysisBuffer;
    private string currentEmotion = "calm";
    private string currentGesture = "idle";
    private Vrm10Instance vrm10Instance;
    private string vrm10SearchSource = "unresolved";
    private readonly Dictionary<string, float> currentEmotionWeights = new Dictionary<string, float>(StringComparer.Ordinal);
    private Coroutine holdExpressionRoutine;
    private const float SupportiveExpressionWeight = 70f;
    private const float SeriousExpressionWeight = 70f;
    private const float WarningExpressionWeight = 70f;
    private const float EmphasisExpressionWeight = 60f;
    private float lastLipSyncFallbackLogTime = -999f;
    private FaceBlendShapeController faceBlendShapeController;

    private sealed class FaceBlendShapeController
    {
        private readonly Dictionary<string, float> emotionBaseWeights = new Dictionary<string, float>(StringComparer.Ordinal);
        private readonly Dictionary<string, float> emotionWeights = new Dictionary<string, float>(StringComparer.Ordinal);
        private readonly Dictionary<string, float> lipSyncWeights = new Dictionary<string, float>(StringComparer.Ordinal);
        private readonly Dictionary<string, int> emotionIndexCache = new Dictionary<string, int>(StringComparer.Ordinal);
        private readonly Dictionary<string, int> lipSyncIndexCache = new Dictionary<string, int>(StringComparer.Ordinal);
        private readonly Dictionary<string, float> lastLoggedWeights = new Dictionary<string, float>(StringComparer.Ordinal);
        private readonly Action<string, string, float> writerLogger;
        private readonly string writerName;
        private string emotionProfile = "calm";
        private readonly float expressionMotionSeed;
        private SkinnedMeshRenderer faceTarget;
        private SkinnedMeshRenderer lipTarget;

        public FaceBlendShapeController(string writerName, Action<string, string, float> writerLogger)
        {
            this.writerName = writerName;
            this.writerLogger = writerLogger;
            expressionMotionSeed = UnityEngine.Random.Range(0f, 100f);
        }

        public void BindTargets(SkinnedMeshRenderer faceRenderer, SkinnedMeshRenderer lipSyncRenderer)
        {
            faceTarget = faceRenderer;
            lipTarget = lipSyncRenderer != null ? lipSyncRenderer : faceRenderer;
            emotionIndexCache.Clear();
            lipSyncIndexCache.Clear();
        }

        public void ClearEmotionWeights()
        {
            emotionBaseWeights.Clear();
            emotionWeights.Clear();
        }

        public void SetEmotionProfile(string emotion)
        {
            emotionProfile = string.IsNullOrWhiteSpace(emotion) ? "calm" : emotion;
        }

        public void ClearLipSyncWeights()
        {
            lipSyncWeights.Clear();
        }

        public void SetEmotionWeight(string blendShapeName, float weight)
        {
            if (!string.IsNullOrWhiteSpace(blendShapeName))
            {
                var clamped = Mathf.Clamp(weight, 0f, 100f);
                emotionBaseWeights[blendShapeName] = clamped;
                emotionWeights[blendShapeName] = clamped;
            }
        }

        public void SetLipSyncWeight(string blendShapeName, float weight)
        {
            if (!string.IsNullOrWhiteSpace(blendShapeName))
            {
                lipSyncWeights[blendShapeName] = Mathf.Clamp(weight, 0f, 100f);
            }
        }

        public void ApplyLateUpdate()
        {
            Apply(faceTarget, emotionWeights, emotionIndexCache);
            Apply(lipTarget, lipSyncWeights, lipSyncIndexCache);
        }

        public void UpdateExpressionMicroMotion(float time)
        {
            if (emotionBaseWeights.Count == 0)
            {
                return;
            }

            var lowerEmotion = emotionProfile.ToLowerInvariant();
            if (lowerEmotion == "calm" || lowerEmotion == "neutral")
            {
                foreach (var kv in emotionBaseWeights)
                {
                    emotionWeights[kv.Key] = kv.Value;
                }
                return;
            }

            foreach (var kv in emotionBaseWeights)
            {
                if (kv.Value <= 0.001f)
                {
                    emotionWeights[kv.Key] = 0f;
                    continue;
                }

                var phase = StablePhase(kv.Key);
                var wave = 0.5f + 0.5f * Mathf.Sin((time + expressionMotionSeed) * 1.15f + phase);
                emotionWeights[kv.Key] = lowerEmotion switch
                {
                    "supportive" => Mathf.Lerp(55f, 70f, wave),
                    "serious" => Mathf.Lerp(45f, 60f, wave),
                    "warning" => Mathf.Lerp(45f, 65f, wave),
                    _ => kv.Value
                };
            }
        }

        private static float StablePhase(string value)
        {
            unchecked
            {
                var hash = 23;
                for (var i = 0; i < value.Length; i++)
                {
                    hash = (hash * 31) + value[i];
                }
                return Mathf.Abs(hash % 1000) / 1000f * Mathf.PI * 2f;
            }
        }

        private void Apply(SkinnedMeshRenderer renderer, Dictionary<string, float> weights, Dictionary<string, int> indexCache)
        {
            if (renderer == null || renderer.sharedMesh == null || weights.Count == 0)
            {
                return;
            }

            foreach (var kv in weights)
            {
                if (!indexCache.TryGetValue(kv.Key, out var index))
                {
                    index = renderer.sharedMesh.GetBlendShapeIndex(kv.Key);
                    indexCache[kv.Key] = index;
                }

                if (index < 0)
                {
                    continue;
                }

                var value = Mathf.Clamp(kv.Value, 0f, 100f);
                renderer.SetBlendShapeWeight(index, value);
                var logKey = $"{renderer.GetInstanceID()}:{kv.Key}";
                if (!lastLoggedWeights.TryGetValue(logKey, out var lastValue) || Mathf.Abs(lastValue - value) >= 1f)
                {
                    lastLoggedWeights[logKey] = value;
                    writerLogger?.Invoke(writerName, kv.Key, value);
                }
            }
        }
    }

    private void Awake()
    {
        Debug.Log($"[WebBridge] Awake gameObject.name={gameObject.name}");
        Debug.Log($"[WebBridge] Receive target ready. Method=ReceiveMessage");
        Debug.Log($"[WebBridge] Build version: {BuildVersion}");
        if (audioSource == null)
        {
            audioSource = GetComponent<AudioSource>();
        }
        ResolveFaceRendererReference();
        ResolveVrm10Instance();
        ResolveLipSyncTarget();
        EnsureFaceBlendShapeController();
        Log($"Awake done. AnimatorBound={characterAnimator != null}, AudioSourceBound={audioSource != null}");
    }

    private void OnValidate()
    {
        ResolveFaceRendererReference();
        ResolveVrm10Instance();
        ResolveLipSyncTarget();
        EnsureFaceBlendShapeController();
    }

    private void LateUpdate()
    {
        if (faceBlendShapeController == null || !useLateUpdateExpressionReapply)
        {
            return;
        }

        if (expressionMotionActive && (lipSyncActive || isSpeaking || (audioSource != null && audioSource.isPlaying)))
        {
            faceBlendShapeController.UpdateExpressionMicroMotion(Time.time);
        }
        faceBlendShapeController.ApplyLateUpdate();
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

        if (wasPlaying && !audioSource.isPlaying && (!hasStartedAudio || Time.time > lipSyncStartTime + 0.5f))
        {
            wasPlaying = false;
            StopLipSync("OnPlayFinished");
            Log("Audio finished -> send OnPlayFinished");
            SendEventToWeb("OnPlayFinished");
        }

        UpdateLipSync();
        UpdateGestureLoop();

#if UNITY_EDITOR
        if (enableEditorHotkeys)
        {
            // Gesture quick test: 1..8 -> idle/explain/point/confirm/greeting/thinking/dismiss/laugh
            if (Input.GetKeyDown(KeyCode.Alpha1)) ApplyGesture("idle");
            if (Input.GetKeyDown(KeyCode.Alpha2)) ApplyGesture("explain");
            if (Input.GetKeyDown(KeyCode.Alpha3)) ApplyGesture("point");
            if (Input.GetKeyDown(KeyCode.Alpha4)) ApplyGesture("confirm");
            if (Input.GetKeyDown(KeyCode.Alpha5)) ApplyGesture("greeting");
            if (Input.GetKeyDown(KeyCode.Alpha6)) ApplyGesture("thinking");
            if (Input.GetKeyDown(KeyCode.Alpha7)) ApplyGesture("dismissing");
            if (Input.GetKeyDown(KeyCode.Alpha8)) ApplyGesture("laughing");
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
                PlayAudio(cmd.payload?.audioUrl, cmd.payload?.subtitleText);
                break;
            case "Avatar.Stop":
                StopAudio();
                break;
            default:
                Log($"Unknown command: {cmd.command}");
                break;
        }
    }

    public void ReceiveMessage(string json)
    {
        Debug.Log($"[WebBridge] ReceiveMessage HIT: {json}");
        Debug.Log($"[WebBridge] ReceiveMessage from WebGL: {json}");
        if (string.IsNullOrWhiteSpace(json))
        {
            Log("ReceiveMessage received empty json.");
            return;
        }

        // Minimal receive path first. If this works in WebGL, we can trust SendMessage/object binding.
        if (json.Contains("explain"))
        {
            ApplyGesture("explain");
        }
        if (json.Contains("supportive"))
        {
            ApplyEmotion("supportive");
        }
        if (json.Contains("point"))
        {
            ApplyGesture("point");
        }
        if (json.Contains("warning"))
        {
            ApplyEmotion("warning");
        }
        if (json.Contains("idle"))
        {
            ApplyGesture("idle");
        }
        if (json.Contains("calm"))
        {
            ApplyEmotion("calm");
        }

        SimpleWebMessage message;
        try
        {
            message = JsonUtility.FromJson<SimpleWebMessage>(json);
        }
        catch (Exception e)
        {
            Debug.LogWarning($"[WebBridge] ReceiveMessage invalid json: {e.Message}");
            return;
        }

        if (message == null)
        {
            Debug.LogWarning("[WebBridge] ReceiveMessage payload is null.");
            return;
        }

        var resolvedAudioUrl = ResolveAudioUrl(message, json);
        Log(
            $"ReceiveMessage parsed gesture={message.gesture}, emotion={message.emotion}, " +
            $"audioUrl={(string.IsNullOrWhiteSpace(resolvedAudioUrl) ? "<empty>" : resolvedAudioUrl)}"
        );

        currentSpeechText = message.text ?? "";
        if (!string.IsNullOrWhiteSpace(message.text))
        {
            Log($"ReceiveMessage text={message.text}");
        }

        if (!string.IsNullOrWhiteSpace(message.gesture))
        {
            ApplyGesture(NormalizeGestureInput(message.gesture));
        }

        if (!string.IsNullOrWhiteSpace(message.emotion))
        {
            ApplyEmotion(message.emotion);
        }

        if (!string.IsNullOrWhiteSpace(resolvedAudioUrl))
        {
            PlayAudio(resolvedAudioUrl, message.text);
        }
        else if (string.IsNullOrWhiteSpace(message.text))
        {
            StopLipSync("empty audio");
        }
    }

    public void TestMessage(string json)
    {
        Debug.Log($"[WebBridge] TestMessage HIT: {json}");
    }

    private void ApplyEmotion(string emotion)
    {
        currentEmotion = string.IsNullOrWhiteSpace(emotion) ? "calm" : emotion;
        faceBlendShapeController?.SetEmotionProfile(currentEmotion);
        LogFaceRendererBinding("ApplyEmotion");

        if (characterAnimator != null)
        {
            var value = currentEmotion switch
            {
                "supportive" => 1,
                "serious" => 2,
                "warning" => 3,
                _ => 0
            };

            if (HasParameter(characterAnimator, "Emotion", AnimatorControllerParameterType.Int))
            {
                characterAnimator.SetInteger("Emotion", value);
                Log($"ApplyEmotion emotion={currentEmotion} -> Emotion={value}");
            }
            else
            {
                Log("Animator missing int parameter: Emotion");
            }
        }

        if (enableExpressionBlendShapes)
        {
            ResetVrm10ExpressionsIfAvailable();
            ApplyEmotionBlendShapes(currentEmotion);
            if (enableVrm10Expressions)
            {
                TryApplyVrm10Expression(currentEmotion);
            }
        }
        else if (enableVrm10Expressions)
        {
            TryApplyVrm10Expression(currentEmotion);
        }
    }

    private void ApplyGesture(string gesture)
    {
        currentGesture = NormalizeGestureInput(gesture);

        if (characterAnimator == null)
        {
            Debug.LogError("[WebBridge] Character Animator is not assigned.");
            return;
        }

        var parameterValue = currentGesture switch
        {
            "explain" => 1,
            "shrug" => 1,
            "point" => 2,
            "confirm" => 3,
            "thinking" => 4,
            "laughing" => 5,
            "dismissing" => 6,
            "greeting" => 7,
            "warning" => 8,
            _ => 0
        };

        if (HasParameter(characterAnimator, "Gesture", AnimatorControllerParameterType.Int))
        {
            characterAnimator.SetInteger("Gesture", parameterValue);
            Log($"ApplyGesture gesture={currentGesture} -> Gesture={parameterValue}");
        }
        else
        {
            Log("Animator missing int parameter: Gesture");
        }

        var stateName = ResolveGestureStateName(currentGesture);
        TryPlayGestureState(stateName, 0.1f);
        if (audioSource != null && audioSource.isPlaying)
        {
            ResetGestureLoopSchedule();
        }
    }

    private void PlayAudio(string url, string speechText = null)
    {
        if (string.IsNullOrWhiteSpace(url) || audioSource == null)
        {
            Log($"PlayAudio skipped. UrlEmpty={string.IsNullOrWhiteSpace(url)}, AudioSourceNull={audioSource == null}");
            if (string.IsNullOrWhiteSpace(url))
            {
                StopLipSync("empty audio");
            }
            return;
        }

        currentSpeechText = speechText ?? "";
        Log($"PlayAudio url={url}");

        if (playRoutine != null)
        {
            StopCoroutine(playRoutine);
        }
        playRoutine = StartCoroutine(PlayAudioRoutine(url, currentSpeechText));
        currentMouthWeight = 0f;
        targetMouthWeight = 0f;
        ResetFallbackMouthPauseSchedule();
        ResetGestureLoopSchedule();
        if (string.IsNullOrWhiteSpace(currentGesture) || currentGesture == "idle")
        {
            ApplyGesture(GetDefaultSpeakingGesture(currentEmotion));
        }
        Log("PlayAudio started coroutine.");
    }

    private string ResolveAudioUrl(SimpleWebMessage message, string rawJson)
    {
        if (!string.IsNullOrWhiteSpace(message.audioUrl))
        {
            return message.audioUrl;
        }

        if (!string.IsNullOrWhiteSpace(message.audio_url))
        {
            return message.audio_url;
        }

        return ExtractJsonStringValue(rawJson, "audioUrl") ?? ExtractJsonStringValue(rawJson, "audio_url") ?? "";
    }

    private string ExtractJsonStringValue(string rawJson, string fieldName)
    {
        if (string.IsNullOrWhiteSpace(rawJson) || string.IsNullOrWhiteSpace(fieldName))
        {
            return null;
        }

        var token = $"\"{fieldName}\"";
        var fieldIndex = rawJson.IndexOf(token, StringComparison.Ordinal);
        if (fieldIndex < 0)
        {
            return null;
        }

        var colonIndex = rawJson.IndexOf(':', fieldIndex + token.Length);
        if (colonIndex < 0)
        {
            return null;
        }

        var quoteStart = rawJson.IndexOf('"', colonIndex + 1);
        if (quoteStart < 0)
        {
            return null;
        }

        var builder = new StringBuilder();
        var escaped = false;
        for (var i = quoteStart + 1; i < rawJson.Length; i++)
        {
            var ch = rawJson[i];
            if (escaped)
            {
                builder.Append(ch switch
                {
                    '\\' => '\\',
                    '"' => '"',
                    '/' => '/',
                    'b' => '\b',
                    'f' => '\f',
                    'n' => '\n',
                    'r' => '\r',
                    't' => '\t',
                    _ => ch,
                });
                escaped = false;
                continue;
            }

            if (ch == '\\')
            {
                escaped = true;
                continue;
            }

            if (ch == '"')
            {
                return builder.ToString();
            }

            builder.Append(ch);
        }

        return null;
    }

    private IEnumerator PlayAudioRoutine(string url, string speechText)
    {
        Log($"PlayAudioRoutine start download. url={url}");
        audioSource.Stop();
        audioSource.clip = null;
        wasPlaying = false;
        StopLipSync("new audio");
        ResetFallbackMouthPauseSchedule();

        if (TryCreateAudioClipFromDataUrl(url, out var embeddedClip))
        {
            audioSource.clip = embeddedClip;
            audioSource.Play();
            wasPlaying = true;
            StartLipSync(speechText);
            ResetFallbackMouthPauseSchedule();
            ResetGestureLoopSchedule();
            Log($"PlayAudioRoutine data-url audioClip null={embeddedClip == null} length={(embeddedClip != null ? embeddedClip.length : 0f):0.000} audioSource null={audioSource == null}");
            Log($"PlayAudioRoutine after Play isPlaying={audioSource.isPlaying}");
            Log("PlayAudioRoutine success. AudioSource is playing.");
            yield break;
        }

        using var req = UnityWebRequestMultimedia.GetAudioClip(url, AudioType.UNKNOWN);
        yield return req.SendWebRequest();
        Log($"PlayAudioRoutine UnityWebRequest result={req.result} responseCode={req.responseCode}");

        if (req.result != UnityWebRequest.Result.Success)
        {
            Debug.LogWarning($"[WebBridge] PlayAudioRoutine failed: request error={req.error}, url={url}, result={req.result}, responseCode={req.responseCode}");
            yield break;
        }

        var clip = DownloadHandlerAudioClip.GetContent(req);
        Log($"PlayAudioRoutine audioClip null={clip == null}");
        if (clip == null)
        {
            Debug.LogWarning("[WebBridge] PlayAudioRoutine failed: audioClip is null.");
            yield break;
        }

        Log($"PlayAudioRoutine audioClip.length={clip.length:0.000}");
        Log($"PlayAudioRoutine audioSource null={audioSource == null}");
        audioSource.clip = clip;
        audioSource.Play();
        wasPlaying = true;
        StartLipSync(speechText);
        ResetFallbackMouthPauseSchedule();
        ResetGestureLoopSchedule();
        Log($"PlayAudioRoutine after Play isPlaying={audioSource.isPlaying}");
        if (!audioSource.isPlaying)
        {
            Debug.LogWarning("[WebBridge] PlayAudioRoutine warning: AudioSource.Play called, isPlaying is false on this frame (will re-check next frame).");
            yield return null;
            Log($"PlayAudioRoutine next frame isPlaying={audioSource.isPlaying}");
            if (!audioSource.isPlaying)
            {
                Debug.LogWarning("[WebBridge] PlayAudioRoutine failed: AudioSource did not enter playing state.");
                StopLipSync("audioSource did not start");
                yield break;
            }
        }
        Log("PlayAudioRoutine success. AudioSource is playing.");
    }

    private bool TryCreateAudioClipFromDataUrl(string url, out AudioClip clip)
    {
        clip = null;
        if (string.IsNullOrWhiteSpace(url) || !url.StartsWith("data:audio/", StringComparison.OrdinalIgnoreCase))
        {
            return false;
        }

        try
        {
            var commaIndex = url.IndexOf(',');
            if (commaIndex < 0 || commaIndex >= url.Length - 1)
            {
                Debug.LogWarning("[WebBridge] Invalid data audio URL.");
                return false;
            }

            var header = url.Substring(0, commaIndex);
            var payload = url.Substring(commaIndex + 1);
            if (!header.Contains(";base64", StringComparison.OrdinalIgnoreCase))
            {
                Debug.LogWarning("[WebBridge] Unsupported audio data URL encoding.");
                return false;
            }

            var audioBytes = Convert.FromBase64String(payload);
            if (!TryDecodeWavPcm16(audioBytes, out var samples, out var channels, out var sampleRate))
            {
                Debug.LogWarning("[WebBridge] Unsupported WAV data URL payload.");
                return false;
            }

            clip = AudioClip.Create(
                $"embedded_tts_{Guid.NewGuid():N}",
                samples.Length / channels,
                channels,
                sampleRate,
                false
            );
            clip.SetData(samples, 0);
            Log($"Decoded embedded audio clip. sampleRate={sampleRate}, channels={channels}, samples={samples.Length}");
            return true;
        }
        catch (Exception e)
        {
            Debug.LogWarning($"[WebBridge] Failed to decode embedded audio URL: {e.Message}");
            clip = null;
            return false;
        }
    }

    private static bool TryDecodeWavPcm16(byte[] wavBytes, out float[] samples, out int channels, out int sampleRate)
    {
        samples = Array.Empty<float>();
        channels = 1;
        sampleRate = 16000;

        if (wavBytes == null || wavBytes.Length < 44)
        {
            return false;
        }

        if (Encoding.ASCII.GetString(wavBytes, 0, 4) != "RIFF" || Encoding.ASCII.GetString(wavBytes, 8, 4) != "WAVE")
        {
            return false;
        }

        var offset = 12;
        var fmtFound = false;
        var dataFound = false;
        short audioFormat = 0;
        short bitsPerSample = 0;
        int dataOffset = 0;
        int dataSize = 0;

        while (offset + 8 <= wavBytes.Length)
        {
            var chunkId = Encoding.ASCII.GetString(wavBytes, offset, 4);
            var chunkSize = BitConverter.ToInt32(wavBytes, offset + 4);
            offset += 8;
            if (offset + chunkSize > wavBytes.Length)
            {
                return false;
            }

            if (chunkId == "fmt ")
            {
                audioFormat = BitConverter.ToInt16(wavBytes, offset);
                channels = BitConverter.ToInt16(wavBytes, offset + 2);
                sampleRate = BitConverter.ToInt32(wavBytes, offset + 4);
                bitsPerSample = BitConverter.ToInt16(wavBytes, offset + 14);
                fmtFound = true;
            }
            else if (chunkId == "data")
            {
                dataOffset = offset;
                dataSize = chunkSize;
                dataFound = true;
            }

            offset += chunkSize;
            if ((chunkSize & 1) == 1)
            {
                offset += 1;
            }
        }

        if (!fmtFound || !dataFound || audioFormat != 1 || bitsPerSample != 16 || channels <= 0 || sampleRate <= 0)
        {
            return false;
        }

        var sampleCount = dataSize / 2;
        samples = new float[sampleCount];
        for (var i = 0; i < sampleCount; i++)
        {
            var pcm = BitConverter.ToInt16(wavBytes, dataOffset + i * 2);
            samples[i] = pcm / 32768f;
        }
        return true;
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
        StopLipSync("StopAudio");
        if (returnToIdleRoutine != null)
        {
            StopCoroutine(returnToIdleRoutine);
        }
        returnToIdleRoutine = StartCoroutine(ReturnToIdleAfterDelay(1.2f));
        Log("StopAudio invoked.");
    }

    private void StartLipSync(string speechText)
    {
        currentSpeechText = speechText ?? "";
        var textLength = CountSpeechCharacters(currentSpeechText);
        var estimatedDuration = Mathf.Clamp(textLength / 4.5f, 1.5f, 25f);
        lipSyncStartTime = Time.time;
        lipSyncEndTime = Time.time + estimatedDuration + 0.3f;
        lipSyncActive = true;
        hasStartedAudio = true;
        isSpeaking = true;
        currentMouthWeight = 0f;
        targetMouthWeight = 0f;
        ResetFallbackMouthPauseSchedule();
        SetMouthWeight(0f);
        faceBlendShapeController?.ApplyLateUpdate();
        StartExpressionMotion();
        Debug.Log($"[LipSync] Start active=true estimatedDuration={estimatedDuration:0.###} endTime={lipSyncEndTime:0.###}");
    }

    private void StopLipSync(string reason)
    {
        lipSyncActive = false;
        hasStartedAudio = false;
        isSpeaking = false;
        targetMouthWeight = 0f;
        currentMouthWeight = 0f;
        lastEstimatedMouthWasFallback = false;
        ResetFallbackMouthPauseSchedule();
        SetMouthWeight(0f);
        faceBlendShapeController?.ApplyLateUpdate();
        StopExpressionMotion(reason);
        Debug.Log($"[LipSync] Stop reason={reason}");
        Debug.Log("[LipSync] mouth reset to 0");
    }

    private void StartExpressionMotion()
    {
        expressionMotionActive = true;
        faceBlendShapeController?.SetEmotionProfile(currentEmotion);
        if (enableExpressionBlendShapes)
        {
            ApplyEmotionBlendShapes(currentEmotion);
        }
        Debug.Log($"[ExpressionMotion] Start emotion={currentEmotion}");
    }

    private void StopExpressionMotion(string reason)
    {
        if (!expressionMotionActive && currentEmotionWeights.Count == 0)
        {
            return;
        }

        expressionMotionActive = false;
        ResetExpressionBlendShapesToCalm();
        Debug.Log($"[ExpressionMotion] Stop reason={reason}");
    }

    private void ResetExpressionBlendShapesToCalm()
    {
        ResolveFaceRendererReference();
        var names = new HashSet<string>(StringComparer.Ordinal)
        {
            "Fcl_ALL_Fun",
            "Fcl_ALL_Surprised",
            "Fcl_ALL_Joy",
            "Fcl_ALL_Angry"
        };

        if (emotionBlendShapes != null)
        {
            foreach (var blendShapeName in emotionBlendShapes)
            {
                if (!string.IsNullOrWhiteSpace(blendShapeName))
                {
                    names.Add(blendShapeName);
                }
            }
        }

        foreach (var blendShapeName in currentEmotionWeights.Keys)
        {
            if (!string.IsNullOrWhiteSpace(blendShapeName))
            {
                names.Add(blendShapeName);
            }
        }

        foreach (var blendShapeName in names)
        {
            faceBlendShapeController?.SetEmotionWeight(blendShapeName, 0f);
        }

        faceBlendShapeController?.ApplyLateUpdate();
        faceBlendShapeController?.ClearEmotionWeights();
        currentEmotionWeights.Clear();
    }

    private static int CountSpeechCharacters(string speechText)
    {
        if (string.IsNullOrWhiteSpace(speechText))
        {
            return 0;
        }

        var count = 0;
        for (var i = 0; i < speechText.Length; i++)
        {
            if (!char.IsWhiteSpace(speechText[i]))
            {
                count++;
            }
        }
        return count;
    }

    private void UpdateLipSync()
    {
        if (!enableLipSync || lipSyncFaceRenderer == null || mouthOpenBlendShapeIndex < 0)
        {
            return;
        }

        lastEstimatedMouthWasFallback = false;
        if (!lipSyncActive)
        {
            targetMouthWeight = 0f;
            currentMouthWeight = Mathf.Lerp(currentMouthWeight, targetMouthWeight, Time.deltaTime * lipSyncFallbackSmoothSpeed);
            if (currentMouthWeight < 0.1f)
            {
                currentMouthWeight = 0f;
            }
            SetMouthWeight(currentMouthWeight);
            return;
        }

        if (Time.time >= lipSyncEndTime)
        {
            StopLipSync("estimated duration reached");
            return;
        }

        if (audioSource != null && hasStartedAudio && !audioSource.isPlaying && Time.time > lipSyncStartTime + 0.5f)
        {
            StopLipSync("audioSource stopped");
            return;
        }

        targetMouthWeight = EstimateMouthWeight();

        if (lastEstimatedMouthWasFallback)
        {
            currentMouthWeight = Mathf.Lerp(currentMouthWeight, targetMouthWeight, Time.deltaTime * lipSyncFallbackSmoothSpeed);
        }
        else
        {
            var step = (targetMouthWeight >= currentMouthWeight ? lipSyncAttackSpeed : lipSyncReleaseSpeed) * Time.deltaTime;
            currentMouthWeight = Mathf.MoveTowards(currentMouthWeight, targetMouthWeight, step);
        }

        SetMouthWeight(currentMouthWeight);

        if (lastEstimatedMouthWasFallback && Time.time - lastLipSyncFallbackLogTime >= 0.25f)
        {
            lastLipSyncFallbackLogTime = Time.time;
            Debug.Log($"[LipSync] WebGL fallback mouthOpen={currentMouthWeight:0.###}");
        }
    }

    private float EstimateMouthWeight()
    {
#if UNITY_WEBGL && !UNITY_EDITOR
        return EstimateFallbackMouthWeight();
#else
        if (audioSource.clip == null)
        {
            audioSource.GetOutputData(audioSamples, 0);
            var outputWeight = NormalizeRms(audioSamples, audioSamples.Length);
            return outputWeight > 0.001f ? outputWeight : EstimateFallbackMouthWeight();
        }

        var clip = audioSource.clip;
        var channels = Mathf.Max(1, clip.channels);
        var windowSamples = Mathf.Clamp(lipSyncAnalysisSamples, 128, 4096);
        var requiredLength = windowSamples * channels;

        if (clipAnalysisBuffer == null || clipAnalysisBuffer.Length != requiredLength)
        {
            clipAnalysisBuffer = new float[requiredLength];
        }

        var clipSamples = Mathf.Max(1, clip.samples);
        var centerSample = Mathf.Clamp(audioSource.timeSamples, 0, clipSamples - 1);
        var startSample = Mathf.Clamp(centerSample - (windowSamples / 4), 0, Mathf.Max(0, clipSamples - windowSamples));

        try
        {
            clip.GetData(clipAnalysisBuffer, startSample);
            var clipWeight = NormalizeRms(clipAnalysisBuffer, requiredLength);
            return clipWeight > 0.001f ? clipWeight : EstimateFallbackMouthWeight();
        }
        catch (Exception e)
        {
            Log($"AudioClip.GetData unavailable, using fallback lip sync: {e.Message}");
            audioSource.GetOutputData(audioSamples, 0);
            var outputWeight = NormalizeRms(audioSamples, audioSamples.Length);
            return outputWeight > 0.001f ? outputWeight : EstimateFallbackMouthWeight();
        }
#endif
    }

    private float EstimateFallbackMouthWeight()
    {
        var talkTime = audioSource != null && audioSource.time > 0f ? audioSource.time : Time.time;
        lastEstimatedMouthWasFallback = true;

        if (nextFallbackMouthPauseTime < 0f)
        {
            ScheduleNextFallbackMouthPause();
        }

        if (Time.time >= nextFallbackMouthPauseTime)
        {
            fallbackMouthPauseEndTime = Time.time + UnityEngine.Random.Range(lipSyncFallbackPauseDurationMin, lipSyncFallbackPauseDurationMax);
            ScheduleNextFallbackMouthPause(fallbackMouthPauseEndTime);
        }

        if (Time.time < fallbackMouthPauseEndTime)
        {
            return 0f;
        }

        var phase = Mathf.Repeat(talkTime * lipSyncFallbackOpenCloseHz, 1f);
        var triangle = phase < 0.5f ? phase * 2f : (1f - phase) * 2f;
        var closedThreshold = 0.12f;
        var openAmount = triangle <= closedThreshold ? 0f : Mathf.InverseLerp(closedThreshold, 1f, triangle);
        openAmount = Mathf.Pow(openAmount, 1.15f);
        var mouthOpen = Mathf.Lerp(lipSyncFallbackMinOpen, lipSyncFallbackMaxOpen, openAmount);
        return mouthOpen;
    }

    private void ScheduleNextFallbackMouthPause(float fromTime = -1f)
    {
        var start = fromTime >= 0f ? fromTime : Time.time;
        var minInterval = Mathf.Min(lipSyncFallbackPauseIntervalMin, lipSyncFallbackPauseIntervalMax);
        var maxInterval = Mathf.Max(lipSyncFallbackPauseIntervalMin, lipSyncFallbackPauseIntervalMax);
        nextFallbackMouthPauseTime = start + UnityEngine.Random.Range(minInterval, maxInterval);
    }

    private void ResetFallbackMouthPauseSchedule()
    {
        nextFallbackMouthPauseTime = -1f;
        fallbackMouthPauseEndTime = -1f;
    }

    private float NormalizeRms(float[] samples, int length)
    {
        if (samples == null || length <= 0)
        {
            return 0f;
        }

        var sum = 0f;
        for (var i = 0; i < length; i++)
        {
            var s = samples[i];
            sum += s * s;
        }

        var rms = Mathf.Sqrt(sum / length);
        var normalized = Mathf.InverseLerp(lipSyncSilenceThreshold, lipSyncMaxRms, rms);
        normalized = Mathf.Clamp01(normalized);
        normalized = Mathf.Pow(normalized, lipSyncGamma);
        if (normalized > 0.001f && lipSyncMinOpenWhileSpeaking > 0f)
        {
            normalized = Mathf.Max(normalized, lipSyncMinOpenWhileSpeaking / 100f);
        }

        if (normalized > 0.001f)
        {
            var talkTime = audioSource != null ? audioSource.time : Time.time;
            var pulse = 0.5f + 0.5f * Mathf.Sin(talkTime * lipSyncTalkCycleHz * Mathf.PI * 2f);
            var pulsed = Mathf.Lerp(1f, pulse, lipSyncTalkPulseBlend);
            normalized *= pulsed;
        }

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
        var clamped = Mathf.Clamp(weight, 0f, 100f);
        var shapeName = mesh.GetBlendShapeName(mouthOpenBlendShapeIndex);
        faceBlendShapeController?.SetLipSyncWeight(shapeName, clamped);
    }

    private void ResolveLipSyncTarget()
    {
        if (lipSyncFaceRenderer == null && faceRenderer != null)
        {
            lipSyncFaceRenderer = faceRenderer;
        }

        if (lipSyncFaceRenderer == null && characterAnimator != null)
        {
            lipSyncFaceRenderer = characterAnimator.GetComponentInChildren<SkinnedMeshRenderer>();
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

        LogAvailableMouthBlendShapes(mesh);
        var preferredIndex = FindPreferredMouthBlendShape(mesh);
        if (preferredIndex >= 0)
        {
            mouthOpenBlendShapeIndex = preferredIndex;
            mouthOpenBlendShapeName = mesh.GetBlendShapeName(preferredIndex);
            Log($"LipSync blendShape auto-selected preferred: {mouthOpenBlendShapeName} -> {preferredIndex}");
            return;
        }

        for (var i = 0; i < mesh.blendShapeCount; i++)
        {
            var shapeName = mesh.GetBlendShapeName(i);
            var lower = shapeName.ToLowerInvariant();
            if (IsLikelyMouthBlendShape(lower))
            {
                mouthOpenBlendShapeIndex = i;
                mouthOpenBlendShapeName = shapeName;
                Log($"LipSync blendShape auto-selected: {shapeName} -> {i}");
                return;
            }
        }
    }

    private static int FindPreferredMouthBlendShape(Mesh mesh)
    {
        string[] preferredNames =
        {
            "JawOpen",
            "Fcl_MTH_A",
            "Fcl_MTH_O",
            "Fcl_MTH_I",
            "Fcl_MTH_U",
            "Fcl_MTH_E",
            "MouthOpen",
            "A",
            "Aa"
        };

        foreach (var preferredName in preferredNames)
        {
            var index = mesh.GetBlendShapeIndex(preferredName);
            if (index >= 0)
            {
                return index;
            }
        }

        return -1;
    }

    private static bool IsLikelyMouthBlendShape(string lowerName)
    {
        return lowerName.Contains("mouth")
            || lowerName.Contains("jaw")
            || lowerName.Contains("mth")
            || lowerName == "a"
            || lowerName == "aa"
            || lowerName.EndsWith("_a", StringComparison.Ordinal)
            || lowerName.EndsWith("_o", StringComparison.Ordinal);
    }

    private void LogAvailableMouthBlendShapes(Mesh mesh)
    {
        if (mesh == null)
        {
            return;
        }

        Log($"LipSync scanning BlendShapeCount={mesh.blendShapeCount}");
        for (var i = 0; i < mesh.blendShapeCount; i++)
        {
            var shapeName = mesh.GetBlendShapeName(i);
            if (IsLikelyMouthBlendShape(shapeName.ToLowerInvariant()))
            {
                Log($"LipSync candidate BlendShape[{i}]={shapeName}");
            }
        }
    }

    private void ResolveFaceRendererReference()
    {
        if (faceRenderer == null && lipSyncFaceRenderer != null)
        {
            faceRenderer = lipSyncFaceRenderer;
        }

        if (lipSyncFaceRenderer == null && faceRenderer != null)
        {
            lipSyncFaceRenderer = faceRenderer;
        }

        if (faceBlendShapeController != null)
        {
            faceBlendShapeController.BindTargets(faceRenderer, lipSyncFaceRenderer);
        }
    }

    private void ApplyEmotionBlendShapes(string emotion)
    {
        if (!enableExpressionBlendShapes)
        {
            return;
        }

        ResolveFaceRendererReference();

        if (faceRenderer == null)
        {
            Debug.LogWarning("[WebBridge] Face Renderer is not assigned.");
            return;
        }

        var mesh = faceRenderer.sharedMesh;
        if (mesh == null)
        {
            Debug.LogWarning("[WebBridge] Face Renderer sharedMesh is null.");
            return;
        }

        if (emotionBlendShapes == null || emotionBlendShapes.Length == 0)
        {
            Debug.LogWarning("[WebBridge] Emotion Blend Shapes is empty.");
            return;
        }

        currentEmotionWeights.Clear();
        faceBlendShapeController?.ClearEmotionWeights();
        ResetConfiguredEmotionBlendShapes(mesh);

        if (emotion == "calm" || emotion == "neutral")
        {
            Log("ApplyEmotionBlendShapes calm -> cleared configured blend shapes.");
            return;
        }

        switch (emotion)
        {
            case "supportive":
                ApplyEmotionBlendShapeBySlot(mesh, 0, SupportiveExpressionWeight);
                break;
            case "serious":
                ApplyEmotionBlendShapeBySlot(mesh, 1, SeriousExpressionWeight);
                break;
            case "warning":
                ApplyEmotionBlendShapeBySlot(mesh, 2, WarningExpressionWeight);
                if (emotionBlendShapes.Length > 3)
                {
                    ApplyEmotionBlendShapeBySlot(mesh, 3, EmphasisExpressionWeight);
                }
                break;
            default:
                Log($"ApplyEmotionBlendShapes no explicit mapping for emotion={emotion}, leaving cleared state.");
                break;
        }
    }

    private void ResetConfiguredEmotionBlendShapes(Mesh mesh)
    {
        foreach (var blendShapeName in emotionBlendShapes)
        {
            if (string.IsNullOrWhiteSpace(blendShapeName))
            {
                continue;
            }

            var index = mesh.GetBlendShapeIndex(blendShapeName);
            if (index < 0)
            {
                Debug.LogError($"[WebBridge] Missing BlendShape: {blendShapeName}");
                continue;
            }

            currentEmotionWeights[blendShapeName] = 0f;
            faceBlendShapeController?.SetEmotionWeight(blendShapeName, 0f);
        }
    }

    private void ApplyEmotionBlendShapeBySlot(Mesh mesh, int slotIndex, float weight)
    {
        if (emotionBlendShapes == null || slotIndex < 0 || slotIndex >= emotionBlendShapes.Length)
        {
            Debug.LogWarning($"[WebBridge] Emotion Blend Shapes slot index out of range: {slotIndex}");
            return;
        }

        var blendShapeName = emotionBlendShapes[slotIndex];
        if (string.IsNullOrWhiteSpace(blendShapeName))
        {
            Debug.LogWarning($"[WebBridge] Emotion Blend Shapes slot {slotIndex} is empty.");
            return;
        }

        var index = mesh.GetBlendShapeIndex(blendShapeName);
        if (index < 0)
        {
            Debug.LogError($"[WebBridge] Missing BlendShape: {blendShapeName}");
            return;
        }

        var clamped = Mathf.Clamp(weight, 0f, 100f);
        currentEmotionWeights[blendShapeName] = clamped;
        faceBlendShapeController?.SetEmotionWeight(blendShapeName, clamped);
        faceBlendShapeController?.ApplyLateUpdate();
        var actual = faceRenderer.GetBlendShapeWeight(index);
        Log($"SetBlendShapeWeight name={blendShapeName} index={index} weight={weight} actual={actual}");
        StartBlendShapeOverwriteMonitor(blendShapeName, index, clamped);
    }

    private void ReapplyCurrentEmotionWeights()
    {
        ResolveFaceRendererReference();
        if (faceRenderer == null || faceRenderer.sharedMesh == null || currentEmotionWeights.Count == 0)
        {
            return;
        }

        foreach (var kv in currentEmotionWeights)
        {
            var index = faceRenderer.sharedMesh.GetBlendShapeIndex(kv.Key);
            if (index < 0)
            {
                continue;
            }

            var current = faceRenderer.GetBlendShapeWeight(index);
            if (!Mathf.Approximately(current, kv.Value))
            {
                faceBlendShapeController?.SetEmotionWeight(kv.Key, kv.Value);
            }
        }

        faceBlendShapeController?.ApplyLateUpdate();
    }

    private void StartBlendShapeOverwriteMonitor(string blendShapeName, int index, float expectedWeight)
    {
        if (!Application.isPlaying)
        {
            return;
        }

        StartCoroutine(MonitorBlendShapeWeight(blendShapeName, index, expectedWeight, 0.2f));
        StartCoroutine(MonitorBlendShapeWeight(blendShapeName, index, expectedWeight, 1.0f));
    }

    private IEnumerator MonitorBlendShapeWeight(string blendShapeName, int index, float expectedWeight, float delay)
    {
        yield return new WaitForSeconds(delay);
        yield return new WaitForEndOfFrame();
        if (faceRenderer == null || faceRenderer.sharedMesh == null || index < 0 || index >= faceRenderer.sharedMesh.blendShapeCount)
        {
            yield break;
        }

        var actual = faceRenderer.GetBlendShapeWeight(index);
        Log($"After {delay:0.0}s actual={actual} name={blendShapeName} index={index}");
        var isValid = expectedWeight > 0.001f
            ? actual > Mathf.Max(1f, expectedWeight * 0.35f)
            : Mathf.Approximately(actual, 0f);
        if (!isValid)
        {
            Debug.LogWarning("[WebBridge] Emotion BlendShape was overwritten after setting.");
        }
    }

    private void ResolveVrm10Instance()
    {
        if (vrm10Instance == null)
        {
            vrm10Instance = GetComponentInChildren<Vrm10Instance>(true);
            if (vrm10Instance != null)
            {
                vrm10SearchSource = "webbridge-children";
            }
        }

        if (vrm10Instance == null && characterAnimator != null)
        {
            vrm10Instance = characterAnimator.GetComponentInChildren<Vrm10Instance>(true);
            if (vrm10Instance != null)
            {
                vrm10SearchSource = "animator-children";
            }
        }

        if (vrm10Instance == null && characterAnimator != null)
        {
            vrm10Instance = characterAnimator.GetComponentInParent<Vrm10Instance>(true);
            if (vrm10Instance != null)
            {
                vrm10SearchSource = "animator-parents";
            }
        }
    }

    private void TryApplyVrm10Expression(string emotion)
    {
        ResolveVrm10Instance();
        if (vrm10Instance == null)
        {
            return;
        }

        try
        {
            var runtimeExpression = vrm10Instance.Runtime?.Expression;
            if (runtimeExpression == null)
            {
                Debug.LogWarning("[WebBridge] VRM10 Runtime.Expression is unavailable.");
                return;
            }

            ResetVrm10Expression(runtimeExpression, ExpressionKey.Happy);
            ResetVrm10Expression(runtimeExpression, ExpressionKey.Angry);
            ResetVrm10Expression(runtimeExpression, ExpressionKey.Relaxed);
            ResetVrm10Expression(runtimeExpression, ExpressionKey.Surprised);
            ResetVrm10Expression(runtimeExpression, ExpressionKey.Neutral);

            switch (emotion)
            {
                case "supportive":
                    SetVrm10Expression(runtimeExpression, ExpressionKey.Happy, 1f);
                    SetVrm10Expression(runtimeExpression, ExpressionKey.Relaxed, 0.35f);
                    break;
                case "serious":
                    SetVrm10Expression(runtimeExpression, ExpressionKey.Angry, 0.75f);
                    break;
                case "warning":
                    SetVrm10Expression(runtimeExpression, ExpressionKey.Angry, 0.45f);
                    SetVrm10Expression(runtimeExpression, ExpressionKey.Surprised, 0.6f);
                    break;
                default:
                    SetVrm10Expression(runtimeExpression, ExpressionKey.Neutral, 1f);
                    break;
            }
        }
        catch (Exception e)
        {
            Debug.LogWarning($"[WebBridge] VRM10 expression apply failed: {e.Message}");
        }
    }

    private void ResetVrm10ExpressionsIfAvailable()
    {
        ResolveVrm10Instance();
        if (vrm10Instance == null)
        {
            return;
        }

        try
        {
            var runtimeExpression = vrm10Instance.Runtime?.Expression;
            if (runtimeExpression == null)
            {
                return;
            }

            ResetVrm10Expression(runtimeExpression, ExpressionKey.Happy);
            ResetVrm10Expression(runtimeExpression, ExpressionKey.Angry);
            ResetVrm10Expression(runtimeExpression, ExpressionKey.Relaxed);
            ResetVrm10Expression(runtimeExpression, ExpressionKey.Surprised);
            ResetVrm10Expression(runtimeExpression, ExpressionKey.Neutral);
        }
        catch (Exception e)
        {
            Debug.LogWarning($"[WebBridge] VRM10 expression reset failed: {e.Message}");
        }
    }

    private static void ResetVrm10Expression(Vrm10RuntimeExpression runtimeExpression, ExpressionKey key)
    {
        if (HasVrm10ExpressionKey(runtimeExpression, key))
        {
            runtimeExpression.SetWeight(key, 0f);
        }
    }

    private void SetVrm10Expression(Vrm10RuntimeExpression runtimeExpression, ExpressionKey key, float weight)
    {
        if (!HasVrm10ExpressionKey(runtimeExpression, key))
        {
            Debug.LogWarning($"[WebBridge] VRM10 expression preset unavailable: {key}");
            return;
        }

        runtimeExpression.SetWeight(key, Mathf.Clamp01(weight));
        Log($"VRM10 SetWeight preset={key} weight={Mathf.Clamp01(weight)}");
    }

    private static bool HasVrm10ExpressionKey(Vrm10RuntimeExpression runtimeExpression, ExpressionKey key)
    {
        foreach (var candidate in runtimeExpression.ExpressionKeys)
        {
            if (candidate.Equals(key))
            {
                return true;
            }
        }
        return false;
    }

    private void LogFaceRendererBlendShapeInfo()
    {
        ResolveFaceRendererReference();
        Log($"Validate FaceRenderer={(faceRenderer != null)}");
        if (faceRenderer == null)
        {
            Debug.LogWarning("[WebBridge] Face Renderer is not assigned.");
            return;
        }

        var mesh = faceRenderer.sharedMesh;
        Log($"Validate FaceRenderer Name={faceRenderer.name}");
        if (mesh == null)
        {
            Debug.LogWarning("[WebBridge] Face Renderer sharedMesh is null.");
            return;
        }

        LogFaceRendererBinding("Validate");
        Log($"Validate FaceRenderer BlendShapeCount={mesh.blendShapeCount}");
        for (var i = 0; i < mesh.blendShapeCount; i++)
        {
            Log($"BlendShape[{i}]={mesh.GetBlendShapeName(i)}");
        }
    }

    private void LogFaceRendererBinding(string context)
    {
        ResolveFaceRendererReference();
        if (faceRenderer == null)
        {
            Log($"{context} FaceRenderer=<null>");
            return;
        }

        var sharedMesh = faceRenderer.sharedMesh;
        var runtimeMesh = faceRenderer.GetComponent<MeshFilter>() != null ? faceRenderer.GetComponent<MeshFilter>().sharedMesh : null;
        Log(
            $"{context} FaceRendererPath={GetHierarchyPath(faceRenderer.transform)}, " +
            $"InstanceID={faceRenderer.GetInstanceID()}, " +
            $"RendererName={faceRenderer.name}, " +
            $"SharedMesh={(sharedMesh != null ? sharedMesh.name : "<null>")}, " +
            $"Mesh={(runtimeMesh != null ? runtimeMesh.name : sharedMesh != null ? sharedMesh.name : "<null>")}"
        );
    }

    private static string GetHierarchyPath(Transform target)
    {
        if (target == null)
        {
            return "<null>";
        }

        var path = new StringBuilder(target.name);
        var current = target.parent;
        while (current != null)
        {
            path.Insert(0, "/");
            path.Insert(0, current.name);
            current = current.parent;
        }
        return path.ToString();
    }

    private IEnumerator DebugTestEmotionBlendShapesRoutine()
    {
        ResolveFaceRendererReference();
        if (faceRenderer == null || faceRenderer.sharedMesh == null)
        {
            Debug.LogWarning("[WebBridge] Cannot test emotion blend shapes because Face Renderer is not ready.");
            yield break;
        }

        var mesh = faceRenderer.sharedMesh;
        foreach (var blendShapeName in emotionBlendShapes)
        {
            if (string.IsNullOrWhiteSpace(blendShapeName))
            {
                continue;
            }

            var index = mesh.GetBlendShapeIndex(blendShapeName);
            if (index < 0)
            {
                Debug.LogError($"[WebBridge] Missing BlendShape: {blendShapeName}");
                continue;
            }

            faceBlendShapeController?.SetEmotionWeight(blendShapeName, 80f);
            faceBlendShapeController?.ApplyLateUpdate();
            Log($"Debug test set BlendShape name={blendShapeName} index={index} weight=80 actual={faceRenderer.GetBlendShapeWeight(index)}");
            yield return new WaitForSeconds(0.2f);
            faceBlendShapeController?.SetEmotionWeight(blendShapeName, 0f);
            faceBlendShapeController?.ApplyLateUpdate();
            Log($"Debug test reset BlendShape name={blendShapeName} index={index} actual={faceRenderer.GetBlendShapeWeight(index)}");
            yield return new WaitForSeconds(0.1f);
        }
    }

    private string ResolveGestureStateName(string gesture)
    {
        return gesture switch
        {
            "idle" => "idle",
            "greeting" => "Standing Greeting",
            "explain" => "explain",
            "shrug" => "explain",
            "point" => "point",
            "confirm" => "confirm",
            "thinking" => "Thoughtful Head Shake",
            "warning" => "point",
            "dismissing" => "Dismissing",
            "laughing" => "Laughing",
            _ => "idle"
        };
    }

    private static string NormalizeGestureInput(string gesture)
    {
        if (string.IsNullOrWhiteSpace(gesture))
        {
            return "idle";
        }

        var trimmed = gesture.Trim();
        var lower = trimmed.ToLowerInvariant();
        return trimmed switch
        {
            "Thoughtful Head Shake" => "thinking",
            "Laughing" => "laughing",
            "Dismissing" => "dismissing",
            _ => lower switch
            {
                "thoughtful head shake" => "thinking",
                "dismissing gesture" => "dismissing",
                "shrug" => "shrug",
                "explain" => "explain",
                "point" => "point",
                "thinking" => "thinking",
                "confirm" => "confirm",
                "greeting" => "greeting",
                "warning" => "warning",
                "laughing" => "laughing",
                "dismiss" => "dismissing",
                "dismissing" => "dismissing",
                _ => trimmed
            }
        };
    }

    private string GetDefaultSpeakingGesture(string emotion)
    {
        return emotion switch
        {
            "supportive" => "confirm",
            "serious" => "thinking",
            "warning" => "warning",
            _ => "explain"
        };
    }

    private void TryPlayGestureState(string stateName, float duration)
    {
        if (characterAnimator == null)
        {
            Debug.LogError("[WebBridge] Character Animator is not assigned.");
            return;
        }

        if (string.IsNullOrWhiteSpace(stateName))
        {
            return;
        }

        var fullPath = BaseLayerPrefix + stateName;
        var stateHash = Animator.StringToHash(fullPath);
        var currentState = characterAnimator.GetCurrentAnimatorStateInfo(0);
        Log($"Animator object: {characterAnimator.gameObject.name}");
        Log($"Controller: {characterAnimator.runtimeAnimatorController?.name ?? "<null>"}");
        Log($"Current state before: {ResolveStateName(currentState)}");
        Log($"Target state: {fullPath}");
        var hasState = characterAnimator.HasState(0, stateHash);
        Log($"HasState: {hasState}");
        if (!hasState)
        {
            Debug.LogError($"[WebBridge] Missing Animator state: {fullPath}");
            return;
        }

        if (returnToIdleRoutine != null)
        {
            StopCoroutine(returnToIdleRoutine);
            returnToIdleRoutine = null;
        }

        characterAnimator.CrossFade(stateHash, duration, 0);
        Log("[WebBridge] CrossFade called");

        if (stateDebugRoutine != null)
        {
            StopCoroutine(stateDebugRoutine);
        }
        stateDebugRoutine = StartCoroutine(LogStateAfterDelay(0.2f, stateHash));
    }

    private void UpdateGestureLoop()
    {
        if (audioSource == null || !audioSource.isPlaying || characterAnimator == null)
        {
            return;
        }

        if (string.IsNullOrWhiteSpace(currentGesture) || currentGesture == "idle")
        {
            ApplyGesture(GetDefaultSpeakingGesture(currentEmotion));
            return;
        }

        var gesture = NormalizeGestureInput(currentGesture);
        if (!IsSpeakingLoopGesture(gesture))
        {
            return;
        }

        if (Time.time - lastGestureLoopReplayTime < nextGestureLoopReplayInterval)
        {
            return;
        }

        var stateName = ResolveGestureStateName(gesture);
        Debug.Log($"[GestureLoop] replay gesture={gesture} state={stateName}");
        TryPlayGestureState(stateName, 0.12f);
        ResetGestureLoopSchedule();
    }

    private bool IsSpeakingLoopGesture(string gesture)
    {
        return gesture switch
        {
            "explain" => true,
            "shrug" => true,
            "point" => true,
            "thinking" => true,
            "warning" => true,
            "confirm" => true,
            "greeting" => true,
            _ => false
        };
    }

    private void ResetGestureLoopSchedule()
    {
        var minInterval = Mathf.Min(gestureReplayIntervalMin, gestureReplayIntervalMax);
        var maxInterval = Mathf.Max(gestureReplayIntervalMin, gestureReplayIntervalMax);
        lastGestureLoopReplayTime = Time.time;
        nextGestureLoopReplayInterval = UnityEngine.Random.Range(minInterval, maxInterval);
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

    [ContextMenu("Debug/Test Expression BlendShapes")]
    private void DebugTestEmotionBlendShapes()
    {
        LogFaceRendererBlendShapeInfo();
        if (!Application.isPlaying)
        {
            Debug.LogWarning("[WebBridge] Enter Play Mode to run timed BlendShape tests.");
            return;
        }

        StartCoroutine(DebugTestEmotionBlendShapesRoutine());
    }

    [ContextMenu("Debug/Test Hold Expression")]
    private void DebugTestHoldExpression()
    {
        if (!Application.isPlaying)
        {
            Debug.LogWarning("[WebBridge] Enter Play Mode to run hold-expression test.");
            return;
        }

        if (holdExpressionRoutine != null)
        {
            StopCoroutine(holdExpressionRoutine);
        }

        holdExpressionRoutine = StartCoroutine(HoldExpressionRoutine());
    }

    private IEnumerator HoldExpressionRoutine()
    {
        ResolveFaceRendererReference();
        if (faceRenderer == null || faceRenderer.sharedMesh == null)
        {
            Debug.LogWarning("[WebBridge] Cannot hold expression because Face Renderer is not ready.");
            yield break;
        }

        const string blendShapeName = "Fcl_ALL_Joy";
        var index = faceRenderer.sharedMesh.GetBlendShapeIndex(blendShapeName);
        if (index < 0)
        {
            Debug.LogError($"[WebBridge] Missing BlendShape: {blendShapeName}");
            yield break;
        }

        var elapsed = 0f;
        var logTimer = 0f;
        while (elapsed < 5f)
        {
            faceBlendShapeController?.SetEmotionWeight(blendShapeName, 100f);
            faceBlendShapeController?.ApplyLateUpdate();
            elapsed += Time.deltaTime;
            logTimer += Time.deltaTime;
            if (logTimer >= 1f)
            {
                logTimer = 0f;
                Log($"HoldExpression actual={faceRenderer.GetBlendShapeWeight(index)} elapsed={elapsed:0.0}s");
            }
            yield return null;
        }

        faceBlendShapeController?.SetEmotionWeight(blendShapeName, 0f);
        faceBlendShapeController?.ApplyLateUpdate();
        Log($"HoldExpression finished actual={faceRenderer.GetBlendShapeWeight(index)}");
        holdExpressionRoutine = null;
    }

    [ContextMenu("Debug/Validate Bridge Setup")]
    private void DebugValidateBridgeSetup()
    {
        Log($"Validate CharacterAnimator={(characterAnimator != null)}, AudioSource={(audioSource != null)}");
        if (characterAnimator == null)
        {
            Debug.LogError("[WebBridge] Character Animator is not assigned.");
            return;
        }
        Log($"Validate Animator Object={characterAnimator.gameObject.name}");
        Log($"Validate Animator Controller={characterAnimator.runtimeAnimatorController?.name ?? "<null>"}");
        Log($"Validate Animator Avatar={characterAnimator.avatar?.name ?? "<null>"}");
        Log($"Validate AnimatorParam Emotion={HasParameter(characterAnimator, "Emotion", AnimatorControllerParameterType.Int)}");
        Log($"Validate AnimatorParam Gesture={HasParameter(characterAnimator, "Gesture", AnimatorControllerParameterType.Int)}");
        Log($"Validate Current Emotion={currentEmotion}, Gesture={currentGesture}");
        Log(
            "Validate LipSync " +
            $"enabled={enableLipSync}, renderer={(lipSyncFaceRenderer != null)}, " +
            $"index={mouthOpenBlendShapeIndex}, name={mouthOpenBlendShapeName}"
        );
        Log($"Validate EmotionBlendShapes enabled={enableExpressionBlendShapes}, count={(emotionBlendShapes == null ? 0 : emotionBlendShapes.Length)}");
        LogFaceRendererBlendShapeInfo();
        ResolveVrm10Instance();
        Log($"Validate VRM10 Instance={(vrm10Instance != null)}");
        if (vrm10Instance != null)
        {
            Log($"Validate VRM10 Object={vrm10Instance.gameObject.name}, source={vrm10SearchSource}");
        }
        Log($"Validate useLateUpdateExpressionReapply={useLateUpdateExpressionReapply}");
    }

    private IEnumerator LogStateAfterDelay(float delay, int targetStateHash)
    {
        yield return new WaitForSeconds(delay);
        if (characterAnimator == null)
        {
            yield break;
        }
        var currentState = characterAnimator.GetCurrentAnimatorStateInfo(0);
        Log($"Current state after 0.2s: {ResolveStateName(currentState)}");
        Log($"Current state fullPathHash == target: {currentState.fullPathHash == targetStateHash}");
    }

    private IEnumerator ReturnToIdleAfterDelay(float delay)
    {
        yield return new WaitForSeconds(delay);
        ApplyGesture("idle");
    }

    private static string ResolveStateName(AnimatorStateInfo stateInfo)
    {
        return $"shortHash={stateInfo.shortNameHash}, fullHash={stateInfo.fullPathHash}";
    }

    private void EnsureFaceBlendShapeController()
    {
        if (faceBlendShapeController == null)
        {
            faceBlendShapeController = new FaceBlendShapeController(
                nameof(WebBridge),
                (writer, blendShapeName, value) =>
                {
                    if (debugBlendShapeWriterLogging)
                    {
                        LogBlendShapeWriter(writer, blendShapeName, value);
                    }
                }
            );
        }
        faceBlendShapeController.SetEmotionProfile(currentEmotion);
        faceBlendShapeController.BindTargets(faceRenderer, lipSyncFaceRenderer);
    }

    private static void LogBlendShapeWriter(string writer, string blendShapeName, float value)
    {
        Debug.Log($"[BlendShapeWriter] writer={writer} name={blendShapeName} value={value:0.###} frame={Time.frameCount}");
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
