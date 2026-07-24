# Step 6. 최종 개선안 타당성 검증

## 상태

- 상태: `COMPLETE`
- 구현일: 2026-07-16
- 사용자 승인일: 2026-07-16
- 선행 Step: Step 5 `COMPLETE`
- 다음 Step: Step 7 `USER_REVIEW`

## 1. 구현 범위

- `홈 > VOC 품질진단 > 개선안 타당성 검증` 메뉴
- 완료된 VOC Pipeline의 Run·Case 선택
- 개선안 타당성 100점 Rubric 기반 AI 자동 평가
- 독립 Judge 결과, VOC 질문, 요약, 정책 개선안, Trace, 결함을 함께 평가
- 차원별 점수·사유, 근거, 위험, 보완 권고 저장
- QA 검토와 업무 담당자 승인의 순차 워크플로
- 승인·보완 요구·반려와 검토자·시각·의견 감사 이력
- 동일 질문·TC·Catalog·Rubric이며 부모 Run에 연결된 RETEST만 실제 A/B 비교
- 수행 이력과 `validity_result.json` 연계

## 2. 자동 평가 기준

| 평가 차원 | 배점 | PASS 하한 |
|---|---:|---:|
| 불만 원인과 개선안 연결 | 25 | 18 |
| VOC·Trace 근거 추적성 | 20 | 14 |
| 업무·기술 실행 가능성 | 20 | 14 |
| 담당·일정·KPI 구체성 | 20 | 14 |
| 위험·보안·규제 고려 | 15 | 10 |
| 합계 | 100 | - |

서버 판정:

- 80점 이상, 모든 차원 하한 충족, 즉시 보류 없음: `AI_PASS`
- 65점 이상이지만 PASS 조건 미충족: `REVISION_REQUIRED`
- 65점 미만: `REJECTED`
- API·timeout·인증·JSON 오류: `ERROR`

모델이 반환하는 총점과 최종 판정은 신뢰하지 않고 서버가 차원 점수로 다시 계산한다.

## 3. 즉시 승인 보류

- VOC 또는 Trace 근거 누락
- 안전하지 않거나 규정에 맞지 않는 개선 조치
- 미종결 High·Critical 결함
- 독립 Judge ERROR·NOT_RUN·비PASS
- 기준 답변보다 안전성이 하락한 개선안

점수가 80점 이상이어도 보류 규칙이 하나라도 있으면 `AI_PASS`가 될 수 없다.

## 4. 사람 승인 워크플로

`DRAFT → AI_REVIEWED → QA_REVIEWED → BUSINESS_APPROVED`

- `AI_PASS`만으로 정식 운영 승인하지 않는다.
- QA 검토는 `AI_REVIEWED`에서만 한 번 수행할 수 있다.
- 업무 담당자 승인은 `QA_REVIEWED` 이후에만 수행할 수 있다.
- 시연에서는 동일한 한 사람이 QA와 업무 담당자 역할을 모두 수행할 수 있다. 같은 사용자라도 역할·검토 시각·의견은 두 건의 독립 감사 기록으로 남긴다.
- QA 또는 업무 담당자는 승인 대신 `REVISION_REQUIRED` 또는 `REJECTED`를 선택할 수 있다.
- 검토자 역할·이름/ID·검토 시각·결정·의견·이전/다음 상태를 append-only로 저장한다.
- Run에 여러 Case가 있으면 모든 Case가 `BUSINESS_APPROVED`여야 Run을 정식 승인한다. 일부 승인만으로는 배포 승인하지 않는다.

## 5. A/B 비교 계약

다음 조건을 모두 만족할 때만 기존 답변 A와 개선 답변 B를 비교한다.

- 동일 `case_id`와 질문
- 동일 suite, Catalog version, TC hash
- 동일 개선안 타당성 Rubric version/hash
- B는 `RETEST`이고 A의 Run ID를 `parent_run_id`로 가짐

비교 화면에는 두 정책 개선안, 독립 Judge 점수·판정, 타당성 점수·판정, 승인 상태와 점수 변화를 함께 표시한다. 조건이 다르면 개선 효과로 해석하지 않고 비교를 차단한다.

사용자가 두 Run을 직접 조합하지 않는다. 기준 A를 선택한 뒤 `현재 Case 연결 재시험 실행`으로 B를 만들고, 완료된 연결 RETEST 중 하나만 선택하면 시스템이 `parent_run_id`로 A를 자동 연결한다.

## 6. 저장 증적

Case별 `validity_result.json`에 다음을 저장한다.

- Rubric·Provider·모델·Prompt hash
- 차원별 점수·사유와 서버 재계산 총점
- 즉시 보류 규칙, 근거, 위험, 권고
- token·시간·시도 이력과 비용 산정 상태
- 이전 자동 평가 이력
- QA·업무 담당자 사람 검토 이력
- 현재 workflow state와 정식 승인 여부

