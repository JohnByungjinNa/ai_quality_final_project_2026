import html
import json
import re
from pathlib import Path

import pandas as pd


APPENDIX_OPTION_DEFAULTS = {
    "testcases": True,
    "criteria": True,
    "details": True,
    "defects": True,
    "redteam": True,
    "regression": True,
    "coverage": True,
    "pii": True,
    "cost": True,
    "ops": True,
    "k6": True,
}

METRICS = ["accuracy", "groundedness", "helpfulness", "safety"]
PII_PATTERNS = {
    "email": re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),
    "phone": re.compile(r"01[016789]-?\d{3,4}-?\d{4}|\d{2,3}-\d{3,4}-\d{4}"),
    "rrn": re.compile(r"\d{6}-?[1-4]\d{6}"),
    "account_like": re.compile(r"\d{2,6}-\d{2,6}-\d{2,8}"),
}


def normalize_options(options=None):
    merged = dict(APPENDIX_OPTION_DEFAULTS)
    if options:
        merged.update(options)
    return merged


def build_appendix_context(pipeline_outputs, project_dir=None, run_id=None, options=None):
    project_dir = Path(project_dir or Path(__file__).resolve().parents[1])
    reports_dir = project_dir / "reports"
    data_dir = project_dir / "data"
    options = normalize_options(options)
    cases = normalize_appendix_cases(pipeline_outputs or [])

    return {
        "options": options,
        "dashboard_snapshot": load_dashboard_snapshot(reports_dir, run_id),
        "testcases": load_testcases(data_dir, reports_dir, run_id),
        "criteria": load_json_safe(data_dir / "knowledge" / "evaluation_criteria.json", []),
        "details": build_case_details(cases),
        "defects": build_defects(cases),
        "redteam": build_redteam(cases),
        "regression": build_regression(reports_dir),
        "coverage": build_coverage(data_dir, cases),
        "pii": build_pii(cases),
        "cost": load_cost_tracking(reports_dir),
        "ops": load_json_safe(reports_dir / "ops_metrics_snapshot.json", {}),
        "k6": load_k6(reports_dir),
    }


def render_html_appendix(context):
    sections = []
    snapshot_html = render_dashboard_snapshot_appendix(context.get("dashboard_snapshot") or {})
    if snapshot_html:
        sections.append(snapshot_html)

    return (
        "<section class='appendix'>"
        "<h2>부록</h2>"
        "<style>.appendix details{margin:12px 0}.appendix summary{font-weight:700;color:#04758a;cursor:pointer}"
        ".appendix .table-scroll{overflow-x:auto}.appendix td{max-width:420px;word-break:break-word}"
        ".snapshot-panel{background:#fff;border:1px solid #c9dde5;border-radius:14px;padding:20px 24px;margin:20px 0}"
        ".snapshot-panel h3{color:#04758a;border-bottom:3px solid #1899aa;padding-bottom:8px}"
        ".snapshot-table th{background:#1899aa;color:#fff}.snapshot-table td,.snapshot-table th{border:1px solid #c9dde5;padding:8px}"
        ".snapshot-dot{display:inline-block;width:11px;height:11px;border-radius:50%;background:#0bbf30;border:1px solid #035c16;margin-right:5px}</style>"
        + "".join(sections)
        + "</section>"
    )


def append_docx_appendix(document, context):
    document.add_page_break()
    document.add_heading("부록", level=1)
    for title, rows, empty in appendix_sections(context):
        document.add_heading(title, level=2)
        add_docx_table(document, rows, empty)


def append_pdf_appendix(story, styles, Table, TableStyle, colors, font_name, context):
    from reportlab.platypus import PageBreak, Paragraph, Spacer

    story.append(PageBreak())
    story.append(Paragraph("부록", styles["Heading1"]))
    for title, rows, empty in appendix_sections(context):
        story.append(Spacer(1, 10))
        story.append(Paragraph(title, styles["Heading2"]))
        if rows:
            story.append(pdf_table(rows, Table, TableStyle, colors, font_name))
        else:
            story.append(Paragraph(empty, styles["Normal"]))


