# VOC 품질진단 안정화 점검표 · 2026-07-31

점검일: 2026-07-31  
점검 방식: 코드 기준 정적 점검 + 핵심 자동 테스트 실행  
점검 범위: 홈 > VOC 품질진단, 홈 > GitHub 관리 중 VOC 시연/보존 흐름 관련 기능

## 1. 안정화 목표

이번 점검의 목적은 기능을 더 많이 붙이는 것이 아니라, 현재까지 복구·보완한 VOC Improve 기능을 잃지 않고 시연 가능한 기준선으로 고정하는 것이다.

특히 다음 원칙을 VOC 품질진단 전체 화면의 공통 검수 기준으로 둔다.

| 원칙 | 적용 기준 |
| --- | --- |
| 원본 데이터는 삭제하지 않고 보존한다 | Run, 재시험, 독립 LLM 재평가, 개선안 타당성 재평가는 덮어쓰기보다 이력·차수·부모 관계로 보존한다. |
| 화면에는 지금 봐야 하는 것만 보여준다 | 목록·카드에는 상태, 판단 근거, 다음 액션만 우선 표시하고 원본 로그는 숨긴다. |
| 재수행, 재시험, 재평가를 명확히 구분한다 | 일괄 재수행, RETEST, 독립 LLM 재평가, Rubric 재평가를 상태와 화면 용어에서 혼용하지 않는다. |
| Run ID보다 Case, 질문, 상태, 다음 액션 중심으로 보여준다 | Run ID는 증적 식별자이므로 보조 정보로 두고, 업무 판단은 Case·질문·판정·다음 액션 중심으로 한다. |
| 상세 로그, Trace, 원본 이력은 접힘/팝업/상세에서만 보여준다 | 실시간 추적이 필요한 순간 외에는 Trace와 원본 로그를 기본 노출하지 않는다. |
| 디자인은 간결하고 일관되게 유지한다 | 카드 높이, 버튼 위치, 표 선택 방식, 색상 톤, 탭 스타일을 화면별로 다르게 만들지 않는다. |

## 2. 현재 git 보존 상태

| 항목 | 현재 상태 |
| --- | --- |
| 브랜치 | `main` |
| upstream | `origin/main` |
| 로컬 커밋 상태 | `origin/main`보다 12커밋 ahead |
| 미커밋 변경 | 29개 파일 |
| 변경 규모 | 1,999 insertions / 606 deletions |
| 가장 큰 변경 파일 | `dashboard/pages_top/voc_quality_view.py` |
| 보존 위험 | 중간 커밋 전 상태이므로 추가 작업 전 안전 커밋 필요 |

변경 파일은 VOC 화면, VOC 서비스, 상태 모델, 보고서, 테스트 코드에 집중되어 있다.  
현재 변경분은 기능 단위가 넓게 섞여 있으므로, 다음 작업 전에 최소 1회 안전 커밋을 권장한다.

권장 커밋 메시지:

```text
Stabilize VOC quality diagnosis flow and checklist
```

## 3. Python / `.venv` 환경 점검

| 항목 | 결과 |
| --- | --- |
| `.venv` Python | `Python 3.12.10` |
| Python 실행 경로 | `C:\QAEDUC\ai_quality_final_project_2026\.venv\Scripts\python.exe` |
| 원본 Python 경로 | `C:\Users\nbj01\AppData\Local\Programs\Python\Python312\python.exe` |
| Streamlit | `1.59.2` |
| pytest | `8.3.2` |
| 현재 상태 | 정상 실행 확인 |

이전에 발생했던 오류:

```text
No Python at "C:\Users\nbj01\AppData\Local\Programs\Python\Python312\python.exe"
```

현재는 같은 경로가 다시 확인되고 `.venv`가 정상 실행된다.  
따라서 원인은 코드 문제가 아니라 Python 설치 경로 또는 VS Code 터미널 세션 상태가 일시적으로 깨졌던 것으로 판단한다.

재발 시 우선 조치:

1. VS Code 터미널을 완전히 닫고 새 PowerShell 터미널을 연다.
2. 아래 명령으로 Python 경로를 확인한다.

   ```powershell
   Test-Path C:\Users\nbj01\AppData\Local\Programs\Python\Python312\python.exe
   .\.venv\Scripts\python.exe --version
   ```

3. `Test-Path`가 `False`이면 Python 3.12 설치 또는 `.venv` 재생성이 필요하다.

