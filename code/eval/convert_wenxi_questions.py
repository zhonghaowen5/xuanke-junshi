"""把队友（古雯茜）提供的题目 xlsx 转换成评测题库格式。

背景：
    队友发来的题库是 xlsx，列头为「题目类型 / 题目 / 标准答案 / 来源出处 / 涉及专业」。
    本项目评测题库 eval/questions.csv 的格式是：
        id,type,question,standard_answer,source
    且 rag.answer_question() 靠「题目文本里的专业名」定位专业，
    所以题目必须自带专业名（如「人工智能专业毕业需要多少总学分」）。

关键风险 1 —— 别把拒答题一起剔掉：
    队友题库的「涉及专业」列**不全是专业名**，还混着题型标签，例如
    「超纲问题」「模糊问题（未指定专业）」「信息缺失」「主观比较」
    「未收录专业（泛化）」「多专业对比」。
    其中前五类标记的题目 type 都是 reject，是**质量很高的拒答测试题**
    （如「怎么申请奖学金？」「学校有哪些社团？」「毕业最低学分是多少？」），
    必须保留；只有 type=fact 且专业确实没接入时才剔除。

关键风险 2 —— 拒答题绝不能自动补专业名：
    「模糊问题（未指定专业）」这类题的测试意图就是"没说专业就该拒答"。
    若自动补成「毕业最低学分是多少？（人工智能专业）」，题目立刻变成
    可答题，测试完全失效。因此 ensure_major_in_question() 只对 fact 生效。

用法：
    # 1. 先预览（默认，不写任何文件）
    python eval/convert_wenxi_questions.py "C:/Users/zhong/Downloads/题目.xlsx"

    # 2. 确认无误后，追加到现有题库（id 接着现有最大编号）
    python eval/convert_wenxi_questions.py "C:/Users/zhong/Downloads/题目.xlsx" --mode append --write

    # 3. 或整体替换现有题库（会先备份）
    python eval/convert_wenxi_questions.py "C:/Users/zhong/Downloads/题目.xlsx" --mode replace --write

    # 4. 强行保留未接入专业的题目（不推荐，仅用于对照实验）
    ... --keep-unknown

依赖：只用标准库（zipfile + XML）解析 xlsx，不需要 openpyxl / pandas。
"""

import argparse
import csv
import re
import shutil
import sys
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent          # code/
sys.path.insert(0, str(ROOT))

EVAL_DIR = ROOT / "eval"
QBANK = EVAL_DIR / "questions.csv"
REQ = ROOT / "data" / "structured" / "requirements.csv"

OUT_COLS = ["id", "type", "question", "standard_answer", "source"]

# xlsx 命名空间
M = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"

# 表头别名 → 标准字段名
ALIAS = {
    "题目类型": "type", "类型": "type", "题型": "type",
    "题目": "question", "问题": "question",
    "标准答案": "standard_answer", "答案": "standard_answer",
    "来源出处": "source", "出处": "source", "来源": "source",
    "涉及专业": "major", "专业": "major",
}


# ---------------------------------------------------------------- xlsx 读取
def _colnum(ref: str) -> int:
    m = re.match(r"([A-Z]+)", ref)
    n = 0
    for ch in m.group(1):
        n = n * 26 + ord(ch) - 64
    return n - 1


def read_xlsx(path: Path) -> list[list[str]]:
    """用标准库解析 xlsx，返回二维列表（第一行是表头）。"""
    z = zipfile.ZipFile(path)
    shared: list[str] = []
    if "xl/sharedStrings.xml" in z.namelist():
        rt = ET.fromstring(z.read("xl/sharedStrings.xml"))
        for si in rt.findall(M + "si"):
            shared.append("".join(t.text or "" for t in si.iter(M + "t")))

    wb = ET.fromstring(z.read("xl/workbook.xml"))
    rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    relmap = {r.get("Id"): r.get("Target") for r in rels}

    rows: list[list[str]] = []
    for sh in wb.find(M + "sheets"):
        tgt = relmap[sh.get(R + "id")].lstrip("/")
        if not tgt.startswith("xl/"):
            tgt = "xl/" + tgt
        rt = ET.fromstring(z.read(tgt))
        for row in rt.iter(M + "row"):
            cells: dict[int, str] = {}
            for c in row.findall(M + "c"):
                t = c.get("t")
                v = c.find(M + "v")
                inline = c.find(M + "is")
                if t == "s" and v is not None:
                    val = shared[int(v.text)]
                elif t == "inlineStr" and inline is not None:
                    val = "".join(x.text or "" for x in inline.iter(M + "t"))
                elif v is not None:
                    val = v.text
                else:
                    val = ""
                cells[_colnum(c.get("r"))] = val
            if cells:
                w = max(cells) + 1
                rows.append([cells.get(i, "") for i in range(w)])
    return rows


