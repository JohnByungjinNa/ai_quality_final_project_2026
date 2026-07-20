# Team3 → 2026 VOC 품질진단 통합 결과

## 프로젝트

- 기반: `C:\qaeduc\ai_quality_final_project_Team3`
- 생성: `C:\qaeduc\ai_quality_final_project_2026`
- 원본 Team3 수정: 없음
- 비밀 `.env` 및 기존 실행 이력 복제: 없음

## UI 구성

상단 대메뉴 `VOC 품질진단` 아래에 다음 좌측 메뉴를 추가했다.

1. Dashboard
2. Agent 관리
3. VOC 분석
4. 테스트케이스
5. 품질 평가 기준
6. 장애 진단
7. A2A Trace
8. Report
9. 실행 가이드

## 자체 포함 런타임

`voc_quality_runtime/`에 6-Agent, gRPC 계약, CSV, 품질 기준, 장애 runner, Report 생성기를 포함했다. 원본과 동시에 실행할 수 있도록 통합본은 6101~6106 포트를 사용한다.

UI의 실행 어댑터는 허용된 명령만 실행하고 Report 루트 밖의 파일을 읽지 않는다. 프로세스 start/stop/restart는 화면에서 확인 체크 후에만 가능하며 명령 출력의 자격 증명 패턴은 마스킹한다. 실제 VOC 질문 결과는 사용자가 저장을 명시적으로 선택한 경우에만 `Reports/VOC`에 기록한다.

## 의존성 통합

- Protobuf 생성 코드: 6.31.1 기준
- Runtime Protobuf: 6.33.2
- Streamlit: Protobuf 6 호환 1.x 범위
- FastAPI: 최신 Streamlit의 Starlette 사용과 호환되는 0.x 범위
- Python: 3.12 전용 `.venv` 검증

## 검증 결과

- Python 문법 검사: PASS
- VOC 메뉴·런타임 통합 테스트: PASS
- 기존 Team3 포함 전체 pytest: 57 PASS
- VOC 테스트케이스·100점표·장애·A2A 종합 진단: PASS
- Streamlit 실제 기동 `/_stcore/health`: PASS
- Report·문서 평문 자격 증명 패턴: 0건
- 원본 Team3 Git 상태: 변경 없음

## 현재 의도적으로 남긴 조건

- 실제 API 키는 복사하지 않았다. `voc_quality_runtime/.env`를 새로 생성해 입력해야 Agent를 시작할 수 있다.
- `quality-diagnosis all`은 테스트 정의·루브릭 구조·장애 대응·기존 Trace 보고서를 검증한다. 20개 질문을 LLM에 실제 실행해 100점 자동채점하는 runner는 별도 후속 기능이다.
- Docker Compose에 6개 VOC Agent sidecar는 아직 추가하지 않았다. 현재 Agent 제어 화면은 Windows 로컬 실행 기준이다.
- 기존 Team3와 이름이 겹치지 않도록 기본 Docker 컨테이너 이름은 `ai-quality-2026-*`로 분리했다. 호스트 포트는 기존 문서와 동일하므로 동시 Docker 실행 시 별도 포트 매핑이 필요하다.
- FastAPI 테스트에서 사용 중인 `httpx` 호환 계층의 deprecation warning 1건은 테스트 실패가 아니며 후속 의존성 정리 대상이다.
