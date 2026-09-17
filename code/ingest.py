"""文档解析 + 条款级切片。

设计要点（这是本作品引用溯源能成立的前提）：
  1. 不按固定字数切片，而是按「章节标题」切 —— 培养方案的知识单元天然是条款和表格；
  2. 每个 chunk 强制携带 source / chapter / page 三个元数据字段，全链路不丢失；
  3. 超长条款按行二次切分，但继承同一份元数据。

用法：
    python ingest.py                      # 处理 data/raw 下所有 PDF
    python ingest.py --file 某培养方案.pdf  # 只处理指定文件
"""

import argparse
import json
import re
from pathlib import Path

import pdfplumber

import config

# 章节标题识别规则，按需补充
HEADING_PATTERNS = [
    r"^第[一二三四五六七八九十百]+[章节部分]",       # 第三章 / 第二节
    r"^[一二三四五六七八九十]+[、.．]",              # 一、学分要求
    r"^\d+\.\d+(\.\d+)?\s*\S",                       # 3.2 课程设置
    r"^（[一二三四五六七八九十]+）",                   # （一）必修课
    r"^附录\s*[A-Za-z一二三四五六七八九十]",         # 附录 B
]


def is_heading(line: str) -> bool:
    line = line.strip()
    if not line or len(line) > 40:
        return False
    return any(re.match(p, line) for p in HEADING_PATTERNS)


def extract_pages(pdf_path: Path):
    """逐页提取文本 + 表格，返回 [(页码, 文本行列表)]。"""
    pages = []
    with pdfplumber.open(pdf_path) as pdf:
        for idx, page in enumerate(pdf.pages, start=1):
            lines = []
            text = page.extract_text() or ""
            lines.extend(text.split("\n"))

            # 表格单独处理：转成用 | 分隔的文本行，避免内容丢失
            for table in page.extract_tables() or []:
                for row in table:
                    cells = [(c or "").replace("\n", " ").strip() for c in row]
                    if any(cells):
                        lines.append("| " + " | ".join(cells) + " |")
            pages.append((idx, lines))
    return pages


def split_long(text: str, max_chars: int):
    """超长条款按行二次切分，尽量在行边界断开。"""
    if len(text) <= max_chars:
        return [text]
    out, buf = [], ""
    for line in text.split("\n"):
        if len(buf) + len(line) + 1 > max_chars and buf:
            out.append(buf)
            buf = line
        else:
            buf = f"{buf}\n{line}" if buf else line
    if buf:
        out.append(buf)
    return out


def build_chunks(pdf_path: Path):
    """把一份 PDF 切成带元数据的条款块。"""
    pages = extract_pages(pdf_path)
    chunks = []
    cur_chapter = "正文"
    buf = []
    buf_page = 1

    def flush():
        nonlocal buf
        text = "\n".join(buf).strip()
        if not text:
            buf = []
            return
        for piece in split_long(text, config.MAX_CHUNK_CHARS):
            chunks.append({
                "source": pdf_path.name,
                "chapter": cur_chapter,
                "page": buf_page,
                "text": piece,
            })
        buf = []

    for page_no, lines in pages:
        for line in lines:
            if is_heading(line):
                flush()
                cur_chapter = line.strip()
                buf_page = page_no
            else:
                if not buf:
                    buf_page = page_no
                buf.append(line)
        # 跨页时合并过短的内容，避免产生大量碎片
    flush()

    # 合并过短的块（提高检索片段的完整性）
    merged = []
    for c in chunks:
        if merged and len(c["text"]) < config.MIN_CHUNK_CHARS \
                and merged[-1]["chapter"] == c["chapter"]:
            merged[-1]["text"] += "\n" + c["text"]
        else:
            merged.append(c)
    return merged


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", help="只处理指定文件名")
    args = ap.parse_args()

    pdfs = sorted(config.DATA_RAW.glob("*.pdf"))
    if args.file:
        pdfs = [p for p in pdfs if p.name == args.file]
    if not pdfs:
        print(f"[!] {config.DATA_RAW} 下没有找到 PDF，请先把培养方案放进去")
        return

    all_chunks = []
    for pdf in pdfs:
        cs = build_chunks(pdf)
        all_chunks.extend(cs)
        print(f"[+] {pdf.name}: {len(cs)} 块")

    out = config.DATA_CHUNKS / "chunks.jsonl"
    with out.open("w", encoding="utf-8") as f:
        for c in all_chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    print(f"\n共 {len(all_chunks)} 块 → {out}")
    print("\n抽样预览：")
    for c in all_chunks[:3]:
        print(f"  [{c['source']} · {c['chapter']} · P{c['page']}] {c['text'][:60]}...")


if __name__ == "__main__":
    main()
