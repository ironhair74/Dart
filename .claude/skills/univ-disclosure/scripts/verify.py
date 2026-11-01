#!/usr/bin/env python3
"""[검증] 산출물을 결정론적으로 검사한다. 실패가 하나라도 있으면 종료 코드 1.

검사 항목
 1. 재계산: analysis.json 의 모든 연도별 값이 tidy.csv 원값과 같은가
 2. 범위: 지표 값이 indicators.csv 의 상식 범위 안인가
 3. 비교군: 3개교 이상인가(미만이면 경고)
 4. 리포트: 기준연도·대학명·출처가 있고, 'nan'/'None' 이 찍히지 않았는가
 5. 해석 문장(narrative.md): 문장 속 숫자가 모두 analysis.json 에 근거가 있는가(환각 숫자 차단),
    금지 표현(단정·낙인)이 없는가

사용: python3 verify.py --dir workspace   (tidy.csv, analysis.json, report.html, narrative.md 를 찾는다)
"""
import argparse
import json
import re
import sys
from pathlib import Path

import pandas as pd

SKILL = Path(__file__).resolve().parent.parent
BANNED = ["부실대학", "부실 대학", "퇴출", "폐교 확정", "폐교될", "공식 기준", "확정적으로", "반드시 탈락", "망한", "최악의 대학"]


def numbers_in(obj, acc):
    if isinstance(obj, dict):
        for v in obj.values():
            numbers_in(v, acc)
    elif isinstance(obj, list):
        for v in obj:
            numbers_in(v, acc)
    elif isinstance(obj, (int, float)) and not isinstance(obj, bool):
        acc.add(round(abs(float(obj)), 2))
    return acc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="workspace")
    a = ap.parse_args()
    d = Path(a.dir)
    errors, warns, passed = [], [], []

    A = json.load(open(d / "analysis.json", encoding="utf-8"))
    T = pd.read_csv(d / "tidy.csv", encoding="utf-8-sig")
    ind = pd.read_csv(SKILL / "references" / "indicators.csv", dtype=str).set_index("id")
    th = json.load(open(SKILL / "references" / "thresholds.json"))

    # 1. 재계산
    mism = 0
    for i in A["indicators"]:
        for p in i["series"]:
            src = T[(T.school == A["school"]) & (T.year == p["year"]) & (T.indicator == i["id"])]["value"]
            if src.empty or abs(float(src.iloc[0]) - p["value"]) > 0.01:
                mism += 1
                errors.append(f"[재계산] {i['name']} {p['year']}: 리포트 {p['value']} ≠ 원자료 {src.tolist()}")
    if not mism:
        passed.append("재계산 일치")

    # 2. 범위
    bad = 0
    for i in A["indicators"]:
        lo, hi = float(ind.loc[i["id"], "min"]), float(ind.loc[i["id"], "max"])
        for p in i["series"]:
            if p["value"] is not None and not lo <= p["value"] <= hi:
                bad += 1
                errors.append(f"[범위] {i['name']} {p['year']} = {p['value']} (허용 {lo}~{hi}) → 열 매핑 오류 의심")
    if not bad:
        passed.append("값 범위 정상")

    # 3. 비교군
    if A["peer_group"]["n"] < 3:
        warns.append(f"[비교군] {A['peer_group']['n']}개교: 순위·중앙값 해석을 약하게 표현하라")
    else:
        passed.append(f"비교군 {A['peer_group']['n']}개교")

    # 4. 리포트
    rp = d / "report.html"
    if rp.exists():
        h = rp.read_text(encoding="utf-8")
        for need in (A["school"], str(A["base_year"]), "대학알리미"):
            if need not in h:
                errors.append(f"[리포트] '{need}' 표기가 없다")
        if re.search(r">\s*(nan|None|NaN)\s*<", h):
            errors.append("[리포트] nan/None 값이 그대로 찍혔다")
        if not any(e.startswith("[리포트]") for e in errors):
            passed.append("리포트 필수 표기")
    else:
        warns.append("[리포트] report.html 이 아직 없다")

    # 5. 해석 문장
    np_ = d / "narrative.md"
    if np_.exists():
        text = np_.read_text(encoding="utf-8")
        allowed = numbers_in(A, set()) | numbers_in(th, set())
        allowed |= {round(abs(float(v)), 2) for v in T[T.school == A["school"]]["value"].dropna()}
        allowed |= {float(n) for n in range(0, 11)} | {25.0, 50.0, 75.0, 100.0}
        # 연도·순위 표현 등 정수와, 문장 속 숫자 전부 검사
        unknown = []
        for m in re.finditer(r"(?<![\w.])[-+]?\d[\d,]*(?:\.\d+)?", text):
            raw = m.group(0)
            v = round(abs(float(raw.replace(",", ""))), 2)
            if v in allowed or any(abs(v - x) <= 0.05 for x in allowed):
                continue
            unknown.append(raw)
        if unknown:
            errors.append(f"[근거 없는 숫자] narrative.md: {sorted(set(unknown))} — analysis.json 에 없는 숫자다. 지우거나 analyze.py 로 계산하라")
        else:
            passed.append("해석 문장 숫자 근거 확인")
        hit = [b for b in BANNED if b in text]
        if hit:
            errors.append(f"[금지 표현] {hit} — 공시 수치로 단정·낙인하지 않는다(guardrails.md)")
        if str(A["base_year"]) not in text:
            warns.append("[해석] narrative.md 에 기준연도가 없다")
    else:
        warns.append("[해석] narrative.md 가 없다(리포트에 해석 문단이 빠진다)")

    res = {"ok": not errors, "passed": passed, "errors": errors, "warnings": warns + A.get("warnings", [])}
    json.dump(res, open(d / "verify_report.json", "w"), ensure_ascii=False, indent=2)
    print(json.dumps(res, ensure_ascii=False, indent=1))
    sys.exit(0 if res["ok"] else 1)


if __name__ == "__main__":
    main()