# ---------------------------------------------------------------- 工具
def read_csv_rows(path: Path) -> list[dict]:
    """读取 CSV，自动跳过 # 注释行和 BOM。"""
    if not path.exists():
        return []
    with open(path, encoding="utf-8-sig", newline="") as fh:
        lines = [l for l in fh if not l.lstrip().startswith("#")]
    return list(csv.DictReader(lines))


def known_majors() -> set[str]:
    """从 requirements.csv 读取本项目已接入的专业名单。"""
    return {r["专业"].strip() for r in read_csv_rows(REQ) if r.get("专业", "").strip()}


def normalize_type(raw: str) -> str:
    t = (raw or "").strip().lower()
    if t in ("fact", "事实", "事实题"):
        return "fact"
    if t in ("reject", "拒答", "拒答题", "超纲"):
        return "reject"
    return t


def ensure_major_in_question(q: str, major: str) -> str:
    """题目里必须出现专业名，否则 RAG 无法定位专业。

    队友的题目大多自带专业名（如「人工智能专业毕业需要多少总学分」），
    缺失时自动补成「...（XX专业）」，与现有题库风格一致。
    """
    q = (q or "").strip()
    if not major:
        return q
    # 已包含专业名（或其主体部分）就不动
    core = major.split("+")[0]
    if major in q or core in q:
        return q
    return f"{q}（{major}专业）"


# ---------------------------------------------------------------- 主流程
def convert(path: Path, keep_unknown: bool):
    rows = read_xlsx(path)
    if not rows:
        raise SystemExit(f"[!] 文件为空：{path}")

    header = [h.strip() for h in rows[0]]
    fields = [ALIAS.get(h, h) for h in header]
    data = [dict(zip(fields, r)) for r in rows[1:] if any(x.strip() for x in r)]

    print(f"[*] 读取 {len(data)} 题，表头：{header}")

    majors = known_majors()
    print(f"[*] 本项目已接入 {len(majors)} 个专业")

    kept, dropped = [], []
    for r in data:
        r = {k: (v or "").strip() for k, v in r.items()}
        maj = r.get("major", "")
        typ = normalize_type(r.get("type", ""))
        known = maj in majors

        if not known and typ != "reject" and not keep_unknown:
            # 未接入专业 / 题型标签，且是事实题 → 知识库答不了，剔除
            if "对比" in maj:
                r["_reason"] = "跨专业对比（可能触发跨专业拒答规则，需人工确认）"
            else:
                r["_reason"] = "未收录专业，知识库无对应培养方案"
            dropped.append(r)
            continue

        item = {
            "type": typ,
            # reject 题不补专业名，否则「未指定专业就该拒答」的测试意图会被破坏
            "question": (ensure_major_in_question(r.get("question", ""), maj)
                         if typ == "fact" else (r.get("question", "").strip())),
            "standard_answer": r.get("standard_answer", ""),
            "source": r.get("source", ""),
            "major": maj,
        }
        if not item["question"]:
            continue
        if item["type"] not in ("fact", "reject"):
            print(f"    [!] 未知题型 {item['type']!r}，已跳过：{item['question'][:30]}")
            continue
        kept.append(item)

    print(f"\n[*] 保留 {len(kept)} 题，剔除 {len(dropped)} 题")
    print(f"    保留题型分布：{dict(Counter(x['type'] for x in kept))}")

    if dropped:
        print("\n[!] 被剔除的题目（按原因归类）：")
        by_reason: dict[str, Counter] = {}
        for x in dropped:
            by_reason.setdefault(x.get("_reason", "其他"), Counter())[x.get("major", "(空)")] += 1
        for reason, cnt in by_reason.items():
            print(f"    原因：{reason}")
            for m, n in cnt.most_common():
                print(f"        {m:20s} {n:4d} 题")

    print("\n[*] 保留题目的分布：")
    print(f"    fact   {sum(1 for x in kept if x['type']=='fact'):4d} 题")
    print(f"    reject {sum(1 for x in kept if x['type']=='reject'):4d} 题")
    for m, n in Counter(x["major"] for x in kept).most_common():
        print(f"      {m or '(未标注)':28s} {n:4d} 题")

    # 抽查
    print("\n[*] 抽查前 5 题：")
    for x in kept[:5]:
        print(f"      [{x['type']}] {x['question'][:52]}")
        print(f"             答：{x['standard_answer'][:40]}")

    return kept


