# Task 8 종합 시나리오 검증·운영 문서화 보고서

## 상태

`APPROVED` — 2026-07-14 사용자로부터 구현 1~5와 최종 운영 기준 전체 승인을 받았다.

## 구현 1~5

1. 정상 시나리오 자동화
   - API 성공, 공급자 usage·비용, RAG 검색 성공, 품질 100점, 테스트 100% 이벤트를 실제 수신 API로 입력했다.
   - JSONL·CSV 집계, summary·timeseries·events API, Streamlit view model을 거쳐 `정상`과 열린 결함 0건을 검증했다.
2. 오류·지연 시나리오 자동화
   - API 5xx는 오류율 위험과 API 로그 확인 조치로 연결되는지 검증했다.
   - 6초 응답은 p95 주의와 단계별 지연 확인 조치로 연결되는지 검증했다.
3. 비용·RAG·안전성 시나리오 자동화
   - 50,000원 초과 비용은 예산 위험, RAG no-result 5% 초과는 주의, 안전성 위반 1건은 위험으로 검증했다.
   - 기존 RAG 권장 조치와 전체 상태의 불일치를 수정해 승인된 KPI 임계값과 일치시켰다.
4. 알림·결함 E2E 검증
   - 각 이상 시나리오에서 Prometheus 원천 metric과 대응 Grafana 규칙 UID를 확인했다.
   - firing 후 열린 결함 1건, resolved 후 0건, 재시도 중복 제거, annotation 원문 미저장을 확인했다.
5. 운영·검증 문서와 실행 도구
   - 정적·전체 검증을 반복 실행할 `tools/validate_dashboard.ps1`을 추가했다.
   - 실행, 화면 확인, 일상 점검, 장애 대응, 백업·복구, 종료, 변경 관리를 하나의 운영 가이드로 정리했다.

## 시나리오 결과

| 시나리오 | 화면 상태 | Prometheus·Grafana | 결함 수명주기 | 결과 |
|---|---|---|---|---|
| 정상 | 정상 | 경고 없음 | 0건 | PASS |
| API 5xx | 위험 | `api.service_errors` / `qa_api_error_rate` | 1→0 | PASS |
| p95 6초 | 주의 | `api.duration_ms` / `qa_api_p95_latency` | 1→0 | PASS |
| 일 비용 초과 | 위험 | `llm.cost_micros_krw` / `qa_llm_budget_critical` | 1→0 | PASS |
| RAG no-result | 주의 | `rag.no_result` / `qa_rag_no_result` | 1→0 | PASS |
| 안전성 위반 | 위험 | `safety.violations` / `qa_safety_violation` | 1→0 | PASS |

## 수정 파일

- `tests/test_dashboard_e2e_scenarios.py`: 6개 데이터→화면→알림→결함 시나리오
- `tools/validate_dashboard.ps1`: 빠른 검증과 전체 회귀 검증 실행기
- `dashboard/services/overview_dashboard.py`: RAG no-result 전체 상태 기준 보완
- `tests/test_overview_dashboard.py`: RAG 상태 회귀 테스트
- `docs/ai_qa_dashboard_operations_guide.md`: 최종 운영 가이드
- `docs/qa_observer_run_guide.md`: webhook 환경변수와 최종 가이드 연결
- `docs/qa_observer_task7_report.md`, `docs/ai_qa_dashboard_roadmap.md`: Task 7 승인과 Task 8 진행 상태

## 검증 결과

- Task 8·Grafana·Streamlit 관련 테스트: 14 PASS
- 전체 회귀 테스트: 114 PASS
- Python compileall: PASS
- Docker Compose 정적 구문 해석: PASS
- 검증 후 백업: `task8-final-validation-verified`, SHA-256 `df8bf97fb896ed9111318e3211adc1be5f909aee442ca8c181c7ac76a0d92759`
- 정상·API 오류·지연·비용 초과·RAG 실패·안전성 위반: 6/6 PASS
- 기존 Starlette/httpx deprecation warning 1건과 Streamlit 내부 NumPy timedelta warning 1건 유지
- 실제 Docker 컨테이너의 Grafana 프로비저닝·화면·알림 송수신은 기존 사용자 요청에 따라 추후 인수 항목 유지

## 실행·확인 방법

빠른 검증:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\validate_dashboard.ps1
```

전체 검증:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\validate_dashboard.ps1 -Full
```

실제 서비스 확인은 `docs/ai_qa_dashboard_operations_guide.md`의 Docker 실행·화면 확인·장애 대응 절차를 따른다.

## 주의 사항

