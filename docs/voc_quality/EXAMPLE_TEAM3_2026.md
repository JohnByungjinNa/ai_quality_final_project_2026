# 적용 예시: ai_quality_final_project_2026

`C:\qaeduc\ai_quality_final_project_Team3`의 Streamlit 대시보드를 기반으로 `C:\qaeduc\ai_quality_final_project_2026` 통합본을 만들었다.

## 적용 방식

- 기존 프로젝트 소스는 변경하지 않고 새 폴더로 복제
- `.git`, `.env`, 가상환경, 캐시, 기존 Report 제외
- `voc_quality_runtime/` 하위에 VOC 런타임 자체 포함
- 상단 `VOC 품질진단` 대메뉴와 좌측 9개 기능 추가
- Dashboard service adapter를 통해 allowlist 명령과 Report만 접근
- 원본 포트 6001~6006과 분리된 6101~6106 사용

## 검증 결과

- 전체 pytest 57개 통과
- VOC 품질진단 `all` 통과
- Streamlit health 통과
- 평문 자격 증명 0건

구체적 파일과 제한사항은 통합 프로젝트의 `docs/voc_quality/IMPLEMENTATION_REPORT.md`를 참고한다.
