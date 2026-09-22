# -*- coding: utf-8 -*-
"""实验三 · 同学盲评 —— 第 1 步：批量向系统提问，生成可直接发给同学的问卷。

【这个脚本干什么】
同学提出 50 个问题后，你不用一个一个去界面里问、再手动复制答案。
把问题填进 eval/blind.csv，跑这个脚本，它会：
  1. 自动调用系统（RAG 完整链路）逐个作答；
  2. 把回答和原文出处写回 blind.csv；
  3. 在 eval/blind_out/ 下给每位同学生成一份「问卷文本」，微信直接复制发送。

【用法】（在 code/ 目录下执行）
    python eval/blind_ask.py              # 问完所有还没问的问题
    python eval/blind_ask.py --limit 10   # 本次最多问 10 题（防止中途超时）
    python eval/blind_ask.py --student 同学A   # 只问某位同学的问题

每问完一题立刻写回文件，中断了再跑一次会接着问，不会重复。
"""

import argparse
import csv
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
CODE = HERE.parent
sys.path.insert(0, str(CODE))

import rag  # noqa: E402  （必须在把 code/ 加进 path 之后导入）

CSV_PATH = HERE / "blind.csv"
OUT_DIR = HERE / "blind_out"

FIELDS = ["id", "student", "major", "question", "answer", "cites",
          "rejected", "acc", "use", "trust", "comment", "guess"]


def load_rows():
    if not CSV_PATH.exists():
        sys.exit(f"找不到 {CSV_PATH}\n请先把同学的问题填进这个文件。")
    with open(CSV_PATH, "r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    for i, r in enumerate(rows, 1):
        r.setdefault("id", str(i))
        for k in FIELDS:
            r.setdefault(k, "")
    return rows


def save_rows(rows):
    with open(CSV_PATH, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in FIELDS})


def ask_one(row):
    """调用系统回答一个问题，写回 row。

    若问题本身没写明专业（如「机器学习这门课几学分？」），
    自动把该同学的专业拼进提问，确保只在本专业培养方案内检索。
    否则会全库检索 → 答案跨专业混杂、啰嗦，盲评观感很差。
    注意：拼的是「提问用的问题」，blind.csv 里的 question 保持同学原话，
    问卷展示的仍是原始问题，同学不会察觉。
    """
    q = row["question"].strip()
    if not q:
        return False
    major = (row.get("major") or "").strip()
    if major:
        # 已提及具体专业（专业名命中，或出现「专业 / 班」字样）则不拼接
        mentions = (rag._match_major(q) is not None
                    or any(k in q for k in ("专业", "班")))
        if not mentions:
            q = f"{major}专业的{q}"
    res = rag.answer_question(q)
    row["answer"] = res["answer"].strip()
    row["cites"] = "；".join(
        f"{c['source']}·{c['chapter']}·P{c['page']}" for c in res["cites"]
    )
    row["rejected"] = "是" if res["rejected"] else "否"
    return True


def build_questionnaire(rows, student):
    """生成某位同学的问卷文本（不透露来源，保留回答与出处）。"""
    mine = [r for r in rows if r["student"] == student and r["question"].strip()]
    lines = [
        "同学你好，这是学业规划问答的一个小测试，大概占用你 3 分钟。",
        "",
        "下面有 %d 个问题和对应的回答，请你根据真实感受打分（1-5 分），" % len(mine),
        "并在最后写一句你的真实想法。答案没有对错，请凭直觉填。",
        "",
        "【评分标准】",
        "5 分 = 完全解决我的疑问",
        "4 分 = 基本解决，还有点小疑问",
        "3 分 = 部分有用",
        "2 分 = 没什么用",
        "1 分 = 完全是错的/答非所问",
        "",
    ]
    for idx, r in enumerate(mine, 1):
        lines += [
            "─" * 40,
            f"问题 {idx}：{r['question'].strip()}",
            "",
            f"回答：{r['answer'].strip()}",
        ]
        if r["cites"].strip():
            lines.append(f"（出处：{r['cites'].strip()}）")
        lines += [
            "",
            f"准确性（答得对不对）：      ___ 分   [题号 {r['id']}]",
            "有用性（对我有没有帮助）：  ___ 分",
            "可信度（我信不信这个答案）：___ 分",
            "",
        ]
    lines += [
        "═" * 40,
        "最后，请写一句你的真实感受（选填）：",
        "________________________________________",
        "",
        "你觉得这些回答最像：",
        "□ 学校官方文件   □ 学长学姐经验   □ AI 生成   □ 说不清",
    ]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="本次最多问几题，0=不限")
    ap.add_argument("--student", default="", help="只问某位同学的问题")
    args = ap.parse_args()

    rows = load_rows()
    todo = [r for r in rows
            if r["question"].strip() and not r["answer"].strip()]
    if args.student:
        todo = [r for r in todo if r["student"] == args.student]
    if args.limit:
        todo = todo[:args.limit]

    if not todo:
        print("没有待回答的问题（可能都问完了，或 blind.csv 里还没填 question）。")
    else:
        print(f"本次待回答 {len(todo)} 题，开始调用系统……")
        done = 0
        for r in todo:
            try:
                ask_one(r)
                done += 1
                tag = "拒答" if r["rejected"] == "是" else "已答"
                print(f"  [{done}/{len(todo)}] id={r['id']} {r['student']} {tag}")
            except Exception as e:
                print(f"  [出错] id={r['id']} {r['student']}：{e}")
                print("  已保存已完成的部分，稍后重跑会继续。")
                break
            save_rows(rows)   # 每题都落盘，防止中断丢失
            time.sleep(0.4)   # 轻微限速，避免触发 API 频率限制
        print(f"完成 {done} 题，结果已写回 blind.csv")

    # 给每位同学生成问卷文本
    OUT_DIR.mkdir(exist_ok=True)
    students = []
    for r in rows:
        s = r["student"].strip()
        if s and s not in students:
            students.append(s)
    for s in students:
        has_answer = any(r["student"] == s and r["answer"].strip() for r in rows)
        if not has_answer:
            continue
        txt = build_questionnaire(rows, s)
        p = OUT_DIR / f"问卷-{s}.txt"
        p.write_text(txt, encoding="utf-8")
        print(f"已生成问卷：{p.relative_to(CODE)}")

    print("\n下一步：把 eval/blind_out/ 里的问卷文本发给对应同学打分，")
    print("收回来后把分数填进 blind.csv 的 acc / use / trust 三列，")
    print("再跑：python eval/blind_stat.py")


if __name__ == "__main__":
    main()