## 4. 자동 검증 결과

### 4.1 문법 / import 기준 검증

다음 핵심 파일 문법 검사를 통과했다.

```text
dashboard/streamlit_app.py
dashboard/pages_top/voc_quality_view.py
dashboard/pages_top/github_view.py
dashboard/services/voc_quality_service.py
dashboard/services/voc_run_store.py
dashboard/services/voc_judge_service.py
dashboard/services/voc_validity_service.py
dashboard/services/voc_acceptance_service.py
dashboard/services/voc_report_service.py
```

### 4.2 핵심 테스트

실행 명령:

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests\test_voc_quality_state_next_actions.py `
  tests\test_voc_validity.py `
  tests\test_voc_quality_integration.py `
  tests\test_voc_acceptance.py `
  tests\test_voc_quality_report.py `
  tests\test_quality_report_template.py `
  tests\test_improver_provider_fallback.py `
  tests\test_github_management.py -q
```

결과:

```text
214 passed, 2 warnings
```

경고는 Streamlit 내부 `pd.Timedelta` 관련 deprecation warning이며, 현재 기능 실패로 보이지 않는다.

## 5. 화면별 안정화 점검표

상태 기준:

| 상태 | 의미 |
| --- | --- |
| 반영 | 코드와 테스트 기준으로 구현 근거가 명확함 |
| 부분반영 | 핵심 기능은 있으나 실제 화면 클릭 검증 또는 UX 보완 필요 |
| 보완필요 | 안정화 원칙과 충돌하거나 시연 흐름에서 막힐 수 있음 |
| 후속 | 시연 안정화 이후 고도화로 넘겨도 됨 |

### 5.1 Dashboard

| 점검 항목 | 상태 | 코드 기준 |
| --- | --- | --- |
| VOC 품질 Dashboard 메뉴 구성 | 반영 | `dashboard/navigation.py`, `VOC_PAGE_META["Dashboard"]` |
| 조회 조건과 상단 설명 통합 | 반영 | `_render_voc_page_header`, `render_dashboard` |
| 실행 환경, 품질 판정, 독립 LLM 평가, 결함 상태 요약 | 반영 | `render_dashboard` |
| Agent 운영 상태 카드형 표현 | 반영 | Dashboard Agent 카드 렌더링 코드 |
| 숨겨진 상세보다 현재 판단 정보 중심 구성 | 부분반영 | 실제 화면 스크롤/중복 정보 최종 확인 필요 |
| 특정 Run/Case의 다음 액션으로 바로 연결 | 후속 | 수행 이력 또는 타당성 검증으로 드릴다운 강화 가능 |

### 5.2 Agent 관리

| 점검 항목 | 상태 | 코드 기준 |
| --- | --- | --- |
| 전체 시작/재시작/중지 기능 | 반영 | `render_agents`, Agent 제어 스크립트 호출 |
| OpenAI / Anthropic / Gemini 인증 점검 | 반영 | `check_openai_agent_credential`, `check_anthropic_agent_credential`, `check_gemini_agent_credential` |
| Agent별 간편테스트 | 반영 | Agent card quick test 관련 코드와 테스트 |
| 전체 시작/재시작 후 진행 메시지가 계속 남는 문제 | 보완필요 | 실제 화면에서 재현 보고됨. job 상태 동기화/메시지 초기화 재점검 필요 |
| 간편테스트 시 다른 카드가 깜빡이는 문제 | 보완필요 | fragment/상태 갱신 범위 재점검 필요 |
| 정상 RUNNING 상태에서 불필요 안내문 숨김 | 부분반영 | `_render_agent_management_messages` 존재. 실제 화면 확인 필요 |
| 원본 데이터 보존 원칙과 충돌 없음 | 반영 | 프로세스 제어 영역으로 Run 데이터 삭제와 무관 |

우선 보완 방향:

- Agent 제어 완료 후 스냅샷을 자동 갱신하고 메시지 상태를 완료/숨김으로 전환한다.
- 간편테스트 결과는 해당 Agent 카드 내부만 갱신되도록 분리한다.

### 5.3 테스트케이스

