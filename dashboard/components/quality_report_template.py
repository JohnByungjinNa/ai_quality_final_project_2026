from collections import Counter, defaultdict
from html import escape

import streamlit as st

from quality_criteria import get_quality_criteria


METRICS = (
    ("accuracy", "정확성", "질문 의도와 기대 정책에 맞는 정확한 답변 제공"),
    ("groundedness", "근거성", "제공된 정책과 검색 근거에 기반한 답변 제공"),
    ("helpfulness", "유용성", "사용자 문제 해결에 도움이 되는 안내 제공"),
    ("safety", "안전성", "위험하거나 부적절한 내용 없이 안전하게 응답"),
)

VOC_DISPLAY_LABELS = {
    "PASS": "통과",
    "FAIL": "실패",
    "ERROR": "오류",
    "REVIEW": "검토 필요",
    "REVIEW_REQUIRED": "검토 필요",
    "NOT_RUN": "미실행",
    "AI_PASS": "AI 평가 통과",
    "AI_REVIEWED": "AI 평가 완료",
    "QA_REVIEWED": "QA 검토 완료",
    "BUSINESS_APPROVED": "업무 승인 완료",
    "BUSINESS_REVIEW_REQUIRED": "업무 검토 필요",
    "HUMAN_REVIEW_REQUIRED": "사람 검토 필요",
    "REMAINING_CASE_REVIEW_REQUIRED": "잔여 케이스 검토 필요",
    "FORMAL_QUALITY_APPROVED": "정식 품질 승인",
    "PARTIALLY_APPROVED": "부분 승인",
    "DRAFT": "작성 중",
    "REJECTED": "반려",
    "REVISION_REQUIRED": "수정 필요",
    "HOLD": "보류",
    "NEEDS_IMPROVEMENT": "보완 필요",
    "NOT_APPROVED": "승인되지 않음",
    "FORMAL_APPROVED": "정식 승인",
    "EVIDENCE_DRAFT": "증적 초안",
    "FINAL": "최종 보고서",
    "BATCH": "일괄 수행",
    "MANUAL": "수동 수행",
    "RETEST": "재시험",
    "BASELINE": "기준선",
    "COMPLETED": "완료",
    "RUNNING": "실행 중",
    "STOPPED": "중지",
    "INTERRUPTED": "중단",
    "PENDING": "대기",
    "OPEN": "미해결",
    "CLOSED": "종료",
    "RESOLVED": "해결",
    "ANALYZED": "분석 완료",
    "CONFIRMED": "확정",
    "FIXED": "수정 완료",
    "RETESTED": "재시험 완료",
    "SUCCESS": "성공",
    "CONFIGURED": "설정 완료",
    "NOT_CONFIGURED": "미설정",
    "CRITICAL": "치명",
    "HIGH": "높음",
    "MEDIUM": "보통",
    "LOW": "낮음",
    "UNKNOWN": "확인 필요",
    "Evaluator": "내부 평가자",
    "Critic": "위험 검토자",
    "독립 LLM Judge": "독립 AI 평가자",
    "LLM Judge": "독립 AI 평가자",
    "Agent": "에이전트",
    "Pipeline": "파이프라인",
    "Rubric": "평가 기준",
    "Catalog": "테스트 목록",
    "Artifact": "증적 파일",
    "Trace": "추적",
    "Case": "케이스",
    "Run": "실행",
}


def _voc_display_label(value):
    text = str(value if value not in (None, "") else "-")
    return VOC_DISPLAY_LABELS.get(text, text)


def _voc_display_text(value):
    text = str(value if value not in (None, "") else "-")
    for code in sorted(VOC_DISPLAY_LABELS, key=len, reverse=True):
        text = text.replace(code, VOC_DISPLAY_LABELS[code])
    return text


def _voc_count_summary(counts):
    if not counts:
        return "평가 결과 없음"
    return " · ".join(
        f"{_voc_display_label(key)} {int(value or 0)}건"
        for key, value in counts.items()
    )


def _score(value):
    if isinstance(value, dict):
        value = value.get("score", 0)
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _evaluation(case, agent_key):
    return case.get(agent_key, {}).get("evaluation_result", {})


def _is_metric_evaluated(case, agent_key, metric_key):
    value = _evaluation(case, agent_key).get(metric_key, {})
    if agent_key == "rule_based" and isinstance(value, dict) and "evaluated" not in value:
        return metric_key == "accuracy"
    return not isinstance(value, dict) or value.get("evaluated", True) is not False


def _decision(case, agent_key):
    return str(_evaluation(case, agent_key).get("overall_decision", "FAIL") or "FAIL").upper()


def _summary(case, agent_key):
    evaluation = _evaluation(case, agent_key)
    return str(evaluation.get("summary") or evaluation.get("comment") or "")


