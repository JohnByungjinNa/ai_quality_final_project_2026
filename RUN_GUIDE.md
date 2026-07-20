# 프로젝트 실행 가이드

이 문서는 현재 프로젝트를 실행하고, 화면에서 테스트 결과와 k6 성능 테스트 결과를 확인하는 방법을 정리합니다.

## 1. 기본 위치

PowerShell에서 프로젝트 폴더로 이동합니다.

```powershell
cd C:\qaeduc\ai_quality_final_project_2026
```

가상환경은 상위 폴더의 `.venv`를 사용합니다.

```powershell
..\.venv\Scripts\python.exe
```

## 2. API 서버 실행

터미널 1에서 FastAPI 서버를 실행합니다.

```powershell
cd C:\qaeduc\ai_quality_final_project_2026
..\.venv\Scripts\python.exe -m uvicorn api_app:app --reload --port 8000
```

정상 실행되면 아래 주소로 확인할 수 있습니다.

```text
http://localhost:8000
http://localhost:8000/health
http://localhost:8000/docs
```

만약 `Could not import module "api_app"` 오류가 나오면 현재 위치가 프로젝트 폴더가 아닌 것입니다. 아래처럼 실행합니다.

```powershell
cd C:\qaeduc
.\.venv\Scripts\python.exe -m uvicorn api_app:app --app-dir .\ai_quality_final_project_2026 --reload --port 8000
```

## 3. qa-observer와 Streamlit 대시보드 실행

터미널 2를 새로 열고 통합 실행기를 사용합니다. 실행기는 qa-observer의 health를 먼저 확인하고, 실행 중이 아니면 백그라운드로 시작한 뒤 Streamlit을 실행합니다. 이미 정상 실행 중인 프로세스는 중복 기동하지 않고 재사용합니다.

```powershell
cd C:\qaeduc\ai_quality_final_project_2026
.\tools\start_dashboard.ps1
```

PowerShell 실행 정책으로 `.ps1` 실행이 차단된 환경에서는 시스템 정책을 변경하지 않고 현재 프로세스에만 bypass를 적용합니다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\start_dashboard.ps1
```

Streamlit만 다시 시작하고 qa-observer는 정상 상태 그대로 재사용하려면 다음 명령을 사용합니다.

```powershell
.\tools\start_dashboard.ps1 -Restart
```

브라우저에서 아래 주소로 접속합니다.

```text
http://localhost:8501
```

qa-observer 상태는 `http://127.0.0.1:8010/health`에서 확인할 수 있으며, 실행 로그는 `logs/local_services`와 `logs/qa_observer`에 기록됩니다.

## 4. 테스트 수행 결과 확인

Streamlit 화면에서 아래 메뉴로 이동합니다.

```text
테스트 관리 > 테스트 수행 이력
```

수행 이력에서 상세 버튼을 누르면 테스트 결과, 고도화 지표, 결과 보고서를 확인할 수 있습니다.

결과 보고서에서 부록을 포함하면 k6 성능 테스트, 운영 모니터링, Jira 결함 등록 정보 등이 함께 반영됩니다.

```text
테스트 관리 > 테스트 수행 이력 > 상세 팝업 > 결과 보고서 > 부록 포함
```

## 5. k6 설치 확인

k6 성능 테스트를 화면에서 실행하려면 PC에 k6가 설치되어 있어야 합니다.

```powershell
k6 version
```

버전 정보가 나오면 설치된 상태입니다.

설치되어 있지 않으면 Streamlit 화면에서 k6 실행 버튼이 비활성화되거나 실행 불가 안내가 표시됩니다.

## 6. 화면에서 k6 성능 테스트 실행

API 서버와 Streamlit을 모두 실행한 뒤 아래 메뉴로 이동합니다.

```text
성능관리 > K6 성능테스트
```

대상 URL은 먼저 헬스체크 주소로 테스트하는 것을 권장합니다.

```text
http://localhost:8000/health
```

질문 API를 테스트하려면 아래처럼 입력할 수 있습니다.

```text
http://localhost:8000/ask?question=이 교육과정은 총 몇 시간인가요?
```

화면에서 조절할 수 있는 값은 다음과 같습니다.

- 동시 사용자 수
- 총 테스트 시간
- Ramp-up 시간
- 요청 간 대기시간
- p95 응답시간 기준
- 실패율 기준
- 체크 성공률 기준

