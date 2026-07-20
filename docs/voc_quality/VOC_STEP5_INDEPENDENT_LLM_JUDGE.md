# Step 5. 독립 LLM Judge

## 상태

- 상태: `COMPLETE`
- 구현일: 2026-07-16
- 승인일: 2026-07-16
- 선행 Step: Step 4 `COMPLETE`
- 다음 Step: Step 6 `USER_REVIEW`

## 1. 구현 범위

- 수동 TC와 일괄 TC에서 Judge 사용 여부 선택
- Anthropic·OpenAI Provider와 모델명 선택
- Pipeline 성공 후 별도 Judge 호출 세션 수행
- 독립 LLM Judge 100점 Rubric과 고정 JSON 출력 계약
- 차원별 점수 범위·PASS 하한·즉시 FAIL 규칙 검증
- 모델이 반환한 total·decision을 신뢰하지 않고 서버가 재계산
- malformed JSON·timeout·429·인증 오류 분리 처리
- 429·timeout 지수 backoff와 시도별 이력 저장
- Judge ERROR와 Pipeline 성공 상태 분리
- Provider·모델·Rubric·Prompt hash·token·시간·비용 설정 상태 저장
- Case별 `judge_result.json`과 Run `judge_counts` 저장
- 저장된 동일 Pipeline 결과 Judge 재평가와 이전 평가 이력 보존
- 수행 이력에서 Judge 증적 조회와 재평가

## 2. 판정 계약

평가 차원:

- 정확성 25점
- 근거성 25점
- 충실성 20점
- 구체성 15점
- 안전성 15점

서버 판정:

- 즉시 FAIL 규칙 발생 또는 65점 미만: `FAIL`
- 80점 이상이며 모든 차원 PASS 하한 충족: 점수 기준 `PASS`
- 그 외: `REVIEW_REQUIRED`
- API·timeout·429 소진·인증·JSON 오류: Judge `ERROR`
- Judge 미선택·Pipeline 실패·격리 장애 Case: Judge `NOT_RUN`

Judge가 응답에 임의 total 또는 decision을 넣어도 차원 점수로 다시 계산한다.

## 3. 독립성 등급과 보류

- `A`: 최종 개선안 생성 Provider와 Judge Provider가 다름
- `B`: Provider는 같지만 모델·Judge Prompt·호출 세션이 다름
- `C`: 같은 Provider·모델로 편향 위험이 높음

독립성 `C`에서 점수 기준 PASS가 나오면 `rubric_decision=PASS`는 보존하지만 유효 판정은 `REVIEW_REQUIRED`로 강제한다.

현재 환경의 기본 구성:

- 최종 개선안 생성: Anthropic `claude-sonnet-4-6`
- 기본 Judge: Anthropic `claude-opus-4-6`
- 예상 독립성: `B`

모델 선택 목록은 고정하지 않고 사용자가 계정에서 사용 가능한 모델명을 입력할 수 있다.

## 4. 오류·재시도 정책

- Judge timeout: 기본 90초
- Judge 최대 재시도: 최초 실행 외 2회
- 재시도: 429, rate limit, timeout, overloaded
- 즉시 종료: 인증 오류, 정의되지 않은 응답, malformed JSON
- 모든 시도: 시작·종료·상태·오류 유형 저장
- Pipeline 성공 후 Judge ERROR: Pipeline을 ERROR나 PASS로 위장하지 않고 Case `REVIEW_REQUIRED`, Judge `ERROR`로 분리

## 5. 비용 기록

- 입력·출력 token은 Provider 응답에서 저장한다.
- 호출 시간과 시도 횟수를 저장한다.
- 확인되지 않은 가격을 코드에 고정하지 않는다.
- KRW/백만 token 환경변수가 설정되면 비용을 계산한다.
- 가격 미설정 시 `amount=null`, `pricing_status=NOT_CONFIGURED`로 명시한다.

## 6. 실제 실행 증적

- Case: `TC-01`
- Run ID: `RUN-20260716-114106-738918-3dbb`
- Pipeline: 성공
- 첫 Judge 호출: 출력 2,500 token 절단으로 malformed JSON `ERROR`
- 출력 제한 보완: reason 300자, 배열 최대 5개·항목 200자, 최대 출력 4,096 token
- 동일 Sonnet 모델 재평가: 86점, 점수 기준 PASS, 독립성 C로 `REVIEW_REQUIRED`
- 다른 Anthropic Opus 모델 재평가: 86점 `PASS`, 독립성 B
- 최종 모델: `claude-opus-4-6`
- 최종 token: 입력 6,954 / 출력 2,359
- 최종 시도: 1회 성공
- 가격표 설정: 없음, 비용 미산정 상태를 명시
- 이전 평가 이력: 3건 보존
- 최종 Run·Judge 무결성: PASS

## 7. 검증 결과

- Judge·VOC 대상 테스트: 47 PASS
- 100점 서버 재계산과 모델 total 무시: PASS
- 차원 PASS 하한·즉시 FAIL: PASS
- 독립성 A·B·C와 C 강제 보류: PASS
- malformed JSON 별도 ERROR: PASS
- 429 재시도 성공·timeout 소진·인증 즉시 종료: PASS
- Judge 비활성 `NOT_RUN`: PASS
- Judge ERROR와 Pipeline 성공 분리: PASS
- 일괄 VOC PASS·격리 장애 NOT_RUN 집계: PASS
- 동일 결과 재평가·이전 결과 보존: PASS
- Streamlit Judge Provider·모델 선택 화면: 예외 0건
- 품질 계약 검증: PASS
- 전체 회귀: 208 PASS / 기존 qa-observer Prometheus 집계 메트릭 결함 6 FAIL
- Step 5 신규 실패: 없음

## 8. 사용자 확인 방법

1. `수동 TC 수행`에서 `독립 LLM Judge 평가`를 켠다.
2. Anthropic과 `claude-opus-4-6`을 선택한다.
3. 실행 후 Judge 점수·판정·독립성·모델을 확인한다.
4. `일괄 TC 수행`에서 Judge를 켜고 소규모 VOC Case를 실행해 Judge 집계를 확인한다.
5. `수행 이력 > Case 증적`에서 `judge_result`와 평가 이력을 확인한다.
6. 같은 Case의 저장된 Pipeline 결과를 다른 모델로 재평가해 이전 결과가 유지되는지 확인한다.

## 9. Step 5 승인 요청

- Anthropic Opus를 기본 Judge로 두는 방식
- 다른 Provider·모델을 사용자가 입력하는 방식
- 독립성 C의 점수 PASS를 사람 검토로 강제 보류하는 방식
- Judge ERROR와 Pipeline 성공을 별도로 집계하는 방식
- token은 기록하되 검증된 가격표가 없으면 비용을 미산정으로 표시하는 방식

위 항목 승인 후 Step 5를 `COMPLETE`로 전환하고 Step 6 개선안 타당성 검증을 시작한다.
