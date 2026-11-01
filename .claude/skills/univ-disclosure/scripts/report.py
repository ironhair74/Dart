#!/usr/bin/env python3
"""[도구 3] analysis.json (+ 선택: narrative.md) → 단일 파일 HTML 리포트.

차트는 외부 라이브러리 없이 인라인 SVG 로 그린다(오프라인에서 열림).
숫자는 analysis.json 에서만 가져온다. narrative.md 는 해석 문장만 담는다.

사용: python3 report.py --analysis workspace/analysis.json [--narrative workspace/narrative.md] \
        [--out workspace/report.html]
"""
import argparse
import html
import json
import re
from pathlib import Path

E = html.escape


def fmt(v, unit=""):
    if v is None:
        return "–"
    if unit == "천원":
        return f"{v:,.0f}천원"
    if unit == ":1":
        return f"{v:,.2f}:1"
    return f"{v:,.1f}{unit}"


def tick(v, span):
    return f"{v:,.0f}" if span >= 6 else (f"{v:,.1f}" if span >= 0.6 else f"{v:,.2f}")


def short(v, unit):
    """차트 직접 라벨: 단위는 부제에 있으니 숫자만."""
    return f"{v:,.0f}" if unit == "천원" else (f"{v:,.2f}" if unit == ":1" else f"{v:,.1f}")


def fmt_delta(v, unit):
    if v is None:
        return "–"
    sign = "+" if v > 0 else ""
    if unit == "천원":
        return f"{sign}{v:,.0f}천원"
    return f"{sign}{v:,.1f}{unit}" if unit != ":1" else f"{sign}{v:,.2f}"


def md(text):
    """아주 작은 마크다운: #, ##, -, **굵게**, 문단."""
    out, in_list = [], False
    for line in text.splitlines():
        s = line.strip()
        s_html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", E(s))
        if s.startswith("- "):
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{s_html[2:]}</li>")
            continue
        if in_list:
            out.append("</ul>")
            in_list = False
        if s.startswith("## "):
            out.append(f"<h3>{s_html[3:]}</h3>")
        elif s.startswith("# "):
            out.append(f"<h2>{s_html[2:]}</h2>")
        elif s:
            out.append(f"<p>{s_html}</p>")
    if in_list:
        out.append("</ul>")
    return "\n".join(out)


def line_chart(ind, peer_series):
    """대상 대학(실선) vs 비교군 중앙값(점선). 단일 y축."""
    W, H, L, R, T, B = 320, 150, 44, 50, 14, 26
    pts = [(p["year"], p["value"]) for p in ind["series"] if p["value"] is not None]
    ref = [(y, v) for y, v in peer_series if v is not None]
    vals = [v for _, v in pts + ref]
    years = sorted({y for y, _ in pts + ref})
    if not vals:
        return ""
    lo, hi = min(vals), max(vals)
    pad = (hi - lo) * 0.25 or abs(hi) * 0.05 or 1
    lo, hi = lo - pad, hi + pad
    x = lambda y: L + (W - L - R) * (0.5 if len(years) == 1 else (years.index(y) / (len(years) - 1)))
    yv = lambda v: T + (H - T - B) * (1 - (v - lo) / (hi - lo))
    u = ind["unit"]
    g = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{E(ind["name"])} 연도별 추이">']
    for k in range(3):
        gv = lo + (hi - lo) * (k + 0.5) / 3
        g.append(f'<line class="grid" x1="{L}" x2="{W - R}" y1="{yv(gv):.1f}" y2="{yv(gv):.1f}"/>'
                 f'<text class="tick" x="{L - 6}" y="{yv(gv) + 3:.1f}" text-anchor="end">{tick(gv, hi - lo)}</text>')
    for yr in years:
        g.append(f'<text class="tick" x="{x(yr):.1f}" y="{H - 8}" text-anchor="middle">{yr}</text>')
    if len(ref) > 1:
        g.append('<polyline class="peer" points="' + " ".join(f"{x(a):.1f},{yv(b):.1f}" for a, b in ref) + '"/>')
    for a, b in ref:
        g.append(f'<circle class="peer-dot" cx="{x(a):.1f}" cy="{yv(b):.1f}" r="3"><title>{a}년 비교군 중앙값 {fmt(b, u)}</title></circle>')
    if len(pts) > 1:
        g.append('<polyline class="me" points="' + " ".join(f"{x(a):.1f},{yv(b):.1f}" for a, b in pts) + '"/>')
    for a, b in pts:
        g.append(f'<circle class="me-dot" cx="{x(a):.1f}" cy="{yv(b):.1f}" r="4.5"><title>{a}년 {fmt(b, u)}</title></circle>'
                 f'<circle class="hit" cx="{x(a):.1f}" cy="{yv(b):.1f}" r="12"><title>{a}년 대상 {fmt(b, u)}</title></circle>')
    a, b = pts[-1]
    g.append(f'<text class="dl" x="{x(a) + 8:.1f}" y="{yv(b) + 4:.1f}">{short(b, u)}</text>')
    g.append("</svg>")
    return "".join(g)


