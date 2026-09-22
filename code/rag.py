"""RAG 问答链路：检索 → 生成 → 引用注入 → 后验校验。

这是产品的主链路，也是评测实验一的被测对象。

用法：
    python rag.py "软件工程专业毕业最低学分是多少"
"""

import re
import sys

from openai import OpenAI

import config
import verify
from vectorstore import Index, _normalize_source

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
8. 不要复述规则本身，直接给出结论。

精简规则（在满足以上 1-8 条的前提下必须遵守）：
9. 只给结论，不写推理过程，不解释资料本身：
   - 禁止出现「根据资料」「资料[N]中明确指出」「资料[N]显示」「综上所述」
     「该结论在…中得到印证」「（注：…）」以及对资料矛盾、统计误差、口径差异的分析；
   - 禁止说明「哪些资料没有提供相关信息」「哪些资料可佐证」；
    - 同一结论只写一次，禁止为了标注不同编号而把同一句话重复多遍；
    - 不得为压缩字数而省略关键限定词（如「联合」「最低」「必修」「双语」「新工科」等），
      这些词直接决定答案对错；
    - 名称类答案必须照抄资料中的完整名称（含前缀与修饰语）：
      资料写「联合学士学位」，就不能简写成「学士学位」；
    - 不要写「资料[N]」「根据资料」这类对资料本身的指代。
10. 长度控制：一般问题一句话作答，不超过 60 字；
    问题要求列举的（如「包含哪些」「有哪些」），每条一行、只写条目本身，不展开描述，总长不超过 200 字；
11. 引用标注：一个结论只标 1 个最相关的编号，写成 [N]；不要写 [1][2] 这类多编号，更不要为不同编号重复同一句话；
12. 规则 1-8 优先级高于规则 9-11：需要拒答时照常拒答，不得为了简洁而省略拒答话术。

拒答边界（即使资料里出现相关词句，也必须回答「资料不足，无法回答」）：
13. 问题没有指明任何具体专业（如「有哪些竞赛可以参加」「这个专业好就业吗」），
    资料只覆盖单个专业的培养方案，回答这类泛化问题会误导用户；
14. 比较类问题（如「A和B有什么区别」「哪个好」「哪个更难」），
    资料中没有同时描述双方并直接对比的段落时；
15. 主观评价、预测、建议类问题（就业前景、专业好不好、难不难、值不值得、该怎么选）；
16. 需要拒答时，直接说「资料不足，无法回答」即可，拒答话术由系统统一给出，
    你不要自行发挥、不要附加解释、建议、引导语。"""

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


# 模型常为标注不同来源而把同一句话重复多遍（如「X是必修课 [2]；X是必修课 [4]」）。
# 这里做一道程序化兜底：去掉引用编号与空白后完全相同的句子只保留首个版本。
_SENT_SPLIT = re.compile(r"[；;\n]+")
_CITE_RE = re.compile(r"\[\d+\]")


def _compact(answer: str) -> str:
    """剔除重复句，保证「只给结论」的精简效果稳定生效。"""
    seen = set()
    kept_lines = []
    for line in answer.split("\n"):
        parts = [p for p in _SENT_SPLIT.split(line) if p.strip()]
        kept = []
        for p in parts:
            key = re.sub(r"\s+", "", _CITE_RE.sub("", p)).rstrip("。.")
            if not key or key in seen:
                continue
            seen.add(key)
            kept.append(p.strip())
        if kept:
            kept_lines.append("；".join(kept))
    return "\n".join(kept_lines).strip()


# 「毕业/总学分」类问题的定向召回：这类答案只存在于「3、毕业学分要求」这类短小节里，
# 而向量检索常被长达数页的「教学计划进程」表格切片挤掉，导致明明有答案却拒答。
# 因此命中关键词时，按章节名把该小节强制补进召回结果。
_CREDIT_KW = ("毕业", "总学分", "最低学分", "毕业学分", "学分要求")
_CREDIT_CHAPTER_KW = ("毕业学分", "学分要求")


def _boost_credit_chunks(hits, major, question):
    """按章节名补召回「毕业学分要求」小节，返回补充后的 hits。"""
    if not major or not any(k in question for k in _CREDIT_KW):
        return hits
    idx = _get_index()
    seen = {h[1]["text"] for h in hits}
    extra = []
    for m in idx.meta:
        if _normalize_source(m["source"]) != major:
            continue
        if not any(k in m.get("chapter", "") for k in _CREDIT_CHAPTER_KW):
            continue
        if m["text"] in seen:
            continue
        seen.add(m["text"])
        extra.append((1.0, m, 1.0))   # 置顶，保证进入上下文并被引用
    return extra + hits


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

    # 定向补召回：学分类问题的答案常藏在「毕业学分要求」短小节里
    hits = _boost_credit_chunks(hits, major, question)

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
    # 精简兜底：去掉为标注不同来源而重复的同一句话
    raw = _compact(raw) or raw

    # 第三层防护：后验数字与课程名校验，不通过即降级为拒答
    final, ok, issues = verify.guard(raw, contexts)

    # 模型遵循 Prompt 规则自行说出拒答话术时，同样视为拒答（统一标志位）
    explicit_reject = any(p in final for p in ("资料不足", "无法回答"))
    rejected = (not ok) or explicit_reject

    # 模型自行拒答时，输出可能有长有短、还夹带建议；统一成标准话术，保证产品口径一致
    if rejected:
        final = config.REJECT_MSG

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
