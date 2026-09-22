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
5. 问题中提及的专业、学校若与资料所属专业不符（例如询问其他专业的培养方案或学分），
   必须回答「资料不足，无法回答」，严禁用资料中本专业的数据冒充其他专业的答案；
6. 若问题询问的是学校整体信息（如学院数量、校区、排名、就业率、校历等），
   而资料只涉及本专业培养方案，必须回答「资料不足，无法回答」，
   不得根据资料中出现的个别学院、单位或课程进行推断；
7. 每条资料开头的「来源」标注了该资料所属的专业（即培养方案文件名）。
   若问题指明了具体专业，只能使用来源与该专业一致的资料作答，
   来源不符的资料一律不得引用；若资料中没有与问题专业一致的内容，回答「资料不足，无法回答」；
8. 不要复述规则本身，直接给出结论。"""

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


def _major_names():
    """从 data/raw 的 PDF 文件名提取已收录专业名（去掉『培养方案-』前缀），
    按长度降序排列，便于对问题做最长匹配。"""
    import re as _re
    names = []
    for f in sorted(config.DATA_RAW.glob("*.pdf")):
        n = _re.sub(r"^培养方案[-－]?", "", f.stem)
        names.append(n)
    return sorted(set(names), key=len, reverse=True)


# 常见口头称呼 → 标准 PDF 专业名。
# 例如用户说"计算机科学与技术文峰班"（按学院名习惯），实际对应 PDF《计算机科学文峰班》。
_MAJOR_ALIASES = {
    "计算机科学与技术文峰班": "计算机科学文峰班",
    "计算机科学与技术文峰实验班": "计算机科学文峰班",
    "计算机文峰班": "计算机科学文峰班",
    "计科文峰班": "计算机科学文峰班",
    # 口语里常把「智能科学与技术新工科英才班」简写成「英才班（新工科）」
    "英才班（新工科）": "智能科学与技术新工科英才班",
    "新工科英才班": "智能科学与技术新工科英才班",
}


def _match_major(question: str):
    """判断问题是否明确提到了某个已收录专业，返回专业名（用于 source 过滤）或 None。
    微专业允许省略「（微专业）」后缀来匹配。"""
    # 0. 先处理已知的口头别名，避免被「计算机科学与技术」这类更短专业名截断。
    for alias, canonical in _MAJOR_ALIASES.items():
        if alias in question:
            return canonical
    for m in _major_names():
        if m in question or m.replace("（微专业）", "") in question:
            return m
    return None


def retrieve(question: str, top_k: int = config.TOP_K, source_filter: str = None):
    return _get_index().search(question, top_k, source_filter=source_filter)


def answer_question(question: str, top_k: int = config.TOP_K):
    """返回 dict：answer / cites / rejected / issues / retrieved"""
    # 规范化口头别名：让 LLM 看到的问题专业名与资料来源文件名一致，
    # 避免模型因「计算机科学与技术文峰班」≠「计算机科学文峰班」而自行拒答。
    original_question = question
    for alias, canonical in _MAJOR_ALIASES.items():
        if alias in question:
            question = question.replace(alias, canonical)
            break

    # 第 0 层防护：专业路由 —— 问题明确提到某专业时，
    # 直接在该专业的切片内检索（source 过滤），避免被其他专业挤出 top-k。
    # 注意：检索用的问题要把专业名剔除，避免长专业名稀释真正的问题语义；
    # 专业信息已通过 source 过滤表达，无需重复出现在检索 query 里。
    major = _match_major(question)
    if major:
        # 把专业名的两种写法（带/不带「（微专业）」后缀）都从检索 query 里剔除
        q_retrieve = question
        for token in (major, major.replace("（微专业）", "")):
            q_retrieve = q_retrieve.replace(token, "")
        q_retrieve = (q_retrieve.replace("（微专业）", "")
                      .replace("（专业）", "")
                      .replace("（）", "").strip() or question)
        hits = retrieve(q_retrieve, top_k + 3, source_filter=major)
        if not hits:
            return {
                "answer": config.REJECT_MSG,
                "cites": [],
                "rejected": True,
                "reason": f"问题所问专业「{major}」不在资料来源中",
                "retrieved": [],
            }
    else:
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
        f"[{i + 1}] （来源：{c['source']} · {c['chapter']} · P{c['page']}）\n{c['text']}"
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

    # 模型遵循 Prompt 规则自行说出拒答话术时，同样视为拒答（统一标志位）
    explicit_reject = any(p in final for p in ("资料不足", "无法回答"))
    rejected = (not ok) or explicit_reject

    # 从原始回答中提取 [n] 引用标记，映射回对应的召回片段
    # 注意：ctx_text 中的编号是 [1..len(contexts)]，直接用 n-1 访问
    import re as _re
    cites = []
    for n in sorted({int(x) for x in _re.findall(r"\[(\d+)\]", raw)}):
        if 1 <= n <= len(contexts):
            c = contexts[n - 1]
            cites.append({"n": n, "source": c["source"],
                          "chapter": c["chapter"], "page": c["page"]})

    return {
        "answer": final,
        "cites": sorted(cites, key=lambda x: x["n"]),
        "rejected": rejected,
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
