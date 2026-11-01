---
name: univ-disclosure
description: 대학알리미(대학정보공시, academyinfo.go.kr)에서 내려받은 공시 데이터(CSV/XLSX)로 한 대학의 핵심 지표를 비교군과 견주어 분석하고, 검증을 통과한 HTML 리포트를 만든다. 다루는 지표는 신입생 충원율, 재학생 충원율, 졸업생 취업률, 중도탈락 학생 비율, 전임교원 확보율, 전임교원 1인당 학생 수, 1인당 등록금, 1인당 장학금, 교육비 환원율, 신입생 경쟁률. 사용자가 "대학공시 분석", "대학알리미 데이터 분석", "○○대 충원율/취업률 비교", "우리 대학 공시 지표 리포트", "/univ-disclosure"라고 하거나 대학알리미 다운로드 파일을 주며 분석을 요청하면 발동한다. 기업 공시(DART), 고등학교·학원 정보, 대학 입시 상담(합격 가능성 예측)은 대상이 아니다.
---

# 대학공시 데이터 분석 (대학알리미)

한 대학의 공시 지표를 **비교군·전체와 견주어** 강점·약점·추세를 찾고, 숫자가 검증된 HTML 리포트로 낸다.
이 스킬은 하네스 엔지니어링 6가지 구조로 짜여 있다. 각 구조가 어느 파일에 있는지는 `README.md` 표를 본다.

> 핵심 원칙: **숫자는 스크립트가 만들고, 모델은 해석만 쓴다.** 모델이 직접 계산하거나 기억으로 수치를 채우지 않는다.

## 0. 시작 전에 (메모리)

1. `memory/lessons.md`를 읽는다. 지난 실행에서 배운 함정(열 이름 변형, 연도 해석 등)이 적혀 있다.
2. `memory/run_log.jsonl` 마지막 몇 줄을 본다. 같은 대학을 전에 분석했다면 그때의 비교군 규칙을 기본값으로 제안한다.

## 1. 요청 확인 (가드레일: 입력)

다음 셋이 정해져야 시작한다. 빠진 것만 한 번에 묻는다.

| 항목 | 기본값 | 메모 |
|---|---|---|
| 대상 대학 | 없음(필수) | 정식 명칭. 본교 기준. 분교를 보려면 사용자가 명시 |
| 데이터 파일 | 없음(필수) | 대학알리미에서 내려받은 CSV/XLSX. 받는 법은 `references/data-sources.md` |
| 비교군 | 같은 설립구분·같은 지역 | 사용자가 학교 목록을 주면 그것을 쓴다 |

- 파일이 없으면 **수치를 지어내지 않는다.** 다운로드 방법을 안내하고 멈춘다. 연습용이면 `sample_data/`(가상 데이터)를 쓸 수 있다고 알리되, 결과에 "가상 데이터"라고 표시한다.
- 이 환경에서 대학알리미 사이트에 직접 접속이 안 될 수 있다. 접속을 시도해 실패하면 사용자에게 파일을 요청한다.

## 2. 워크플로우 (오케스트레이션)

작업 폴더는 `workspace/`(사용자 작업 디렉터리 아래)로 한다. `SK=~/.claude/skills/univ-disclosure`(프로젝트 스킬이면 `.claude/skills/univ-disclosure`).

```bash
# Step 1. 적재·정규화  → workspace/tidy.csv, load_report.json
python3 $SK/scripts/load.py <파일 또는 폴더> --out workspace

# Step 2. 지표 계산    → workspace/analysis.json (+ memory/run_log.jsonl 기록)
python3 $SK/scripts/analyze.py --tidy workspace/tidy.csv --school "한빛대학교" \
        [--peer-rule same_founding_region|same_founding|same_region|all] [--peers "A대학교,B대학교"] [--year 2026] \
        --out workspace/analysis.json

# Step 3. 해석 작성    → workspace/narrative.md  (모델이 쓴다. 아래 규칙)

# Step 4. 리포트       → workspace/report.html
python3 $SK/scripts/report.py --analysis workspace/analysis.json --narrative workspace/narrative.md --out workspace/report.html

# Step 5. 검증         → workspace/verify_report.json (실패 시 종료 코드 1)
python3 $SK/scripts/verify.py --dir workspace
```

