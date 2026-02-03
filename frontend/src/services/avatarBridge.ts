import { reactive } from "vue";

export type AvatarEmotion = "calm" | "serious" | "supportive" | "warning";
export type AvatarGesture = "idle" | "explain" | "point" | "confirm";

type AvatarCommand = "Avatar.Play" | "Avatar.SetEmotion" | "Avatar.SetGesture" | "Avatar.Stop";
type UnityEvent = "OnAvatarReady" | "OnPlayFinished";

type UnityCommandMessage = {
  source: "law-web";
  target: "unity-avatar";
  command: AvatarCommand;
  payload: Record<string, string>;
};

declare global {
  interface Window {
    unityInstance?: {
      SendMessage?: (gameObject: string, method: string, parameter?: string) => void;
    };
  }
}

const KNOWN_EMOTIONS: readonly AvatarEmotion[] = ["calm", "serious", "supportive", "warning"] as const;

let callbacksBound = false;

export const avatarState = reactive({
  ready: false,
  isPlaying: false,
  emotion: "calm" as AvatarEmotion,
  subtitle: "",
  lastAudioUrl: "" as string,
  lastEvent: "" as string,
});

export function normalizeAvatarEmotion(value: unknown, fallback: AvatarEmotion = "calm"): AvatarEmotion {
  return typeof value === "string" && KNOWN_EMOTIONS.includes(value as AvatarEmotion)
    ? (value as AvatarEmotion)
    : fallback;
}

function dispatchCommand(command: AvatarCommand, payload: Record<string, string>): void {
  if (typeof window === "undefined") {
    return;
  }

  const message: UnityCommandMessage = {
    source: "law-web",
    target: "unity-avatar",
    command,
    payload,
  };

  window.dispatchEvent(new CustomEvent("avatar:command", { detail: message }));
  window.postMessage(message, "*");

  const sender = window.unityInstance?.SendMessage;
  if (typeof sender === "function") {
    try {
      sender("WebBridge", "OnWebCommand", JSON.stringify(message));
    } catch {
      // Keep fallback transport available even if Unity bridge object is absent.
    }
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
  }
}

export function setAvatarSubtitle(text: string): void {
  avatarState.subtitle = text.trim();
}

export function setAvatarEmotion(emotion: AvatarEmotion): void {
  avatarState.emotion = emotion;
  dispatchCommand("Avatar.SetEmotion", { emotionTag: emotion });
}

export function setAvatarGesture(gesture: AvatarGesture): void {
  dispatchCommand("Avatar.SetGesture", { gestureTag: gesture });
}

export function playAvatar(audioUrl: string, subtitleText: string, emotion: AvatarEmotion = avatarState.emotion): void {
  const trimmedUrl = audioUrl.trim();
  if (!trimmedUrl) {
    return;
  }

  if (emotion !== avatarState.emotion) {
    setAvatarEmotion(emotion);
  }

  avatarState.isPlaying = true;
  avatarState.lastAudioUrl = trimmedUrl;
  setAvatarSubtitle(subtitleText);

  dispatchCommand("Avatar.Play", {
    audioUrl: trimmedUrl,
    subtitleText: avatarState.subtitle,
  });
}

export function stopAvatar(): void {
  avatarState.isPlaying = false;
  dispatchCommand("Avatar.Stop", {});
}
