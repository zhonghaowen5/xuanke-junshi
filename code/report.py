"""生成「个人学业规划报告」HTML。

设计目标：
    零第三方依赖（不装 reportlab / python-docx），输出一份排版完整的 HTML，
    浏览器打开后可直接「打印 → 另存为 PDF」，作为可交付的实物成果。

用法：
    from report import build_html
    html = build_html(prof, grade, diag, rec=rec, semester="2026秋")
"""

from datetime import datetime
from html import escape


_STYLE = """
:root { --blue:#2563eb; --green:#10b981; --gray:#6b7280; --line:#e5e7eb; }
* { box-sizing: border-box; }
body {
  font-family: "Microsoft YaHei", "PingFang SC", "Helvetica Neue", Arial, sans-serif;
  color:#111827; margin:0; padding:32px; background:#fff; line-height:1.7;
}
.wrap { max-width: 820px; margin: 0 auto; }
h1 { font-size:26px; margin:0 0 4px; }
.sub { color:var(--gray); font-size:13px; margin-bottom:24px; }
.badge { display:inline-block; background:#eff6ff; color:var(--blue);
  border-radius:999px; padding:4px 12px; font-size:12px; margin-bottom:18px; }
.cards { display:flex; gap:16px; margin:20px 0 28px; flex-wrap:wrap; }
.card { flex:1; min-width:180px; border:1px solid var(--line); border-radius:12px;
  padding:16px 18px; }
.card .k { color:var(--gray); font-size:13px; }
.card .v { font-size:28px; font-weight:700; margin-top:4px; }
.card.a .v { color:var(--green); }
.card.b .v { color:var(--blue); }
.card.c .v { color:#ef4444; }
h2 { font-size:18px; margin:28px 0 12px; padding-left:10px;
  border-left:4px solid var(--blue); }
table { width:100%; border-collapse:collapse; font-size:14px; }
th, td { border:1px solid var(--line); padding:8px 10px; text-align:left; }
th { background:#f9fafb; font-weight:600; }
.bar { background:#f3f4f6; border-radius:999px; height:10px; overflow:hidden; }
.bar > i { display:block; height:100%; background:var(--green); }
.warn { background:#fffbeb; border-left:4px solid #f59e0b;
  padding:10px 14px; margin:8px 0; font-size:14px; }
.ok { background:#ecfdf5; border-left:4px solid var(--green);
  padding:10px 14px; margin:8px 0; font-size:14px; }
.foot { margin-top:36px; padding-top:14px; border-top:1px solid var(--line);
  color:var(--gray); font-size:12px; }
@media print {
  body { padding:0; }
  .card { break-inside: avoid; }
  table { break-inside: auto; }
  tr { break-inside: avoid; }
}
"""


def _fmt(v):
    """数字尽量去掉多余小数：140.0 → 140。"""
    try:
        f = float(v)
        return str(int(f)) if f == int(f) else str(round(f, 1))
    except (TypeError, ValueError):
        return escape(str(v))


