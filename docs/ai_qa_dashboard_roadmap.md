# AI QA 종합 상황판 구축 로드맵

## 목표

`ai_quality_final_project_2026` 프로젝트에 품질, 테스트, 성능, LLM 비용, RAG 품질, 안전성, 서비스 상태, 결함과 알림을 한 화면에서 확인할 수 있는 종합 상황판을 구축한다.

이 문서는 다른 작업이 중간에 수행되더라도 대시보드 구축의 현재 위치와 다음 할 일을 잃지 않기 위한 기준 문서다.

## 진행 원칙

- 한 번에 하나의 큰 Task만 진행한다.
- 각 Task는 설계 확인, 구현, 검증, 사용자 확인 순서로 닫는다.
- Streamlit은 원천 데이터를 직접 수집하지 않고 집계 API를 조회한다.
- Prometheus에는 낮은 카디널리티의 시계열만 저장한다.
- 질문, 응답, 프롬프트, 사용자 ID, `run_id`, `case_id`, 문서 ID는 Prometheus label로 저장하지 않는다.
- LLM 토큰은 문자열 길이 추정이 아니라 공급자 응답의 실제 usage를 우선 저장한다.
- MVP 상세 이벤트는 JSONL에 저장하고, 데이터량 증가 시 SQLite 또는 PostgreSQL 전환을 별도 승인한다.
- 진행 상태가 바뀔 때 이 문서의 상태, 완료 증거, 다음 작업을 갱신한다.
- 대규모 구성 변경은 변경 직전과 검증 완료 후에 프로젝트 소스·설정 백업을 생성한다.
- 백업은 프로젝트 밖 `C:\qaeduc\_backups\ai_quality_final_project_2026`에 저장하고 비밀값·가상환경·생성 데이터는 제외한다.

## 공통 백업 정책

- 실행 명령: `.\tools\create_project_backup.ps1 -Label "변경단계"`
- 적용 시점: 운영 구성, DB schema, API 계약, 5개 이상 파일, 큰 Task 시작·완료 시점
- 산출물: ZIP, ZIP SHA-256 파일, ZIP 내부 `backup-manifest.json`
- 복구 절차: `docs/backup_restore_guide.md`
- 작은 문서 수정이나 단일 파일 수정에는 불필요한 백업을 반복하지 않는다.

## 전체 Task 현황

| Task | 내용 | 상태 | 완료 증거 |
|---|---|---|---|
| 1 | KPI·SLO·대시보드 범위와 완료 기준 확정 | 완료 | 승인된 KPI 정의서, 일 예산 50,000 KRW, 화면·상태 우선순위 |
| 2 | 이벤트 스키마·저장소·보안/보존 정책 설계 | 완료 | 승인된 이벤트 계약, JSONL·CSV 저장, 보안·보존 정책 |
| 3 | `qa-observer` 자동 수집 서비스와 스케줄러 구축 | 완료 | 승인된 health, metrics, 자동 수집 로그와 92 PASS |
| 4 | LLM·RAG·테스트·안전성·성능 계측 연결 | 완료 | 사용자 승인, 전체 97 PASS, 원문 차단·outbox 회수 검증 |
| 5 | Prometheus·파일 이벤트 저장소·집계 API 연계 | 완료 | 사용자 승인, 필터·KPI·비용·Prometheus, 전체 99 PASS |
| 6 | Streamlit 종합 현황 대시보드 구현 | 완료 | 사용자 승인, 별도 화면·필터·KPI·차트·표, 전체 104 PASS |
| 7 | Grafana Alerting·알림·결함 조치 연계 | 완료 | 사용자 승인, 규칙 8개·내부 webhook·해제·결함 이벤트, 전체 108 PASS |
| 8 | 정상·오류·지연·비용·안전성 시나리오 검증 및 운영 문서화 | 완료 | 사용자 승인, 6개 E2E 시나리오·운영 가이드, 전체 114 PASS |

## Task별 역할과 완료 기준

### Task 1. KPI·SLO·범위 확정

Codex가 할 일:

- 현재 코드와 데이터 원천을 KPI 후보에 매핑한다.
- KPI 공식, 단위, 기간, 정상·주의·위험 기준을 정의한다.
- 참고 이미지의 각 카드와 차트를 실제 데이터 원천에 연결한다.
- MVP 범위와 후속 확장 범위를 분리한다.

사용자가 할 일:

