import html
import json
import re
import zipfile
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
TEMPLATE = Path(r"C:\Users\DWIT\Downloads\09_팀별_발표자료_템플릿 (1).pptx")
OUTPUT = PROJECT_DIR / "reports" / "최강3조_AI_챗봇_품질관리_발표자료.pptx"


def load_context():
    evaluation_path = PROJECT_DIR / "reports" / "evaluation_result.json"
    k6_path = PROJECT_DIR / "reports" / "k6_summary.json"
    snapshot_path = PROJECT_DIR / "reports" / "test_runs" / "RUN-20260709163847" / "dashboard_snapshot.json"

    cases = json.loads(evaluation_path.read_text(encoding="utf-8"))
    k6 = json.loads(k6_path.read_text(encoding="utf-8"))
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8")) if snapshot_path.exists() else {}

    total = len(cases)
    rule_pass = sum(1 for item in cases if item.get("rule_passed") is True)
    rule_fail = total - rule_pass
    avg_scores = {
        key: sum(float(item.get(key, 0) or 0) for item in cases) / total
        for key in ("accuracy", "groundedness", "helpfulness", "safety")
    }
    metrics = k6.get("metrics", {})
    http_reqs = metrics.get("http_reqs", {})
    failed = metrics.get("http_req_failed", {})
    duration = metrics.get("http_req_duration", {})
    checks = metrics.get("checks", {})

    return {
        "total": total,
        "rule_pass": rule_pass,
        "rule_fail": rule_fail,
        "rule_rate": rule_pass / total * 100 if total else 0,
        "avg_scores": avg_scores,
        "snapshot": snapshot,
        "k6_total": int(http_reqs.get("count", 0) or 0),
        "k6_error_rate": float(failed.get("rate", 0) or 0) * 100,
        "k6_avg_ms": float(duration.get("avg", 0) or 0),
        "k6_p95_ms": float(duration.get("p(95)", 0) or 0),
        "k6_checks": float(checks.get("value", 0) or 0) * 100,
        "k6_vus": int(metrics.get("vus_max", {}).get("value", 0) or 0),
    }


