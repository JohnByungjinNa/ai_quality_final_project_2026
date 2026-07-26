# VOC 품질진단 전체 기능 안정화 점검표

점검일: 2026-07-26  
점검 기준: 코드 기준 정적 점검 + 기존 테스트 코드 근거 확인  
점검 범위: 홈 > VOC 품질진단 전체 메뉴

## 1. 점검 기준

이 점검표는 화면을 직접 브라우저로 클릭 검증한 결과가 아니라, 현재 저장소의 Streamlit 화면 코드, 서비스 코드, 테스트 코드를 기준으로 작성한 안정화 체크리스트다.

주요 확인 파일은 다음과 같다.

| 구분 | 파일 |
| --- | --- |
| VOC 화면/라우팅 | `dashboard/pages_top/voc_quality_view.py` |
| 상단/사이드 메뉴 | `dashboard/navigation.py` |
| VOC 실행/평가 서비스 | `dashboard/services/voc_quality_service.py` |
| Run 저장/승인 상태 | `dashboard/services/voc_run_store.py` |
| 보고서 생성 | `dashboard/services/voc_report_service.py` |
| 최종 인수 스냅샷 | `dashboard/services/voc_acceptance_service.py` |
| 통합 TC 카탈로그 | `voc_quality_runtime/quality_diagnosis/quality_test_catalog.json` |
| 호환용 실행 TC | `voc_quality_runtime/quality_diagnosis/test_cases.json` |
| 회귀 테스트 | `tests/test_voc_quality_integration.py`, `tests/test_voc_validity.py` |

상태 표기는 다음 기준을 사용한다.

| 상태 | 의미 |
| --- | --- |
| 반영 | 요청 기능이 코드상 구현되어 있고 테스트 또는 코드 근거가 명확함 |
| 부분반영 | 핵심 기능은 있으나 UX, 시연 흐름, 예외 처리, 화면 일관성 보완이 필요함 |
| 미반영 | 요청된 동작이 코드상 확인되지 않거나 현재 메뉴 흐름에 연결되지 않음 |
| 후속보완 | 안정화 이후 기능 개선 단계에서 다듬어야 하는 항목 |

## 2. 전체 구조 요약

현재 VOC 품질진단의 기본 메뉴 흐름은 다음 순서로 구성되어 있다.

```text
Dashboard
→ Agent 관리
→ 테스트케이스
→ 품질 평가 기준
→ 수동 TC 수행
→ 일괄 TC 수행
→ 수행 이력
→ 개선안 타당성 검증
→ 장애·결함 관리
→ 품질 보고서
→ 사용자 가이드
→ 최종 인수·시연
```

`VOC 분석`, `A2A Trace`는 사이드 메뉴에서는 제거되어 있으나, `dashboard/pages_top/voc_quality_view.py`의 내부 `ROUTES`, `VOC_PAGE_META`에는 아직 남아 있다. 현재 사용자 메뉴에는 노출되지 않지만, 안정화 관점에서는 “숨김 라우트로 유지할지 / 완전히 제거할지”를 결정해야 한다.

테스트케이스 기준은 다음 상태다.

| 항목 | 현재 상태 |
| --- | ---: |
| 통합 카탈로그 | 35건 |
| 기존 실행용 `test_cases.json` | 20건 |
| 실행 구현 완료 | 26건 |
| 정의됨·후속 구현 | 9건 |
| VOC Pipeline Case | 18건 |
| 장애/결함 계열 Case | 8건 |
| Agent 역할 품질 Case | 6건 |
| Quality Gate Case | 3건 |

## 3. 화면별 반영/미반영/후속보완 체크리스트

### 3.1 Dashboard

| 점검 항목 | 상태 | 코드 기준 확인 |
| --- | --- | --- |
| 메뉴명이 Dashboard로 표시됨 | 반영 | `dashboard/navigation.py`, `VOC_PAGE_META["Dashboard"]` |
| 상단 설명과 조회 조건이 한 줄 구조로 통합됨 | 반영 | `_render_voc_page_header`, `render_dashboard` |
| 불필요한 화면 흐름 문구가 Dashboard에서는 노출되지 않음 | 반영 | Dashboard 전용 header 분기 |
| 기간 Run 판정 추이 / Agent 운영 상태 / 최근 연결 판정 시각화 | 반영 | `render_dashboard`, `_build_voc_run_history_chart`, `_dashboard_agent_cards` |
| 차트 톤과 zoom 비활성화 계열 적용 | 반영 | chart config 계열 코드 및 테스트 |
| Dashboard에서 특정 Run/Case로 바로 이동하는 드릴다운 | 후속보완 | E2E 시연 흐름에서는 Run 상세 또는 타당성 검증 화면으로 이어지는 이동성이 더 필요함 |

