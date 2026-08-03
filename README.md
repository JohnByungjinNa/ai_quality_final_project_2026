# VOC 멀티 에이전트 품질관리·운영 모니터링 플랫폼

이 문서는 프로젝트 설치부터 VOC 품질진단, 테스트, 증적 확인까지 안내하는 운영 매뉴얼입니다. 앱의 `홈 > VOC 품질진단 > 사용자 가이드`에서도 같은 문서를 조회합니다.

## 1. 프로젝트 목적

이 프로젝트는 프로그램이 실행되는지만 확인하지 않고, 사용자 질문이 실제 VOC를 근거로 정확하고 안전한 정책 개선안으로 만들어지는 전체 과정을 검증합니다.

- Interpreter, Retriever, Summarizer, Evaluator, Critic, Improver의 6개 Agent 처리 흐름을 추적합니다.
- 최종 답변뿐 아니라 Agent 간 데이터 전달, Trace, 장애 응답과 로그를 검증합니다.
- 내부 Evaluator·Critic과 별도로 독립 LLM Judge가 최종 산출물을 100점 Rubric으로 평가합니다.
- 개선안의 VOC 근거, 구체성, 실행 가능성, KPI, 위험을 평가하고 QA·업무 담당자의 순차 승인을 관리합니다.
- 수동·일괄·재시험 Run, 결함, 품질 보고서를 연결해 배포 가능 여부를 판단합니다.
- 미실행, 오류, 미검증 수치를 성공으로 표현하지 않고 증적 상태로 명확히 구분합니다.

현재 품질 정책상 AI 자동 PASS만으로 정식 운영 승인을 내리지 않습니다. 독립 Judge, 개선안 타당성, QA 검토, 업무 승인, 중요 결함 상태를 함께 확인합니다.

## 2. 프로젝트 구조

```text
ai_quality_final_project_2026/
├─ dashboard/
│  ├─ streamlit_app.py              # Streamlit 대시보드 진입점
│  ├─ navigation.py                 # 상단·좌측 메뉴
│  ├─ pages_top/voc_quality_view.py # VOC 품질진단 화면
│  └─ services/                     # Run·Judge·타당성·결함·보고서 서비스
├─ voc_quality_runtime/
│  ├─ agents/                       # 6개 gRPC Agent
│  ├─ scripts/                      # Agent 및 품질진단 실행 스크립트
│  ├─ quality_diagnosis/            # TC, Rubric, 증적 계약, 진단 runner
│  ├─ voc.csv                       # VOC 검색 데이터
│  └─ .env.example                  # 환경변수 예시
├─ qa_observer/                     # 운영 이벤트·집계·Prometheus API
├─ tests/                           # 자동 회귀 테스트
├─ reports/
│  ├─ voc_quality_runs/             # Run·Case·Judge·타당성·보고서 증적
│  └─ voc_quality_defects/          # 결함 원장
├─ docs/voc_quality/                # 단계별 계약·로드맵·운영 문서
├─ tools/start_dashboard.ps1        # 대시보드·qa-observer 통합 실행
├─ requirements.txt                 # 통합 Python 의존성
└─ README.md                        # 이 운영 매뉴얼
```

VOC 런타임은 6101~6106 포트를 사용하며 기존 챗봇 품질평가 기능과 데이터·모듈·증적 폴더를 분리합니다.

## 3. 설치 방법

### 3.1 사전 조건

- Windows PowerShell
- Python 3.12 권장
- 프로젝트 경로에 대한 읽기·쓰기 권한
- 실제 LLM 평가를 수행할 경우 각 공급자의 사용 가능한 API 자격 증명

### 3.2 가상환경과 의존성 설치

프로젝트 루트에서 실행합니다.

```powershell
cd C:\qaeduc\ai_quality_final_project_2026
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r .\requirements.txt
```

설치 확인:

```powershell
.\.venv\Scripts\python.exe --version
.\.venv\Scripts\python.exe -c "import streamlit, grpc, anthropic, openai; print(streamlit.__version__)"
```

현재 검증 환경은 Python 3.12.9, Streamlit 1.59.2입니다.

## 4. 환경변수 설정

### 4.1 초기 파일 생성

```powershell
cd C:\qaeduc\ai_quality_final_project_2026\voc_quality_runtime
.\scripts\agents.cmd init
notepad .env
```

`init`은 `.env`가 없을 때 `.env.example`을 복사합니다. 런타임 `.env`가 없고 프로젝트 루트 `.env`가 있으면 루트 파일을 사용합니다. 우선순위는 `voc_quality_runtime/.env`가 먼저입니다.

