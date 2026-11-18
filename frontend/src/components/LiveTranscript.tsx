import { useEffect, useRef, useState } from "react";
import { ArrowDown, Captions, LoaderCircle, Mic } from "lucide-react";
import StatusTelemetry from "./StatusTelemetry";
import {
  formatDuration,
  type DisplayStatus,
  type SessionPhase,
  type TranscriptSegment,
} from "../types";

interface Props {
  active: boolean;
  phase: SessionPhase;
  status: DisplayStatus;
  duration: number;
  segments: TranscriptSegment[];
  partial: string;
  partialSeconds: number;
  latencyMs: number | null;
  rtf: number | null;
  level: number;
  loadingTopics: boolean;
  onRecord: () => void;
}

export default function LiveTranscript(props: Props) {
  const scroll = useRef<HTMLDivElement>(null);
  const follow = useRef(true);
  const [showLatest, setShowLatest] = useState(false);
  const hasText = props.segments.length > 0 || Boolean(props.partial);
  const recording = props.phase === "recording";
  const pending = props.phase === "connecting" || props.phase === "stopping";

  useEffect(() => {
    if (follow.current && scroll.current)
      scroll.current.scrollTop = scroll.current.scrollHeight;
  }, [props.segments, props.partial, props.active]);
  useEffect(() => {
    if (!hasText) {
      follow.current = true;
      setShowLatest(false);
    }
  }, [hasText]);

  const jumpToLatest = () => {
    follow.current = true;
    setShowLatest(false);
    if (scroll.current) scroll.current.scrollTop = scroll.current.scrollHeight;
  };

  return (
    <section
      aria-labelledby="transcript-title"
      className={`min-h-0 min-w-0 grid-rows-[auto_minmax(0,1fr)_auto] overflow-hidden rounded-[14px] bg-white ${props.active ? "grid" : "hidden workspace:grid"}`}
    >
      <header className="panel-header">
        <div className="panel-heading">
          <Captions size={18} className="text-slate-400" aria-hidden="true" />
          <h2 id="transcript-title">Live Transcript</h2>
          <time
            className="ml-1 font-mono text-xs text-muted tabular-nums"
            aria-label="Durasi rekaman"
          >
            {formatDuration(props.duration)}
          </time>
        </div>
        <button
          type="button"
          className="button bg-[#d33d45] text-white hover:bg-[#bf3039] disabled:opacity-60"
          onClick={props.onRecord}
          disabled={props.phase === "stopping" || props.loadingTopics}
        >
          {pending ? (
            <LoaderCircle
              size={15}
              className="motion-safe:animate-spin"
              aria-hidden="true"
            />
          ) : (
            <span
              className={`size-2.5 bg-white ${recording ? "rounded-sm" : "rounded-full"}`}
              aria-hidden="true"
            />
          )}
          {props.phase === "connecting"
            ? "Batalkan"
            : props.phase === "stopping"
              ? "Menyelesaikan…"
              : recording
                ? "Akhiri rekaman"
                : "Mulai rekam"}
        </button>
      </header>
      <div className="relative min-h-0">
        <div
          ref={scroll}
          className="panel-scroll h-full"
          role="region"
          aria-label="Isi transkrip"
          tabIndex={0}
          onScroll={() => {
            const element = scroll.current!;
            const nearBottom =
              element.scrollHeight - element.scrollTop - element.clientHeight <
              70;
            follow.current = nearBottom;
            setShowLatest(!nearBottom && hasText);
          }}
        >
          {hasText ? (
            <>
              {props.segments.map((segment) => (
                <article key={segment.id} className="utterance">
                  <time>{formatDuration(segment.seconds)}</time>
                  <p>{segment.text}</p>
                </article>
              ))}
              {props.partial && (
                <article className="utterance rounded-xl bg-[#f6f7fd] p-3.5">
                  <time>{formatDuration(props.partialSeconds)}</time>
                  <div>
                    <span className="mb-1 block text-xs font-medium text-accent">
                      Sementara
                    </span>
                    <p className="italic !text-muted">
                      {props.partial}
                      <span
                        className="ml-1 inline-block h-4 w-0.5 bg-accent align-middle"
                        aria-hidden="true"
                      />
                    </p>
                  </div>
                </article>
              )}
            </>
          ) : (
            <div className="empty-state">
              <span className="empty-icon">
                <Mic size={21} aria-hidden="true" />
              </span>
              <h3>
                {props.phase === "connecting"
                  ? "Menyiapkan sesi…"
                  : props.phase === "recording"
                    ? "Mendengarkan…"
                    : props.phase === "error"
                      ? "Sesi belum dapat dilanjutkan"
                      : "Siap mengikuti kuliah?"}
              </h3>
              <p>
                {props.phase === "connecting"
                  ? "Tunggu hingga model dan mikrofon siap."
                  : props.phase === "recording"
                    ? "Transkrip akan muncul saat ada ucapan."
                    : "Pilih konteks mata kuliah, lalu mulai merekam."}
              </p>
            </div>
          )}
        </div>
        {showLatest && (
          <button
            type="button"
            onClick={jumpToLatest}
            className="absolute right-4 bottom-3 flex items-center gap-2 rounded-full bg-accent px-3 py-2 text-sm text-white shadow-md"
          >
            <ArrowDown size={15} aria-hidden="true" />
            Ke teks terbaru
          </button>
        )}
      </div>
      <StatusTelemetry
        status={props.status}
        latencyMs={props.latencyMs}
        rtf={props.rtf}
        level={props.level}
      />
    </section>
  );
}
