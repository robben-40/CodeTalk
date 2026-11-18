import { useEffect, useRef } from "react";
import { AudioLines, ChevronDown, Download } from "lucide-react";
import type { Topic } from "../types";

interface Props {
  topics: Topic[];
  topic: string;
  extraTerms: string;
  busy: boolean;
  loadingTopics: boolean;
  hasTranscript: boolean;
  hasNotes: boolean;
  onTopicChange: (topic: string) => void;
  onTermsChange: (terms: string) => void;
  onNewSession: () => void;
  onExport: (kind: "transcript" | "notes" | "metrics") => void;
}

export default function HeaderBar(props: Props) {
  const menu = useRef<HTMLDetailsElement>(null);
  useEffect(() => {
    const closeOutside = (event: PointerEvent) => {
      if (menu.current && !menu.current.contains(event.target as Node))
        menu.current.open = false;
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape" && menu.current?.open) {
        menu.current.open = false;
        menu.current.querySelector("summary")?.focus();
      }
    };
    document.addEventListener("pointerdown", closeOutside);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("pointerdown", closeOutside);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, []);

  const exportFile = (kind: "transcript" | "notes" | "metrics") => {
    if (menu.current) menu.current.open = false;
    props.onExport(kind);
  };

  return (
    <header className="relative z-20 shrink-0 bg-white">
      <div className="flex items-center justify-between gap-3 px-4 pt-5 pb-4 sm:px-6">
        <div
          className="flex items-center gap-2.5 text-2xl font-semibold tracking-tight"
          aria-label="CodeTalk"
        >
          <span className="grid size-8 place-items-center rounded-xl bg-accent text-white">
            <AudioLines size={22} aria-hidden="true" />
          </span>
          <span className="hidden min-[521px]:inline">
            CodeTalk<span className="text-accent">.</span>
          </span>
        </div>
        <div className="flex items-center gap-2.5" aria-label="Aksi sesi">
          <button
            type="button"
            className="button button-new"
            disabled={props.busy}
            onClick={props.onNewSession}
            title={
              props.busy
                ? "Akhiri rekaman untuk membuat sesi baru."
                : "Siapkan sesi baru."
            }
          >
            <span className="text-2xl leading-5 font-medium" aria-hidden="true">
              +
            </span>
            <span>Sesi baru</span>
          </button>
          <details ref={menu} className="relative">
            <summary className="button cursor-pointer list-none bg-[#191b20] text-white hover:bg-[#30333a] [&::-webkit-details-marker]:hidden">
              <Download size={17} aria-hidden="true" />
              <span>Ekspor</span>
              <ChevronDown size={14} aria-hidden="true" />
            </summary>
            <div className="absolute right-0 top-full z-30 mt-2 w-60 rounded-xl border border-slate-100 bg-white p-1.5 shadow-xl shadow-slate-900/10">
              <button
                className="export-item"
                disabled={!props.hasTranscript}
                onClick={() => exportFile("transcript")}
              >
                Transkrip <span>.txt</span>
              </button>
              <button
                className="export-item"
                disabled={!props.hasNotes || props.busy}
                title={
                  props.busy
                    ? "Akhiri rekaman sebelum menyimpan PDF."
                    : "Buka dialog cetak, lalu pilih Simpan sebagai PDF."
                }
                onClick={() => exportFile("notes")}
              >
                Smart Notes <span>.pdf</span>
              </button>
              <button
                className="export-item"
                disabled={!props.hasTranscript}
                onClick={() => exportFile("metrics")}
              >
                Metrik sesi <span>.json</span>
              </button>
            </div>
          </details>
        </div>
      </div>
      <section
        aria-labelledby="context-title"
        className="px-4 pt-1 pb-5 sm:px-6"
      >
        <h1
          id="context-title"
          className="mb-4 text-[23px] leading-snug font-semibold tracking-tight sm:text-[25px]"
        >
          Konteks mata kuliah
        </h1>
        <div className="grid grid-cols-2 items-start gap-3 sm:gap-5">
          <label className="context-field">
            <span id="course-label">Mata kuliah</span>
            <select
              aria-labelledby="course-label"
              aria-describedby="course-help"
              value={props.topic}
              disabled={props.busy || props.loadingTopics}
              onChange={(event) => props.onTopicChange(event.target.value)}
            >
              {props.topics.map((topic) => (
                <option key={topic.key} value={topic.key}>
                  {topic.label}
                </option>
              ))}
            </select>
            <small id="course-help">
              {props.loadingTopics
                ? "Memuat daftar mata kuliah…"
                : props.busy
                  ? "Akhiri rekaman untuk mengubah konteks."
                  : "Pilih sesuai materi kuliah."}
            </small>
          </label>
          <label className="context-field">
            <span id="terms-label">
              Istilah tambahan{" "}
              <small className="ml-1.5 max-[520px]:ml-0 max-[520px]:block">
                opsional
              </small>
            </span>
            <input
              type="text"
              value={props.extraTerms}
              disabled={props.busy}
              onChange={(event) => props.onTermsChange(event.target.value)}
              placeholder="Contoh: sentinel node, ListNode"
              aria-labelledby="terms-label"
              aria-describedby="terms-help"
            />
            <small id="terms-help">Boleh kosong. Pisahkan dengan koma.</small>
          </label>
        </div>
      </section>
    </header>
  );
}
