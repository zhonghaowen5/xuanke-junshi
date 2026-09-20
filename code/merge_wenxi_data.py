# -*- coding: utf-8 -*-
"""合并古雯茜 2026-09-20 提供的数据（1+2+3）。

合并内容：
  1. 人工courses..csv      —— AI学院8专业完整课程表（808门，2024级）
  2. requirements(2)..csv  —— AI学院8专业毕业要求（用于交叉校验 + 选修课备注细化）
  3. 计算机requirements..csv —— CS学院7专业富备注（专业特色/核心课/方向课/关键词）

关键原则（务必遵守）：
  · 实践环节学分【绝不单独成行】。已验证实践学分含在必修课内
    （课表必修学分合计 ≈ 规则必修学分），若单独成行 diagnose.py 会把
    总学分重复计算（如联合培养 140+26+43=209，正确应为 166）。
    实践信息一律写入"备注"列。
  · 年级统一 2024。雯茜 requirements(2) 标 2025，但必修/选修数值与
    现有 2024 完全一致，判定为同一版培养方案，统一为 2024，
    否则 app.py 取最大年级 2025 会导致 CS 专业（仅 2024）查不到规则。
  · 必修课/选修课的学分数值一律不改动。
"""

import csv
import re
from collections import OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parent          # code/
STRUCT = ROOT / "data" / "structured"
DOWN = Path(r"C:/Users/zhong/Downloads")

COURSES = STRUCT / "courses.csv"
REQS = STRUCT / "requirements.csv"

COURSE_COLS = ["课程代码", "课程名称", "学分", "所属模块", "开课学期", "先修课", "专业", "年级"]
REQ_COLS = ["专业", "年级", "模块名称", "要求学分", "最低选修学分", "备注"]


def read_csv(path):
    """读取 CSV，跳过 # 注释行，返回 (注释行列表, 表头, 数据行dict列表)。"""
    comments, rows = [], []
    with open(path, encoding="utf-8-sig", newline="") as fh:
        for line in fh:
            if line.lstrip().startswith("#"):
                comments.append(line.rstrip("\n"))
                continue
            rows.append(line)
    rdr = csv.DictReader(rows)
    return comments, rdr.fieldnames, list(rdr)


def write_csv(path, comments, fieldnames, rows):
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        for c in comments:
            fh.write(c + "\n")
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})


# ---------------------------------------------------------------- 1+2 课程
def merge_rows(rows):
    """同一门课（同键）的多行合并为一行。

    开课学期合并成逗号分隔的多值字符串（如"2024秋,2026春"），
    其余字段取第一个非空值。避免"形势与政策"这类跨学期开课的行被误删。
    """
    base, terms = {}, []
    for r in rows:
        for k, v in r.items():
            v = (v or "").strip()
            if not v:
                continue
            if k == "开课学期":
                for t in v.split(","):
                    t = t.strip()
                    if t and t not in terms:
                        terms.append(t)
            elif not base.get(k):
                base[k] = v
    base["开课学期"] = ",".join(terms)
    return base


def merge_courses():
    _, _, cur = read_csv(COURSES)
    _, _, new = read_csv(DOWN / "人工courses..csv")

    # 按 (课程代码, 专业, 年级) 分组，同键行合并学期
    groups = OrderedDict()
    cur_keys = set()
    for r in cur:
        r = {k: (v or "").strip() for k, v in r.items()}
        key = (r["课程代码"], r["专业"], r["年级"])
        cur_keys.add(key)
        groups.setdefault(key, []).append(r)

    added, patched = 0, 0
    for r in new:
        r = {k: (v or "").strip() for k, v in r.items()}
        if not r.get("课程代码"):
            continue
        key = (r["课程代码"], r["专业"], r["年级"])
        if key in groups:
            groups[key].append(r)   # 已存在：并入同组，学期随后合并
            patched += 1
        else:
            groups[key] = [r]
            added += 1

    rows = [merge_rows(v) for v in groups.values()]
    write_csv(COURSES, [], COURSE_COLS, rows)
    print(f"[课程] 原有 {len(cur)} 行 -> 合并后 {len(rows)} 门（同键行已合并学期）")
    print(f"       新并入 {added} 门，与现有重叠 {patched} 门")
    return rows


# ---------------------------------------------------------------- 3 备注
def merge_requirements():
    comments, _, cur = read_csv(REQS)
    _, _, cs_new = read_csv(DOWN / "计算机requirements..csv")
    _, _, ai_new = read_csv(DOWN / "requirements(2)..csv")

    # CS 学院：把雯茜的富备注（必修/选修/实践活动三行）拼到对应模块行
    cs_note = {}
    for r in cs_new:
        maj, mod = r["专业"].strip(), r["模块名称"].strip()
        note = (r["备注"] or "").strip()
        if mod == "实践活动":
            # 实践信息只进备注，绝不单独成行
            cs_note.setdefault(maj, {})["__实践__"] = note
        else:
            cs_note.setdefault(maj, {})[mod] = note

    # AI 学院：只取选修课备注做细化，必修课备注保持现有（避免引入冲突的实践学分）
    ai_note = {}
    for r in ai_new:
        maj, mod = r["专业"].strip(), r["模块名称"].strip()
        if mod == "选修课":
            ai_note[maj] = (r["备注"] or "").strip()

    updated_cs, updated_ai = 0, 0
    for r in cur:
        maj = r["专业"].strip()
        mod = r["模块名称"].strip()

        if maj in cs_note:
            parts = [(r["备注"] or "").strip()]
            body = cs_note[maj].get(mod, "")
            if body and body not in parts[0]:          # 幂等：已含则不再追加
                parts.append(body)
            prac = cs_note[maj].get("__实践__", "")
            if prac and "实践环节：" not in parts[0]:
                parts.append("实践环节：" + prac)
            merged = "；".join(p for p in parts if p)
            if merged != (r["备注"] or "").strip():
                r["备注"] = merged
                updated_cs += 1

        elif maj in ai_note and mod == "选修课":
            new_note = ai_note[maj]
            old_note = (r["备注"] or "").strip()
            # 仅在雯茜备注比现有更长（信息更多）时采用
            if new_note and len(new_note) > len(old_note):
                r["备注"] = new_note
                updated_ai += 1

    write_csv(REQS, comments, REQ_COLS, cur)
    print(f"[要求] CS学院备注更新 {updated_cs} 行，AI学院选修课备注细化 {updated_ai} 行")
    print(f"       总行数保持 {len(cur)}（实践环节未单独成行）")
    return cur


if __name__ == "__main__":
    print("=" * 60)
    merge_courses()
    print("-" * 60)
    merge_requirements()
    print("=" * 60)
