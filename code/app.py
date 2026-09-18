"""选课军师 · Streamlit 前端 Demo。

启动：
    python -m streamlit run app.py
"""

import pandas as pd
import streamlit as st

import config
from diagnose import diagnose

st.set_page_config(page_title="选课军师", page_icon="🎓", layout="wide")

# ============ 侧边栏：专业 / 年级（三个功能共用） ============
@st.cache_data(show_spinner=False)
def _load_req():
    return pd.read_csv(config.DATA_STRUCT / "requirements.csv", comment="#")


try:
    _req = _load_req()
    _profs = sorted(_req["专业"].dropna().unique().tolist())
    _grades = sorted(_req["年级"].dropna().unique().tolist(), reverse=True)
except Exception as _e:
    _profs, _grades = [], []
    st.sidebar.error(f"读取培养方案规则表失败：{_e}\n\n请先运行 python diagnose.py --template")

with st.sidebar:
    st.header("🎓 选课军师")
    st.caption("学业规划 AI 助手 · 逐光队")
    st.divider()
    _def = "数据科学与大数据技术"
    prof = st.selectbox("专业", _profs,
                        index=_profs.index(_def) if _def in _profs else 0)
    grade = st.selectbox("年级", _grades, index=0) if _grades else 2025
    st.caption(f"已收录 **{len(_profs)}** 个专业的培养方案规则")
    st.divider()
    try:
        _d0 = diagnose(prof, grade)
        if "error" not in _d0:
            st.metric("毕业要求总学分", _d0["总要求"])
    except Exception:
        pass

# ============ 主区标题 ============
st.title("选课军师")
st.caption(f"把几百页的培养方案，变成会聊天、会算学分、会排课的 AI 助手　|　"
           f"当前：**{prof} · {grade} 级**")

tab_qa, tab_diag, tab_rec, tab_about = st.tabs(
    ["📚 方案问答", "🎯 学分诊断", "🗓️ 选课建议", "ℹ️ 关于"])

# ---------------- 方案问答 ----------------
with tab_qa:
    st.subheader("问培养方案里的任何问题")
    st.caption("每条回答都会附上原文出处（文件 · 章节 · 页码）；"
               "超出培养方案范围的问题会明确拒答，不会编造。")

    if "history" not in st.session_state:
        st.session_state.history = []

    _examples = [
        f"{prof}专业毕业需要多少总学分？",
        f"{prof}专业的选修课要修满多少学分？",
        f"{prof}专业的实践环节包含哪些内容？",
        "英才班和普通班的学分要求有什么区别？",
    ]
    st.markdown("**试试这些问题：**")
    _cols = st.columns(2)
    for _i, _ex in enumerate(_examples):
        if _cols[_i % 2].button(_ex, key=f"ex{_i}", use_container_width=True):
            st.session_state.qa_input = _ex
            st.rerun()

    q = st.text_input("输入你的问题",
                      placeholder=f"例：{prof}专业毕业最低学分是多少？",
                      key="qa_input")

    if st.button("提问", type="primary") and q.strip():
        import rag
        with st.spinner("正在检索培养方案…"):
            res = rag.answer_question(q.strip())
        st.session_state.history.insert(0, (q.strip(), res))

    if not st.session_state.history:
        st.info("👆 点击上方任意一个示例问题，或在输入框里打字后点「提问」。")

    for question, res in st.session_state.history:
        st.markdown(f"**你：** {question}")
        if res["rejected"]:
            st.warning("🤔 " + res["answer"])
        else:
            st.success(res["answer"])
        if res.get("cites"):
            with st.expander(f"📎 查看原文出处（{len(res['cites'])} 条）"):
                for c in res["cites"]:
                    st.markdown(f"**[{c['n']}]** `{c['source']}` · "
                                f"{c['chapter']} · 第 {c['page']} 页")
        st.divider()

