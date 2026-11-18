import { useCallback, useEffect, useRef, useState } from "react";
import { backendUrl } from "../api";
import type {
  ServerStatus,
  TelemetrySample,
  TranscriptSegment,
} from "../types";

interface Transcript {
  finalText: string;
  partialText: string;
  partialSeconds: number;
  segments: TranscriptSegment[];
}

interface Connection {
  socket: WebSocket;
  ready: boolean;
  expectedClose: boolean;
  stopping: boolean;
  readyTimer?: number;
  stopTimer?: number;
  resolveReady?: () => void;
  rejectReady?: (error: Error) => void;
  resolveStop?: () => void;
  rejectStop?: (error: Error) => void;
  stopPromise?: Promise<void>;
}

const emptyTranscript = (): Transcript => ({
  finalText: "",
  partialText: "",
  partialSeconds: 0,
  segments: [],
});
const finite = (value: unknown): number | null =>
  typeof value === "number" && Number.isFinite(value) ? value : null;

export function useWebSocketASR(onFailure: (message: string) => void) {
  const connection = useRef<Connection | null>(null);
  const failureHandler = useRef(onFailure);
  failureHandler.current = onFailure;
  const snapshot = useRef<Transcript>(emptyTranscript());
  const samples = useRef<TelemetrySample[]>([]);
  const metadata = useRef<Record<string, unknown>>({});
  const summary = useRef<unknown>(null);
  const [transcript, setTranscript] = useState<Transcript>(emptyTranscript);
  const [serverStatus, setServerStatus] = useState<ServerStatus>("stopped");
  const [metrics, setMetrics] = useState<{
    latencyMs: number | null;
    rtf: number | null;
  }>({ latencyMs: null, rtf: null });
  const [error, setError] = useState<string | null>(null);

  const cancel = useCallback(() => {
    const current = connection.current;
    if (!current) return;
    connection.current = null;
    current.expectedClose = true;
    clearTimeout(current.readyTimer);
    clearTimeout(current.stopTimer);
    const cancelled = new DOMException("Sesi dibatalkan.", "AbortError");
    current.rejectReady?.(cancelled);
    current.rejectStop?.(cancelled);
    current.socket.close();
  }, []);

  const reset = useCallback(() => {
    cancel();
    snapshot.current = emptyTranscript();
    samples.current = [];
    metadata.current = {};
    summary.current = null;
    setTranscript(snapshot.current);
    setServerStatus("stopped");
    setMetrics({ latencyMs: null, rtf: null });
    setError(null);
  }, [cancel]);

  const connect = useCallback(
    (topic: string, extraTerms: string) => {
      reset();
      return new Promise<void>((resolve, reject) => {
        const url = backendUrl("/ws/stream");
        url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
        url.searchParams.set("topic", topic);
        const terms = [
          ...new Set(
            extraTerms
              .split(",")
              .map((term) => term.trim())
              .filter(Boolean),
          ),
        ];
        if (terms.length) url.searchParams.set("extra_terms", terms.join(","));
        const socket = new WebSocket(url);
        const current: Connection = {
          socket,
          ready: false,
          expectedClose: false,
          stopping: false,
          resolveReady: resolve,
          rejectReady: reject,
        };
        connection.current = current;

        const rejectBeforeReady = (message: string) => {
          current.expectedClose = true;
          clearTimeout(current.readyTimer);
          current.rejectReady?.(new Error(message));
          current.rejectReady = undefined;
          current.resolveReady = undefined;
          socket.close();
        };
        current.readyTimer = window.setTimeout(() => {
          rejectBeforeReady(
            "Backend belum siap setelah 2 menit. Periksa pemuatan model lalu coba lagi.",
          );
        }, 120_000);

        const commit = (text: string, seconds: number) => {
          const previous = snapshot.current;
          if (text === previous.finalText) return;
          const append = text.startsWith(previous.finalText);
          const delta = append
            ? text.slice(previous.finalText.length).trim()
            : text;
          const segments = append ? [...previous.segments] : [];
          if (delta)
            segments.push({ id: segments.length, text: delta, seconds });
          snapshot.current = { ...previous, finalText: text, segments };
        };

        socket.onmessage = (event) => {
          if (connection.current !== current) return;
          let message: Record<string, unknown>;
          try {
            const parsed = JSON.parse(event.data);
            if (
              !parsed ||
              typeof parsed !== "object" ||
              typeof parsed.type !== "string"
            )
              return;
            message = parsed;
          } catch {
            setError("Pesan transkripsi dari backend belum dapat dibaca.");
            return;
          }
          if (message.type === "ready") {
            if (current.ready || current.stopping) return;
            if (finite(message.sample_rate) !== 16000) {
              rejectBeforeReady(
                "Sample rate backend belum sesuai dengan audio 16 kHz.",
              );
              return;
            }
            clearTimeout(current.readyTimer);
            metadata.current = {
              ...message,
              started_at: new Date().toISOString(),
            };
            current.ready = true;
            current.resolveReady?.();
            current.resolveReady = undefined;
            current.rejectReady = undefined;
          } else if (message.type === "status") {
            if (
              message.state === "listening" ||
              message.state === "processing" ||
              message.state === "stopped"
            ) {
              setServerStatus(message.state);
            }
          } else if (message.type === "transcript") {
            const seconds = finite(message.window_start_sec) ?? 0;
            const finalText =
              typeof message.committed_transcript === "string"
                ? message.committed_transcript.trim()
                : [
                    snapshot.current.finalText,
                    typeof message.final_text === "string"
                      ? message.final_text
                      : "",
                  ]
                    .filter(Boolean)
                    .join(" ")
                    .trim();
            commit(finalText, seconds);
            snapshot.current = {
              ...snapshot.current,
              partialText:
                typeof message.partial_text === "string"
                  ? message.partial_text
                  : "",
              partialSeconds: seconds,
            };
            setTranscript(snapshot.current);
            const latencyMs = finite(message.latency_ms);
            const rtf = finite(message.rtf);
            setMetrics((previous) => ({
              latencyMs: latencyMs ?? previous.latencyMs,
              rtf: rtf ?? previous.rtf,
            }));
            samples.current.push({
              received_at: new Date().toISOString(),
              latency_ms: latencyMs,
              rtf,
              window_start_sec: finite(message.window_start_sec),
              window_end_sec: finite(message.window_end_sec),
            });
          } else if (message.type === "error") {
            const text =
              typeof message.message === "string"
                ? message.message
                : "Backend belum dapat memproses audio.";
            if (!current.ready) rejectBeforeReady(text);
            else setError(text); // Backend can recover from an individual ASR step failure.
          } else if (message.type === "stopped") {
            if (typeof message.committed_transcript === "string") {
              commit(
                message.committed_transcript.trim(),
                snapshot.current.partialSeconds,
              );
            }
            snapshot.current = { ...snapshot.current, partialText: "" };
            setTranscript(snapshot.current);
            summary.current = message.summary ?? null;
            metadata.current = {
              ...metadata.current,
              stopped_at: new Date().toISOString(),
              reason: message.reason,
            };
            current.expectedClose = true;
            current.ready = false;
            setServerStatus("stopped");
            clearTimeout(current.stopTimer);
            current.resolveStop?.();
            current.resolveStop = undefined;
            current.rejectStop = undefined;
            socket.close(1000);
          }
        };
        socket.onerror = () => {
          // onclose handles both failed connections and unexpected disconnects once.
        };
        socket.onclose = () => {
          if (connection.current !== current) return;
          clearTimeout(current.readyTimer);
          clearTimeout(current.stopTimer);
          const message = current.ready
            ? "Koneksi terputus. Transkrip yang sudah diterima tetap tersimpan di layar."
            : "Tidak dapat terhubung ke backend. Pastikan server CodeTalk sudah berjalan.";
          if (current.rejectReady) {
            current.rejectReady(new Error(message));
            current.rejectReady = undefined;
          } else if (current.rejectStop) {
            current.rejectStop(
              new Error(
                "Sesi terputus sebelum transkrip terakhir dikonfirmasi. Hasil sebelumnya tetap tersedia.",
              ),
            );
            current.rejectStop = undefined;
          } else if (!current.expectedClose) {
            failureHandler.current(message);
          }
          current.ready = false;
        };
      });
    },
    [reset],
  );

  const sendAudio = useCallback((buffer: ArrayBuffer) => {
    const current = connection.current;
    if (
      !current?.ready ||
      current.stopping ||
      current.socket.readyState !== WebSocket.OPEN
    ) {
      throw new Error(
        "Koneksi audio terputus. Mulai sesi kembali setelah backend siap.",
      );
    }
    if (current.socket.bufferedAmount > 256_000) {
      throw new Error(
        "Koneksi audio terlalu lambat. Sesi dihentikan agar antrean audio tidak terus bertambah.",
      );
    }
    current.socket.send(buffer);
  }, []);

  const stop = useCallback(() => {
    const current = connection.current;
    if (!current?.ready || current.socket.readyState !== WebSocket.OPEN)
      return Promise.resolve();
    if (current.stopPromise) return current.stopPromise;
    current.stopping = true;
    current.expectedClose = true;
    current.stopPromise = new Promise<void>((resolve, reject) => {
      current.resolveStop = resolve;
      current.rejectStop = reject;
      current.stopTimer = window.setTimeout(() => {
        current.rejectStop?.(
          new Error(
            "Backend belum menyelesaikan transkrip terakhir. Hasil yang sudah diterima tetap tersedia.",
          ),
        );
        current.resolveStop = undefined;
        current.rejectStop = undefined;
        current.socket.close();
      }, 15_000);
      current.socket.send(JSON.stringify({ type: "stop" }));
    });
    return current.stopPromise;
  }, []);

  const getSessionLog = useCallback(
    () => ({
      ...metadata.current,
      transcript: snapshot.current.finalText,
      partial_transcript: snapshot.current.partialText,
      telemetry: [...samples.current],
      summary: summary.current,
    }),
    [],
  );

  useEffect(() => () => cancel(), [cancel]);
  return {
    ...transcript,
    ...metrics,
    serverStatus,
    error,
    clearError: () => setError(null),
    connect,
    sendAudio,
    stop,
    cancel,
    reset,
    getSessionLog,
  };
}
