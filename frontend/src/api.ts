import type { Topic } from "./types";

export function backendUrl(path: string): URL {
  return new URL(
    path,
    import.meta.env.VITE_BACKEND_URL || window.location.origin,
  );
}

export async function fetchTopics(
  signal: AbortSignal,
): Promise<{ topics: Topic[]; defaultTopic: string }> {
  const response = await fetch(backendUrl("/topics"), { signal });
  if (!response.ok)
    throw new Error(
      "Daftar mata kuliah belum dapat dimuat. Menggunakan daftar bawaan.",
    );
  const data = await response.json();
  const topics: Topic[] = Array.isArray(data.topics)
    ? data.topics.filter(
        (topic: Topic) =>
          typeof topic?.key === "string" && typeof topic?.label === "string",
      )
    : [];
  if (topics.length === 0)
    throw new Error(
      "Daftar mata kuliah belum dapat dibaca. Menggunakan daftar bawaan.",
    );
  return {
    topics,
    defaultTopic: topics.some((topic) => topic.key === data.default_topic)
      ? data.default_topic
      : topics[0].key,
  };
}

// Kontrak frontend untuk Orang 4; router backend saat ini belum diimplementasikan.
export async function requestSmartNotes(
  transcript: string,
  topic: string,
  signal: AbortSignal,
): Promise<string> {
  const response = await fetch(backendUrl("/api/notes"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ transcript, topic }),
    signal,
  });
  if (response.status === 404 || response.status === 501) {
    throw new Error(
      "Layanan Smart Notes belum tersedia pada backend. Transkrip tetap dapat digunakan dan diekspor.",
    );
  }
  if (!response.ok)
    throw new Error(
      "Smart Notes gagal dibuat. Periksa layanan catatan lalu coba lagi.",
    );
  const data = await response.json();
  if (!data || typeof data.markdown !== "string" || !data.markdown.trim()) {
    throw new Error(
      "Catatan dari backend belum dapat dibaca. Coba lagi setelah layanan catatan siap.",
    );
  }
  return data.markdown;
}

export interface UploadTranscriptionSegment {
  start: number;
  end: number;
  text: string;
}

export interface UploadTranscriptionResponse {
  text: string;
  segments: UploadTranscriptionSegment[];
  language: string;
  audio_duration_sec: number;
  processing_time_sec: number;
  latency_ms: number;
  rtf: number;
  topic: string;
  model_size: string;
  filename: string;
}

export async function transcribeAudioFile(
  file: File,
  topic: string,
  extraTerms: string,
  signal?: AbortSignal,
): Promise<UploadTranscriptionResponse> {
  const url = backendUrl("/api/transcribe-audio");
  url.searchParams.set("topic", topic);
  url.searchParams.set("filename", file.name);
  const terms = [
    ...new Set(
      extraTerms
        .split(",")
        .map((term) => term.trim())
        .filter(Boolean),
    ),
  ];
  if (terms.length) url.searchParams.set("extra_terms", terms.join(","));

  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": file.type || "application/octet-stream",
    },
    body: file,
    signal,
  });

  if (!response.ok) {
    let detail = "Gagal mentranskrip file audio. Periksa format file lalu coba lagi.";
    try {
      const errData = await response.json();
      if (typeof errData?.detail === "string" && errData.detail.trim()) {
        detail = errData.detail;
      }
    } catch {
      /* Gunakan pesan default jika body bukan JSON. */
    }
    throw new Error(detail);
  }

  return (await response.json()) as UploadTranscriptionResponse;
}

export function downloadText(
  text: string,
  filename: string,
  type: string,
): void {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