# ---------------- 学分诊断 ----------------
with tab_diag:
    st.subheader("看看你还差多少学分能毕业")
    st.caption("专业与年级在**左侧边栏**切换；成绩单可在下方上传。")

    up = st.file_uploader("上传你的成绩单（CSV，可选）", type=["csv"],
                          help="表头需为：课程代码,课程名称,学分,所属模块,学期,成绩。"
                               "不上传则使用内置样例成绩单。")
    if up is not None:
        st.info(f"已选择文件：{up.name}（接入解析中，当前仍按样例成绩单计算）")

    if st.button("开始诊断", type="primary"):
        with st.spinner("正在比对培养方案…"):
            d = diagnose(prof, grade)
        if "error" in d:
            st.error(d["error"])
        else:
            c1, c2, c3 = st.columns(3)
            c1.metric("毕业要求总学分", d["总要求"])
            c2.metric("已修学分", d["已修"])
            c3.metric("待修学分", d["总缺口"], delta=f"-{d['总缺口']}",
                      delta_color="inverse")

            st.divider()
            for m in d["模块明细"]:
                st.markdown(f"**{m['模块']}** — 已修 {m['已修']} / 要求 {m['要求']}"
                            f"　·　缺口 {m['缺口']} 学分")
                st.progress(min(m["达成率"] / 100, 1.0),
                            text=f"达成率 {m['达成率']}%")
            if d["风险提示"]:
                st.warning("\n".join("· " + r for r in d["风险提示"]))
            st.caption("⚠️ 当前成绩单为样例数据，仅用于功能演示；"
                       "正式使用时请上传本人成绩单。")

# ---------------- 选课建议 ----------------
with tab_rec:
    st.subheader("下学期该选哪些课")
    st.caption("推荐逻辑：先修课已通过 → 缺口大的模块优先 → 必修优先于选修 → "
               "单学期总学分控制在 18–24 之间。")

    try:
        _courses_all = pd.read_csv(config.DATA_STRUCT / "courses.csv", comment="#")
        _courses_prof = _courses_all[_courses_all["专业"] == prof]
        if _courses_prof.empty:
            st.info(f"课程库中暂无「{prof}」的开课数据，"
                    f"下方结果基于示例课程库（{len(_courses_all)} 门）生成。")
    except Exception:
        pass

    semester = st.text_input("学期", value="2026秋")
    if st.button("生成建议", type="primary"):
        import recommend as rm
        with st.spinner("正在计算课程组合…"):
            r = rm.recommend(semester, prof, grade)
        if "error" in r:
            st.error(r["error"])
        elif not r["推荐课程"]:
            st.warning("没有符合条件的课程。请检查课程库中是否有该专业、"
                       "该学期的开课数据，或先修课是否已通过。")
        else:
            st.success(f"推荐 {len(r['推荐课程'])} 门课，"
                       f"合计 {r['总学分']} 学分（建议区间 18–24）")
            st.dataframe(pd.DataFrame(r["推荐课程"]),
                         use_container_width=True, hide_index=True)
            st.markdown("**推荐理由**")
            for c in r["推荐课程"][:5]:
                why = []
                if c["所属模块"] == "必修课":
                    why.append("必修课，须优先完成")
                if c["缺口"] > 0:
                    why.append(f"所属模块尚缺 {c['缺口']} 学分")
                if c["重修"]:
                    why.append("此前未通过，需重修")
                st.markdown(f"- **{c['课程名称']}**（{c['学分']} 学分）："
                            f"{'；'.join(why) or '满足选课条件'}")
            if r["说明"]:
                for s in r["说明"]:
                    st.info(s)
            st.caption("⚠️ 课程库为示例数据，待替换为本院真实开课计划。")

# ---------------- 关于 ----------------
with tab_about:
    st.subheader("关于本项目")
    st.markdown(f"""
**选课军师** —— 学业规划 AI 助手

2026 年第二届重庆市 AI 大模型创新应用大赛 · 企业出题赛道 · 阿里出题「创意 AI 校园」

**参赛团队：** 逐光队（重庆邮电大学）
**团队成员：** 钟浩文、周婧妍、古雯茜
**指导教师：** 曾巧林

**技术栈：** 阿里云百炼 qwen-plus（对话）· text-embedding-v3（向量，1024 维）·
numpy 混合检索 · pandas · Streamlit

---

### 三层防幻觉机制

| 层级 | 位置 | 做法 |
|---|---|---|
| 检索层 | `rag.answer_question` | 最高相似度低于 {config.SCORE_THRESHOLD} 直接拒答 |
| 生成层 | `rag.SYSTEM_PROMPT` | 温度 0.1，限定「只能用给定资料」，按编号标注来源 |
| 校验层 | `verify.guard` | 回答中的每个数字与课程名回召回原文核验，不通过即降级为拒答 |

### 引用溯源

`ingest.py` 在切片阶段即按章节标题切分，并为每个片段打上
`source / chapter / page` 元数据，使「一个片段 ≈ 一条完整规则」；
`rag.py` 将片段编号后送入 Prompt，要求模型以 `[1] [2]` 标注来源，
最终反解编号还原为可核对的出处清单。

### 当前数据覆盖

已收录 **{len(_profs)}** 个专业（{grade} 级）培养方案学分规则：
{'、'.join(_profs) if _profs else '（待载入）'}
""")