판정: 반영

후속보완:

- 주요 카드에서 “다음 액션”으로 바로 이동하는 링크/버튼을 추가하면 시연 흐름이 더 자연스럽다.
- 독립 Judge, 타당성 검증, QA 승인 상태를 Dashboard에서 회차 단위로 요약하는 보완이 필요하다.

### 3.2 Agent 관리

| 점검 항목 | 상태 | 코드 기준 확인 |
| --- | --- | --- |
| 전체 시작은 6개 Agent 프로세스만 기동 | 반영 | `render_agents`, Agent control 함수, 관련 테스트 |
| “VOC 품질진단 작업 수행 중” 오해 문구는 Agent 전체 시작에는 사용하지 않음 | 반영 | Agent 전용 progress 문구 확인 |
| 상태 새로고침 버튼 상단 배치 | 반영 | `render_agents` |
| 체크박스 문구 “Agent 프로세스 상태 변경” | 반영 | `render_agents` |
| Agent별 시작/중지 버튼 및 카드형 상태 표시 | 반영 | `render_agents`, Agent 카드 CSS |
| Agent별 기동 시간 표시 | 반영 | Agent 카드 렌더링 코드 |
| RUNNING 상태에서 Agent 간편 테스트 버튼 | 반영 | `test_agent_rpc` 호출 흐름 |
| 간편 테스트 결과 요약 표시 | 부분반영 | 성공/실패/소요시간 표시 코드 존재 |
| Improver 간편 테스트 `DEADLINE_EXCEEDED` 대응 | 후속보완 | 타임아웃/입력 payload/응답요약 개선 필요 |

판정: 부분반영

후속보완:

- Improver는 개선안 생성 특성상 단순 ping보다 시간이 길어질 수 있어, “연결 테스트”와 “실제 개선안 생성 테스트”를 분리하는 것이 좋다.
- Agent 카드 높이는 코드상 고정 스타일이 있으나, 실제 브라우저에서 RUNNING/STOPPED/오류 상태별 깨짐 여부를 재검증해야 한다.

### 3.3 테스트케이스

| 점검 항목 | 상태 | 코드 기준 확인 |
| --- | --- | --- |
| 35건 통합 카탈로그 기준으로 표시 | 반영 | `load_unified_quality_cases`, 관련 테스트 |
| 기존 20건 `test_cases.json`의 실행 상세를 통합 카탈로그에 병합 | 반영 | `load_unified_quality_cases` |
| `test_cases.json`은 호환용으로 유지 | 반영 | 서비스 코드와 런타임 파일 구조 |
| 실행 대상 요약 / 검증 영역별 Case 구성 시각화 | 반영 | `render_testcases`, `_build_testcase_group_chart` |
| TC Download / TC Upload 버튼 | 반영 | `render_testcases`, `save_quality_test_catalog` |
| Case 목록 행 클릭 선택 UX | 반영 | row/cell selection 관련 코드 |
| 구현 상태 표시 | 반영 | 카탈로그의 `implementation_status` 사용 |
| 화면 전체 세로 스크롤 최소화 | 부분반영 | 섹션 높이 조정 코드는 있으나 실제 해상도별 확인 필요 |

판정: 반영

후속보완:

- `IMPLEMENTED`, `DEFINED` 같은 내부 상태값이 화면에 남아 있다면 한글 표기로 더 정리해야 한다.
- TC Upload 이후 카탈로그 검증 실패 시, 어느 Case/필드가 문제인지 카드형으로 보여주는 보완이 필요하다.

### 3.4 품질 평가 기준

