import { useCallback, useEffect, useRef, useState } from "react";

interface AudioResources {
  context: AudioContext;
  stream?: MediaStream;
  source?: MediaStreamAudioSourceNode;
  processor?: AudioWorkletNode;
  mute?: GainNode;
  flushed?: () => void;
  stopPromise?: Promise<void>;
}

export function audioErrorMessage(error: unknown): string {
  if (error instanceof DOMException) {
    if (error.name === "NotAllowedError" || error.name === "SecurityError") {
      return "Akses mikrofon ditolak. Izinkan mikrofon di browser, lalu coba lagi.";
    }
    if (error.name === "NotFoundError")
      return "Mikrofon tidak ditemukan. Hubungkan mikrofon lalu coba lagi.";
    if (error.name === "NotReadableError")
      return "Mikrofon tidak dapat digunakan. Periksa perangkat atau aplikasi lain yang memakainya.";
  }
  return error instanceof Error
    ? error.message
    : "Mikrofon belum dapat digunakan.";
}

export function useAudioStream() {
  const resources = useRef<AudioResources | null>(null);
  const generation = useRef(0);
  const mounted = useRef(true);
  const samples = useRef(0);
  const [level, setLevel] = useState(0);
  const [duration, setDuration] = useState(0);

  const stop = useCallback(async () => {
    generation.current++;
    const current = resources.current;
    if (!current) return;
    if (current.stopPromise) return current.stopPromise;
    current.stopPromise = (async () => {
      current.stream?.getTracks().forEach((track) => {
        track.onended = null;
        track.stop();
      });
      if (current.processor && current.context.state === "running") {
        await new Promise<void>((resolve) => {
          const timeout = window.setTimeout(resolve, 1000);
          current.flushed = () => {
            clearTimeout(timeout);
            resolve();
          };
          current.processor!.port.postMessage({ type: "flush" });
        });
      }
      current.source?.disconnect();
      current.processor?.disconnect();
      current.mute?.disconnect();
      if (current.processor) current.processor.port.onmessage = null;
      if (current.processor) current.processor.onprocessorerror = null;
      try {
        if (current.context.state !== "closed") await current.context.close();
      } finally {
        if (resources.current === current) resources.current = null;
        if (mounted.current) setLevel(0);
      }
    })();
    return current.stopPromise;
  }, []);

  // Called directly from the record button to unlock Web Audio under user activation.
  const prepare = useCallback(async () => {
    if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
      throw new Error(
        "Mikrofon memerlukan HTTPS atau localhost dan browser yang mendukung Web Audio.",
      );
    }
    if (!window.AudioContext || !window.AudioWorkletNode) {
      throw new Error(
        "Browser belum mendukung AudioWorklet. Gunakan Chrome, Edge, Firefox, atau Safari versi terbaru.",
      );
    }
    if (resources.current) await stop();
    const ticket = ++generation.current;
    let context: AudioContext;
    try {
      context = new AudioContext({
        sampleRate: 16000,
        latencyHint: "interactive",
      });
    } catch {
      context = new AudioContext({ latencyHint: "interactive" });
    }
    const current: AudioResources = { context };
    resources.current = current;
    samples.current = 0;
    setDuration(0);
    setLevel(0);
    try {
      await context.resume();
      if (ticket !== generation.current)
        throw new DOMException("Sesi dibatalkan.", "AbortError");
    } catch (error) {
      if (resources.current === current) await stop();
      throw error;
    }
  }, [stop]);

  const start = useCallback(
    async (
      onFrame: (buffer: ArrayBuffer) => void,
      onFailure: (message: string) => void,
    ) => {
      const current = resources.current;
      const ticket = generation.current;
      if (!current)
        throw new Error("Perangkat audio belum disiapkan. Mulai sesi kembali.");
      try {
        await current.context.audioWorklet.addModule(
          `${import.meta.env.BASE_URL}audio-worklet.js`,
        );
        if (ticket !== generation.current || resources.current !== current) {
          throw new DOMException("Sesi dibatalkan.", "AbortError");
        }
        const stream = await navigator.mediaDevices.getUserMedia({
          audio: {
            channelCount: 1,
            sampleRate: { ideal: 16000 },
            echoCancellation: true,
            noiseSuppression: true,
          },
        });
        if (ticket !== generation.current || resources.current !== current) {
          stream.getTracks().forEach((track) => track.stop());
          throw new DOMException("Sesi dibatalkan.", "AbortError");
        }
        current.stream = stream;
        current.source = current.context.createMediaStreamSource(stream);
        current.processor = new AudioWorkletNode(
          current.context,
          "codetalk-audio",
          {
            channelCount: 1,
            channelCountMode: "explicit",
            numberOfInputs: 1,
            numberOfOutputs: 1,
            outputChannelCount: [1],
          },
        );
        current.processor.port.onmessage = ({ data }) => {
          if (data.type === "flushed") {
            current.flushed?.();
            return;
          }
          if (data.type !== "audio" || !(data.buffer instanceof ArrayBuffer))
            return;
          try {
            onFrame(data.buffer);
            samples.current += data.buffer.byteLength / 2;
            if (mounted.current) {
              setDuration(samples.current / 16000);
              setLevel(Math.min(1, Math.max(0, data.rms * 5)));
            }
          } catch (error) {
            onFailure(audioErrorMessage(error));
          }
        };
        current.processor.onprocessorerror = () =>
          onFailure("Pemrosesan audio terhenti. Akhiri sesi lalu coba lagi.");
        stream.getAudioTracks().forEach((track) => {
          track.onended = () =>
            onFailure(
              "Mikrofon terputus. Periksa perangkat lalu mulai sesi kembali.",
            );
        });
        // Keep the worklet in a live audio graph without playing the microphone back.
        current.mute = current.context.createGain();
        current.mute.gain.value = 0;
        current.source.connect(current.processor);
        current.processor
          .connect(current.mute)
          .connect(current.context.destination);
      } catch (error) {
        if (resources.current === current) await stop();
        throw error;
      }
    },
    [stop],
  );

  const reset = useCallback(() => {
    samples.current = 0;
    setDuration(0);
    setLevel(0);
  }, []);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      void stop();
    };
  }, [stop]);

  return { prepare, start, stop, reset, level, duration };
}
