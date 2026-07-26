# Step 3. 35건 검증 회차 / Batch Run 상태 모델

## 결정 요약

VOC 품질진단의 실행 단위는 개별 테스트케이스가 아니라 `Run ID`로 식별되는 검증 회차다.

35건 통합 카탈로그(`quality_test_catalog.json`)를 기준으로 한 회차를 만들고, 회차 안에서 각 Case가 실행·미실행·검토·오류 상태를 가진다. `test_cases.json`은 기존 20건 실행 상세를 위한 호환 파일로 유지하지만, 신규 관리 기준은 35건 통합 카탈로그다.

## 1. 상태 모델

### Run lifecycle

| 상태 | 의미 |
|---|---|
| `RUNNING` | 회차가 백그라운드에서 진행 중 |
| `COMPLETED` | 선택된 Case 처리가 정상 종료됨. 단, Case 결과에 `REVIEW_REQUIRED`나 `NOT_RUN`이 있을 수 있음 |
| `ERROR` | 회차 엔진 자체가 오류로 종료됨 |
| `INTERRUPTED` | 사용자가 중지를 요청했거나 중간 종료됨 |

### Case execution status

| 상태 | 의미 | 후속 액션 |
|---|---|---|
| `PASS` | 실행과 자동/독립 평가가 통과됨 | 타당성 검증 또는 승인 단계로 진행 가능 |
| `REVIEW_REQUIRED` | 실행은 완료됐지만 자동 판정만으로 결론을 내리기 어려움 | Judge 또는 사람 검토 필요 |
| `FAIL` | 기준 미충족 | 결함/개선 대상으로 분류 |
| `ERROR` | Agent, API, timeout, 환경 문제로 유효한 결과 생성 실패 | 오류 원인 조치 후 재실행 |
| `NOT_RUN` | 선택되지 않았거나 후속 구현/중지로 실행하지 않음 | 구현 또는 다음 회차 실행 |

### 독립 Judge 상태

`PASS`, `FAIL`, `REVIEW_REQUIRED`, `ERROR`, `NOT_RUN`을 사용한다.

### 개선안 타당성 상태

자동 평가는 `AI_PASS`, `AI_REVIEWED`, `REVISION_REQUIRED`, `ERROR`, `NOT_RUN`을 사용하고, 사람 승인 workflow는 `DRAFT → AI_REVIEWED → QA_REVIEWED → BUSINESS_APPROVED` 흐름을 기본으로 한다.

## 2. 35건 카탈로그 기준

현재 35건은 다음처럼 나뉜다.

| 구분 | 건수 | 처리 방식 |
|---|---:|---|
| VOC Pipeline Case | 18 | A2A Agent Pipeline 실행 |
| 장애 Proxy Case | 2 | Fault runner 실행 |
| 격리 장애 Case | 6 | Fault runner 실행 |
| Agent 역할 품질 Case | 6 | 후속 구현 전까지 `NOT_RUN` |
| 품질 Gate Case | 3 | 후속 구현 전까지 `NOT_RUN` |

따라서 전체 35건을 일괄 실행하면 현재 초안 기준으로는 실행 가능 26건, 후속 구현 9건이다. 9건은 성공도 실패도 아니며 `NOT_RUN`으로 남겨야 한다.

## 3. 메뉴별 입력과 출력

### 일괄 TC 수행

입력:

- `quality_test_catalog.json`의 `cases[]`
- 선택된 `case_ids`
- 독립 Judge 설정
- timeout / retry 정책
- 재실행이면 `parent_run_id`

출력:

- `manifest.json`
- `summary.json`
- `cases/<case_id>/pipeline_result.json`
- `cases/<case_id>/trace.json`
- `cases/<case_id>/rule_result.json`
- Judge 사용 시 `cases/<case_id>/judge_result.json`

핵심 판단 기준:

- Run은 `run_id`가 소유한다.
- Case 상태는 `summary.case_results[]`에 누적한다.
- 후속 구현 대상은 `NOT_RUN`으로 기록한다.

### 수행 이력

입력:

- `reports/voc_quality_runs/index.json`
- 각 Run의 `manifest.json`, `summary.json`
- Case별 증적 파일

출력:

- Run 목록
- Run 상세
- Case별 증적 상세
- Run 증적 ZIP
- 실패/오류 Case의 `RETEST` 실행 요청

핵심 판단 기준:

- 이력은 결과를 변경하지 않는 조회 중심 메뉴다.
- `RUNNING` Run은 삭제하거나 자동 복구하지 않는다.
- 재실행 비교는 같은 catalog, 같은 rubric, 부모 Run 연결이 확인되는 경우에만 의미가 있다.

### 개선안 타당성 검증

입력:

- 완료된 VOC Pipeline Case
- `pipeline_result.json`
- `trace.json`
- `judge_result.json`
- `improvement_validity_rubric.json`

출력:

- `validity_result.json`
- `summary.case_results[].validity_status`
- `summary.validity_state`
- `summary.deployment_decision`
- `human_reviews[]`

핵심 판단 기준:

- 타당성 검증 대상은 “성공적으로 실행된 VOC Pipeline 결과”다.
- 격리 장애 Case, Agent 역할 품질 Case, 품질 Gate Case는 개선안 타당성 대상이 아니다.
- `AI_PASS`이고 즉시 보류 규칙이 없어야 QA 검토로 넘어간다.
- 최종 배포 가능 상태는 AI 판정만으로 확정하지 않고 QA/업무 승인까지 필요하다.

## 4. 코드 반영 위치

| 파일 | 역할 |
|---|---|
| `dashboard/services/voc_quality_state_model.py` | 상태 모델, 메뉴별 입출력, 35건 회차 범위 계산 |
| `dashboard/services/voc_quality_service.py` | Batch Run 시작/진행 조회 시 상태 모델 메타데이터 기록 |
| `dashboard/services/voc_run_store.py` | Run manifest/summary에 state model version 보존 |
| `tests/test_voc_quality_integration.py` | 35건 회차 모델과 Run 메타데이터 검증 |

## 5. 다음 Step 제안

다음 단계는 수행 이력 화면에서 `verification_scope`를 시각적으로 보여주는 것이다.

추천 표시:

- 전체 선택 건수
- 실행 가능 건수
- 후속 구현으로 `NOT_RUN` 예정인 건수
- execution type별 구성
- `RETEST`이면 부모 Run과 비교 가능 여부

이렇게 하면 사용자는 “오늘의 Run이 35건 전체 검증인지, 일부 재실행인지, 왜 9건이 NOT_RUN인지”를 이력 화면에서 바로 이해할 수 있다.
