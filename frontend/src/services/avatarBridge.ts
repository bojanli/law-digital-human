import { reactive } from "vue";

export type AvatarEmotion = "calm" | "serious" | "supportive" | "warning";
export type AvatarGesture =
  | "idle"
  | "greeting"
  | "explain"
  | "point"
  | "confirm"
  | "thinking"
  | "warning"
  | "dismissing"
  | "laughing"
  | "Thoughtful Head Shake"
  | "Laughing"
  | "Dismissing";

export type AvatarBridgeCommand = {
  gesture?: string;
  emotion?: string;
  text?: string;
  audioUrl?: string;
};
export type AvatarAudioOptions = {
  rate?: number;
  volume?: number;
};

type UnityEvent = "OnAvatarReady" | "OnPlayFinished";

type UnityInstance = {
  SendMessage?: (gameObject: string, method: string, parameter?: string) => void;
};

declare global {
  interface Window {
    unityInstance?: UnityInstance;
  }
}

const KNOWN_EMOTIONS: readonly AvatarEmotion[] = ["calm", "serious", "supportive", "warning"] as const;
const DEFAULT_GESTURE_BY_EMOTION: Record<AvatarEmotion, AvatarGesture> = {
  calm: "explain",
  supportive: "explain",
  serious: "Thoughtful Head Shake",
  warning: "point",
};

let callbacksBound = false;
const avatarAudioOptions: Required<AvatarAudioOptions> = {
  rate: 1,
  volume: 1,
};

export const avatarState = reactive({
  ready: false,
  isPlaying: false,
  emotion: "calm" as AvatarEmotion,
  subtitle: "",
  lastAudioUrl: "" as string,
  lastEvent: "" as string,
});

export function setUnityInstance(instance: UnityInstance | null): void {
  if (typeof window === "undefined") {
    return;
  }
  window.unityInstance = instance || undefined;
  if (!instance) {
    avatarState.ready = false;
  }
}

export function normalizeAvatarEmotion(value: unknown, fallback: AvatarEmotion = "calm"): AvatarEmotion {
  return typeof value === "string" && KNOWN_EMOTIONS.includes(value as AvatarEmotion)
    ? (value as AvatarEmotion)
    : fallback;
}

export function sendAvatarCommand(command: AvatarBridgeCommand): void {
  if (typeof window === "undefined") {
    return;
  }

  const unityInstance = window.unityInstance;
  if (!unityInstance?.SendMessage) {
    avatarState.ready = false;
    console.warn("[AvatarBridge] unityInstance not ready", command);
    return;
  }
  avatarState.ready = true;

  const payload = JSON.stringify(command);
  console.log("[AvatarBridge] SendMessage WebBridge.ReceiveMessage", payload);
  try {
    unityInstance.SendMessage("WebBridge", "ReceiveMessage", payload);
    console.log("[AvatarBridge] SendMessage success");
  } catch (err) {
    console.error("[AvatarBridge] SendMessage failed", err);
  }
}

export function bindAvatarCallbacks(): void {
  if (callbacksBound || typeof window === "undefined") {
    return;
  }
  callbacksBound = true;

  window.addEventListener("message", (evt: MessageEvent<unknown>) => {
    const data = evt.data;
    if (!data || typeof data !== "object") {
      return;
    }
    const eventName = (data as { event?: unknown }).event;
    if (eventName !== "OnAvatarReady" && eventName !== "OnPlayFinished") {
      return;
    }
    handleUnityEvent(eventName);
  });

  window.addEventListener("avatar:ready", () => handleUnityEvent("OnAvatarReady"));
  window.addEventListener("avatar:play-finished", () => handleUnityEvent("OnPlayFinished"));
}

function handleUnityEvent(eventName: UnityEvent): void {
  avatarState.lastEvent = eventName;
  if (eventName === "OnAvatarReady") {
    avatarState.ready = true;
  } else if (eventName === "OnPlayFinished") {
    avatarState.isPlaying = false;
    setAvatarPose("idle", "calm");
  }
}

export function setAvatarSubtitle(text: string): void {
  avatarState.subtitle = text.trim();
}

export function setAvatarEmotion(emotion: AvatarEmotion): void {
  avatarState.emotion = emotion;
  sendAvatarCommand({ emotion });
}

export function setAvatarGesture(gesture: AvatarGesture): void {
  sendAvatarCommand({ gesture });
}

export function setAvatarPose(gesture: string, emotion: AvatarEmotion, text = ""): void {
  avatarState.emotion = emotion;
  if (text.trim()) {
    setAvatarSubtitle(text);
  }
  sendAvatarCommand({
    gesture,
    emotion,
    text: text.trim() || undefined,
  });
}

export function getDefaultGestureForEmotion(emotion: AvatarEmotion): AvatarGesture {
  return DEFAULT_GESTURE_BY_EMOTION[emotion];
}

export function playAvatar(
  audioUrl: string,
  subtitleText: string,
  emotion: AvatarEmotion = avatarState.emotion,
  gesture: string = getDefaultGestureForEmotion(emotion),
): void {
  const trimmedUrl = audioUrl.trim();
  if (!trimmedUrl) {
    return;
  }

  avatarState.emotion = emotion;
  avatarState.isPlaying = true;
  avatarState.lastAudioUrl = trimmedUrl;
  setAvatarSubtitle(subtitleText);
  console.log("[TTS] playAvatar payload =", {
    gesture,
    emotion,
    text: avatarState.subtitle,
    audioUrl: trimmedUrl,
  });

  sendAvatarCommand({
    gesture,
    emotion,
    text: avatarState.subtitle,
    audioUrl: trimmedUrl,
  });
  console.log("[TTS] playback source=unity-only");
}

export function setAvatarAudioOptions(options: AvatarAudioOptions): void {
  if (typeof options.rate === "number" && Number.isFinite(options.rate)) {
    avatarAudioOptions.rate = Math.min(2, Math.max(0.5, options.rate));
  }
  if (typeof options.volume === "number" && Number.isFinite(options.volume)) {
    avatarAudioOptions.volume = Math.min(1, Math.max(0, options.volume));
  }
  // Unity-side audio params are not controlled here for now.
}

export function stopAvatar(): void {
  avatarState.isPlaying = false;
  sendAvatarCommand({ gesture: "idle", emotion: "calm", text: "", audioUrl: "" });
  if (typeof window !== "undefined") {
    const unityInstance = window.unityInstance;
    if (unityInstance?.SendMessage) {
      const legacyStopPayload = JSON.stringify({
        source: "law-web",
        target: "unity-avatar",
        command: "Avatar.Stop",
        payload: {},
      });
      try {
        unityInstance.SendMessage("WebBridge", "OnWebCommand", legacyStopPayload);
      } catch {
        // no-op: ReceiveMessage channel above is still sent.
      }
    }
  }
}
