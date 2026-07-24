# Step 2. VOC 실행 세션·수행 이력 저장 기반

## 상태

- 상태: `COMPLETE`
- 구현일: 2026-07-16
- 사용자 승인일: 2026-07-16
- 선행 Step: Step 1 `COMPLETE`
- 다음 Step: Step 3 `USER_REVIEW`

## 1. 구현 범위

- 충돌 방지 Run ID 생성
- Run 시작 시 `RUNNING` manifest 선저장
- Run별 manifest·summary·defects 원자적 저장
- case별 Pipeline 결과·Trace·품질 판정 파일 저장
- 중앙 `index.json` 원자적 갱신과 손상 시 재구축
- 앱 재시작 후 미완료 Run을 `INTERRUPTED`로 복구
- TC·Catalog·Rubric·모델·Prompt source hash 스냅샷
- API 키·이메일·전화번호·주민번호 패턴 마스킹
- index에서 전체 질문과 전체 응답 제외
- Run ID와 저장 상태를 수동 TC 수행 결과에 표시

## 2. 저장 구조

```text
reports/voc_quality_runs/
  index.json
  <run_id>/
    manifest.json
    summary.json
    defects.json
    cases/<case_id>/
      pipeline_result.json
      trace.json
      rule_result.json
    snapshots/
      selected_test_cases.json
      quality_test_catalog.json
      quality_evidence_contract.json
      model_snapshot.json
      prompt_snapshot.json
      rubrics/
        system_quality_rubric.json
        independent_judge_rubric.json
        improvement_validity_rubric.json
```

## 3. 상태 계약

Run lifecycle:

- `RUNNING`: 실행 시작 후 결과 저장 전
- `COMPLETED`: 실행이 종료되고 필수 파일이 저장됨
- `ERROR`: 실행 또는 저장 오류로 정상 완료되지 못함
- `INTERRUPTED`: 앱 재시작 시 완료되지 않은 이전 Run을 복구함

Case quality status:

- `PASS`, `FAIL`, `ERROR`, `NOT_RUN`, `REVIEW_REQUIRED`
- 현재 수동 TC는 Pipeline 성공 후에도 자동 100점 채점 전이므로 `REVIEW_REQUIRED`로 저장한다.
- Pipeline 자체가 실패하면 `ERROR`, 자동 채점은 `NOT_RUN`으로 분리한다.

## 4. 버전·무결성 스냅샷

manifest에는 다음 값을 저장한다.

- suite ID와 catalog version
- 전체 35건 정의의 SHA-256
- 선택 case ID
- 내부 Pipeline·독립 LLM Judge·개선안 타당성 Rubric 버전과 SHA-256
- 생성 모델 Provider·모델명과 자격 증명 설정 여부
- Judge 활성 여부
- Python·운영체제 기반 환경 fingerprint

Prompt 원문을 index에 복제하지 않고 6개 Agent와 실행 진입 파일의 SHA-256을 `prompt_snapshot.json`에 저장한다.

## 5. 보호·보존 정책

- API 키·token 값과 인증정보는 저장 전에 마스킹한다.
- 이메일, 휴대전화, 주민번호 패턴은 Run 증적에서 마스킹한다.
- 중앙 index에는 전체 질문과 전체 LLM 응답을 저장하지 않는다.
- 기본 Run 180일, 정식 배포 증적 1,095일, 미완료 Run 30일 보존을 기준으로 한다.
- 자동 삭제는 사용하지 않는다. Step 4에서 사용자 명시 삭제 시 Run 폴더와 index를 함께 갱신한다.

## 6. 실제 수동 TC 증적

- Case: `TC-01`
- Run ID: `RUN-20260716-100912-880955-d634`
- Pipeline 실행: 성공
- Run lifecycle: `COMPLETED`
- Case 상태: `REVIEW_REQUIRED`
- manifest 필수 필드: 12/12
- 필수 Run·case 파일: 6/6
- 스냅샷 JSON: 8개
- index 전체 질문·응답·비밀값 포함: 0건

`REVIEW_REQUIRED`는 실행 실패가 아니다. Step 5 이전에는 독립 Judge와 자동 100점 평가가 없으므로 사람 검토가 남아 있음을 표현한다.

## 7. 검증 결과

- Python 문법 검사: PASS
- VOC 통합 테스트: 21 PASS
- 수동 TC 정상·격리 장애 저장: PASS
- Run ID 연속 생성 충돌 없음: PASS
- 앱 재시작 모의 미완료 Run 복구: PASS
- 손상 manifest index 노출: PASS
- 안전하지 않은 snapshot 경로 차단: PASS
- API 키·이메일·전화번호 마스킹: PASS
- 품질 계약 validation 3단계: PASS
- 전체 회귀 테스트: 182 PASS / 기존 qa-observer Prometheus 집계 메트릭 결함 6 FAIL
- Step 2 신규 실패: 없음

## 8. 후속 Step과 범위 구분

- Step 3: 여러 TC·전체 35건 일괄 실행
- Step 4: 수행 이력 화면, 필터·상세·삭제·A/B 비교
- Step 5: 독립 LLM Judge 실제 판정 파일 추가
- Step 6: 개선안 타당성·사람 승인 파일 추가
- Step 8: TXT·XML·HTML 최종 증적과 보고서 생성
- 화면 디자인 일괄 정리는 전체 기능 흐름 완성 후 수행

## 9. 사용자 검토 항목

1. `reports/voc_quality_runs` 저장 위치
2. Run lifecycle과 Case quality status 분리 방식
3. 성공한 수동 실행을 자동 채점 전 `REVIEW_REQUIRED`로 표시하는 방식
4. 기본 180일·정식 증적 1,095일·미완료 30일 보존 정책

2026-07-16 사용자 승인으로 Step 2를 `COMPLETE`로 전환하고 Step 3을 시작했다.
