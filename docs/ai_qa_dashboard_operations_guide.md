# AI QA 종합 상황판 운영 가이드

## 운영 범위

이 가이드는 기존 운영 대시보드를 유지하면서 별도 `종합 현황 > AI QA 종합 현황` 화면과 다음 흐름을 실행·확인·복구하는 절차를 제공한다.

```text
API·LLM·RAG·테스트·안전성 계측
  → qa-observer 이벤트 계약 검증
  → JSONL 상세 이벤트 + 일별 CSV 집계
  → summary·timeseries·events API + Prometheus
  → Streamlit 종합 현황 + Grafana Alerting
  → firing/resolved 결함 이벤트
```

MVP는 SQLite를 사용하지 않는다. `data/qa_observer`의 JSONL·CSV·checkpoint가 런타임 저장소이며 SQLite 계약은 향후 확장용이다.

## 1. 사전 준비

프로젝트 루트는 `C:\qaeduc\ai_quality_final_project_2026`이다. 다음 값을 운영 비밀 저장소나 로컬 `.env`에 준비한다.

| 변수 | 필수 조건 |
|---|---|
| `QA_OBSERVER_GRAFANA_WEBHOOK_TOKEN` | Grafana와 qa-observer에 동일한 긴 무작위 값 설정 |
| `QA_OBSERVER_USD_KRW` | 실제 KRW 비용 집계가 필요할 때 명시적 환율 설정 |
| `QA_OBSERVER_HMAC_KEY` | 원문 없는 안정적 HMAC 지문이 필요할 때 설정 |
| `QA_OBSERVER_DAILY_BUDGET_KRW` | 기본값 50,000원, 변경 시 알림 규칙도 함께 검토 |

토큰·API 키·HMAC 키는 문서, 로그, Grafana annotation, Prometheus label에 기록하지 않는다.

## 2. 변경 전 정적 검증

빠른 인수 검증:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\validate_dashboard.ps1
```

전체 회귀 검증:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\validate_dashboard.ps1 -Full
```

검증기는 Python compileall, Docker Compose 정적 구문, 시나리오·Grafana·Streamlit 테스트를 순서대로 실행한다. 이 명령은 컨테이너를 시작하지 않고 런타임 데이터도 생성하지 않는다.

### Windows 로컬 Streamlit 실행

시스템 Python의 구형 Streamlit이 선택되지 않도록 반드시 프로젝트 가상환경 실행 스크립트를 사용한다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\start_dashboard.ps1 -Restart
```

이 스크립트는 `.venv\Scripts\python.exe`와 Streamlit 1.59 이상을 검증하고, 8501의 기존 Streamlit 프로세스만 안전하게 교체한다. 다른 프로그램이 8501을 사용 중이면 해당 프로세스를 종료하지 않고 오류로 중단한다.

## 3. Docker 실행

```powershell
$env:QA_OBSERVER_GRAFANA_WEBHOOK_TOKEN = "운영용-임의-긴-토큰"
$env:QA_OBSERVER_USD_KRW = "운영 승인 환율"
docker compose up -d --build qa-observer api prometheus grafana dashboard
docker compose ps
```

확인 주소:

| 구성 | 주소 | 정상 기준 |
|---|---|---|
| qa-observer | `http://127.0.0.1:8010/health` | `status=healthy`, storage writable, scheduler running |
| qa-observer metrics | `http://127.0.0.1:8010/metrics` | `qa_observer_up 1` |
| API | `http://127.0.0.1:8000/health` | HTTP 200 |
| Prometheus | `http://localhost:9090/targets` | API와 qa-observer target UP |
| Grafana | `http://localhost:3000` | `AI QA Monitoring` 규칙 8개 확인 |
| Streamlit | `http://localhost:8501` | 기존 기본 화면과 신규 종합 현황 모두 진입 가능 |

실제 Docker 기동 확인은 현재 보류된 인수 항목이다. Docker Desktop 실행이 가능한 시점에 위 순서로 수행하고 결과를 Task 8 보고서에 추가한다.

## 4. 화면 확인

1. Streamlit에서 상단 `종합 현황`, 좌측 `AI QA 종합 현황`을 선택한다.
2. 기간·환경·서비스·공급자·모델을 선택하고 `조회`를 누른다.
3. 전체 품질점수, 테스트 통과율, p95, 오류율, 안전성 위반, API 비용, RAG, 토큰, 예산, 열린 결함을 확인한다.
4. 데이터가 없으면 0이나 정상 대신 `데이터 없음`이 표시되는지 확인한다.
5. qa-observer 중단 시 연결 경고가 표시되고 기존 대시보드는 계속 사용할 수 있는지 확인한다.

## 5. 시나리오별 예상 결과

