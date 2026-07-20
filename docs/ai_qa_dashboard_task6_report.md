# Task 6 Streamlit 종합 현황 화면 구현 보고서

## 상태

`APPROVED` — 2026-07-14 사용자로부터 구현 1~5 전체 승인을 받았다.

## 구현 1~5

1. 별도 메뉴와 필터
   - 기존 `성능관리 > 운영 모니터링`을 유지하고 상단에 독립된 `종합 현황` 메뉴를 추가했다.
   - 기간, 환경, 서비스, 공급자, 모델 필터를 하나의 form으로 묶어 조회할 때만 갱신한다.
2. 핵심 KPI와 전체 상태
   - 전체 품질점수, 테스트 통과율, p95 응답시간, 오류율, 안전성 위반, API 비용을 상단 카드로 표시한다.
   - 안전성 → 오류 → 성능 → 품질 → 테스트 → 비용 → 신선도 순서로 정상·주의·위험을 계산한다.
   - 데이터가 없거나 수집기가 연결되지 않으면 0이나 정상으로 표시하지 않는다.
3. 품질·성능·RAG·비용 차트
   - 품질점수 추이, 요청·오류 추이, 품질 지표별 점수, 단계별 평균 응답시간을 제공한다.
   - RAG no-result, LLM token, 가격 적용률, 일 예산 사용률을 별도 카드로 표시한다.
4. 최근 이벤트와 추천 조치
   - 원문이 제거된 최근 이벤트를 UTC 시각, 이벤트 유형, 서비스, run/case ID, 상태로 표시한다.
   - 안전성, 오류율, 지연, 테스트, RAG, 비용 상태에 따라 운영 조치를 자동 추천한다.
5. 성능과 장애 내성
   - 필터 옵션은 60초, 대시보드 데이터는 15초 TTL·제한된 entry 수로 캐시한다.
   - summary, timeseries, events API는 병렬 조회한다.
   - qa-observer가 중단되어도 신규 화면만 데이터 없음·연결 경고를 표시하고 기존 화면은 계속 사용할 수 있다.

## Streamlit 구현 원칙

- 설치된 Streamlit 버전의 공식 번들 지침을 사용했다.
- 신규 화면은 `st.metric`, `st.container(border=True)`, 네이티브 line/bar chart, `st.dataframe`을 사용한다.
- 새 코드에 deprecated `use_container_width`를 추가하지 않았다.
- 기존 앱의 커스텀 상단 메뉴 구조를 전면 교체하지 않아 기존 페이지 동작을 보존했다.

## 수정 파일

- `dashboard/navigation.py`: 별도 상단 메뉴와 하위 메뉴 추가
- `dashboard/streamlit_app.py`: 신규 화면 routing 추가
- `dashboard/pages_top/overview_dashboard.py`: 종합 현황 UI
- `dashboard/services/qa_observer_client.py`: 필터·summary·timeseries·events API client
- `dashboard/services/overview_dashboard.py`: 상태·차트·이벤트·조치 변환
- `tests/fixtures/overview_dashboard_app.py`: 고정 데이터 AppTest fixture
- `tests/test_overview_dashboard.py`: 메뉴·상태·차트·전체 앱 전환 검증

## 검증 결과

- 신규 화면 테스트: 5 PASS
- 고정 데이터 AppTest: 제목, KPI 10개, 차트·이벤트 표, 예외 0건
- 전체 앱 AppTest: 기존 기본 화면 예외 0건, 신규 메뉴 전환 예외 0건
- 전체 회귀 테스트: 104 PASS
- 기존 Starlette/httpx warning 1건과 Streamlit 내부 NumPy timedelta warning 1건
- Docker Compose 구문: PASS
- Docker 실제 화면 검증: 기존 요청대로 추후 체크 항목 유지

## 사용자 확인 항목

- [x] 구현 1: 기존 화면 유지 + 신규 종합 현황 메뉴 승인
- [x] 구현 2: 상단 KPI와 전체 상태 우선순위 승인
- [x] 구현 3: 품질·성능·RAG·LLM 차트 구성 승인
- [x] 구현 4: 최근 이벤트·추천 조치 구성 승인
- [x] 구현 5: 캐시·병렬 조회·수집 장애 표시 승인

## 실행 및 확인

```powershell
.venv\Scripts\python.exe -m uvicorn qa_observer.app:app --host 127.0.0.1 --port 8010
$env:QA_OBSERVER_URL = "http://127.0.0.1:8010"
.venv\Scripts\streamlit.exe run dashboard\streamlit_app.py
```

브라우저에서 상단 `종합 현황` → 좌측 `AI QA 종합 현황`을 선택한다.

## 추후 작업

- Docker Desktop 실행 후 실제 container 데이터로 화면 시각 검증
- Task 7에서 알림 규칙·contact point·runbook과 추천 조치를 연결
- 최종 화면 검증 후에만 기존 운영 모니터링의 숨김·삭제 여부를 별도로 결정