- 운영 환경 범위와 주요 서비스·모델을 확인한다.
- 비용 예산과 알림 임계값을 승인하거나 수정한다.
- 첫 화면에 반드시 필요한 KPI와 제외할 KPI를 확인한다.

완료 기준:

- 모든 상단 KPI에 공식, 원천, 갱신 주기, 상태 기준이 있다.
- 데이터가 없을 때 표시 방식이 정해져 있다.
- 사용자 승인을 받은 KPI 정의서가 있다.

### Task 2. 이벤트 스키마·저장 정책

Codex가 할 일:

- LLM 호출, RAG 검색, 테스트 실행, 안전성 위반, 결함, 수집 작업 이벤트를 설계한다.
- 저카디널리티 Prometheus 지표와 상세 DB 필드를 분리한다.
- 중복 방지 키, 시간대, 보존 기간, 마스킹 규칙을 정의한다.

사용자가 할 일:

- SQLite로 시작할지 PostgreSQL을 바로 사용할지 결정한다.
- 질문·응답 원문 저장 허용 여부와 보존 기간을 승인한다.

완료 기준:

- 스키마와 마이그레이션 전략이 정해져 있다.
- 민감정보와 보존 정책이 명확하다.

### Task 3. 자동 수집 서비스

Codex가 할 일:

- `qa-observer` 서비스, health, metrics, 이벤트 수신 API를 구현한다.
- 보고서 동기화, 상태 점검, 집계 갱신 스케줄러를 구현한다.
- Docker Compose에 서비스를 연결한다.

사용자가 할 일:

- 서비스 실행 방식과 자동 시작 여부를 확인한다.
- 운영에 사용할 환경변수와 자격 증명을 준비한다.

완료 기준:

- 서비스가 자동 시작되고 재시작 후에도 수집을 재개한다.
- 수집 성공·실패·마지막 성공 시각을 확인할 수 있다.

### Task 4. 계측 연결

Codex가 할 일:

- OpenAI·Anthropic 실제 usage, 모델, 비용, 지연시간을 기록한다.
- RAG hit, no-result, Top-K 관련성, 검색시간을 기록한다.
- 테스트·안전성·단계별 latency 이벤트를 기록한다.

사용자가 할 일:

- 실제 API 호출이 필요한 검증 실행을 승인한다.
- 테스트용 비용 한도와 안전한 샘플 데이터를 확인한다.

완료 기준:

- 각 영역에서 실제 이벤트 한 건 이상이 수집된다.
- 실패 호출과 재시도도 별도로 구분된다.

### Task 5. 저장·집계 API

Codex가 할 일:

- Prometheus scrape와 상세 이벤트 DB를 연결한다.
- 기간·모델·서비스 필터를 지원하는 집계 API를 구현한다.
- 반복 계산은 recording rule 또는 사전 집계로 분리한다.

사용자가 할 일:

- 기본 조회 기간과 데이터 보존 기간을 확인한다.

완료 기준:

- KPI, 추이, 결함 목록이 동일한 필터 조건으로 조회된다.
- 데이터 신선도와 누락 상태가 함께 반환된다.

### Task 6. Streamlit 상황판

Codex가 할 일:

- 종합 현황 메뉴와 KPI·차트·운영 상태·결함·추천 조치를 구현한다.
- 캐시, fragment, 부분 갱신으로 전체 rerun 비용을 제한한다.
- 빈 데이터, 수집 지연, 오류 상태 UI를 구현한다.

사용자가 할 일:

- 화면 배치, 용어, 색상, 우선순위를 검토한다.
- 참고 이미지와 비교해 수정 요청을 확정한다.

완료 기준:

- 기간·모델·서비스 필터가 모든 패널에 동일하게 적용된다.
- 화면 진입과 갱신이 안정적이며 수집 장애가 명확히 표시된다.

### Task 7. 알림·조치 연계

Codex가 할 일:

- Grafana Alerting 규칙과 contact point 설정을 코드로 관리한다.
- 중복 알림 억제, 해제 알림, runbook 링크를 구성한다.
- 필요 시 Jira 결함 자동 등록을 연결한다.

사용자가 할 일:

- Slack, 이메일, Webhook, Jira 중 실제 알림 채널을 선택한다.
- 수신 대상과 운영 시간을 승인한다.

완료 기준:

- 경고 발생, 알림 전송, 정상 복구 알림이 검증된다.

### Task 8. 종합 검증·문서화

Codex가 할 일:

