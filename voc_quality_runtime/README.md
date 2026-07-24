# Embedded VOC Quality Runtime

`ai_quality_final_project_2026`의 `VOC 품질진단` 메뉴가 사용하는 독립 6-Agent 런타임입니다.

```powershell
.\scripts\agents.cmd init
notepad .env
.\scripts\agents.cmd start
.\scripts\agents.cmd status
.\scripts\quality-diagnosis.cmd all
```

- API 키는 이 폴더의 `.env`에만 저장합니다.
- 6101~6106 포트를 사용합니다.
- Report는 `quality_diagnosis/Reports`에 저장됩니다.
- 현재 `quality-diagnosis all`은 테스트 정의·루브릭 구조, 장애 대응, 기존 A2A Trace 보고서를 검증하며 20개 LLM 테스트의 100점 자동채점은 아직 수행하지 않습니다.