def build_agent_report_model(pipeline_outputs, agent_key, quality_criteria=None, metadata=None):
    criteria = get_quality_criteria(quality_criteria)
    cases = list(pipeline_outputs or [])
    metadata = dict(metadata or {})
    agent_label = "규칙 기반" if agent_key == "rule_based" else "API 기반"
    decisions = [_decision(case, agent_key) for case in cases]
    decision_counts = Counter(decisions)
    total = len(cases)
    passed = decision_counts["PASS"]
    review = decision_counts["REVIEW"]
    failed = decision_counts["FAIL"]
    pass_rate = round(passed / total * 100, 1) if total else 0.0
    pass_threshold = (
        criteria.rule_pass_rate_min if agent_key == "rule_based" else criteria.api_pass_rate_min
    )

    metric_rows = []
    for metric_key, label, description in METRICS:
        scores = [
            _score(_evaluation(case, agent_key).get(metric_key, 0))
            for case in cases
            if _is_metric_evaluated(case, agent_key, metric_key)
        ]
        average_5 = round(sum(scores) / len(scores), 2) if scores else None
        score_100 = round(average_5 / 5 * 100, 1) if average_5 is not None else None
        metric_rows.append(
            {
                "key": metric_key,
                "label": label,
                "description": description,
                "average_5": average_5,
                "score_100": score_100,
                "evaluated_count": len(scores),
                "status": "평가 제외" if score_100 is None else "양호" if score_100 >= 80 else "개선 필요",
            }
        )

    grouped = defaultdict(list)
    for case in cases:
        grouped[str(case.get("test_type") or case.get("category") or "기타")].append(case)
    type_rows = []
    for type_name, type_cases in sorted(grouped.items()):
        type_passed = sum(1 for case in type_cases if _decision(case, agent_key) == "PASS")
        count = len(type_cases)
        type_rows.append(
            {
                "type": type_name,
                "total": count,
                "passed": type_passed,
                "failed": count - type_passed,
                "rate": round(type_passed / count * 100, 1) if count else 0.0,
            }
        )

    case_rows = []
    defects = []
    for case in cases:
        evaluation = _evaluation(case, agent_key)
        decision = _decision(case, agent_key)
        answer = str(case.get(agent_key, {}).get("ai_answer", "") or "")
        reason = _summary(case, agent_key)
        row = {
            "case_id": str(case.get("case_id", "")),
            "type": str(case.get("test_type") or case.get("category") or "기타"),
            "category": str(case.get("category") or "미분류"),
            "question": str(case.get("user_question", "")),
            "answer": answer,
            "decision": decision,
            "reason": reason,
        }
        case_rows.append(row)
        if decision != "PASS":
            safety = _score(evaluation.get("safety", 0))
            severity = "Critical" if safety and safety < criteria.safety_critical_min else "High" if decision == "FAIL" else "Medium"
            defects.append(
                {
                    "id": f"{agent_key.upper()}-{len(defects) + 1:03d}",
                    "case_id": row["case_id"],
                    "title": reason or f"{row['category']} 품질 기준 미달",
                    "severity": severity,
                    "type": row["type"],
                    "status": "Open",
                    "summary": f"{row['question']} — {reason or '평가 사유를 확인해 주세요.'}",
                }
            )

    evaluated_metric_scores = [row["score_100"] for row in metric_rows if row["score_100"] is not None]
    average_score = round(sum(evaluated_metric_scores) / len(evaluated_metric_scores), 1) if evaluated_metric_scores else 0.0
    safety_row = next(row for row in metric_rows if row["key"] == "safety")
    safety_ok = agent_key == "rule_based" or (
        safety_row["average_5"] is not None and safety_row["average_5"] >= criteria.safety_avg_min
    )
    passed_gate = total > 0 and pass_rate >= pass_threshold and safety_ok

    weakest = sorted(
        (row for row in metric_rows if row["score_100"] is not None),
        key=lambda row: row["score_100"],
    )
    recommendations = []
    if defects:
        recommendations.append("미통과 케이스의 질문·답변·평가 사유를 우선 검토하고 회귀 테스트를 수행하세요.")
    if weakest and weakest[0]["score_100"] < 80:
        recommendations.append(f"가장 낮은 {weakest[0]['label']} 지표의 프롬프트와 검색 근거를 보강하세요.")
    if agent_key == "rule_based":
        recommendations.append("규칙 기반 평가는 기대 키워드 정확성만 판정하므로 다른 품질 지표는 API 평가와 함께 확인하세요.")
    elif not safety_ok:
        recommendations.append("안전성 기준 미달 사례를 분석해 차단 정책과 안전 응답 지침을 강화하세요.")
    if not recommendations:
        recommendations.append("현재 기준을 충족했습니다. 기준을 유지하며 신규·경계 사례를 지속 추가하세요.")

    return {
        "agent_key": agent_key,
        "agent_label": agent_label,
        "title": f"{agent_label} 챗봇 품질 테스트 결과 보고서",
        "subtitle": (
            "기대 키워드 포함 여부를 기준으로 응답 정확성을 검증한 결과입니다."
            if agent_key == "rule_based"
            else "정확성·근거성·유용성·안전성을 종합적으로 검증한 결과입니다."
        ),
        "metadata": {
            "실행 ID": metadata.get("run_id", "-"),
            "수행일자": metadata.get("executed_at", "-"),
            "테스트 대상": metadata.get("target_files", "-"),
            "판정 단계": criteria.stage_label,
        },
        "total": total,
        "passed": passed,
        "review": review,
        "failed": failed,
        "not_passed": review + failed,
        "pass_rate": pass_rate,
        "pass_threshold": pass_threshold,
        "average_score": average_score,
        "passed_gate": passed_gate,
        "final_label": "기준 충족" if passed_gate else "개선 필요",
        "final_reason": (
            "합격률과 핵심 품질 기준을 충족했습니다."
            if passed_gate
            else "합격률 또는 핵심 품질 지표가 기준에 미달했습니다."
        ),
        "metric_rows": metric_rows,
        "type_rows": type_rows,
        "case_rows": case_rows,
        "defects": defects,
        "recommendations": recommendations,
    }


def _icon(name):
    paths = {
        "clipboard": "<rect x='6' y='5' width='12' height='16' rx='2'/><path d='M9 5V3h6v2M9 10h6M9 14h6M9 18h4'/>",
        "check": "<circle cx='12' cy='12' r='9'/><path d='m8 12 3 3 6-7'/>",
        "fail": "<circle cx='12' cy='12' r='9'/><path d='m9 9 6 6m0-6-6 6'/>",
        "target": "<circle cx='11' cy='13' r='8'/><circle cx='11' cy='13' r='4'/><path d='m14 10 7-7m-4 0h4v4'/>",
        "shield": "<path d='M12 3 4 6v6c0 5 3.4 8.3 8 10 4.6-1.7 8-5 8-10V6l-8-3Z'/><path d='m8.5 12 2.2 2.2 4.8-5'/>",
        "database": "<ellipse cx='12' cy='5' rx='8' ry='3'/><path d='M4 5v6c0 1.7 3.6 3 8 3s8-1.3 8-3V5M4 11v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6'/>",
    }
    return (
        "<svg viewBox='0 0 24 24' aria-hidden='true' fill='none' stroke='currentColor' "
        "stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'>"
        + paths[name]
        + "</svg>"
    )


def _decision_badge(decision):
    label = {"PASS": "Pass", "REVIEW": "Review", "FAIL": "Fail"}.get(decision, decision)
    return f"<span class='qrt-badge qrt-{decision.lower()}'>{escape(label)}</span>"


def _display_score(value, decimals=1):
    return "N/A" if value is None else f"{value:.{decimals}f}"


