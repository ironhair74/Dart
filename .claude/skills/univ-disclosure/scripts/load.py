#!/usr/bin/env python3
"""[도구 1] 대학알리미 공시 다운로드 파일(CSV/XLSX)을 하나의 긴 표(tidy.csv)로 정리한다.

- 인코딩 자동 판별(utf-8-sig → cp949 → euc-kr)
- 1~3줄짜리 머리글(병합 셀) 자동 탐지·결합
- references/indicators.csv 의 별칭으로 지표 열을 찾는다
- 숫자 정리: 쉼표, '-', '해당없음', 공백 → 결측
- 결과: <out>/tidy.csv, <out>/load_report.json

사용: python3 load.py <입력 파일 또는 폴더> [--out workspace] [--include-branch]
"""
import argparse
import json
import re
import sys
from pathlib import Path

import pandas as pd

SKILL = Path(__file__).resolve().parent.parent
META = {
    "year": ["기준년도", "공시년도", "공시연도", "기준연도", "연도"],
    "school": ["학교명", "대학명", "대학교명"],
    "campus": ["본분교", "본교분교", "본교/분교"],
    "founding": ["설립구분", "설립유형", "설립"],
    "region": ["지역", "시도", "소재지"],
    "school_type": ["학교종류", "학교구분", "학제"],
}
NA_TOKENS = {"", "-", "－", "해당없음", "N/A", "n/a", "nan", "NaN", "*", "."}


def norm(s):
    s = str(s) if s is not None else ""
    s = re.sub(r"\s+", "", s)
    return re.sub(r"[()\[\]·%/,_\-:]", "", s)


def read_raw(path):
    if path.suffix.lower() in (".xlsx", ".xls"):
        return pd.read_excel(path, header=None, dtype=str)
    last = None
    for enc in ("utf-8-sig", "cp949", "euc-kr"):
        try:
            return pd.read_csv(path, header=None, dtype=str, encoding=enc)
        except UnicodeDecodeError as e:
            last = e
    raise last


def find_header(raw):
    """학교명이 들어 있는 행을 머리글 시작으로 보고, 그 아래 문자열 행을 하위 머리글로 붙인다."""
    start = None
    for i in range(min(15, len(raw))):
        cells = [norm(c) for c in raw.iloc[i].tolist()]
        if any(c in META["school"] for c in cells):
            start = i
            break
    if start is None:
        raise ValueError("머리글에서 '학교명' 열을 찾지 못했다")
    end = start
    for j in range(start + 1, min(start + 3, len(raw))):
        row = raw.iloc[j]
        vals = [v for v in row.tolist() if isinstance(v, str) and v.strip()]
        numeric = sum(bool(re.fullmatch(r"[\d,.\-]+", v.strip())) for v in vals)
        # 하위 머리글: 학교명 열이 비어 있고 숫자 셀이 거의 없다
        school_idx = [k for k, c in enumerate(raw.iloc[start].tolist()) if norm(c) in META["school"]][0]
        if (pd.isna(row.iloc[school_idx]) or not str(row.iloc[school_idx]).strip()) and numeric <= len(vals) * 0.2:
            end = j
        else:
            break
    levels = []
    for i in range(start, end + 1):
        lv = raw.iloc[i].tolist()
        if i < end:  # 병합 셀은 오른쪽으로 채운다
            filled, prev = [], ""
            for v in lv:
                if isinstance(v, str) and v.strip():
                    prev = v.strip()
                filled.append(prev)
            lv = filled
        levels.append(["" if (v is None or (isinstance(v, float) and pd.isna(v))) else str(v).strip() for v in lv])
    names = []
    for k in range(raw.shape[1]):
        parts = []
        for lv in levels:
            if lv[k] and (not parts or parts[-1] != lv[k]):
                parts.append(lv[k])
        names.append(parts)
    return end + 1, names


def load_indicators():
    ind = pd.read_csv(SKILL / "references" / "indicators.csv", dtype=str).fillna("")
    out = []
    for r in ind.to_dict("records"):
        r["aliases"] = [norm(a) for a in r["aliases"].split("|") if a]
        r["exclude"] = [norm(a) for a in r["exclude"].split("|") if a]
        out.append(r)
    return out