def position_chart(inds):
    """지표별 전체 백분위(높을수록 좋음으로 방향 통일). 50 기준선."""
    rows = [i for i in inds if i.get("percentile") is not None]
    W, rh, L, R = 900, 28, 200, 50
    H = rh * len(rows) + 30
    g = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="지표별 전체 백분위">']
    sx = lambda p: L + (W - L - R) * p / 100
    for p in (0, 25, 50, 75, 100):
        g.append(f'<line class="{"mid" if p == 50 else "grid"}" x1="{sx(p):.1f}" x2="{sx(p):.1f}" y1="4" y2="{H - 22}"/>'
                 f'<text class="tick" x="{sx(p):.1f}" y="{H - 8}" text-anchor="middle">{p}</text>')
    for k, i in enumerate(rows):
        cy = 4 + rh * k + rh / 2
        p = i["percentile"]
        g.append(f'<text class="lab" x="{L - 10}" y="{cy + 4:.1f}" text-anchor="end">{E(i["name"])}</text>'
                 f'<rect class="bar" x="{L}" y="{cy - 5:.1f}" width="{max(sx(p) - L, 2):.1f}" height="10" rx="4"/>'
                 f'<text class="dl" x="{sx(p) + 6:.1f}" y="{cy + 4:.1f}">{p:.0f}</text>'
                 f'<rect class="hit" x="0" y="{cy - rh / 2:.1f}" width="{W}" height="{rh}">'
                 f'<title>{E(i["name"])}: 전체 {p:.0f} 백분위 (값 {fmt(i.get("value"), i["unit"])})</title></rect>')
    g.append("</svg>")
    return "".join(g)