설정을 조정한 뒤 `k6 백그라운드 실행` 버튼을 누르면 Streamlit과 분리된 worker 프로세스에서 성능 테스트가 실행됩니다.

- 설정을 변경하면 Ramp-up, 유지, 종료 구간과 결과 저장 시간을 반영한 예상 수행 시간이 즉시 갱신됩니다.
- 실행 직후 큰 수행 팝업이 열리며 `설정 검증 → worker 시작 → k6 수행 → 결과 집계·이력 저장 → 완료` 단계를 2초 주기로 보여줍니다.
- Windows에서는 worker와 k6를 콘솔 창 없이 실행하므로 CMD 창이 화면 전면이나 작업표시줄에 나타나지 않습니다.
- 진행률 아래의 단계 선택 표시에서 완료 단계는 `✓`, 현재 단계는 선택 강조, 이후 단계는 `○`로 구분됩니다.
- 수행 팝업에는 대상 URL, 동시 사용자, 시간, 대기시간과 PASS/FAIL 평가 기준이 함께 표시됩니다.
- 팝업을 닫아도 테스트는 중단되지 않으며, 실행 버튼 위치의 `수행 화면 열기`로 다시 열 수 있습니다.
- 팝업의 `닫기`는 상단 상태 정보 옆에 표시되며 팝업만 닫고 백그라운드 테스트는 계속 수행합니다.
- 본 페이지에는 별도의 진행률·단계 카드를 중복 표시하지 않고 실행 버튼 위치에 `수행 화면 열기`를 제공합니다.
- 실행 중지는 본 페이지가 아니라 수행 팝업의 `실행 중지 확인`과 `테스트 중지`로 제어합니다.
- 실행 직후 Run ID와 `RUNNING` 상태가 저장됩니다.
- 다른 메뉴로 이동하거나 브라우저 탭을 닫아도 테스트는 계속됩니다.
- K6 성능테스트 페이지로 돌아오면 2초 주기로 현재 상태가 자동 갱신됩니다.
- 동시에 하나의 k6 테스트만 실행할 수 있습니다.
- 중지가 필요하면 `중지 확인`을 선택한 뒤 `실행 중지`를 누릅니다. 이력에는 `STOPPED`로 기록됩니다.
- Streamlit 서버가 재시작되어도 실행 이력과 완료 결과는 파일에서 복원됩니다.

## 7. k6 결과 확인 위치

화면에서 바로 확인할 수 있는 메뉴입니다.

```text
성능관리 > K6 성능테스트 > 실행 결과
성능관리 > K6 성능테스트 > 최근 k6 수행이력
성능관리 > 운영 모니터링
```

파일로 저장되는 위치는 아래와 같습니다.

```text
reports/k6_runs/<실행시각>/
reports/k6_summary.json
```

`reports/k6_summary.json`은 최신 k6 결과이며, 결과 보고서 부록에서도 이 파일을 사용합니다.

각 실행 폴더에는 기존과 동일하게 `script.js`, `summary.json`, `run_record.json`이 저장되며 worker 진단용 `worker.log`가 추가됩니다. `run_record.json`의 상태는 다음 중 하나입니다.

- `STARTING`: worker 시작 준비
- `RUNNING`: 백그라운드 수행 중
- `PASS` / `FAIL`: 수행 완료 및 기준 판정
- `ERROR`: 실행 오류 또는 worker 비정상 종료
- `STOPPED`: 사용자 요청으로 중지

## 8. Prometheus 연결

운영 모니터링 화면에서 Prometheus를 연결하려면 먼저 API 서버가 `/metrics`를 제공해야 합니다.

API 서버 실행 후 아래 주소가 열리는지 확인합니다.

```text
http://localhost:8000/metrics
```

Prometheus 설정 파일은 프로젝트 루트의 `prometheus.yml`을 사용합니다.

```text
prometheus.yml
```

Prometheus를 로컬 실행 파일로 설치한 경우, 터미널 3에서 아래처럼 실행합니다.

```powershell
cd C:\qaeduc\ai_quality_final_project_2026
C:\prometheus\prometheus.exe --config.file=prometheus.yml --web.listen-address=:9090
```

정상 실행되면 아래 주소로 Prometheus를 확인합니다.

```text
http://localhost:9090
```

Streamlit의 운영 모니터링 화면은 기본적으로 아래 주소의 Prometheus를 조회합니다.

```text
http://localhost:9090
```

`C:\prometheus`가 Windows 환경변수 `Path`에 등록되어 있다면 아래처럼 짧게 실행해도 됩니다.

