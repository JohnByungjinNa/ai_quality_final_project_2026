# VOC Improve 재사용 키트

이 폴더는 `VOC_Improve`의 멀티 Agent 품질진단 구성을 다른 프로젝트에 이식하기 위한 자료다. 구현 코드 전체를 무작정 합치는 대신 런타임, UI 어댑터, 품질 기준, Report를 분리해 적용한다.

## 포함 자료

| 파일 | 용도 |
|---|---|
| `ARCHITECTURE.md` | 6개 Agent, gRPC, LLM, 감사 로그와 Report 흐름 |
| `ADOPTION_GUIDE.md` | 다른 프로젝트로 복사하고 연결하는 절차 |
| `PORTABILITY_CHECKLIST.md` | 비밀값·포트·경로·시험·배포 점검표 |
| `menu_manifest.json` | 대메뉴와 좌측 하위 메뉴 표준 구성 |
| `runtime_manifest.json` | 필요한 코드·설정·실행 명령·산출물 목록 |
| `EXAMPLE_TEAM3_2026.md` | Team3 대시보드에 실제 적용한 예시와 검증 결과 |

## 권장 통합 구조

```text
target-project/
├── dashboard/                    기존 UI
├── voc_quality_runtime/          VOC Improve 독립 런타임
│   ├── agents/
│   ├── llm_wrappers/
│   ├── quality_diagnosis/
│   ├── scripts/
│   └── voc.csv
└── dashboard/pages_top/          VOC 품질진단 UI 라우터·화면
```

런타임을 하위 폴더로 격리하면 기존 프로젝트 모듈명, 데이터, Report와 충돌하지 않고 향후 원본 개선사항도 비교·교체하기 쉽다.

## 최소 실행

```powershell
cd target-project\voc_quality_runtime
.\scripts\agents.cmd init
notepad .env
.\scripts\agents.cmd start
.\scripts\quality-diagnosis.cmd all
```

비밀값이 포함된 `.env`, `.runtime`, 과거 Report, 가상환경은 다른 프로젝트로 복사하지 않는다.