CSS = """
.viz-root{color-scheme:light;--surface-1:#fcfcfb;--page:#f9f9f7;--text-primary:#0b0b0b;--text-secondary:#52514e;
--grid:#e1e0d9;--axis:#c3c2b7;--series-1:#2a78d6;--peer:#8a8980;--good:#006300;--critical:#d03b3b;--warning:#fab219;
--border:rgba(11,11,11,.10)}
@media (prefers-color-scheme:dark){.viz-root{color-scheme:dark;--surface-1:#1a1a19;--page:#0d0d0d;--text-primary:#f0efec;
--text-secondary:#c3c2b7;--grid:#2c2c2a;--axis:#383835;--series-1:#3987e5;--peer:#9a998f;--good:#0ca30c;--critical:#e66767;
--border:rgba(255,255,255,.10)}}
*{box-sizing:border-box}body{margin:0;background:var(--page);color:var(--text-primary);
font:15px/1.6 "Pretendard","Apple SD Gothic Neo","Noto Sans KR",system-ui,sans-serif}
main{max-width:1040px;margin:0 auto;padding:32px 20px 60px}
h1{font-size:26px;margin:0 0 4px}h2{font-size:19px;margin:36px 0 12px}h3{font-size:16px;margin:20px 0 6px}
.sub{color:var(--text-secondary);font-size:13px}
.card{background:var(--surface-1);border:1px solid var(--border);border-radius:10px;padding:16px}
.kpis{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:12px}
.kpi .n{font-size:13px;color:var(--text-secondary)}.kpi .v{font-size:24px;font-weight:700;font-variant-numeric:tabular-nums}
.kpi .d{font-size:13px;color:var(--text-secondary)}.up{color:var(--good)}.down{color:var(--critical)}
.grid2{display:grid;grid-template-columns:repeat(auto-fill,minmax(310px,1fr));gap:12px}
svg{width:100%;height:auto;display:block}
svg .grid{stroke:var(--grid);stroke-width:1}svg .mid{stroke:var(--axis);stroke-width:1.5;stroke-dasharray:3 3}
svg .tick{fill:var(--text-secondary);font-size:10px}svg .lab{fill:var(--text-primary);font-size:12px}
svg .dl{fill:var(--text-primary);font-size:11px;font-weight:600}
svg .me{fill:none;stroke:var(--series-1);stroke-width:2}svg .me-dot{fill:var(--series-1);stroke:var(--surface-1);stroke-width:2}
svg .peer{fill:none;stroke:var(--peer);stroke-width:2;stroke-dasharray:5 4}svg .peer-dot{fill:var(--peer)}
svg .bar{fill:var(--series-1)}svg .hit{fill:transparent}svg .hit:hover{fill:rgba(127,127,127,.08)}
.legend{display:flex;gap:18px;font-size:13px;color:var(--text-secondary);margin:4px 0 10px}
.sw{display:inline-block;width:18px;height:0;border-top:2px solid var(--series-1);vertical-align:middle;margin-right:6px}
.sw.p{border-top:2px dashed var(--peer)}
table{width:100%;border-collapse:collapse;font-size:13px;font-variant-numeric:tabular-nums}
th,td{padding:7px 8px;border-bottom:1px solid var(--grid);text-align:right}th:first-child,td:first-child{text-align:left}
th{color:var(--text-secondary);font-weight:600}
.flag{padding:8px 12px;border-left:4px solid var(--warning);background:var(--surface-1);margin:6px 0;border-radius:4px}
.warn{border-left-color:var(--critical)}
.foot{font-size:12px;color:var(--text-secondary);margin-top:40px;border-top:1px solid var(--grid);padding-top:12px}
.chart-title{font-weight:600;font-size:14px}.chart-sub{font-size:12px;color:var(--text-secondary)}
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--analysis", default="workspace/analysis.json")
    ap.add_argument("--tidy", default=None, help="비교군 중앙값 추이를 그리려면 tidy.csv 경로(기본: analysis 옆)")
    ap.add_argument("--narrative")
    ap.add_argument("--out", default="workspace/report.html")
    ap.add_argument("--banner", default="", help='맨 위 경고 띠 문구. 가상 데이터면 "가상 데이터 결과"')
    a = ap.parse_args()
    A = json.load(open(a.analysis, encoding="utf-8"))
    tidy = Path(a.tidy) if a.tidy else Path(a.analysis).with_name("tidy.csv")
    peer_med = {}
    if tidy.exists():
        import pandas as pd
        d = pd.read_csv(tidy, encoding="utf-8-sig")
        d = d[d.school.isin(A["peer_group"]["schools"])].dropna(subset=["value"])
        for (iid, yr), v in d.groupby(["indicator", "year"])["value"].median().items():
            peer_med.setdefault(iid, []).append((int(yr), round(float(v), 2)))
    inds = A["indicators"]
    by = {i["id"]: i for i in inds}
    Y = A["base_year"]

    kpi = []
    for i in inds:
        if i.get("value") is None:
            continue
        cls = ""
        if i.get("yoy"):
            good = (i["yoy"] > 0) == (i["direction"] == "up")
            cls = "up" if good else "down"
        arrow = "▲" if (i.get("yoy") or 0) > 0 else ("▼" if (i.get("yoy") or 0) < 0 else "")
        peer = i.get("peer")
        kpi.append(f'<div class="card kpi"><div class="n">{E(i["name"])}</div><div class="v">{fmt(i["value"], i["unit"])}</div>'
                   f'<div class="d"><span class="{cls}">{arrow} {fmt_delta(i.get("yoy"), i.get("yoy_unit", ""))}</span> 전년 대비'
                   + (f' · 비교군 {peer["rank"]}/{peer["rank_of"]}위' if peer else "") + "</div></div>")

    charts = []
    for i in inds:
        if not i["series"]:
            continue
        charts.append(f'<div class="card"><div class="chart-title">{E(i["name"])}</div>'
                      f'<div class="chart-sub">단위 {E(i["unit"])} · {"높을수록" if i["direction"] == "up" else "낮을수록"} 양호</div>'
                      f'{line_chart(i, sorted(peer_med.get(i["id"], [])))}</div>')

    trows = []
    for i in inds:
        p = i.get("peer") or {}
        pct = "–" if i.get("percentile") is None else f"{i['percentile']:.0f}"
        trows.append(f'<tr><td>{E(i["name"])}</td><td>{fmt(i.get("value"), i["unit"])}</td>'
                     f'<td>{fmt_delta(i.get("yoy"), i.get("yoy_unit", ""))}</td><td>{fmt(p.get("median"), i["unit"])}</td>'
                     f'<td>{fmt_delta(p.get("gap_vs_median"), i.get("yoy_unit", i["unit"])) if p else "–"}</td>'
                     f'<td>{(str(p["rank"]) + "/" + str(p["rank_of"])) if p else "–"}</td>'
                     f'<td>{pct}</td>'
                     f'<td>{E((i.get("trend") or {}).get("label", "–"))}</td></tr>')
    flags = "".join(f'<div class="flag">⚠ <strong>주의</strong> {E(f["text"])}</div>' for f in A["flags"]) or "<p>내부 경보선에 걸린 지표가 없다.</p>"
    warns = "".join(f'<div class="flag warn">✗ <strong>데이터 경고</strong> {E(w)}</div>' for w in A["warnings"])
    narrative = md(Path(a.narrative).read_text(encoding="utf-8")) if a.narrative and Path(a.narrative).exists() else \
        "<p class='sub'>(해석 문단 없음: narrative.md 를 넣으면 이 자리에 표시된다)</p>"
    banner = f'<div class="flag warn">ⓘ <strong>{E(a.banner)}</strong> — 실제 대학과 무관한 수치다.</div>' if a.banner else ""
    strengths = ", ".join(by[s]["name"] for s in A["strengths"]) or "없음"
    weaknesses = ", ".join(by[s]["name"] for s in A["weaknesses"]) or "없음"
    defs = "".join(f"<li><strong>{E(i['name'])}</strong>: {E(i['definition'])} <span class='sub'>(원자료 열: {E(i['source_column'])} · {E(i['source_file'])})</span></li>" for i in inds)

    doc = f"""<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{E(A['school'])} 대학공시 분석 ({Y})</title><style>{CSS}</style></head>