```powershell
cd C:\qaeduc\ai_quality_final_project_2026
prometheus.exe --config.file=prometheus.yml --web.listen-address=:9090
```

다른 Prometheus 주소를 사용할 경우 `.env`에 아래 값을 설정합니다.

```env
PROMETHEUS_URL=http://localhost:9090
```

Prometheus 화면에서 아래 쿼리를 입력해 데이터가 나오는지 확인할 수 있습니다.

```promql
up
```

```promql
http_requests_total
```

```promql
agent_response_seconds_count
```

Docker로 Prometheus를 실행하는 경우에는 컨테이너 안에서 Windows 호스트의 API 서버를 `localhost`로 볼 수 없습니다. 이 경우 `prometheus.yml`의 target을 아래처럼 바꿔야 합니다.

```yaml
targets:
  - "host.docker.internal:8000"
```

그 다음 Docker에서 실행합니다.

```powershell
cd C:\qaeduc\ai_quality_final_project_2026
docker run --rm -p 9090:9090 -v ${PWD}\prometheus.yml:/etc/prometheus/prometheus.yml prom/prometheus
```

## 9. 종료 방법

각 터미널에서 실행 중인 서버는 `Ctrl + C`로 종료합니다.

종료 대상은 보통 두 개입니다.

- uvicorn API 서버
- Streamlit 대시보드
- Prometheus

## 10. 권장 실행 순서 요약

1. API 서버 실행

```powershell
cd C:\qaeduc\ai_quality_final_project_2026
..\.venv\Scripts\python.exe -m uvicorn api_app:app --reload --port 8000
```

2. qa-observer와 Streamlit 통합 실행

```powershell
cd C:\qaeduc\ai_quality_final_project_2026
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\start_dashboard.ps1
```

대시보드만 직접 실행하면 qa-observer가 준비되지 않아 첫 화면에 데이터가 표시되지 않을 수 있으므로 통합 실행기를 사용합니다.

3. 브라우저 접속

```text
http://localhost:8501
```

4. k6 성능 테스트 실행

```text
성능관리 > K6 성능테스트
```

5. Prometheus 실행

```powershell
cd C:\qaeduc\ai_quality_final_project_2026
C:\prometheus\prometheus.exe --config.file=prometheus.yml --web.listen-address=:9090
```

6. 결과 보고서 확인

```text
테스트 관리 > 테스트 수행 이력 > 상세 팝업 > 결과 보고서
```

## 11. 서비스 관리에서 독립 실행

아래 메뉴에서 Docker Engine, Grafana, Prometheus, FastAPI를 각각 시작·중지할 수 있습니다.

```text
홈 > 성능관리 > 서비스 관리
```

Grafana, Prometheus, FastAPI는 서비스별로 다음 실행 방식을 선택해 저장합니다.

- `Docker Compose`: Docker Engine이 이미 실행 중일 때 해당 컨테이너만 `--no-deps`로 시작·중지
- `로컬 실행`: 이 화면이 직접 시작하고 PID를 기록한 로컬 프로세스만 시작·중지
- `외부 관리`: 외부 서버·Windows 서비스·관리형 서비스의 endpoint 상태만 조회

기본 실행 방식은 다음과 같습니다.

```text
Grafana: Docker Compose
Prometheus: Docker Compose
FastAPI: 로컬 실행
```

각 행의 `시작` 또는 `중지`를 누르면 페이지 하단이 아니라 `서비스 제어 확인` 팝업이 열립니다. 팝업에서 `오조작 방지 확인`을 선택한 뒤 실행합니다.

- 시작은 프로세스·컨테이너 명령 성공만 보지 않고 실제 health endpoint 응답까지 확인합니다.
- 중지는 관리 대상 PID·컨테이너 종료와 endpoint 중지까지 확인합니다.
- 준비 시간 안에 health가 확인되지 않으면 포트 충돌·설정 오류와 최근 로그를 실패 메시지로 안내합니다.
- Docker Engine이 중지된 Docker 방식이나 실행 파일이 없는 로컬 방식도 시작 팝업을 열 수 있으며, 실행 시 충족되지 않은 조건을 구체적으로 표시합니다.

로컬 Grafana·Prometheus 실행 파일이 PATH에 없다면 아래 환경변수로 경로를 지정합니다.

```powershell
$env:GRAFANA_EXECUTABLE='C:\Program Files\GrafanaLabs\grafana\bin\grafana.exe'
$env:PROMETHEUS_EXECUTABLE='C:\prometheus\prometheus.exe'
```

