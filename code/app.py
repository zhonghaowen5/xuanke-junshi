"""选课军师 · Streamlit 前端 Demo。

启动：
    python -m streamlit run app.py

合并说明（2026-09-19）：
    UI 主体来自周婧妍的版本（侧边栏专业切换、示例问题按钮、成绩单上传、关于页），
    并合入专业路由能力：问答页新增「仅查询左侧专业」开关，
    开启时若问题未提及任何已收录专业，自动把侧边栏选中的专业名拼进问题，
    确保检索命中正确专业的培养方案，避免跨专业串味。
"""

import random

import pandas as pd
import streamlit as st

import config
from diagnose import diagnose

st.set_page_config(page_title="选课军师", page_icon="🎓", layout="wide")

# 隐藏 Streamlit 默认菜单、页脚、页眉，使 Demo 和视频更干净
st.markdown(
    """
    <style>
    #MainMenu, footer, header {visibility: hidden;}
    .block-container {padding-top: 2rem;}
    </style>
    """,
    unsafe_allow_html=True,
)

# ============ 侧边栏：专业选择（三个功能共用） ============
@st.cache_data(show_spinner=False)
def _load_req():
    return pd.read_csv(config.DATA_STRUCT / "requirements.csv", comment="#")


try:
    _req = _load_req()
    _profs = sorted(_req["专业"].dropna().unique().tolist())
    _grades = sorted(_req["年级"].dropna().unique().tolist(), reverse=True)
except Exception as _e:
    _profs, _grades = [], []
    st.sidebar.error(f"读取培养方案规则表失败：{_e}\n\n请检查 requirements.csv")


# ============ 成绩单上传：解析逻辑见 transcript.py ============
from transcript import TRA_TEMPLATE, parse_transcript

with st.sidebar:
    st.header("🎓 选课军师")
    st.caption("学业规划 AI 助手 · 逐光队")
    st.divider()
    _def = "数据科学与大数据技术+经济学联合培养"
    prof = st.selectbox("专业", _profs,
                        index=_profs.index(_def) if _def in _profs else 0)
    # 年级不下拉：规则表默认采用当前执行的培养方案（现行为 2024 版），
    # 作品说明中表述为「每年根据各学院政策维护数据库」。
    grade = int(_grades[0]) if _grades else 2024
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
           f"当前：**{prof}**（现行培养方案）")

tab_qa, tab_diag, tab_rec, tab_about = st.tabs(
    ["📚 方案问答", "🎯 学分诊断", "🗓️ 选课建议", "ℹ️ 关于"])