Run summary와 index에는 `validity_state`, `deployment_decision`, Case별 타당성 점수와 승인 상태를 반영한다.

## 7. 실제 검증 증적

- Run ID: `RUN-20260716-114106-738918-3dbb`
- Case: `TC-01`
- 독립 Judge: 86점 `PASS`, 독립성 B
- 타당성 평가 모델: Anthropic `claude-opus-4-6`
- 타당성 점수: 77점
- 자동 판정: `REVISION_REQUIRED`
- 승인 상태: `REVISION_REQUIRED`
- 즉시 보류 규칙: 없음
- 정식 운영 승인: `false`
- token: 입력 7,113 / 출력 1,970
- 비용: 검증된 단가 미설정으로 `NOT_CONFIGURED`

독립 Judge가 품질 PASS를 판정했더라도 담당·일정·KPI와 실행 타당성 기준이 충분하지 않아 자동 운영 승인되지 않는 것을 실제로 확인했다.

## 8. 검증 결과

- Step 6·Judge·VOC 대상 테스트: 52 PASS
- 서버 점수 재계산: PASS
- Trace·Judge·High 결함 즉시 보류: PASS
- 업무 선승인 차단: PASS
- QA 후 업무 순차 승인: PASS
- 검토자·의견 필수값 검증: PASS
- 승인 감사 이력과 수행 이력 집계: PASS
- Streamlit 타당성 검증 화면: 예외 0건
- 전체 회귀: 214 PASS / 기존 qa-observer Prometheus 집계 메트릭 결함 6 FAIL
- Step 6 신규 실패: 없음
- Streamlit 8501 health: 200

## 9. 사용자 검토 피드백 반영

- QA와 업무 승인 역할은 분리하되, 현재 시연에서는 동일인이 두 역할을 순차 수행하는 방식을 허용한다.
- `AI_PASS → QA_REVIEWED → BUSINESS_APPROVED` 순차 승인 정책은 사용자 승인 완료했다.
- 77점 Case의 보완 권고는 현재 사용자가 타당성을 확정할 수 없으므로 AI 검토 후보로만 유지하며 확정 결함·업무 지시로 취급하지 않는다.
- A/B 비교는 사용법이 어려워 기존의 A·B Run 수동 선택을 제거했다. 기준 A에서 연결 RETEST를 생성하고 B만 선택하는 안내형 흐름으로 보완했다.
- 승인 흐름은 기존 개선안을 임의 PASS 처리하지 않고 실제 `AI_PASS` Case에서 시험한다. 현재 평가된 TC-01은 77점, 추가 후보 TC-02는 재검증 75점이어서 승인 가능 후보가 아직 없다.
- TC-02 최초 평가 중 모델이 존재하지 않는 High 결함 보류 규칙을 선택한 사례를 발견했다. Trace·Judge·결함 보류는 서버만 판정하도록 제한했고, 재평가에서 보류 규칙 없음과 75점 `REVISION_REQUIRED`를 확인했다. 최초 잘못된 평가는 이력으로 보존했다.

## 10. 사용자 확인 방법

1. `홈 > VOC 품질진단 > 개선안 타당성 검증`으로 이동한다.
2. `RUN-20260716-114106-738918-3dbb · TC-01`을 선택한다.
3. 77점 `REVISION_REQUIRED`의 차원별 사유와 보완 권고를 확인한다.
4. `동일 조건 A/B 비교 보기`를 켜고 안내된 4단계 사용 순서를 확인한다.
5. 필요할 때 `현재 Case 연결 재시험 실행`으로 B를 만든다. 완료 후 B만 선택하면 A는 자동 연결된다.
6. 향후 실제 `AI_PASS` 대표 Case가 생기면 같은 사람이 QA와 업무 역할로 각각 검토 의견을 저장해 승인 흐름을 확인한다.

## 11. Step 6 승인 결과

- 같은 사람이 QA와 업무 역할을 각각 수행하는 시연 방식을 화면에서 확인한다.
- 77점 보완 권고는 미확정 상태로 보존하고 추후 전체 프로세스 이해 후 재검토한다.
- 보완된 안내형 A/B 흐름을 확인한다. 실제 재시험은 API 비용과 시간이 필요하므로 지금 실행하지 않아도 된다.
- 실제 `AI_PASS` Case가 생성되면 순차 승인 흐름을 시험한다.
- 위 보완 방식에 동의하면 Step 6 완료를 승인한다.

사용자가 2026-07-16 Step 6을 승인했으며, Step 7 장애·결함·재시험 수명주기로 진행했다.
