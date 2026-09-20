"""从计算机科学与技术学院 8 份新培养方案 PDF 中提取
requirements.csv 与 courses.csv 所需数据。

用法：
    cd code && python extract_cs_majors.py
    # 输出在 data/structured/_extracted_requirements.csv 和 _extracted_courses.csv
"""

import re
from pathlib import Path

import pdfplumber
import pandas as pd

RAW_DIR = Path(__file__).parent / "data" / "raw"
STRUCT_DIR = Path(__file__).parent / "data" / "structured"

NEW_MAJORS = [
    "计算机科学与技术",
    "计算机科学与技术卓越工程师班",
    "计算机科学与技术菁英班",
    "计算机科学与技术（拔尖创新班）",
    "计算机科学文峰班",
    "软件工程",
    "软件工程专业卓越工程师班",
    "软件工程英才班",
]

SEM_MAP = {
    "1": "2024秋",
    "2": "2025春",
    "3": "2025秋",
    "4": "2026春",
    "5": "2026秋",
    "6": "2027春",
    "7": "2027秋",
    "8": "2028春",
}


def extract_total_credits(text: str):
    """从全文文本提取「必修X学分，选修Y学分，总学分：Z学分」。"""
    pattern = re.compile(r"必修\s*(\d+(?:\.\d+)?)\s*学分\s*[，,]\s*选修\s*(\d+(?:\.\d+)?)\s*学分\s*[，,]\s*总学分\s*[：:]\s*(\d+(?:\.\d+)?)\s*学分")
    m = pattern.search(text)
    if m:
        return float(m.group(1)), float(m.group(2)), float(m.group(3))
    return None, None, None


def parse_credit_req(cell: str):
    """从「学分要求 必修：6 学分，选修：0 学分」提取必修/选修学分。"""
    cell = (cell or "").replace("：", ":").replace("，", ",")
    m = re.search(r"必修\s*[:：]\s*(\d+(?:\.\d+)?)", cell)
    req = float(m.group(1)) if m else None
    m = re.search(r"选修\s*[:：]\s*(\d+(?:\.\d+)?)", cell)
    elec = float(m.group(1)) if m else None
    return req, elec


def normalize_header(header_row):
    """根据表头列名返回每列语义索引。"""
    # 用 row[0]（合并后的一整行）做关键词匹配
    flat = " ".join(str(c or "") for c in header_row)
    flat = flat.replace("\n", " ")
    cols = {}
    # 遍历实际单元格
    for i, cell in enumerate(header_row):
        if cell is None:
            continue
        c = str(cell).replace("\n", "").replace(" ", "")
        if "课程号" in c or "课程代码" in c:
            cols["code"] = i
        elif "课程名称" in c:
            cols["name"] = i
        elif "学分" == c:
            cols["credit"] = i
        elif "考核方式" in c:
            cols["exam"] = i
        elif "开课学期" in c:
            cols["semester"] = i
        elif "修读要求" in c:
            cols["type"] = i
    return cols


