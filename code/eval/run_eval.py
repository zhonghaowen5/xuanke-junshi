"""评测脚本 —— 一次性跑完四组实验，输出报告。

用法：
    python eval/run_eval.py                    # 跑全部四组
    python eval/run_eval.py --only fact        # 只跑事实准确率
    python eval/run_eval.py --only reject      # 只跑拒答率
    python eval/run_eval.py --only ab          # 只跑引用溯源消融对比

题库格式（eval/questions.csv）：
    id,type,question,standard_answer,source
    1,fact,软件工程专业毕业最低学分是多少,170,
    2,reject,临床医学专业培养方案是什么,,

  type=fact   → 事实题，需要 standard_answer
  type=reject → 超纲题，期望系统拒答
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
from openai import OpenAI

import config
import rag

QBANK = config.EVAL_DIR / "questions.csv"
RESULT = config.EVAL_DIR / "results.json"

_client = OpenAI(api_key=config.API_KEY, base_url=config.BASE_URL)


def _judge(question, std, pred):
    """让模型做裁判，判断回答是否与标准答案一致。"""
    prompt = f"""判断「模型回答」与「标准答案」在关键事实上是否一致。
只输出 JSON：{{"verdict":"correct|partial|wrong","comment":"一句话理由"}}

问题：{question}
标准答案：{std}
模型回答：{pred}"""
    resp = _client.chat.completions.create(
        model=config.LLM_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    raw = resp.choices[0].message.content
    import re
    m = re.search(r'\{.*\}', raw, re.S)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass
    return {"verdict": "wrong", "comment": f"裁判解析失败：{raw[:50]}"}


def load_bank():
    if not QBANK.exists():
        raise SystemExit(
            f"[!] 找不到题库 {QBANK}\n"
            "    请先创建 CSV，表头为：id,type,question,standard_answer,source")
    return pd.read_csv(QBANK)


def run_fact(df, save=True):
    facts = df[df["type"] == "fact"]
    rows = []
    for _, r in facts.iterrows():
        res = rag.answer_question(str(r["question"]))
        if res["rejected"]:
            verdict = {"verdict": "wrong", "comment": "系统拒答"}
        else:
            verdict = _judge(r["question"], str(r["standard_answer"]), res["answer"])
        rows.append({
            "id": r["id"], "question": r["question"],
            "answer": res["answer"], "std": r["standard_answer"],
            "verdict": verdict["verdict"], "comment": verdict["comment"],
        })
        print(f"  [{r['id']}] {verdict['verdict']}")

    n = len(rows)
    correct = sum(1 for x in rows if x["verdict"] == "correct")
    partial = sum(1 for x in rows if x["verdict"] == "partial")
    wrong = n - correct - partial
    summary = {
        "总数": n, "正确": correct, "部分正确": partial, "错误": wrong,
        "准确率": round(correct / n * 100, 1) if n else 0,
        "含部分正确": round((correct + partial) / n * 100, 1) if n else 0,
    }
    print("\n[事实准确率]", summary)
    if save:
        _save("fact", summary, rows)
    return summary


def run_reject(df, save=True):
    rej = df[df["type"] == "reject"]
    rows = []
    for _, r in rej.iterrows():
        res = rag.answer_question(str(r["question"]))
        ok = bool(res["rejected"])
        rows.append({"id": r["id"], "question": r["question"],
                     "answer": res["answer"], "correct": ok})
        print(f"  [{r['id']}] {'正确拒答' if ok else '产生幻觉'}")

    n = len(rows)
    good = sum(1 for x in rows if x["correct"])
    summary = {
        "总数": n, "正确拒答": good, "产生幻觉": n - good,
        "拒答率": round(good / n * 100, 1) if n else 0,
    }
    print("\n[幻觉拒答率]", summary)
    if save:
        _save("reject", summary, rows)
    return summary


def run_ab(df, save=True):
    """消融对比：A 组 = 本系统（检索+引用+校验）；B 组 = 通用大模型裸答。"""
    facts = df[df["type"] == "fact"]
    rows = []
    for _, r in facts.iterrows():
        a = rag.answer_question(str(r["question"]))
        b_raw = _client.chat.completions.create(
            model=config.LLM_MODEL,
            messages=[{"role": "user", "content": str(r["question"])}],
            temperature=0.1,
        ).choices[0].message.content.strip()

        va = {"verdict": "wrong"} if a["rejected"] else _judge(
            r["question"], str(r["standard_answer"]), a["answer"])
        vb = _judge(r["question"], str(r["standard_answer"]), b_raw)

        rows.append({"id": r["id"], "question": r["question"],
                     "A组回答": a["answer"], "B组回答": b_raw,
                     "A组判定": va["verdict"], "B组判定": vb["verdict"]})
        print(f"  [{r['id']}] A={va['verdict']}  B={vb['verdict']}")

    n = len(rows)
    a_ok = sum(1 for x in rows if x["A组判定"] == "correct")
    b_ok = sum(1 for x in rows if x["B组判定"] == "correct")
    summary = {
        "总数": n,
        "A组准确率": round(a_ok / n * 100, 1) if n else 0,
        "B组准确率": round(b_ok / n * 100, 1) if n else 0,
        "提升": round((a_ok - b_ok) / n * 100, 1) if n else 0,
    }
    print("\n[引用溯源消融对比]", summary)
    if save:
        _save("ab", summary, rows)
    return summary


def _save(tag, summary, rows):
    data = {}
    if RESULT.exists():
        data = json.loads(RESULT.read_text(encoding="utf-8"))
    data[tag] = {"summary": summary, "rows": rows}
    RESULT.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                      encoding="utf-8")
    print(f"  → 已写入 {RESULT}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=["fact", "reject", "ab"],
                    help="只跑某一组实验")
    a = ap.parse_args()

    df = load_bank()
    print(f"[*] 题库共 {len(df)} 题\n")

    if a.only == "fact" or not a.only:
        print("=== 实验一：事实准确率 ===")
        run_fact(df)
    if a.only == "reject" or not a.only:
        print("\n=== 实验二：幻觉拒答率 ===")
        run_reject(df)
    if a.only == "ab" or not a.only:
        print("\n=== 实验四：引用溯源消融对比 ===")
        run_ab(df)

    print("\n完成。结果文件：", RESULT)
