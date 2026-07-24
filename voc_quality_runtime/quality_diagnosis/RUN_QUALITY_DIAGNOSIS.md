# 현재 구성 실행 및 Report 확인 방법

모든 명령은 프로젝트 루트 `C:\qaeduc\VOC_Improve`에서 실행한다.

## 1. 최초 환경 설정

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
.\scripts\agents.cmd init
notepad .env
```

`.env`에는 새로 발급한 실제 키를 입력하고 저장소나 Report에 복사하지 않는다.

## 2. Agent 실행과 상태 확인

```powershell
.\scripts\agents.cmd start
.\scripts\agents.cmd status
```

정상이라면 Interpreter부터 Improver까지 6101~6106 포트가 모두 `RUNNING`으로 표시된다.

## 3. 실제 VOC 처리

VS Code에서 MCP 도구 `analyze_voc_nl_v2`에 질문을 입력한다. 처리 중 생성되는 Agent 간 호출 기록은 `.runtime/audit/a2a_events.jsonl`에 누적되며 VOC 원문 대신 핵심 키워드만 기록된다.

빈 검색은 다음 안전 응답과 `ok=false`를 반환해야 한다.

> 현재 VOC 데이터에서 직접적으로 일치하는 사례를 찾지 못했습니다.  
> 추가 로그 또는 주문번호 기반 확인이 필요합니다.

## 4. 전체 품질진단 실행

```powershell
.\scripts\quality-diagnosis.cmd all
```

다음 항목을 순서대로 수행한다.

1. 테스트케이스 20개 개수·분포·기대 결과 검증
2. 100점 품질 평가표 배점·즉시 배포 보류 규칙 검증
3. Retriever 중단 등 장애 시험 6개
4. 누적 A2A 감사 로그의 Markdown 보고서 생성
5. 전체 실행 결과 Summary 생성

## 5. 항목별 실행

```powershell
# 테스트케이스와 평가표만 검증
.\scripts\quality-diagnosis.cmd validation

# 장애 진단 6개만 실행
.\scripts\quality-diagnosis.cmd fault

# 누적 A2A Trace 보고서만 생성
.\scripts\quality-diagnosis.cmd a2a

# 특정 장애만 직접 실행
.\scripts\fault-tests.cmd --case FT-03 --case FT-06
```

## 6. Report 위치

```text
quality_diagnosis/Reports/
├── Summary/       전체 실행 종합 결과
├── Validation/    테스트 정의·100점 평가표 검증
├── Fault/         장애 진단 JSON/Markdown
└── A2A/           Agent 간 gRPC Trace Markdown
```

각 폴더의 `latest.*`는 최신 결과이고, 파일명에 실행 시각이 있는 파일은 이력 보관용이다.

```powershell
notepad quality_diagnosis\Reports\Summary\latest.md
notepad quality_diagnosis\Reports\Validation\latest.md
notepad quality_diagnosis\Reports\Fault\latest.md
notepad quality_diagnosis\Reports\A2A\latest.md
```

`all` 결과가 PASS여도 실제 답변의 100점 품질 점수가 자동 산출됐다는 의미는 아니다. 현재 자동 실행은 시험 정의, 평가표 구조, 장애 대응, Trace 보고서 생성을 검증한다. 실제 VOC 답변 점수는 각 실행 증거를 100점 평가표에 대입해 별도로 판정한다.

## 7. 종료

```powershell
.\scripts\agents.cmd stop
```
