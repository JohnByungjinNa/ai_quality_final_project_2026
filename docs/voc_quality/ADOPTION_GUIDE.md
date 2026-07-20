# 다른 프로젝트 적용 가이드

## 1. 런타임 격리

대상 프로젝트 아래 `voc_quality_runtime` 폴더를 만들고 다음 항목을 복사한다.

```text
agents/ llm_wrappers/ utils/ quality_diagnosis/ scripts/
grpc_server.py main.py voc.proto voc_pb2.py voc_pb2_grpc.py
voc.csv .env.example pyproject.toml requirements.txt
```

복사하지 않는 항목:

```text
.env .venv .runtime __pycache__ quality_diagnosis/Reports의 실행 이력
```

## 2. 의존성

대상 가상환경에 `openai`, `anthropic`, `grpcio`, `grpcio-tools`, `protobuf`, `mcp`, `python-dotenv`를 설치한다. 현재 gRPC 생성 코드는 Protobuf 6.31 이상을 요구하므로 `protobuf==6.33.2`와 Protobuf 6을 지원하는 UI 프레임워크 버전을 사용한다. 최신 Streamlit과 FastAPI를 함께 쓰면 양쪽이 요구하는 Starlette 범위도 함께 검증한다. 기존 프로젝트가 `protobuf<6` 또는 구형 Starlette를 강제하면 UI 의존성을 올리거나 VOC Agent 런타임을 별도 가상환경·컨테이너로 분리한다.

## 3. 환경설정

`.env.example`을 `.env`로 복사해 새 키를 입력한다. 포트 충돌 시 다음 환경변수로 Endpoint를 변경하고 모든 호출자와 서버에 동일하게 적용한다.

```dotenv
INTERPRETER_ENDPOINT=localhost:6101
RETRIEVER_ENDPOINT=localhost:6102
SUMMARIZER_ENDPOINT=localhost:6103
EVALUATOR_ENDPOINT=localhost:6104
CRITIC_ENDPOINT=localhost:6105
IMPROVER_ENDPOINT=localhost:6106
```

## 4. UI 통합

권장 대메뉴는 `VOC 품질진단`이며 좌측 메뉴는 다음 순서로 구성한다.

1. Dashboard
2. Agent 관리
3. VOC 분석
4. 테스트케이스
5. 품질 평가 기준
6. 장애 진단
7. A2A Trace
8. Report
9. 실행 가이드

UI는 런타임 파일을 직접 수정하지 않고 다음 안전한 어댑터 기능만 사용한다.

- JSON/Markdown 정의와 Report 읽기
- `agents.cmd status` 실행
- 확인 절차를 거친 Agent start/stop/restart
- `quality-diagnosis.cmd`의 validation/fault/a2a/all 실행
- 최신 Report 목록과 내용 표시

## 5. 검증

```powershell
.\scripts\agents.cmd status
.\scripts\quality-diagnosis.cmd all
```

`Summary/latest.md`가 PASS이고 Report에 평문 비밀값이 없는지 확인한다. 자동 PASS는 실제 AI 답변이 100점이라는 뜻이 아니므로 실제 VOC 실행은 100점 평가표로 별도 판정한다.
