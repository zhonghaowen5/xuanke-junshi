"""选课军师 · 一键环境配置（新手专用）

在【任意位置】都能运行，不需要先切换到 code 目录：

    A:\\Pyhton\\python.exe "C:\\Users\\zhong\\WorkBuddy\\2026-09-17-16-19-59\\逐光队-选课军师\\code\\setup.py"

它会自动帮你完成五件事：
    [1/5] 检查 Python 版本
    [2/5] 检查并安装缺失的依赖库
    [3/5] 创建 .env 配置文件
    [4/5] 引导你粘贴 API Key 并写入
    [5/5] 联网验证 Key、对话模型、向量模型

全程只需要你粘贴一次 API Key。
"""

import os
import subprocess
import sys
from pathlib import Path

# ---------- 让 Windows 控制台能正确显示中文 ----------
if sys.platform == "win32":
    os.system("chcp 65001 > nul 2>&1")
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

ROOT = Path(__file__).resolve().parent
ENV_FILE = ROOT / ".env"
ENV_EXAMPLE = ROOT / ".env.example"

LINE = "=" * 64
SUB = "-" * 64

# 依赖名 -> import 名
DEPS = [
    ("openai", "openai"),
    ("python-dotenv", "dotenv"),
    ("pdfplumber", "pdfplumber"),
    ("numpy", "numpy"),
    ("pandas", "pandas"),
    ("tqdm", "tqdm"),
]

MIRROR = "https://pypi.tuna.tsinghua.edu.cn/simple"


def title(step, text):
    print()
    print(LINE)
    print(f"[{step}] {text}")
    print(LINE)


def ask_yes(prompt):
    """问一个是/否问题，默认是。"""
    try:
        ans = input(f"{prompt} [直接回车 = 是]：").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return ans in ("", "y", "yes", "是")


def pause(msg="按回车键继续..."):
    try:
        input(msg)
    except (EOFError, KeyboardInterrupt):
        print()


# ====================================================================


def step1_python():
    title("1/5", "检查 Python 版本")
    v = sys.version_info
    print(f"当前 Python：{sys.version.split()[0]}")
    print(f"所在位置  ：{sys.executable}")
    if v < (3, 9):
        print()
        print("[X] Python 版本过低（需要 3.9 或更高）。")
        print("    建议去 https://www.python.org/downloads/ 下载新版安装。")
        return False
    print()
    print("[OK] Python 版本符合要求。")
    return True


def step2_deps():
    title("2/5", "检查依赖库")
    missing = []
    for pip_name, import_name in DEPS:
        try:
            __import__(import_name)
            print(f"  [已有] {pip_name}")
        except ImportError:
            print(f"  [缺失] {pip_name}")
            missing.append(pip_name)

    if not missing:
        print()
        print("[OK] 所有依赖库都已安装。")
        return True

    print()
    print(f"缺少 {len(missing)} 个库，需要安装：{'、'.join(missing)}")
    print("安装过程需要联网，大约 1-3 分钟，会滚动很多行英文——那是正常的。")
    print()
    if not ask_yes("现在就自动安装吗？"):
        print()
        print("已跳过。你可以稍后自己在命令行执行：")
        print(f'  "{sys.executable}" -m pip install {" ".join(missing)} -i {MIRROR}')
        return False

    print()
    print("正在安装，请耐心等待，不要关闭窗口...")
    print(SUB)
    cmd = [sys.executable, "-m", "pip", "install",
           "--disable-pip-version-check", "-i", MIRROR] + missing
    try:
        rc = subprocess.call(cmd)
    except Exception as e:  # noqa: BLE001
        print("[X] 安装命令执行失败：", e)
        return False
    print(SUB)

    if rc != 0:
        print()
        print("[X] 安装过程报错了。可以尝试：")
        print("    1. 检查网络是否通畅；")
        print("    2. 复制上面最后几行红字，发到赛事 QQ 群 1061821631 求助。")
        return False

    # 复查
    print()
    print("复查安装结果：")
    still = []
    for pip_name, import_name in DEPS:
        try:
            __import__(import_name)
            print(f"  [OK] {pip_name}")
        except ImportError:
            print(f"  [X ] {pip_name} 仍未装上")
            still.append(pip_name)

    if still:
        print()
        print("[X] 还有库没装上：", "、".join(still))
        print("    请把上面的信息发到群里求助。")
        return False

    print()
    print("[OK] 全部依赖安装完成。")
    return True


def step3_env_file():
    title("3/5", "创建配置文件 .env")
    if ENV_FILE.exists():
        print(f"[OK] 配置文件已存在：{ENV_FILE.name}")
        return True

    if not ENV_EXAMPLE.exists():
        print(f"[X] 找不到模板文件 {ENV_EXAMPLE.name}，无法创建配置。")
        return False

    content = ENV_EXAMPLE.read_text(encoding="utf-8")
    ENV_FILE.write_text(content, encoding="utf-8")
    print(f"[OK] 已根据模板创建：{ENV_FILE.name}")
    print("     （这个文件只在你电脑上，不会被提交到 GitHub）")
    return True


