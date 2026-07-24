# Step 9. README 매뉴얼과 사용자 가이드

## 상태

- 상태: `COMPLETE`
- 구현일: 2026-07-16
- 선행 Step: Step 8 `COMPLETE`
- 승인일: 2026-07-16
- 다음 Step: Step 10 `USER_REVIEW`

## 1. 구현 목적

초기 개발 단계 설명과 오래된 메뉴·테스트 수치가 섞여 있던 루트 README를 현재 VOC 품질관리 운영 매뉴얼로 재구성하고, 앱이 별도 복사본이 아니라 같은 README를 직접 읽도록 연결한다.

## 2. README 필수 순서

루트 `README.md`를 다음 순서로 정리했다.

1. 프로젝트 목적
2. 프로젝트 구조
3. 설치 방법
4. 환경변수 설정
5. 실행 방법
6. 테스트 방법
7. 결과물 위치

자동 테스트에서 7개 제목의 존재와 순서를 검증한다.

## 3. 추가 운영 내용

- 6개 Agent와 Evaluator·Critic·독립 Judge·타당성 평가·사람 승인 역할
- Agent 중단, CSV 누락, 포트 충돌, 인증 오류, timeout, 빈 검색 결과 대응
- 429·timeout 제한 재시도와 Pipeline·Judge 상태 분리
- 결함 수명주기와 연결 RETEST 종료 조건
- 35 PASS, Judge, 타당성, QA·업무 승인, 중요 결함을 포함한 배포 판정
- 비밀값·개인정보·VOC 원문 최소 보존 원칙
- 현재 전체 회귀 테스트 225 PASS와 기존 qa-observer Prometheus 잔여 실패 6건
- Agent·대시보드 실행, 품질진단, VOC 회귀·전체 회귀 명령
- Run·Case·보고서·결함·로그·단계별 문서 위치
- 주요 문제 진단 방법

## 4. 앱 사용자 가이드

- 좌측 메뉴명을 `실행 가이드`에서 `사용자 가이드`로 변경했다.
- 기본 선택은 `사용자 가이드`이며 루트 `README.md`를 직접 표시한다.
- 추가 문서는 `품질진단 실행`, `이식 가이드`, `이식 체크리스트`로 구분한다.
- 중복 페이지 제목과 별도 CSS 없이 Streamlit `segmented_control`과 Markdown 렌더링을 사용한다.

README 수정은 앱에 자동 반영되므로 두 문서의 내용이 달라지는 문제를 방지한다.

## 5. 실제 명령 검증

2026-07-16 현재 환경에서 다음을 확인했다.

- Python 3.12.9
- Streamlit 1.59.2
- `pip check`: `No broken requirements found`
- `agents.cmd status`: 6개 Agent 모두 `RUNNING`
- `quality-diagnosis.cmd validation`: PASS
- 테스트케이스·100점 평가표·35건 Catalog·Judge·타당성·증적 계약 검증: PASS
- `python -m compileall dashboard voc_quality_runtime`: PASS
- Streamlit 사용자 가이드 화면: 예외 0건

## 6. 자동 검증 결과

- README 7개 필수 제목 순서: PASS
- README와 `load_guide("사용자 가이드")` 내용 일치: PASS
- README에 등록된 핵심 명령 파일 존재: PASS
- 현재 VOC 메뉴명이 README에 모두 포함됨: PASS
- README 평문 자격 증명 패턴: 0건
- 앱 사용자 가이드 기본 렌더링: PASS
- Step 9·VOC 대상 테스트: 37 PASS
- 전체 회귀 테스트: 225 PASS / 6 FAIL
- 전체 회귀 실패 6건은 기존 qa-observer Prometheus 업무 집계 메트릭 미노출 문제이며 Step 9 변경과 직접 관련되지 않는다.
- Streamlit 상태 확인: HTTP 200, `ok`
- README·Step 9 문서 평문 자격 증명 패턴: 0건

## 7. 사용자 확인 방법

1. 루트 `README.md`에서 7개 필수 항목 순서를 확인한다.
2. 설치·환경변수·Agent·대시보드 명령이 이해하기 쉬운지 검토한다.
3. `홈 > VOC 품질진단 > 사용자 가이드`로 이동한다.
4. 기본 사용자 가이드가 README와 같은 내용인지 확인한다.
5. `품질진단 실행`, `이식 가이드`, `이식 체크리스트`를 선택해 기존 문서도 조회되는지 확인한다.
6. 역할, 장애·429, 배포 판정, 결과물 위치와 보안 안내를 검토한다.

## 8. Step 9 승인 전 사용자 액션

- README와 메뉴 매뉴얼의 용어·실행 순서·담당자 안내를 확인한다.
- 가능하면 README의 설치 확인 또는 실행 명령을 직접 따라 해본다.
- 실제 운영 경로가 현재 `C:\qaeduc\ai_quality_final_project_2026`과 다르면 경로 일반화 방식을 요청한다.
- 환경변수, 포트, 결과물 보존 기간에 추가 안내가 필요한지 결정한다.
- 향후 기능 변경 시 README를 먼저 또는 함께 갱신하는 운영 정책을 승인한다.

확인 후 `Step 9 승인, Step 10 시작`이라고 전달하면 최종 회귀·운영 인수·시연 준비 단계로 진행한다.

## 9. Step 9 승인 결과

사용자가 2026-07-16 Step 9을 승인했다. README와 앱 사용자 가이드는 현재 운영 매뉴얼 기준선으로 확정했으며, 기능·경로·환경 변경 시 함께 갱신한다.
