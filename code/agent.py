"""Agent 编排层：意图识别 + 工具路由。

刻意保持轻量 —— 7 天工期下，一个稳定的分类器 + 三条工具链路，
比一套复杂的多轮规划器更可靠，也更容易在答辩时讲清楚。

工具：
  search_regulation   培养方案规则问答（RAG）
  diagnose_credits    学分进度诊断
  recommend_courses   选课建议
  reject              超纲问题统一拒答
"""

import json
import re

from openai import OpenAI

import config
import diagnose as diag_mod
import rag
import recommend as rec_mod

_client = OpenAI(api_key=config.API_KEY, base_url=config.BASE_URL)

INTENTS = ["search_regulation", "diagnose_credits", "recommend_courses"]

CLASSIFY_PROMPT = """判断用户问题的意图，只输出一个 JSON，不要任何额外文字。

可选意图：
- search_regulation：询问培养方案、课程要求、学分规则、毕业条件等「规则本身」
- diagnose_credits：询问「我的」学分进度、还差多少、能不能毕业
- recommend_courses：询问下学期选什么课、如何安排选课

示例：
问：软件工程专业毕业最低学分是多少？ → {"intent":"search_regulation"}
问：我现在修了92学分，还差多少？ → {"intent":"diagnose_credits"}
问：下学期我该优先选哪几门课？ → {"intent":"recommend_courses"}

用户问题：{question}"""

# 模型不可用时的兜底规则
KEYWORDS = {
    "diagnose_credits": ["我修了", "我目前", "还差多少", "能不能毕业", "我的学分",
                         "进度", "已修"],
    "recommend_courses": ["选什么课", "选课", "下学期选", "怎么安排", "推荐课程",
                          "下个学期"],
}


def classify(question: str) -> str:
    try:
        resp = _client.chat.completions.create(
            model=config.LLM_MODEL,
            messages=[{"role": "user",
                       "content": CLASSIFY_PROMPT.format(question=question)}],
            temperature=0,
        )
        raw = resp.choices[0].message.content
        m = re.search(r'\{[^}]*\}', raw)
        if m:
            intent = json.loads(m.group()).get("intent", "")
            if intent in INTENTS:
                return intent
    except Exception as e:      # 网络或额度问题 → 走兜底规则
        print(f"[warn] 意图识别调用失败，改用关键词兜底：{e}")

    for intent, kws in KEYWORDS.items():
        if any(k in question for k in kws):
            return intent
    return "search_regulation"


def run(question: str, profession: str = None, grade: int = None,
        semester: str = "2026秋"):
    """统一入口：识别意图 → 调用工具 → 返回结构化结果。"""
    intent = classify(question)

    if intent == "diagnose_credits":
        d = diag_mod.diagnose(profession, grade)
        if "error" in d:
            return {"intent": intent, "answer": d["error"], "cites": []}
        return {"intent": intent, "answer": diag_mod.render(d), "cites": []}

    if intent == "recommend_courses":
        r = rec_mod.recommend(semester, profession, grade)
        if "error" in r:
            return {"intent": intent, "answer": r["error"], "cites": []}
        return {"intent": intent, "answer": rec_mod.render(r), "cites": []}

    # 默认走 RAG 规则问答
    res = rag.answer_question(question)
    return {"intent": intent, "answer": res["answer"],
            "cites": res["cites"], "rejected": res["rejected"]}


def render(out):
    lines = [f"[意图] {out['intent']}", "", out["answer"]]
    if out.get("cites"):
        lines.append("\n出处：")
        for c in out["cites"]:
            lines.append(f"  [{c['n']}] {c['source']} · {c['chapter']} · 第 {c['page']} 页")
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    q = sys.argv[1] if len(sys.argv) > 1 else "软件工程专业毕业最低学分是多少"
    print(render(run(q)))