# ---------------- 方案问答 ----------------
with tab_qa:
    st.subheader("问培养方案里的任何问题")
    st.caption("每条回答都会附上原文出处（文件 · 章节 · 页码）；"
               "超出培养方案范围的问题会明确拒答，不会编造。")

    if "history" not in st.session_state:
        st.session_state.history = []

    # 推荐问题候选池：全部是可被系统正确回答的事实性问题
    _EXAMPLE_QUESTIONS = [
        "{prof}专业毕业需要多少总学分？",
        "{prof}专业的选修课要修满多少学分？",
        "{prof}专业的必修课要修满多少学分？",
        "{prof}专业的实践环节包含哪些内容？",
        "计算机科学文峰班毕业需要多少总学分？",
        "软件工程英才班毕业需要多少总学分？",
        "智能机器人英才班毕业需要多少总学分？",
        "数据科学与大数据技术英才班毕业需要多少总学分？",
    ]

    # 用 session_state 保持当前 4 条推荐索引，避免每次 rerun 都跳动
    if "qa_example_idx" not in st.session_state:
        st.session_state.qa_example_idx = random.sample(
            range(len(_EXAMPLE_QUESTIONS)), 4)

    _examples = [
        _EXAMPLE_QUESTIONS[i].format(prof=prof)
        for i in st.session_state.qa_example_idx
    ]

    _h1, _h2 = st.columns([4, 1])
    with _h1:
        st.markdown("**试试这些问题：**")
    with _h2:
        if st.button("🔄 换一批", key="refresh_examples"):
            st.session_state.qa_example_idx = random.sample(
                range(len(_EXAMPLE_QUESTIONS)), 4)
            st.rerun()

    _cols = st.columns(2)
    for _i, _ex in enumerate(_examples):
        if _cols[_i % 2].button(_ex, key=f"ex{_i}", use_container_width=True):
            st.session_state.qa_input = _ex
            st.rerun()

    qa_lock = st.checkbox(
        "🔒 仅查询左侧选中的专业",
        value=True, key="qa_lock",
        help="开启后：问题里没写专业名时，自动按左侧选中的专业检索，"
             "避免答成别的专业。想看多专业对比（如「英才班和普通班有什么区别」），"
             "请取消勾选。")

    q = st.text_input("输入你的问题",
                      placeholder=f"例：{prof}专业毕业最低学分是多少？",
                      key="qa_input")

    if st.button("提问", type="primary") and q.strip():
        import rag
        ask = q.strip()
        # 专业路由：开启限定且问题未指向任何具体专业时，
        # 自动拼上侧边栏专业名，保证检索命中正确专业的培养方案。
        # 注意：问题里出现「专业 / 班」等字眼说明用户在指某个具体专业
        # （哪怕是未收录的，如软件工程），此时不拼接，交给拒答机制处理
        if qa_lock and prof:
            mentions_specific = (rag._match_major(ask) is not None
                                 or any(k in ask for k in ("专业", "班")))
            if not mentions_specific:
                ask = f"{prof}专业的{ask}"
        with st.spinner("正在检索培养方案…"):
            res = rag.answer_question(ask)
        st.session_state.history.insert(0, (ask, res))

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
    st.caption("专业在**左侧边栏**切换；成绩单可在下方上传。")

    up = st.file_uploader("上传你的成绩单（CSV，可选）", type=["csv"],
                          help="表头需为：课程代码,课程名称,学分,所属模块,学期,成绩。"
                               "不上传则使用内置演示成绩单。")
    st.download_button(
        "📥 下载成绩单模板（用 Excel 照着填）",
        data=("\ufeff" + TRA_TEMPLATE).encode("utf-8"),
        file_name="成绩单模板.csv", mime="text/csv",
        help="下载后用 Excel 打开，把你的课程填进去，另存为 CSV 再上传。")

    tra_df = None
    if up is not None:
        try:
            tra_df = parse_transcript(up.getvalue())
        except ValueError as e:
            st.error(f"❌ 成绩单解析失败：{e}")
        else:
            st.success(f"✅ 已读取 **{len(tra_df)} 门课程**，"
                       "诊断和选课建议将按你上传的成绩单计算")
            unknown = set(tra_df["所属模块"]) - {"必修课", "选修课"}
            if unknown:
                st.warning("成绩单里有不属于「必修课 / 选修课」的模块："
                           f"{'、'.join(sorted(unknown))}，"
                           "这些学分不会计入诊断结果。")
            with st.expander("预览解析后的成绩单"):
                st.dataframe(tra_df, use_container_width=True, hide_index=True)

    if st.button("开始诊断", type="primary"):
        with st.spinner("正在比对培养方案…"):
            d = diagnose(prof, grade, tra_df)
        st.session_state["diag"] = d          # 存下来，供导出报告使用
        st.session_state["diag_prof"] = prof
        st.session_state["diag_grade"] = grade
        if "error" in d:
            st.error(d["error"])
        else:
            c1, c2, c3 = st.columns(3)
            c1.metric("毕业要求总学分", d["总要求"])
            c2.metric("已修学分", d["已修"])
            c3.metric("待修学分", d["总缺口"], delta=f"-{d['总缺口']}",
                      delta_color="inverse")

            st.divider()

            # ---- 可视化：总学分完成度环形图 + 各模块达成率柱状图 ----
            try:
                import altair as alt

                _donut_df = pd.DataFrame({
                    "状态": ["已修", "待修"],
                    "学分": [d["已修"], d["总缺口"]],
                })
                _donut = alt.Chart(_donut_df).mark_arc(innerRadius=68).encode(
                    theta=alt.Theta("学分:Q", stack=True),
                    color=alt.Color(
                        "状态:N",
                        scale=alt.Scale(domain=["已修", "待修"],
                                        range=["#10B981", "#E5E7EB"]),
                        legend=alt.Legend(orient="bottom", title=None),
                    ),
                    tooltip=["状态:N", "学分:Q"],
                ).properties(width=250, height=250, title="总学分完成度")

                _mod_df = pd.DataFrame([
                    {"模块": m["模块"], "达成率": m["达成率"],
                     "已修": m["已修"], "要求": m["要求"], "缺口": m["缺口"]}
                    for m in d["模块明细"]
                ])
                _bar = alt.Chart(_mod_df).mark_bar(cornerRadiusEnd=4).encode(
                    x=alt.X("达成率:Q", scale=alt.Scale(domain=[0, 100]),
                            title="达成率 (%)"),
                    y=alt.Y("模块:N", sort="-x", title=None),
                    color=alt.value("#2563EB"),
                    tooltip=["模块:N", "已修:Q", "要求:Q", "缺口:Q", "达成率:Q"],
                ).properties(height=44 * max(len(_mod_df), 1),
                             title="各模块达成率")

                _lc, _rc = st.columns([1, 1.3])
                with _lc:
                    st.altair_chart(_donut, use_container_width=True)
                with _rc:
                    st.altair_chart(_bar, use_container_width=True)
            except Exception as _ve:
                st.caption(f"（图表渲染跳过：{_ve}）")

            for m in d["模块明细"]:
                st.markdown(f"**{m['模块']}** — 已修 {m['已修']} / 要求 {m['要求']}"
                            f"　·　缺口 {m['缺口']} 学分")
                st.progress(min(m["达成率"] / 100, 1.0),
                            text=f"达成率 {m['达成率']}%")
            if d["风险提示"]:
                st.warning("\n".join("· " + r for r in d["风险提示"]))
            st.caption("📊 数据来源：" +
                       ("**你上传的成绩单**" if tra_df is not None
                        else "内置演示成绩单（可在上方上传你自己的）"))

            try:
                from report import build_html
                _html_d = build_html(prof, grade, d)
                st.download_button(
                    "📄 导出学分诊断报告（HTML，可打印为 PDF）",
                    data=_html_d.encode("utf-8"),
                    file_name=f"学分诊断报告-{prof}.html",
                    mime="text/html",
                    help="下载后用浏览器打开，按 Ctrl+P 即可另存为 PDF。")
            except Exception as _re:
                st.caption(f"（报告导出不可用：{_re}）")

