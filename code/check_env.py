"""环境自检：验证百炼 API Key 与两个模型是否真的可用。

在 code/ 目录下运行：
    python check_env.py

它会依次检查：
    1. .env 里的 Key / 地址 / 模型名是否读到了
    2. 对话模型（qwen-plus）能否调通
    3. 向量模型（text-embedding-v3）能否调通，并打印向量维度

全部打 [OK] 才算步骤 0.2 完成。
"""

import sys

LINE = "=" * 62
SUB = "-" * 62


def _hint(err):
    """把常见报错翻译成下一步该干什么。"""
    name = type(err).__name__
    msg = str(err)
    low = msg.lower()
    print("    ---- 排查建议 ----")
    if "authentication" in low or "invalid_api_key" in low or "401" in low:
        print("    [Key 无效] 检查 .env 里的 DASHSCOPE_API_KEY 是否复制完整、")
        print("               是否在百炼控制台被删除。建议重新创建一个 Key。")
    elif "model" in low and ("not" in low or "exist" in low or "permission" in low):
        print("    [模型未开通] 去百炼控制台 → 模型广场，搜索该模型并开通；")
        print("                 或者模型名拼错了（注意是 text-embedding-v3）。")
    elif ("quota" in low or "balance" in low or "arrear" in low or "欠费" in msg
          or "余额不足" in msg
          or ("额度" in msg and ("消耗完" in msg or "用尽" in msg or "已用完" in msg))):
        print("    [额度不足] 阿里云/百炼账户余额或该模型免费额度不足。")
        print("               按下面顺序检查：")
        print("                 1. 百炼控制台 → 额度管理/费用中心，查看 qwen-plus、text-embedding-v3 是否还有免费额度；")
        print("                 2. 阿里云费用中心 → 卡券管理 → 优惠券，确认 300 元券是否到账；")
        print("                 3. 若免费额度用完，可点「立即充值」或在购买模型服务时勾选优惠券抵扣。")
    elif "workspace endpoint access denied" in low or "access_denied" in low:
        print("    [业务空间不匹配] 当前 Key 与 base_url 所属的业务空间不一致。")
        print("                   做法：")
        print("                   1. 先尝试把 .env 里的 DASHSCOPE_BASE_URL 改成通用地址：")
        print("                      https://dashscope.aliyuncs.com/compatible-mode/v1")
        print("                   2. 若仍报错，去百炼控制台 → API-KEY 管理，确认 Key 的")
        print("                      「所归属业务空间」和模型服务地址是否在同一空间；")
        print("                   3. 如不匹配，请在目标业务空间下重新创建 API-KEY。")
    elif "connect" in low or "timeout" in low or "ssl" in low or "proxy" in low:
        print("    [网络问题] 检查网络；若开了代理，确认能访问 dashscope.aliyuncs.com。")
    else:
        print("    [未知错误] 原始信息：", name, msg[:200])
    print("    完整报错已忽略，必要时把上面的信息发到赛事 QQ 群 1061821631 求助。")


def main():
    print(LINE)
    print("选课军师 · 环境自检（步骤 0.2 验收工具）")
    print(LINE)

    # ---------- 1. 配置 ----------
    try:
        import config
    except Exception as e:  # noqa: BLE001
        print("[X] 无法导入 config.py：", e)
        print("    请确认在 code/ 目录下运行本脚本，且已安装依赖：")
        print("    pip install -r requirements.txt")
        return 1

    key = config.API_KEY or ""
    if (not key) or ("替换" in key) or (not key.startswith("sk-")):
        print("[X] DASHSCOPE_API_KEY 尚未正确配置")
        print("    当前读到：", (key[:10] + "...") if key else "(空)")
        print("    做法：把 .env.example 复制成 .env，用记事本打开，")
        print("          把 sk-替换成你自己的Key 这一行改成真实 Key 后保存。")
        return 1

    print("[OK] 配置读取成功")
    print("     API Key  ：", key[:7] + "*" * 6 + key[-4:])
    print("     base_url ：", config.BASE_URL)
    print("     LLM      ：", config.LLM_MODEL)
    print("     Embedding：", config.EMBED_MODEL)
    print(SUB)

    try:
        from openai import OpenAI
    except ImportError:
        print("[X] 未安装 openai 库。请执行：pip install openai")
        return 1

    client = OpenAI(api_key=key, base_url=config.BASE_URL)

    # ---------- 2. 对话模型 ----------
    print("测试 1/2 · 对话模型", config.LLM_MODEL)
    try:
        resp = client.chat.completions.create(
            model=config.LLM_MODEL,
            messages=[{"role": "user", "content": "只回复两个字：通了"}],
            temperature=0,
        )
        print("[OK] 模型回复：", resp.choices[0].message.content.strip())
    except Exception as e:  # noqa: BLE001
        print("[X] 对话模型调用失败：", type(e).__name__)
        print("    原始信息：", str(e)[:300])
        _hint(e)
        return 1
    print(SUB)

    # ---------- 3. 向量模型 ----------
    print("测试 2/2 · 向量模型", config.EMBED_MODEL)
    try:
        resp = client.embeddings.create(model=config.EMBED_MODEL, input=["测试文本"])
        vec = resp.data[0].embedding
        print("[OK] 向量维度：", len(vec))
        print("     前 3 维：", [round(float(x), 4) for x in vec[:3]])
    except Exception as e:  # noqa: BLE001
        print("[X] 向量模型调用失败：", type(e).__name__)
        print("    原始信息：", str(e)[:300])
        _hint(e)
        return 1

    print(LINE)
    print("全部通过 — Key、对话模型、向量模型都可用。")
    print("步骤 0.2 完成，可以开始第 1 天的数据准备。")
    print(LINE)
    return 0


if __name__ == "__main__":
    sys.exit(main())