필수 변수 이름:

```env
OPENAI_API_KEY=YOUR_OPENAI_API_KEY
ANTHROPIC_API_KEY=YOUR_ANTHROPIC_API_KEY
TAVILY_API_KEY=YOUR_TAVILY_API_KEY
```

모델 변수와 선택적 비용 단가는 [voc_quality_runtime/.env.example](voc_quality_runtime/.env.example)을 참고합니다. 검증된 단가가 없으면 비용 변수를 비워 두며 시스템은 금액을 추정하지 않습니다.

### 4.2 보안 원칙

- `.env`, API 키, token, 고객 개인정보를 Git·README·Notion·보고서에 기록하지 않습니다.
- 키가 노출되면 즉시 폐기하고 새 키를 발급합니다.
- 화면과 증적에는 자격 증명 값이 아니라 설정 여부만 기록합니다.
- VOC 원문과 전체 LLM 응답은 필요한 Run 증적에만 최소 범위로 보존합니다.

## 5. 실행 방법

### 5.1 VOC Agent 시작

```powershell
cd C:\qaeduc\ai_quality_final_project_2026\voc_quality_runtime
.\scripts\agents.cmd start
.\scripts\agents.cmd status
```

정상 상태는 6개 Agent가 모두 `RUNNING`이며 6101~6106 포트가 열려 있습니다.

개별 Agent 관리:

```powershell
.\scripts\agents.cmd restart retriever
.\scripts\agents.cmd status retriever
```

전체 종료:

```powershell
.\scripts\agents.cmd stop
```

### 5.2 Streamlit 대시보드 시작

프로젝트 루트에서 실행합니다.

```powershell
cd C:\qaeduc\ai_quality_final_project_2026
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\start_dashboard.ps1
```

이 스크립트는 qa-observer의 health를 확인해 8010 포트에서 시작하거나 기존 정상 프로세스를 재사용하고, Streamlit을 8501 포트에서 시작합니다.

- 대시보드: `http://127.0.0.1:8501`
- qa-observer health: `http://127.0.0.1:8010/health`

대시보드만 재시작:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\start_dashboard.ps1 -Restart
```

### 5.3 GitHub 환경 등록

다른 사용자가 저장소를 clone하거나 ZIP으로 전달받은 경우, 대시보드의
`GitHub 관리 > 환경 설정`에서 Git 설치 상태, 저장소, 사용자 이름·이메일,
원격 저장소(origin)를 순서대로 점검하고 등록할 수 있습니다.

- 사용자 이름과 이메일은 이 프로젝트의 로컬 Git 설정에만 저장됩니다.
- ZIP으로 받은 폴더는 사용자가 동의한 경우에만 Git 저장소로 초기화됩니다.
- 인증 토큰과 비밀번호는 화면이나 프로젝트 파일에 저장하지 않습니다.
- 자세한 내용은 [GitHub 관리 메뉴 사용 가이드](docs/github_management_guide.md)를 참고합니다.

### 5.4 VOC 품질진단 사용 순서

1. `Agent 관리`에서 6개 Agent 상태를 확인합니다.
2. `수동 TC 수행`에서 대표 Case와 독립 Judge 사용 여부를 선택합니다.
3. `일괄 TC 수행`에서 실행 가능한 Case를 선택하고 Run ID와 진행률을 확인합니다.
4. `수행 이력`에서 manifest, Case 결과, Trace, Judge와 타당성 증적을 조회합니다.
5. `개선안 타당성 검증`에서 AI 평가 후 QA·업무 순차 승인을 진행합니다.
6. `장애·결함 관리`에서 결함 원인·조치·연결 RETEST·종료 이력을 관리합니다.
7. `품질 보고서`에서 실측 수치, 잔여 위험, 배포 판정과 TXT·XML·HTML 증적을 확인합니다.
8. `최종 인수·시연`에서 최종 품질 게이트, 업무 흐름 인수 범위, 잔여 위험과 사용자 승인 대기 여부를 확인합니다.

## 6. 테스트 방법

### 6.1 정의·Rubric·장애·A2A 진단

```powershell
cd C:\qaeduc\ai_quality_final_project_2026\voc_quality_runtime
.\scripts\quality-diagnosis.cmd validation
.\scripts\quality-diagnosis.cmd fault
.\scripts\quality-diagnosis.cmd a2a
.\scripts\quality-diagnosis.cmd all
```

격리 장애시험은 운영 Agent와 실제 API 키를 변경하지 않고 Retriever 종료, 포트 충돌, CSV 누락, 인증 오류, 지연, 빈 검색 결과를 재현합니다.

### 6.2 VOC 기능 회귀

```powershell
cd C:\qaeduc\ai_quality_final_project_2026
.\.venv\Scripts\python.exe -m pytest `
  tests\test_voc_quality_integration.py `
  tests\test_voc_defects.py `
  tests\test_voc_quality_report.py -q
```

