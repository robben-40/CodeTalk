"""Ringkas latency & RTF dari folder sesi session_logger, dikelompokkan per kondisi.

Sumber: <folder sesi>/latency.csv (kolom dari LatencyTracker). Tiga ukuran dilaporkan TERPISAH
(sesuai catatan di latency_tracker.py, jangan dicampur di laporan):
  server_e2e_ms  : latency sisi server; pembanding target PRD 1,0-1,5 s.
                   Belum termasuk buffering browser, jaringan localhost, dan render UI.
  asr_latency_ms : waktu inferensi engine per jendela.
  rtf            : asr_latency / durasi jendela. Syarat PRD: < 1,0.
Secara default hanya langkah dengan in_speech=True yang dihitung (--all-steps untuk semua langkah).
Kondisi tiap sesi ditentukan lewat manifest atau config session.json (lihat evaluate_wer.py).
"""
from __future__ import annotations

import argparse
import csv
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path

from evaluate_wer import DEFAULT_MANIFEST, DEFAULT_SESSIONS_DIR, EVAL_DIR, load_sessions

TARGET_E2E_MS = 1500  # PRD: di bawah 1.0 - 1.5 detik
TARGET_RTF = 1.0      # PRD: RTF < 1.0


def nearest_rank(values: list[float], p: float) -> float:
    """Persentil nearest-rank (sama dengan summary() di latency_tracker.py)."""
    s = sorted(values)
    return s[min(len(s) - 1, max(0, math.ceil(p / 100 * len(s)) - 1))]


def to_float(x) -> float | None:
    try:
        return float(x)
    except (TypeError, ValueError):  # termasuk string kosong (server_e2e_ms bisa kosong)
        return None


def to_bool(x) -> bool:
    return str(x).strip().lower() in {"true", "1", "yes"}


def read_steps(folder: Path, all_steps: bool) -> list[dict]:
    path = folder / "latency.csv"
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return [r for r in csv.DictReader(f) if all_steps or to_bool(r.get("in_speech"))]


def column(rows: list[dict], key: str) -> list[float]:
    return [v for r in rows if (v := to_float(r.get(key))) is not None]


def stats(vals: list[float]) -> dict:
    if not vals:
        return {"mean": None, "p50": None, "p95": None, "max": None}
    return {"mean": round(statistics.mean(vals), 3), "p50": round(nearest_rank(vals, 50), 3),
            "p95": round(nearest_rank(vals, 95), 3), "max": round(max(vals), 3)}


def summarize(condition: str, n_sessions: int, rows: list[dict]) -> dict:
    e2e, asr, rtf = column(rows, "server_e2e_ms"), column(rows, "asr_latency_ms"), column(rows, "rtf")
    se, sa, sr = stats(e2e), stats(asr), stats(rtf)
    overruns = sum(to_bool(r.get("overrun")) for r in rows)
    return {
        "condition": condition, "sessions": n_sessions, "steps": len(rows),
        "e2e_mean_ms": se["mean"], "e2e_p50_ms": se["p50"], "e2e_p95_ms": se["p95"], "e2e_max_ms": se["max"],
        "e2e_within_target_pct": round(sum(v <= TARGET_E2E_MS for v in e2e) / len(e2e) * 100, 1) if e2e else None,
        "asr_mean_ms": sa["mean"], "asr_p95_ms": sa["p95"],
        "rtf_mean": sr["mean"], "rtf_p95": sr["p95"], "rtf_max": sr["max"],
        "overruns": overruns, "overrun_pct": round(overruns / len(rows) * 100, 1) if rows else None,
        "rtf_ok": (sr["mean"] < TARGET_RTF) if sr["mean"] is not None else None,
    }


def fmt(v, suffix: str = "") -> str:
    return "-" if v is None else f"{v}{suffix}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="*", type=Path, help="Folder sesi atau folder induknya")
    ap.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    ap.add_argument("--all-steps", action="store_true", help="Sertakan langkah tanpa ucapan (in_speech=False)")
    ap.add_argument("--out", type=Path, default=EVAL_DIR / "results" / "latency_summary.csv")
    args = ap.parse_args()

    sessions = load_sessions(args.paths or [DEFAULT_SESSIONS_DIR], args.manifest)
    if not sessions:
        print("Tidak ada folder sesi yang ditemukan.", file=sys.stderr)
        return 1

    rows_by_cond: dict[str, list[dict]] = defaultdict(list)
    sessions_by_cond: dict[str, int] = defaultdict(int)
    for s in sessions:
        steps = read_steps(s.folder, args.all_steps)
        if not steps:
            print(f"[warn] {s.name}: latency.csv tidak ada / tidak ada langkah in_speech", file=sys.stderr)
            continue
        rows_by_cond[s.condition] += steps
        sessions_by_cond[s.condition] += 1
    if "unlabeled" in rows_by_cond:
        print("[warn] ada sesi tanpa kondisi ('unlabeled'); isi sessions_manifest.json "
              "(python evaluate_wer.py --init-manifest)", file=sys.stderr)

    summary = [summarize(c, sessions_by_cond[c], rows_by_cond[c]) for c in sorted(rows_by_cond)]
    if not summary:
        return 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(summary[0].keys()))
        writer.writeheader()
        writer.writerows(summary)

    print(f"{'Kondisi':<22}{'Sesi':>5}{'Langkah':>9}{'e2e p50':>9}{'e2e p95':>9}"
          f"{f'<={TARGET_E2E_MS}ms':>10}{'ASR mean':>10}{'RTF mean':>10}{'RTF p95':>9}{'Overrun':>9}{'RTF<1':>7}")
    for r in summary:
        ok = "-" if r["rtf_ok"] is None else ("OK" if r["rtf_ok"] else "GAGAL")
        print(f"{r['condition']:<22}{r['sessions']:>5}{r['steps']:>9}{fmt(r['e2e_p50_ms']):>9}{fmt(r['e2e_p95_ms']):>9}"
              f"{fmt(r['e2e_within_target_pct'], '%'):>10}{fmt(r['asr_mean_ms']):>10}{fmt(r['rtf_mean']):>10}"
              f"{fmt(r['rtf_p95']):>9}{fmt(r['overrun_pct'], '%'):>9}{ok:>7}")
    print(f"\nTersimpan di: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