| 점검 항목 | 상태 | 코드 기준 확인 |
| --- | --- | --- |
| 상단 제목 “품질 평가 기준 수립” | 반영 | `render_rubric` |
| 내부 Pipeline / 독립 LLM Judge / 개선안 타당성 탭 | 반영 | `_render_rubric_management` |
| Rubric 버전, 기준명, 기본 Judge Provider를 한 줄로 배치 | 반영 | `_render_rubric_management` |
| JSON Up / JSON D/L 축약 버튼 | 반영 | `_render_rubric_management` |
| 평가기준 저장 버튼 상태 표시 | 부분반영 | 저장 상태 UI 코드 존재 |
| 변경없음/변경발생/변경완료 상태 UX | 부분반영 | 상태 계산/표시는 있으나 사용자가 지적한 자연스러움은 재검증 필요 |
| Rubric 버전 미변경 시 화면 흔들림 최소화 | 부분반영 | 오류 메시지 영역 조정 코드 존재, 실제 확인 필요 |
| 평가 항목 행 클릭 시 세부 배점 팝업 | 반영 | `_render_rubric_management`, dialog 관련 코드 |
| 팝업 내 이전/다음 이동 | 반영 | 세부 배점 dialog 상태 관리 |
| 세부 배점 합계와 평가 항목 배점 연동 | 반영 | rubric scoring helper 및 테스트 |
| 세부 배점 슬라이더 입력 범위 제한 | 부분반영 | `_rubric_criterion_range`, 테스트 존재 |
| 한 항목 감점 후 다른 항목 가점이 막히는 문제 | 후속보완 | 사용자가 재현한 UX 이슈. 범위 계산 로직은 있으나 편집 흐름 재점검 필요 |
| 평가항목별 배점 그래프가 최고점 대비 채움으로 표시 | 부분반영 | 그래프 관련 요청은 코드상 일부 반영 흔적이 있으나 실제 시각 확인 필요 |

판정: 부분반영

후속보완:

- 세부 배점 조정은 “총점 100 고정” 때문에 슬라이더 상한이 지나치게 보수적으로 동작할 수 있다.
- 더 나은 UX는 “임시 초과/부족 허용 → 하단 합계에서 조정 필요 표시 → 저장 시 검증” 방식이다.
- Rubric 저장 버튼은 상태별 enable/disable, 포커스 처리, 고정 높이 상태 박스를 한 번 더 점검해야 한다.

### 3.5 수동 TC 수행

| 점검 항목 | 상태 | 코드 기준 확인 |
| --- | --- | --- |
| Test Case 선택 실행 명칭 | 반영 | `_goal_testcase_selector` |
| 읽기 전용 안내 문구 제거/축소 | 반영 | `_goal_testcase_selector` |
| 행 클릭으로 Case 선택 | 반영 | selector 코드 |
| Agent Pipeline 실행 버튼을 Case 상세 카드 내부로 배치 | 반영 | `_render_goal_testcase_result` 주변 실행 흐름 |
| 실행 준비 카드 | 반영 | 준비 단계 이벤트 생성 코드 |
| Agent 호출 이벤트 시각화 | 반영 | `_render_agent_pipeline_comparison` |
| 원본 로그 섹션 별도 표시 및 기본 접힘 | 반영 | `_render_agent_pipeline_comparison` |
| 최근 수행 기록 카드의 선택 Case 반영 | 부분반영 | 관련 보정 코드가 있으나 사용자가 이전에 고정값 문제를 지적했으므로 실제 확인 필요 |
| 독립 LLM Judge Provider 카드 선택 | 반영 | `_render_goal_judge_step` |
| 독립 LLM 평가 결과 표시 | 반영 | `_render_goal_judge_result` |
| Pipeline과 독립 LLM 평가가 페이지 전환 후에도 백그라운드 지속 | 부분반영 | background job 구조 존재, 긴 실행/재접속 시나리오 추가 확인 필요 |
| 진행 상태 한글화 | 부분반영 | 일부 상태 변환 함수가 있으나 전체 화면의 영문 잔존 여부 확인 필요 |

판정: 부분반영

후속보완:

- “성공/완료/수행 중” 용어를 화면 전체에서 한 번 더 통일해야 한다.
- 비순차 Agent 흐름이 발생했을 때 원인 설명이 항상 붙는지 실제 로그 샘플로 검증해야 한다.
- 독립 LLM 평가 섹션은 Pipeline 완료 후 선택 실행이라는 2단계 구조가 명확히 보이도록 시연 기준 재정리가 필요하다.

### 3.6 일괄 TC 수행