### 6.3 전체 회귀

```powershell
cd C:\qaeduc\ai_quality_final_project_2026
.\.venv\Scripts\python.exe -m pytest -q
```

2026-07-16 Step 10 검증 기준은 229 PASS이며, 기존 qa-observer Prometheus 업무 집계 메트릭 문제 6건은 별도 잔여 결함입니다. 이 6건을 성공으로 간주하지 않습니다.

실제 LLM 테스트는 API 호출 시간·비용·429 가능성이 있으므로 대표 Case부터 수행하고, 대량 실행 전 자격 증명과 사용 한도를 확인합니다.

## 7. 결과물 위치

| 결과물 | 위치 | 설명 |
|---|---|---|
| VOC Run 원장 | `reports/voc_quality_runs/{RUN_ID}/` | manifest, summary, Case 증적, 결함 역참조 |
| Case 증적 | `reports/voc_quality_runs/{RUN_ID}/cases/{CASE_ID}/` | Pipeline, Trace, rule, Judge, 타당성 결과 |
| 품질 보고서 | `reports/voc_quality_runs/{RUN_ID}/evidence/` | TXT, JUnit XML, HTML, report model·manifest |
| 결함 원장 | `reports/voc_quality_defects/` | 결함 상세와 중앙 index |
| 기존 진단 Report | `voc_quality_runtime/quality_diagnosis/Reports/` | Summary, Validation, Fault, A2A, VOC |
| Agent 로그 | `voc_quality_runtime/.runtime/logs/` | Agent별 표준 출력·오류 로그 |
| A2A 감사 로그 | `voc_quality_runtime/.runtime/audit/` | Trace 이벤트 JSONL |
| 대시보드 로그 | `logs/local_services/` | Streamlit·qa-observer 실행 로그 |
| 단계별 문서 | `docs/voc_quality/` | 품질 계약, 로드맵, Step별 검증 문서 |

Run 삭제는 `수행 이력`에서 완료 Run을 명시적으로 선택했을 때만 가능하며 Run 폴더와 중앙 index를 함께 갱신합니다.

## Agent와 평가자 역할

| 구성 | 역할 |
|---|---|
| Interpreter | 질문 의도·키워드·검색조건 해석 |
| Retriever | 관련 VOC 검색과 출처·원문 의미 보존 |
| Summarizer | 불만 유형·원인·영향을 사실 기반으로 요약 |
| Evaluator | Pipeline 내부 후보를 기준에 따라 상대평가 |
| Critic | 누락·모순·위험 탐지와 수정 가능한 지침 제공 |
| Improver | VOC 근거·담당·일정·KPI가 포함된 개선안 생성 |
| 독립 LLM Judge | 최종 산출물을 별도 호출·Rubric으로 재평가 |
| 개선안 타당성 평가 | 근거성·구체성·실행 가능성·측정 가능성·위험 평가 |
| QA 검토자 | 자동 평가 근거와 증적을 확인하고 검토 의견 기록 |
| 업무 승인자 | 실제 운영 적용 가능성과 책임 범위를 최종 승인 |

Evaluator와 Critic은 Pipeline 내부 구성원이며, 독립 Judge는 최종 결과를 별도 모델 호출로 평가해 자기평가 편향을 줄입니다.

## 장애·429 대응과 결함관리

- Agent 중단, CSV 누락, 포트 충돌, 인증 오류, timeout, 빈 검색은 성공 응답으로 숨기지 않습니다.
- 429·timeout·overloaded 오류는 설정된 횟수 안에서 지수 backoff로 재시도하고 시도 이력을 남깁니다.
- Pipeline 상태와 Judge 상태를 분리해 Judge 오류가 Pipeline 성공을 덮어쓰지 않게 합니다.
- 결함은 `OPEN → ANALYZED → FIXED → RETESTED → CLOSED` 순서로만 전환합니다.
- 원본 Run과 연결된 RETEST의 관련 Case가 모두 PASS이고 종료 근거가 있어야 CLOSED로 전환할 수 있습니다.
- Jira Key는 선택 정보입니다. 실제 테스트 이슈가 Jira 등록 대상인지 검토한 뒤 연계합니다.

