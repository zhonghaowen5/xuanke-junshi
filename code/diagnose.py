"""学分进度诊断。

输入：
  data/structured/requirements.csv  —— 培养方案解析出的规则表
  data/structured/transcript.csv    —— 学生已修课程（成绩单）

输出：各模块达成度 + 缺口清单 + 风险提示

先运行 `python diagnose.py --template` 生成两张模板表，照着填即可。
"""

import argparse
from pathlib import Path

import pandas as pd

import config

REQ_FILE = config.DATA_STRUCT / "requirements.csv"
TRA_FILE = config.DATA_STRUCT / "transcript.csv"

REQ_COLS = ["专业", "年级", "模块名称", "要求学分", "最低选修学分", "备注"]
TRA_COLS = ["课程代码", "课程名称", "学分", "所属模块", "学期", "成绩"]


def make_template():
    REQ_FILE.write_text(
        "专业,年级,模块名称,要求学分,最低选修学分,备注\n"
        "软件工程,2024,必修课,120,0,含专业基础课与专业核心课\n"
        "软件工程,2024,选修课,0,40,专业选修不少于40学分\n"
        "软件工程,2024,实践环节,10,0,含实习与毕业设计\n",
        encoding="utf-8-sig")
    TRA_FILE.write_text(
        "课程代码,课程名称,学分,所属模块,学期,成绩\n"
        "CS101,程序设计基础,4,必修课,2024秋,88\n"
        "CS102,数据结构,4,必修课,2024秋,85\n"
        "MA101,高等数学A,5,必修课,2024秋,79\n",
        encoding="utf-8-sig")
    print(f"[+] 模板已生成：\n  {REQ_FILE}\n  {TRA_FILE}\n请照格式填写真实数据后重跑。")


def load(profession: str = None, grade: int = None):
    if not REQ_FILE.exists() or not TRA_FILE.exists():
        raise SystemExit("[!] 缺少规则表或成绩单，请先运行 python diagnose.py --template")

    req = pd.read_csv(REQ_FILE, comment="#")
    tra = pd.read_csv(TRA_FILE, comment="#")

    if profession:
        req = req[req["专业"] == profession]
    if grade:
        req = req[req["年级"] == grade]
    return req, tra


def diagnose(profession: str = None, grade: int = None):
    """返回结构化的诊断结果。"""
    req, tra = load(profession, grade)
    if req.empty:
        return {"error": "规则表中没有匹配的专业/年级"}

    earned = tra.groupby("所属模块")["学分"].sum().to_dict()
    # 按成绩判断是否通过（<60 不计入）
    passed = tra[tra["成绩"] >= 60].groupby("所属模块")["学分"].sum().to_dict()
    failed = tra[tra["成绩"] < 60].groupby("所属模块")["学分"].sum().to_dict()

    details, total_req, total_got = [], 0.0, 0.0
    for _, r in req.iterrows():
        mod = r["模块名称"]
        need = float(r["要求学分"]) if pd.notna(r["要求学分"]) else 0.0
        min_elec = float(r["最低选修学分"]) if pd.notna(r["最低选修学分"]) else 0.0
        need_total = need if need > 0 else min_elec
        got = float(passed.get(mod, 0.0))

        total_req += need_total
        total_got += min(got, need_total) if need_total else got

        details.append({
            "模块": mod,
            "要求": need_total,
            "已修": got,
            "缺口": max(round(need_total - got, 1), 0.0),
            "达成率": round(got / need_total * 100, 1) if need_total else 100.0,
            "未通过学分": float(failed.get(mod, 0.0)),
        })

    # 风险提示
    risks = []
    for d in details:
        if d["缺口"] > 0 and d["达成率"] < 60:
            risks.append(f"{d['模块']}缺口较大（还差 {d['缺口']} 学分），建议优先补足")
        if d["未通过学分"] > 0:
            risks.append(f"{d['模块']}有 {d['未通过学分']} 学分课程未通过，需重修")

    return {
        "专业": profession or (req.iloc[0]["专业"]),
        "年级": grade or int(req.iloc[0]["年级"]),
        "总要求": round(total_req, 1),
        "已修": round(total_got, 1),
        "总缺口": round(max(total_req - total_got, 0.0), 1),
        "模块明细": details,
        "风险提示": risks,
    }


def render(d):
    if "error" in d:
        return d["error"]
    lines = [
        f"【学分进度诊断】{d['专业']} · {d['年级']} 级",
        f"毕业要求总学分 {d['总要求']} | 已修 {d['已修']} | 待修 {d['总缺口']}",
        "",
        "模块明细：",
    ]
    for m in d["模块明细"]:
        flag = "OK" if m["缺口"] == 0 else "缺 %.1f" % m["缺口"]
        lines.append(
            f"  {m['模块']:<8} 要求 {m['要求']:>6.1f} | 已修 {m['已修']:>6.1f} "
            f"| 达成 {m['达成率']:>5.1f}% | {flag}")
    if d["风险提示"]:
        lines.append("\n风险提示：")
        lines += [f"  · {r}" for r in d["风险提示"]]
    return "\n".join(lines)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--template", action="store_true", help="生成模板表")
    ap.add_argument("--profession", help="专业名称")
    ap.add_argument("--grade", type=int, help="年级")
    a = ap.parse_args()

    if a.template:
        make_template()
    else:
        print(render(diagnose(a.profession, a.grade)))
