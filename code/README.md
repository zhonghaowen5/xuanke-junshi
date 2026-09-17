# 选课军师 · 代码说明

把几百页的培养方案，变成会聊天、会算学分、会排课的 AI 助手。

2026 年第二届重庆市 AI 大模型创新应用大赛 · 企业出题赛道 · 阿里出题「创意 AI 校园」

---

## 一、环境准备

### 方式 A：一键配置（推荐，新手首选）

```bash
python setup.py
```

脚本会依次自动完成：检查 Python 版本 → 检测并安装缺失依赖 → 创建 `.env`
→ 引导粘贴 API Key → 联网验证 Key 与两个模型。

全程只需粘贴一次 Key，不需要手动编辑任何配置文件。

### 方式 B：手动逐步（进阶）

```bash
# 1. 进入代码目录
cd code

# 2. 创建虚拟环境（Python 3.10+）
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS / Linux:
source .venv/bin/activate

# 3. 安装依赖
pip install -r requirements.txt

# 4. 配置 API Key
copy .env.example .env      # Windows
# cp .env.example .env      # macOS / Linux
# 编辑 .env，填入阿里云百炼的 API Key

# 5. 自检：确认 Key 与两个模型都能调通
python check_env.py
```

**API Key 获取：** 阿里云百炼控制台（https://bailian.console.aliyun.com/）→ API-KEY 管理 → 创建新的 API-KEY。

**赛题算力领取（大赛专属页）：** https://university.aliyun.com/action/creative-ai
完成阿里云学生认证后，300 元算力券自动发放。注意：学生身份有效期 30 天，券有效期 1 年，
券仅能在购买指定产品时抵扣且同一商品只抵扣一次 —— 攒着用在决赛部署上。
详细步骤与排错见同目录《逐光队-第0天环境准备指引》。

**⚠️ `.env` 含真实密钥，绝不能提交到仓库**（`.gitignore` 已排除）。

---

## 二、运行顺序

必须按以下顺序执行，后一步依赖前一步的产物。

```bash
# 第 1 步：把培养方案 PDF 放进 data/raw/
#         然后执行条款级切片
python ingest.py
#   产物：data/chunks/chunks.jsonl

# 第 2 步：向量化并建立索引
python vectorstore.py build
#   产物：data/index/vectors.npz + meta.jsonl

# 第 3 步：单测检索效果（可选，用于调参）
python vectorstore.py "毕业最低学分是多少"
python rag.py "软件工程专业毕业最低学分是多少"

# 第 4 步：准备结构化数据
python diagnose.py --template     # 生成规则表与成绩单模板
python recommend.py --template    # 生成课程库模板
#   然后照格式填入真实数据，放在 data/structured/

# 第 5 步：测试诊断与排课
python diagnose.py --profession 软件工程 --grade 2024
python recommend.py --semester 2026秋 --profession 软件工程 --grade 2024

# 第 6 步：测试 Agent 统一入口
python agent.py "我现在修了92学分，还差多少"

# 第 7 步：启动 Web Demo
streamlit run app.py
```

---

## 三、跑评测

```bash
# 先在 eval/questions.csv 建好题库（表头见文件内注释）
python eval/run_eval.py            # 跑全部
python eval/run_eval.py --only fact     # 只跑事实准确率
python eval/run_eval.py --only reject   # 只跑幻觉拒答率
python eval/run_eval.py --only ab       # 只跑引用溯源消融对比
#   产物：eval/results.json
```

---

## 四、目录结构

```
code/
├── setup.py           一键环境配置（装依赖 + 填 Key + 联网验证）★ 先跑这个
├── check_env.py       环境自检（单独验证 Key 与两个模型是否可用）
├── config.py          全局配置（路径、模型、超参数、拒答话术）
├── ingest.py          PDF 解析 + 条款级切片（引用溯源的地基）
├── vectorstore.py     向量化 + 向量/关键词混合检索
├── rag.py             RAG 问答主链路
├── verify.py          后验数字校验（核心防幻觉机制）
├── diagnose.py        学分进度诊断
├── recommend.py       排课建议
├── agent.py           意图识别 + 工具路由
├── app.py             Streamlit 前端
├── eval/
│   ├── run_eval.py    评测脚本
│   └── questions.csv  评测题库
└── data/
    ├── raw/           原始 PDF
    ├── chunks/        切片结果
    ├── index/         向量索引
    └── structured/    规则表 / 成绩单 / 课程库
```

---

## 五、核心设计说明

### 5.1 三层防幻觉机制

| 层级 | 位置 | 做法 |
|---|---|---|
| 检索层 | `rag.answer_question` | 最高相似度低于 `SCORE_THRESHOLD` 直接拒答 |
| 生成层 | `rag.SYSTEM_PROMPT` | 约束「只能用给定资料」，温度设为 0.1 |
| 校验层 | `verify.guard` | 回答中的数字与课程名回原文核验，不通过即降级为拒答 |

### 5.2 引用溯源为什么能成立

`ingest.py` 在切片阶段就给每个片段打上 `source / chapter / page` 元数据，
并且按章节标题切片（而非固定字数），使一个片段 ≈ 一条完整规则。
`rag.py` 再把片段编号后送进 Prompt，要求模型用 `[1] [2]` 标注来源，
最后从回答中反解编号、还原成可点击的出处清单。

### 5.3 常见问题

**Q：相似度阈值定多少合适？**
先用 `python vectorstore.py "一个问题"` 打印实际得分分布，再调 `config.SCORE_THRESHOLD`。
建议让「正常问题」最低分在 0.45 以上，「超纲问题」最高分在 0.3 以下，阈值取中间值。

**Q：想换成阿里云 DashVector？**
只需替换 `vectorstore.Index` 的 `__init__` 与 `search()` 两个方法，其余代码不用动。
当前用 numpy 是为了零安装成本，几千个片段下性能完全够用。

**Q：切片质量差怎么办？**
优先补 `ingest.HEADING_PATTERNS` 里的标题正则，适配本校培养方案的排版。
表格错位严重时，可先把关键页转成文本单独放入 `data/raw/`。

**Q：Windows 控制台输出中文乱码？**
Git Bash / CMD 默认用 GBK 解码，运行时加一个环境变量即可：

```bash
PYTHONIOENCODING=utf-8 python ingest.py
```

或在 PowerShell 中先执行 `$env:PYTHONIOENCODING="utf-8"`。

**Q：`verify.py` 会不会把正常回答误判为幻觉？**
`verify._looks_like_course` 会过滤掉「培养方案 / 通知 / 规定」这类文件名词汇，
避免把《培养方案》当成课程名。如果误拒率仍然偏高，在 `DOC_WORDS` 里继续补充即可。