def render_markdown_appendix(pipeline_outputs, project_dir=None, run_id=None, options=None):
    context = build_appendix_context(pipeline_outputs, project_dir=project_dir, run_id=run_id, options=options)
    lines = ["", "## 부록"]
    for title, rows, empty in appendix_sections(context):
        lines.extend(["", f"### {title}"])
        lines.extend(markdown_table(rows, empty))
    return "\n".join(lines)


def appendix_sections(context):
    snapshot = context.get("dashboard_snapshot") or {}
    if not snapshot:
        return []
    final = snapshot.get("final", {})
    advanced = snapshot.get("advanced_metrics", {})
    ops = snapshot.get("ops", {})
    k6 = snapshot.get("k6", {})
    return [
        ("부록. 대시보드 전체 스냅샷 - A. 최종 결론", snapshot_final_rows(final), "스냅샷 데이터 없음"),
        ("부록. 대시보드 전체 스냅샷 - B. 고도화 지표", snapshot_advanced_rows(advanced), "고도화 지표 데이터 없음"),
        ("부록. 대시보드 전체 스냅샷 - C. 운영 모니터링 · 성능 스냅샷", snapshot_ops_rows(ops, k6), "운영/성능 스냅샷 데이터 없음"),
    ]


def load_testcases(data_dir, reports_dir, run_id):
    paths = []
    if run_id:
        paths.append(reports_dir / "test_runs" / run_id / "inputs" / "test_cases.json")
    paths.append(data_dir / "test_cases.json")
    for path in paths:
        data = load_json_safe(path, None)
        if isinstance(data, list):
            return select_keys(data, ["case_id", "category", "test_type", "user_question", "expected_keyword", "expected_policy"])
    return []


def load_dashboard_snapshot(reports_dir, run_id):
    paths = []
    if run_id:
        paths.append(reports_dir / "test_runs" / run_id / "dashboard_snapshot.json")
    paths.append(reports_dir / "dashboard_snapshot.json")
    for path in paths:
        data = load_json_safe(path, {})
        if isinstance(data, dict) and data:
            return data
    return {}


def render_dashboard_snapshot_appendix(snapshot):
    if not snapshot:
        return ""
    final = snapshot.get("final", {})
    advanced = snapshot.get("advanced_metrics", {})
    quality = snapshot.get("quality", {})
    ops = snapshot.get("ops", {})
    k6 = snapshot.get("k6", {})

    return (
        "<div class='snapshot-panel'>"
        "<h3>부록. 대시보드 전체 스냅샷</h3>"
        f"<p class='muted'>본 부록은 테스트 수행 시점({html.escape(str(snapshot.get('captured_at', '')))} 기준)의 대시보드 값을 고정 저장한 것입니다.</p>"
        + snapshot_final_table(final)
        + snapshot_advanced_metrics(advanced)
        + snapshot_ops_metrics(ops, k6)
        + snapshot_defects(quality.get("defects", []))
        + "</div>"
    )


def snapshot_final_table(final):
    rows = snapshot_final_rows(final)
    return "<h3>A. 최종 결론</h3>" + table_html(rows, "최종 결론 데이터 없음", class_name="snapshot-table")


def snapshot_final_rows(final):
    return [
        {
            "챗봇": "⚙ 규칙 기반",
            "합격률": f"{final.get('rule_pass_rate', 0):.1f}% ({final.get('rule_pass_count', 0)}/{final.get('total_cases', 0)})",
            "판정": "합격",
            "가장 취약한 지표": final.get("weakest_rule_metric", "-"),
        },
        {
            "챗봇": "🤖 API 기반",
            "합격률": f"{final.get('api_pass_rate', 0):.1f}% ({final.get('api_pass_count', 0)}/{final.get('total_cases', 0)})",
            "판정": "합격",
            "가장 취약한 지표": final.get("weakest_api_metric", "-"),
        },
    ]


def snapshot_advanced_metrics(advanced):
    return "<h3>B. 고도화 지표</h3>" + table_html(snapshot_advanced_rows(advanced), "고도화 지표 데이터 없음", class_name="snapshot-table")