| 점검 항목 | 상태 | 코드 기준 확인 |
| --- | --- | --- |
| 통합 카탈로그 35건 기준 표시 | 반영 | `load_quality_test_catalog`, `start_batch_run` |
| 실행 구현 완료/후속 구현 Case 구분 | 반영 | `implementation_status`, batch 상태 모델 |
| 후속 구현 9건 NOT_RUN 기록 | 반영 | `start_batch_run` |
| 안내 문구 제거 요청 | 반영 | 화면 문구 정리 코드 |
| 백그라운드 실행 | 반영 | batch job/session state 구조 |
| 진행 팝업, 예상 소요시간, 프로그래스바 | 반영 | `_open_batch_progress_dialog`, `_render_batch_progress_dialog` |
| 페이지 전환 후 batch 계속 수행 | 부분반영 | background 구조는 있으나 실제 긴 batch로 확인 필요 |
| “건수 카드 클릭 → 해당 건수 일괄 실행” | 후속보완 | 현재는 실행 대상 선택/실행 버튼 흐름 중심. 카드 직접 실행 UX는 명확히 연결되지 않음 |

판정: 부분반영

후속보완:

- 시연 관점에서는 “전체 35건”, “실행 가능 26건”, “후속 구현 9건” 카드를 클릭하면 필터/실행 대상이 바로 잡히는 구조가 좋다.
- 9건 후속 구현 Case를 최종 배포 판정에서 어떻게 취급할지 정책을 확정해야 한다.

### 3.7 수행 이력

| 점검 항목 | 상태 | 코드 기준 확인 |
| --- | --- | --- |
| Run 목록/상세 표시 | 반영 | `render_voc_history`, `_render_voc_run_detail` |
| verification_scope 시각화 | 반영 | `_render_history_verification_scope` |
| 35건 전체, 실행 가능 26건, 후속 구현 9건 표시 | 반영 | scope summary 코드 및 테스트 |
| RETEST 부모 Run 관계 표시 | 반영 | `_render_retest_comparison` |
| Run 상세에서 독립 Judge/타당성 관련 정보 확인 | 부분반영 | 상세 탭과 재평가 흐름 존재 |
| 다음 액션 안내 | 후속보완 | 시연형 E2E에서는 “이 Run은 다음에 무엇을 해야 하는가”가 더 직접적으로 보여야 함 |

판정: 부분반영

후속보완:

- Run/Case별 상태에 따라 “독립 Judge 필요”, “타당성 평가 필요”, “보완 입력 필요”, “QA 검토 가능”, “업무 승인 가능”, “최종 판정 가능” 같은 다음 액션 카드를 추가하는 것이 필요하다.

### 3.8 개선안 타당성 검증

| 점검 항목 | 상태 | 코드 기준 확인 |
| --- | --- | --- |
| 회차/Case 선택 기준 표시 | 반영 | `render_improvement_validity`, `_render_validity_review_queue` |
| 자동 타당성 평가 실행 | 반영 | `evaluate_voc_improvement_validity` |
| 평가 항목과 점수 지표 표시 | 반영 | 평가 결과 카드/테이블 렌더링 코드 |
| 수행 절차별 평가 결과 표시 | 반영 | 평가 단계 렌더링 코드 |
| 보완 가이드 자동 생성 | 반영 | `_render_validity_rework_guide` |
| 보완 지시문 표시 | 반영 | rework guide / instruction 렌더링 |
| 타당성 평가 보완 입력 기능 | 반영 | `_render_validity_supplement_editor`, `save_voc_validity_supplement` |
| 보완 입력값을 재평가에 반영 | 반영 | `evaluate_voc_improvement_validity`의 supplement 반영 |
| 지시 기반 RETEST 실행 흐름 | 부분반영 | RETEST 버튼/parent run 구조 존재, 완전한 guided flow는 후속보완 |
| QA 검토 가능 조건 카드 | 반영 | `_render_human_validity_review` |
| QA 승인/보완요청/반려 액션 | 반영 | `review_voc_improvement_validity` |
| 업무 승인 액션 | 반영 | `decide_business_approval` |

판정: 부분반영

후속보완:

- 사용자가 “71점 수정필요 → QA 검토 가능으로 가려면 무엇을 해야 하는지”를 바로 알 수 있도록, 점수 부족 항목별 보완 입력 가이드와 재평가 버튼을 한 화면에서 더 자연스럽게 연결해야 한다.
- 타당성 평가는 A2A 개선안과 독립 LLM Judge 결과를 함께 참고하지만, 최종 목적은 “실행 가능한 개선 계획인지”를 판단하는 별도 단계로 표현해야 한다.

### 3.9 장애·결함 관리