- 검증 시나리오는 임시 디렉터리와 TestClient를 사용하므로 운영 JSONL·CSV를 변경하지 않는다.
- 실제 Docker 검증 전 운영용 webhook token과 명시적 USD/KRW 환율을 준비한다.
- notification policy는 기존 Grafana 정책 트리 전체를 덮어쓸 수 있으므로 적용 전 export·백업한다.
- 백업 ZIP에는 비밀값과 런타임 data·logs·reports가 포함되지 않는다.
- 외부 Slack·Jira 자동 연동과 기존 대시보드 숨김·삭제는 이번 최종 인수 범위에 포함하지 않았다.

## 사용자 확인 항목

- [x] 구현 1: 정상 시나리오와 정상 화면 기준 승인
- [x] 구현 2: API 오류·지연 상태와 조치 기준 승인
- [x] 구현 3: 비용·RAG·안전성 상태 기준 승인
- [x] 구현 4: Prometheus→Grafana→결함 firing/resolved 검증 승인
- [x] 구현 5: 검증 스크립트·최종 운영 가이드 승인

## 추후 체크 및 확장

- [ ] Docker Desktop 실행 후 전체 서비스 build·health 확인
- [ ] Grafana 규칙 8개·contact point·notification policy 실제 프로비저닝 확인
- [ ] 실제 test alert firing·resolved로 Streamlit 열린 결함 1→0 확인
- [ ] 운영 환율과 HMAC key를 비밀 저장소에서 주입
- [ ] 신규 상황판 인수 후 기존 대시보드 숨김·삭제 여부 별도 결정
- [ ] 데이터량 증가 시 SQLite 도입 여부 별도 승인
- [ ] 필요 시 Slack·이메일·Jira 외부 연동 별도 승인

## 종합 상황판 시각화 개선 (2026-07-14)

참고 화면의 정보 위계에 맞춰 신규 `종합 현황 > AI QA 종합 현황` 화면을 다음과 같이 재구성했다. 기존 운영 대시보드와 메뉴는 변경하지 않았다.

- 상단: 전체 품질점수, 테스트 통과율, p95 응답시간, 오류율, 안전성 위반, API 비용 6개 KPI 카드
- 1행: 품질 점수 영역 차트, 테스트 Pass·Fail·Error 도넛 차트, 정확성·안전성·성능·RAG 운영 상태
- 2행: 품질 지표별 가로 막대 차트, 단계별 평균 응답시간 누적 구성, RAG 검색 성공률·Top-K 적중률·No Result·검색시간
- 하단: 실제 이벤트에서 추출한 최근 실패·결함 표, 임계값 기반 알림, 상태별 추천 조치
- 데이터 부재 시 임의의 예시 수치를 생성하지 않고 `데이터 없음` 또는 빈 상태 안내를 표시

수정 파일:

- `dashboard/pages_top/overview_dashboard.py`: 참고 화면형 레이아웃과 Altair 차트·상태 카드 구현
- `dashboard/services/overview_dashboard.py`: 테스트 분포, 운영 상태, RAG 품질, 실패·결함, 알림 view model 추가
- `tests/fixtures/overview_dashboard_app.py`: 차트·상태 검증용 비식별 샘플 집계 보완
- `tests/test_overview_dashboard.py`: 신규 구성과 데이터 변환 회귀 테스트 보완

검증 결과:

- 신규 종합 화면 전용: 5 PASS
- 전체 회귀: 114 PASS
- Python 구문 검사: PASS
- 기존 경고 2건(Starlette/httpx, Streamlit 내부 NumPy timedelta) 외 신규 경고·예외 없음

확인 방법:

```powershell
streamlit run .\dashboard\streamlit_app.py
```

브라우저에서 `종합 현황` → `AI QA 종합 현황`을 선택한다. 차트의 실데이터 표시를 위해서는 `qa-observer`가 실행 중이고 선택 기간에 수집 이벤트가 있어야 한다.

### 공급자·모델 필터 수정

시각화 개선 당시 공급자 선택지가 1개이면 화면에 표시하지 않고 `openai`를 자동 적용한 결과, provider/model 차원이 없는 품질·테스트·API·안전성·RAG 공통 집계가 제외되는 문제가 발생했다.

- 환경·서비스·공급자·모델 필터를 모두 화면에 명시적으로 표시
- 공급자와 모델의 기본값을 `전체`로 설정
- `전체`일 때 API에는 `provider=None`, `model=None`을 전달
- 사용자가 값을 선택한 경우에만 해당 차원 필터 적용
- 기본 실데이터 렌더링: 품질 92.7점, 테스트 37.6%, p95 0.01초, 오류율 0%, 안전성 2건, RAG 성공률 94.2%
- 전용 테스트 5 PASS, 전체 테스트 114 PASS, Streamlit 실데이터 AppTest 예외 0건

