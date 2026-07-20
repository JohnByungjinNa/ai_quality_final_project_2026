# VOC Improve 구성 및 구현 개요

## 목적

사용자 VOC 질문을 해석하고 CSV 근거를 검색한 뒤 요약·평가·비평·정책 개선안을 생성하며, Agent 간 연결과 장애 대응을 품질 증거로 남긴다.

## 6개 Agent

| 포트 | Agent | 책임 | 주요 결과 |
|---:|---|---|---|
| 6101 | Interpreter | 질문 의도·키워드·검색 조건 해석 | task, filters, max_items, csv_path |
| 6102 | Retriever | `voc.csv` 근거 검색 | 관련 VOC 텍스트 |
| 6103 | Summarizer | 단일 파이프라인 오케스트레이션·요약 | summary, policy, trace |
| 6104 | Evaluator | 요약 후보 상대평가 | winner, scores |
| 6105 | Critic | 사실·명확성·실행 위험 검토 | need_refine, edits |
| 6106 | Improver | VOC 기반 정책 개선안 생성 | policy |

후속 Agent 호출은 `Summarizer.RunPipeline` 한 곳에서만 담당하며 각 Servicer는 자신의 결과만 반환한다.

## 처리 흐름

```text
VS Code MCP
  → Interpreter
  → Summarizer.RunPipeline
      → Retriever(voc.csv)
      → OpenAI 요약 후보
      → Evaluator
      → Critic(summary)
      → Claude Improver
      → Critic(policy)
      → 필요 시 refine
  → summary + policy + trace
```

- OpenAI: 질문 해석, 요약 후보, 평가, 비평, 요약 재작성
- Anthropic Claude: 정책 개선안과 정책 재작성
- Tavily: 키 설정 항목은 있으나 현재 런타임에서 웹 검색에 사용하지 않음

## 안전 동작

- 빈 검색은 LLM을 호출하지 않고 `ok=false`로 반환한다.
- 안전 문구: `현재 VOC 데이터에서 직접적으로 일치하는 사례를 찾지 못했습니다. 추가 로그 또는 주문번호 기반 확인이 필요합니다.`
- Retriever 연결·CSV·timeout 오류는 성공으로 숨기지 않는다.
- API 키 누락은 Agent 초기화 단계에서 명시적으로 차단한다.

## 품질진단

- 테스트케이스 20개: 정상 8, 모호 3, 복합 3, 데이터 없음 2, 오타·비문 2, 장애 2
- 100점 평가: Agent 80, 연계 10, 장애·로그 5, 성능 5
- 즉시 배포 보류: 민감정보 노출, 사실·정책 조작, 장애 성공 보고, 잘못된 결제·환불 확정 안내
- 장애 시험 6개: Retriever 중단, 포트 충돌, CSV 누락, 키 오류, 지연, 빈 검색

## 기록과 Report

```text
.runtime/audit/a2a_events.jsonl              원시 A2A 감사 이벤트
quality_diagnosis/Reports/Summary/           종합 결과
quality_diagnosis/Reports/Validation/        테스트·루브릭 검증
quality_diagnosis/Reports/Fault/             장애 시험
quality_diagnosis/Reports/A2A/               Trace별 연결 보고서
```

Report에는 API 키, 토큰, VOC 원문과 개인정보를 기록하지 않는다.
