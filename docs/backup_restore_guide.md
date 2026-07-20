# 프로젝트 중간 백업·복구 가이드

## 목적

대규모 구성 변경이나 여러 파일을 함께 수정하는 작업에서 안전한 복구 지점을 남긴다. 현재 프로젝트는 Git 저장소가 아니므로 백업 ZIP과 SHA-256 checksum을 별도로 관리한다.

## 백업 생성

프로젝트 루트에서 실행한다.

```powershell
.\tools\create_project_backup.ps1 -Label "task3-before-observer"
```

Windows 실행 정책이 스크립트 실행을 차단하는 환경에서는 시스템 정책을 바꾸지 않고 해당 프로세스에만 다음 명령을 사용한다.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\tools\create_project_backup.ps1" -Label "task3-before-observer"
```

기본 저장 위치:

```text
C:\qaeduc\_backups\ai_quality_final_project_2026\
```

결과물:

- `ai_quality_final_project_2026-yyyyMMdd-HHmmss-label.zip`
- 같은 이름의 `.zip.sha256`
- ZIP 내부의 `backup-manifest.json`: 원본 상대 경로, 크기, 파일 SHA-256

## 자동 제외 대상

- `.env*`, `secrets.toml` 등 비밀값 파일
- `.venv`, `venv`, `node_modules`, Python cache
- `logs`, `reports`, `data`, `user_Docs`, 런타임 디렉터리
- Git metadata와 기존 백업 디렉터리

`.env.example`, `.env.sample`, `.env.template`은 복구에 필요한 설정 예시이므로 포함한다.

## 백업 수행 시점

다음 조건 중 하나에 해당하면 변경 직전과 검증 완료 후에 백업한다.

1. Docker Compose, Prometheus, Grafana provisioning 등 운영 구성이 함께 변경된다.
2. 데이터베이스 schema 또는 migration이 변경된다.
3. 5개 이상의 소스·설정 파일을 동시에 수정한다.
4. 기존 이벤트 형식이나 API 계약을 호환되지 않게 변경한다.
5. qa-observer, Streamlit 상황판 등 큰 Task의 구현을 시작하거나 완료한다.

작은 문서 수정, 단일 파일의 쉽게 되돌릴 수 있는 수정에는 매번 백업하지 않는다.

## 검증

checksum 확인:

```powershell
$zip = "C:\qaeduc\_backups\ai_quality_final_project_2026\백업파일.zip"
Get-FileHash -LiteralPath $zip -Algorithm SHA256
Get-Content -LiteralPath "$zip.sha256"
```

두 SHA-256 값이 같아야 한다.

ZIP 항목 확인:

```powershell
tar -tf $zip | Select-Object -First 20
```

## 복구

1. 현재 프로젝트를 덮어쓰기 전에 반드시 현재 상태도 별도 백업한다.
2. 빈 임시 폴더에 ZIP을 먼저 압축 해제한다.
3. `backup-manifest.json`과 필요한 파일을 확인한다.
4. 전체 덮어쓰기 대신 복구할 파일만 프로젝트로 복사한다.
5. `.env`, 데이터, 보고서는 백업에 없으므로 운영 환경에서 별도로 복구한다.
6. 복구 후 문법 검사, 단위 테스트, Docker 구성 검증을 다시 실행한다.

예시:

```powershell
$restoreDir = Join-Path $env:TEMP "ai-qa-restore-check"
Expand-Archive -LiteralPath $zip -DestinationPath $restoreDir
Get-Content -LiteralPath (Join-Path $restoreDir "backup-manifest.json") -Encoding UTF8
```

백업 ZIP을 프로젝트 루트에 직접 압축 해제하지 않는다.