def write_out(items: list[dict], mode: str, write: bool):
    cur = read_csv_rows(QBANK)
    cur = [r for r in cur if r.get("question", "").strip()]

    if mode == "replace":
        if write:
            bak = QBANK.with_suffix(".csv.bak")
            shutil.copy(QBANK, bak)
            print(f"\n[*] 已备份原题库 -> {bak.name}")
        base: list[dict] = []
        start_id = 1
    else:  # append
        base = [{
            "id": r.get("id", ""), "type": r.get("type", ""),
            "question": r.get("question", ""),
            "standard_answer": r.get("standard_answer", ""),
            "source": r.get("source", ""),
        } for r in cur]
        ids = [int(r["id"]) for r in base if str(r["id"]).strip().isdigit()]
        start_id = (max(ids) + 1) if ids else 1

    # 与原题库去重（按题目文本）
    exist = {r.get("question", "").strip() for r in cur} if mode == "append" else set()
    added, dup = 0, 0
    for x in items:
        if x["question"] in exist:
            dup += 1
            continue
        exist.add(x["question"])
        base.append({
            "id": start_id + added, "type": x["type"],
            "question": x["question"],
            "standard_answer": x["standard_answer"],
            "source": x["source"],
        })
        added += 1

    print(f"\n[*] 新写入 {added} 题，与现有题库重复 {dup} 题，最终共 {len(base)} 题")
    print(f"    最终题型分布：{dict(Counter(r['type'] for r in base))}")

    if not write:
        print("\n[!] 预览模式，未写入任何文件。确认无误后加 --write 执行。")
        return

    with open(QBANK, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=OUT_COLS)
        w.writeheader()
        w.writerows(base)
    print(f"\n[✓] 已写入 {QBANK}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("xlsx", help="队友提供的题目 xlsx 路径")
    ap.add_argument("--mode", choices=["append", "replace"], default="append",
                    help="append=追加到现有题库（默认）；replace=整体替换")
    ap.add_argument("--write", action="store_true",
                    help="真正写入 questions.csv；不加则只预览")
    ap.add_argument("--keep-unknown", action="store_true",
                    help="保留未接入专业的题目（不推荐）")
    ap.add_argument("--out",
                    help="输出到指定 CSV（默认写 eval/questions.csv）；"
                         "用于先生成临时题库单独试跑评测")
    a = ap.parse_args()

    path = Path(a.xlsx)
    if not path.exists():
        raise SystemExit(f"[!] 找不到文件：{path}")

    items = convert(path, a.keep_unknown)
    if not items:
        raise SystemExit("[!] 没有可用题目，终止。")

    if a.out:
        out = Path(a.out)
        with open(out, "w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=OUT_COLS)
            w.writeheader()
            for i, x in enumerate(items, 1):
                w.writerow({
                    "id": i, "type": x["type"], "question": x["question"],
                    "standard_answer": x["standard_answer"], "source": x["source"],
                })
        print(f"\n[✓] 已写出 {len(items)} 题 -> {out}")
        return

    write_out(items, a.mode, a.write)


if __name__ == "__main__":
    main()
