# 6개 에이전트 일괄 실행

## 최초 1회 설정

```powershell
.\scripts\agents.cmd init
notepad .env
```

`.env`의 세 자리표시자를 새로 발급한 실제 키로 교체합니다. 따옴표는 없어도 됩니다.

```dotenv
OPENAI_API_KEY=YOUR_OPENAI_API_KEY
ANTHROPIC_API_KEY=YOUR_ANTHROPIC_API_KEY
TAVILY_API_KEY=YOUR_TAVILY_API_KEY
```

`.env`는 `.gitignore`에 포함되어 있으므로 Git에 커밋하지 않습니다.

## 실행 및 관리

프로젝트 루트에서 다음 명령을 사용합니다.

```powershell
# 6개 서버 시작
.\scripts\agents.cmd start

# 상태 확인
.\scripts\agents.cmd status

# 6개 서버 종료
.\scripts\agents.cmd stop

# 전체 재시작
.\scripts\agents.cmd restart
```

특정 Agent만 시작·상태 확인·중지·재시작할 때는 두 번째 인자에 Agent 이름을 지정합니다.

```powershell
.\scripts\agents.cmd start retriever
.\scripts\agents.cmd status retriever
.\scripts\agents.cmd stop retriever
.\scripts\agents.cmd restart retriever
```

허용 이름은 `interpreter`, `retriever`, `summarizer`, `evaluator`, `critic`, `improver`입니다. 개별 중지는 `.runtime\agents.json`에 기록된 관리 PID만 종료하며, 외부 프로세스가 같은 포트를 사용 중이면 종료하지 않고 오류로 안내합니다.

서버는 백그라운드에서 실행되므로 PowerShell 창을 6개 열 필요가 없습니다. 로그는 `.runtime\logs`에, 실행 중인 PID는 `.runtime\agents.json`에 저장됩니다.

`agents.cmd`가 프로젝트 스크립트 실행에만 PowerShell 실행 정책 우회를 적용하므로 별도의 실행 정책 변경은 필요하지 않습니다.

## Agent 간 gRPC 감사 보고서

실제 VOC 처리 시 Agent 호출 구간, 성공 여부, 처리시간, 핵심 키워드가 다음 파일에 누적됩니다.

```text
.runtime/audit/a2a_events.jsonl
```

원문 VOC 대신 핵심 키워드만 저장합니다. Markdown 보고서는 다음 명령으로 생성합니다.

```powershell
.\.venv\Scripts\python.exe scripts\a2a-report.py
```

결과 파일:

```text
quality_diagnosis/Reports/A2A/latest.md
```

특정 요청만 보고하려면 JSONL 또는 전체 보고서에 표시된 trace ID를 사용합니다.

```powershell
.\.venv\Scripts\python.exe scripts\a2a-report.py --trace-id TRACE_ID
```