| 점검 항목 | 상태 | 코드 기준 |
| --- | --- | --- |
| 35건 통합 카탈로그 기준 관리 | 반영 | `quality_test_catalog.json`, 테스트케이스 렌더링 코드 |
| `test_cases.json` 호환 유지 | 반영 | 실행 호환 구조 유지 |
| TC Download / TC Upload | 반영 | `render_testcases`, `TC Download`, `TC Upload` |
| Upload 검증 실패 시 Case/필드별 카드 표시 | 반영 | `카탈로그 검증 실패` 카드 렌더링 코드 |
| Case 목록 행 클릭 선택 UX | 부분반영 | 코드/테스트 일부 존재. 실제 화면에서 행 전체 선택감 확인 필요 |
| 화면 스크롤 최소화 | 부분반영 | 섹션 높이 조정 흔적 있음. 브라우저 기준 최종 확인 필요 |

### 5.4 품질 평가 기준

| 점검 항목 | 상태 | 코드 기준 |
| --- | --- | --- |
| Rubric 버전 용어 통일 | 반영 | Rubric 화면/테스트 |
| 변경 상태 박스: 변경없음/변경발생/변경완료 | 반영 | `_rubric_save_state` 계열 코드와 테스트 |
| 세부 배점 임시 조정 범위 ±2점 | 반영 | `RUBRIC_CRITERION_TEMPORARY_DELTA = 2` |
| 저장 시 총점 100점 검증 | 반영 | Rubric 저장 검증 코드 |
| 팝업 좌우 이동/닫힘 안정화 | 부분반영 | 관련 dialog state 코드 존재. 실제 반복 클릭 확인 필요 |
| 화면 흔들림 없는 에러/상태 표시 | 부분반영 | 고정 상태 박스 구현 흔적 있음. 실제 브라우저 확인 필요 |
| 항목별 배점 그래프가 최고점 대비 표시 | 부분반영 | 코드/테스트 근거 확인 필요. 화면 확인 우선 |

### 5.5 수동 TC 수행

| 점검 항목 | 상태 | 코드 기준 |
| --- | --- | --- |
| Test Case 선택 후 Agent 파이프라인 실행 | 반영 | `render_goal_monitor` |
| 실행 시작 시 테스트 수행 준비 카드 표시 | 반영 | `테스트 수행 준비`, 준비 단계 렌더링 테스트 |
| 실시간 Agent 파이프라인 fragment 유지 | 반영 | `_live_testcase_pipeline` |
| 실행 중 파이프라인 영역 포커싱 | 반영 | `_render_goal_pipeline_focus_anchor_once` |
| 완료 후 A2A 수행 결과 영역 포커싱 | 반영 | `_render_goal_result_focus_anchor_once` |
| 최근 수행 이벤트와 원본 로그 분리 | 반영 | Agent 호출/원본 로그 섹션 분리 |
| 원본 로그 기본 접힘 | 반영 | raw log `<details>` 구조 |
| 독립 LLM 평가 백그라운드 처리 안내 | 반영 | 독립 LLM 평가 실행 상태/백그라운드 안내 |
| Provider별 독립 LLM 평가 비교 | 반영 | `_manual_judge_comparison_rows` |
| 평가시각 `YYYY-MM-DD HH:MM:SS` 표시 | 반영 | 2026-07-31 요청 반영 |
| 실행 버튼 한 번 클릭으로 동작 | 부분반영 | 이전 이슈 재현 여부 실제 클릭 검증 필요 |
| 선택 TC별 최근 수행 카드의 Case 정보 정확성 | 부분반영 | 보완 코드 흔적 있음. 실제 화면 검증 필요 |
| A2A 결과 내용의 시각적 정돈 | 부분반영 | 구조화 섹션 존재. 디자인 최종 정리 필요 |

### 5.6 일괄 TC 수행

| 점검 항목 | 상태 | 코드 기준 |
| --- | --- | --- |
| 35건 통합 카탈로그 기준 대상 표시 | 반영 | batch selector / catalog 기반 코드 |
| 그룹-Case 선택형 리스트 | 반영 | batch selector 관련 테스트 |
| 선택 건수 유지 및 실행 버튼 연결 | 반영 | session state 기반 선택 관리 |
| 백그라운드 일괄 수행 | 반영 | batch background progress 코드 |
| 진행 팝업 / 예상 소요시간 / 굵은 progress bar | 반영 | progress dialog 테스트 |
| 화면 닫기/페이지 이동 시 백그라운드 안내 | 반영 | `_render_batch_execution_safety_notice` |
| Streamlit 서버 종료 시 작업 지속 불가 안내 | 반영 | safety notice 문구 |
| 실행 중 화면 복귀 시 진행 화면 열기 정확성 | 보완필요 | 실제 화면에서 혼동 보고됨. 상태 복원 로직 재확인 필요 |
| 선택 대상 섹션 영문 잔여 한글화 | 부분반영 | 최근 한글화 반영. 실제 화면 전체 확인 필요 |