- 정상, API 오류, 지연, 비용 초과, RAG 실패, 안전성 위반 시나리오를 자동화한다.
- 데이터 원천부터 화면·알림까지 E2E 검증한다.
- 실행, 장애 대응, 백업·복구 문서를 작성한다.

사용자가 할 일:

- 최종 화면과 알림을 인수 확인한다.
- 운영 기준과 남은 후속 과제를 승인한다.

완료 기준:

- 모든 필수 시나리오가 재현되고 예상 상태와 알림이 일치한다.
- 운영자가 문서만으로 실행·확인·복구할 수 있다.

## Task 1 기본 제안안

- 기본 기간: 최근 7일
- 필터: 기간, 환경, 서비스, 공급자, 모델
- 상단 KPI: 전체 품질점수, 테스트 통과율, p95 응답시간, 오류율, 안전성 위반, API 비용
- 품질 지표: 정확성, 근거성, 관련성, 신뢰성, 안전성, 유용성
- 기본 경고: 통과율 95% 미만, 오류율 2% 초과, p95 5초 초과, 안전성 위반 1건 이상
- RAG 경고: No Result 5% 초과, Top-K 적중률 90% 미만
- 비용 경고: 일 예산 80% 주의, 100% 위험
- 데이터 없음은 0이 아니라 `데이터 없음`으로 표시
- MVP 저장소: 일자별 JSONL 이벤트, 일별 집계 CSV, checkpoint JSON
- 향후 저장소: 데이터량 증가 시 SQLite를 별도 승인 후 적용
- 일 API 비용 예산: 50,000 KRW
- 화면 전환 원칙: 기존 대시보드는 유지하고 새 종합 상황판을 별도 화면으로 추가

## 현재 체크포인트

- 현재 Task: 전체 Task 1~8 완료
- 현재 단계: AI QA 종합 상황판 구축·자동 검증·운영 문서화 완료
- 진행 상태: `COMPLETE`
- Task 1 완료 문서: `docs/ai_qa_dashboard_kpi_spec.md`, `docs/ai_qa_dashboard_task1_review.md`
- Task 2 시작 전 백업: `task2-before-event-schema`
- Task 2 완료 문서: `docs/ai_qa_dashboard_event_schema.md`
- 계약 파일: `contracts/qa_observer/event-envelope-v1.schema.json`, `contracts/qa_observer/sqlite-v1.sql`
- 검증 상태: 계약 테스트 2 PASS, 전체 테스트 89 PASS, 기존 dashboard 41개 파일 변경 없음
- Task 2 검증 후 백업: `task2-contract-draft-verified`
- Task 3 완료 문서: `docs/qa_observer_task3_report.md`
- Task 3 검증: 로컬 health·metrics·자동 수집 PASS, 계약/서비스 5 PASS, 전체 92 PASS
- 기존 화면 보존: `dashboard/` 41개 파일 변경 없음
- Docker 상태: Compose 구문 PASS, Docker Desktop engine 미실행으로 container health 미검증
- Task 3 검증 후 백업: `task3-qa-observer-verified`
- Task 4 시작 전 백업: `task4-before-instrumentation`
- Task 4 완료 문서: `docs/qa_observer_task4_report.md`
- Task 4 검증 상태: 계측 전용 5 PASS, 전체 97 PASS, Compose 구문 PASS
- Task 5 시작 전 백업: `task5-before-aggregation-api`
- Task 5 완료 문서: `docs/qa_observer_task5_report.md`
- Task 5 검증 상태: 관련 10 PASS, 전체 99 PASS, Compose 구문 PASS
- Task 6 시작 전 백업: `task6-before-overview-dashboard`
- Task 6 완료 문서: `docs/ai_qa_dashboard_task6_report.md`
- Task 6 검증 상태: 신규 화면 5 PASS, 전체 104 PASS, 전체 앱 메뉴 전환 예외 0건
- Task 7 시작 전 백업: `task7-before-alerting`
- Task 7 완료 문서: `docs/qa_observer_task7_report.md`
- Task 7 검증 상태: 관련 13 PASS, 전체 108 PASS, compileall·Compose 구문 PASS
- Task 7 검증 후 백업: `task7-alerting-verified`
- Task 8 시작 전 백업: `task8-before-final-validation`
- Task 8 완료 문서: `docs/ai_qa_dashboard_task8_report.md`
- Task 8 운영 문서: `docs/ai_qa_dashboard_operations_guide.md`
- Task 8 검증 상태: 6개 E2E 시나리오 PASS, 관련 14 PASS, 전체 114 PASS, compileall·Compose 구문 PASS
- Task 8 검증 후 백업: `task8-final-validation-verified`
- 다음 Codex 작업: 후속 요청이 있을 때 Docker 실구동 인수, 외부 알림 채널 또는 저장소 확장을 별도 Task로 진행
- 다음 사용자 작업: 필요 시 추후 체크 항목 중 수행할 작업을 선택

