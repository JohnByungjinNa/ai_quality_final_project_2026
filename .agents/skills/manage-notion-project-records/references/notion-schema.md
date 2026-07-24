# Notion Project Journal Schema

## Recommended structure

```text
Confirmed parent
├─ Project journal index
│  ├─ Work record database (inline)
│  └─ 중요 설계 결정
└─ Project journal Archive · <cutoff> 이전
```

Keep the index lightweight. Store new work as database items. Preserve the legacy page as an archive rather than migrating every old block row by row.

## Work record properties

| Property | Type | Values or purpose |
|---|---|---|
| 작업명 | Title | Searchable outcome-oriented title |
| 작업 일시 | Date | Completion time in the user's timezone |
| 영역 | Select | Project-specific areas plus `프로젝트 공통` |
| 유형 | Select | `진단`, `구현`, `디자인`, `검증`, `환경`, `문서`, `Git·배포` |
| 상태 | Select | `완료`, `부분 완료`, `후속 필요`, `차단` |
| 중요도 | Select | `중요`, `보통` |
| 요약 | Rich text | One-sentence outcome |
| 수정 파일 | Rich text | Files or external artifacts changed |
| 검증 결과 | Rich text | Tests, checks, and observed result |
| 등록 시간 | Created time | Automatic creation timestamp |

Adapt area choices to the project, but keep property names stable unless repository instructions require otherwise.

## Recommended views

- **최근 작업:** sort `작업 일시` descending.
- **후속 조치 필요:** filter `상태` is not `완료`.
- **영역별 기록:** board grouped by `영역`.
- **월별 기록:** calendar using `작업 일시`.

## Record body

Start with a green callout containing the original request or a concise task statement with date and time. Follow it with a blue toggle containing:

- 수행 내용
- 수정 파일
- 검증 결과
- 실행·확인 방법
- 주의 사항
- 완료 시간

Keep property summaries short and put detailed evidence inside the toggle.

## Architectural decision record

Use sequential IDs such as `ADR-001`. Include:

- 상태
- 결정일
- 배경
- 결정
- 대안
- 영향

Record only decisions that future work needs to understand. Ordinary implementation notes belong in the work-record database.