### 5.7 수행 이력

| 점검 항목 | 상태 | 코드 기준 |
| --- | --- | --- |
| 조회 조건을 수행 이력 섹션 내부로 이동 | 반영 | 수행 이력 렌더링 코드 |
| Run 목록 행 클릭 선택 | 반영 | `selection_mode`, selected rows 처리 |
| 선택 Run 상세 팝업 | 반영 | Run 상세 dialog |
| 선택 Run 다음 액션 카드 | 반영 | `_render_history_next_action_cards` |
| 수행 이력에서 타당성/QA/보고서 화면 이동 | 반영 | `_apply_history_next_action_target` |
| 재시험 전후 비교 자동 매칭 | 반영 | `_history_retest_pair_basis`, `_history_retest_comparison_plan` |
| 비교 조건 불일치 시 차단 | 반영 | Catalog·TC·Rubric 조건 확인 |
| Rubric 재평가 필요 상태 표시 | 반영 | rubric drift / reevaluation plan |
| 여러 번 RETEST / 여러 번 재평가 차수 표시 | 후속 | 계보와 차수 UI를 더 명확히 해야 함 |
| 선택 Run 영구 삭제 기능 | 보완필요 | 원본 데이터 보존 원칙과 충돌 가능. 삭제 대신 숨김/보관 처리로 전환 권장 |

### 5.8 개선안 타당성 검증

| 점검 항목 | 상태 | 코드 기준 |
| --- | --- | --- |
| 검증 대상 목록 카드 지표 | 반영 | validity candidate cards |
| 대상 검색/회차 유형/평가 상태 한 줄 필터 | 반영 | filter UI 코드 |
| 대상 상세 팝업 | 반영 | GitHub 스타일 탭 구조 계열 코드 |
| 개선안 타당성 평가 절차/점수/지표 표시 | 반영 | validity dimension scorecard / process rendering |
| 보완 입력 저장 | 반영 | `save_validity_supplement` |
| 보완 입력 → 재평가 흐름 | 반영 | validity reevaluation flow |
| QA 검토 가능 조건 카드 | 반영 | `_validity_readiness_model` 계열 코드 |
| QA 검토/승인/보완요청/반려/업무 승인 액션 | 반영 | acceptance/review action flow |
| 실제 TC 1건 E2E 승인 성공 시연 | 보완필요 | 자동 테스트는 통과했으나 실제 API/Agent 환경에서 1건 시연 필요 |
| 평가 편향 보완 설명/증적화 | 후속 | Provider별 비교와 보완 지시문은 있으나 정책 문서화 강화 가능 |

### 5.9 장애·결함 관리

| 점검 항목 | 상태 | 코드 기준 |
| --- | --- | --- |
| 결함 후보/장애 유형 표시 | 반영 | defect service/view code |
| RETEST 연결 | 부분반영 | 재시험 Run과 결함 상태 연결 코드 존재 |
| 결함과 개선안 타당성/QA 승인 연결 | 후속 | 시연 흐름에서 필요한 최소 연결성 검증 필요 |
| 영구 삭제 대신 이력 보존 | 부분반영 | 결함 상태 변경 이력은 보존. Run 삭제 기능과 분리 필요 |

### 5.10 품질 보고서

| 점검 항목 | 상태 | 코드 기준 |
| --- | --- | --- |
| 업무 승인 완료 대상 중심 보고서 | 반영 | report eligibility / approved candidate filtering |
| 품질 증적 보고서 팝업 | 반영 | `_render_quality_report_dialog` |
| HTML / PDF / Word 다운로드 | 반영 | dialog download buttons |
| 미승인/미평가 Run 노출 제한 | 부분반영 | 코드상 게이트 존재. 실제 화면 데이터로 확인 필요 |
| 기존 진단 보고서 보조 영역 설명 | 부분반영 | 보조 영역 설명 문구 존재. 사용자 화면 필요성 재판단 가능 |

### 5.11 사용자 가이드

| 점검 항목 | 상태 | 코드 기준 |
| --- | --- | --- |
| VOC 품질진단 실행·이식·운영 안내 | 반영 | `render_guide` |
| 현재 안정화 원칙 반영 | 후속 | 이번 점검표 기준을 사용자 가이드에도 요약 반영 권장 |