<body class="viz-root"><main>
<h1>{E(A['school'])} 대학공시 분석</h1>
<div class="sub">기준연도 {Y} · {E(A['founding'])} · {E(A['region'])} · 비교군: {E(A['peer_group']['rule'])} {A['peer_group']['n']}개교
 · 전체 데이터 {A['universe_n']}개교 · 생성 {E(A['generated_at'])}</div>
{banner}{warns}
<h2>요약</h2><div class="card">{narrative}
<p class="sub">자동 판정 — 강점(전체 상위 25%): {E(strengths)} / 약점(하위 25%): {E(weaknesses)}</p></div>
<h2>핵심 지표 ({Y})</h2><div class="kpis">{''.join(kpi)}</div>
<h2>내부 경보</h2>{flags}
<h2>전체 대비 위치</h2><div class="card"><div class="chart-sub">전체 {A['universe_n']}개교 중 백분위. 낮을수록 좋은 지표는 뒤집어 100에 가까울수록 양호하게 맞췄다. 점선 = 50(중간).</div>
{position_chart(inds)}</div>
<h2>연도별 추이</h2><div class="legend"><span><span class="sw"></span>{E(A['school'])}</span><span><span class="sw p"></span>비교군 중앙값</span></div>
<div class="grid2">{''.join(charts)}</div>
<h2>지표 표</h2><div class="card" style="overflow-x:auto"><table>
<tr><th>지표</th><th>{Y}</th><th>전년 대비</th><th>비교군 중앙값</th><th>중앙값 대비</th><th>비교군 순위</th><th>전체 백분위</th><th>3년 추세</th></tr>
{''.join(trows)}</table></div>
<h2>지표 정의와 출처</h2><ul class="sub">{defs}</ul>
<div class="foot">자료: 대학알리미(www.academyinfo.go.kr) 공시 다운로드 파일 — {E(', '.join(A['sources']))}.
비교군: {E(', '.join(A['peer_group']['schools']))}.
'내부 경보선'은 이 스킬의 참고값이며 정부 평가의 공식 기준이 아니다. 공시 수치는 학교가 정정 공시할 수 있으니 의사결정 전 원문을 확인할 것.</div>
</main></body></html>"""
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(doc, encoding="utf-8")
    print(f"리포트 저장: {a.out}")


if __name__ == "__main__":
    main()