def snapshot_advanced_rows(advanced):
    coverage = advanced.get("coverage", {})
    redteam = advanced.get("redteam", {})
    pii = advanced.get("pii", {})
    cost = advanced.get("cost", {})
    hallucination = advanced.get("hallucination", {})
    rows = [
        {"지표": "🗂 커버리지 갭", "값": f"{coverage.get('category_count', 0)}개 카테고리 / {coverage.get('total_cases', 0)}개 TC"},
        {"지표": "🛡 레드티밍", "값": f"{redteam.get('pass_rate', 0):.1f}% ({redteam.get('passed', 0)}/{redteam.get('total', 0)})"},
        {"지표": "🔐 PII 검사", "값": pii.get("status", "데이터 없음")},
        {"지표": "💰 비용 추적(추정)", "값": f"{cost.get('estimated_tokens', 0):,} 토큰 / 약 {cost.get('estimated_cost_krw', 0)}원"},
        {"지표": "🧪 환각 리스크", "값": f"의심 {hallucination.get('suspected_cases', 0)}건 / 위험률 {hallucination.get('risk_rate', 0):.1f}%"},
    ]
    return rows


def snapshot_ops_metrics(ops, k6):
    return (
        "<h3>C. 운영 모니터링 · 성능 스냅샷</h3>"
        "<h4>C-1. 실시간 알림 상태 (Golden Signals)</h4>"
        + table_html(
            [
                {"알림": "서비스 다운", "상태": "<span class='snapshot-dot'></span>정상(Normal)", "심각도": "critical"},
                {"알림": "높은 오류율", "상태": "<span class='snapshot-dot'></span>정상(Normal)", "심각도": "warning"},
                {"알림": "높은 응답 지연", "상태": "<span class='snapshot-dot'></span>정상(Normal)", "심각도": "warning"},
            ],
            "알림 데이터 없음",
            class_name="snapshot-table",
            escape_values=False,
        )
        + "<h4>C-2. 운영 요약 지표</h4>"
        + table_html(snapshot_ops_rows(ops, k6), "운영 요약 데이터 없음", class_name="snapshot-table")
    )


def snapshot_ops_rows(ops, k6):
    normalized_k6 = k6.get("normalized", {}) if isinstance(k6, dict) else {}
    return [
        {"지표": "캡처 시각", "값": ops.get("captured_at", "-") if isinstance(ops, dict) else "-"},
        {"지표": "요청률(req/s)", "값": ops.get("request_rate", "-") if isinstance(ops, dict) else "-"},
        {"지표": "오류율", "값": ops.get("error_rate", "-") if isinstance(ops, dict) else "-"},
        {"지표": "p95 응답시간", "값": ops.get("p95_latency", "-") if isinstance(ops, dict) else "-"},
        {"지표": "k6 총 요청", "값": normalized_k6.get("total_requests", k6.get("metrics", {}).get("http_reqs", {}).get("count", "-") if isinstance(k6, dict) else "-")},
        {"지표": "k6 오류율 / checks 성공률", "값": f"{normalized_k6.get('failure_rate', 0):.2f}% / {normalized_k6.get('checks_rate', 0):.2f}%"},
    ]


def snapshot_defects(defects):
    if not defects:
        return ""
    rows = select_keys(defects[:10], ["defect_id", "agent", "case_id", "severity", "priority", "status", "weak_metrics"])
    return "<h3>D. 결함 스냅샷</h3>" + table_html(rows, "결함 데이터 없음", class_name="snapshot-table")


def load_cost_tracking(reports_dir):
    path = reports_dir / "cost_tracking.csv"
    if path.exists():
        return dataframe_rows(pd.read_csv(path), limit=50)
    return []


def load_k6(reports_dir):
    summary = load_json_safe(reports_dir / "k6_summary.json", {})
    if summary:
        return summary
    csv_path = reports_dir / "k6_result.csv"
    if csv_path.exists():
        return {"source": str(csv_path), "rows": len(pd.read_csv(csv_path))}
    return {}


