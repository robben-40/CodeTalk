import { Mic } from "lucide-react";
import type { DisplayStatus } from "../types";

const labels: Record<DisplayStatus, string> = {
  idle: "Siap",
  connecting: "Menyiapkan",
  listening: "Listening",
  processing: "Processing",
  stopping: "Menyelesaikan",
  stopped: "Stopped",
  error: "Terhenti",
};

export default function StatusTelemetry({
  status,
  latencyMs,
  rtf,
  level,
}: {
  status: DisplayStatus;
  latencyMs: number | null;
  rtf: number | null;
  level: number;
}) {
  const active = status === "listening" || status === "processing";
  const color =
    status === "error"
      ? "text-red-700"
      : active
        ? "text-emerald-700"
        : "text-muted";
  return (
    <footer className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2 bg-white px-4 pt-3 pb-4 text-[13px] text-muted sm:px-5">
      <div className="flex items-center gap-2">
        <div
          className="flex h-6 items-center gap-[3px] text-accent"
          aria-hidden="true"
        >
          <Mic size={15} className="mr-1" />
          {[0.4, 0.7, 0.5, 1, 0.6, 0.8].map((height, index) => (
            <span
              key={index}
              className="hidden w-[3px] rounded-full bg-current opacity-60 sm:block"
              style={{
                height: active ? `${3 + level * height * 23}px` : "3px",
              }}
            />
          ))}
        </div>
        <span className={`flex items-center gap-1.5 ${color}`} role="status">
          <span
            className="size-1.5 rounded-full bg-current"
            aria-hidden="true"
          />
          {labels[status]}
        </span>
      </div>
      <span>
        Latency{" "}
        <strong
          className={`ml-1 font-medium tabular-nums ${latencyMs !== null && latencyMs > 1500 ? "text-amber-700" : "text-ink"}`}
        >
          {latencyMs === null ? "—" : `${Math.round(latencyMs)} ms`}
        </strong>
      </span>
      <span title="Real-Time Factor: di bawah 1 berarti pemrosesan lebih cepat daripada durasi audio.">
        RTF{" "}
        <strong
          className={`ml-1 font-medium tabular-nums ${rtf !== null && rtf >= 1 ? "text-amber-700" : "text-ink"}`}
        >
          {rtf === null ? "—" : rtf.toFixed(2)}
        </strong>
      </span>
    </footer>
  );
}