### 단계별 판단 지점

- **Step 1 뒤**: `load_report.json`을 확인한다.
  - `ambiguous`(한 지표에 여러 열 후보) → 어떤 열을 썼는지 사용자에게 보여 주고 확인받는다.
  - `unmapped_columns`에 분석에 필요한 지표가 있으면 `references/indicators.csv`의 `aliases`에 별칭을 더하고 Step 1을 다시 돈다. 더한 별칭은 `memory/lessons.md`에 적는다.
  - `conflicting_duplicates` > 0 → 같은 학교·연도·지표에 값이 둘 이상이다. 어느 파일이 최신인지 사용자에게 묻는다.
  - `errors`(읽기 실패 파일) → 파일 이름과 이유를 알린다.
- **Step 2 뒤**: `warnings`가 있으면 해석 전에 해결한다. 비교군이 3개교 미만이면 `--peer-rule`을 넓힐지 묻는다.
- **Step 5 실패**: 오류 메시지대로 고친 뒤 **Step 3~5를 다시 돈다.** 최대 3회. 3회째도 실패하면 남은 오류를 그대로 보고하고 멈춘다(숨기지 않는다).

## 3. 해석 작성 규칙 (Step 3)

`analysis.json`만 보고 `workspace/narrative.md`를 쓴다. 형식은 `references/narrative-guide.md`.

- 숫자는 `analysis.json`에 있는 값만 그대로 옮긴다. 새로 더하거나 나누지 않는다. 필요한 숫자가 없으면 `analyze.py`를 고치거나 "자료 없음"이라고 쓴다.
- 기준연도를 첫 문단에 밝힌다. 공시연도와 기준연도가 다른 지표(취업률 등)는 `references/indicators-guide.md`의 주의를 따른다.
- 비교는 항상 **비교군 규칙과 개교 수**를 함께 쓴다("같은 사립·대전 3개교 중 1위").
- '내부 경보선'은 공식 기준이 아니다. "정부 평가 기준 미달"처럼 쓰지 않는다.
- 단정·낙인 표현 금지(`references/guardrails.md`). 원인은 추정이면 "가능성"으로 쓰고, 공시 자료로 확인되지 않는다고 밝힌다.

## 4. 결과 전달

- `report.html` 경로, 한 줄 결론, 강점 2개·약점 2개, 검증 결과(통과 항목 수, 경고)를 짧게 알린다.
- 가상 데이터로 돌렸으면 맨 앞에 "가상 데이터 결과"라고 쓰고, Step 4에 `--banner "가상 데이터 결과"`를 붙인다.
- 실행 중 새로 알게 된 함정이 있으면 `memory/lessons.md`에 한 줄 추가한다(날짜·현상·해결).

## 5. 빠른 질문

"○○대 취업률 몇 %야?"처럼 숫자 하나를 물으면 Step 1~2만 돌리고 `analysis.json`에서 값·전년 대비·비교군 순위를 답한다. 리포트는 만들지 않고, 원하면 만들어 준다고 한 줄 덧붙인다.

## 참고 파일

| 파일 | 내용 |
|---|---|
| `references/data-sources.md` | 대학알리미에서 파일 받는 법, 파일 형태의 특징 |
| `references/indicators.csv` | 지표 사전(정의·단위·방향·상식 범위·열 별칭) — 도구가 읽는다 |
| `references/indicators-guide.md` | 지표 해석 주의(기준연도, 정원내/외, 분교) |
| `references/thresholds.json` | 내부 경보선(공식 기준 아님) |
| `references/guardrails.md` | 해서는 안 되는 것 |
| `references/narrative-guide.md` | 해석 문단 형식과 예시 |
| `evals/` | 평가 시나리오와 채점 기준 |
