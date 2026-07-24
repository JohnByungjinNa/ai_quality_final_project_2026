# Task 5 저장·집계 API 구현 보고서

## 상태

`APPROVED` — 2026-07-14 사용자로부터 구현 1~5 전체 승인을 받았다.

## 구현 1~5

1. 파일 집계 필터 확장
   - SQLite를 추가하지 않고 JSONL 상세 이벤트와 일별 CSV 집계를 사용한다.
   - 날짜, 환경, 서비스, 공급자, 모델, metric 필터를 지원한다.
2. 대시보드 KPI 요약 API
   - `/v1/dashboard/summary`에서 품질점수, 테스트 통과율, API p95, 오류율, 안전성 위반, 토큰·비용, RAG no-result, 데이터 신선도를 반환한다.
   - 비율은 0~100, 비용은 KRW, 처리 시간은 millisecond 단위다.
   - 데이터 또는 가격이 없으면 0으로 위장하지 않고 `null`과 적용률을 반환한다.
3. 시계열·상세 조회 API
   - `/v1/timeseries`는 날짜·metric별 sum/count/average/min/max를 반환한다.
   - GET `/v1/events`는 원문이 제거된 최신 JSONL 이벤트를 최대 500건 반환한다.
4. Prometheus 연결
   - Prometheus scrape 대상에 `qa-observer:8010`을 추가했다.
   - 오늘 집계와 데이터 최종 갱신 시각을 낮은 카디널리티 gauge로 노출한다.
5. 비용 스냅샷
   - 공식 OpenAI gpt-4o-mini 단가를 버전이 있는 로컬 JSON 스냅샷으로 기록했다.
   - 실제 provider usage와 명시적 `QA_OBSERVER_USD_KRW` 환율이 모두 있을 때만 micro-KRW 비용을 계산한다.
   - 환율이 없으면 비용은 `null`이며 가격 적용률로 미산정 호출을 확인할 수 있다.

## 주요 파일

- `qa_observer/query.py`: JSONL·CSV 조회와 KPI 계산
- `qa_observer/pricing.py`: 공급자 usage 기반 재현 가능한 비용 계산
- `config/llm_prices.json`: 가격 출처·검증 시각·모델 단가 스냅샷
- `qa_observer/app.py`: summary, timeseries, events API
- `qa_observer/metrics.py`: 대시보드 집계 Prometheus gauge
- `qa_observer/storage.py`: 기간·공급자·모델 필터
- `docker/prometheus.yml`: qa-observer scrape 추가
- `tests/test_qa_observer_service.py`, `tests/test_qa_observer_telemetry.py`: 집계·비용 검증

## 검증 결과

- Task 5 관련 테스트: 10 PASS
- 전체 회귀 테스트: 99 PASS
- Python 컴파일: PASS
- Docker Compose 구문: PASS
- 기존 Starlette/httpx deprecation warning 1건 유지
- Docker 컨테이너 실구동: 기존 사용자 요청대로 추후 체크 항목 유지

## 가격 기준

- 모델: `gpt-4o-mini`
- 공식 단가: 입력 USD 0.15, 캐시 입력 USD 0.075, 출력 USD 0.60 / 1M tokens
- 출처: <https://developers.openai.com/api/docs/models/gpt-4o-mini>
- 가격 스냅샷: `openai-standard-20260714`
- 환율: 운영자가 `QA_OBSERVER_USD_KRW`로 명시하며 호출 당시 snapshot ID에 포함

## 사용자 확인 항목

- [x] 구현 1: JSONL·CSV 기반 필터 집계 승인
- [x] 구현 2: KPI summary 응답과 데이터 없음 처리 승인
- [x] 구현 3: 시계열·최근 이벤트 조회 승인
- [x] 구현 4: qa-observer Prometheus scrape와 gauge 승인
- [x] 구현 5: 공식 USD 가격표 + 명시적 환율 기반 비용 계산 승인

## 추후 체크

- Docker Desktop 실행 후 Prometheus targets에서 `qa-observer`가 UP인지 확인
- 실제 OpenAI 호출 전 `QA_OBSERVER_USD_KRW` 운영 환율 설정
- 가격표는 48시간 이상 확인되지 않으면 주의, 7일 이상이면 위험으로 표시하도록 Task 6 화면에 연결
