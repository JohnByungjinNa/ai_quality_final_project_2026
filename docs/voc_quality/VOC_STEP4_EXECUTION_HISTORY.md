# Step 4. VOC 수행 이력 관리

## 상태

- 상태: `COMPLETE`
- 구현일: 2026-07-16
- 사용자 승인일: 2026-07-16
- 선행 Step: Step 3 `COMPLETE`
- 다음 Step: Step 5 `USER_REVIEW`

## 1. 구현 범위

- `홈 > VOC 품질진단 > 수행 이력` 메뉴
- 실행 기간·lifecycle·실행 유형·Judge·Case ID 필터
- Run ID·실행 시각·유형·상태·대상·완료·진행률·품질 상태 목록
- 실행 중인 Run을 포함한 수동·일괄·재시험 통합 조회
- 선택 Run의 manifest·Case 결과·Case별 Pipeline·Trace·Rule 증적 조회
- Run 전체 증적 ZIP 다운로드
- Run 폴더·Case 증적·summary 집계·중앙 index 무결성 점검
- 완료 Run 선택 삭제와 index 동시 갱신
- 실행 중 Run 삭제 차단
- 원본 Run과 연결된 RETEST Run의 재시험 전후 비교

## 2. A/B 비교 판단

Step 4에서 임의의 두 Run을 A/B 비교하는 방식은 적용하지 않는다. 모델·TC·Rubric·질문 범위가 다른 Run을 비교하면 개선 효과로 오해할 수 있기 때문이다.

Step 4의 비교는 다음 조건을 만족하는 `재시험 전후 비교`로 제한한다.

- 후보 Run 유형이 `RETEST`
- 후보 Run의 `parent_run_id`가 원본 Run ID와 일치
- suite ID, Catalog version, 전체 TC hash가 일치
- 적용 Rubric version과 hash가 일치
- 재시험 Case가 원본 Run Case의 부분집합

화면에는 Case 상태 변화, 시도 횟수 변화, 상태별 건수 차이만 표시한다. 위 조건이 다르면 비교를 차단한다.

기존 답변과 개선 답변의 실제 A/B 평가는 Step 6에서 구현한다. 이때는 동일 질문·동일 TC·동일 Rubric을 잠그고 독립 LLM Judge 점수, 개선안 타당성, 안전성, 근거성을 비교한다.

## 3. 실행 중 Run 보호

이력 조회 시 자동 복구를 수행하지 않는다. Streamlit 실행 프로세스와 이력 조회 프로세스가 다를 때 정상 `RUNNING` Run을 `INTERRUPTED`로 오판할 수 있기 때문이다.

- 목록 조회: 읽기 전용
- 실행 중 Run: 상세·부분 결과·무결성 경고 조회 가능
- 실행 중 Run 삭제: 차단
- 불완전 Run 복구: 사용자가 명시한 복구 흐름에서만 수행

## 4. 성공률 표시 원칙

- `REVIEW_REQUIRED`는 실행 완료지만 품질 PASS가 아니다.
- PASS와 FAIL 판정이 한 건도 없으면 성공률을 계산하지 않는다.
- 실행 진행률과 품질 성공률을 분리한다.
- Judge와 배포 판정이 아직 없으면 각각 `미사용`, `미판정`으로 표시한다.

## 5. 검증 결과

- VOC 통합 테스트: 33 PASS
- Streamlit 수행 이력 페이지 렌더링: 예외 0건
- 다른 프로세스의 RUNNING Run 비변경 조회: PASS
- Run 폴더·index·Case 증적 무결성 검사: PASS
- ZIP 증적 생성: PASS
- 완료 Run 삭제와 index 동기화: PASS
- 실행 중 Run 삭제 차단: PASS
- 부모 Run·버전이 일치하는 RETEST 비교: PASS
- REVIEW_REQUIRED를 성공률로 오인하지 않음: PASS
- 전체 회귀: 194 PASS / 기존 qa-observer Prometheus 집계 메트릭 결함 6 FAIL
- Step 4 신규 실패: 없음

## 6. 사용자 확인 방법

1. `홈 > VOC 품질진단 > 수행 이력`으로 이동한다.
2. 현재 실행 중인 35건 Run의 진행률과 부분 결과가 표시되는지 확인한다.
3. 완료 Run 행을 선택해 Case 결과·실행 정보·Case 증적을 조회한다.
4. Run 전체 증적 ZIP을 내려받아 manifest와 Case 파일을 확인한다.
5. 삭제 확인은 테스트용 Run으로만 수행하고 실행 중 Run의 삭제 버튼이 비활성인지 확인한다.
6. 실패·오류 재실행으로 RETEST가 생성되면 재시험 전후 비교를 확인한다.

## 7. Step 4 승인 요청

- 이력 목록 필드와 필터가 충분한지
- 상세·Case 증적·ZIP 다운로드 구성이 적절한지
- 실행 중 Run 삭제 차단과 완료 Run 영구 삭제 방식
- 임의 A/B 대신 연결된 RETEST만 비교하는 정책
- 실제 답변 A/B 비교를 Step 6으로 이동하는 정책

2026-07-16 사용자 승인으로 Step 4를 `COMPLETE`로 전환하고 Step 5 독립 LLM Judge를 시작했다.