API 비용은 승인 환율과 가격 적용 데이터가 없고 Top-K 적중률은 원천 평가 표본이 없으므로 해당 두 항목의 `데이터 없음` 표시는 정상이다.

### 테스트 수행 상세 스타일·압축 레이아웃 적용

기존 `테스트 수행 상세` 화면의 시각 체계를 신규 종합 상황판에도 일관되게 적용했다.

- 진청 제목, 얇은 청색 테두리, 흰색→연청 그라데이션 카드 사용
- 테스트 상세의 아이콘 방식과 동일한 인라인 선형 SVG를 상태·KPI·RAG 카드에 적용
- 최상단 제목 왼쪽, 기간·환경·서비스·공급자·모델·조회 조건 오른쪽의 한 행 구성
- 전체 상태·수집 신선도를 별도 경고 두 줄 대신 압축 상태 바 한 줄로 통합
- KPI 6개를 높이 91px의 아이콘 카드로 변경
- 품질·테스트·응답시간 차트 높이를 145~165px로 축소
- RAG 4개 지표를 높이 73px의 2×2 아이콘 카드로 변경
- 실패 테스트·결함·알림·추천 조치를 기본 접힘 상세 영역으로 이동
- 기존 운영 대시보드와 데이터 집계 구조는 변경하지 않음

검증 결과는 종합 화면 5 PASS, 전체 114 PASS, 실데이터 AppTest 예외 0건이며 qa-observer·FastAPI·Streamlit 세 서비스는 정상 실행 중이다.

### 안전성 위험 조치 연결·수집 상태 판정 개선

`마지막 수집 데이터 2분 이상 미갱신`은 수집기 장애가 아니라 최근 업무 이벤트의 발생 시각을 기준으로 한 신선도 판정이었다. qa-observer의 `/health` 확인 결과 스케줄러는 30초 주기로 실행되고 저장소도 쓰기 가능한 상태였으므로, 수집기 상태와 업무 이벤트 신선도를 분리했다.

- `/health`를 종합 현황 조회 묶음에 추가해 수집기·스케줄러·저장소 상태를 별도로 확인
- 수집기가 정상일 때 오래된 이벤트를 장애로 판정하지 않고 `신규 이벤트 대기 중`으로 표시
- `갱신` 버튼으로 수집 상태와 집계 캐시를 즉시 다시 조회
- Streamlit 실시간 영역을 30초 자동 갱신 fragment로 구성해 새 위험과 수집 상태를 화면에 자동 반영
- 안전성 위험 발생 시 최신 Severity·Run ID·Case ID·탐지 기준을 상단에 표시
- `상세·조치`에서 안전성 이벤트 목록과 빠른 조치 순서를 확인
- `실행 이력`에서 해당 Run의 테스트 수행 상세를 자동으로 열어 실패 응답과 평가 결과 확인
- 이벤트 이력과 테스트 수행 이력이 불일치하면 보존 이력 확인 경고 표시

실데이터에서 확인한 최신 위험은 `RUN-20260714132338 / TC-017`이며 `llm_judge_safety_score` Critical 및 `rule_safety_score` High 이벤트가 수집되어 있다. 전체 회귀 테스트는 116 PASS이며 Streamlit 8501을 재시작해 변경 사항을 반영했다.

### Streamlit 실행 환경 불일치 오류 수정

페이지 전환 중 발생한 `LayoutsMixin.container() got an unexpected keyword argument 'key'`는 30초 자동 갱신 로직 자체의 오류가 아니었다. 8501이 프로젝트 `.venv`가 아니라 시스템 Python으로 재기동되어 Streamlit 1.37.1이 사용되었고, 현재 화면이 요구하는 `st.container(key=...)` 등 최신 API와 호환되지 않은 것이 원인이었다. 자동 갱신 rerun 시점에 전체 스크립트가 다시 실행되면서 해당 불일치가 드러났다.

- 프로젝트 `.venv` Streamlit 1.59.2와 시스템 Streamlit 1.37.1의 버전 차이 확인
- 요구사항을 `streamlit>=1.59.0,<2.0.0`으로 상향
- 앱 시작 시 1.59 미만이면 원래 TypeError 대신 올바른 실행 명령을 안내하고 중단
- `tools/start_dashboard.ps1` 추가: `.venv`와 버전을 검증하고 8501의 기존 Streamlit만 안전하게 교체
- 운영 가이드에 Windows 로컬 표준 실행 명령 추가
- 8501을 새 스크립트로 재기동하고 HTTP 200 및 Streamlit 1.59 계열 Uvicorn 실행 로그 확인
- Python compileall PASS, 종합 현황 7 PASS, 전체 회귀 116 PASS

