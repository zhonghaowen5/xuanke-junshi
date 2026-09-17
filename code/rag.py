"""RAG 问答链路：检索 → 生成 → 引用注入 → 后验校验。

这是产品的主链路，也是评测实验一的被测对象。

用法：
    python rag.py "软件工程专业毕业最低学分是多少"
"""

import sys

from openai import OpenAI

import config
import verify
from vectorstore import Index

_client = OpenAI(api_key=config.API_KEY, base_url=config.BASE_URL)
_index = None

SYSTEM_PROMPT = """你是「选课军师」，一名严格依据给定资料回答学业规划问题的助手。

回答规则（必须严格遵守）：
1. 只能依据【资料】中的内容回答，不得使用任何资料之外的知识；
2. 每一条结论后面必须用 [编号] 标注来源，例如 [1]、[2]；
3. 资料中出现的学分、课程名、学期等具体信息，必须原样引用，不得改写或推算；
4. 如果资料不足以回答问题，直接回答「资料不足，无法回答」，不要做任何推测；
5. 不要复述规则本身，直接给出结论。"""

USER_TEMPLATE = """【资料】
{context}

【问题】
{question}

请依据上述资料回答，并在每条结论后标注来源编号。"""


def _get_index():
    global _index
    if _index is None:
        _index = Index()
    return _index


def retrieve(question: str, top_k: int = config.TOP_K):
    return _get_index().search(question, top_k)


def answer_question(question: str, top_k: int = config.TOP_K):
    """返回 dict：answer / cites / rejected / issues / retrieved"""
    hits = retrieve(question, top_k)

    # 第一层防护：检索相似度低于阈值 → 判定为知识库外问题，直接拒答
    if not hits or hits[0][0] < config.SCORE_THRESHOLD:
        return {
            "answer": config.REJECT_MSG,
            "cites": [],
            "rejected": True,
            "reason": f"最高相似度 {hits[0][0]:.3f} 低于阈值 {config.SCORE_THRESHOLD}",
            "retrieved": hits,
        }

    contexts = [h[1] for h in hits]
    ctx_text = "\n\n".join(
        f"[{i + 1}] （{c['chapter']} · P{c['page']}）\n{c['text']}"
        for i, c in enumerate(contexts)
    )

    # 第二层防护：Prompt 约束
    resp = _client.chat.completions.create(
        model=config.LLM_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": USER_TEMPLATE.format(
                context=ctx_text, question=question)},
        ],
        temperature=0.1,   # 低温度，降低发挥空间
    )
    raw = resp.choices[0].message.content.strip()

    # 第三层防护：后验数字与课程名校验，不通过即降级为拒答
    final, ok, issues = verify.guard(raw, contexts)

    cites = []
    for m in {i + 1 for i in (int(x) for x in
              __import__("re").findall(r"\[(\d+)\]", raw)) if 1 <= i <= len(contexts)}:
        c = contexts[m - 1]
        cites.append({"n": m, "source": c["source"],
                      "chapter": c["chapter"], "page": c["page"]})

    return {
        "answer": final,
        "cites": sorted(cites, key=lambda x: x["n"]),
        "rejected": not ok,
        "issues": issues,
        "retrieved": hits,
    }


def render(result):
    """把结果渲染成给人看的文本（含出处清单）。"""
    out = [result["answer"]]
    if result["cites"]:
        out.append("\n出处：")
        for c in result["cites"]:
            out.append(f"  [{c['n']}] {c['source']} · {c['chapter']} · 第 {c['page']} 页")
    if result.get("issues"):
        out.append(f"\n（已拦截：{'; '.join(result['issues'])}）")
    return "\n".join(out)


if __name__ == "__main__":
    q = sys.argv[1] if len(sys.argv) > 1 else "毕业最低学分是多少"
    print(f"[问题] {q}\n")
    print(render(answer_question(q)))