def extract_pdf(pdf_path: Path):
    """提取一个 PDF 的课程和学分要求。"""
    major = pdf_path.stem.replace("培养方案-", "")
    courses = []
    req_bx_sum = 0.0
    req_xx_sum = 0.0
    total_bx = None
    total_xx = None
    total_z = None

    with pdfplumber.open(pdf_path) as pdf:
        full_text = "\n".join((pg.extract_text() or "") for pg in pdf.pages)
        total_bx, total_xx, total_z = extract_total_credits(full_text)

        for pg in pdf.pages:
            tables = pg.extract_tables() or []
            for tb in tables:
                if not tb or len(tb) < 2:
                    continue
                # 判断是不是课程表：第一行必须有「课程号」+「课程名称」
                header = " ".join(str(c or "") for c in tb[0])
                if "课程号" not in header or "课程名称" not in header:
                    continue

                cols = normalize_header(tb[0])
                if not all(k in cols for k in ("code", "name", "credit", "semester", "type")):
                    # 尝试更宽松的列定位：只要有课程号/名称/学分/开课学期/修读要求就行
                    continue

                for row in tb[2:]:
                    if not row or not row[0]:
                        continue
                    first = str(row[0]).strip().replace("\n", "")

                    # 学分要求汇总行
                    if "学分要求" in first or (len(row) > 1 and "学分要求" in str(row[1])):
                        cell = " ".join(str(c or "") for c in row)
                        bx, xx = parse_credit_req(cell)
                        if bx is not None:
                            req_bx_sum += bx
                        if xx is not None:
                            req_xx_sum += xx
                        continue

                    # 课程行：第一格应为课程代码
                    if not re.match(r"^[A-Za-z]\d{6,}", first):
                        continue

                    code = first
                    name = str(row[cols["name"]] or "").replace("\n", " ").strip()
                    try:
                        credit = float(str(row[cols["credit"]] or "0").strip())
                    except ValueError:
                        continue
                    sem_raw = str(row[cols["semester"]] or "").strip()
                    type_raw = str(row[cols["type"]] or "").strip()

                    # 模块：必修/选修
                    if "必修" in type_raw:
                        module = "必修课"
                    elif "选修" in type_raw:
                        module = "选修课"
                    else:
                        module = "未知"

                    # 开课学期拆分为多个学期
                    sems = re.split(r"[,，]", sem_raw)
                    for s in sems:
                        s = s.strip()
                        if s in SEM_MAP:
                            courses.append({
                                "课程代码": code,
                                "课程名称": name,
                                "学分": credit,
                                "所属模块": module,
                                "开课学期": SEM_MAP[s],
                                "先修课": "",
                                "专业": major,
                                "年级": 2024,
                            })

    return {
        "major": major,
        "total_bx": total_bx,
        "total_xx": total_xx,
        "total_z": total_z,
        "req_bx_sum": req_bx_sum,
        "req_xx_sum": req_xx_sum,
        "courses": courses,
    }


def main():
    results = []
    all_courses = []
    for name in NEW_MAJORS:
        pdf = RAW_DIR / f"{name}.pdf"
        if not pdf.exists():
            print(f"[!] 缺失 {pdf.name}")
            continue
        print(f"正在处理 {pdf.name} ...")
        r = extract_pdf(pdf)
        results.append(r)
        all_courses.extend(r["courses"])

    # 汇总表
    print("\n========== 学分要求汇总 ==========")
    print(f"{'专业':<30} {'PDF必修':<10} {'PDF选修':<10} {'PDF总':<10} {'课程数':<10}")
    for r in results:
        print(f"{r['major']:<30} {str(r['total_bx']):<10} {str(r['total_xx']):<10} {str(r['total_z']):<10} {len(r['courses']):<10}")

    # 写 requirements
    req_rows = []
    for r in results:
        bx = r["total_bx"] if r["total_bx"] else r["req_bx_sum"]
        xx = r["total_xx"] if r["total_xx"] else r["req_xx_sum"]
        req_rows.append({
            "专业": r["major"],
            "年级": 2024,
            "模块名称": "必修课",
            "要求学分": bx,
            "最低选修学分": 0,
            "备注": f"含通识、数理、专业基础及核心课（含实践环节），总学分{r['total_z']}"
        })
        req_rows.append({
            "专业": r["major"],
            "年级": 2024,
            "模块名称": "选修课",
            "要求学分": 0,
            "最低选修学分": xx,
            "备注": f"需修满{xx}学分"
        })

    req_df = pd.DataFrame(req_rows)
    out_req = STRUCT_DIR / "_extracted_requirements.csv"
    req_df.to_csv(out_req, index=False, encoding="utf-8-sig")
    print(f"\n已写出 {out_req}")

    # 写 courses
    if all_courses:
        course_df = pd.DataFrame(all_courses)
        # 去重：同一专业、同一课程代码、同一开课学期
        course_df = course_df.drop_duplicates(subset=["专业", "课程代码", "开课学期"])
        out_course = STRUCT_DIR / "_extracted_courses.csv"
        course_df.to_csv(out_course, index=False, encoding="utf-8-sig")
        print(f"已写出 {out_course}，共 {len(course_df)} 行")
    else:
        print("未提取到课程")


if __name__ == "__main__":
    main()
