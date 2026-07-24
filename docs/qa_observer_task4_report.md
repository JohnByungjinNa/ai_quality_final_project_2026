# Task 4 계측 연결 구현 보고서

## 상태

`APPROVED` — 2026-07-14 사용자로부터 구현 1~5 전체 승인을 받았다.

## 구현 1~5

1. API 요청 계측
   - trace ID, route template, 상태 코드, 처리 시간, 오류 유형을 기록한다.
   - 질문 원문이 포함되는 URL 대신 낮은 카디널리티의 route template을 사용한다.
2. LLM usage 계측
   - OpenAI 응답 `usage`에서 input/output/cached/reasoning/total token을 기록한다.
   - 성공과 호출 오류, JSON 파싱 오류를 구분한다. 가격 연결 전 비용은 `null`이다.
3. RAG 검색 계측
   - Top-K, 결과 수, no-result, 검색 시간, 순위·점수를 기록한다.
   - 질문, 파일명, chunk 식별자는 HMAC 키가 있을 때만 비가역 지문으로 기록한다.
4. 품질·안전성 계측
   - 규칙 평가와 LLM Judge 평가를 별도 이벤트로 기록한다.
   - 안전성 점수 1 또는 2이면 critical/high 안전성 위반 이벤트를 추가 기록한다.
5. 장애 내성 수집
   - HTTP 전송 실패 시 JSONL outbox에 fsync 후 저장한다.
   - Observer가 원자적으로 회수해 계약 검증·중복 제거 후 이벤트와 CSV 집계에 반영한다.

## 수정 파일

- `api_app.py`, `judge_agent.py`, `knowledge_base.py`
- `dashboard/services/pipeline_runner.py`, `dashboard/components/test_execution_dialog.py`
- `qa_observer/telemetry.py`, `qa_observer/collectors/outbox.py`, `qa_observer/scheduler.py`, `qa_observer/app.py`
- `contracts/qa_observer/event-envelope-v1.schema.json`, `contracts/qa_observer/sqlite-v1.sql`
- `docker-compose.yml`, `tests/test_qa_observer_telemetry.py`

## 검증 결과

- Python 컴파일: PASS
- 기존 관련 테스트: 29 PASS
- 계측 전용 테스트: 5 PASS
- 전체 회귀 테스트: 97 PASS, 기존 Starlette/httpx deprecation warning 1건
- Docker Compose 구문: PASS
- Docker 컨테이너 실구동: 사용자 요청에 따라 추후 검증 체크 항목으로 유지

## 실행 및 확인

```powershell
.venv\Scripts\python.exe -m uvicorn qa_observer.app:app --host 127.0.0.1 --port 8010
$env:QA_OBSERVER_URL = "http://127.0.0.1:8010"
.venv\Scripts\python.exe -m uvicorn api_app:app --host 127.0.0.1 --port 8000
```

확인 경로는 `data/qa_observer/events`, `data/qa_observer/aggregates/daily-aggregates.csv`, `data/qa_observer/outbox`이다.

## 사용자 확인 항목

- [x] 구현 1: API 요청 계측 승인
- [x] 구현 2: 공급자 usage 기반 LLM 토큰 계측 승인
- [x] 구현 3: 원문 없는 RAG 계측 승인
- [x] 구현 4: 규칙·Judge 품질 및 안전성 위반 계측 승인
- [x] 구현 5: HTTP 실패 시 JSONL outbox와 자동 회수 방식 승인

## 추후 작업

- Docker Desktop 실행 후 `qa-observer` container health와 outbox 회수 검증
- Task 5에서 모델 가격 스냅샷과 KRW 환산 비용 연결
- Task 5에서 CSV 집계 조회 API와 Prometheus KPI를 대시보드용으로 확장