서비스 실행 방식 자체를 환경변수로 고정하려면 `GRAFANA_RUNTIME_MODE`, `PROMETHEUS_RUNTIME_MODE`, `FASTAPI_RUNTIME_MODE`에 `docker`, `local`, `external` 중 하나를 설정합니다. 환경변수는 화면에서 저장한 값보다 우선합니다.

Docker 방식의 Grafana·Prometheus·FastAPI 시작은 Docker Desktop을 자동으로 시작하지 않습니다. 먼저 Docker Engine 행의 시작 버튼을 누르고 준비된 뒤 원하는 서비스만 시작합니다. Docker Engine 중지는 실행 중인 모든 컨테이너에 영향을 주므로 `오조작 방지 확인`을 선택한 뒤 실행합니다.

Docker Compose에서도 서비스 생명주기 의존 관계를 제거했으므로 다음처럼 개별 실행할 수 있습니다.

```powershell
docker compose up -d --no-deps api
docker compose up -d --no-deps prometheus
docker compose up -d --no-deps grafana
docker compose stop grafana
```

Prometheus나 Grafana를 먼저 실행할 수는 있지만 연결 대상이 아직 중지 상태이면 target 또는 datasource가 일시적으로 비정상으로 표시됩니다. 대상 서비스가 시작되면 자동으로 정상화됩니다.

## 12. Docker Compose 통합 실행

Docker Compose를 사용하면 FastAPI, Streamlit, Prometheus, Grafana를 한 번에 실행할 수도 있습니다. 각 서비스의 `depends_on`은 제거되어 있어 실행 순서를 강제하지 않으며, 통합 실행 명령을 선택한 경우에만 함께 시작됩니다.

먼저 Windows에서 Docker Desktop을 실행합니다. Docker Desktop 상태가 `Running` 또는 `Engine running`이 된 뒤 PowerShell에서 아래 명령으로 Docker가 준비됐는지 확인합니다.

```powershell
docker ps
```

정상이라면 실행 중인 컨테이너 목록이 표시됩니다. Docker Desktop이 켜져 있지 않으면 `Cannot connect to the Docker daemon` 오류가 날 수 있습니다.

Docker Desktop 준비가 끝나면 프로젝트 전체 환경을 실행합니다.

```powershell
cd C:\qaeduc\ai_quality_final_project_2026
docker compose up --build
```

실행 후 접속 주소는 아래와 같습니다.

```text
Streamlit 대시보드: http://localhost:8501
FastAPI: http://localhost:8000
Prometheus: http://localhost:9090
Grafana: http://localhost:3000
```

Grafana 기본 계정은 아래와 같습니다.

```text
ID: admin
PW: admin
```

Prometheus datasource는 Docker Compose 실행 시 Grafana에 자동 등록됩니다.

종료할 때는 아래 명령을 사용합니다.

```powershell
cd C:\qaeduc\ai_quality_final_project_2026
docker compose down
```

## 12. VOC 품질진단 실행

### 12.1 환경 초기화

```powershell
cd C:\qaeduc\ai_quality_final_project_2026\voc_quality_runtime
.\scripts\agents.cmd init
notepad .env
```

실제 비밀값은 `.env`에만 입력하며 화면·문서·Report에 붙여 넣지 않습니다.

### 12.2 6개 Agent 실행

```powershell
.\scripts\agents.cmd start
.\scripts\agents.cmd status
```

Interpreter부터 Improver까지 6101~6106 포트가 모두 `RUNNING`이어야 합니다. 기존 `VOC_Improve`가 같은 포트를 사용 중이라면 둘 중 하나만 실행하거나 Endpoint 설정을 분리해야 합니다.

### 12.3 품질진단과 Report

```powershell
# 전체
.\scripts\quality-diagnosis.cmd all

# 선택 실행
.\scripts\quality-diagnosis.cmd validation
.\scripts\quality-diagnosis.cmd fault
.\scripts\quality-diagnosis.cmd a2a
```

```text
voc_quality_runtime/quality_diagnosis/Reports/
├── Summary/
├── Validation/
├── Fault/
├── A2A/
└── VOC/
```

Streamlit을 실행한 뒤 상단 `VOC 품질진단` 메뉴에서 같은 정의와 Report를 조회할 수 있습니다. Agent start/stop/restart는 확인 체크 후에만 실행됩니다.