def build_comparison_summary_html(
    rule_rate,
    rule_passed_count,
    api_rate,
    api_passed_count,
    total_count,
    release_decision,
    release_reason,
):
    decision_class = "good" if release_decision == "배포 가능" else "warn" if release_decision == "조건부 배포" else "bad"
    cards = (
        (
            "target",
            "규칙 기반 합격률",
            f"{float(rule_rate):.1f}<small>%</small>",
            f"{int(rule_passed_count)}/{int(total_count)}",
            "",
        ),
        (
            "check",
            "API 기반 합격률",
            f"{float(api_rate):.1f}<small>%</small>",
            f"{int(api_passed_count)}/{int(total_count)}",
            "",
        ),
        (
            "shield",
            "최종 판정",
            escape(str(release_decision)),
            escape(str(release_reason)),
            decision_class,
        ),
    )
    card_html = "".join(
        f"<article class='qcs-card {status}'><div class='qcs-icon'>{_icon(icon)}</div>"
        f"<div class='qcs-copy'><span>{escape(label)}</span><strong>{value}</strong><small>{note}</small></div></article>"
        for icon, label, value, note, status in cards
    )
    return f"""
    <style>
    .qcs-row{{font-family:'Malgun Gothic','Apple SD Gothic Neo',sans-serif;display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin:12px 0 18px;color:#15243b}}
    .qcs-card{{min-height:106px;border:1px solid #c8d9ee;border-radius:7px;background:linear-gradient(145deg,#fff,#f8fbff);display:flex;align-items:center;gap:14px;padding:15px 17px;box-shadow:0 4px 13px rgba(22,78,128,.06);box-sizing:border-box}}
    .qcs-icon{{width:43px;min-width:43px;color:#0e4a80}}.qcs-icon svg{{width:100%;height:auto}}
    .qcs-copy{{min-width:0}}.qcs-copy>span{{display:block;color:#40536d;font-size:12px;font-weight:700}}
    .qcs-copy>strong{{display:block;color:#073b72;font-size:26px;line-height:1.15;margin:5px 0 2px;white-space:nowrap}}
    .qcs-copy>strong small{{font-size:15px;font-weight:600}}.qcs-copy>small{{display:block;color:#627087;font-size:11px;line-height:1.35}}
    .qcs-card.good .qcs-icon,.qcs-card.good strong{{color:#299049}}.qcs-card.warn .qcs-icon,.qcs-card.warn strong{{color:#b36a08}}.qcs-card.bad .qcs-icon,.qcs-card.bad strong{{color:#e13f3b}}
    @media(max-width:780px){{.qcs-row{{grid-template-columns:1fr}}}}
    </style>
    <div class="qcs-row">{card_html}</div>
    """


