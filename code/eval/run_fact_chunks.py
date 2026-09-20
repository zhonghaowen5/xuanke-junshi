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
    a = ap.parse_args()

    df = load_bank()
    facts = df[df["type"] == "fact"].reset_index(drop=True)
    total_chunks = (len(facts) + a.size - 1) // a.size
    start = a.chunk * a.size
    sub = facts.iloc[start:start + a.size]
    print(f"[*] 事实题共 {len(facts)} 道，当前第 {a.chunk + 1}/{total_chunks} 块（id {start + 1}-{start + len(sub)}）\n")

    all_rows = []
    for _, r in sub.iterrows():
        res = answer_question(str(r["question"]))
        verdict = _judge(r["question"], str(r["standard_answer"]), res["answer"])
        all_rows.append({
            "id": r["id"],
            "question": r["question"],
            "answer": res["answer"],
            "std": r["standard_answer"],
            "verdict": verdict["verdict"],
            "comment": verdict["comment"],
        })
        print(f"  [{r['id']}] {verdict['verdict']}")

    # 保存分块结果
    out = Path(f"_fact_chunk_{a.chunk}.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(all_rows, f, ensure_ascii=False, indent=2)
    print(f"\n已写入 {out}（{len(all_rows)} 条）")


if __name__ == "__main__":
    main()