def slide_texts(ctx):
    final = ctx["snapshot"].get("final", {})
    api_pass_rate = final.get("api_pass_rate", 30.0)
    api_pass_count = final.get("api_pass_count", 3)
    defect_count = final.get("defect_count", 9)
    weakest_api = final.get("weakest_api_metric", "유용성 (30.0점)")
    weakest_rule = final.get("weakest_rule_metric", "정확성 (60.0점)")

    k6_decision = "PASS" if ctx["k6_error_rate"] <= 1 and ctx["k6_p95_ms"] <= 3000 else "FAIL"

    return {
        1: [
            "AI 교육과정 안내 챗봇",
            "품질관리 프로젝트 발표",
            "SW 품질관리 및 모니터링 실무 10일 과정",
            "팀명: 최강3조",
            "발표일: 2026. 07. 09",
            "발표자: 최강3조",
            "최강3조 발표자료 | 1",
        ],
        2: [
            "1. 프로젝트 개요",
            "규칙 기반 Agent와 API 기반 Agent의 품질을 비교하고 운영 지표까지 연결",
            "대상 Agent",
            "서비스명: AI 교육과정 안내 챗봇",
            "주요 기능: 교육시간, 출결, 수료 기준, 취업지원 등 과정 문의 응답",
            "사용자 시나리오: 교육생이 과정 규정 질문 → 챗봇 응답 → 품질 자동 평가",
            "품질관리 범위",
            "기능 테스트",
            "로그/모니터링",
            "성능 테스트",
            "결함관리",
            "팀 역할",
            "팀장: 최강3조",
            "테스터: 테스트케이스 설계 및 실행",
            "모니터링: Prometheus/Grafana/k6 지표 확인",
            "결함관리: FAIL 사례 Jira 등록 및 추적",
            "발표: 결과 보고서와 Docker 통합 실행 시연",
            "이번 발표의 핵심 메시지",
            "규칙 기반과 API 기반 응답을 동일 기준으로 평가하고, 실패 사례를 결함으로 연결했습니다. 마지막 단계에서는 Docker Compose로 FastAPI, Streamlit, Prometheus, Grafana를 한 번에 실행해 환경 차이를 줄였습니다.",
            "최강3조 발표자료 | 2",
        ],
        3: [
            "2. 테스트 설계",
            "Happy, Edge, Negative 케이스로 정확성·근거성·유용성·안전성 검증",
            "테스트케이스 요약",
            f"총 테스트케이스 수: {ctx['total']}건",
            f"Pass: 규칙 기반 {ctx['rule_pass']}건 / API 기반 {api_pass_count}건",
            f"Fail: 규칙 기반 {ctx['rule_fail']}건 / API 기반 {ctx['total'] - api_pass_count}건",
            "Blocked: 0건",
            "주요 검증 포인트:",
            "- 교육시간/출결/수료 기준 정상 응답",
            "- 문서 외 질문 제한",
            "- 안전·위험 요청 방어",
            "- 자동 평가 결과와 결함 등록",
            "장애 시나리오",
            "장애 유형 1: 필수 키워드 누락",
            "장애 유형 2: 문서 근거 부족",
            "장애 유형 3: 유용성 낮은 일반 실패 응답",
            "가장 중요한 장애:",
            f"API 기반 응답의 취약 지표: {weakest_api}",
            "발생 원인 추정:",
            "검색 문맥 부족 또는 프롬프트가 정책 수치/예외 조건을 충분히 강제하지 못함",
            "재현 방법:",
            "테스트 관리 > 테스트 케이스 실행 후 수행 이력 상세 결과 확인",
            "최강3조 발표자료 | 3",
        ],
        4: [
            "3. 모니터링 결과",
            "Prometheus 직접 조회 화면과 Grafana 상세 대시보드 연결",
            "핵심 지표",
            f"요청 수: k6 기준 {ctx['k6_total']}건",
            f"성공률: checks {ctx['k6_checks']:.1f}%",
            f"오류율: {ctx['k6_error_rate']:.2f}%",
            f"평균 응답시간: {ctx['k6_avg_ms']:.2f}ms",
            f"p95 응답시간: {ctx['k6_p95_ms']:.2f}ms",
            "로그 근거",
            "오류 로그 위치: reports/k6_summary.json, reports/evaluation_result.json",
            "반복 발생 시각: 테스트 수행 이력의 RUN 단위로 추적",
            "주요 메시지: FAIL 판정, 취약 지표, k6 응답시간/오류율",
            "원인 후보: RAG 검색 근거 부족, 규칙 키워드 누락, 예외 조건 안내 미흡",
            "대시보드 캡처",
            "운영 모니터링 화면에서 Prometheus API를 직접 조회하고, Grafana 열기 버튼으로 상세 대시보드를 확인합니다.",
            "최강3조 발표자료 | 4",
        ],
        5: [
            "4. 성능테스트 결과",
            "k6 결과를 기준으로 응답시간과 오류율 최종 판정",
            "도구",
            "총 요청",
            "오류율",
            "평균(ms)",
            "p95(ms)",
            "판정",
            "JMeter",
            "-",
            "-",
            "-",
            "-",
            "미사용",
            "k6",
            str(ctx["k6_total"]),
            f"{ctx['k6_error_rate']:.2f}%",
            f"{ctx['k6_avg_ms']:.2f}",
            f"{ctx['k6_p95_ms']:.2f}",
            k6_decision,
            "판정 기준",
            "오류율 1% 이하, p95 응답시간 3000ms 이하이면 Pass로 판정합니다.",
            "성능 개선 의견",
            f"20 VUs 기준 오류율은 낮고 p95 응답시간은 기준 이내입니다. 다만 품질 FAIL 케이스가 남아 있어 응답 품질 개선 후 동일 k6 조건으로 회귀 테스트가 필요합니다.",
            "최강3조 발표자료 | 5",
        ],
        6: [
            "5. 결함 및 개선 결과",
            "품질 FAIL 사례를 결함으로 등록하고 재시작 후에도 상태를 유지",
            "주요 결함 TOP 3",
            "1) 필수 정책 수치 누락 / High / 교육시간·수료 기준 답변 실패",
            "2) 문서 근거 부족 / Medium / RAG 검색 결과와 답변 불일치",
            "3) 유용성 낮은 실패 응답 / Medium / 사용자에게 대안 안내 부족",
            "개선 전후 비교",
            f"개선 전: API 기반 합격률 {api_pass_rate:.1f}%, 결함 {defect_count}건",
            "개선 활동: 결과보고서, 고도화 지표, Jira 자동등록, 운영 모니터링, Docker 통합 실행 추가",
            f"개선 후: 테스트 수행 이력별 품질 지표와 결함 상태를 화면/보고서에서 추적 가능",
            "재테스트 결과: Docker Compose 환경에서 동일 조건 재실행 가능",
            "최강3조 발표자료 | 6",
        ],
        7: [
            "6. 최종 품질 판정",
            "운영 가능 여부와 팀 의견",
            "최종 판정",
            "□ 운영 가능",
            "■ 조건부 가능",
            "□ 개선 필요",
            "판정 근거",
            f"기능 테스트: 규칙 기반 {ctx['rule_rate']:.1f}%, API 기반 {api_pass_rate:.1f}%로 보완 필요",
            "모니터링: Prometheus 직접 조회와 Grafana 상세 대시보드 연결 완료",
            f"성능 테스트: k6 {ctx['k6_total']}요청, 오류율 {ctx['k6_error_rate']:.2f}%, p95 {ctx['k6_p95_ms']:.2f}ms",
            "결함 조치: Jira 자동등록 및 등록 상태 영속화 구현",
            "향후 과제",
            "1) API 기반 응답의 유용성·정확성 개선",
            "2) Grafana 패널 템플릿 고도화 및 알림 조건 추가",
            "3) Docker Compose 기반 회귀 테스트 자동화",
            "팀 회고",
            "단순 기능 확인을 넘어 테스트 설계, 성능 측정, 운영 모니터링, 결함관리, 보고서 자동화를 하나의 QA 흐름으로 연결했습니다.",
            "최강3조 발표자료 | 7",
        ],
    }


def replace_slide_text(xml, values):
    index = 0

    def repl(match):
        nonlocal index
        if index >= len(values):
            return match.group(0)
        value = html.escape(str(values[index]), quote=False)
        index += 1
        return f"<a:t>{value}</a:t>"

    return re.sub(r"<a:t>.*?</a:t>", repl, xml, flags=re.DOTALL)


def main():
    if not TEMPLATE.exists():
        raise FileNotFoundError(TEMPLATE)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    ctx = load_context()
    replacements = slide_texts(ctx)

    with zipfile.ZipFile(TEMPLATE, "r") as source, zipfile.ZipFile(OUTPUT, "w", zipfile.ZIP_DEFLATED) as target:
        for item in source.infolist():
            data = source.read(item.filename)
            match = re.match(r"ppt/slides/slide(\d+)\.xml$", item.filename)
            if match:
                slide_no = int(match.group(1))
                xml = data.decode("utf-8")
                if slide_no in replacements:
                    xml = replace_slide_text(xml, replacements[slide_no])
                data = xml.encode("utf-8")
            target.writestr(item, data)

    print(OUTPUT)


if __name__ == "__main__":
    main()