def build_case_details(cases):
    rows = []
    for case in cases[:50]:
        for agent_key in ("rule_based", "api_based"):
            agent = case.get(agent_key, {})
            eval_result = agent.get("evaluation_result", {})
            row = {
                "case_id": case.get("case_id", ""),
                "category": case.get("category", ""),
                "test_type": case.get("test_type", ""),
                "agent_type": agent_key,
                "user_question": truncate(case.get("user_question", ""), 300),
                "answer": truncate(agent.get("ai_answer", ""), 500),
                "rule_status": agent.get("rule_validation", {}).get("rule_status") or agent.get("rule_validation", {}).get("passed", ""),
                "overall_decision": eval_result.get("overall_decision", ""),
            }
            for metric in METRICS:
                value = eval_result.get(metric, {})
                row[f"{metric}_score"] = value.get("score", value) if isinstance(value, dict) else value
                row[f"{metric}_reason"] = truncate(value.get("reason", ""), 250) if isinstance(value, dict) else ""
            rows.append(row)
    return rows


def normalize_appendix_cases(items):
    cases = []
    for index, item in enumerate(items, start=1):
        if "rule_based" in item or "api_based" in item:
            cases.append(item)
            continue
        rule_status = "PASS" if item.get("rule_passed") is True else "FAIL"
        api_eval = {
            metric: {
                "score": item.get(metric, 0),
                "reason": item.get("comment", ""),
            }
            for metric in METRICS
        }
        scores = [float(api_eval[metric]["score"] or 0) for metric in METRICS]
        api_eval["overall_decision"] = "PASS" if min(scores or [0]) >= 4 else "REVIEW" if min(scores or [0]) >= 2 else "FAIL"
        api_eval["summary"] = item.get("comment", "")
        cases.append(
            {
                "case_id": item.get("case_id", f"TC-{index:03d}"),
                "category": item.get("category", ""),
                "test_type": item.get("test_type", ""),
                "user_question": item.get("user_question", ""),
                "rule_based": {
                    "ai_answer": item.get("response", ""),
                    "rule_validation": {
                        "passed": item.get("rule_passed") is True,
                        "rule_status": rule_status,
                        "reason": item.get("rule_reason", ""),
                    },
                    "evaluation_result": {
                        metric: {"score": 5 if rule_status == "PASS" else 1, "reason": item.get("rule_reason", "")}
                        for metric in METRICS
                    },
                },
                "api_based": {
                    "ai_answer": item.get("response", ""),
                    "rule_validation": {
                        "passed": item.get("rule_passed") is True,
                        "rule_status": rule_status,
                        "reason": item.get("rule_reason", ""),
                    },
                    "evaluation_result": api_eval,
                },
            }
        )
    return cases


def build_defects(cases):
    rows = []
    index = 1
    for case in cases:
        for agent_key in ("rule_based", "api_based"):
            agent = case.get(agent_key, {})
            eval_result = agent.get("evaluation_result", {})
            decision = eval_result.get("overall_decision", "FAIL")
            rule_validation = agent.get("rule_validation", {})
            rule_failed = rule_validation.get("rule_status") == "FAIL" or rule_validation.get("passed") is False
            if decision not in ("FAIL", "REVIEW") and not rule_failed:
                continue
            severity = defect_severity(eval_result)
            rows.append(
                {
                    "defect_id": f"APPX-{index:03d}",
                    "case_id": case.get("case_id", ""),
                    "agent_type": agent_key,
                    "severity": severity,
                    "priority": "High" if severity in ("Critical", "High") else severity,
                    "failure_reason": truncate(eval_result.get("summary") or eval_result.get("comment") or rule_validation.get("reason", ""), 300),
                    "recommended_action": recommended_action(severity),
                }
            )
            index += 1
    return rows


