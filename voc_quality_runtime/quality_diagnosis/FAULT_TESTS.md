# 장애 진단 실행 가이드

6개 장애 시험은 현재 실행 중인 Agent나 실제 API 키를 변경하지 않는 격리 모드로 수행한다.

```powershell
.\scripts\fault-tests.cmd
```

특정 시험만 실행할 수도 있다.

```powershell
.\scripts\fault-tests.cmd --case FT-01
.\scripts\fault-tests.cmd --case FT-03 --case FT-06
```

| ID | 장애 상황 | 안전한 시험 방법 | 기대 결과 |
|---|---|---|---|
| FT-01 | Retriever 종료 | 사용하지 않는 로컬 Retriever 주소로 호출 | `검색 불가`와 Retriever 연결 실패 표시 |
| FT-02 | 포트 충돌 | 격리 임시 포트를 선점한 후 gRPC 바인딩 | `포트 사용 중` 표시 |
| FT-03 | CSV 파일 누락 | 존재하지 않는 시험용 경로 전달 | `CSV not found` 표시 |
| FT-04 | API 키 오류 | 시험 프로세스 안에서 키를 일시 제거 | 자격 증명 오류 표시 후 환경 복구 |
| FT-05 | 응답 지연 | 격리 Retriever를 0.5초 지연하고 0.1초 timeout 적용 | `DEADLINE_EXCEEDED` 표시 |
| FT-06 | 빈 검색 결과 | CSV에 없는 고유 검색어 전달 | VOC 직접 일치 없음, 추가 확인 필요, `ok=false` 반환 |

실제 Retriever에서 지연을 직접 재현해야 할 때만 해당 프로세스에 다음 환경변수를 적용한다.

```powershell
$env:A2A_FAULT_RETRIEVER_DELAY_MS = "2000"
python -m agents.retriever
```

시험이 끝나면 환경변수를 제거한다.

```powershell
Remove-Item Env:A2A_FAULT_RETRIEVER_DELAY_MS -ErrorAction SilentlyContinue
```

결과는 `quality_diagnosis/Reports/Fault/latest.json`과 `quality_diagnosis/Reports/Fault/latest.md`에 저장되며 실행 시각별 파일도 함께 보관된다. 실제 API 키 값, VOC 원문, 개인정보는 보고서에 기록하지 않는다.