def to_num(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    s = str(v).strip().replace(",", "")
    if s in NA_TOKENS:
        return None
    s = s.rstrip("%")
    try:
        return float(s)
    except ValueError:
        return None


def map_columns(names, indicators):
    meta, chosen, ambiguous, unmapped = {}, {}, [], []
    for k, parts in enumerate(names):
        full = norm("".join(parts))
        last = norm(parts[-1]) if parts else ""
        for key, al in META.items():
            if key not in meta and (last in al or full in al):
                meta[key] = k
    cands = {}
    for k, parts in enumerate(names):
        if k in meta.values() or not parts:
            continue
        full = norm("".join(parts))
        raw_last = parts[-1]
        hit = False
        for ind in indicators:
            if any(x in full for x in ind["exclude"]):
                continue
            if any(a in full for a in ind["aliases"]):
                rate_like = bool(re.search(r"율|률|%|당|등록금|장학금|경쟁", raw_last))
                score = (2 if rate_like else 1) + (1 if any(a in norm(raw_last) for a in ind["aliases"]) else 0)
                # 별칭이 길수록(구체적일수록) 우선
                score += max(len(a) for a in ind["aliases"] if a in full) / 100
                cands.setdefault(ind["id"], []).append((score, k))
                hit = True
        if not hit:
            unmapped.append(" > ".join(parts))
    for iid, lst in cands.items():
        lst.sort(reverse=True)
        chosen[iid] = lst[0][1]
        if len(lst) > 1 and int(lst[0][0]) == int(lst[1][0]):
            ambiguous.append({"indicator": iid, "columns": [" > ".join(names[k]) for _, k in lst]})
    # 한 열이 두 지표에 잡히면 점수가 높은 쪽만 남긴다
    used = {}
    for iid, k in list(chosen.items()):
        sc = max(s for s, kk in cands[iid] if kk == k)
        if k in used and used[k][0] >= sc:
            del chosen[iid]
            continue
        if k in used:
            del chosen[used[k][1]]
        used[k] = (sc, iid)
    return meta, chosen, ambiguous, unmapped


def process(path, indicators, include_branch, year_hint):
    raw = read_raw(path)
    body_start, names = find_header(raw)
    meta, chosen, ambiguous, unmapped = map_columns(names, indicators)
    body = raw.iloc[body_start:].reset_index(drop=True)
    rows, skipped = [], 0
    for _, r in body.iterrows():
        school = r.iloc[meta["school"]] if "school" in meta else None
        if not isinstance(school, str) or not school.strip() or "합계" in school or "평균" in school:
            skipped += 1
            continue
        campus = str(r.iloc[meta["campus"]]).strip() if "campus" in meta and isinstance(r.iloc[meta["campus"]], str) else "본교"
        if not include_branch and "분교" in campus and "본교" not in campus:
            continue
        year = to_num(r.iloc[meta["year"]]) if "year" in meta else year_hint
        if year is None:
            skipped += 1
            continue
        base = {
            "year": int(year), "school": school.strip(), "campus": campus,
            "founding": str(r.iloc[meta["founding"]]).strip() if "founding" in meta else "",
            "region": str(r.iloc[meta["region"]]).strip() if "region" in meta else "",
            "school_type": str(r.iloc[meta["school_type"]]).strip() if "school_type" in meta else "",
        }
        for iid, k in chosen.items():
            v = to_num(r.iloc[k])
            rows.append({**base, "indicator": iid, "value": v, "source_file": path.name,
                         "source_column": " > ".join(names[k])})
    rep = {
        "file": path.name, "header_rows": body_start, "meta_columns": {k: " > ".join(names[v]) for k, v in meta.items()},
        "mapped": {iid: " > ".join(names[k]) for iid, k in chosen.items()},
        "ambiguous": ambiguous, "unmapped_columns": unmapped[:40], "skipped_rows": skipped,
        "year_from": "column" if "year" in meta else ("filename" if year_hint else "missing"),
    }
    return rows, rep


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("inputs", nargs="+")
    ap.add_argument("--out", default="workspace")
    ap.add_argument("--include-branch", action="store_true", help="분교도 포함")
    a = ap.parse_args()
    files = []
    for p in map(Path, a.inputs):
        files += sorted(x for x in p.rglob("*") if x.suffix.lower() in (".csv", ".xlsx", ".xls")) if p.is_dir() else [p]
    if not files:
        sys.exit("입력 파일이 없다 (CSV/XLSX)")
    indicators = load_indicators()
    all_rows, reports, errors = [], [], []
    for f in files:
        m = re.search(r"(20\d{2})", f.name)
        try:
            rows, rep = process(f, indicators, a.include_branch, int(m.group(1)) if m else None)
            all_rows += rows
            reports.append(rep)
        except Exception as e:  # 파일 하나가 깨져도 나머지는 진행하고 보고한다
            errors.append({"file": f.name, "error": str(e)})
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(all_rows)
    if df.empty:
        json.dump({"files": reports, "errors": errors}, open(out / "load_report.json", "w"), ensure_ascii=False, indent=2)
        sys.exit("지표 열을 하나도 찾지 못했다. load_report.json 의 unmapped_columns 를 확인하라")
    key = ["year", "school", "campus", "indicator"]
    dups = df[df.duplicated(key, keep=False)]
    conflict_list = [
        {"year": int(k[0]), "school": k[1], "indicator": k[3], "values": g["value"].tolist(), "files": g["source_file"].tolist()}
        for k, g in dups.groupby(key) if g["value"].nunique(dropna=False) > 1
    ]
    # 중복이면 값이 있는 행을 남긴다(결측 '-' 행보다 우선). 값이 서로 다르면 conflicts 로 보고한다
    df = df.assign(_has=df["value"].notna()).sort_values("_has", kind="stable")
    df = df[~df.duplicated(key, keep="last")].drop(columns="_has").sort_index()
    df.to_csv(out / "tidy.csv", index=False, encoding="utf-8-sig")
    summary = {
        "files": reports, "errors": errors, "rows": len(df),
        "schools": int(df["school"].nunique()), "years": sorted(df["year"].unique().tolist()),
        "indicators": sorted(df["indicator"].unique().tolist()),
        "missing_values": int(df["value"].isna().sum()),
        "conflicting_duplicates": len(conflict_list), "conflicts": conflict_list[:50],
    }
    json.dump(summary, open(out / "load_report.json", "w"), ensure_ascii=False, indent=2)
    print(json.dumps({k: summary[k] for k in ("rows", "schools", "years", "indicators", "missing_values", "conflicting_duplicates")}, ensure_ascii=False))
    for r in reports:
        if r["ambiguous"]:
            print("⚠ 모호한 열:", r["file"], json.dumps(r["ambiguous"], ensure_ascii=False))
    for e in errors:
        print("✗ 읽기 실패:", e["file"], e["error"])


if __name__ == "__main__":
    main()
