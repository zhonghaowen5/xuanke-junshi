"""向量化 + 本地混合检索。

为什么用 numpy 而不是向量数据库：
  7 天工期下，几百到几千个 chunk 用 numpy 算余弦相似度完全够用（毫秒级），
  且零安装成本。后期要换成阿里云 DashVector 只需替换 search() 的实现。

混合检索 = 向量相似度 + 关键词命中加权。
  纯向量检索对「课程代码」「具体学分数字」这类精确查询容易失手，
  关键词加权能补上这一块。
"""

import json
import re

import numpy as np
from openai import OpenAI

import config

_client = OpenAI(api_key=config.API_KEY, base_url=config.BASE_URL)


def embed(texts, batch_size: int = 10):
    """批量向量化，返回 (n, dim) 的 float32 数组。"""
    vecs = []
    for i in range(0, len(texts), batch_size):
        batch = [t[:2000] for t in texts[i:i + batch_size]]  # 单条截断，防超长
        resp = _client.embeddings.create(model=config.EMBED_MODEL, input=batch)
        vecs.extend([d.embedding for d in resp.data])
        print(f"    向量化 {min(i + batch_size, len(texts))}/{len(texts)}", end="\r")
    print()
    arr = np.asarray(vecs, dtype=np.float32)
    # 归一化，后续用点积即余弦相似度
    norm = np.linalg.norm(arr, axis=1, keepdims=True)
    return arr / np.clip(norm, 1e-8, None)


def _tokens(text: str):
    """中英混合的简易分词：中文按 2-gram，英文/数字按词。"""
    text = text.lower()
    words = re.findall(r"[a-z0-9]+", text)
    cjk = re.findall(r"[\u4e00-\u9fff]", text)
    grams = ["".join(cjk[i:i + 2]) for i in range(max(len(cjk) - 1, 0))]
    return set(words + grams + cjk)


def build_index():
    """读取 chunks.jsonl，生成向量索引并落盘。"""
    src = config.DATA_CHUNKS / "chunks.jsonl"
    if not src.exists():
        raise SystemExit(f"[!] 找不到 {src}，请先运行 python ingest.py")

    chunks = [json.loads(l) for l in src.open(encoding="utf-8") if l.strip()]
    print(f"[*] 共 {len(chunks)} 个片段，开始向量化…")
    vecs = embed([c["text"] for c in chunks])

    out = config.DATA_INDEX / "vectors.npz"
    np.savez_compressed(out, vectors=vecs, texts=np.array(
        [c["text"] for c in chunks], dtype=object))
    (config.DATA_INDEX / "meta.jsonl").write_text(
        "\n".join(json.dumps(c, ensure_ascii=False) for c in chunks),
        encoding="utf-8")

    print(f"[+] 索引已保存 → {out}")


class Index:
    """加载一次，反复检索。"""

    def __init__(self):
        vec_file = config.DATA_INDEX / "vectors.npz"
        meta_file = config.DATA_INDEX / "meta.jsonl"
        if not vec_file.exists():
            raise SystemExit("[!] 索引不存在，请先运行 python vectorstore.py build")
        data = np.load(vec_file, allow_pickle=True)
        self.vectors = data["vectors"]
        self.meta = [json.loads(l) for l in meta_file.open(encoding="utf-8")]
        self.tokens = [_tokens(m["text"]) for m in self.meta]

    def search(self, query: str, top_k: int = config.TOP_K):
        """返回 [(相似度, 元数据), ...]，按混合得分降序。"""
        qv = embed([query])[0]
        vec_score = self.vectors @ qv                      # 余弦相似度

        q_tok = _tokens(query)
        # 关键词命中率：查询词中有多少比例出现在该片段里
        kw_score = np.array([
            len(q_tok & t) / max(len(q_tok), 1) for t in self.tokens
        ], dtype=np.float32)

        # 混合：向量为主，关键词为辅
        score = 0.7 * vec_score + 0.3 * kw_score
        order = np.argsort(-score)[:top_k]
        return [(float(score[i]), self.meta[i], float(vec_score[i])) for i in order]


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "build":
        build_index()
    else:
        idx = Index()
        q = sys.argv[1] if len(sys.argv) > 1 else "毕业最低学分是多少"
        print(f"[查询] {q}\n")
        for s, m, v in idx.search(q):
            print(f"  {s:.3f} (向量 {v:.3f}) | {m['chapter']} · P{m['page']}")
            print(f"    {m['text'][:90]}...")