## 배포 판정과 사람 승인

정식 품질 승인은 다음 조건을 모두 요구합니다.

1. 동일 조건의 35개 Case가 모두 PASS
2. 독립 Judge 35건 PASS
3. 개선안 타당성 35건 `AI_PASS`
4. QA 검토 완료
5. 업무 승인 완료
6. 미종결 High·Critical 결함 0건
7. Run·Case·보고서 증적 무결성 정상

조건이 부족하면 `EVIDENCE_DRAFT`, `REVIEW_REQUIRED`, `NOT_APPROVED` 등 실제 상태를 유지합니다. `33 PASS / 2 FAIL → 35 PASS` 개선 주장은 동일 TC·Catalog·Rubric·해시와 결함 링크가 있는 기준선·최종 Run이 모두 확인될 때만 사용합니다.

## 메뉴 구성

`홈 > VOC 품질진단`에서 다음 메뉴를 사용합니다.

- Dashboard
- 수동 TC 수행
- 일괄 TC 수행
- 수행 이력
- 개선안 타당성 검증
- Agent 관리
- VOC 분석
- 테스트케이스
- 품질 평가 기준
- 장애·결함 관리
- A2A Trace
- 품질 보고서
- 사용자 가이드
- 최종 인수·시연

## 자주 발생하는 문제

### Agent가 시작되지 않음

```powershell
cd C:\qaeduc\ai_quality_final_project_2026\voc_quality_runtime
.\scripts\agents.cmd status
Get-Content .\.runtime\logs\retriever.err.log -Tail 50
```

`.env` 필수값과 6101~6106 포트 점유 여부를 확인합니다. 스크립트가 관리하지 않는 프로세스가 포트를 사용하면 자동 종료하지 않습니다.

### Agent 간편 테스트가 OpenAI 401로 실패

`홈 > VOC 품질진단 > Agent 관리`에서 `OpenAI 인증 점검`을 실행합니다. 인증 실패라면 프로젝트 루트 `.env`의 `OPENAI_API_KEY`를 새로 발급한 유효한 키로 교체한 뒤 `Agent 프로세스 상태 변경`을 선택하고 `전체 재시작`합니다.

Interpreter·Summarizer·Evaluator·Critic은 OpenAI 호출이 포함되어 있어 프로세스가 `RUNNING`이어도 키가 잘못되면 간편 테스트가 실패합니다. Retriever의 로컬 검색 성공은 OpenAI 인증 성공을 의미하지 않습니다. 키 값은 화면·로그·보고서·Notion에 기록하지 않습니다.

### Judge 또는 타당성 평가가 ERROR

- 공급자 API 자격 증명과 모델 사용 권한을 확인합니다.
- 429, timeout, 출력 JSON 파싱 오류와 독립성 등급을 수행 이력에서 확인합니다.
- Judge ERROR를 Pipeline FAIL이나 PASS로 바꾸지 않습니다.

### 35건인데 완료 판정이 아님

35개를 선택한 것과 35 PASS는 다릅니다. `NOT_RUN`, `REVIEW_REQUIRED`, `ERROR`, Judge 미평가, 사람 미승인이 있으면 정식 완료가 아닙니다.

### 대시보드가 열리지 않음

```powershell
Get-Content .\logs\local_services\streamlit.stderr.log -Tail 100
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8501/_stcore/health
```

8501 포트를 다른 프로세스가 사용하는 경우 통합 실행기는 해당 프로세스를 임의 종료하지 않습니다.

## 관련 문서

- [VOC 품질개선 로드맵](docs/voc_quality/VOC_QUALITY_IMPROVEMENT_ROADMAP.md)
- [품질 증적 계약](docs/voc_quality/VOC_STEP1_QUALITY_CONTRACT.md)
- [일괄 실행](docs/voc_quality/VOC_STEP3_BATCH_EXECUTION.md)
- [수행 이력](docs/voc_quality/VOC_STEP4_EXECUTION_HISTORY.md)
- [독립 Judge](docs/voc_quality/VOC_STEP5_INDEPENDENT_LLM_JUDGE.md)
- [개선안 타당성](docs/voc_quality/VOC_STEP6_IMPROVEMENT_VALIDITY.md)
- [결함 수명주기](docs/voc_quality/VOC_STEP7_DEFECT_LIFECYCLE.md)
- [품질 보고서](docs/voc_quality/VOC_STEP8_QUALITY_REPORT.md)
- [최종 운영 인수·시연 준비](docs/voc_quality/VOC_STEP10_FINAL_ACCEPTANCE.md)
