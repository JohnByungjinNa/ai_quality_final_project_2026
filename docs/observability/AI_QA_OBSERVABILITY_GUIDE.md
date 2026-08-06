# AI QA 관측성 센터 운영 가이드

## 1. 적용 범위

기존 업무 메뉴와 화면은 수정하지 않고 최상위 `관측성` 메뉴를 추가했다. 이 메뉴는 다음 네 화면으로 분리된다.

| 화면 | 목적 |
|---|---|
| SLO·Error Budget | API 가용성, 5초 이내 응답, 테스트 통과율, 품질 PASS율과 잔여 오류 예산 확인 |
| Agent Pipeline | 기존 A2A 감사 JSONL에서 파생한 Agent 호출 수, 실패율, p95 지연 확인 |
| Drift·FinOps | 기존 품질 평가 및 LLM 비용 이벤트를 이용한 품질 추이와 품질 PASS당 비용 확인 |
| 관측 인프라 | Blackbox 시연 준비 상태와 선택형 Tempo 확장 상태 확인 |

기존 JSONL과 QA 이벤트가 원본이며 Prometheus에는 집계 지표만 적재한다. `run_id`, `trace_id`, 프롬프트, 응답, 개인정보는 Prometheus label에 넣지 않는다.

## 2. 구성

```text
A2A 감사 JSONL ─┐
QA·비용·AWS 이벤트 ─ qa-observer /metrics ─ Prometheus Recording Rules
API /metrics ───┘                         ├─ Grafana 대시보드 3개
Blackbox Exporter ─ probe_success ────────└─ Streamlit 관측성 메뉴

A2A Agent ─ OTLP(선택) ─ Tempo ─ Grafana Explore
```

AWS 증적은 두 번째 배포 항목이다. 실제 `업로드 + 원격 SHA-256 검증` 액션이 끝날 때 `evidence.upload.completed` 이벤트를 발생시키며 업로드, 검증, 파일 수, 바이트 수, 지연, 오류 유형만 저장한다.

## 3. 실행

Docker Desktop을 먼저 실행한 뒤 프로젝트 루트에서 다음 명령을 사용한다.

```powershell
docker compose up -d --build qa-observer api prometheus blackbox-exporter tempo grafana dashboard
docker compose ps
```

접속 주소:

- Streamlit 관측성 메뉴: `http://localhost:8501`
- Grafana: `http://localhost:3000`
- Prometheus Rules/Targets: `http://localhost:9090/rules`, `http://localhost:9090/targets`
- Tempo: `http://localhost:3200`
- Blackbox Exporter: `http://localhost:9115`

## 4. Grafana 대시보드

| 대시보드 | UID | 주요 내용 |
|---|---|---|
| AI QA Executive & SLO | `ai-qa-slo` | 핵심 SLI, SLO, Error Budget, Blackbox 준비 상태 |
| Agent Pipeline Drilldown | `ai-qa-agent-pipeline` | A2A 호출, 실패율, 구간별 p95, 최근 성공 시각 |
| Audit, Drift & FinOps | `ai-qa-audit-finops` | 품질 Drift, LLM 비용, PASS당 비용, AWS 증적 업로드·검증 |

대시보드는 Grafana provisioning으로 자동 생성되므로 UI에서 수동 import할 필요가 없다.

## 5. 시연 전 점검

1. `http://localhost:9090/targets`에서 `ai-quality-api`, `qa-observer`, `blackbox-http`가 UP인지 확인한다.
2. Streamlit `관측성 > 관측 인프라`에서 API, qa-observer, Dashboard, Grafana, Prometheus가 모두 정상인지 확인한다.
3. A2A Pipeline을 한 번 실행해 `voc_agent_rpc_calls_total`과 `voc_agent_rpc_duration_seconds`가 생성되는지 확인한다.
4. 품질 평가를 한 번 실행해 SLO·Drift 화면의 값을 채운다.
5. 두 번째 배포에서 AWS 증적 업로드와 원격 해시 검증을 수행한 뒤 `Audit, Drift & FinOps` 대시보드에서 이벤트를 확인한다.

값이 없는 항목은 0으로 위장하지 않고 `데이터 없음` 또는 `대기`로 표시한다.

## 6. Tempo 고급 확장

Tempo 서버와 Grafana 데이터소스는 미리 프로비저닝되지만 Agent 추적 전송은 기본 비활성화다. A2A 런타임 환경에서 다음 값만 활성화한다.

```dotenv
A2A_TEMPO_ENABLED=true
OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:4318
OTEL_SERVICE_NAME=voc-a2a-agent
```

전송 실패는 업무 파이프라인을 중단하지 않는다. 운영 적용 전에는 보존 기간, 샘플링, 민감 속성 차단, 저장 용량을 별도로 승인한다.

## 7. 철회와 영향 범위

관측성 메뉴 분기, 수집기, Docker 서비스, provisioning 파일이 독립되어 있어 철회할 때 기존 메뉴 코드를 되돌릴 필요가 없다. `관측성` 메뉴 분기와 Docker의 Prometheus/Blackbox/Tempo/Grafana 관련 설정만 제거하면 기존 업무 흐름은 유지된다.
