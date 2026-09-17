"""后验数字校验 —— 本作品的核心防幻觉机制。

思路：模型生成的回答里，凡是「数字」和「课程名」这类硬事实，
都要回过头去召回片段里核对。核对不上就降级为拒答。

为什么必须做这一步：
  Prompt 里写「不许编造」只能降低幻觉概率，不能消除。
  把「模型自愿引用」变成「系统强制核验」，才真正兜住底。
"""

import re

import config

NUM_RE = re.compile(r"\d+(?:\.\d+)?")
COURSE_RE = re.compile(r"《([^》]{2,30})》")

# 书名号里出现的「非课程名」：文件类词汇，不应参与课程名校验
# 否则「根据《培养方案》…」会被误判为编造课程名 → 造成大量误拒
DOC_WORDS = ("培养方案", "方案", "通知", "规定", "办法", "细则", "大纲",
             "手册", "文件", "报告", "标准", "条例", "制度", "意见",
             "指南", "章程", "说明", "目录", "清单")


def _extract_numbers(text: str):
    return set(NUM_RE.findall(text))


def _looks_like_course(name: str) -> bool:
    """排除文件名类词汇，只留下疑似课程名。"""
    return not any(w in name for w in DOC_WORDS)


def _extract_courses(text: str):
    return {c for c in COURSE_RE.findall(text) if _looks_like_course(c)}


def verify(answer: str, contexts):
    """校验回答中的硬事实是否能在召回片段中找到依据。

    contexts: [{"text": ..., "chapter": ..., "page": ...}, ...]

    返回 (是否通过, 问题列表)
    """
    haystack = "\n".join(c["text"] for c in contexts)
    issues = []

    # 1) 数字校验：回答中出现的每个数字都应能在原文找到
    ans_nums = _extract_numbers(answer)
    ctx_nums = _extract_numbers(haystack)
    bad_nums = {n for n in ans_nums if n not in ctx_nums}
    # 过滤掉序号类小数字（1/2/3 等引用编号）造成的误报
    bad_nums = {n for n in bad_nums if len(n) > 1 or float(n) > 10}
    if bad_nums:
        issues.append(f"数字无法在原文找到依据：{sorted(bad_nums)}")

    # 2) 课程名校验
    bad_courses = _extract_courses(answer) - _extract_courses(haystack)
    # 课程名可能不带书名号出现，退化为子串检查
    bad_courses = {c for c in bad_courses if c not in haystack}
    if bad_courses:
        issues.append(f"课程名无法在原文找到依据：{sorted(bad_courses)}")

    return (len(issues) == 0), issues


def guard(answer: str, contexts):
    """校验不通过时，返回统一拒答话术。"""
    ok, issues = verify(answer, contexts)
    if ok:
        return answer, True, []
    return config.REJECT_MSG, False, issues


if __name__ == "__main__":
    ctx = [{"text": "软件工程专业毕业最低总学分为 170 学分，其中必修课 120 学分。",
            "chapter": "第三章 学分要求", "page": 12}]

    a1 = "根据《培养方案》，软件工程专业毕业最低总学分为 170 学分。"
    a2 = "根据《培养方案》，软件工程专业毕业最低总学分为 185 学分。"

    for a in (a1, a2):
        print(f"回答：{a}")
        print("  →", guard(a, ctx)[1:], "\n")