def build_agent_report_html(model):
    total = max(model["total"], 1)
    pass_deg = model["passed"] / total * 360
    review_deg = model["review"] / total * 360
    donut_style = (
        f"background:conic-gradient(#155A96 0 {pass_deg:.2f}deg,"
        f"#5599D2 {pass_deg:.2f}deg {pass_deg + review_deg:.2f}deg,"
        f"#A9CAE7 {pass_deg + review_deg:.2f}deg 360deg)"
    )
    final_class = "good" if model["passed_gate"] else "bad"

    metadata_rows = "".join(
        f"<div><b>{escape(str(key))}</b><span>{escape(str(value))}</span></div>"
        for key, value in model["metadata"].items()
    )
    cards = (
        ("clipboard", "전체 테스트 케이스", f"{model['total']}<small>건</small>", ""),
        ("check", "통과 (Pass)", f"{model['passed']}<small>건</small>", f"{model['pass_rate']:.1f}%"),
        ("fail", "미통과", f"{model['not_passed']}<small>건</small>", f"Review {model['review']} · Fail {model['failed']}"),
        ("target", "합격 기준", f"{model['pass_threshold']:g}<small>% 이상</small>", ""),
        ("shield", "최종 판정", model["final_label"], model["final_reason"]),
    )
    card_html = "".join(
        f"<div class='qrt-kpi {final_class if index == 4 else ''}'><div class='qrt-icon'>{_icon(icon)}</div>"
        f"<div><span>{escape(label)}</span><strong>{value}</strong><small>{escape(note)}</small></div></div>"
        for index, (icon, label, value, note) in enumerate(cards)
    )

    type_bars = "".join(
        f"<div class='qrt-rate-row'><span>{escape(row['type'])}</span><div><i style='width:{row['rate']:.1f}%'></i></div>"
        f"<b>{row['rate']:.1f}%</b></div>"
        for row in model["type_rows"]
    ) or "<p class='qrt-empty'>표시할 유형 데이터가 없습니다.</p>"

    metric_bars = "".join(
        f"<div class='qrt-metric-bar'><b>{escape(row['label'])}</b><div><i style='height:{max(row['score_100'] or 0, 2):.1f}%'></i></div>"
        f"<span>{_display_score(row['score_100'], 0)}</span></div>"
        for row in model["metric_rows"]
    )
    type_table_rows = "".join(
        f"<tr><td>{escape(row['type'])}</td><td>{row['total']}</td><td>{row['passed']}</td>"
        f"<td>{row['failed']}</td><td class='{'qrt-green' if row['rate'] >= model['pass_threshold'] else 'qrt-red'}'>{row['rate']:.1f}%</td></tr>"
        for row in model["type_rows"]
    ) or "<tr><td colspan='5'>데이터 없음</td></tr>"
    metric_table_rows = "".join(
        f"<tr><td><b>{escape(row['label'])}</b></td><td>{escape(row['description'])}</td>"
        f"<td>{_display_score(row['score_100'])}</td>"
        f"<td><span class='qrt-dot {'off' if row['score_100'] is None else 'warn' if row['score_100'] < 80 else ''}'></span>{escape(row['status'])}</td></tr>"
        for row in model["metric_rows"]
    )
    case_table_rows = "".join(
        f"<tr><td><b>{escape(row['case_id'])}</b></td><td>{escape(row['type'])}</td><td>{escape(row['category'])}</td>"
        f"<td>{escape(row['question'])}</td><td>{escape(row['answer'])}</td>"
        f"<td>{_decision_badge(row['decision'])}</td><td>{escape(row['reason'] or '-')}</td></tr>"
        for row in model["case_rows"]
    ) or "<tr><td colspan='7'>테스트 결과가 없습니다.</td></tr>"
    defect_rows = "".join(
        f"<tr><td><b>{escape(row['id'])}</b></td><td>{escape(row['case_id'])}</td><td>{escape(row['title'])}</td>"
        f"<td><span class='qrt-severity'>{escape(row['severity'])}</span></td><td>{escape(row['type'])}</td>"
        f"<td><span class='qrt-open'>{escape(row['status'])}</span></td><td>{escape(row['summary'])}</td></tr>"
        for row in model["defects"]
    ) or "<tr><td colspan='7' class='qrt-green'>등록할 주요 결함이 없습니다.</td></tr>"
    recommendations = "".join(
        f"<li>{_icon('target' if index == 0 else 'shield' if index == 1 else 'database')}<span>{escape(text)}</span></li>"
        for index, text in enumerate(model["recommendations"])
    )

    style = """
    <style>
    .qrt-report{font-family:'Malgun Gothic','Apple SD Gothic Neo',sans-serif;color:#15243b;background:#fff;border:1px solid #c8d9ee;padding:22px;line-height:1.45}.qrt-report *{box-sizing:border-box}.qrt-head{display:grid;grid-template-columns:1fr 330px;gap:28px;align-items:start;margin-bottom:18px}.qrt-head h1{margin:4px 0 9px;color:#0c3768;font-size:29px;letter-spacing:-1.2px}.qrt-head p{margin:0;color:#40536d;font-size:13px}.qrt-meta{border:1px solid #c8d8eb;font-size:12px}.qrt-meta div{display:grid;grid-template-columns:105px 1fr;border-bottom:1px solid #d9e5f2}.qrt-meta div:last-child{border:0}.qrt-meta b{background:#edf3fa;padding:7px 9px}.qrt-meta span{padding:7px 10px}.qrt-section{margin:15px 0;border:1px solid #9ebde0;border-radius:5px;padding:20px 16px 14px;position:relative}.qrt-section-title{display:inline-block;margin:-21px 0 16px -17px;padding:7px 16px;background:linear-gradient(90deg,#0b4f91,#176aab);color:#fff;font-weight:800;border-radius:5px 5px 0 0;font-size:15px}.qrt-kpis{display:grid;grid-template-columns:repeat(5,1fr);gap:11px}.qrt-kpi{min-height:105px;border:1px solid #d6e2f0;border-radius:6px;display:flex;align-items:center;gap:12px;padding:14px;background:linear-gradient(145deg,#fff,#f9fbfe)}.qrt-kpi .qrt-icon{width:40px;color:#0e4a80;flex:0 0 40px}.qrt-icon svg,.qrt-recommend svg{width:100%;height:auto}.qrt-kpi span{display:block;font-size:12px;font-weight:700}.qrt-kpi strong{display:block;color:#073b72;font-size:25px;margin:5px 0 1px}.qrt-kpi strong small{font-size:14px;font-weight:500}.qrt-kpi small{font-size:11px;color:#627087}.qrt-kpi.bad strong{color:#e13f3b}.qrt-kpi.good strong{color:#299049}.qrt-charts{display:grid;grid-template-columns:1fr 1.25fr 1.2fr;border:1px solid #d4e1ef;border-radius:5px;margin-top:12px}.qrt-chart{padding:12px 18px;min-height:205px;border-right:1px solid #dce6f1}.qrt-chart:last-child{border:0}.qrt-chart h3{text-align:center;margin:0 0 13px;font-size:13px}.qrt-donut-wrap{display:flex;align-items:center;justify-content:center;gap:20px}.qrt-donut{width:120px;height:120px;border-radius:50%;display:grid;place-items:center}.qrt-donut:after{content:'';width:64px;height:64px;background:#fff;border-radius:50%;position:absolute}.qrt-donut{position:relative}.qrt-donut b{z-index:1;text-align:center;font-size:12px}.qrt-legend div{font-size:11px;margin:8px 0}.qrt-legend i{display:inline-block;width:10px;height:10px;margin-right:7px}.qrt-metric-bars{height:145px;display:flex;align-items:flex-end;justify-content:space-around;border-bottom:1px solid #8095ac;padding:0 10px}.qrt-metric-bar{text-align:center;width:22%}.qrt-metric-bar>div{height:110px;background:#edf2f8;display:flex;align-items:flex-end;margin:0 auto 5px;width:34px}.qrt-metric-bar i{display:block;width:100%;background:linear-gradient(#2f73bb,#145598)}.qrt-metric-bar b{display:block;font-size:10px;margin-bottom:4px}.qrt-metric-bar span{font-size:11px;color:#164f89}.qrt-rate-row{display:grid;grid-template-columns:70px 1fr 48px;gap:7px;align-items:center;margin:13px 0;font-size:11px}.qrt-rate-row>div{height:18px;background:#e8f0f8;border:1px solid #d7e4f1}.qrt-rate-row i{display:block;height:100%;background:linear-gradient(90deg,#0F4C81,#2E78B7 58%,#5EA1D7)}.qrt-rate-row b{text-align:right;color:#123F6D}.qrt-two{display:grid;grid-template-columns:0.85fr 1.7fr;gap:16px}.qrt-subtitle{color:#0a4b88;font-size:13px;margin:0 0 8px}.qrt-table-wrap{overflow:auto}.qrt-table{width:100%;border-collapse:collapse;font-size:11px}.qrt-table th{background:linear-gradient(#edf4fb,#dfeaf6);color:#173e69;font-weight:800}.qrt-table th,.qrt-table td{border:1px solid #cbd9e8;padding:7px 8px;vertical-align:top}.qrt-table tr:nth-child(even) td{background:#fbfdff}.qrt-green{color:#279445!important;font-weight:700}.qrt-red{color:#e03f36!important;font-weight:700}.qrt-badge,.qrt-severity,.qrt-open{display:inline-block;border-radius:999px;padding:2px 8px;font-weight:700;white-space:nowrap}.qrt-pass{color:#248c46;background:#e4f6e9}.qrt-review{color:#b26a0a;background:#fff3da}.qrt-fail{color:#d83f36;background:#fde8e6}.qrt-severity{color:#d83f36;background:#fde8e6}.qrt-open{color:#bf7000;background:#fff1d3}.qrt-dot{display:inline-block;width:9px;height:9px;border-radius:50%;background:#43a65b;margin-right:6px}.qrt-dot.warn{background:#f39a3d}.qrt-dot.off{background:#9caabd}.qrt-bottom{display:grid;grid-template-columns:1.05fr .95fr;gap:16px}.qrt-opinion,.qrt-recommend{border:1px solid #a8c2df;padding:15px;min-height:135px}.qrt-opinion p{margin:7px 0;font-size:12px}.qrt-conclusion{font-size:15px!important;color:#084f92;font-weight:800}.qrt-recommend ul{list-style:none;padding:0;margin:0}.qrt-recommend li{display:grid;grid-template-columns:32px 1fr;gap:10px;align-items:center;margin:8px 0;font-size:11px}.qrt-recommend svg{color:#0b568f}.qrt-empty{color:#77869a;text-align:center}@media(max-width:900px){.qrt-head{grid-template-columns:1fr}.qrt-kpis{grid-template-columns:repeat(2,1fr)}.qrt-charts,.qrt-two,.qrt-bottom{grid-template-columns:1fr}.qrt-chart{border-right:0;border-bottom:1px solid #dce6f1}.qrt-report{padding:14px}.qrt-head h1{font-size:23px}}
    </style>
    """

    return style + f"""
    <div class="qrt-report">
      <header class="qrt-head"><div><h1>{escape(model['title'])}</h1><p>{escape(model['subtitle'])}</p></div><div class="qrt-meta">{metadata_rows}</div></header>
      <section class="qrt-section"><div class="qrt-section-title">1. 테스트 요약 (Summary)</div><div class="qrt-kpis">{card_html}</div>
        <div class="qrt-charts">
          <div class="qrt-chart"><h3>판정 결과</h3><div class="qrt-donut-wrap"><div class="qrt-donut" style="{donut_style}"><b>합계<br>{model['total']}건</b></div><div class="qrt-legend"><div><i style="background:#155A96"></i>Pass {model['passed']}건</div><div><i style="background:#5599D2"></i>Review {model['review']}건</div><div><i style="background:#A9CAE7"></i>Fail {model['failed']}건</div></div></div></div>
          <div class="qrt-chart"><h3>품질 항목별 점수 (100점 환산)</h3><div class="qrt-metric-bars">{metric_bars}</div></div>
          <div class="qrt-chart"><h3>유형별 성공률</h3>{type_bars}</div>
        </div>
      </section>
      <section class="qrt-section"><div class="qrt-section-title">2. 테스트 결과 상세</div><div class="qrt-two">
        <div><h3 class="qrt-subtitle">테스트 케이스 결과 요약</h3><div class="qrt-table-wrap"><table class="qrt-table"><thead><tr><th>유형</th><th>케이스</th><th>통과</th><th>미통과</th><th>성공률</th></tr></thead><tbody>{type_table_rows}</tbody></table></div></div>
        <div><h3 class="qrt-subtitle">주요 품질 항목 평가 결과</h3><div class="qrt-table-wrap"><table class="qrt-table"><thead><tr><th>품질 항목</th><th>설명</th><th>점수</th><th>평가</th></tr></thead><tbody>{metric_table_rows}</tbody></table></div></div>
      </div></section>
      <section class="qrt-section"><div class="qrt-section-title">3. 테스트 케이스 결과 목록</div><div class="qrt-table-wrap"><table class="qrt-table"><thead><tr><th>TC ID</th><th>유형</th><th>카테고리</th><th>질문</th><th>실제 답변</th><th>결과</th><th>평가 사유</th></tr></thead><tbody>{case_table_rows}</tbody></table></div></section>
      <section class="qrt-section"><div class="qrt-section-title">4. 주요 결함 요약</div><div class="qrt-table-wrap"><table class="qrt-table"><thead><tr><th>BUG ID</th><th>발생 TC</th><th>결함 제목</th><th>심각도</th><th>발생 유형</th><th>상태</th><th>요약</th></tr></thead><tbody>{defect_rows}</tbody></table></div></section>
      <div class="qrt-bottom"><section class="qrt-opinion"><h3 class="qrt-subtitle">5. 종합 평가 및 의견</h3><p>✓ 전체 성공률은 <b>{model['pass_rate']:.1f}%</b>, 적용 합격 기준은 <b>{model['pass_threshold']:g}%</b>입니다.</p><p>✓ 평가 지표 평균은 <b>{model['average_score']:.1f}점</b>입니다.</p><p class="qrt-conclusion">→ 결론: {escape(model['final_label'])} — {escape(model['final_reason'])}</p></section><section class="qrt-recommend"><h3 class="qrt-subtitle">6. 개선 권고 사항</h3><ul>{recommendations}</ul></section></div>
    </div>
    """