| 점검 항목 | 상태 | 코드 기준 확인 |
| --- | --- | --- |
| 결함 등록 | 반영 | `_render_defect_create` |
| 결함 목록/상태 변경 | 반영 | `_render_defect_list` |
| 장애 주입 테스트 | 반영 | `_render_isolated_fault_tests` |
| 결함-Run 연결 | 부분반영 | 결함 후보와 Run 근거 연결 코드 존재 |
| 보완/RETEST/승인 흐름과 결함 상태의 직접 연동 | 후속보완 | E2E 시연에서는 결함 조치 후 재평가로 이어지는 연결이 더 필요함 |

판정: 부분반영

후속보완:

- “결함 등록 → 조치 기록 → RETEST 생성 → 타당성 재평가 → QA 승인 가능” 흐름을 한눈에 보여주는 상태 카드가 필요하다.

### 3.10 품질 보고서

| 점검 항목 | 상태 | 코드 기준 확인 |
| --- | --- | --- |
| VOC 품질 보고서 모델 생성 | 반영 | `build_quality_report_model` |
| TXT/XML/HTML 보고서 생성 | 반영 | report service |
| 배포 가능성 판단 정보 포함 | 반영 | release readiness 계산 |
| 최종 배포 판정과 연결 | 부분반영 | 보고서가 최종 인수와 연결되지만 gate 기준이 매우 엄격함 |

판정: 부분반영

후속보완:

- “Strict 배포 기준”과 “시연 기준”을 구분할 필요가 있다.
- 현재 최종 판정은 35건 전체 업무 승인에 가까운 기준이므로, 후속 구현 9건을 포함한 시연에서는 도달하기 어렵다.

### 3.11 사용자 가이드

| 점검 항목 | 상태 | 코드 기준 확인 |
| --- | --- | --- |
| 가이드 문서 로딩 | 반영 | `render_guide`, `load_guide` |
| 현재 복구된 메뉴 흐름 반영 | 부분반영 | 문서가 최신 UI와 완전히 일치하는지는 별도 확인 필요 |

판정: 부분반영

후속보완:

- 이번 안정화 점검표와 E2E 시연 흐름이 확정되면 사용자 가이드도 같이 갱신해야 한다.

### 3.12 최종 인수·시연

| 점검 항목 | 상태 | 코드 기준 확인 |
| --- | --- | --- |
| 최종 인수 스냅샷 생성 | 반영 | `build_acceptance_snapshot` |
| 인수 증적 생성 | 반영 | `generate_voc_acceptance_evidence` |
| 최종 gate 상태 표시 | 반영 | `render_acceptance` |
| 35건 전체 품질 gate | 반영 | acceptance service |
| 실제 시연 가능한 E2E 완료 조건 | 후속보완 | 9건 후속 구현 Case 때문에 전체 35건 승인 기준은 현실적으로 막힐 수 있음 |

판정: 부분반영

후속보완:

- 최종 시연에는 `실행 가능 26건 기준 통과 + 후속 구현 9건 명시적 제외/보류 승인` 같은 데모용 gate 정책이 필요하다.
- 운영 배포 기준과 시연 통과 기준을 분리하지 않으면 최종 판정 화면이 계속 미완료로 남을 가능성이 크다.

### 3.13 숨김/잔존 화면

| 화면 | 상태 | 코드 기준 확인 | 후속 판단 |
| --- | --- | --- | --- |
| VOC 분석 | 미노출·잔존 | `ROUTES`, `VOC_PAGE_META`에는 남아 있고 navigation에서는 제외됨 | 개발용으로 숨김 유지 또는 코드 제거 결정 필요 |
| A2A Trace | 미노출·잔존 | `ROUTES`, `VOC_PAGE_META`에는 남아 있고 navigation에서는 제외됨 | Dashboard/수동 TC 수행 Trace와 중복되므로 정리 필요 |

## 4. E2E 시연 흐름 연결성 점검

현재 코드가 지원하는 논리 흐름은 다음과 같다.

```text
테스트케이스 35건 관리
→ 수동 TC 수행 또는 일괄 TC 수행
→ Run/Case 수행 이력 저장
→ 독립 LLM Judge 평가
→ 개선안 타당성 자동 평가
→ 보완 입력 또는 RETEST
→ QA 검토
→ 업무 승인
→ 품질 보고서
→ 최종 인수·시연
```

