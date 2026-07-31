# Step 8. 품질 보고서와 시각화

## 상태

- 상태: `COMPLETE`
- 구현일: 2026-07-16
- 사용자 승인일: 2026-07-16
- 선행 Step: Step 7 `COMPLETE`
- 다음 Step: Step 9 `USER_REVIEW`

## 1. 구현 목적

수행 이력의 manifest·summary·Case 증적·Judge·타당성·결함 원장을 자동 대조해 재현 가능한 품질 보고서를 생성한다. 기획 문구인 `초기 33 PASS / 2 FAIL → 최종 35 PASS`는 실제 연결 Run이 확인될 때만 성과로 표시하며, 현재처럼 증적이 없으면 보고서 생성 자체를 거짓 완료로 만들지 않고 `EVIDENCE_DRAFT / NOT_APPROVED`로 명확히 표시한다.

## 2. 메뉴와 화면

`홈 > VOC 품질진단 > 품질 보고서`에서 다음을 제공한다.

- 최종 품질 보고서: 35건 전체 정식 승인 완료 Run만 보고 대상 Run으로 표시
- 증적 초안: 승인 전 Run의 누락 평가와 보완 위치 확인
- 운영 진단 산출물: 기존 Summary·Validation·Fault·A2A·VOC 분석 원본을 접힌 보조 영역에서 조회
- 3단계 품질평가 요약
- 전체 테스트 상태와 그룹별 점검 범위
- 33/2 기준선과 35 PASS 최종 수치 자동 대조
- 결함 상태와 잔여 위험·운영 권고
- Evaluator·Critic·독립 Judge 역할과 산식
- TXT·JUnit XML·HTML 생성 및 다운로드

페이지 상단 중복 제목과 별도 CSS를 추가하지 않고 Streamlit 기본 metric·container·chart·dataframe을 사용했다.

## 3. 보고서 구성

기본 증적 템플릿에는 다음 항목을 포함한다.

1. VOC 분석 및 정책 개선안 생성
2. 6개 멀티 에이전트 내부 품질진단과 Trace 집계
3. 독립 LLM Judge 평가 건수와 판정
4. 전체 35건 정량 분석과 점검 범위
5. 초기 33 PASS / 2 FAIL에서 최종 35 PASS 개선 주장 검증
6. 분기 인터페이스 오류와 API 429 후보 결함 상태
7. Evaluator·Critic과 독립 Judge 역할 구분
8. 성공적인 품질평가 판단 방식
9. 잔여 위험과 운영 권고
10. 최종 완료 판정
11. 상태 분포, 점검 범위, 결함과 위험 원본 데이터·산식

사용자가 별도 보고서 양식을 제공하면 공통 report model은 유지하고 HTML 표현 템플릿을 교체한다.

## 4. 수치 대조와 판정 규칙

- 상태별 건수는 Case `summary.status`를 직접 집계한다.
- 35건 범위는 Catalog의 정확한 35개 Case ID 집합과 비교한다.
- 기준선은 `33 PASS / 2 FAIL / 기타 0건`이어야 한다.
- 기준선에는 분기 인터페이스 오류와 API 429 결함 링크가 있어야 한다.
- 최종은 `35 PASS / 기타 0건`이어야 한다.
- 기준선과 최종은 suite·Catalog version·TC hash·Rubric·Case 범위가 같아야 한다.
- 위 조건이 하나라도 다르면 개선 주장은 `NOT_VERIFIED`이다.
- 정식 승인은 35 PASS, Judge 35 PASS, 타당성 `BUSINESS_APPROVED` 35건, 미종결 High·Critical 0건을 모두 요구한다.

## 5. 현재 실제 35건 Run 판정

- Run ID: `RUN-20260716-110130-319110-c8fe`
- 실제 결과: 1 PASS / 0 FAIL / 2 ERROR / 23 REVIEW_REQUIRED / 9 NOT_RUN
- 기준선 Run: 연결 없음
- `33 PASS / 2 FAIL → 35 PASS`: `NOT_VERIFIED`
- 보고서 상태: `EVIDENCE_DRAFT`
- 최종 판정: `NOT_APPROVED`

이 결과는 실패가 아니라 현재 증적 수준을 정직하게 나타낸 것이다. 정식 품질 완료나 35건 성공으로 발표할 수 없다.

## 6. 산출물

다음 파일을 동일 report model에서 생성했다.

- `reports/voc_quality_runs/RUN-20260716-110130-319110-c8fe/evidence/result.txt`
- `reports/voc_quality_runs/RUN-20260716-110130-319110-c8fe/evidence/junit.xml`
- `reports/voc_quality_runs/RUN-20260716-110130-319110-c8fe/evidence/report.html`
- `reports/voc_quality_runs/RUN-20260716-110130-319110-c8fe/evidence/report_model.json`
- `reports/voc_quality_runs/RUN-20260716-110130-319110-c8fe/evidence/report_manifest.json`

manifest에는 TXT·XML·HTML의 SHA-256과 공통 상태 집계를 기록한다.

## 7. 검증 결과

- TXT·XML·HTML 공통 상태 수치 일치: PASS
- JUnit tests·failures·errors·skipped 집계: PASS
- 파일 저장 및 report manifest 생성: PASS
- 기준선 없는 33/2→35 주장 차단: PASS
- 동일 35 Case·버전·해시·Rubric·결함 링크가 있는 모의 기준선/최종 쌍만 개선 주장 허용: PASS
- 개선 주장이 검증돼도 Judge·업무 승인 미충족 시 정식 승인 차단: PASS
- Streamlit 품질 보고서 화면: 예외 0건
- Step 8·VOC 대상 테스트: 40 PASS

## 8. 사용자 확인 방법

1. `홈 > VOC 품질진단 > 품질 보고서`로 이동한다.
2. 기본 선택된 35건 Run의 실제 상태가 1 PASS / 2 ERROR / 23 REVIEW_REQUIRED / 9 NOT_RUN인지 확인한다.
3. `초기 33 PASS / 2 FAIL → 최종 35 PASS`가 `NOT_VERIFIED`로 차단되는지 확인한다.
4. PENDING 결함 2건과 잔여 위험·운영 권고를 확인한다.
5. `TXT·XML·HTML 증적 생성`을 누르고 세 파일을 내려받는다.
6. HTML 미리보기 구성과 TXT 문구, JUnit XML 집계가 같은지 확인한다.
7. 운영 진단 산출물 보기 영역에서 기존 Summary·Validation·Fault·A2A·VOC 분석 원본 조회 기능이 유지되는지 확인한다.

## 9. Step 8 승인 결과

- 현재 실측 수치와 `EVIDENCE_DRAFT / NOT_APPROVED` 판정이 타당한지 확인한다.
- 보고서의 11개 구성 항목, 차트·표·잔여 위험 문구를 검토한다.
- TXT·JUnit XML·HTML 중 실제 제출에 사용할 형식을 결정한다.
- 이전에 예고한 보고서 템플릿이 있으면 제공한다. 없으면 기본 증적 템플릿 사용을 승인할 수 있다.
- 33/2 기준선과 35 PASS 증적은 현재 없으므로 후속 실제 실행 전까지 발표 성과에서 제외하는 정책을 승인한다.

사용자가 2026-07-16 Step 8을 승인했으며, Step 9 README 매뉴얼과 사용자 가이드로 진행했다. 실제 제출 형식과 별도 보고서 템플릿은 후속 검토에서 변경할 수 있다.