### LLM 토큰 표시·갱신 안정화·시작 화면 변경

API 비용이 `데이터 없음`으로 표시된 원인을 실제 summary, timeseries, LLM 이벤트, 가격 카탈로그 및 실행 환경으로 추적했다.

- 최근 7일 LLM 호출 72건, 입력 43,962개, 출력 4,348개, 캐시 입력 0개, 총 48,310개 토큰은 정상 수집·집계됨
- 이벤트 모델 `gpt-4o-mini-2024-07-18`은 가격표의 alias와 일치함
- LLM 호출 시 `QA_OBSERVER_USD_KRW`가 설정되지 않아 이벤트의 가격 snapshot과 KRW 비용 필드가 null로 기록됨
- 따라서 가격 적용률 0%, KRW 비용 null, 예산 사용률 null이 된 것이며 토큰 누락은 아님
- 비용이 미산정이어도 KPI를 `LLM 토큰 / API 비용`으로 표시하고 총·입력·출력 토큰과 비용 미산정 상태를 노출
- 비용이 산정된 경우에는 KRW 비용, 토큰 수, 예산 사용률을 함께 표시
- 30초 fragment 재조회 시 위험 표시 위에 나타나던 spinner를 제거해 세로 레이아웃 이동 방지
- 신규 Streamlit 세션의 기본 메뉴를 `종합 현황 > AI QA 종합 현황`으로 변경
- 실데이터 AppTest에서 시작 화면 제목, `48,310개`, 비용 카드 표시 및 예외 0건 확인
- 종합 현황 7 PASS, 전체 회귀 116 PASS, Streamlit 8501 HTTP 200

### 테스트 도넛 블루톤·상단 패널 균등화

테스트 결과 도넛에 남아 있던 녹색·빨강·주황 상태 팔레트를 테스트 수행 상세 화면과 동일 계열의 블루톤으로 통일했다.

- Pass `#155A96`, Fail `#5599D2`, Error `#A9CAE7` 적용
- 품질 점수 추이·테스트 결과·운영 상태 패널 폭을 1:1:1로 변경
- 품질 추이와 테스트 도넛의 차트 높이를 모두 185px로 통일
- 도넛 반지름을 inner 62px, outer 98px로 확대
- 세 패널 모두 동일 행의 stretch 컨테이너를 유지해 외곽 박스 높이 동일
- Windows `.venv` Python wrapper와 실제 Streamlit 자식 프로세스를 함께 종료하도록 재기동 스크립트 보완
- 종합 현황 전용 8 PASS, 전체 회귀 117 PASS

### RAG Top-K 원인 표기·실행별 품질 추이

RAG 검색 이벤트 500건과 최근 품질 평가 이벤트를 직접 확인해 Top-K 및 품질 추이 기준을 보완했다.

- RAG 검색 수·결과 수·No Result·검색시간 이벤트는 정상 수집됨
- 모든 RAG 이벤트의 `expected_document_fingerprint`와 `top_k_hit`가 null이므로 Top-K 집계 표본은 0건
- 원인은 테스트 케이스에 정답 문서 ground truth가 없고 검색 함수도 정답 문서 ID를 전달받지 않는 구조
- Top-K를 `데이터 없음` 대신 `평가 기준 없음`으로 표시하고 정답 문서 기준 미수집 안내 추가
- Top-K 적용 절차: 테스트 케이스 `expected_document_id` 정의 → 동일 HMAC 문서 ID 생성 → 검색 상위 K 결과와 비교 → `top_k_hit` boolean 기록 → 평가된 표본만 적중률 집계
- 기존 품질 추이는 일별 metric 평균이라 같은 날 여러 실행이 한 점으로 합쳐졌음을 확인
- 품질 평가 이벤트 전용 조회를 추가하고 `run_id`별 평가 지표 평균 × 20점으로 재집계
- 최신 Run 최대 7개를 시간순으로 표시하며 tooltip에 Run ID와 테스트 케이스 수 제공
- 품질·테스트 차트 높이를 220px로 확대하고 세 외곽 패널 동일 높이 유지
- 실데이터 화면 최근 실행 7건 및 Top-K 원인 문구 확인, 종합 현황 9 PASS, 전체 회귀 118 PASS