## 최종 완료 상태

- Task 1~8 사용자 승인 완료
- 신규 `종합 현황 > AI QA 종합 현황` 화면 구현 완료
- 기존 운영 대시보드 유지
- JSONL·CSV 기반 qa-observer 수집·집계와 Prometheus 연계 완료
- Grafana 규칙 8개와 내부 webhook·결함 수명주기 구현 완료
- 정상·API 오류·지연·비용·RAG·안전성 6개 E2E 시나리오 완료
- 전체 회귀 테스트 114 PASS
- 최종 운영 가이드와 검증 스크립트 제공 완료
- Docker 실제 기동과 외부 Slack·Jira 연동은 승인된 완료 범위 밖의 후속 항목으로 유지

## 추후 체크 및 작업 사항

- [ ] Docker Desktop engine 실행 후 `docker compose up -d --build qa-observer` 수행
- [ ] `docker compose ps qa-observer`에서 healthy 확인
- [ ] `http://127.0.0.1:8010/health`와 `/metrics` container 응답 확인
- [ ] `docker compose logs --tail 100 qa-observer`에서 자동 수집 오류 없음 확인
- [ ] 새 종합 상황판 검증 후 기존 대시보드 숨김·삭제 여부 별도 결정
- [ ] Grafana 컨테이너 실행 후 규칙·contact point·notification policy 파일 프로비저닝 확인
- [ ] 실제 firing·resolved 알림으로 열린 결함 1건→0건 수명주기 확인

## 결정 로그

