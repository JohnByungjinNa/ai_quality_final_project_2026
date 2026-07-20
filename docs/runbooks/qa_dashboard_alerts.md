# AI QA 대시보드 알림 런북

## 목적과 범위

이 문서는 Grafana의 `AI QA Monitoring` 폴더에 파일 프로비저닝되는 운영 알림의 확인 및 해제 절차를 정의한다. 알림은 내부 `qa-observer` 웹훅으로 전달되어 `defect.changed` 이벤트와 대시보드의 `열린 결함` 수치로 집계된다.

외부 Slack 전송과 Jira 자동 생성은 활성화하지 않았다. 외부 연동은 자격 증명 보관 방식, 수신 채널, 중복 생성 정책을 별도로 승인한 뒤 추가한다. 현재 Jira 등록은 기존 사용자 실행 방식만 사용한다.

## 알림 기준

| Runbook ID | 조건 | 대기 | 심각도 | 우선 확인 |
|---|---:|---:|---|---|
| `observer-down` | `qa_observer_up < 1` 또는 데이터 없음 | 즉시 | critical | qa-observer `/health`, 저장 경로 쓰기 권한, scheduler 상태 |
| `safety-violation` | 안전성 위반 1건 이상 | 즉시 | critical | 위반 category·정책 버전, 차단 여부, 재현 케이스 |
| `api-error-rate` | API 오류율 2% 초과 | 1분 | critical | 5xx/timeout, API 로그, 의존 서비스 상태 |
| `api-p95-latency` | p95 응답시간 5초 초과 | 2분 | warning | API·RAG·LLM 구간별 지연, 최근 배포 |
| `test-pass-rate` | 테스트 통과율 95% 미만 | 1분 | warning | 실패 케이스 재실행, 평가 오류와 실제 결함 구분 |
| `rag-no-result` | RAG no-result 비율 5% 초과 | 2분 | warning | 질의 유형, 인덱스 최신성, 검색 키워드 |
| `llm-budget-warning` | 일 비용 40,000원 초과 | 1분 | warning | 모델·operation별 토큰, 캐시 적용 가능성 |
| `llm-budget-critical` | 일 비용 50,000원 초과 | 즉시 | critical | 비정상 반복 호출, 모델 변경, 실행 중단 필요성 |

비용 규칙은 가격이 적용된 `llm.cost_micros_krw` 집계만 사용한다. 가격 정보가 없어 비용 메트릭이 생성되지 않으면 비용 알림도 평가할 데이터가 없으므로 먼저 가격 적용률을 확인한다.

## 공통 처리 절차

1. Grafana Alerting에서 `alertname`, `service`, `severity`, 시작 시각을 확인한다.
2. Streamlit의 `종합 현황 > AI QA 종합 현황`에서 같은 기간과 서비스를 선택하고 열린 결함 및 관련 KPI를 확인한다.
3. 위 표의 우선 확인 항목을 점검하고 재현 가능한 경우 최소 1회 재현한다.
4. 실제 제품 결함이면 기존 Jira 등록 기능으로 이슈를 생성하고 Grafana 규칙명과 발생 시각을 기록한다. 질문·프롬프트·응답 원문은 이 이벤트 저장소에 복사하지 않는다.
5. 원인을 제거한 뒤 다음 평가 주기에서 조건이 정상화되는지 확인한다. Grafana의 resolved 웹훅이 수신되면 동일 fingerprint의 결함 상태가 `resolved`로 바뀐다.

## 알림이 해제되지 않을 때

- `qa-observer`의 `/metrics`에서 해당 원천 메트릭이 실제로 정상 범위인지 확인한다.
- Grafana 데이터소스 UID가 `prometheus`이고 Prometheus 타깃이 정상인지 확인한다.
- `qa_observer_grafana_webhook_requests_total`의 `accepted`, `unauthorized`, `rejected` 상태를 확인한다.
- 인증 실패 시 Grafana와 qa-observer 양쪽의 `QA_OBSERVER_GRAFANA_WEBHOOK_TOKEN`이 같은지 확인한다. 토큰 값을 로그나 문서에 기록하지 않는다.
- 웹훅 재시도는 동일 이벤트로 중복 집계되지 않는다. 다른 payload가 같은 event key로 충돌하면 422 응답과 `rejected` 메트릭을 확인한다.

## 프로비저닝 변경 주의

파일로 프로비저닝된 알림 자원은 Grafana UI에서 직접 수정하지 않는다. `docker/grafana/provisioning/alerting` 파일을 수정하고 Grafana를 재시작하거나 Admin API로 reload한다. 특히 notification policy 파일은 정책 트리 전체를 덮어쓰므로 기존 정책이 있는 환경에 적용하기 전에 반드시 백업하고 병합 여부를 검토한다.
