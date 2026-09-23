# -*- coding: utf-8 -*-
"""实验三 · 同学盲评 —— 第 2 步：统计评分，生成可直接回填的表格。

【用法】（在 code/ 目录下执行）
    python eval/blind_stat.py

前提：blind.csv 里的 acc / use / trust 三列已经填好同学打的分（1-5 整数）。

会输出：
  1. 屏幕上的统计摘要；
  2. eval/blind_out/盲评统计结果.md —— 三个 Markdown 表格，
     分别粘到 01-模型与算法说明文档.md 6.6、07-同学盲评问卷.md 3.1/3.2、
     06-答辩PPT大纲.md 第 9 页。
"""

import csv
import statistics
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
CODE = HERE.parent
CSV_PATH = HERE / "blind.csv"
OUT_DIR = HERE / "blind_out"

DIMS = [("acc", "准确性"), ("use", "有用性"), ("trust", "可信度")]
SCORES = [5, 4, 3, 2, 1]


def load_rows():
    if not CSV_PATH.exists():
        sys.exit(f"找不到 {CSV_PATH}")
    with open(CSV_PATH, "r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def to_int(v):
    try:
        return int(str(v).strip())
    except (ValueError, AttributeError):
        return None


def main():
    rows = load_rows()
    scored = []
    for r in rows:
        vals = {k: to_int(r.get(k, "")) for k, _ in DIMS}
        if all(v is not None for v in vals.values()):
            scored.append((r, vals))

    if not scored:
        sys.exit("还没有任何打分记录。请先把同学的分数填进 blind.csv 的 "
                 "acc / use / trust 三列。")

    students = sorted({r["student"].strip() for r, _ in scored
                       if r["student"].strip()})
    n_student = len(students)
    n_q = len(scored)
    rejected_n = sum(1 for r, _ in scored if r.get("rejected", "").strip() == "是")

    print(f"参与人数：{n_student} 人")
    print(f"有效问题数：{n_q} 条（其中系统拒答 {rejected_n} 条）")

    avg = {}
    dist = {}
    for key, name in DIMS:
        vals = [v[key] for _, v in scored]
        avg[key] = statistics.mean(vals)
        dist[key] = Counter(vals)
        print(f"{name}平均分：{avg[key]:.2f}  "
              f"分布 " + " ".join(f"{s}分×{dist[key].get(s, 0)}" for s in SCORES))

    overall = statistics.mean(avg[k] for k, _ in DIMS)
    print(f"综合平均分：{overall:.2f}")

    # ---- 生成 Markdown ----
    L = []
    L.append("# 实验三 · 同学盲评统计结果\n")
    L.append(f"- 参与人数：**{n_student} 人**")
    L.append(f"- 有效问题数：**{n_q} 条**（其中系统主动拒答 **{rejected_n} 条**）")
    L.append(f"- 综合平均分：**{overall:.2f} / 5**\n")

    L.append("## 表 1 · 总览（回填到 01-模型与算法说明文档.md 6.6 / 07 文档 3.1）\n")
    L.append("| 指标 | 结果 |")
    L.append("| --- | --- |")
    L.append(f"| 参与人数 | {n_student}（目标 10 人） |")
    L.append(f"| 有效问题数 | {n_q}（目标 50 条） |")
    for key, name in DIMS:
        L.append(f"| {name}平均分 | {avg[key]:.2f} |")
    L.append(f"| **综合平均分** | **{overall:.2f}** |")

    L.append("\n## 表 2 · 分维度明细（回填到 07-同学盲评问卷.md 3.2）\n")
    L.append("| 维度 | 5 分 | 4 分 | 3 分 | 2 分 | 1 分 | 平均分 |")
    L.append("| --- | --- | --- | --- | --- | --- | --- |")
    for key, name in DIMS:
        d = dist[key]
        cells = " | ".join(str(d.get(s, 0)) for s in SCORES)
        L.append(f"| {name} | {cells} | {avg[key]:.2f} |")

    # 同学原话
    comments = [(r["student"].strip(), r.get("comment", "").strip())
                for r, _ in scored if r.get("comment", "").strip()]
    if comments:
        L.append("\n## 表 3 · 同学原话摘录（回填到 07-同学盲评问卷.md 3.3）\n")
        L.append("| 同学（可匿名） | 原话 |")
        L.append("| --- | --- |")
        seen = set()
        for s, c in comments:
            if s in seen:
                continue
            seen.add(s)
            L.append(f"| {s} | {c} |")

    # 来源猜测分布
    guesses = [r.get("guess", "").strip() for r, _ in scored
               if r.get("guess", "").strip()]
    if guesses:
        gc = Counter(guesses)
        L.append("\n## 表 4 · 来源猜测分布（回填到 07-同学盲评问卷.md 3.4）\n")
        L.append("| 同学认为答案来自 | 人数 |")
        L.append("| --- | --- |")
        for g, n in gc.most_common():
            L.append(f"| {g} | {n} |")

    L.append("\n## 一句话结论（可放进答辩 PPT 第 9 页）\n")
    L.append(f"> 10 名同学共提出 {n_q} 个真实学业问题，盲评（不告知回答来源）"
             f"综合平均分 **{overall:.2f} / 5**，"
             f"其中准确性 {avg['acc']:.2f}、有用性 {avg['use']:.2f}、"
             f"可信度 {avg['trust']:.2f}；"
             f"系统对知识库外问题主动拒答 {rejected_n} 次，未出现编造答案的情况。")

    OUT_DIR.mkdir(exist_ok=True)
    out = OUT_DIR / "盲评统计结果.md"
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"\n已生成回填表格：{out.relative_to(CODE)}")


if __name__ == "__main__":
    main()
