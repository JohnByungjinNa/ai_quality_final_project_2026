# Task 3 qa-observer 구현 결과

- 상태: `APPROVED`
- 승인 시각: `2026-07-14`
- 저장 방식: JSONL + CSV + checkpoint JSON + 회전 local log
- SQLite 생성: 없음
- 기존 대시보드 변경: 없음

## 1. 구현 범위

- FastAPI 기반 독립 `qa-observer` 서비스
- JSON Schema v1 이벤트 검증
- 동일 `event_id`·`dedup_key` 멱등 처리와 payload 충돌 거절
- 이벤트 유형·UTC 일자별 JSONL 저장
- 일별 KPI CSV 집계와 원자적 파일 교체
- 재시작 시 JSONL 기반 dedup index 재구성
- `reports/test_runs` 자동 검색과 실행 단위 PASS/FAIL/ERROR 동기화
- collector checkpoint 원자적 저장
- 유형별 보존 기간 정리
- 회전 local log
- `/health`, `/metrics`, `/v1/events`, `/v1/aggregates` 제공
- 수동 보고서 수집 endpoint 제공
- 기존 서비스에 의존하지 않는 Docker Compose 서비스 추가

## 2. 주요 파일

| 파일 | 역할 |
|---|---|
| `qa_observer/app.py` | API, lifespan, health, metrics |
| `qa_observer/storage.py` | JSONL append, CSV 집계, dedup, retention |
| `qa_observer/validation.py` | JSON Schema 검증·안전한 오류 응답 |
| `qa_observer/collectors/test_reports.py` | 테스트 보고서 자동 동기화 |
| `qa_observer/scheduler.py` | 주기 실행과 collector 상태 |
| `qa_observer/metrics.py` | Prometheus 형식 자체 metric |
| `qa_observer/logging_utils.py` | 10MB × 5개 회전 log |
| `docs/qa_observer_run_guide.md` | 실행·확인·주의 사항 |

## 3. 실제 검증 결과

| 항목 | 결과 |
|---|---|
| Python 문법 | PASS |
| Docker Compose 구문 | PASS |
| 계약·서비스·보존 테스트 | 5 PASS |
| 전체 프로젝트 테스트 | 92 PASS |
| 실제 로컬 `/health` | healthy |
| 실제 scheduler 상태 | running |
| 기존 manifest 자동 발견 | 12개 |
| 수동 재수집 | 0 processed / 12 skipped |
| 저장된 JSONL record | 13건 |
| 집계 CSV row | 15행 |
| `/metrics` up | 1 |
| raw-content key/value 검사 | PASS |
| CSV header 계약 검사 | PASS |
| 기존 `dashboard/` | 41개 파일 변경 없음 |
| SQLite 파일 | 생성 없음 |

기존 Starlette/httpx deprecation warning 1건은 이번 구현 이전부터 존재하며 테스트 실패가 아니다.

## 4. Docker 검증 상태

- `docker compose config -q`: PASS
- Docker Desktop engine: 현재 미실행
- 따라서 실제 container build·health 확인은 수행하지 못했다.
- Python 로컬 프로세스의 실제 health·metrics·scheduler·파일 생성은 검증했다.

Docker Desktop 실행 후 확인 명령:

```powershell
docker compose up -d --build qa-observer
docker compose ps qa-observer
Invoke-RestMethod http://127.0.0.1:8010/health
docker compose logs --tail 100 qa-observer
```

## 5. 이번 Task에서 하지 않은 것

- 기존 FastAPI 요청 자동 계측
- Judge 실제 token usage 계측
- RAG 검색 이벤트 계측
- 케이스별 품질·안전성 이벤트 발행
- Prometheus scrape 대상 추가
- 새 Streamlit 종합 상황판 화면

위 항목은 각각 Task 4~6에서 진행한다.

## 6. 사용자 확인 항목

1. SQLite 없이 JSONL·CSV·local log 기반 qa-observer 구성을 승인한다.
2. 30초 기본 보고서 검색 주기와 수동 실행 endpoint를 승인한다.
3. 로컬 `127.0.0.1:8010` 및 독립 Docker service 구성을 승인한다.
4. Docker Desktop이 실행되지 않은 상태이므로 container 실제 검증은 추후 수행하는 것을 승인한다.
5. 기존 대시보드 무변경 상태를 승인한다.

답변 양식:

```text
Task 3 구현 1~5: 승인 / 수정 필요
Docker 검증: 추후 진행 / 지금 Docker 실행 후 진행
추가 의견: 없음 / 내용 작성
```

Task 3 구현 1~5 승인 완료. Docker 실제 검증은 추후 체크 항목으로 이관하고 Task 4 LLM·RAG·테스트·안전성·API 계측 연결을 시작한다.
