<template>
  <div class="unity-card" aria-label="Unity 数字人画面">
    <iframe ref="unityFrameRef" class="unity-frame" src="/unity/index.html" title="Unity Avatar" scrolling="no" />
    <p v-if="unityError" class="unity-error">{{ unityError }}</p>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from "vue";
import { bindAvatarCallbacks, setUnityInstance } from "../services/avatarBridge";

type UnityInstance = {
  SendMessage?: (gameObject: string, method: string, parameter?: string) => void;
};

declare global {
  interface Window {
    createUnityInstance?: (
      canvas: HTMLCanvasElement,
      config: Record<string, unknown>,
      onProgress?: (progress: number) => void
    ) => Promise<UnityInstance>;
    unityInstance?: UnityInstance;
  }
}

const unityFrameRef = ref<HTMLIFrameElement | null>(null);
const unityInstanceRef = ref<UnityInstance | null>(null);
const unityError = ref("");

function mountUnityFrameBridge(): void {
  const frame = unityFrameRef.value;
  if (!frame) {
    unityError.value = "Unity 画面未找到";
    return;
  }

  unityInstanceRef.value = {
    SendMessage: (gameObject: string, method: string, parameter?: string) => {
      frame.contentWindow?.postMessage(
        { type: "unity-sendmessage", gameObject, method, parameter: parameter ?? "" },
        "*",
      );
    },
  };
  setUnityInstance(unityInstanceRef.value);
}

onMounted(() => {
  bindAvatarCallbacks();
  mountUnityFrameBridge();
});

onBeforeUnmount(() => {
  unityInstanceRef.value = null;
  setUnityInstance(null);
});
</script>

<style scoped>
.unity-card {
  position: relative;
  width: 100%;
  overflow: hidden;
  border-radius: 22px;
  background:
    radial-gradient(110% 100% at 50% 0%, rgba(76, 126, 240, 0.15), transparent 65%),
    linear-gradient(180deg, rgba(15, 24, 40, 0.78), rgba(14, 20, 32, 0.92));
}

.unity-frame {
  display: block;
  width: 100%;
  height: min(64vh, 720px);
  border: 0;
  overflow: hidden;
}

.unity-error {
  position: absolute;
  left: 0.8rem;
  bottom: 0.8rem;
  margin: 0;
  border-radius: 12px;
  padding: 0.45rem 0.7rem;
  background: rgba(180, 56, 70, 0.82);
  color: #fff;
  font-size: 0.78rem;
}

@media (max-width: 900px) {
  .unity-frame {
    height: 280px;
  }
}
</style>
