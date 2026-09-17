"""智能排课建议。

输入：
  data/structured/courses.csv    —— 开课计划（课程库）
  data/structured/requirements.csv + transcript.csv（复用 diagnose 的结果）

决策规则（按优先级）：
  1. 先修课必须已通过，否则不推荐；
  2. 缺口大的模块优先；
  3. 必修课优先于选修课；
  4. 单学期总学分控制在 18—24 之间，避免过载。

先运行 `python recommend.py --template` 生成课程库模板。
"""

import argparse

import pandas as pd

import config
from diagnose import diagnose

COURSE_FILE = config.DATA_STRUCT / "courses.csv"
COURSE_COLS = ["课程代码", "课程名称", "学分", "所属模块", "开课学期",
               "先修课", "专业", "年级"]

CREDIT_MIN, CREDIT_MAX = 18, 24


def make_template():
    COURSE_FILE.write_text(
        "课程代码,课程名称,学分,所属模块,开课学期,先修课,专业,年级\n"
        "CS201,算法设计与分析,4,必修课,2026秋,数据结构,软件工程,2024\n"
        "CS202,操作系统,4,必修课,2026秋,数据结构,软件工程,2024\n"
        "CS203,计算机网络,3,必修课,2026秋,,软件工程,2024\n"
        "SE301,软件工程导论,3,必修课,2026秋,,软件工程,2024\n"
        "SE310,Web应用开发,2,选修课,2026秋,程序设计基础,软件工程,2024\n"
        "SE311,人工智能导论,2,选修课,2026秋,,软件工程,2024\n"
        "SE312,数据可视化,2,选修课,2026秋,,软件工程,2024\n"
        "SE313,软件测试技术,2,选修课,2026秋,,软件工程,2024\n",
        encoding="utf-8-sig")
    print(f"[+] 课程库模板已生成：{COURSE_FILE}")


def load():
    if not COURSE_FILE.exists():
        raise SystemExit("[!] 缺少课程库，请先运行 python recommend.py --template")
    return pd.read_csv(COURSE_FILE, comment="#")


def recommend(semester: str = "2026秋", profession: str = None,
              grade: int = None, max_credit: int = CREDIT_MAX):
    diag = diagnose(profession, grade)
    if "error" in diag:
        return diag

    courses = load()
    if profession:
        courses = courses[courses["专业"] == profession]
    if grade:
        courses = courses[courses["年级"] == grade]
    courses = courses[courses["开课学期"] == semester]

    # 已通过的课程不再推荐；未通过的记录为「待重修」
    from diagnose import TRA_FILE
    tra = pd.read_csv(TRA_FILE, comment="#")
    passed = set(tra[tra["成绩"] >= 60]["课程名称"])
    failed = set(tra[tra["成绩"] < 60]["课程名称"])

    gap_map = {d["模块"]: d["缺口"] for d in diag["模块明细"]}

    cands = []
    for _, c in courses.iterrows():
        name = c["课程名称"]
        if name in passed:
            continue
        prereq = str(c["先修课"]).strip() if pd.notna(c["先修课"]) else ""
        if prereq and prereq not in passed:
            continue  # 先修课未通过，剔除
        gap = gap_map.get(c["所属模块"], 0.0)
        if gap <= 0 and c["所属模块"] != "必修课":
            continue  # 该模块已修满，选修课不再推荐
        cands.append({
            "课程代码": c["课程代码"],
            "课程名称": name,
            "学分": float(c["学分"]),
            "所属模块": c["所属模块"],
            "缺口": gap,
            "重修": name in failed,
        })

    # 排序：必修优先 → 重修优先 → 缺口大的模块优先 → 学分大的优先
    cands.sort(key=lambda x: (
        0 if x["所属模块"] == "必修课" else 1,
        0 if x["重修"] else 1,
        -x["缺口"],
        -x["学分"],
    ))

    picked, total = [], 0.0
    for c in cands:
        if total + c["学分"] > max_credit:
            continue
        picked.append(c)
        total += c["学分"]

    reasons = []
    if total < CREDIT_MIN:
        reasons.append(f"可选课程总学分仅 {total}，低于建议下限 {CREDIT_MIN}，"
                       f"请确认课程库数据是否完整")
    if any(c["重修"] for c in picked):
        names = "、".join(c["课程名称"] for c in picked if c["重修"])
        reasons.append(f"含待重修课程：{names}，建议优先安排")

    return {
        "学期": semester,
        "推荐课程": picked,
        "总学分": round(total, 1),
        "说明": reasons,
        "诊断摘要": diag,
    }


def render(r):
    if "error" in r:
        return r["error"]
    d = r["诊断摘要"]
    lines = [
        f"【排课建议】{r['学期']} | 当前待修总学分 {d['总缺口']}",
        "",
        "推荐课程组合：",
    ]
    for c in r["推荐课程"]:
        tag = "【重修】" if c["重修"] else ""
        lines.append(f"  {c['课程代码']} {c['课程名称']}  {c['学分']} 学分"
                     f"  {c['所属模块']} {tag}")
    lines.append(f"\n合计 {r['总学分']} 学分（建议区间 {CREDIT_MIN}—{CREDIT_MAX}）")

    lines.append("\n推荐理由：")
    for c in r["推荐课程"][:3]:
        why = []
        if c["所属模块"] == "必修课":
            why.append("必修课，须优先完成")
        if c["缺口"] > 0:
            why.append(f"所属模块尚缺 {c['缺口']} 学分")
        if c["重修"]:
            why.append("此前未通过，需重修")
        lines.append(f"  · {c['课程名称']}：{'；'.join(why) or '满足选课条件'}")

    if r["说明"]:
        lines.append("")
        lines += [f"  提示：{s}" for s in r["说明"]]
    return "\n".join(lines)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--template", action="store_true")
    ap.add_argument("--semester", default="2026秋")
    ap.add_argument("--profession")
    ap.add_argument("--grade", type=int)
    a = ap.parse_args()

    if a.template:
        make_template()
    else:
        print(render(recommend(a.semester, a.profession, a.grade)))
