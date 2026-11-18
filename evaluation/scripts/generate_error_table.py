"""Buat Error Analysis Table (Reference vs System Output + klasifikasi S/D/I) dalam Markdown.

Contoh:
  python generate_error_table.py --top 5        # dari folder sesi + manifest
  python generate_error_table.py --hypotheses ../results/hypotheses.json --top 5
Output: evaluation/results/error_analysis.md
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

from evaluate_wer import (DEFAULT_OUT, DEFAULT_REFS, add_hypothesis_args, align, get_hypotheses,
                          load_texts, normalize, score)

LABELS = {"S": "Substitution", "D": "Deletion", "I": "Insertion"}

# Istilah teknis umum untuk menandai error pada code-switching (tambahkan sesuai materi).
CS_TERMS = {
    "pointer", "array", "recursion", "polymorphism", "inheritance", "encapsulation", "abstraction",
    "linked", "list", "stack", "queue", "heap", "tree", "graph", "hash", "table", "node", "loop",
    "asynchronous", "function", "class", "object", "interface", "algorithm", "complexity", "binary",
    "search", "sort", "string", "integer", "boolean", "variable", "compile", "runtime", "database",
    "query", "index", "key", "join", "thread", "memory", "overflow",
}


def cell(text: str) -> str:
    return (text or "-").replace("|", "\\|").replace("\n", " ")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--references", type=Path, default=DEFAULT_REFS)
    add_hypothesis_args(ap)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT / "error_analysis.md")
    ap.add_argument("--top", type=int, default=5, help="Jumlah sampel dengan WER tertinggi untuk tabel kalimat")
    ap.add_argument("--max-detail", type=int, default=30, help="Maksimum baris tabel detail kata")
    args = ap.parse_args()

    refs, hyps = load_texts(args.references), get_hypotheses(args)
    ids = sorted(set(refs) & set(hyps))
    if not ids:
        print("Tidak ada ID yang cocok antara references dan hypotheses.", file=sys.stderr)
        return 1

    results = {sid: score(refs[sid]["text"], hyps[sid]["text"]) for sid in ids}
    worst = sorted(ids, key=lambda s: results[s]["WER"], reverse=True)[: args.top]

    out = ["# Error Analysis", ""]

    # 1) Tabel tingkat kalimat
    out += ["## 1. Reference vs System Output (sampel dengan WER tertinggi)", "",
            "| Sampel | Kondisi | Reference | System Output | S | D | I | WER |",
            "|---|---|---|---|---|---|---|---|"]
    for sid in worst:
        r = results[sid]
        out.append(f"| {cell(sid)} | {cell(refs[sid]['condition'])} | {cell(normalize(refs[sid]['text']))} | "
                   f"{cell(normalize(hyps[sid]['text']))} | {r['S']} | {r['D']} | {r['I']} | {r['WER'] * 100:.1f}% |")

    # 2) Tabel detail kata
    details, counts = [], Counter()
    for sid in worst:
        for op, rw, hw in align(normalize(refs[sid]["text"]).split(), normalize(hyps[sid]["text"]).split()):
            if op == "C":
                continue
            counts[op] += 1
            is_term = "Ya" if (rw or hw) in CS_TERMS else "-"
            details.append((refs[sid]["condition"], sid, rw, hw, LABELS[op], is_term))

    out += ["", "## 2. Detail kesalahan per kata", "",
            "| Kondisi | Sampel | Reference | System Output | Tipe | Istilah CS |", "|---|---|---|---|---|---|"]
    for cond, sid, rw, hw, typ, term in details[: args.max_detail]:
        out.append(f"| {cell(cond)} | {cell(sid)} | {cell(rw)} | {cell(hw)} | {typ} | {term} |")
    if len(details) > args.max_detail:
        out.append(f"\n_{len(details) - args.max_detail} kesalahan lain tidak ditampilkan (--max-detail)._")

    # 3) Ringkasan jenis error
    total = sum(counts.values()) or 1
    term_errors = sum(1 for d in details if d[5] == "Ya")
    out += ["", "## 3. Ringkasan jenis kesalahan (pada sampel di atas)", "",
            "| Tipe | Jumlah | Persentase |", "|---|---|---|"]
    for op in ("S", "D", "I"):
        out.append(f"| {LABELS[op]} | {counts[op]} | {counts[op] / total * 100:.1f}% |")
    out += ["", f"Kesalahan pada istilah teknis CS: **{term_errors}** dari **{len(details)}** kesalahan.", ""]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(out), encoding="utf-8")
    print(f"Tersimpan di: {args.out}  ({len(details)} kesalahan dari {len(worst)} sampel)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
