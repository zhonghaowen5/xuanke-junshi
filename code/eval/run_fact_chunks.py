import argparse
from pathlib import Path
import json
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from rag import answer_question
from run_eval import _judge, load_bank


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chunk", type=int, default=0, help="块号（0开始）")
    ap.add_argument("--size", type=int, default=20, help="每块题数")
    ap.add_argument("--type", dest="qtype", choices=["fact", "reject"],
                    default="fact", help="跑事实题还是拒答题（默认 fact）")
    a = ap.parse_args()

    df = load_bank()
    facts = df[df["type"] == a.qtype].reset_index(drop=True)
    total_chunks = (len(facts) + a.size - 1) // a.size
    start = a.chunk * a.size
    sub = facts.iloc[start:start + a.size]
    print(f"[*] {a.qtype} 题共 {len(facts)} 道，当前第 {a.chunk + 1}/{total_chunks} 块"
          f"（第 {start + 1}-{start + len(sub)} 道）\n", flush=True)

    all_rows = []
    for _, r in sub.iterrows():
        res = answer_question(str(r["question"]))
        if a.qtype == "fact":
            verdict = _judge(r["question"], str(r["standard_answer"]), res["answer"])
            row = {
                "id": r["id"],
                "question": r["question"],
                "answer": res["answer"],
                "std": r["standard_answer"],
                "verdict": verdict["verdict"],
                "comment": verdict["comment"],
            }
            tag = verdict["verdict"]
        else:
            ok = bool(res["rejected"])
            row = {
                "id": r["id"],
                "question": r["question"],
                "answer": res["answer"],
                "correct": ok,
            }
            tag = "正确拒答" if ok else "产生幻觉"
        all_rows.append(row)
        print(f"  [{r['id']}] {tag}", flush=True)

    # 保存分块结果
    out = Path(f"_{a.qtype}_chunk_{a.chunk}.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(all_rows, f, ensure_ascii=False, indent=2)
    print(f"\n已写入 {out}（{len(all_rows)} 条）")


if __name__ == "__main__":
    main()
