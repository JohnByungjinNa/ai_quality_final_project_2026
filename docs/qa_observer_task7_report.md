# Task 7 Grafana Alerting·알림·결함 조치 연계 보고서

## 상태

`APPROVED` — 2026-07-14 사용자로부터 구현 1~5 전체 승인을 받았다.

## 구현 1~5

1. Grafana Alerting 규칙 프로비저닝
   - `AI QA Monitoring` 폴더에 8개 규칙을 파일로 관리한다.
   - 수집 서비스 중단, 안전성 위반, API 오류율, API p95, 테스트 통과율, RAG no-result, 일 비용 80%·100%를 감시한다.
   - 모든 규칙에 고정 UID, service·severity·alert_family label, runbook annotation을 부여했다.
2. 내부 contact point와 알림 정책
   - Grafana가 `qa-observer`의 `/v1/alerts/grafana`로 firing과 resolved 알림을 전송한다.
   - Bearer token은 `QA_OBSERVER_GRAFANA_WEBHOOK_TOKEN` 환경변수로 양쪽에 동일하게 주입한다.
   - `alertname`, `service`, `severity`로 묶고 최초 30초, 추가 5분, 반복 4시간 정책을 적용했다.
3. 결함 이벤트 수명주기
   - firing은 `defect.changed/open`, resolved는 동일 fingerprint의 `defect.changed/resolved`로 변환한다.
   - 이벤트 ID와 중복 키를 결정적으로 만들어 Grafana 재시도가 중복 집계되지 않게 했다.
   - 웹훅 annotation·description·질문·응답 원문은 저장하지 않는다.
4. 대시보드 조치 연결
   - summary API에 최신 결함 상태를 기준으로 `open_defect_count`를 제공한다.
   - 신규 종합 현황 화면에 `열린 결함` KPI와 runbook 확인 권장 조치를 추가했다.
5. 런북과 외부 채널 경계
   - 알림별 기준, 우선 확인 항목, 공통 처리·해제 절차를 런북에 작성했다.
   - Slack과 Jira 자동 등록은 활성화하지 않았다. Jira는 기존 사용자 실행 방식만 유지한다.

## 알림 임계값

| 알림 | 조건 | 대기 | 심각도 |
|---|---:|---:|---|
| QA Observer Down | `qa_observer_up < 1` 또는 데이터 없음 | 즉시 | critical |
| Safety Violation | 1건 이상 | 즉시 | critical |
| API Error Rate | 2% 초과 | 1분 | critical |
| API P95 Latency | 5초 초과 | 2분 | warning |
| Test Pass Rate | 95% 미만 | 1분 | warning |
| RAG No Result | 5% 초과 | 2분 | warning |
| LLM Budget Warning | 40,000원 초과 | 1분 | warning |
| LLM Budget Critical | 50,000원 초과 | 즉시 | critical |

## 수정 파일

- `docker/grafana/provisioning/alerting/alert-rules.json`
- `docker/grafana/provisioning/alerting/contact-points.json`
- `docker/grafana/provisioning/alerting/notification-policies.json`
- `docker/grafana/provisioning/datasources/prometheus.yml`
- `docker-compose.yml`
- `qa_observer/grafana_webhook.py`
- `qa_observer/app.py`, `qa_observer/settings.py`, `qa_observer/metrics.py`, `qa_observer/query.py`
- `dashboard/pages_top/overview_dashboard.py`, `dashboard/services/overview_dashboard.py`
- `docs/runbooks/qa_dashboard_alerts.md`
- `tests/test_grafana_alerting.py`, `tests/test_qa_observer_service.py`
- `tests/fixtures/overview_dashboard_app.py`, `tests/test_overview_dashboard.py`

## 검증 결과

- Task 7 관련 테스트: 13 PASS
- 전체 회귀 테스트: 108 PASS
- Python compileall: PASS
- Docker Compose 정적 구문 해석: PASS
- 검증 후 백업: `task7-alerting-verified`, SHA-256 `e06e1ff86a444ae084a003b256b06aa7fecf9325601985094aab8ad9408d0324`
- 기존 Starlette/httpx deprecation warning 1건과 Streamlit 내부 NumPy timedelta warning 1건 유지
- 실제 Grafana 컨테이너 프로비저닝과 알림 전송은 기존 사용자 요청에 따라 추후 검증

자동 테스트에서 다음을 확인했다.

- 인증되지 않은 Grafana 웹훅은 401로 거부된다.
- 동일 firing 재전송은 duplicate로 처리된다.
- firing 후 열린 결함은 1건, resolved 후 0건이다.
- annotation의 민감한 문자열은 JSONL 이벤트에 저장되지 않는다.
- 규칙 8개의 UID·Prometheus datasource·runbook·내부 contact point·notification policy가 일관된다.
- 외부 Slack/Jira contact point가 프로비저닝되지 않았다.

## 실행·확인 방법

```powershell
$env:QA_OBSERVER_GRAFANA_WEBHOOK_TOKEN = "운영용-임의-긴-토큰"
docker compose up -d --build qa-observer prometheus grafana dashboard
docker compose ps
```

1. Grafana `http://localhost:3000`의 Alerting에서 `AI QA Monitoring` 규칙 8개와 `qa-observer-local` contact point를 확인한다.
2. qa-observer `http://127.0.0.1:8010/metrics`에서 `qa_observer_grafana_webhook_requests_total`을 확인한다.
3. Streamlit `http://localhost:8501`의 `종합 현황 > AI QA 종합 현황`에서 `열린 결함`과 권장 조치를 확인한다.
4. 세부 대응은 `docs/runbooks/qa_dashboard_alerts.md`를 따른다.

## 주의 사항

- 파일 프로비저닝된 Grafana 자원은 UI에서 수정하지 말고 파일 수정 후 재시작 또는 reload한다.
- notification policy는 트리 전체를 덮어쓴다. 기존 정책이 있는 Grafana에 적용하기 전에 반드시 백업·병합 검토가 필요하다.
- 예제 기본 토큰은 로컬 개발용이다. 공유·운영 환경에서는 반드시 환경변수로 교체하고 로그나 문서에 토큰 값을 남기지 않는다.
- 비용 알림은 가격이 적용된 비용 집계가 있을 때만 평가된다. `QA_OBSERVER_USD_KRW`가 없으면 가격 적용률을 먼저 확인한다.

## 사용자 확인 항목

- [x] 구현 1: 알림 규칙 8개와 임계값 승인
- [x] 구현 2: 내부 webhook·group/repeat 정책 승인
- [x] 구현 3: firing/resolved 결함 수명주기와 원문 미저장 승인
- [x] 구현 4: 열린 결함 KPI·권장 조치 승인
- [x] 구현 5: 외부 Slack/Jira 비활성 및 런북 승인

## 추후 체크

- [ ] Docker Desktop 실행 후 Grafana 파일 프로비저닝 성공 여부 확인
- [ ] 실제 test alert firing → qa-observer accepted → 열린 결함 1건 확인
- [ ] 실제 resolved 알림 → 열린 결함 0건 확인
- [ ] 기존 Grafana notification policy가 있는 환경은 적용 전 export·백업
- [ ] 외부 채널이 필요하면 수신 대상·운영 시간·자격 증명 보관 정책을 별도 승인