def build_voc_quality_report_html(model):
    """Render VOC evidence with the same report layout used by the chatbot report."""
    run = model.get("run", {})
    counts = run.get("counts", {})
    evaluation = model.get("evaluation", {})
    integrity = model.get("integrity", {})
    claims = model.get("claims", {})
    coverage = model.get("coverage", [])
    defects = model.get("defects", [])
    risks = model.get("risks", [])
    roles = model.get("roles", [])

    status_keys = ("PASS", "FAIL", "ERROR", "REVIEW_REQUIRED", "NOT_RUN")
    total = int(run.get("selected_count") or sum(int(counts.get(key, 0) or 0) for key in status_keys))
    passed = int(counts.get("PASS", 0) or 0)
    failed = int(counts.get("FAIL", 0) or 0)
    errors = int(counts.get("ERROR", 0) or 0)
    review = int(counts.get("REVIEW_REQUIRED", 0) or 0)
    not_run = int(counts.get("NOT_RUN", 0) or 0)
    pass_rate = round(passed / total * 100, 1) if total else 0.0
    final_approved = model.get("release_decision") == "FORMAL_APPROVED"
    final_class = "good" if final_approved else "bad"

    metadata = {
        "보고서 ID": model.get("report_id", "-"),
        "생성 일시": model.get("generated_at", "-"),
        "실행 ID": run.get("run_id", "-"),
        "테스트 묶음 / 목록": f"{run.get('suite_id') or '-'} / {run.get('catalog_version') or '-'}",
        "실행 유형": _voc_display_label(run.get("run_type")),
    }
    metadata_rows = "".join(
        f"<div><b>{escape(str(key))}</b><span>{escape(str(value))}</span></div>"
        for key, value in metadata.items()
    )
    cards = (
        ("clipboard", "전체 테스트 케이스", f"{total}<small>건</small>", ""),
        ("check", "통과", f"{passed}<small>건</small>", f"{pass_rate:.1f}%"),
        (
            "fail",
            "미완료·미통과",
            f"{failed + errors + review + not_run}<small>건</small>",
            f"실패 {failed} · 오류 {errors} · 검토 {review} · 미실행 {not_run}",
        ),
        (
            "database",
            "증적 무결성",
            "정상" if integrity.get("ok") else "확인 필요",
            "실행·케이스·증적 파일 대조 결과",
        ),
        (
            "shield",
            "최종 판정",
            _voc_display_label(model.get("release_decision", "NOT_APPROVED")),
            "정식 승인" if final_approved else "승인 조건 보완 필요",
        ),
    )
    card_html = "".join(
        f"<div class='qrt-kpi {final_class if index == 4 else ''}'><div class='qrt-icon'>{_icon(icon)}</div>"
        f"<div><span>{escape(label)}</span><strong>{value}</strong><small>{escape(note)}</small></div></div>"
        for index, (icon, label, value, note) in enumerate(cards)
    )

    status_values = (
        ("통과", passed, "#155A96"),
        ("실패", failed, "#3578B3"),
        ("오류", errors, "#5599D2"),
        ("검토 필요", review, "#7EAFD8"),
        ("미실행", not_run, "#A9CAE7"),
    )
    cursor = 0.0
    gradient_parts = []
    legend_rows = []
    denominator = max(total, 1)
    for label, value, color in status_values:
        start = cursor
        cursor += value / denominator * 360
        gradient_parts.append(f"{color} {start:.2f}deg {cursor:.2f}deg")
        legend_rows.append(f"<div><i style='background:{color}'></i>{escape(label)} {value}건</div>")
    donut_style = "background:conic-gradient(" + ",".join(gradient_parts) + ")"

    stage_rows = (
        (
            "1단계 · VOC 분석 및 개선안",
            len(evaluation.get("voc_examples", [])),
            total,
            "대표 산출물·개선안 연결",
        ),
        (
            "2단계 · 6개 에이전트 내부 진단",
            int(evaluation.get("trace_cases", 0) or 0),
            total,
            f"추적 이벤트 {int(evaluation.get('trace_events', 0) or 0)}건",
        ),
        (
            "3단계 · 독립 AI 평가",
            int(evaluation.get("judge_evaluated", 0) or 0),
            total,
            _voc_count_summary(evaluation.get("judge_counts", {})),
        ),
        (
            "4단계 · 개선안 타당성",
            int(evaluation.get("validity_evaluated", 0) or 0),
            total,
            _voc_count_summary(evaluation.get("validity_counts", {})),
        ),
    )
    stage_bars = "".join(
        f"<div class='qrt-rate-row qrt-stage-row'><span>{escape(label)}</span>"
        f"<div><i style='width:{(value / max(expected, 1) * 100):.1f}%'></i></div>"
        f"<b>{value}/{expected}</b><small>{escape(note)}</small></div>"
        for label, value, expected, note in stage_rows
    )
    coverage_bars = "".join(
        f"<div class='qrt-rate-row'><span>{escape(str(row.get('group', '-')))}</span>"
        f"<div><i style='width:{(int(row.get('selected', 0) or 0) / max(int(row.get('expected', 0) or 0), 1) * 100):.1f}%'></i></div>"
        f"<b>{int(row.get('selected', 0) or 0)}/{int(row.get('expected', 0) or 0)}</b></div>"
        for row in coverage
    ) or "<p class='qrt-empty'>표시할 점검 범위가 없습니다.</p>"
    coverage_rows = "".join(
        "<tr>"
        f"<td><b>{escape(str(row.get('group', '-')))}</b></td>"
        f"<td>{int(row.get('selected', 0) or 0)}/{int(row.get('expected', 0) or 0)}</td>"
        f"<td>{int(row.get('PASS', 0) or 0)}</td><td>{int(row.get('FAIL', 0) or 0)}</td>"
        f"<td>{int(row.get('ERROR', 0) or 0)}</td><td>{int(row.get('REVIEW_REQUIRED', 0) or 0)}</td>"
        f"<td>{int(row.get('NOT_RUN', 0) or 0)}</td></tr>"
        for row in coverage
    ) or "<tr><td colspan='7'>점검 범위 데이터가 없습니다.</td></tr>"

    claim_verified = bool(claims.get("improvement_verified"))
    baseline = claims.get("baseline", {})
    final = claims.get("final", {})
    claim_rows = (
        (
            "기준선 실행",
            "검증 완료" if baseline.get("verified") else "미검증",
            _voc_display_text("; ".join(baseline.get("errors", [])) or "33건 통과 / 2건 실패 조건 확인"),
        ),
        (
            "최종 실행",
            "검증 완료" if final.get("verified") else "미검증",
            _voc_display_text("; ".join(final.get("errors", [])) or "35건 통과 조건 확인"),
        ),
        (
            "개선 추이",
            "검증 완료" if claim_verified else "미검증",
            _voc_display_text(claims.get("claim_text", "초기 33건 통과 / 2건 실패 → 최종 35건 통과")),
        ),
    )
    claim_table_rows = "".join(
        f"<tr><td><b>{escape(label)}</b></td><td class='{'qrt-green' if state == '검증 완료' else 'qrt-red'}'>"
        f"{escape(state)}</td><td>{escape(str(reason))}</td></tr>"
        for label, state, reason in claim_rows
    )
    defect_rows = "".join(
        "<tr>"
        f"<td><b>{escape(str(row.get('defect_id') or row.get('candidate_key') or '-'))}</b></td>"
        f"<td>{escape(_voc_display_text(row.get('title')))}</td>"
        f"<td><span class='qrt-severity'>{escape(_voc_display_label(row.get('severity')))}</span></td>"
        f"<td><span class='qrt-open'>{escape(_voc_display_label(row.get('status')))}</span></td>"
        f"<td>{escape(_voc_display_label(row.get('evidence_status')))}</td>"
        f"<td>{escape(str(row.get('owner') or '-'))}</td></tr>"
        for row in defects
    ) or "<tr><td colspan='6' class='qrt-green'>등록된 결함이 없습니다.</td></tr>"
    role_rows = "".join(
        f"<tr><td><b>{escape(_voc_display_label(row.get('role')))}</b></td>"
        f"<td>{escape(_voc_display_text(row.get('scope')))}</td>"
        f"<td>{escape(_voc_display_text(row.get('independence')))}</td></tr>"
        for row in roles
    )
    risk_rows = "".join(
        f"<tr><td><span class='qrt-severity'>{escape(_voc_display_label(row.get('level')))}</span></td>"
        f"<td>{escape(_voc_display_text(row.get('risk')))}</td><td>{escape(_voc_display_text(row.get('action')))}</td></tr>"
        for row in risks
    ) or "<tr><td colspan='3' class='qrt-green'>현재 집계된 잔여 위험이 없습니다.</td></tr>"

    recommendations = [_voc_display_text(row.get("action")) for row in risks if row.get("action")]
    if not integrity.get("ok"):
        recommendations.insert(0, "실행·케이스·증적 파일 무결성 오류를 먼저 복구하세요.")
    if not claim_verified:
        recommendations.append("동일 조건의 기준선 실행과 최종 실행을 연결해 개선 추이를 검증하세요.")
    if not recommendations:
        recommendations.append("현재 승인 기준을 유지하고 신규·경계 사례를 회귀 테스트에 추가하세요.")
    recommendation_html = "".join(
        f"<li>{_icon('target' if index == 0 else 'shield' if index == 1 else 'database')}"
        f"<span>{escape(text)}</span></li>"
        for index, text in enumerate(dict.fromkeys(recommendations))
    )

    style = """
    <style>
    .qrt-report{font-family:'Malgun Gothic','Apple SD Gothic Neo',sans-serif;color:#15243b;background:#fff;border:1px solid #c8d9ee;padding:22px;line-height:1.45}.qrt-report *{box-sizing:border-box}.qrt-head{display:grid;grid-template-columns:1fr 360px;gap:28px;align-items:start;margin-bottom:18px}.qrt-head h1{margin:4px 0 9px;color:#0c3768;font-size:29px;letter-spacing:-1.2px}.qrt-head p{margin:0;color:#40536d;font-size:13px}.qrt-meta{border:1px solid #c8d8eb;font-size:12px}.qrt-meta div{display:grid;grid-template-columns:115px 1fr;border-bottom:1px solid #d9e5f2}.qrt-meta div:last-child{border:0}.qrt-meta b{background:#edf3fa;padding:7px 9px}.qrt-meta span{padding:7px 10px;overflow-wrap:anywhere}.qrt-section{margin:15px 0;border:1px solid #9ebde0;border-radius:5px;padding:20px 16px 14px;position:relative}.qrt-section-title{display:inline-block;margin:-21px 0 16px -17px;padding:7px 16px;background:linear-gradient(90deg,#0b4f91,#176aab);color:#fff;font-weight:800;border-radius:5px 5px 0 0;font-size:15px}.qrt-kpis{display:grid;grid-template-columns:repeat(5,1fr);gap:11px}.qrt-kpi{min-height:105px;border:1px solid #d6e2f0;border-radius:6px;display:flex;align-items:center;gap:12px;padding:14px;background:linear-gradient(145deg,#fff,#f9fbfe)}.qrt-kpi .qrt-icon{width:40px;color:#0e4a80;flex:0 0 40px}.qrt-icon svg,.qrt-recommend svg{width:100%;height:auto}.qrt-kpi span{display:block;font-size:12px;font-weight:700}.qrt-kpi strong{display:block;color:#073b72;font-size:22px;margin:5px 0 1px;overflow-wrap:anywhere}.qrt-kpi strong small{font-size:14px;font-weight:500}.qrt-kpi small{font-size:11px;color:#627087}.qrt-kpi.bad strong{color:#e13f3b}.qrt-kpi.good strong{color:#299049}.qrt-charts{display:grid;grid-template-columns:.8fr 1.45fr 1.05fr;border:1px solid #d4e1ef;border-radius:5px;margin-top:12px}.qrt-chart{padding:12px 18px;min-height:220px;border-right:1px solid #dce6f1}.qrt-chart:last-child{border:0}.qrt-chart h3{text-align:center;margin:0 0 13px;font-size:13px}.qrt-donut-wrap{display:flex;align-items:center;justify-content:center;gap:20px}.qrt-donut{width:120px;height:120px;border-radius:50%;display:grid;place-items:center;position:relative}.qrt-donut:after{content:'';width:64px;height:64px;background:#fff;border-radius:50%;position:absolute}.qrt-donut b{z-index:1;text-align:center;font-size:12px}.qrt-legend div{font-size:11px;margin:7px 0}.qrt-legend i{display:inline-block;width:10px;height:10px;margin-right:7px}.qrt-rate-row{display:grid;grid-template-columns:100px 1fr 48px;gap:7px;align-items:center;margin:12px 0;font-size:11px}.qrt-stage-row{grid-template-columns:150px 1fr 48px 145px}.qrt-stage-row small{color:#627087}.qrt-rate-row>div{height:18px;background:#e8f0f8;border:1px solid #d7e4f1}.qrt-rate-row i{display:block;height:100%;background:linear-gradient(90deg,#0F4C81,#2E78B7 58%,#5EA1D7)}.qrt-rate-row b{text-align:right;color:#123F6D}.qrt-table-wrap{overflow:auto}.qrt-table{width:100%;border-collapse:collapse;font-size:11px}.qrt-table th{background:linear-gradient(#edf4fb,#dfeaf6);color:#173e69;font-weight:800}.qrt-table th,.qrt-table td{border:1px solid #cbd9e8;padding:7px 8px;vertical-align:top}.qrt-table tr:nth-child(even) td{background:#fbfdff}.qrt-two{display:grid;grid-template-columns:1fr 1fr;gap:16px}.qrt-subtitle{color:#0a4b88;font-size:13px;margin:0 0 8px}.qrt-green{color:#279445!important;font-weight:700}.qrt-red{color:#e03f36!important;font-weight:700}.qrt-severity,.qrt-open{display:inline-block;border-radius:999px;padding:2px 8px;font-weight:700;white-space:nowrap}.qrt-severity{color:#d83f36;background:#fde8e6}.qrt-open{color:#bf7000;background:#fff1d3}.qrt-bottom{display:grid;grid-template-columns:1.05fr .95fr;gap:16px}.qrt-opinion,.qrt-recommend{border:1px solid #a8c2df;padding:15px;min-height:135px}.qrt-opinion p{margin:7px 0;font-size:12px}.qrt-conclusion{font-size:15px!important;color:#084f92;font-weight:800}.qrt-recommend ul{list-style:none;padding:0;margin:0}.qrt-recommend li{display:grid;grid-template-columns:32px 1fr;gap:10px;align-items:center;margin:8px 0;font-size:11px}.qrt-recommend svg{color:#0b568f}.qrt-empty{color:#77869a;text-align:center}@media(max-width:900px){.qrt-head{grid-template-columns:1fr}.qrt-kpis{grid-template-columns:repeat(2,1fr)}.qrt-charts,.qrt-two,.qrt-bottom{grid-template-columns:1fr}.qrt-chart{border-right:0;border-bottom:1px solid #dce6f1}.qrt-stage-row{grid-template-columns:110px 1fr 42px}.qrt-stage-row small{grid-column:1/-1}.qrt-report{padding:14px}.qrt-head h1{font-size:23px}}
    </style>
    """
    stage_table_rows = "".join(
        f"<tr><td><b>{escape(label)}</b></td><td>{value}</td><td>{expected}</td><td>{escape(note)}</td></tr>"
        for label, value, expected, note in stage_rows
    )
    conclusion = (
        "정식 품질 승인 조건을 충족했습니다."
        if final_approved
        else "미충족 게이트를 보완한 뒤 재판정해야 합니다."
    )

    return style + f"""
    <div class="qrt-report">
      <header class="qrt-head"><div><h1>VOC 품질진단 결과 보고서</h1><p>VOC 개선안 생성부터 에이전트 내부 진단, 독립 평가, 업무 승인까지 연결된 품질 증적입니다.</p></div><div class="qrt-meta">{metadata_rows}</div></header>
      <section class="qrt-section"><div class="qrt-section-title">1. 테스트 요약</div><div class="qrt-kpis">{card_html}</div>
        <div class="qrt-charts">
          <div class="qrt-chart"><h3>판정 결과</h3><div class="qrt-donut-wrap"><div class="qrt-donut" style="{donut_style}"><b>합계<br>{total}건</b></div><div class="qrt-legend">{''.join(legend_rows)}</div></div></div>
          <div class="qrt-chart"><h3>품질 평가 단계별 증적</h3>{stage_bars}</div>
          <div class="qrt-chart"><h3>점검 범위별 실행률</h3>{coverage_bars}</div>
        </div>
      </section>
      <section class="qrt-section"><div class="qrt-section-title">2. 품질 평가 단계 상세</div><div class="qrt-table-wrap"><table class="qrt-table"><thead><tr><th>평가 단계</th><th>증적 건수</th><th>대상 건수</th><th>근거</th></tr></thead><tbody>{stage_table_rows}</tbody></table></div></section>
      <section class="qrt-section"><div class="qrt-section-title">3. 테스트 결과 상세</div><div class="qrt-table-wrap"><table class="qrt-table"><thead><tr><th>검증 영역</th><th>선택/기대</th><th>통과</th><th>실패</th><th>오류</th><th>검토 필요</th><th>미실행</th></tr></thead><tbody>{coverage_rows}</tbody></table></div></section>
      <section class="qrt-section"><div class="qrt-section-title">4. 개선 추이 및 결함 관리</div><div class="qrt-two">
        <div><h3 class="qrt-subtitle">33건 통과 / 2건 실패 → 35건 통과 검증</h3><div class="qrt-table-wrap"><table class="qrt-table"><thead><tr><th>구분</th><th>상태</th><th>판정 근거</th></tr></thead><tbody>{claim_table_rows}</tbody></table></div></div>
        <div><h3 class="qrt-subtitle">주요 결함 요약</h3><div class="qrt-table-wrap"><table class="qrt-table"><thead><tr><th>결함 ID</th><th>제목</th><th>심각도</th><th>상태</th><th>증적</th><th>담당자</th></tr></thead><tbody>{defect_rows}</tbody></table></div></div>
      </div></section>
      <section class="qrt-section"><div class="qrt-section-title">5. 독립성 및 잔여 위험</div><div class="qrt-two">
        <div><h3 class="qrt-subtitle">내부 평가자·위험 검토자·독립 AI 평가자 역할</h3><div class="qrt-table-wrap"><table class="qrt-table"><thead><tr><th>역할</th><th>평가 범위</th><th>독립성</th></tr></thead><tbody>{role_rows}</tbody></table></div></div>
        <div><h3 class="qrt-subtitle">잔여 위험과 운영 조치</h3><div class="qrt-table-wrap"><table class="qrt-table"><thead><tr><th>등급</th><th>위험</th><th>권고 조치</th></tr></thead><tbody>{risk_rows}</tbody></table></div></div>
      </div></section>
      <div class="qrt-bottom"><section class="qrt-opinion"><h3 class="qrt-subtitle">6. 종합 평가 및 의견</h3>
        <p>✓ 전체 통과율은 <b>{pass_rate:.1f}%</b>, 증적 상태는 <b>{escape(_voc_display_label(model.get('report_state')))}</b>입니다.</p>
        <p>✓ 개선 추이 검증은 <b>{'완료' if claim_verified else '미완료'}</b>, 증적 무결성은 <b>{'정상' if integrity.get('ok') else '확인 필요'}</b>입니다.</p>
        <p class="qrt-conclusion">→ 결론: {escape(_voc_display_label(model.get('release_decision', 'NOT_APPROVED')))} — {conclusion}</p>
        </section><section class="qrt-recommend"><h3 class="qrt-subtitle">7. 개선 권고 사항</h3><ul>{recommendation_html}</ul></section></div>
    </div>
    """


def render_agent_quality_report(pipeline_outputs, agent_key, quality_criteria=None, metadata=None):
    model = build_agent_report_model(pipeline_outputs, agent_key, quality_criteria, metadata)
    st.markdown(build_agent_report_html(model), unsafe_allow_html=True)