def build_html(prof: str, grade, diag: dict, rec: dict = None,
               semester: str = "") -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    total = _fmt(diag.get("总要求", 0))
    done = _fmt(diag.get("已修", 0))
    gap = _fmt(diag.get("总缺口", 0))
    pct = 0
    try:
        pct = round(float(diag.get("已修", 0)) / float(diag.get("总要求", 1)) * 100, 1)
    except (TypeError, ValueError, ZeroDivisionError):
        pct = 0

    parts = [
        "<!DOCTYPE html><html lang='zh-CN'><head><meta charset='utf-8'>",
        "<title>个人学业规划报告</title>",
        f"<style>{_STYLE}</style></head><body><div class='wrap'>",
        "<h1>个人学业规划报告</h1>",
        "<div class='sub'>选课军师 · 学业规划 AI 助手　|　"
        "依据重庆邮电大学现行本科培养方案生成</div>",
        f"<div class='badge'>{escape(str(prof))}　·　{escape(str(grade))} 级"
        f"{'　·　' + escape(semester) if semester else ''}</div>",
        "<div class='cards'>",
        f"<div class='card'><div class='k'>毕业要求总学分</div>"
        f"<div class='v'>{total}</div></div>",
        f"<div class='card a'><div class='k'>已修学分</div>"
        f"<div class='v'>{done}</div></div>",
        f"<div class='card c'><div class='k'>待修学分</div>"
        f"<div class='v'>{gap}</div></div>",
        f"<div class='card b'><div class='k'>总体完成度</div>"
        f"<div class='v'>{pct}%</div></div>",
        "</div>",
    ]

    # ---- 模块明细 ----
    parts.append("<h2>一、学分构成与达成情况</h2>")
    parts.append("<table><thead><tr><th>模块</th><th>已修</th><th>要求</th>"
                 "<th>缺口</th><th style='width:180px'>达成率</th></tr></thead><tbody>")
    for m in diag.get("模块明细", []):
        rate = m.get("达成率", 0)
        try:
            rate_f = float(rate)
        except (TypeError, ValueError):
            rate_f = 0.0
        parts.append(
            f"<tr><td>{escape(str(m.get('模块', '')))}</td>"
            f"<td>{_fmt(m.get('已修', 0))}</td>"
            f"<td>{_fmt(m.get('要求', 0))}</td>"
            f"<td>{_fmt(m.get('缺口', 0))}</td>"
            f"<td><div class='bar'><i style='width:{min(rate_f, 100)}%'></i></div>"
            f"<span style='font-size:12px;color:#6b7280'>{_fmt(rate)}%</span></td></tr>"
        )
    parts.append("</tbody></table>")

    # ---- 风险提示 ----
    risks = diag.get("风险提示", [])
    if risks:
        parts.append("<h2>二、风险提示</h2>")
        for r in risks:
            parts.append(f"<div class='warn'>{escape(str(r))}</div>")
    else:
        parts.append("<h2>二、风险提示</h2>")
        parts.append("<div class='ok'>当前进度正常，未发现明显学分风险。</div>")

    # ---- 选课建议 ----
    if rec and rec.get("推荐课程"):
        courses = rec["推荐课程"]
        parts.append(f"<h2>三、{escape(semester) if semester else '下学期'}选课建议</h2>")
        parts.append(
            f"<p style='font-size:14px;color:#374151'>"
            f"共推荐 <b>{len(courses)}</b> 门课，合计 "
            f"<b>{_fmt(rec.get('总学分', 0))}</b> 学分（建议区间 18–24 学分）。</p>")
        parts.append("<table><thead><tr><th>#</th><th>课程名称</th><th>学分</th>"
                     "<th>所属模块</th><th>推荐理由</th></tr></thead><tbody>")
        for i, c in enumerate(courses, 1):
            why = []
            if c.get("所属模块") == "必修课":
                why.append("必修课，须优先完成")
            if c.get("缺口", 0) > 0:
                why.append(f"所属模块尚缺 {_fmt(c['缺口'])} 学分")
            if c.get("重修"):
                why.append("此前未通过，需重修")
            parts.append(
                f"<tr><td>{i}</td>"
                f"<td>{escape(str(c.get('课程名称', '')))}</td>"
                f"<td>{_fmt(c.get('学分', 0))}</td>"
                f"<td>{escape(str(c.get('所属模块', '')))}</td>"
                f"<td>{escape('；'.join(why) or '满足选课条件')}</td></tr>"
            )
        parts.append("</tbody></table>")
        for s in rec.get("说明", []):
            parts.append(f"<div class='warn'>{escape(str(s))}</div>")

    parts.append(
        "<div class='foot'>"
        "本报告由「选课军师」依据各专业现行培养方案与个人成绩单自动生成，"
        "仅供学业规划参考，最终以学校教务处与所在学院的官方审核结果为准。"
        f"<br>生成时间：{now}　·　逐光队 · 重庆邮电大学"
        "</div>")
    parts.append("</div></body></html>")
    return "\n".join(parts)
