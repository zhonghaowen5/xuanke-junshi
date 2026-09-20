"""实验四（引用溯源消融对比）分块执行脚本。

背景：
    整轮 114 题会被执行环境 2 分钟超时掐断，必须分块跑。

分工：
    A 组 = 本系统（检索 + 引用 + 后验校验）→ 直接复用 results.json 中已有的
           fact 实验结果，不重复调用，节省额度；
    B 组 = 通用大模型裸答（无检索、无引用、无校验）→ 本脚本逐块跑。

用法：
    python eval/run_ab_chunks.py --chunk 0 --size 10     # 跑第 0 块
    python eval/run_ab_chunks.py --merge                 # 合并所有分块并与 A 组对比
"""

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from openai import OpenAI

import config
from run_eval import _judge, load_bank

_client = OpenAI(api_key=config.API_KEY, base_url=config.BASE_URL)

OUT_DIR = Path(__file__).resolve().parent
RESULT = config.EVAL_DIR / "results.json"


def ask_baseline(question: str) -> str:
    """B 组：通用大模型裸答。不注入任何资料、不设系统提示。"""
    resp = _client.chat.completions.create(
        model=config.LLM_MODEL,
        messages=[{"role": "user", "content": question}],
        temperature=0.1,
    )
    return resp.choices[0].message.content.strip()


def run_chunk(chunk: int, size: int):
    df = load_bank()
    facts = df[df["type"] == "fact"].reset_index(drop=True)
    total_chunks = (len(facts) + size - 1) // size
    start = chunk * size
    sub = facts.iloc[start:start + size]
    print(f"[*] fact 题共 {len(facts)} 道，当前第 {chunk + 1}/{total_chunks} 块"
          f"（第 {start + 1}-{start + len(sub)} 道）\n", flush=True)

    rows = []
    for _, r in sub.iterrows():
        q = str(r["question"])
        b_ans = ask_baseline(q)
        vb = _judge(q, str(r["standard_answer"]), b_ans)
        rows.append({
            "id": int(r["id"]),
            "question": q,
            "B组回答": b_ans,
            "B组判定": vb["verdict"],
            "comment": vb.get("comment", ""),
        })
        print(f"  [{r['id']}] B={vb['verdict']}", flush=True)

    out = OUT_DIR / f"_ab_chunk_{chunk}.json"
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    print(f"\n已写入 {out}（{len(rows)} 条）")


def merge():
    """合并所有 B 组分块，与 A 组（已有 fact 结果）对比。"""
    b_rows = []
    for f in sorted(OUT_DIR.glob("_ab_chunk_*.json")):
        b_rows.extend(json.loads(f.read_text(encoding="utf-8")))

    if not b_rows:
        raise SystemExit("[!] 没有找到任何 _ab_chunk_*.json，请先分块跑。")

    # A 组：复用 results.json 中已跑好的事实题结果
    data = json.loads(RESULT.read_text(encoding="utf-8")) if RESULT.exists() else {}
    a_fact = data.get("fact", {}).get("rows", [])
    a_map = {int(r["id"]): r for r in a_fact}

    merged = []
    for b in b_rows:
        a = a_map.get(b["id"], {})
        a_verdict = a.get("verdict", "missing")
        # 与 run_eval.run_ab 保持一致：A 组若拒答则记为 wrong
        if a.get("answer", "").startswith("这个问题超出了"):
            a_verdict = "wrong"
        merged.append({
            "id": b["id"],
            "question": b["question"],
            "A组回答": a.get("answer", ""),
            "A组判定": a_verdict,
            "B组回答": b["B组回答"],
            "B组判定": b["B组判定"],
        })

    n = len(merged)
    a_ok = sum(1 for x in merged if x["A组判定"] == "correct")
    b_ok = sum(1 for x in merged if x["B组判定"] == "correct")
    a_hall = sum(1 for x in merged if x["A组判定"] == "wrong")
    b_hall = sum(1 for x in merged if x["B组判定"] == "wrong")

    summary = {
        "总数": n,
        "A组准确率": round(a_ok / n * 100, 1) if n else 0,
        "B组准确率": round(b_ok / n * 100, 1) if n else 0,
        "准确率提升": round((a_ok - b_ok) / n * 100, 1) if n else 0,
        "A组错误数": a_hall,
        "B组错误数": b_hall,
    }

    data["ab"] = {"summary": summary, "rows": merged}
    RESULT.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                      encoding="utf-8")

    print("\n=== 实验四 · 引用溯源消融对比 ===")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"\n已写入 {RESULT}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--chunk", type=int, default=0)
    ap.add_argument("--size", type=int, default=10)
    ap.add_argument("--merge", action="store_true")
    a = ap.parse_args()

    if a.merge:
        merge()
    else:
        run_chunk(a.chunk, a.size)