# ---------------- 选课建议 ----------------
with tab_rec:
    st.subheader("下学期该选哪些课")
    st.caption("推荐逻辑：先修课已通过 → 缺口大的模块优先 → 必修优先于选修 → "
               "单学期总学分控制在 18–24 之间。")

    _courses_prof_empty = False
    try:
        _courses_all = pd.read_csv(config.DATA_STRUCT / "courses.csv", comment="#")
        _courses_prof = _courses_all[_courses_all["专业"] == prof]
        if _courses_prof.empty:
            _courses_prof_empty = True
            st.info(f"课程库中暂无「{prof}」的开课数据，"
                    f"下方结果基于全部课程库（{len(_courses_all)} 门）生成。")
    except Exception:
        pass

    semester = st.text_input("学期", value="2026秋")
    if tra_df is not None:
        st.caption("ℹ️ 将按你在「学分诊断」页上传的成绩单判断先修课与重修。")
    if st.button("生成建议", type="primary"):
        import recommend as rm
        with st.spinner("正在计算课程组合…"):
            r = rm.recommend(semester, prof, grade, tra_df=tra_df)
        if "error" in r:
            st.error(r["error"])
        elif not r["推荐课程"]:
            st.warning("没有符合条件的课程。请检查课程库中是否有该专业、"
                       "该学期的开课数据，或先修课是否已通过。")
        else:
            st.session_state["rec"] = r
            st.session_state["rec_sem"] = semester
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
            if not _courses_prof_empty:
                st.caption("课程库为真实开课计划数据（2026 秋）。")

            # ---- 导出个人学业规划报告 ----
            st.divider()
            _d = st.session_state.get("diag")
            if _d and "error" not in _d:
                try:
                    from report import build_html
                    _html = build_html(
                        st.session_state.get("diag_prof", prof),
                        st.session_state.get("diag_grade", grade),
                        _d, rec=r, semester=semester)
                    st.download_button(
                        "📄 导出个人学业规划报告（HTML，可打印为 PDF）",
                        data=_html.encode("utf-8"),
                        file_name=f"学业规划报告-{prof}-{semester}.html",
                        mime="text/html",
                        help="下载后用浏览器打开，按 Ctrl+P 即可另存为 PDF。")
                except Exception as _re:
                    st.caption(f"（报告导出不可用：{_re}）")
            else:
                st.caption("ℹ️ 先在「学分诊断」页点一次「开始诊断」，"
                           "即可导出含诊断 + 选课建议的完整报告。")

# ---------------- 关于 ----------------
with tab_about:
    # 动态统计当前知识库规模，避免文案随数据更新而过时
    _n_pdfs = 0
    try:
        _n_pdfs = len(list(config.DATA_RAW.glob("*.pdf")))
    except Exception:
        pass
    _n_chunks = 0
    try:
        with open(config.DATA_CHUNKS / "chunks.jsonl", "r", encoding="utf-8") as _cf:
            for _ in _cf:
                _n_chunks += 1
    except Exception:
        pass

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

### 四层防幻觉机制

| 层级 | 位置 | 做法 |
|---|---|---|
| 路由层 | `rag._match_major` | 问题提及专业时只在对应专业的切片内检索，杜绝跨专业「串味」 |
| 检索层 | `rag.answer_question` | 最高相似度低于 {config.SCORE_THRESHOLD} 直接拒答 |
| 生成层 | `rag.SYSTEM_PROMPT` | 温度 0.1，限定「只能用给定资料」，按编号标注来源 |
| 校验层 | `verify.guard` | 回答中的每个数字与课程名回召回原文核验，不通过即降级为拒答 |

### 引用溯源

`ingest.py` 在切片阶段即按章节标题切分，并为每个片段打上
`source / chapter / page` 元数据，使「一个片段 ≈ 一条完整规则」；
`rag.py` 将片段编号后送入 Prompt，要求模型以 `[1] [2]` 标注来源，
最终反解编号还原为可核对的出处清单。

### 当前数据覆盖

已收录 **{_n_pdfs} 份培养方案 / {_n_chunks} 个切片**，
以及 **{len(_profs)} 个专业**的现行培养方案学分规则表：
{'、'.join(_profs) if _profs else '（待载入）'}

培养方案数据每年随各学院政策更新而维护，确保查询结果与学校现行方案一致。
""")