- 2026-07-14: 종합 상황판 구축을 8개 상위 Task로 분리했다.
- 2026-07-14: 한 번에 하나의 Task만 진행하고 사용자 확인 후 다음 Task로 이동하기로 했다.
- 2026-07-14: 진행 상태는 이 문서와 대화의 지속 목표에서 함께 관리한다.
- 2026-07-14: Task 1 산출물 준비 후 사용자 승인 입력을 기다리며 다음 Task 진행을 중지했다.
- 2026-07-14: 대규모 구성 변경 전·후에 소스·설정 ZIP과 SHA-256 manifest를 생성하는 공통 백업 정책을 추가했다.
- 2026-07-14: 최초 정책 백업 `task1-backup-policy`를 프로젝트 외부에 생성하고 checksum, manifest 141개 파일, 비밀값 제외를 검증했다.
- 2026-07-14: Task 1 권장안, 일 예산 50,000 KRW, 화면 배치와 전체 상태 우선순위를 승인받았다.
- 2026-07-14: 기존 대시보드를 유지하고 새 종합 상황판을 별도 화면으로 추가하기로 했다.
- 2026-07-14: Task 2 시작 전 `task2-before-event-schema` 백업을 생성했다.
- 2026-07-14: v1 이벤트 8종, SQLite table 15개, 보안·보존 정책 초안을 작성하고 전체 89개 테스트를 통과했다.
- 2026-07-14: Task 2 설계 중 기존 `dashboard/` 41개 파일이 변경되지 않았음을 시작 전 백업과 대조했다.
- 2026-07-14: 검증된 Task 2 초안을 `task2-contract-draft-verified` 백업으로 보존했다.
- 2026-07-14: Task 2 권장안과 보존 기간을 승인받고, 사용자 의견에 따라 MVP 저장소를 SQLite에서 JSONL·CSV·local log로 변경했다.
- 2026-07-14: SQLite DDL은 삭제하지 않고 향후 확장용 migration 계약으로 전환했다.
- 2026-07-14: JSONL·CSV 기반 qa-observer, test report collector, scheduler, health·metrics API를 구현했다.
- 2026-07-14: 기존 실행 12건 자동 수집, JSONL 13건, CSV 15행, 전체 92 PASS를 확인했다.
- 2026-07-14: Docker Compose 구문은 통과했으나 Docker Desktop engine 미실행으로 container health 검증은 보류했다.
- 2026-07-14: 검증된 Task 3 구현을 `task3-qa-observer-verified` 백업으로 보존했다.
- 2026-07-14: Task 3 구현 1~5를 승인받고 완료 처리했다.
- 2026-07-14: Docker 실제 기동 검증은 추후 체크 항목으로 이관했다.
- 2026-07-14: API·LLM usage·RAG·품질·안전성 계측과 장애 시 JSONL outbox fallback을 구현했다.
- 2026-07-14: 질문·응답 원문 차단, HMAC 지문, outbox 자동 회수와 전체 97 PASS를 확인하고 Task 4를 승인 대기로 전환했다.
- 2026-07-14: Task 4 구현 1~5를 추가 의견 없이 승인받고 완료 처리했다.
- 2026-07-14: MVP 저장소 원칙에 따라 Task 5의 상세 저장소 표현을 DB에서 JSONL·CSV 파일 저장소로 명확히 했다.
- 2026-07-14: 기간·환경·서비스·공급자·모델 필터 집계, KPI summary, 시계열, 최근 이벤트 API를 구현했다.
- 2026-07-14: 공식 OpenAI 가격 스냅샷과 명시적 환율 기반 비용 계산, qa-observer Prometheus scrape를 연결하고 전체 99 PASS를 확인했다.
- 2026-07-14: Task 5 구현 1~5를 추가 의견 없이 승인받고 완료 처리했다.
- 2026-07-14: 기존 대시보드를 유지한 채 신규 종합 현황 화면을 별도 상단 메뉴로 추가하는 Task 6에 착수했다.
- 2026-07-14: qa-observer 집계 API만 조회하는 신규 종합 현황 메뉴, KPI·차트·이벤트·추천 조치 화면을 구현했다.
- 2026-07-14: 수집 장애 시 데이터 없음 표시와 기존 화면 무회귀를 AppTest로 검증하고 전체 104 PASS를 확인했다.
- 2026-07-14: Task 6 구현 1~5를 추가 의견 없이 승인받고 완료 처리했다.
- 2026-07-14: 외부 Slack/Jira 자동 전송은 활성화하지 않고 Grafana 로컬 webhook부터 구성하는 Task 7에 착수했다.
- 2026-07-14: Grafana 규칙 8개, 내부 Bearer webhook, notification policy, 결함 firing/resolved 수명주기와 운영 런북을 구현했다.
- 2026-07-14: 인증·중복·원문 미저장·열린 결함 해제를 검증하고 전체 108 PASS 후 Task 7을 승인 대기로 전환했다.
- 2026-07-14: Task 7 구현 1~5를 추가 의견 없이 승인받고 완료 처리했다.
- 2026-07-14: 정상·오류·지연·비용·RAG·안전성 시나리오와 최종 운영 문서를 만드는 Task 8에 착수했다.
- 2026-07-14: 6개 시나리오의 이벤트 수신·집계·화면 상태·Prometheus·Grafana·결함 firing/resolved 흐름을 자동화했다.
- 2026-07-14: RAG no-result 5% 초과를 전체 주의 상태에 반영하고 전체 114 PASS 후 Task 8을 최종 승인 대기로 전환했다.
- 2026-07-14: Task 8 구현 1~5와 최종 운영 기준을 승인받아 전체 Task 1~8을 완료 처리했다.
- 2026-07-14: Docker 실구동, 외부 알림 채널, 기존 화면 정리, SQLite 확장은 별도 승인 후 진행할 후속 작업으로 유지했다.
- 2026-07-14: 참고 이미지의 정보 위계에 맞춰 신규 종합 상황판을 6개 KPI, 품질 추이·테스트 도넛·운영 상태, 품질·응답시간·RAG 차트, 결함·알림·추천 조치 구조로 개선했다.
- 2026-07-14: 종합 상황판 시각화 개선 후 전용 5 PASS와 전체 114 PASS를 확인했으며 기존 운영 대시보드는 그대로 유지했다.
- 2026-07-14: 단일 공급자를 숨은 기본 필터로 자동 적용해 공통 KPI가 제외되는 원인을 확인하고, 공급자·모델을 명시적 필터로 복원하여 기본 `전체` 조회 시 필터를 전달하지 않도록 수정했다.
- 2026-07-14: 테스트 수행 상세의 진청·연청 카드와 선형 SVG 스타일을 종합 상황판에 적용하고 제목 옆 조회 조건, 낮은 차트, 접힌 결함 상세로 세로 길이를 압축했다.
