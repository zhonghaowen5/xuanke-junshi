"""答案精简前后对比探针（只读，不写回 blind.csv）。

用途：在同一批问题（盲评 50 题）上，测量「精简优化」前（blind.csv 里的旧答案）
与优化后（当前链路新生成）的答案长度差异，为评测报告提供量化依据。

用法：
    python _compact_probe.py --chunk 0 --size 15
输出：_compact_probe_{chunk}.json
"""

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import rag  # noqa: E402


def ask_one(question: str, major: str):
    """与 blind_ask.py 一致：未指明专业时补上本人专业名，避免全库检索串味。"""
    q = str(question).strip()
    if not (rag._match_major(q) or any(k in q for k in ("专业", "班"))):
        q = f"{major}专业的{q}"
    return rag.answer_question(q)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chunk", type=int, default=0)
    ap.add_argument("--size", type=int, default=15)
    a = ap.parse_args()

    rows = list(csv.DictReader(open("blind.csv", encoding="utf-8-sig")))
    start = a.chunk * a.size
    sub = rows[start:start + a.size]
    print(f"[*] 第 {a.chunk + 1} 块：第 {start + 1}-{start + len(sub)} 题", flush=True)

    out = []
    for i, r in enumerate(sub, start=start + 1):
        res = ask_one(r["question"], r["major"])
        out.append({
            "no": i,
            "question": r["question"],
            "old_len": len(r["answer"]),
            "new_len": len(res["answer"]),
            "new_answer": res["answer"],
            "rejected": res["rejected"],
        })
        print(f"  [{i}] {len(r['answer'])}字 → {len(res['answer'])}字", flush=True)

    with open(f"_compact_probe_{a.chunk}.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"已写入 _compact_probe_{a.chunk}.json（{len(out)} 条）")


if __name__ == "__main__":
    main()
