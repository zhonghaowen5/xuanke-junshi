"""成绩单解析：把用户上传的 CSV 转成 diagnose / recommend 可用的 DataFrame。

设计要点：
  - 编码兼容：依次尝试 utf-8-sig → gbk → utf-8（国内教务系统导出多为 GBK）；
  - 列校验：表头必须包含 6 列，缺列给出中文报错；
  - 成绩兼容：百分制数字，或五级制/两级制（优秀/良好/…/不合格）自动映射；
  - 所有错误抛 ValueError，由前端 st.error 展示，不会崩掉整个应用。

成绩单模板见 TRA_TEMPLATE，可在前端「下载成绩单模板」获取。
"""

import io

import pandas as pd

TRA_COLS = ["课程代码", "课程名称", "学分", "所属模块", "学期", "成绩"]

# 五级制 / 两级制成绩 → 百分制（≥60 视为通过）
GRADE_MAP = {"优秀": 95, "良好": 85, "中等": 75, "及格": 65,
             "合格": 75, "不合格": 0, "不及格": 0}

TRA_TEMPLATE = (
    "课程代码,课程名称,学分,所属模块,学期,成绩\n"
    "A1100015,形势与政策,1,必修课,2024秋,82\n"
    "A2041720,经济数学分析I,5,必修课,2024秋,75\n"
    "B2101234,人工智能导论,2,选修课,2025春,90\n"
)


def _score(v):
    """把单个成绩值转成 float；无法识别返回 None。"""
    if pd.isna(v):
        return None
    s = str(v).strip()
    if s in GRADE_MAP:
        return float(GRADE_MAP[s])
    try:
        return float(s)
    except ValueError:
        return None


def parse_transcript(raw: bytes) -> pd.DataFrame:
    """解析上传的成绩单 CSV（bytes）→ 干净的 DataFrame。

    格式不符时抛 ValueError，错误信息直接面向用户（中文）。"""
    df = None
    for enc in ("utf-8-sig", "gbk", "utf-8"):
        try:
            df = pd.read_csv(io.BytesIO(raw), encoding=enc)
            break
        except UnicodeDecodeError:
            continue
    if df is None:
        raise ValueError("文件编码无法识别，请用 Excel 打开后另存为「CSV UTF-8」再试。")
    if df.empty:
        raise ValueError("文件是空的，请检查是否填入了课程数据。")

    # 列名清洗：去 BOM、去首尾空格
    df.columns = [str(c).strip().lstrip("\ufeff") for c in df.columns]
    missing = [c for c in TRA_COLS if c not in df.columns]
    if missing:
        raise ValueError(
            f"缺少列：{'、'.join(missing)}。"
            f"表头必须包含：{'、'.join(TRA_COLS)}。"
            "可点「下载成绩单模板」查看格式。")
    df = df[TRA_COLS].copy()

    # 学分必须能转成数字
    df["学分"] = pd.to_numeric(df["学分"], errors="coerce")
    bad_credit = df[df["学分"].isna()]
    if not bad_credit.empty:
        raise ValueError(
            f"有 {len(bad_credit)} 行的「学分」不是数字，"
            f"例如「{bad_credit.iloc[0]['课程名称']}」这一行。"
            "请修改后重新上传。")

    # 成绩：百分制或等级制
    scores = df["成绩"].map(_score)
    bad = df[scores.isna() & df["成绩"].notna()]
    if not bad.empty:
        example = bad.iloc[0]
        raise ValueError(
            f"「成绩」列有无法识别的值：「{example['课程名称']}」的成绩是"
            f"「{example['成绩']}」。请填百分制数字（60 及格），"
            "或 优秀/良好/中等/及格/合格/不合格。")
    df["成绩"] = scores.fillna(0)  # 缺成绩按 0 处理（视为未通过）

    # 文本列去空格
    df["所属模块"] = df["所属模块"].astype(str).str.strip()
    df["课程名称"] = df["课程名称"].astype(str).str.strip()
    return df