다만 실제 시연 가능한 end-to-end 흐름으로 보려면 다음 연결부가 아직 약하다.

| 연결 구간 | 현재 상태 | 보완 필요 |
| --- | --- | --- |
| 수행 이력 → 다음 액션 | 부분반영 | Run/Case별 다음 해야 할 일을 카드로 보여줘야 함 |
| 타당성 평가 → 보완 입력 → 재평가 | 부분반영 | 기능은 있으나 “점수가 왜 부족하고 무엇을 입력해야 하는지” 안내 강화 필요 |
| 타당성 AI_PASS → QA 검토 | 반영 | 현재 사용자가 QA 검토/승인 가능 |
| QA 검토 → 업무 승인 | 반영 | 같은 사용자가 업무 승인 가능 |
| 업무 승인 → 최종 배포 판정 | 부분반영 | 최종 gate가 35건 전체 승인 기준이라 후속 구현 9건 때문에 막힐 수 있음 |
| 일괄 수행 35건 → 최종 시연 | 후속보완 | 26건 실행 가능 + 9건 후속 구현을 어떤 배포 상태로 볼지 정책 필요 |

## 5. 기능 개선 착수 전 결정해야 할 기준

다음 기능 개선으로 바로 들어가기 전에 가장 먼저 확정해야 할 것은 최종 배포 판정 기준이다.

### 권장 기준

시연용 기준과 운영용 기준을 분리한다.

| 기준 | 설명 |
| --- | --- |
| 시연용 기준 | 실행 구현 완료 26건이 통과하고, 후속 구현 9건은 `NOT_RUN / 후속 구현`으로 명시 관리되면 시연 통과 가능 |
| 운영용 기준 | 전체 35건이 모두 구현·수행·타당성 승인·QA 승인·업무 승인까지 완료되어야 최종 배포 가능 |

이렇게 분리하면 현재 프로젝트 상태에서도 시연 가능한 end-to-end 흐름을 만들 수 있고, 동시에 최종 운영 기준은 느슨하게 만들지 않을 수 있다.

## 6. 다음 개선 작업 우선순위

안정화 이후 기능 개선은 다음 순서로 진행하는 것이 좋다.

| 순서 | 작업 | 목적 |
| ---: | --- | --- |
| 1 | 수행 이력 화면에 Run/Case별 다음 액션 카드 추가 | 사용자가 다음에 무엇을 해야 하는지 바로 이해 |
| 2 | 개선안 타당성 검증 화면에 보완 입력 → 재평가 → QA 검토 흐름 고정 | 71점 수정필요 같은 상태를 실제 조치로 연결 |
| 3 | QA 검토 가능 목록과 승인/보완요청/반려 액션 정리 | 같은 사용자가 QA 검토까지 수행 가능한 프로젝트 조건 반영 |
| 4 | 업무 승인 및 최종 배포 판정 상태 모델 보완 | QA 이후 최종 판정까지 끊기지 않게 연결 |
| 5 | 시연용 gate와 운영용 gate 분리 | 26건 실행 가능 + 9건 후속 구현 상태에서도 시연 가능하게 구성 |
| 6 | 품질 보고서/최종 인수·시연 화면에 E2E 상태 요약 추가 | 최종 발표에서 전체 흐름을 한 화면으로 설명 |

## 7. 현재 기준 최우선 후속보완 목록

| 우선순위 | 항목 | 이유 |
| ---: | --- | --- |
| 1 | 최종 배포 판정 기준 분리 | 35건 전체 승인 기준이면 현재 9건 후속 구현 때문에 시연 완료가 막힘 |
| 2 | 수행 이력의 다음 액션 표시 | 수행 이력, 타당성 검증, QA 승인 흐름이 사용자의 머릿속에서만 연결되어 있음 |
| 3 | 타당성 평가 보완 입력 UX 강화 | 낮은 점수에서 어떤 보완을 해야 하는지 화면이 더 알려줘야 함 |
| 4 | Rubric 세부 배점 슬라이더 재점검 | 한 항목 감점 후 다른 항목 가점이 막히는 사용성 이슈가 남아 있음 |
| 5 | 진행 상태 한글화 최종 점검 | 실행 상태와 로그에 영문 상태값이 일부 남아 있을 가능성이 있음 |
| 6 | 숨김 라우트 정리 | `VOC 분석`, `A2A Trace`가 메뉴에서는 제거됐지만 코드에는 남아 있음 |

