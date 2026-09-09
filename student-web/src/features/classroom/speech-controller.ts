import type { LearningTeacherProfile } from "@/lib/contracts/learning";
import {
  browserVoiceForTeacher,
  type LearningBrowserVoice,
} from "@/features/learning/teacher-registry";

export type NarrationPlaybackSource = "package_audio" | "browser_tts_fallback" | "silent";

export type SpeechController = {
  speak: (text: string, signal: AbortSignal) => Promise<{ played: boolean }>;
  stop: () => void;
};

export type NarrationPlaybackResult = {
  played: boolean;
  source: NarrationPlaybackSource;
  assetFailed?: boolean;
};

export type ClassroomAudioController = {
  playNarration: (
    input: {
      text: string;
      audioAssetRef?: string;
      teacher?: LearningTeacherProfile;
      allowBrowserFallback?: boolean;
      onSource?: (source: NarrationPlaybackSource) => void;
      onProgress?: (progress: number) => void;
    },
    signal: AbortSignal,
  ) => Promise<NarrationPlaybackResult>;
  stop: () => void;
};

export function createClassroomAudioController(): ClassroomAudioController {
  let activeAudio: HTMLAudioElement | null = null;
  let activeSpeech: SpeechController | null = null;

  function stop() {
    if (activeAudio) {
      activeAudio.pause();
      activeAudio.removeAttribute("src");
      activeAudio.load();
      activeAudio = null;
    }
    activeSpeech?.stop();
    activeSpeech = null;
  }

  return {
    async playNarration(input, signal) {
      stop();
      const assetUrl = learningAssetUrl(input.audioAssetRef);
      if (assetUrl) {
        input.onSource?.("package_audio");
        try {
          const audio = new Audio();
          activeAudio = audio;
          await playAudioElement(audio, assetUrl, signal, input.onProgress);
          if (activeAudio === audio) activeAudio = null;
          return { played: true, source: "package_audio" };
        } catch (error) {
          activeAudio = null;
          if (isAbortError(error)) throw error;
          if (input.allowBrowserFallback === false) {
            input.onSource?.("silent");
            return { played: false, source: "silent", assetFailed: true };
          }
        }
      }

      if (input.allowBrowserFallback === false) {
        input.onSource?.("silent");
        return { played: false, source: "silent", assetFailed: Boolean(assetUrl) };
      }
      input.onSource?.("browser_tts_fallback");
      const speech = browserSpeechController(browserVoiceForTeacher(input.teacher));
      activeSpeech = speech;
      const result = await speech.speak(input.text, signal);
      if (activeSpeech === speech) activeSpeech = null;
      const source = result.played ? "browser_tts_fallback" : "silent";
      if (!result.played) input.onSource?.("silent");
      return { ...result, source, assetFailed: Boolean(assetUrl) };
    },
    stop,
  };
}

export function browserSpeechController(
  voice: LearningBrowserVoice = { language: "zh-CN", rate: 0.9, pitch: 1.08 },
): SpeechController {
  return {
    async speak(text, signal) {
      if (typeof window === "undefined" || !("speechSynthesis" in window) || typeof SpeechSynthesisUtterance === "undefined") {
        await fallbackReadingDelay(text, signal);
        return { played: false };
      }
      window.speechSynthesis.cancel();
      return new Promise((resolve, reject) => {
        const utterance = new SpeechSynthesisUtterance(text);
        utterance.lang = voice.language;
        utterance.rate = voice.rate;
        utterance.pitch = voice.pitch;
        const voices = window.speechSynthesis.getVoices();
        const languagePrefix = voice.language.toLowerCase().split("-")[0];
        utterance.voice = voices.find((item) => item.lang.toLowerCase().startsWith(languagePrefix)) || null;
        const abort = () => {
          window.speechSynthesis.cancel();
          reject(new DOMException("课堂讲解已停止", "AbortError"));
        };
        signal.addEventListener("abort", abort, { once: true });
        utterance.onend = () => {
          signal.removeEventListener("abort", abort);
          resolve({ played: true });
        };
        utterance.onerror = (event) => {
          signal.removeEventListener("abort", abort);
          if (event.error === "canceled" || event.error === "interrupted") reject(new DOMException("课堂讲解已停止", "AbortError"));
          else resolve({ played: false });
        };
        window.speechSynthesis.speak(utterance);
      });
    },
    stop() {
      if (typeof window !== "undefined" && "speechSynthesis" in window) window.speechSynthesis.cancel();
    },
  };
}

export function learningAssetUrl(assetRef: string | null | undefined) {
  if (!assetRef?.startsWith("asset:")) return null;
  const assetId = assetRef.slice(6).trim();
  if (!assetId || assetId.length > 160 || /[\\/]/.test(assetId)) return null;
  return `/api/learning/assets/${encodeURIComponent(assetId)}`;
}

function playAudioElement(
  audio: HTMLAudioElement,
  url: string,
  signal: AbortSignal,
  onProgress?: (progress: number) => void,
) {
  return new Promise<void>((resolve, reject) => {
    let animationFrame = 0;
    let settled = false;
    audio.preload = "auto";
    audio.src = url;

    const reportProgress = () => {
      if (Number.isFinite(audio.duration) && audio.duration > 0) {
        onProgress?.(Math.min(1, Math.max(0, audio.currentTime / audio.duration)));
      }
      if (!audio.paused && typeof requestAnimationFrame === "function") {
        animationFrame = requestAnimationFrame(reportProgress);
      }
    };
    const cleanup = () => {
      signal.removeEventListener("abort", abort);
      audio.removeEventListener("ended", ended);
      audio.removeEventListener("error", failed);
      audio.removeEventListener("playing", reportProgress);
      if (animationFrame && typeof cancelAnimationFrame === "function") cancelAnimationFrame(animationFrame);
    };
    const finish = (callback: () => void) => {
      if (settled) return;
      settled = true;
      cleanup();
      callback();
    };
    const abort = () => {
      audio.pause();
      finish(() => reject(new DOMException("课堂讲解已停止", "AbortError")));
    };
    const ended = () => {
      onProgress?.(1);
      finish(resolve);
    };
    const failed = () => finish(() => reject(new Error("正式课程音频暂时无法播放")));

    signal.addEventListener("abort", abort, { once: true });
    audio.addEventListener("ended", ended, { once: true });
    audio.addEventListener("error", failed, { once: true });
    audio.addEventListener("playing", reportProgress, { once: true });
    onProgress?.(0);
    void audio.play().catch(failed);
  });
}

function isAbortError(error: unknown) {
  return error instanceof DOMException && error.name === "AbortError";
}

function fallbackReadingDelay(text: string, signal: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    const duration = Math.min(2200, Math.max(600, text.length * 45));
    const timer = window.setTimeout(resolve, duration);
    signal.addEventListener("abort", () => {
      window.clearTimeout(timer);
      reject(new DOMException("课堂讲解已停止", "AbortError"));
    }, { once: true });
  });
}
