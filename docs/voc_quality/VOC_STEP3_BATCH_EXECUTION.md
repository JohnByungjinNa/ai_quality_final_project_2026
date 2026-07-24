# Step 3. 테스트케이스 일괄 실행

## 상태

- 상태: `COMPLETE`
- 구현일: 2026-07-16
- 사용자 승인일: 2026-07-16
- 선행 Step: Step 2 `COMPLETE`
- 다음 Step: Step 4 `USER_REVIEW`

## 1. 구현 범위

- `홈 > VOC 품질진단 > 일괄 TC 수행` 메뉴 등록
- 전체 35건·그룹·개별 Case 다중 선택
- 런타임 필수 파일과 6개 Agent 실행 전 점검
- 기본 순차 실행과 Case별 즉시 증적 저장
- 전체 진행률과 `REVIEW_REQUIRED`, `FAIL`, `ERROR`, `NOT_RUN` 집계
- 현재 Case 완료 후 안전하게 멈추는 사용자 중지
- 실패·오류 Case만 새 `RETEST` Run으로 재실행
- timeout·429 등 일시 오류의 지수 backoff와 최대 재시도
- 동일 Case 조합의 동시 중복 실행 차단
- 재시도별 시작·종료·성공·일시 오류·응답을 `attempts`로 보존

## 2. 35건 실행 정책

현재 카탈로그 35건의 구현 상태는 다음과 같다.

- 즉시 실행 가능: 26건
  - VOC 기능 Case 20건
  - 격리 장애 Case 6건
- 후속 단계 구현 대상: 9건
  - Agent 역할 품질 Case 6건
  - 품질 게이트 Case 3건

후속 구현 9건은 성공으로 간주하지 않고 `NOT_RUN`으로 저장한다. Step 5 독립 LLM Judge와 Step 6 개선안 타당성 검증이 구현된 뒤 실행 가능한 품질 게이트로 전환한다.

Pipeline 실행이 성공한 26건도 자동 100점 평가 전에는 `PASS`가 아니라 `REVIEW_REQUIRED`로 저장한다.

## 3. 실행·재시도 정책

- 실행 방식: `SEQUENTIAL`
- 기본 Case timeout: 180초
- 기본 재시도: 최초 실행 외 최대 2회
- 재시도 대상: 429, rate limit, timeout, `DEADLINE_EXCEEDED`
- backoff: 1초, 2초 순서의 지수 증가
- 비일시 오류: 즉시 `ERROR`
- 사용자 중지: 현재 Case 종료 후 남은 Case를 `NOT_RUN`, Run을 `INTERRUPTED`
- 재실행: 실패·오류 Case만 선택하고 원본 Run ID를 `parent_run_id`로 저장

## 4. 저장 증적

Run manifest의 `run_metadata`에 다음을 저장한다.

- 원본 Run ID
- 순차 실행 정책
- timeout
- 최대 재시도 횟수
- backoff 정책

각 Case의 `pipeline_result.json`에는 모든 실행 시도의 상태와 최종 실행 결과를 저장한다. 진행 중에도 `summary.json`을 원자적으로 갱신하므로 화면 새로고침과 앱 재시작 후 부분 결과를 확인할 수 있다.

## 5. 자동 검증 결과

- VOC 통합 테스트: 27 PASS
- 35건 전체 모의 실행: 26 `REVIEW_REQUIRED` / 9 `NOT_RUN` / 0 `ERROR`
- 429 후 2번째 시도 성공 및 시도 이력 보존: PASS
- timeout 재시도 소진 후 `ERROR`: PASS
- 실행 전 사용자 중지와 3건 `NOT_RUN`: PASS
- 동일 Case 조합 중복 실행 차단: PASS
- 실패 재실행의 `RETEST` 유형과 부모 Run 연결: PASS
- Python 문법 검사: PASS
- 실제 대표 일괄 실행: `TC-01`, `FT-06` 2건 모두 `REVIEW_REQUIRED`, Run `COMPLETED`
- 실제 Run ID: `RUN-20260716-103313-987145-b692`
- 전체 회귀 테스트: 188 PASS / 기존 qa-observer Prometheus 집계 메트릭 결함 6 FAIL
- Step 3 신규 실패: 없음

## 6. 사용자 확인 방법

1. 앱에서 `홈 > VOC 품질진단 > 일괄 TC 수행`으로 이동한다.
2. `개별 선택`에서 대표 Case 2~3건을 선택한다.
3. 사전 점검에서 런타임과 Agent 6/6 상태를 확인한다.
4. 순차 실행 후 진행률, Case 상태, Run ID와 증적 위치를 확인한다.
5. 필요하면 실행 중지를 눌러 남은 Case가 `NOT_RUN`인지 확인한다.
6. 전체 35건 선택 시 후속 구현 9건 안내 문구를 확인한다.

## 7. Step 3 승인 요청

- 선택 방식과 사전 점검 정보가 충분한지
- 성공 실행을 자동 채점 전 `REVIEW_REQUIRED`로 표시하는 방식
- 후속 구현 9건을 `NOT_RUN`으로 표시하는 방식
- 중지·재시도·실패 재실행 정책
- 실제 26건 전체 실행을 지금 수행할지, Step 5~6 이후 최종 35건 실행 때 수행할지

2026-07-16 사용자 승인으로 Step 3을 `COMPLETE`로 전환하고 Step 4 수행 이력 관리로 진행했다. 후속 구현 9건은 `NOT_RUN` 정책을 적용하며, 사용자가 전체 35건 Run을 시작해 실행 가능 26건을 순차 수행 중이다.
