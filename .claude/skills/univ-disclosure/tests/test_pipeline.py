"""가상 샘플로 load → analyze → report → verify 전체를 돌리는 회귀 테스트.  python3 -m pytest tests -q"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

SK = Path(__file__).resolve().parent.parent
PY = sys.executable


def run(*args, ok=True):
    r = subprocess.run([PY, *map(str, args)], capture_output=True, text=True, cwd=SK)
    if ok:
        assert r.returncode == 0, r.stdout + r.stderr
    return r


@pytest.fixture(scope="module")
def ws(tmp_path_factory):
    w = tmp_path_factory.mktemp("ws")
    run(SK / "sample_data/make_sample.py")
    run(SK / "scripts/load.py", SK / "sample_data", "--out", w)
    run(SK / "scripts/analyze.py", "--tidy", w / "tidy.csv", "--school", "한빛대학교",
        "--peer-rule", "same_founding", "--out", w / "analysis.json")
    return w


def test_load(ws):
    rep = json.load(open(ws / "load_report.json"))
    assert rep["schools"] == 12 and rep["years"] == [2024, 2025, 2026]
    assert len(rep["indicators"]) == 10
    assert rep["conflicting_duplicates"] > 0  # 아라대 2024 중복 행을 잡아낸다
    csv = next(f for f in rep["files"] if f["file"].endswith(".csv"))
    assert csv["mapped"]["fresh_fill"] == "신입생 충원율 > 충원율(%)"


def test_branch_and_total_rows_excluded(ws):
    import pandas as pd
    t = pd.read_csv(ws / "tidy.csv", encoding="utf-8-sig")
    assert "합계" not in set(t.school)
    assert set(t.campus) == {"본교"}


def test_analysis_values(ws):
    a = json.load(open(ws / "analysis.json"))
    f = {i["id"]: i for i in a["indicators"]}
    assert a["peer_group"]["n"] == 9
    assert f["fresh_fill"]["value"] == 95.8 and f["fresh_fill"]["yoy"] == -1.6
    assert f["fresh_fill"]["trend"]["label"] == "악화"
    assert f["faculty_secure"]["source_column"] == "전임교원 확보율(재학생 기준)"
    assert len(a["flags"]) == 3


def test_unknown_school_suggests(ws):
    r = run(SK / "scripts/analyze.py", "--tidy", ws / "tidy.csv", "--school", "한빛대", "--out", ws / "x.json", ok=False)
    assert r.returncode != 0 and "한빛대학교" in r.stderr


def test_verify_pass_and_fail(ws):
    (ws / "narrative.md").write_text("## 한 줄 결론\n**2026년 공시 기준 신입생 충원율 95.8%(전년 대비 -1.6%p).**\n", encoding="utf-8")
    run(SK / "scripts/report.py", "--analysis", ws / "analysis.json", "--narrative", ws / "narrative.md", "--out", ws / "report.html")
    assert run(SK / "scripts/verify.py", "--dir", ws).returncode == 0
    (ws / "narrative.md").write_text("2026년 취업률은 71.3%로 부실대학이다.\n", encoding="utf-8")
    r = run(SK / "scripts/verify.py", "--dir", ws, ok=False)
    res = json.loads((ws / "verify_report.json").read_text())
    assert r.returncode == 1
    assert any("근거 없는 숫자" in e for e in res["errors"]) and any("금지 표현" in e for e in res["errors"])
