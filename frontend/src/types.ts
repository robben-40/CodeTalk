export type SessionPhase =
  "idle" | "connecting" | "recording" | "stopping" | "stopped" | "error";
export type ServerStatus = "listening" | "processing" | "stopped";
export type DisplayStatus = Exclude<SessionPhase, "recording"> | ServerStatus;

export interface Topic {
  key: string;
  label: string;
}

export interface TranscriptSegment {
  id: number;
  text: string;
  seconds: number;
}

export interface TelemetrySample {
  received_at: string;
  latency_ms: number | null;
  rtf: number | null;
  window_start_sec: number | null;
  window_end_sec: number | null;
}

export const FALLBACK_TOPICS: Topic[] = [
  { key: "general", label: "Umum / Live Coding CS" },
  { key: "data_structures", label: "Struktur Data" },
  { key: "algorithms", label: "Algoritma & Kompleksitas" },
  { key: "oop", label: "OOP" },
  { key: "databases", label: "Basis Data" },
  { key: "operating_systems", label: "Sistem Operasi" },
  { key: "computer_networks", label: "Jaringan Komputer" },
  { key: "web_backend", label: "Web & Backend" },
  { key: "software_engineering", label: "Rekayasa Perangkat Lunak" },
  { key: "machine_learning", label: "AI & Machine Learning" },
];

export function formatDuration(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds));
  const minutes = Math.floor(total / 60);
  return `${String(minutes).padStart(2, "0")}:${String(total % 60).padStart(2, "0")}`;
}
