# Content sources and publication guardrails

이 문서는 공개 페이지에 들어간 문구의 출처와, 확인되지 않아 넣지 않은 내용을 구분하기 위한 내부 검토 메모입니다.

## 확인한 외부 참고 구조

- [참고 포트폴리오](https://jongsu1002-star.github.io/ai_agent_quality_portfolio/)

실제 heading 흐름은 `IT RPA PM · AI 품질관리 전문가`, `PM · QA · 운영 자동화`, `IT 경력`, `일하는 방식`, `대표 프로젝트 중심 경력`, `핵심 역량과 기술`, `기여 가능한 역할`, `채용·협업·프로젝트 제안` 순서였습니다. 이 구조의 정보 설계만 참고하고, 참고 사이트의 회사명·고객사·성과 수치를 사용하지 않았습니다.

## 사용한 Notion 원문

| 포트폴리오 영역 | 원문 | 확인한 내용 |
|---|---|---|
| 교육 배경 | [AI 기반 소프트웨어 테스터(QA) 및 모니터링 실무 과정](https://app.notion.com/p/54c6031e8cac82c88d6d81ea3da075a3?pvs=204) | 2026.05.27~2026.08.07, 이론 5%·실습 80%·팀 프로젝트 15%, QA·모니터링·AI 서비스 품질관리 목표 |
| AI Agent QA & Monitoring | [AI Agent 품질관리·운영 모니터링 플랫폼](https://app.notion.com/p/4956031e8cac832bae54014f84b9b498?pvs=204) | FastAPI, pytest, k6, Prometheus, Grafana, Streamlit, Jira, Docker Compose로 확장하는 품질·운영 흐름 |
| VOC Multi-Agent QA / AWS | [(최종) AWS 기반 VOC 멀티 에이전트 QA 결과관리 및 운영감사 프로젝트](https://app.notion.com/p/6286031e8cac820d9fc2016b31094ee6?pvs=204) | VOC 근거, Agent Pipeline, 독립 LLM Judge, 품질·타당성 평가, 승인·증적·AWS S3 연결 |
| RAG Chatbot | [RAG 기반 챗봇 Agent 자동 품질 평가](https://app.notion.com/p/e446031e8cac830a9e5c81f21ca084cc?pvs=204) | 문서 기반 검색·응답 흐름, PDF 업로드, 품질평가용 TC, 정확성·근거성·환각 여부·검색성능, Judge Agent |
| Tool Calling Agent | [AI Agent 품질 진단 프로젝트](https://app.notion.com/p/7ce6031e8cac83f7ad1281f14940a1b4?pvs=204) | Accuracy, Reliability, Robustness, Tool Calling, Error Handling, Happy·Edge·Negative 테스트, Agent 뒤 Judge 구조 |

## 로컬 프로젝트 자료

포트폴리오 문구를 보강할 때 인접 작업 폴더의 다음 문서를 함께 대조했습니다.

- `work/ai_quality_final_project_2026/PORTFOLIO.md`
- `work/ai_quality_final_project_2026/README.md`
- `work/ai_quality_final_project_2026/docs/`
- `work/ai_quality_final_project_2026/qa_observer/`
- `work/ai_quality_final_project_2026/voc_quality_runtime/`

로컬 자료에는 더 상세한 구현·시연 수치가 있으나, 개인별 기여 범위와 공개 검증 상태를 이 요청에서 확정할 수 없는 숫자는 공개 페이지에서 의도적으로 제외했습니다.

## 공개 페이지에 의도적으로 넣지 않은 내용

- 정확한 성명, 이메일, 전화번호, GitHub 저장소 URL
- 회사명·고객사명·근무 기간별 상세 경력
- 개인별 프로젝트 역할, 팀 내 기여도, 작성자 정보
- 회귀 테스트 횟수, 품질 점수, Pass/Fail 비율, 응답시간 개선치 등 성과 숫자
- 교육 수료 여부를 증명하는 자격·인증 문구

위 정보는 사용자가 원문이나 공개 링크로 확인해 주면 다음 버전에서 추가할 수 있습니다.

## 공개 전 주의

Notion 링크는 현재 연결된 워크스페이스 권한이 필요할 수 있습니다. GitHub Pages를 공개하기 전 각 링크의 공유 권한을 확인하고, 비공개 자료를 그대로 노출하지 않도록 공개용 문서로 대체하는 것이 안전합니다.
