"""选课军师 · Streamlit 前端 Demo。

启动：
    streamlit run app.py
"""

import streamlit as st

st.set_page_config(page_title="选课军师", page_icon="🎓", layout="wide")

st.title("选课军师")
st.caption("把几百页的培养方案，变成会聊天、会算学分、会排课的 AI 助手")

tab_qa, tab_diag, tab_rec, tab_about = st.tabs(
    ["方案问答", "学分诊断", "选课建议", "关于"])

# ---------------- 方案问答 ----------------
with tab_qa:
    st.subheader("问培养方案里的任何问题")
    st.caption("每条回答都会附上原文出处；回答不了的问题会明确拒答，不会编造。")

    if "history" not in st.session_state:
        st.session_state.history = []

    qa_prof = st.text_input(
        "你问的是哪个专业（可留空）",
        value="数据科学与大数据技术+经济学联合培养",
        help="已收录：数据科学与大数据技术+经济学联合培养、数据科学与大数据技术（含英才班）、"
             "人工智能、智能科学与技术（含新工科英才班）、机器人工程、智能机器人英才班，"
             "以及 HarmonyOS技术与应用、具身智能机器人应用开发、智能机器人设计与开发、"
             "行业大数据挖掘及应用等微专业",
        key="qa_prof")

    q = st.text_input("输入你的问题",
                      placeholder="例：人工智能专业毕业最低学分是多少？",
                      key="qa_input")

    if st.button("提问", type="primary") and q.strip():
        import rag
        # 用户填了专业且问题里没写专业名时，自动拼上，保证检索到正确专业的资料
        ask = q.strip()
        if qa_prof.strip() and qa_prof.strip() not in ask:
            ask = f"{qa_prof.strip()}专业的{ask}"
        with st.spinner("正在检索培养方案…"):
            res = rag.answer_question(ask)
        st.session_state.history.insert(0, (ask, res))

    for question, res in st.session_state.history:
        st.markdown(f"**你：** {question}")
        if res["rejected"]:
            st.warning(res["answer"])
        else:
            st.success(res["answer"])
        if res.get("cites"):
            with st.expander("查看原文出处"):
                for c in res["cites"]:
                    st.markdown(f"**[{c['n']}]** `{c['source']}` · "
                                f"{c['chapter']} · 第 {c['page']} 页")
        st.divider()

# ---------------- 学分诊断 ----------------
with tab_diag:
    st.subheader("看看你还差多少学分能毕业")
    col1, col2 = st.columns(2)
    prof = col1.text_input("专业", value="数据科学与大数据技术+经济学联合培养")
    grade = col2.number_input("年级", value=2024, step=1)

    if st.button("开始诊断", type="primary"):
        import diagnose as dm
        with st.spinner("正在比对培养方案…"):
            d = dm.diagnose(prof, grade)
        if "error" in d:
            st.error(d["error"])
        else:
            c1, c2, c3 = st.columns(3)
            c1.metric("毕业要求总学分", d["总要求"])
            c2.metric("已修学分", d["已修"])
            c3.metric("待修学分", d["总缺口"])

            for m in d["模块明细"]:
                st.markdown(f"**{m['模块']}** — 已修 {m['已修']} / 要求 {m['要求']}")
                st.progress(min(m["达成率"] / 100, 1.0),
                            text=f"达成率 {m['达成率']}%")
            if d["风险提示"]:
                st.warning("\n".join("· " + r for r in d["风险提示"]))

# ---------------- 选课建议 ----------------
with tab_rec:
    st.subheader("下学期该选哪些课")
    semester = st.text_input("学期", value="2026秋")
    if st.button("生成建议", type="primary"):
        import recommend as rm
        with st.spinner("正在计算课程组合…"):
            r = rm.recommend(semester)
        if "error" in r:
            st.error(r["error"])
        else:
            st.success(f"推荐 {len(r['推荐课程'])} 门课，合计 {r['总学分']} 学分")
            import pandas as pd
            st.dataframe(pd.DataFrame(r["推荐课程"]),
                         use_container_width=True, hide_index=True)
            st.markdown(rm.render(r).split("推荐理由：")[-1])

# ---------------- 关于 ----------------
with tab_about:
    st.subheader("关于本项目")
    st.markdown("""
**选课军师** —— 学业规划 AI 助手

2026 年第二届重庆市 AI 大模型创新应用大赛 · 企业出题赛道 · 阿里出题「创意 AI 校园」

**参赛团队：** 逐光队（重庆邮电大学）
**团队成员：** 钟浩文、周婧妍、古雯茜
**指导教师：** 曾巧林

**技术栈：** 阿里云百炼（通义千问）· text-embedding-v3 · LangChain · Streamlit

**核心机制：** 引用溯源 + 后验数字校验。回答中的每个数字与课程名都会回到召回原文中核验，
核验不通过则降级为拒答。
""")
