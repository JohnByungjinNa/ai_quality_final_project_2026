# VOC 품질진단 테스트케이스

`test_cases.json`에는 실제 `voc.csv`에 맞춘 20개 테스트가 있습니다.

```powershell
.\.venv\Scripts\python.exe quality_diagnosis\validate_test_cases.py
```

구성:

- 정상 VOC 8개
- 모호한 질문 3개
- 복합 불만 3개
- 데이터 없음 2개
- 오타·비문 2개
- 장애 상황 2개

AI 결과는 완전한 문자열 일치로 판정하지 않습니다. `expected_intent`, `expected_keywords`, `expected_voc_ids`, `required_output`, `prohibited_output`, `expected_system_behavior`를 이용해 의미 요소와 안전성을 평가합니다.

장애 테스트는 `setup`을 적용한 뒤 실행하고 테스트가 끝나면 Agent와 CSV 설정을 원상 복구해야 합니다.
