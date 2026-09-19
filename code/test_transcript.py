# -*- coding: utf-8 -*-
"""成绩单上传功能测试：模拟各种用户上传场景。"""
import sys
import pandas as pd

from transcript import parse_transcript
from diagnose import diagnose
from recommend import recommend

PROF = "数据科学与大数据技术+经济学联合培养"
ok = 0
fail = 0

def check(name, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  [PASS] {name} {extra}")
    else:
        fail += 1
        print(f"  [FAIL] {name} {extra}")

print("== 1. 正常 UTF-8 成绩单（含等级制成绩）==")
csv_ok = ("课程代码,课程名称,学分,所属模块,学期,成绩\n"
          "A1100015,形势与政策,1,必修课,2024秋,82\n"
          "A2040100,数据库原理(双语),4,必修课,2025春,45\n"
          "B2101234,人工智能导论,2,选修课,2025春,优秀\n"
          "B2999,劳动教育,1,通识课,2024秋,合格\n")
tra = parse_transcript(csv_ok.encode("utf-8"))
check("解析出 4 行", len(tra) == 4)
check("「优秀」映射为 95", float(tra.loc[tra["课程名称"] == "人工智能导论", "成绩"].iloc[0]) == 95.0)
check("「合格」映射为 75", float(tra.loc[tra["课程名称"] == "劳动教育", "成绩"].iloc[0]) == 75.0)

print("== 2. GBK 编码成绩单（教务系统常见导出格式）==")
csv_gbk = csv_ok.encode("gbk")
tra2 = parse_transcript(csv_gbk)
check("GBK 正常解析", len(tra2) == 4)

print("== 3. 格式错误场景（应给出中文报错而非崩溃）==")
for name, content in [
    ("缺列", "课程代码,课程名称,学分\nX1,数学,3\n"),
    ("学分非数字", "课程代码,课程名称,学分,所属模块,学期,成绩\nX1,数学,三,必修课,2024秋,80\n"),
    ("成绩无法识别", "课程代码,课程名称,学分,所属模块,学期,成绩\nX1,数学,3,必修课,2024秋,pass\n"),
    ("空文件", "课程代码,课程名称,学分,所属模块,学期,成绩\n"),
]:
    try:
        parse_transcript(content.encode("utf-8"))
        check(f"{name} 报错", False, "（竟然没报错！）")
    except ValueError as e:
        check(f"{name} 报错", True, f"→ {str(e)[:40]}…")

print("== 4. 诊断结果：上传成绩单 vs 内置成绩单 ==")
d_up = diagnose(PROF, 2024, tra_df=tra)
d_in = diagnose(PROF, 2024)
# 上传：必修通过 1(形势)；数据库原理45分不及格不计；选修「优秀」2；通识1不计
bx = [m for m in d_up["模块明细"] if m["模块"] == "必修课"][0]
xx = [m for m in d_up["模块明细"] if m["模块"] == "选修课"][0]
check("必修已修=1（数据库原理45分不及格不计）", bx["已修"] == 1.0, f"实际 {bx['已修']}")
check("选修已修=2（优秀计2分）", xx["已修"] == 2.0, f"实际 {xx['已修']}")
check("有重修风险提示", any("未通过" in r for r in d_up["风险提示"]))
check("与内置成绩单(57分)结果不同", d_up["已修"] != d_in["已修"],
      f"上传 {d_up['已修']} vs 内置 {d_in['已修']}")

print("== 5. 推荐结果：按上传成绩单判断重修 ==")
r = recommend("2026秋", PROF, 2024, tra_df=tra)
retake = [c["课程名称"] for c in r["推荐课程"] if c["重修"]]
check("推荐正常返回", "推荐课程" in r and len(r["推荐课程"]) > 0,
      f"共 {len(r['推荐课程'])} 门 {r['总学分']} 学分")
check("数据库原理(45分)出现在重修列表", "数据库原理(双语)" in retake, f"重修：{retake}")

print(f"\n结果：{ok} 通过 / {fail} 失败")
sys.exit(1 if fail else 0)
