"""全局配置：路径、模型、超参数。

所有需要调整的参数都集中在这里，避免散落在各个文件中。
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# 用绝对路径读取本文件同级的 .env。
# 这样无论从哪个目录启动脚本，都能正确读到配置
# （否则在别的目录运行时会读不到 Key，报「未配置」）
ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")

# ---------- 阿里云百炼（OpenAI 兼容模式） ----------
API_KEY = os.getenv("DASHSCOPE_API_KEY", "")
BASE_URL = os.getenv(
    "DASHSCOPE_BASE_URL",
    "https://dashscope.aliyuncs.com/compatible-mode/v1",
)
LLM_MODEL = os.getenv("LLM_MODEL", "qwen-plus")
EMBED_MODEL = os.getenv("EMBED_MODEL", "text-embedding-v3")

# ---------- 目录 ----------
DATA_RAW = ROOT / "data" / "raw"          # 原始 PDF
DATA_CHUNKS = ROOT / "data" / "chunks"    # 切片结果 chunks.jsonl
DATA_INDEX = ROOT / "data" / "index"      # 向量索引 vectors.npz
DATA_STRUCT = ROOT / "data" / "structured"  # 结构化规则表 / 成绩单
EVAL_DIR = ROOT / "eval"                  # 评测题库与结果

for _p in (DATA_RAW, DATA_CHUNKS, DATA_INDEX, DATA_STRUCT, EVAL_DIR):
    _p.mkdir(parents=True, exist_ok=True)

# ---------- 检索超参数 ----------
TOP_K = 5                 # 送进模型的片段数
SCORE_THRESHOLD = 0.35    # 低于该相似度直接判定为「知识库外问题」→ 拒答

# ---------- 切片参数 ----------
MIN_CHUNK_CHARS = 60      # 过短的片段并入上一块
MAX_CHUNK_CHARS = 1200    # 超长条款强制二次切分

# ---------- 拒答话术（统一口径，便于统计拒答率） ----------
REJECT_MSG = (
    "抱歉，这个问题在我的培养方案资料里查不到依据，为避免误导我不做推测。"
    "建议向教务处或学院教学秘书确认。"
)