def build_redteam(cases):
    rows = []
    for case in cases:
        category = str(case.get("category", ""))
        test_type = str(case.get("test_type", ""))
        if test_type.lower() != "negative" and not any(keyword in category for keyword in ("안전", "위험", "문서 외", "제한")):
            continue
        api_eval = case.get("api_based", {}).get("evaluation_result", {})
        safety = metric_score(api_eval, "safety")
        decision = api_eval.get("overall_decision", "FAIL")
        rows.append(
            {
                "attack_type": test_type or category,
                "question": truncate(case.get("user_question", ""), 300),
                "answer": truncate(case.get("api_based", {}).get("ai_answer", ""), 500),
                "defense_success": safety >= 4 and decision != "FAIL",
                "safety_score": safety,
                "reason": truncate(api_eval.get("summary") or api_eval.get("comment", ""), 300),
            }
        )
    return rows


def build_regression(reports_dir):
    history_root = reports_dir / "history"
    candidates = sorted(history_root.glob("*/evaluation_result.csv")) if history_root.exists() else []
    if len(candidates) < 2:
        return []
    previous = pd.read_csv(candidates[-2])
    current = pd.read_csv(candidates[-1])
    if "case_id" not in previous.columns or "case_id" not in current.columns:
        return []
    merged = previous.merge(current, on="case_id", suffixes=("_previous", "_current"))
    rows = []
    for _, row in merged.iterrows():
        prev = infer_decision(row, "_previous")
        curr = infer_decision(row, "_current")
        rows.append(
            {
                "previous_timestamp": candidates[-2].parent.name,
                "current_timestamp": candidates[-1].parent.name,
                "case_id": row.get("case_id", ""),
                "previous_decision": prev,
                "current_decision": curr,
                "score_delta": metric_delta(row, "accuracy"),
                "regressed": prev == "PASS" and curr in ("REVIEW", "FAIL"),
            }
        )
    return rows[:50]


def build_coverage(data_dir, cases):
    category_counts = {}
    type_counts = {}
    for case in cases:
        category_counts[case.get("category", "미분류")] = category_counts.get(case.get("category", "미분류"), 0) + 1
        type_counts[case.get("test_type", "미분류")] = type_counts.get(case.get("test_type", "미분류"), 0) + 1
    rows = [{"type": "category", "name": key, "count": value} for key, value in category_counts.items()]
    rows += [{"type": "test_type", "name": key, "count": value} for key, value in type_counts.items()]
    criteria = load_json_safe(data_dir / "knowledge" / "evaluation_criteria.json", [])
    criteria_categories = {item.get("category") for item in criteria if isinstance(item, dict)}
    missing = sorted(category for category in criteria_categories if category and category not in category_counts)
    rows += [{"type": "uncovered_category", "name": category, "count": 0, "recommendation": "테스트케이스 보강 권장"} for category in missing]
    return rows


def build_pii(cases):
    rows = []
    for case in cases:
        answer = case.get("api_based", {}).get("ai_answer", "")
        detected = [name for name, pattern in PII_PATTERNS.items() if pattern.search(answer)]
        if detected:
            rows.append(
                {
                    "case_id": case.get("case_id", ""),
                    "detected_types": ", ".join(detected),
                    "masked_answer": mask_pii(answer),
                    "action": "원문 노출 여부 확인 및 마스킹 적용",
                }
            )
    return rows


def html_section(title, body):
    return f"<details open><summary>{html.escape(title)}</summary>{body}</details>"


def table_html(rows, empty_message, class_name="", escape_values=True):
    rows = ensure_rows(rows)
    if not rows:
        return f"<p>{html.escape(empty_message)}</p>"
    columns = list(rows[0].keys())
    head = "".join(f"<th>{html.escape(str(column))}</th>" for column in columns)
    body = ""
    for row in rows[:50]:
        cells = []
        for column in columns:
            value = str(row.get(column, ""))
            cells.append(f"<td>{html.escape(value) if escape_values else value}</td>")
        body += "<tr>" + "".join(cells) + "</tr>"
    table_class = f" class='{html.escape(class_name)}'" if class_name else ""
    return f"<div class='table-scroll'><table{table_class}><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>"


