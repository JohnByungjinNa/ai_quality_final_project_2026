# qa-observer 실행 가이드

## 역할

`qa-observer`는 기존 FastAPI와 Streamlit 대시보드와 독립적으로 실행된다.

- v1 이벤트 계약 검증
- 중복 이벤트 멱등 처리
- 이벤트 유형·UTC 일자별 JSONL append
- 일별 KPI CSV 집계
- 테스트 실행 보고서 자동 동기화
- 보존 기간 정리
- health와 Prometheus 형식 자체 metric 제공

SQLite는 생성하거나 사용하지 않는다. `contracts/qa_observer/sqlite-v1.sql`은 향후 확장 계약이다.

## 로컬 실행

```powershell
.venv\Scripts\python.exe -m uvicorn qa_observer.app:app --host 127.0.0.1 --port 8010
```

확인 주소:

- Health: `http://127.0.0.1:8010/health`
- Metrics: `http://127.0.0.1:8010/metrics`
- API 문서: `http://127.0.0.1:8010/docs`
- 집계 조회: `http://127.0.0.1:8010/v1/aggregates`
- 대시보드 KPI 요약: `http://127.0.0.1:8010/v1/dashboard/summary`
- 일별 시계열: `http://127.0.0.1:8010/v1/timeseries`
- 최근 상세 이벤트: `http://127.0.0.1:8010/v1/events`

## Docker 실행

```powershell
docker compose up -d qa-observer
docker compose ps qa-observer
docker compose logs --tail 100 qa-observer
```

호스트 포트는 `127.0.0.1:8010`에만 바인딩한다. 기존 `api`, `dashboard`, `prometheus`, `grafana` 서비스 구성과 화면은 유지한다.

## 저장 파일

```text
data/qa_observer/events/<event_type>/YYYY-MM-DD.jsonl
data/qa_observer/aggregates/daily-aggregates.csv
data/qa_observer/state/collector-checkpoints.json
logs/qa_observer/qa-observer.log
```

이 경로는 `.gitignore`와 프로젝트 소스 백업 제외 대상에 포함된다.

## 이벤트 수신

```powershell
$event = Get-Content .\sample-event.json -Raw -Encoding UTF8
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8010/v1/events `
  -ContentType 'application/json' `
  -Body $event
```

응답:

- 신규 저장: `stored=true`, `duplicate=false`
- 같은 이벤트 재전송: HTTP 200, `duplicate=true`
- 같은 key와 다른 payload: HTTP 409
- 계약 위반 또는 원문 field 추가: HTTP 422

## 테스트 보고서 수집

기본 30초마다 `reports/test_runs/*/run_manifest.json`을 검색한다. `run_id`별 fingerprint를 checkpoint에 저장해 이미 처리한 실행은 건너뛴다.

수동 실행:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8010/v1/collectors/test-reports/run
```

실행 단위 PASS/FAIL/ERROR뿐 아니라 케이스별 품질·안전성, 공급자 usage 기반 LLM 토큰, RAG 검색, API 요청 이벤트를 수집한다.

애플리케이션은 `QA_OBSERVER_URL`로 먼저 전송하고, Observer가 중단되었거나 URL이 없으면 `data/qa_observer/outbox`에 JSONL로 적재한다. Observer 스케줄러가 outbox를 원자적으로 가져와 계약 검증 후 이벤트 저장소와 일별 CSV 집계에 반영한다.

## 환경 변수

| 변수 | 기본값 | 설명 |
|---|---|---|
| `QA_OBSERVER_DATA_DIR` | `data/qa_observer` | JSONL·CSV·checkpoint 경로 |
| `QA_OBSERVER_URL` | 없음 | 이벤트 수신 주소. Docker 내부 기본값은 `http://qa-observer:8010` |
| `QA_OBSERVER_TIMEOUT_SECONDS` | `0.25` | 전송 실패를 outbox로 전환하기 전 HTTP 제한 시간(초) |
| `QA_OBSERVER_HMAC_KEY` | 없음 | 질문·응답·문서 식별용 HMAC 키. 미설정 시 지문은 `null` |
| `QA_OBSERVER_HMAC_KEY_VERSION` | `v1` | HMAC 키 회전 버전 |
| `QA_OBSERVER_PRICE_CATALOG` | `config/llm_prices.json` | 공급자 모델 단가 스냅샷 경로 |
| `QA_OBSERVER_USD_KRW` | 없음 | 명시적 USD/KRW 적용 환율. 없으면 비용은 `null` |
| `QA_OBSERVER_DAILY_BUDGET_KRW` | `50000` | 일 API 비용 예산 |
| `QA_OBSERVER_GRAFANA_WEBHOOK_TOKEN` | 없음 | Grafana 내부 webhook Bearer token. 공유·운영 환경에서 반드시 긴 무작위 값 사용 |
| `QA_OBSERVER_LOG_DIR` | `logs/qa_observer` | 회전 log 경로 |
| `QA_OBSERVER_REPORTS_DIR` | `reports/test_runs` | 테스트 실행 원천 |
| `QA_OBSERVER_ENVIRONMENT` | `local` | local/dev/stage/prod |
| `QA_OBSERVER_SYNC_INTERVAL_SECONDS` | `30` | 보고서 검색 주기 |
| `QA_OBSERVER_EVENT_RETENTION_DAYS` | `90` | API·LLM·RAG 상세 로그 |
| `QA_OBSERVER_COLLECTOR_RETENTION_DAYS` | `30` | 수집기 이벤트 |
| `QA_OBSERVER_QUALITY_RETENTION_DAYS` | `365` | 테스트·품질·안전성 이벤트 |
| `QA_OBSERVER_DEFECT_RETENTION_DAYS` | `730` | 결함 이벤트 |
| `QA_OBSERVER_AGGREGATE_RETENTION_DAYS` | `730` | CSV 집계 |

