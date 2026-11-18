import { useEffect, useRef, useState, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import { Copy, LoaderCircle, NotebookPen, Sparkles } from "lucide-react";

function CodeBlock({ children }: { children?: ReactNode }) {
  const code = useRef<HTMLPreElement>(null);
  const timer = useRef<ReturnType<typeof setTimeout>>();
  const [status, setStatus] = useState("Salin");
  useEffect(() => () => clearTimeout(timer.current), []);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(code.current?.textContent || "");
      setStatus("Tersalin");
    } catch {
      setStatus("Gagal menyalin");
    }
    clearTimeout(timer.current);
    timer.current = setTimeout(() => setStatus("Salin"), 2000);
  };
  return (
    <div className="note-code">
      <div
        className="mb-3 flex items-center justify-between gap-3 text-[13px] text-muted"
        data-no-print
      >
        <span>Contoh kode</span>
        <button
          type="button"
          onClick={() => void copy()}
          className="flex items-center gap-1.5 rounded px-1 py-1"
          aria-label="Salin kode"
        >
          <Copy size={14} aria-hidden="true" />
          <span role="status">{status}</span>
        </button>
      </div>
      <pre ref={code}>{children}</pre>
    </div>
  );
}

export function MarkdownNotes({ markdown }: { markdown: string }) {
  return (
    <div className="note-document">
      <ReactMarkdown
        skipHtml
        allowedElements={[
          "h1",
          "h2",
          "h3",
          "h4",
          "p",
          "ul",
          "ol",
          "li",
          "strong",
          "em",
          "code",
          "pre",
          "blockquote",
          "hr",
          "a",
          "br",
        ]}
        components={{
          pre: ({ children }) => <CodeBlock>{children}</CodeBlock>,
          a: ({ href, children }) => (
            <a href={href} target="_blank" rel="noreferrer">
              {children}
            </a>
          ),
        }}
      >
        {markdown}
      </ReactMarkdown>
    </div>
  );
}

export default function SmartNotesPanel({
  active,
  markdown,
  loading,
  canGenerate,
  onGenerate,
}: {
  active: boolean;
  markdown: string;
  loading: boolean;
  canGenerate: boolean;
  onGenerate: () => void;
}) {
  return (
    <section
      aria-labelledby="notes-title"
      className={`min-h-0 min-w-0 grid-rows-[auto_minmax(0,1fr)] overflow-hidden rounded-[14px] bg-white ${active ? "grid" : "hidden workspace:grid"}`}
    >
      <header className="panel-header">
        <div className="panel-heading">
          <span className="grid size-7 place-items-center rounded-lg bg-[#f0f1fd] text-accent">
            <NotebookPen size={17} aria-hidden="true" />
          </span>
          <h2 id="notes-title">Smart Notes</h2>
        </div>
        <button
          type="button"
          className="button bg-accent text-white hover:brightness-95 disabled:opacity-50"
          disabled={!canGenerate || loading}
          onClick={onGenerate}
        >
          {loading ? (
            <LoaderCircle
              size={16}
              className="motion-safe:animate-spin"
              aria-hidden="true"
            />
          ) : (
            <Sparkles size={16} aria-hidden="true" />
          )}
          {loading
            ? "Menyusun…"
            : markdown
              ? "Perbarui catatan"
              : "Buat Smart Note"}
        </button>
      </header>
      <div
        className="panel-scroll"
        role="region"
        aria-label="Isi Smart Notes"
        tabIndex={0}
        aria-busy={loading}
      >
        {markdown ? (
          <>
            <MarkdownNotes markdown={markdown} />
            {loading && (
              <p className="mt-5 text-sm text-muted" role="status">
                Memperbarui catatan…
              </p>
            )}
          </>
        ) : (
          <div className="empty-state">
            <span className="empty-icon">
              <NotebookPen size={22} aria-hidden="true" />
            </span>
            <h3>{loading ? "Menyusun catatan…" : "Catatan muncul di sini"}</h3>
            <p role={loading ? "status" : undefined}>
              {loading
                ? "Sedang merangkum penjelasan kuliah."
                : "Setelah ada transkrip final, klik Buat Smart Note di atas."}
            </p>
          </div>
        )}
      </div>
    </section>
  );
}