| 시나리오 | 입력 조건 | 화면 상태 | Grafana 규칙 | 권장 조치 |
|---|---|---|---|---|
| 정상 | 품질 100, 테스트 100%, 오류 0%, RAG no-result 0%, 예산 20% | 정상 | 없음 | 즉시 조치 없음 |
| API 오류 | 5xx 또는 timeout으로 오류율 2% 초과 | 위험 | `qa_api_error_rate` | API 로그·의존 서비스 확인 |
| 지연 | p95 5초 초과 | 주의, 8초 초과 시 위험 | `qa_api_p95_latency` | RAG·LLM 단계별 지연 비교 |
| 비용 초과 | 일 비용 50,000원 초과 | 위험 | `qa_llm_budget_critical` | 반복 호출·모델·캐시 확인 |
| RAG 실패 | no-result 5% 초과 | 주의 | `qa_rag_no_result` | 검색어·인덱스 최신성 확인 |
| 안전성 위반 | 위반 1건 이상 | 위험 | `qa_safety_violation` | 케이스 재현·정책 검토 |

Grafana firing 수신 후 `열린 결함`은 1건 증가하고 동일 fingerprint의 resolved 수신 후 0건으로 돌아와야 한다. 알림 재전송은 중복 집계되지 않아야 한다.

## 6. 일상 운영 점검

매일 확인:

- qa-observer health와 마지막 수집 시각
- Prometheus target 상태
- 안전성 위반과 열린 결함
- 오류율·p95·테스트 통과율
- 가격 적용률과 일 예산 사용률
- `logs/qa_observer/qa-observer.log`의 collector error

주간 확인:

- RAG no-result 추이와 인덱스 최신성
- 품질 지표별 하락 추이
- JSONL·CSV 보존 정책과 디스크 사용량
- Grafana 경고 임계값의 과다·누락 알림 여부
- 백업 ZIP의 checksum과 복구 절차 유효성

## 7. 장애 대응

### qa-observer가 degraded일 때

1. `/health`의 storage writable과 scheduler error type을 확인한다.
2. `docker compose logs --tail 100 qa-observer`를 확인한다.
3. `data/qa_observer`와 `logs/qa_observer` 쓰기 권한을 확인한다.
4. API·테스트가 outbox에 이벤트를 적재 중인지 확인한다.
5. 재기동 후 outbox가 자동 회수되는지 확인한다.

### Grafana 알림이 결함으로 반영되지 않을 때

1. `qa_observer_grafana_webhook_requests_total`의 accepted·unauthorized·rejected를 확인한다.
2. Grafana와 qa-observer의 webhook token이 같은지 값 자체를 출력하지 않고 설정 유무만 확인한다.
3. contact point URL이 `http://qa-observer:8010/v1/alerts/grafana`인지 확인한다.
4. `docs/runbooks/qa_dashboard_alerts.md`의 알림별 절차를 수행한다.

### 비용이 표시되지 않을 때

1. 공급자 응답의 실제 usage가 수집됐는지 확인한다.
2. 가격 snapshot의 모델명이 실제 모델과 일치하는지 확인한다.
3. `QA_OBSERVER_USD_KRW`가 호출 시점에 설정됐는지 확인한다.
4. 가격 적용률이 0이면 비용을 임의로 0원으로 해석하지 않는다.

## 8. 백업과 복구

변경 전 백업:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\create_project_backup.ps1 -Label "before-dashboard-change"
```

복구 시 프로젝트 루트에 바로 압축 해제하지 않는다. 임시 폴더에 해제하고 `backup-manifest.json`과 SHA-256을 확인한 뒤 필요한 소스·설정 파일만 복원한다. 상세 절차는 `docs/backup_restore_guide.md`를 따른다.

백업에는 `.env`, 런타임 `data`, `logs`, `reports`가 포함되지 않는다. 운영 데이터와 비밀값은 별도 정책으로 백업해야 한다.

## 9. 종료

```powershell
docker compose down
```

volume까지 삭제하는 명령은 Prometheus·Grafana 이력을 제거하므로 일반 종료에 사용하지 않는다.

## 10. 변경 관리

- Grafana 파일 프로비저닝 자원은 UI에서 수정하지 않는다.
- notification policy 파일은 정책 트리 전체를 덮어쓰므로 기존 정책을 먼저 export한다.
- 일 예산, 상태 임계값, 보존 기간 변경은 KPI 정의서·알림 규칙·테스트·문서를 함께 수정한다.
- 외부 Slack·Jira 자동 연동은 수신 대상, 운영 시간, 자격 증명 보관 정책을 별도로 승인한 뒤 활성화한다.
- 기존 운영 대시보드의 숨김·삭제 여부는 신규 화면 최종 인수 후 별도로 결정한다.
