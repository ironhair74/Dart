# 평가

- `tests/test_pipeline.py`: 결정론적 회귀 테스트(스크립트만). `python3 -m pytest tests -q`
- `evals.json`: 모델이 스킬을 따라 했는지 보는 시나리오. 각 assertion 을 사람 또는 채점 모델이 통과/실패로 매긴다.
- `trigger_queries.json`: description 이 맞는 요청에만 발동하는지 확인하는 질문 목록.

스킬을 고칠 때마다 테스트 → 시나리오 순으로 돌리고, 실패한 항목은 SKILL.md·references 를 고쳐 다시 돌린다.