## 검증

```powershell
.venv\Scripts\python.exe -m pytest tests\test_qa_observer_contracts.py tests\test_qa_observer_service.py -q
```

전체 프로젝트:

```powershell
.venv\Scripts\python.exe -m pytest -q
```

종합 상황판 인수 검증과 운영 절차는 `docs/ai_qa_dashboard_operations_guide.md`를 따른다.

## 주의 사항

- 이벤트 payload에 질문·프롬프트·응답·검색 chunk 원문을 추가하지 않는다. 금지 필드가 있으면 전송·outbox 저장 전에 폐기한다.
- `QA_OBSERVER_HMAC_KEY`는 `.env` 또는 비밀 저장소에 두며 저장소에 커밋하지 않는다. 운영 키는 충분히 긴 무작위 값으로 설정한다.
- LLM 토큰은 문자 수로 추정하지 않고 OpenAI 응답의 `usage` 값을 기록한다. 비용은 Task 5의 가격 스냅샷 연결 전까지 `null`이다.
- 기본 가격표는 공식 OpenAI gpt-4o-mini 단가를 기록한 스냅샷이다. 환율은 자동 추정하지 않으며 `QA_OBSERVER_USD_KRW`가 설정된 호출부터 micro-KRW 비용과 snapshot ID를 함께 기록한다.
- 기간 조회의 기본 범위는 최근 7일, 최대 범위는 366일이다. 비율 API 값은 0~100이며 데이터가 없으면 `null`이다.

## Task 5 집계 조회 예시

```powershell
Invoke-RestMethod "http://127.0.0.1:8010/v1/dashboard/summary?date_from=2026-07-08&date_to=2026-07-14"
Invoke-RestMethod "http://127.0.0.1:8010/v1/timeseries?metric=llm.total_tokens&provider=openai"
Invoke-RestMethod "http://127.0.0.1:8010/v1/events?event_type=safety.violation.detected&limit=20"
```

Prometheus는 `qa-observer:8010/metrics`를 추가 scrape한다. 현재 UTC 일자의 파일 집계를 다음 gauge로 제공한다.

```promql
qa_dashboard_aggregate_value{metric="api.requests",aggregation="sum"}
qa_dashboard_aggregate_value{metric="llm.total_tokens",aggregation="sum"}
qa_dashboard_aggregate_value{metric="quality.safety.score",aggregation="average"}
time() - qa_dashboard_data_updated_timestamp_seconds
```
- 현재 API는 로컬 내부 수집용이다. 외부 네트워크 공개 전 인증과 TLS를 추가해야 한다.
- JSONL을 수동 편집하지 않는다. 손상 기록은 원문 없이 파일명·행 번호·오류 유형만 log에 남는다.
- CSV와 checkpoint는 qa-observer만 쓴다. 다른 프로세스는 읽기 전용으로 사용한다.
