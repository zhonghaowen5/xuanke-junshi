"""从结构化课程表自动生成评测题库补充题目。

用法：
    python eval/gen_questions.py

功能：
1. 读取 data/structured/courses.csv，为每门课生成 5 类事实题
   （学分 / 学期 / 模块 / 先修课 / 课程代码）
2. 追加 30 道固定的超纲拒答题
3. 自动去重（与 questions.csv 中已有题目比对）
4. 事实题 id 从 51 起递增，拒答题 id 从 121 起递增
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

import config

COURSES = config.DATA_STRUCT / "courses.csv"
QBANK = config.EVAL_DIR / "questions.csv"

# ---------------------------------------------------------------- 事实题生成

FACT_TEMPLATES = [
    ("{name}是多少学分", lambda r: f"{r['学分']}学分"),
    ("{name}开课学期是哪一学期", lambda r: str(r["开课学期"])),
    ("{name}属于必修课还是选修课", lambda r: str(r["所属模块"])),
    ("{name}的先修课是什么", lambda r: str(r["先修课"]) if str(r["先修课"]).strip() else "无先修课"),
    ("{name}的课程代码是什么", lambda r: str(r["课程代码"])),
]

# ---------------------------------------------------------------- 拒答题题库

REJECT_EXTRA = [
    "重庆邮电大学的校训是什么",
    "学校的占地面积有多大",
    "学校有多少个学院",
    "学校有多少名教职工",
    "学校有几个校区",
    "学校的邮政编码是多少",
    "学校的官网网址是什么",
    "学校的招生办电话是多少",
    "学校的就业率是多少",
    "学校的排名是多少",
    "学校的校历是怎么安排的",
    "学校的校车时刻表是什么",
    "学校的校医院地址在哪里",
    "学校的体育馆开放时间是什么",
    "学校的游泳池收费标准是多少",
    "学校的毕业典礼是什么时候",
    "学校的开学典礼是什么时候",
    "学校的军训时长是几周",
    "学校的选课系统网址是什么",
    "学校的教务处办公时间是什么",
    "学校的成绩绩点怎么计算",
    "学校的学生会联系方式是什么",
    "学校的社团有哪些",
    "学校的宿舍是几人间",
    "学校的宿舍有没有空调",
    "学校的宿舍收费标准是多少",
    "学校的奖学金有哪些种类",
    "学校的助学贷款怎么申请",
    "学校的勤工俭学岗位有哪些",
    "学校的校车路线有哪些",
    "学校的食堂哪家最好吃",
    "学校的考研率是多少",
    "学校的就业去向有哪些",
    "学校的国际合作项目有哪些",
    "学校的交换生政策是什么",
    "学校的毕业证和学位证什么时候发",
    "学校的学位授予条件是什么",
    "学校的学位英语要求是什么",
    "学校的学士学位类型有哪些",
    "学校的研究生专业有哪些",
]


def main():
    if not COURSES.exists():
        raise SystemExit(f"[!] 找不到课程表 {COURSES}")

    courses = pd.read_csv(COURSES, dtype=str).fillna("")
    qbank = pd.read_csv(QBANK, dtype=str).fillna("")

    exist_q = set(qbank["question"].astype(str).str.strip())
    new_rows = []

    # ---- 事实题：从课程表生成 ----
    fact_id = 51
    for _, r in courses.iterrows():
        name = str(r["课程名称"]).strip()
        if not name:
            continue
        for tpl, ans_fn in FACT_TEMPLATES:
            q = tpl.format(name=name)
            if q in exist_q:
                continue
            a = ans_fn(r)
            if not a:
                continue
            new_rows.append({
                "id": fact_id, "type": "fact",
                "question": q, "standard_answer": a, "source": "六、指导性教学计划进程",
            })
            exist_q.add(q)
            fact_id += 1

    # ---- 拒答题：固定题库 ----
    rej_id = 121
    for q in REJECT_EXTRA:
        if q in exist_q:
            continue
        new_rows.append({
            "id": rej_id, "type": "reject",
            "question": q, "standard_answer": "", "source": "",
        })
        exist_q.add(q)
        rej_id += 1

    if not new_rows:
        print("[*] 没有新题需要添加")
        return

    out = pd.concat([qbank, pd.DataFrame(new_rows)], ignore_index=True)
    out.to_csv(QBANK, index=False, encoding="utf-8-sig")
    n_fact = sum(1 for x in new_rows if x["type"] == "fact")
    n_rej = sum(1 for x in new_rows if x["type"] == "reject")
    print(f"[+] 新增事实题 {n_fact} 道，拒答题 {n_rej} 道")
    print(f"[+] 题库总量：{len(out)} 道 → {QBANK}")


if __name__ == "__main__":
    main()
