#!/usr/bin/env python3
"""테스트용 '가상' 공시 파일을 만든다. 학교명·수치는 모두 지어낸 것이며 실제 대학과 무관하다.

대학알리미 다운로드 파일의 형태(2줄 머리글, cp949 CSV, 연도 없는 XLSX, 분교·합계 행)를 흉내 낸다.
"""
import random
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
random.seed(7)
SCHOOLS = [
    ("한빛대학교", "사립", "대전"), ("가람대학교", "사립", "대전"), ("누리대학교", "사립", "충남"),
    ("다온대학교", "사립", "충남"), ("마루대학교", "사립", "충북"), ("바다대학교", "국립", "충남"),
    ("새솔대학교", "사립", "대전"), ("아라대학교", "사립", "세종"), ("자람대학교", "국립", "충북"),
    ("차오름대학교", "사립", "충남"), ("하늘대학교", "사립", "대전"), ("푸른대학교", "사립", "충북"),
]
YEARS = [2024, 2025, 2026]


def base(i):
    r = random.Random(i)
    return {"fill": r.uniform(88, 101), "enr": r.uniform(85, 115), "emp": r.uniform(52, 72),
            "drop": r.uniform(3, 9), "comp": r.uniform(3, 9), "fac": r.uniform(68, 95),
            "spf": r.uniform(20, 34), "tui": r.uniform(6300, 8400), "sch": r.uniform(3200, 5200),
            "ret": r.uniform(120, 190), "quota": r.choice([1200, 1500, 1800, 2200, 2800])}


def main():
    student = []
    finance = {y: [] for y in YEARS}
    for i, (name, f, reg) in enumerate(SCHOOLS):
        b = base(i)
        for t, y in enumerate(YEARS):
            drift = -1.6 * t if name == "한빛대학교" else random.uniform(-1, 1) * t
            fill = min(100.0, b["fill"] + drift)
            quota = b["quota"]
            student.append(["대학교", f, reg, name, "본교", y, quota, round(quota * fill / 100), round(fill, 1),
                            round(b["enr"] + drift, 1), round(b["emp"] + random.uniform(-2, 2), 1),
                            round(b["drop"] - drift * 0.3, 1), round(b["comp"] + drift * 0.3, 1)])
            finance[y].append([name, f, reg, "본교", round(b["fac"] + 3, 1), round(b["fac"] + random.uniform(-1, 2) * t, 1),
                               round(b["spf"] - t * 0.3, 1), f"{b['tui'] + 60 * t:,.0f}", f"{b['sch'] + 90 * t:,.0f}",
                               round(b["ret"] + random.uniform(-4, 4), 1)])
    # 분교·합계 행: 로더가 걸러내야 한다
    student.append(["대학교", "사립", "강원", "한빛대학교", "분교", 2026, 600, 410, 68.3, 70.1, 48.0, 12.0, 1.5])
    student.append(["", "", "", "합계", "", 2026, "", "", "", "", "", "", ""])
    student.append(["대학교", "사립", "충남", "아라대학교", "본교", 2024, 1500, "-", "-", 99.0, "-", 4.2, 3.0])

    top = ["학교종류", "설립구분", "지역", "학교명", "본분교", "기준년도", "신입생 충원율", "신입생 충원율", "신입생 충원율",
           "재학생 충원율(%)", "졸업생 취업률(%)", "중도탈락 학생 비율(%)", "신입생 경쟁률"]
    sub = ["", "", "", "", "", "", "모집인원", "입학자", "충원율(%)", "", "", "", ""]
    rows = [top, sub] + [[("" if v is None else v) for v in r] for r in student]
    pd.DataFrame(rows).to_csv(HERE / "학생지표_2024-2026.csv", header=False, index=False, encoding="cp949")

    cols = ["학교명", "설립구분", "지역", "본분교", "전임교원 확보율(학생정원 기준)", "전임교원 확보율(재학생 기준)",
            "전임교원 1인당 학생 수", "1인당 연간 평균 등록금(천원)", "1인당 장학금(천원)", "교육비 환원율(%)"]
    for y, rs in finance.items():
        pd.DataFrame(rs, columns=cols).to_excel(HERE / f"교육재정_{y}.xlsx", index=False)
    print("가상 샘플 생성:", sorted(p.name for p in HERE.iterdir() if p.suffix in (".csv", ".xlsx")))


if __name__ == "__main__":
    main()
