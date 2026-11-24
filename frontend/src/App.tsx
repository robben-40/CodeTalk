import { useCallback, useEffect, useRef, useState } from "react";
import { AlertCircle, RotateCw, X } from "lucide-react";
import HeaderBar from "./components/HeaderBar";
import LiveTranscript from "./components/LiveTranscript";
import SmartNotesPanel, { MarkdownNotes } from "./components/SmartNotesPanel";
import { audioErrorMessage, useAudioStream } from "./hooks/useAudioStream";
import { useWebSocketASR } from "./hooks/useWebSocketASR";
import {
  downloadText,
  fetchTopics,
  requestSmartNotes,
  transcribeAudioFile,
} from "./api";
import {
  FALLBACK_TOPICS,
  type DisplayStatus,
  type SessionPhase,
  type Topic,
} from "./types";

export default function App() {
  const [phase, setPhaseState] = useState<SessionPhase>("idle");
  const phaseRef = useRef<SessionPhase>("idle");
  const [topics, setTopics] = useState<Topic[]>(FALLBACK_TOPICS);
  const [topic, setTopic] = useState("general");
  const [sessionTopic, setSessionTopic] = useState("general");
  const [extraTerms, setExtraTerms] = useState("");
  const [loadingTopics, setLoadingTopics] = useState(true);
  const [topicsError, setTopicsError] = useState<string | null>(null);
  const [topicReload, setTopicReload] = useState(0);
  const topicSelected = useRef(false);
  const [view, setView] = useState<"transcript" | "notes">("transcript");
  const [notes, setNotes] = useState("");
  const [generating, setGenerating] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadDuration, setUploadDuration] = useState<number | null>(null);
  const [uiError, setUiError] = useState<string | null>(null);
  const mounted = useRef(true);
  const operation = useRef(0);
  const noteRequest = useRef(0);
  const notesAbort = useRef<AbortController | null>(null);
  const uploadAbort = useRef<AbortController | null>(null);
  const failureHandler = useRef<(message: string) => void>(() => {});
  const audio = useAudioStream();
  const asr = useWebSocketASR((message) => failureHandler.current(message));
  const busy =
    uploading ||
    phase === "connecting" ||
    phase === "recording" ||
    phase === "stopping";
  const setPhase = useCallback((next: SessionPhase) => {
    phaseRef.current = next;
    if (mounted.current) setPhaseState(next);
  }, []);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      operation.current++;
      noteRequest.current++;
      notesAbort.current?.abort();
      uploadAbort.current?.abort();
    };
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    let cancelled = false;
    const timeout = window.setTimeout(() => controller.abort(), 8000);
    setLoadingTopics(true);
    setTopicsError(null);
    fetchTopics(controller.signal)
      .then((data) => {
        if (cancelled) return;
        setTopics(data.topics);
        setTopic((current) =>
          topicSelected.current &&
          data.topics.some((entry) => entry.key === current)
            ? current
            : data.defaultTopic,
        );
      })
      .catch(() => {
        if (!cancelled)
          setTopicsError(
            "Daftar mata kuliah belum dapat dimuat dari server. Daftar bawaan ditampilkan.",
          );
      })
      .finally(() => {
        clearTimeout(timeout);
        if (!cancelled) setLoadingTopics(false);
      });
    return () => {
      cancelled = true;
      clearTimeout(timeout);
      controller.abort();
    };
  }, [topicReload]);

  const finishSession = async (failure?: string) => {
    if (phaseRef.current === "stopping" || !mounted.current) return;
    const ticket = ++operation.current;
    setPhase("stopping");
    let message = failure;
    try {
      await audio.stop();
    } catch (error) {
      message ||= audioErrorMessage(error);
    }
    // AudioWorklet flushes its last short PCM frame before this stop message.
    try {
      await asr.stop();
    } catch (error) {
      message ||= audioErrorMessage(error);
    }
    if (!mounted.current || ticket !== operation.current) return;
    setUiError(message || null);
    setPhase(message ? "error" : "stopped");
  };
  failureHandler.current = (message) => {
    void finishSession(message);
  };

  const startSession = async () => {
    if (busy || loadingTopics) return;
    const ticket = ++operation.current;
    notesAbort.current?.abort();
    noteRequest.current++;
    setGenerating(false);
    setNotes("");
    setUploadDuration(null);
    setSessionTopic(topic);
    setUiError(null);
    setView("transcript");
    setPhase("connecting");
    try {
      await audio.prepare();
      if (ticket !== operation.current) return;
      await asr.connect(topic, extraTerms);
      if (ticket !== operation.current) return;
      await audio.start(asr.sendAudio, (message) =>
        failureHandler.current(message),
      );
      if (mounted.current && ticket === operation.current)
        setPhase("recording");
    } catch (error) {
      if (!mounted.current || ticket !== operation.current) return;
      asr.cancel();
      try {
        await audio.stop();
      } catch {
        /* Preserve the original connection or microphone error. */
      }
      if (!mounted.current || ticket !== operation.current) return;
      setUiError(audioErrorMessage(error));
      setPhase("error");
    }
  };

  const record = async () => {
    if (phaseRef.current === "connecting") {
      operation.current++;
      setPhase("stopping");
      asr.cancel();
      await audio.stop();
      if (mounted.current) setPhase("idle");
    } else if (phaseRef.current === "recording") {
      await finishSession();
    } else if (phaseRef.current !== "stopping") {
      await startSession();
    }
  };

  const newSession = () => {
    if (busy) return;
    operation.current++;
    noteRequest.current++;
    notesAbort.current?.abort();
    uploadAbort.current?.abort();
    asr.reset();
    audio.reset();
    setNotes("");
    setGenerating(false);
    setUploadDuration(null);
    setExtraTerms("");
    setUiError(null);
    setView("transcript");
    setPhase("idle");
  };

  const handleUploadAudio = async (file: File) => {
    if (busy || loadingTopics) return;
    const ticket = ++operation.current;
    notesAbort.current?.abort();
    noteRequest.current++;
    uploadAbort.current?.abort();
    const controller = new AbortController();
    uploadAbort.current = controller;
    setGenerating(false);
    setNotes("");
    setUploadDuration(null);
    setSessionTopic(topic);
    setUiError(null);
    setView("transcript");
    asr.reset();
    audio.reset();
    setUploading(true);
    try {
      const result = await transcribeAudioFile(
        file,
        topic,
        extraTerms,
        controller.signal,
      );
      if (!mounted.current || ticket !== operation.current) return;
      asr.loadUploadedResult(result);
      setUploadDuration(result.audio_duration_sec);
      setPhase("stopped");
    } catch (error) {
      if (!mounted.current || ticket !== operation.current) return;
      setUiError(audioErrorMessage(error));
      setPhase("error");
    } finally {
      if (mounted.current && ticket === operation.current) {
        setUploading(false);
      }
    }
  };

  const generateNotes = async () => {
    if (
      !asr.finalText.trim() ||
      generating ||
      phaseRef.current === "connecting" ||
      phaseRef.current === "stopping"
    )
      return;
    const ticket = ++noteRequest.current;
    const controller = new AbortController();
    notesAbort.current?.abort();
    notesAbort.current = controller;
    const timeout = window.setTimeout(() => controller.abort(), 60_000);
    setUiError(null);
    setGenerating(true);
    setView("notes");
    try {
      const markdown = await requestSmartNotes(
        asr.finalText,
        sessionTopic,
        controller.signal,
      );
      if (mounted.current && ticket === noteRequest.current) setNotes(markdown);
    } catch (error) {
      if (mounted.current && ticket === noteRequest.current) {
        setUiError(
          controller.signal.aborted
            ? "Pembuatan catatan terlalu lama. Coba lagi."
            : audioErrorMessage(error),
        );
      }
    } finally {
      clearTimeout(timeout);
      if (mounted.current && ticket === noteRequest.current)
        setGenerating(false);
    }
  };

  const exportSession = (kind: "transcript" | "notes" | "metrics") => {
    const filename = `codetalk-${new Date().toISOString().replace(/[:.]/g, "-")}`;
    if (kind === "notes") {
      if (notes && !busy) window.print();
    } else if (kind === "transcript") {
      const text =
        asr.finalText +
        (asr.partialText
          ? `\n\n[Transkrip sementara — belum final]\n${asr.partialText}`
          : "");
      downloadText(text, `${filename}.txt`, "text/plain;charset=utf-8");
    } else {
      downloadText(
        JSON.stringify(asr.getSessionLog(), null, 2),
        `${filename}.json`,
        "application/json",
      );
    }
  };

  const error = uiError || asr.error || topicsError;
  const status: DisplayStatus = uploading
    ? "processing"
    : phase === "recording"
      ? asr.serverStatus === "processing"
        ? "processing"
        : "listening"
      : phase;
  const topicLabel =
    topics.find((entry) => entry.key === sessionTopic)?.label || sessionTopic;

  return (
    <>
      <div className="app-shell grid h-dvh min-h-[600px] grid-rows-[auto_minmax(0,1fr)] bg-canvas text-ink">
        <div className="relative z-20 bg-white">
          <HeaderBar
            topics={topics}
            topic={topic}
            extraTerms={extraTerms}
            busy={busy}
            loadingTopics={loadingTopics}
            hasTranscript={Boolean(asr.finalText || asr.partialText)}
            hasNotes={Boolean(notes)}
            onTopicChange={(value) => {
              topicSelected.current = true;
              setTopic(value);
            }}
            onTermsChange={setExtraTerms}
            onNewSession={newSession}
            onExport={exportSession}
          />
          {error && (
            <div
              className="mx-4 mb-3 flex flex-wrap items-center gap-2.5 rounded-lg bg-red-50 px-3 py-2.5 text-sm text-red-800 sm:mx-6"
              role="alert"
            >
              <AlertCircle size={18} className="shrink-0" aria-hidden="true" />
              <p className="min-w-0 flex-1">{error}</p>
              {error === topicsError && (
                <button
                  type="button"
                  className="flex items-center gap-1.5 rounded px-2 py-1 font-medium"
                  onClick={() => setTopicReload((value) => value + 1)}
                >
                  <RotateCw size={15} aria-hidden="true" />
                  Coba lagi
                </button>
              )}
              <button
                type="button"
                className="rounded p-1"
                aria-label="Tutup pesan"
                onClick={() => {
                  setUiError(null);
                  asr.clearError();
                  setTopicsError(null);
                }}
              >
                <X size={17} aria-hidden="true" />
              </button>
            </div>
          )}
          <nav
            aria-label="Pilih panel sesi"
            className="flex gap-2 px-4 pb-3 workspace:hidden sm:px-6"
          >
            {(["transcript", "notes"] as const).map((panel) => (
              <button
                key={panel}
                type="button"
                aria-pressed={view === panel}
                aria-controls={
                  panel === "transcript" ? "transcript-title" : "notes-title"
                }
                className={`flex-1 rounded-lg px-3 py-2 text-sm ${view === panel ? "bg-[#eef0fd] font-semibold text-accent" : "text-muted"}`}
                onClick={() => setView(panel)}
              >
                {panel === "transcript" ? "Transkrip" : "Smart Notes"}
              </button>
            ))}
          </nav>
        </div>
        <main className="grid min-h-0 grid-cols-1 gap-3 p-2.5 workspace:grid-cols-2 sm:p-3">
          <LiveTranscript
            active={view === "transcript"}
            phase={phase}
            status={status}
            duration={uploadDuration ?? audio.duration}
            segments={asr.segments}
            partial={asr.partialText}
            partialSeconds={asr.partialSeconds}
            latencyMs={asr.latencyMs}
            rtf={asr.rtf}
            level={audio.level}
            loadingTopics={loadingTopics}
            uploading={uploading}
            onRecord={() => void record()}
            onUploadAudio={(file) => void handleUploadAudio(file)}
          />
          <SmartNotesPanel
            active={view === "notes"}
            markdown={notes}
            loading={generating}
            canGenerate={
              Boolean(asr.finalText.trim()) &&
              !uploading &&
              phase !== "connecting" &&
              phase !== "stopping"
            }
            onGenerate={() => void generateNotes()}
          />
        </main>
      </div>
      <article className="print-notes">
        <header>
          <h1>Smart Notes</h1>
          <p>{topicLabel}</p>
        </header>
        <MarkdownNotes markdown={notes} />
      </article>
    </>
  );
}
