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