### 5.12 최종 인수·시연

| 점검 항목 | 상태 | 코드 기준 |
| --- | --- | --- |
| 최종 인수 대상 Run 선택 | 반영 | `render_acceptance` |
| 35건 Run 기준 최종 판정 | 반영 | acceptance service |
| 품질 보고서와 연결 | 반영 | 수행 이력/타당성에서 report/demo 이동 코드 |
| 실제 승인 완료 Run 기반 시연 | 보완필요 | 실제 Agent/API 환경에서 끝까지 통과되는 Run 확보 필요 |

### 5.13 GitHub 관리

| 점검 항목 | 상태 | 코드 기준 |
| --- | --- | --- |
| 저장소 현황 | 반영 | `dashboard/pages_top/github_view.py` |
| 프로젝트 동기화 | 반영 | Git 저장 / Git 다운로드 / ZIP 준비 |
| 충돌 사전 점검 | 반영 | conflict preflight code/tests |
| 안전 동기화 가이드 기본 펼침 | 반영 | `expanded=True` |
| README 본문 제거 | 반영 | 저장소 현황 하단 README 본문 검색되지 않음 |
| 실제 원격 GitHub와 차이 확인 | 보완필요 | 현재 로컬 ahead 12 + 미커밋 29개. push 전까지 원격과 차이 존재 |

## 6. 우선 처리해야 할 안정화 작업

### 1순위: 현재 변경분 안전 커밋

이유: 테스트는 통과했지만 아직 미커밋 상태다. 추가 작업 중 충돌·원복이 발생하면 복구 난도가 커진다.

권장 액션:

```powershell
git add dashboard docs tests
git commit -m "Stabilize VOC quality diagnosis flow and checklist"
```

원격 push는 로컬 12커밋 ahead 상태이므로, push 전 `git fetch`와 GitHub 관리 화면의 충돌 사전 점검을 먼저 확인한다.

### 2순위: 수동 TC 1건 E2E 시연

확인 흐름:

```text
수동 TC 선택
→ Agent 파이프라인 실행
→ 독립 LLM 평가
→ 개선안 타당성 평가
→ AI_PASS
→ QA 검토 완료
→ 업무 승인 완료
→ 품질 보고서
→ 최종 인수·시연
```

이 흐름에서 막히는 지점이 실제 다음 보완 대상이다.

### 3순위: Agent 관리 메시지/갱신 문제

현재 사용자 보고 기준으로 가장 불편한 운영 이슈다.

점검 포인트:

- 전체 시작/재시작 후 완료되었는데 메시지가 남는가?
- 상태 새로고침 없이 RUNNING으로 반영되는가?
- 간편테스트 시 다른 Agent 카드가 깜빡이는가?

### 4순위: 원본 데이터 삭제 기능 정책 정리

`선택 Run 영구 삭제`는 개발 중에는 편하지만, 최종 VOC 품질관리 원칙과 맞지 않는다.

권장 변경:

- 일반 화면에서는 영구 삭제 제거
- 필요 시 `보관 처리`, `시연 목록에서 숨김`, `개발자 도구에서만 삭제` 중 하나로 전환

### 5순위: 다중 RETEST / 재평가 계보 UI

여러 번 재시험하거나 Provider별 재평가를 반복할 경우, 사용자는 최신 결과와 부모 관계를 쉽게 이해해야 한다.

권장 표시:

```text
TC-01
원본 Run
 ├─ RETEST #1
 ├─ RETEST #2
 └─ 독립 LLM 재평가 #3 / 개선안 타당성 재평가 #2
```

단, 기본 화면에는 최신 상태와 다음 액션만 표시하고, 계보는 팝업/접힘에서 제공한다.

## 7. 현재 결론

현재 코드 기준으로 VOC 품질진단의 큰 기능 축은 대부분 복구·반영되어 있다.

다만 남은 핵심은 다음이다.

1. 미커밋 변경분 보존
2. 실제 브라우저에서 E2E 1건 시연 검증
3. Agent 관리 갱신/메시지 안정화
4. 원본 데이터 보존 원칙에 맞춘 삭제 기능 정리
5. 여러 번 재시험·재평가되는 계보 표시 정교화

따라서 다음 단계는 기능 추가가 아니라, 통과 가능한 단건 시연을 기준으로 막히는 지점을 하나씩 제거하는 방식이 가장 안전하다.