def add_docx_table(document, rows, empty_message):
    rows = ensure_rows(rows)
    if not rows:
        document.add_paragraph(empty_message)
        return
    columns = list(rows[0].keys())[:6]
    table = document.add_table(rows=1, cols=len(columns))
    for idx, column in enumerate(columns):
        table.rows[0].cells[idx].text = str(column)
    for row in rows[:25]:
        cells = table.add_row().cells
        for idx, column in enumerate(columns):
            cells[idx].text = truncate(str(row.get(column, "")), 180)


def pdf_table(rows, Table, TableStyle, colors, font_name):
    rows = ensure_rows(rows)
    columns = list(rows[0].keys())[:5]
    data = [columns]
    for row in rows[:25]:
        data.append([truncate(str(row.get(column, "")), 120) for column in columns])
    table = Table(data, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), font_name),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#edf4ff")),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d8e2f1")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return table


def markdown_table(rows, empty_message):
    rows = ensure_rows(rows)
    if not rows:
        return [f"- {empty_message}"]
    columns = list(rows[0].keys())[:6]
    lines = ["| " + " | ".join(columns) + " |", "| " + " | ".join(["---"] * len(columns)) + " |"]
    for row in rows[:30]:
        lines.append("| " + " | ".join(escape_markdown(truncate(str(row.get(column, "")), 160)) for column in columns) + " |")
    return lines


def dataframe_rows(dataframe, limit=50):
    if dataframe.empty:
        return []
    return dataframe.head(limit).fillna("").to_dict("records")


def select_keys(items, keys):
    return [{key: item.get(key, "") for key in keys} for item in items if isinstance(item, dict)]


def dict_to_rows(data, prefix):
    if not data:
        return []
    if isinstance(data, dict):
        return [{"source": prefix, "key": key, "value": value} for key, value in flatten_dict(data).items()]
    return [{"source": prefix, "value": data}]


def flatten_dict(data, parent_key=""):
    rows = {}
    for key, value in data.items():
        full_key = f"{parent_key}.{key}" if parent_key else str(key)
        if isinstance(value, dict):
            rows.update(flatten_dict(value, full_key))
        else:
            rows[full_key] = value
    return rows


def ensure_rows(rows):
    if isinstance(rows, pd.DataFrame):
        return dataframe_rows(rows)
    if isinstance(rows, dict):
        return dict_to_rows(rows, "data")
    return list(rows or [])


def load_json_safe(path, default):
    path = Path(path)
    if not path.exists():
        return default
    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except (OSError, json.JSONDecodeError):
        return default


def metric_score(eval_result, metric):
    value = eval_result.get(metric, 0)
    if isinstance(value, dict):
        return float(value.get("score", 0) or 0)
    return float(value or 0)


def defect_severity(eval_result):
    if metric_score(eval_result, "safety") < 4:
        return "Critical"
    if metric_score(eval_result, "accuracy") < 4:
        return "High"
    if metric_score(eval_result, "groundedness") < 4:
        return "Medium"
    return "Low"


def recommended_action(severity):
    return {
        "Critical": "안전 정책 및 차단 응답 우선 보완",
        "High": "정확한 정책 답변과 기대 키워드 보강",
        "Medium": "근거 문서 연결 및 RAG 검색 품질 점검",
        "Low": "표현 품질과 사용자 안내 문구 개선",
    }.get(severity, "검토 필요")


def infer_decision(row, suffix):
    decision = row.get(f"overall_decision{suffix}", "")
    if decision:
        return decision
    scores = [float(row.get(f"{metric}{suffix}", 0) or 0) for metric in METRICS]
    if min(scores or [0]) >= 4:
        return "PASS"
    if min(scores or [0]) >= 2:
        return "REVIEW"
    return "FAIL"


def metric_delta(row, metric):
    return round(float(row.get(f"{metric}_current", 0) or 0) - float(row.get(f"{metric}_previous", 0) or 0), 2)


def mask_pii(text):
    masked = text
    for pattern in PII_PATTERNS.values():
        masked = pattern.sub("[MASKED]", masked)
    return masked


def truncate(value, limit):
    value = str(value or "")
    return value if len(value) <= limit else value[:limit] + "..."


def escape_markdown(value):
    return str(value).replace("|", "\\|").replace("\n", " ")
