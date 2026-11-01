#!/usr/bin/env python3
"""[도구 2] tidy.csv 에서 대상 대학의 지표를 계산한다. 숫자는 모두 여기서만 만든다(LLM이 계산하지 않는다).

지표별로: 연도별 값, 전년 대비 변화, 비교군 통계(n·중앙값·평균·최소·최대), 비교군 내 순위,
전체 백분위(방향 반영: 높을수록 좋은 지표/낮을수록 좋은 지표), 3년 추세, 내부 경보선 플래그.

사용: python3 analyze.py --tidy workspace/tidy.csv --school 한빛대학교 \
        [--peers "가람대학교,누리대학교"] [--peer-rule same_founding_region|same_founding|same_region|all] \
        [--year 2026] [--out workspace/analysis.json]
"""
import argparse
import datetime as dt
import json
import sys
from pathlib import Path

import pandas as pd

SKILL = Path(__file__).resolve().parent.parent


def r1(x):
    return None if x is None or pd.isna(x) else round(float(x), 2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tidy", default="workspace/tidy.csv")
    ap.add_argument("--school", required=True)
    ap.add_argument("--peers", default="")
    ap.add_argument("--peer-rule", default="same_founding_region",
                    choices=["same_founding_region", "same_founding", "same_region", "all"])
    ap.add_argument("--year", type=int)
    ap.add_argument("--out", default="workspace/analysis.json")
    a = ap.parse_args()

    df = pd.read_csv(a.tidy, encoding="utf-8-sig")
    ind = pd.read_csv(SKILL / "references" / "indicators.csv", dtype=str).set_index("id")
    th = json.load(open(SKILL / "references" / "thresholds.json"))

    schools = sorted(df["school"].unique())
    if a.school not in schools:
        near = [s for s in schools if a.school.replace("대학교", "") in s]
        sys.exit(f"'{a.school}' 이(가) 데이터에 없다. 비슷한 이름: {near or '없음'} (전체 {len(schools)}개교)")
    t = df[df["school"] == a.school]
    prof = t.sort_values("year").iloc[-1]
    year = a.year or int(df["year"].max())

    if a.peers:
        peers = [p.strip() for p in a.peers.split(",") if p.strip()]
        missing = [p for p in peers if p not in schools]
        if missing:
            sys.exit(f"비교 대학이 데이터에 없다: {missing}")
        rule = "사용자 지정"
    else:
        sel = df[["school", "founding", "region"]].drop_duplicates("school")
        if a.peer_rule == "same_founding_region":
            sel = sel[(sel.founding == prof.founding) & (sel.region == prof.region)]
        elif a.peer_rule == "same_founding":
            sel = sel[sel.founding == prof.founding]
        elif a.peer_rule == "same_region":
            sel = sel[sel.region == prof.region]
        peers = sorted(set(sel["school"]) - {a.school})
        rule = {"same_founding_region": f"같은 설립구분({prof.founding})·지역({prof.region})",
                "same_founding": f"같은 설립구분({prof.founding})", "same_region": f"같은 지역({prof.region})",
                "all": "데이터 내 전체"}[a.peer_rule]

    out = {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "school": a.school, "founding": prof.founding, "region": prof.region, "base_year": year,
        "years": sorted(int(y) for y in t["year"].unique()),
        "peer_group": {"rule": rule, "schools": peers, "n": len(peers)},
        "universe_n": len(schools), "indicators": [], "flags": [], "warnings": [],
        "sources": sorted(df["source_file"].unique().tolist()),
    }
    if len(peers) < 3:
        out["warnings"].append(f"비교군이 {len(peers)}개교뿐이다. 통계가 불안정하니 --peer-rule 을 넓히거나 --peers 로 지정하라")

    for iid, meta in ind.iterrows():
        d = df[df.indicator == iid].dropna(subset=["value"])
        ts = d[d.school == a.school].sort_values("year")
        if ts.empty:
            continue
        up = meta["direction"] == "up"
        series = [{"year": int(r.year), "value": r1(r.value)} for r in ts.itertuples()]
        cur = ts[ts.year == year]
        rec = {"id": iid, "name": meta["name"], "unit": meta["unit"], "direction": meta["direction"],
               "definition": meta["definition"], "series": series,
               "source_column": ts.iloc[-1]["source_column"], "source_file": ts.iloc[-1]["source_file"]}
        if cur.empty:
            rec["note"] = f"{year}년 값 없음"
            out["indicators"].append(rec)
            continue
        v = float(cur.iloc[0]["value"])
        prev = ts[ts.year == year - 1]
        rec["value"] = r1(v)
        rec["yoy"] = r1(v - float(prev.iloc[0]["value"])) if not prev.empty else None
        rec["yoy_unit"] = "%p" if meta["unit"] == "%" else meta["unit"]
        yr = d[d.year == year]
        pv = yr[yr.school.isin(peers)]["value"]
        if len(pv):
            group = pd.concat([pv, pd.Series([v])])
            rank = int((group > v).sum() + 1) if up else int((group < v).sum() + 1)
            rec["peer"] = {"n": int(len(pv)), "median": r1(pv.median()), "mean": r1(pv.mean()),
                           "min": r1(pv.min()), "max": r1(pv.max()),
                           "gap_vs_median": r1(v - pv.median()), "rank": rank, "rank_of": int(len(group))}
        allv = yr["value"]
        better = (allv < v).sum() if up else (allv > v).sum()
        rec["percentile"] = r1(100 * (better + 0.5 * ((allv == v).sum() - 1)) / max(len(allv) - 1, 1))
        last3 = ts[ts.year > year - 3]
        if len(last3) >= 2:
            delta = float(last3.iloc[-1]["value"] - last3.iloc[0]["value"])
            good = delta > 0 if up else delta < 0
            rec["trend"] = {"from_year": int(last3.iloc[0]["year"]), "delta": r1(delta),
                            "label": "개선" if good and abs(delta) > 1e-9 else ("악화" if abs(delta) > 1e-9 else "보합")}
        lo, hi = float(meta["min"]), float(meta["max"])
        if not lo <= v <= hi:
            out["warnings"].append(f"{meta['name']} 값 {v} 이(가) 상식 범위 [{lo}, {hi}] 밖이다. 원자료 열 매핑을 확인하라")
        rule_t = th.get(iid, {})
        if "warn_below" in rule_t and v < rule_t["warn_below"]:
            out["flags"].append({"id": iid, "text": f"{meta['name']} {v:g}{meta['unit']} < 내부 경보선 {rule_t['warn_below']:g}"})
        if "warn_above" in rule_t and v > rule_t["warn_above"]:
            out["flags"].append({"id": iid, "text": f"{meta['name']} {v:g}{meta['unit']} > 내부 경보선 {rule_t['warn_above']:g}"})
        out["indicators"].append(rec)

    scored = [i for i in out["indicators"] if i.get("percentile") is not None]
    out["strengths"] = [i["id"] for i in sorted(scored, key=lambda i: -i["percentile"]) if i["percentile"] >= 75]
    out["weaknesses"] = [i["id"] for i in sorted(scored, key=lambda i: i["percentile"]) if i["percentile"] <= 25]

    p = Path(a.out)
    p.parent.mkdir(parents=True, exist_ok=True)
    json.dump(out, open(p, "w"), ensure_ascii=False, indent=2)

    # [메모리] 실행 기록을 남겨 다음 실행이 같은 설정을 재사용하거나 비교할 수 있게 한다
    log = SKILL / "memory" / "run_log.jsonl"
    log.parent.mkdir(exist_ok=True)
    with open(log, "a", encoding="utf-8") as f:
        f.write(json.dumps({"at": out["generated_at"], "school": a.school, "year": year, "peer_rule": rule,
                            "peers_n": len(peers), "indicators": len(out["indicators"]), "flags": len(out["flags"]),
                            "sources": out["sources"]}, ensure_ascii=False) + "\n")

    print(json.dumps({"school": a.school, "base_year": year, "peers": out["peer_group"],
                      "indicators": len(out["indicators"]), "strengths": out["strengths"],
                      "weaknesses": out["weaknesses"], "flags": [f["text"] for f in out["flags"]],
                      "warnings": out["warnings"]}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