def read_env():
    """读 .env 为字典（忽略注释行）。"""
    data = {}
    if not ENV_FILE.exists():
        return data
    for raw in ENV_FILE.read_text(encoding="utf-8").splitlines():
        s = raw.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        data[k.strip()] = v.strip()
    return data


def write_env(data):
    """按模板顺序重写 .env。"""
    order = ["DASHSCOPE_API_KEY", "DASHSCOPE_BASE_URL", "LLM_MODEL", "EMBED_MODEL"]
    lines = [
        "# 本文件由 setup.py 自动维护，含真实密钥，切勿提交到仓库或发给他人",
        "",
    ]
    for k in order:
        if k in data:
            lines.append(f"{k}={data[k]}")
    for k, v in data.items():
        if k not in order:
            lines.append(f"{k}={v}")
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def step4_key():
    title("4/5", "配置 API Key")
    data = read_env()
    cur = data.get("DASHSCOPE_API_KEY", "")

    valid = cur.startswith("sk-") and "替换" not in cur and len(cur) > 20
    if valid:
        print(f"[OK] 已检测到 Key：{cur[:7]}{'*' * 8}{cur[-4:]}")
        print()
        if not ask_yes("要换一个新的 Key 吗？（不换就直接回车）"):
            return True

    print()
    print("请按下面两步操作：")
    print("  第 1 步：打开浏览器进入百炼控制台")
    print("           https://bailian.console.aliyun.com/")
    print("  第 2 步：右上角头像 → API-KEY 管理 → 创建我的 API-KEY")
    print("           创建后点「复制」按钮")
    print()
    print("提示：如果之前把 Key 截图发出去过，请先删掉旧的再建新的。")
    print()

    while True:
        try:
            key = input("把 Key 粘贴到这里，然后按回车：").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return False

        if not key:
            print("  （没有输入内容，请重新粘贴。如果你不想现在配置，按 Ctrl+C 退出）")
            continue
        if key.startswith("sk-") and len(key) > 20 and "替换" not in key:
            break
        print("  [X] 这看起来不像有效的 Key。")
        print("      有效的 Key 以 sk- 开头，是一长串字母和数字。")
        print("      请回到百炼控制台重新点「复制」，再粘贴一次。")

    data["DASHSCOPE_API_KEY"] = key
    # 默认使用百炼 OpenAI 兼容入口；若控制台显示专属 workspace 域名(ws-开头)，
    # 且 Key 也是在同一业务空间创建的，再改为该地址。普通场景下 dashscope 通用地址最稳。
    data.setdefault("DASHSCOPE_BASE_URL",
                    "https://dashscope.aliyuncs.com/compatible-mode/v1")
    data.setdefault("LLM_MODEL", "qwen-plus")
    data.setdefault("EMBED_MODEL", "text-embedding-v3")
    write_env(data)

    print()
    print(f"[OK] 已写入配置文件：{ENV_FILE.name}")
    print(f"     使用的 Key：{key[:7]}{'*' * 8}{key[-4:]}")

    print()
    print("如果你的百炼控制台显示的模型服务地址是 ws- 开头的一长串，")
    print("（形如 https://ws-xxxx.cn-beijing.maas.aliyuncs.com/compatible-mode/v1）")
    if ask_yes("要现在把这个地址也填进去吗？（不知道就回车跳过）"):
        try:
            url = input("粘贴控制台显示的那个完整地址：").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return True
        if url.startswith("http"):
            data["DASHSCOPE_BASE_URL"] = url
            write_env(data)
            print("[OK] 地址已更新。")
        else:
            print("（不像有效地址，已保持默认）")
    return True


def step5_verify():
    title("5/5", "联网验证")
    print("接下来会真实调用一次阿里云接口，确认 Key 和模型都能用。")
    print("这一步需要联网，大概 10 秒。")
    print()
    if not ask_yes("开始验证吗？"):
        print()
        print("已跳过。你可以稍后自己运行：")
        print(f'  "{sys.executable}" "{ROOT / "check_env.py"}"')
        return False

    print(SUB)
    rc = subprocess.call([sys.executable, str(ROOT / "check_env.py")])
    print(SUB)
    return rc == 0


def main():
    print()
    print(LINE)
    print("        选课军师 · 一键环境配置")
    print("        逐光队 · 2026 重庆市 AI 大模型大赛")
    print(LINE)
    print(f"项目位置：{ROOT}")

    if not step1_python():
        pause()
        return 1
    if not step2_deps():
        pause()
        return 1
    if not step3_env_file():
        pause()
        return 1
    if not step4_key():
        pause()
        return 1

    ok = step5_verify()

    print()
    print(LINE)
    if ok:
        print("全部完成！环境已经配置好了。")
        print()
        print("下一步：把培养方案的 PDF 文件放进 data/raw/ 文件夹，")
        print("然后运行 ingest.py 开始做数据切片。")
    else:
        print("配置已保存，但联网验证没有全部通过。")
        print()
        print("请把上面显示的报错信息截图，发到赛事 QQ 群 1061821631 求助，")
        print("或者直接回来问我。")
    print(LINE)
    pause("按回车键结束...")
    return 0 if ok else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n已取消。")
        sys.exit(130)
