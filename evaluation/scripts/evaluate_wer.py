"""Hitung WER & CER per sampel dan per kondisi (Baseline vs Eksperimen).
WER = (S + D + I) / N
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path


EVAL_DIR = Path(__file__).resolve().parents[1]
DEFAULT_REFS = EVAL_DIR / "ground_truth" / "references.json"
DEFAULT_OUT = EVAL_DIR / "results"
DEFAULT_SESSIONS_DIR = DEFAULT_OUT / "sessions"
DEFAULT_MANIFEST = DEFAULT_OUT / "sessions_manifest.json"
BASELINE = "baseline_clean"


def normalize(text: str) -> str:
    """Lowercase, buang tanda baca, rapikan spasi (diterapkan ke reference & hypothesis)."""
    text = re.sub(r"[^\w\s]", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def align(ref: list[str], hyp: list[str]) -> list[tuple[str, str | None, str | None]]:
    """Alignment Levenshtein. Return list (op, ref_word, hyp_word); op = C/S/D/I."""
    n, m = len(ref), len(hyp)
    d = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        d[i][0] = i
    for j in range(1, m + 1):
        d[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            cost = 0 if ref[i - 1] == hyp[j - 1] else 1
            d[i][j] = min(d[i - 1][j - 1] + cost, d[i - 1][j] + 1, d[i][j - 1] + 1)

    ops: list[tuple[str, str | None, str | None]] = []
    i, j = n, m
    while i > 0 or j > 0:
        if i > 0 and j > 0 and d[i][j] == d[i - 1][j - 1] + (0 if ref[i - 1] == hyp[j - 1] else 1):
            ops.append(("C" if ref[i - 1] == hyp[j - 1] else "S", ref[i - 1], hyp[j - 1]))
            i, j = i - 1, j - 1
        elif i > 0 and d[i][j] == d[i - 1][j] + 1:
            ops.append(("D", ref[i - 1], None))
            i -= 1
        else:
            ops.append(("I", None, hyp[j - 1]))
            j -= 1
    ops.reverse()
    return ops


def edit_distance(a: str, b: str) -> int:
    """Levenshtein dengan memori O(len(b)); dipakai untuk CER."""
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j - 1] + (ca != cb), prev[j] + 1, cur[j - 1] + 1))
        prev = cur
    return prev[-1]


def score(reference: str, hypothesis: str) -> dict:
    ref_n, hyp_n = normalize(reference), normalize(hypothesis)
    ops = align(ref_n.split(), hyp_n.split())
    s = sum(op == "S" for op, _, _ in ops)
    d = sum(op == "D" for op, _, _ in ops)
    i = sum(op == "I" for op, _, _ in ops)
    c = sum(op == "C" for op, _, _ in ops)
    n = s + d + c  # jumlah kata referensi
    cer_den = len(ref_n.replace(" ", ""))
    cer = edit_distance(ref_n.replace(" ", ""), hyp_n.replace(" ", "")) / cer_den if cer_den else 0.0
    return {"S": s, "D": d, "I": i, "C": c, "N": n, "WER": (s + d + i) / n if n else 0.0, "CER": cer}


def load_texts(path: Path) -> dict[str, dict]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    out: dict[str, dict] = {}
    for sid, val in data.items():
        text = val.get("text", "") if isinstance(val, dict) else str(val)
        cond = val.get("condition") if isinstance(val, dict) else None
        out[sid] = {"text": text, "condition": cond or (sid.split("/")[0] if "/" in sid else "default")}
    return out


@dataclass
class Session:
    folder: Path
    session_id: str
    started_at: str
    topic: str
    sample_id: str | None
    condition: str

    @property
    def name(self) -> str:
        return self.folder.name

    def transcript(self) -> str:
        path = self.folder / "transcript.txt"
        return path.read_text(encoding="utf-8").strip() if path.exists() else ""


def load_manifest(path: Path | None) -> dict:
    if path and Path(path).exists():
        return json.loads(Path(path).read_text(encoding="utf-8"))
    return {}


def list_session_dirs(root: Path) -> list[Path]:
    root = Path(root)
    if (root / "session.json").exists():  # root itu sendiri satu sesi
        return [root]
    if not root.is_dir():
        return []
    return sorted(p for p in root.iterdir() if p.is_dir() and (p / "session.json").exists())


def load_session(folder: Path, manifest: dict) -> Session:
    info = json.loads((folder / "session.json").read_text(encoding="utf-8"))
    config = info.get("config") or {}
    entry = manifest.get(folder.name) or manifest.get(info.get("session_id", ""))

    sample_id = condition = None
    if isinstance(entry, dict):
        sample_id, condition = entry.get("sample_id"), entry.get("condition")
    elif isinstance(entry, str):
        sample_id = entry
    sample_id = sample_id or config.get("sample_id")
    if not condition:
        condition = config.get("condition") or (
            sample_id.split("/")[0] if sample_id and "/" in sample_id else "unlabeled"
        )
    return Session(
        folder=folder,
        session_id=info.get("session_id", ""),
        started_at=info.get("started_at", ""),
        topic=info.get("topic", ""),
        sample_id=sample_id,
        condition=condition,
    )


def load_sessions(paths: list[Path], manifest_path: Path | None = None) -> list[Session]:
    manifest = load_manifest(manifest_path)
    sessions: list[Session] = []
    for p in paths:
        sessions += [load_session(f, manifest) for f in list_session_dirs(p)]
    return sorted(sessions, key=lambda s: s.started_at)


def hypotheses_from_sessions(sessions_dir: Path, manifest_path: Path | None = None) -> dict[str, dict]:
    """Bentuk {sample_id: {"text", "condition"}} dari sesi yang sudah dipetakan.
    Jika satu sampel punya beberapa sesi, dipakai sesi TERBARU."""
    sessions = load_sessions([sessions_dir], manifest_path)
    if not sessions:
        print(f"[warn] tidak ada folder sesi di {sessions_dir}", file=sys.stderr)
    out: dict[str, dict] = {}
    for s in sessions:  # sudah urut dari yang terlama
        if not s.sample_id:
            print(f"[warn] sesi {s.name} belum dipetakan ke sample_id (lihat sessions_manifest.json)", file=sys.stderr)
            continue
        if s.sample_id in out:
            print(f"[warn] {s.sample_id} punya >1 sesi; memakai yang terbaru ({s.name})", file=sys.stderr)
        out[s.sample_id] = {"text": s.transcript(), "condition": s.condition}
    return out


def init_manifest(sessions_dir: Path, manifest_path: Path) -> None:
    existing = load_manifest(manifest_path)
    sessions = load_sessions([sessions_dir], manifest_path)
    if not sessions:
        print(f"Tidak ada folder sesi di {sessions_dir}")
        return
    manifest = dict(existing)
    for s in sessions:
        manifest.setdefault(s.name, None)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"{'Folder sesi':<34}{'Topik':<12}{'Mulai':<22}{'Karakter':>9}  Sample ID")
    for s in sessions:
        print(f"{s.name:<34}{s.topic:<12}{s.started_at:<22}{len(s.transcript()):>9}  {s.sample_id or '(isi manual)'}")
    print(f"\nManifest ditulis ke {manifest_path}. Ganti nilai null dengan ID sampel, mis. \"baseline_clean/s01\".")


def add_hypothesis_args(ap: argparse.ArgumentParser) -> None:
    ap.add_argument("--hypotheses", type=Path, help="JSON hypothesis; jika kosong dibaca dari --sessions-dir")
    ap.add_argument("--sessions-dir", type=Path, default=DEFAULT_SESSIONS_DIR)
    ap.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    ap.add_argument("--init-manifest", action="store_true", help="Buat/lengkapi sessions_manifest.json lalu keluar")


def get_hypotheses(args: argparse.Namespace) -> dict[str, dict]:
    if args.hypotheses:
        return load_texts(args.hypotheses)
    return hypotheses_from_sessions(args.sessions_dir, args.manifest)


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--references", type=Path, default=DEFAULT_REFS)
    add_hypothesis_args(ap)
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    if args.init_manifest:
        init_manifest(args.sessions_dir, args.manifest)
        return 0

    refs, hyps = load_texts(args.references), get_hypotheses(args)
    for sid in sorted(set(refs) - set(hyps)):
        print(f"[warn] tidak ada hypothesis untuk: {sid}", file=sys.stderr)
    ids = sorted(set(refs) & set(hyps))
    if not ids:
        print("Tidak ada ID yang cocok antara references dan hypotheses.", file=sys.stderr)
        return 1

    per_sample, groups = [], defaultdict(lambda: {"S": 0, "D": 0, "I": 0, "N": 0, "cer": [], "samples": 0})
    for sid in ids:
        sc = score(refs[sid]["text"], hyps[sid]["text"])
        cond = refs[sid]["condition"]
        per_sample.append({"id": sid, "condition": cond, **{k: sc[k] for k in ("N", "S", "D", "I")},
                           "WER": round(sc["WER"], 4), "CER": round(sc["CER"], 4)})
        g = groups[cond]
        for k in ("S", "D", "I", "N"):
            g[k] += sc[k]
        g["cer"].append(sc["CER"])
        g["samples"] += 1

    summary = []
    for cond, g in sorted(groups.items()):
        wer = (g["S"] + g["D"] + g["I"]) / g["N"] if g["N"] else 0.0
        summary.append({"condition": cond, "samples": g["samples"], "N": g["N"], "S": g["S"], "D": g["D"],
                        "I": g["I"], "WER": round(wer, 4), "CER_mean": round(sum(g["cer"]) / len(g["cer"]), 4)})

    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.out_dir / "wer_per_sample.csv", per_sample)
    write_csv(args.out_dir / "wer_summary.csv", summary)

    base = next((r["WER"] for r in summary if r["condition"] == BASELINE), None)
    print(f"{'Kondisi':<22}{'Sampel':>7}{'N':>7}{'S':>5}{'D':>5}{'I':>5}{'WER':>9}{'CER':>9}{'ΔWER':>9}")
    for r in summary:
        delta = f"{(r['WER'] - base) * 100:+.1f}pp" if base is not None and r["condition"] != BASELINE else "-"
        print(f"{r['condition']:<22}{r['samples']:>7}{r['N']:>7}{r['S']:>5}{r['D']:>5}{r['I']:>5}"
              f"{r['WER'] * 100:>8.1f}%{r['CER_mean'] * 100:>8.1f}%{delta:>9}")
    print(f"\nTersimpan di: {args.out_dir}/wer_per_sample.csv dan wer_summary.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
