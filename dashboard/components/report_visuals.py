from html import escape

import pandas as pd
import streamlit as st

from pages_top.result_report_view import render_report_tab
from pages_top.advanced_metrics_view import render_advanced_metrics_for_dataframe
from quality_metrics import dataframe_from_pipeline_outputs
from quality_criteria import LEGACY_CRITERIA, criteria_summary, get_quality_criteria
from components.quality_report_template import build_comparison_summary_html, render_agent_quality_report

def summarize_pipeline_outputs(pipeline_outputs, quality_criteria=None):
    criteria = get_quality_criteria(quality_criteria)
    total_count = len(pipeline_outputs)
    rule_passed_count = sum(
        1
        for item in pipeline_outputs
        if item.get("rule_based", {}).get("evaluation_result", {}).get("overall_decision") == "PASS"
    )
    api_passed_count = sum(
        1
        for item in pipeline_outputs
        if item.get("api_based", {}).get("evaluation_result", {}).get("overall_decision") == "PASS"
    )
    matched_count = sum(
        1
        for item in pipeline_outputs
        if item.get("rule_based", {}).get("evaluation_result", {}).get("overall_decision")
        == item.get("api_based", {}).get("evaluation_result", {}).get("overall_decision")
    )
    combined_passed_count = sum(
        1
        for item in pipeline_outputs
        if item.get("api_based", {}).get("evaluation_result", {}).get("overall_decision") == "PASS"
        and (
            not criteria.require_rule_pass_for_overall
            or item.get("rule_based", {}).get("evaluation_result", {}).get("overall_decision") == "PASS"
        )
    )
    failed_count = total_count - combined_passed_count

    file_results = []
    for item in pipeline_outputs:
        rule_decision = item.get("rule_based", {}).get("evaluation_result", {}).get("overall_decision", "FAIL")
        api_decision = item.get("api_based", {}).get("evaluation_result", {}).get("overall_decision", "FAIL")
        file_results.append(
            {
                "케이스ID": item.get("case_id", ""),
                "카테고리": item.get("category", ""),
                "유형": item.get("test_type", ""),
                "질문": item.get("user_question", ""),
                "규칙기반 판정": rule_decision,
                "API기반 판정": api_decision,
                "판정일치": "일치" if rule_decision == api_decision else "불일치",
            }
        )

    return {
        "total_count": total_count,
        "rule_passed_count": rule_passed_count,
        "api_passed_count": api_passed_count,
        "combined_passed_count": combined_passed_count,
        "matched_count": matched_count,
        "failed_count": failed_count,
        "file_results": file_results,
    }


BLUE_PALETTE = {
    "dark": "#153E75",
    "primary": "#2563EB",
    "medium": "#60A5FA",
    "light": "#BFDBFE",
    "pale": "#EFF6FF",
    "text": "#1E3A8A",
}

METRIC_DEFINITIONS = [
    {
        "key": "accuracy",
        "label": "accuracy(정확성)",
        "description": "응답이 사실적으로 올바르고 기대 정책과 일치하는가",
    },
    {
        "key": "groundedness",
        "label": "groundedness(근거성)",
        "description": "응답이 제공된 정책/근거에 기반하고 있는가 (근거 없는 추측이 없는가)",
    },
    {
        "key": "helpfulness",
        "label": "helpfulness(유용성)",
        "description": "사용자 질문에 실질적으로 도움이 되는가",
    },
    {
        "key": "safety",
        "label": "safety(안전성)",
        "description": "부적절하거나 위험한 내용 없이 안전하게 응답했는가",
    },
]

METRIC_LABEL_BY_KEY = {item["key"]: item["label"] for item in METRIC_DEFINITIONS}


def compute_release_decision(pipeline_outputs, rule_rate, api_rate, quality_criteria=None):
    criteria = get_quality_criteria(quality_criteria)
    if not pipeline_outputs:
        return "판정 불가", "표시할 테스트 결과가 없습니다."

    api_scores = [
        get_agent_metric_score(case, "api_based", metric["key"])
        for case in pipeline_outputs
        for metric in METRIC_DEFINITIONS
    ]
    comments = [
        str(case.get("api_based", {}).get("evaluation_result", {}).get("comment", ""))
        for case in pipeline_outputs
    ]
    judge_unavailable = all(score == 0 for score in api_scores) and any("평가 실패" in comment for comment in comments)
    safety_scores = [get_agent_metric_score(case, "api_based", "safety") for case in pipeline_outputs]
    safety_avg = sum(safety_scores) / len(safety_scores) if safety_scores else 0

    if judge_unavailable:
        return "조건부 배포", "AI Judge API 평가가 실패하여 규칙 검증 결과 중심으로만 판단했습니다."
    if (
        rule_rate >= criteria.rule_pass_rate_min
        and api_rate >= criteria.api_pass_rate_min
        and safety_avg >= criteria.safety_avg_min
    ):
        return "배포 가능", "규칙 기반/API 기반 평가가 모두 기준을 만족했습니다."
    if (
        rule_rate >= criteria.conditional_rule_pass_rate_min
        and api_rate >= criteria.conditional_api_pass_rate_min
        and safety_avg >= criteria.conditional_safety_avg_min
    ):
        return "조건부 배포", "실패 사례를 보완한 뒤 재검증이 필요합니다."
    return "배포 보류", "통과율 또는 안전성 점수가 기준에 미달합니다."


def build_failed_case_rows(pipeline_outputs, quality_criteria=None):
    criteria = get_quality_criteria(quality_criteria)
    rows = []
    for case in pipeline_outputs:
        rule_decision = get_agent_decision(case, "rule_based")
        api_decision = get_agent_decision(case, "api_based")
        safety_score = get_agent_metric_score(case, "api_based", "safety")
        accuracy_score = get_agent_metric_score(case, "api_based", "accuracy")
        rule_satisfied = rule_decision == "PASS" or not criteria.require_rule_pass_for_overall
        if rule_satisfied and api_decision == "PASS":
            continue

        rows.append(
            {
                "케이스ID": case.get("case_id", ""),
                "카테고리": case.get("category", ""),
                "질문": case.get("user_question", ""),
                "규칙판정": rule_decision,
                "API판정": api_decision,
                "정확성": accuracy_score,
                "안전성": safety_score,
                "비고": case.get("api_based", {}).get("evaluation_result", {}).get("comment", ""),
            }
        )
    return rows


def agent_label(agent_key):
    return "규칙 기반" if agent_key == "rule_based" else "API 기반"


def get_agent_decision(case, agent_key):
    return case.get(agent_key, {}).get("evaluation_result", {}).get("overall_decision", "FAIL")


def get_agent_metric_score(case, agent_key, metric):
    return case.get(agent_key, {}).get("evaluation_result", {}).get(metric, {}).get("score", 0)


def render_metric_definition_box():
    with st.expander("평가 지표 설명", expanded=False):
        metric_cards = []
        for item in METRIC_DEFINITIONS:
            metric_cards.append(
                f"<div style='border:1px solid #D9E6F5;border-radius:8px;padding:10px 12px;background:#F8FBFF;'>"
                f"<div style='font-weight:700;color:{BLUE_PALETTE['text']};font-size:13px;margin-bottom:4px;'>"
                f"{escape(item['label'])}</div>"
                f"<div style='font-size:12px;color:#475569;line-height:1.45;'>{escape(item['description'])}</div>"
                f"</div>"
            )
        st.markdown(
            "<div style='display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;'>"
            + "".join(metric_cards)
            + "</div>",
            unsafe_allow_html=True,
        )


def build_decision_chart_data(pipeline_outputs):
    rows = []
    for agent_key in ("rule_based", "api_based"):
        decisions = [get_agent_decision(case, agent_key) for case in pipeline_outputs]
        for decision in ("PASS", "REVIEW", "FAIL"):
            rows.append(
                {
                    "챗봇": agent_label(agent_key),
                    "판정": decision,
                    "건수": decisions.count(decision),
                }
            )
    return pd.DataFrame(rows)


def build_metric_chart_data(pipeline_outputs):
    rows = []
    for agent_key in ("rule_based", "api_based"):
        for metric in METRIC_DEFINITIONS:
            metric_key = metric["key"]
            scores = [get_agent_metric_score(case, agent_key, metric_key) for case in pipeline_outputs]
            average_score = sum(scores) / len(scores) if scores else 0
            rows.append(
                {
                    "챗봇": agent_label(agent_key),
                    "지표": metric["label"],
                    "평균점수": round(average_score, 2),
                }
            )
    return pd.DataFrame(rows)


def build_metric_profile_data(pipeline_outputs, case=None):
    target_cases = [case] if case else pipeline_outputs
    rows = []

    for metric in METRIC_DEFINITIONS:
        metric_key = metric["key"]
        row = {"metric": metric["label"]}
        for agent_key in ("rule_based", "api_based"):
            scores = [get_agent_metric_score(item, agent_key, metric_key) for item in target_cases]
            row[agent_key] = round(sum(scores) / len(scores), 2) if scores else 0
        rows.append(row)

    return rows


def build_category_chart_data(pipeline_outputs):
    rows = []
    categories = sorted({case.get("category", "미분류") for case in pipeline_outputs})
    for category in categories:
        category_cases = [case for case in pipeline_outputs if case.get("category", "미분류") == category]
        total = len(category_cases)
        for agent_key in ("rule_based", "api_based"):
            passed = sum(1 for case in category_cases if get_agent_decision(case, agent_key) == "PASS")
            rows.append(
                {
                    "카테고리": category,
                    "챗봇": agent_label(agent_key),
                    "합격률": round((passed / total) * 100, 1) if total else 0,
                }
            )
    return pd.DataFrame(rows)


def strip_altair_type(field_name):
    return field_name.split(":", 1)[0]


def render_blue_bar_chart(dataframe, x_field, y_field, color_field=None, height=260, domain=None, title=None):
    if dataframe.empty:
        st.info("차트로 표시할 데이터가 없습니다.")
        return

    x_column = strip_altair_type(x_field)
    y_column = strip_altair_type(y_field)
    color_column = strip_altair_type(color_field) if color_field else None
    max_value = domain[1] if domain else max(float(value or 0) for value in dataframe[y_column].tolist()) or 1
    color_values = dataframe[color_column].dropna().unique().tolist() if color_column else []
    color_map = {
        value: [BLUE_PALETTE["primary"], BLUE_PALETTE["medium"], BLUE_PALETTE["dark"], BLUE_PALETTE["light"]][index % 4]
        for index, value in enumerate(color_values)
    }

    html_parts = [
        "<div style='width:100%;'>",
        f"<div style='font-weight:700;color:{BLUE_PALETTE['text']};margin:4px 0 10px;'>{escape(title or '')}</div>" if title else "",
    ]

    if color_column:
        legend_items = "".join(
            f"<span style='display:inline-flex;align-items:center;margin-right:14px;color:#42526b;font-size:12px;'>"
            f"<span style='width:10px;height:10px;border-radius:2px;background:{color_map[value]};display:inline-block;margin-right:5px;'></span>"
            f"{escape(str(value))}</span>"
            for value in color_values
        )
        html_parts.append(f"<div style='margin-bottom:8px;'>{legend_items}</div>")

    for _, row in dataframe.iterrows():
        label = str(row.get(x_column, ""))
        value = float(row.get(y_column, 0) or 0)
        group = str(row.get(color_column, "")) if color_column else ""
        color = color_map.get(group, BLUE_PALETTE["primary"])
        width = min(max(value / max_value * 100, 0), 100)
        value_label = f"{value:.1f}" if value % 1 else f"{int(value)}"
        row_label = f"{label} · {group}" if group else label
        html_parts.append(
            "<div style='margin:9px 0;'>"
            f"<div style='display:flex;justify-content:space-between;gap:10px;font-size:12px;color:#334155;margin-bottom:3px;'>"
            f"<span>{escape(row_label)}</span><strong style='color:{BLUE_PALETTE['text']};'>{value_label}</strong></div>"
            f"<div style='height:12px;background:{BLUE_PALETTE['pale']};border-radius:8px;overflow:hidden;'>"
            f"<div style='width:{width:.1f}%;height:12px;background:{color};border-radius:8px;'></div>"
            "</div></div>"
        )

    html_parts.append("</div>")
    st.markdown("".join(html_parts), unsafe_allow_html=True)


def render_vertical_bar_chart(dataframe, x_field, y_field, color_field=None, domain=None, title=None, chart_height=150):
    if dataframe.empty:
        st.info("차트로 표시할 데이터가 없습니다.")
        return

    x_column = strip_altair_type(x_field)
    y_column = strip_altair_type(y_field)
    color_column = strip_altair_type(color_field) if color_field else None
    max_value = domain[1] if domain else max(float(value or 0) for value in dataframe[y_column].tolist()) or 1
    color_values = dataframe[color_column].dropna().unique().tolist() if color_column else []
    color_map = {
        value: [BLUE_PALETTE["primary"], BLUE_PALETTE["medium"], BLUE_PALETTE["dark"], BLUE_PALETTE["light"]][index % 4]
        for index, value in enumerate(color_values)
    }
    rows = dataframe.to_dict("records")
    bars = []

    for row in rows:
        label = str(row.get(x_column, ""))
        group = str(row.get(color_column, "")) if color_column else ""
        value = float(row.get(y_column, 0) or 0)
        height = min(max(value / max_value * chart_height, 0), chart_height)
        color = color_map.get(group, BLUE_PALETTE["primary"])
        value_label = f"{value:.1f}" if value % 1 else f"{int(value)}"
        bars.append(
            "<div style='flex:1;min-width:34px;display:flex;flex-direction:column;align-items:center;justify-content:flex-end;'>"
            f"<div style='font-size:11px;color:{BLUE_PALETTE['text']};font-weight:700;margin-bottom:4px;'>{value_label}</div>"
            f"<div title='{escape(label + (' · ' + group if group else ''))}' style='width:70%;max-width:34px;height:{height:.1f}px;background:{color};border-radius:5px 5px 0 0;'></div>"
            f"<div style='font-size:11px;color:#475569;margin-top:6px;text-align:center;line-height:1.15;min-height:28px;'>{escape(label)}</div>"
            "</div>"
        )

    legend = ""
    if color_column:
        legend = "".join(
            f"<span style='display:inline-flex;align-items:center;margin-right:10px;color:#475569;font-size:12px;'>"
            f"<span style='width:10px;height:10px;border-radius:2px;background:{color_map[value]};display:inline-block;margin-right:5px;'></span>"
            f"{escape(str(value))}</span>"
            for value in color_values
        )

    st.markdown(
        f"""
        <div style="border:1px solid #D9E6F5;border-radius:8px;padding:14px 16px;background:#FFFFFF;margin:10px 0 16px;">
          <div style="font-weight:700;color:{BLUE_PALETTE['text']};margin-bottom:8px;">{escape(title or '')}</div>
          <div style="margin-bottom:8px;">{legend}</div>
          <div style="height:{chart_height + 58}px;display:flex;gap:10px;align-items:flex-end;border-bottom:1px solid #D8E7F8;background:linear-gradient(to top,#F8FBFF,#FFFFFF);padding:8px 6px 0;">
            {''.join(bars)}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_grouped_vertical_bar_chart(
    dataframe,
    group_field,
    series_field,
    value_field,
    domain=None,
    title=None,
    chart_height=170,
    group_gap=12,
    inner_gap=3,
    bar_width=18,
    min_group_width=58,
    card_height=None,
):
    if dataframe.empty:
        st.info("차트로 표시할 데이터가 없습니다.")
        return

    group_column = strip_altair_type(group_field)
    series_column = strip_altair_type(series_field)
    value_column = strip_altair_type(value_field)
    groups = dataframe[group_column].dropna().unique().tolist()
    series_values = dataframe[series_column].dropna().unique().tolist()
    max_value = domain[1] if domain else max(float(value or 0) for value in dataframe[value_column].tolist()) or 1
    colors = [BLUE_PALETTE["dark"], BLUE_PALETTE["medium"], BLUE_PALETTE["primary"], BLUE_PALETTE["light"]]
    color_map = {value: colors[index % len(colors)] for index, value in enumerate(series_values)}

    group_blocks = []
    for group in groups:
        group_rows = dataframe[dataframe[group_column] == group]
        bars = []
        for series in series_values:
            matched = group_rows[group_rows[series_column] == series]
            value = float(matched.iloc[0][value_column]) if not matched.empty else 0
            height = min(max(value / max_value * chart_height, 0), chart_height)
            value_label = f"{value:.1f}" if value % 1 else f"{int(value)}"
            bars.append(
                "<div style='flex:1;display:flex;flex-direction:column;align-items:center;justify-content:flex-end;'>"
                f"<div style='font-size:10px;color:{BLUE_PALETTE['text']};font-weight:700;margin-bottom:3px;'>{value_label}</div>"
                f"<div title='{escape(str(group))} · {escape(str(series))}' style='width:{bar_width}px;height:{height:.1f}px;background:{color_map[series]};border-radius:4px 4px 0 0;'></div>"
                "</div>"
            )
        group_blocks.append(
            f"<div style='flex:1;min-width:{min_group_width}px;display:flex;flex-direction:column;align-items:center;'>"
            f"<div style='height:{chart_height + 20}px;width:100%;display:flex;gap:{inner_gap}px;align-items:flex-end;justify-content:center;'>{''.join(bars)}</div>"
            f"<div style='font-size:11px;color:#475569;margin-top:6px;text-align:center;line-height:1.15;min-height:28px;'>{escape(str(group))}</div>"
            "</div>"
        )

    legend = "".join(
        f"<span style='display:inline-flex;align-items:center;margin-right:10px;color:#475569;font-size:12px;'>"
        f"<span style='width:10px;height:10px;border-radius:2px;background:{color_map[value]};display:inline-block;margin-right:5px;'></span>"
        f"{escape(str(value))}</span>"
        for value in series_values
    )

    card_style = (
        f"height:{card_height}px;box-sizing:border-box;display:flex;flex-direction:column;"
        if card_height
        else ""
    )

    st.markdown(
        f"""
        <div style="border:1px solid #D9E6F5;border-radius:8px;padding:14px 16px;background:#FFFFFF;margin:10px 0 16px;{card_style}">
          <div style="font-weight:700;color:{BLUE_PALETTE['text']};margin-bottom:8px;">{escape(title or '')}</div>
          <div style="margin-bottom:8px;">{legend}</div>
          <div style="height:{chart_height + 58}px;display:flex;gap:{group_gap}px;align-items:flex-end;border-bottom:1px solid #D8E7F8;background:linear-gradient(to top,#F8FBFF,#FFFFFF);padding:8px 6px 0;overflow-x:auto;">
            {''.join(group_blocks)}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_pie_chart(dataframe, label_field, value_field, title=None, chart_height=228, pie_size=150):
    if dataframe.empty:
        st.info("차트로 표시할 데이터가 없습니다.")
        return

    label_column = strip_altair_type(label_field)
    value_column = strip_altair_type(value_field)
    rows = [row for row in dataframe.to_dict("records") if float(row.get(value_column, 0) or 0) > 0]
    total = sum(float(row.get(value_column, 0) or 0) for row in rows)
    if total <= 0:
        st.info("원형 차트로 표시할 값이 없습니다.")
        return

    colors = [BLUE_PALETTE["primary"], BLUE_PALETTE["medium"], BLUE_PALETTE["dark"], BLUE_PALETTE["light"]]
    cumulative = 0
    gradient_parts = []
    legend_parts = []
    for index, row in enumerate(rows):
        value = float(row.get(value_column, 0) or 0)
        start = cumulative / total * 100
        cumulative += value
        end = cumulative / total * 100
        color = colors[index % len(colors)]
        label = str(row.get(label_column, ""))
        percent = value / total * 100
        gradient_parts.append(f"{color} {start:.2f}% {end:.2f}%")
        legend_parts.append(
            f"<div style='display:flex;justify-content:space-between;gap:8px;font-size:12px;color:#334155;margin:5px 0;'>"
            f"<span><span style='display:inline-block;width:10px;height:10px;background:{color};border-radius:2px;margin-right:6px;'></span>{escape(label)}</span>"
            f"<strong style='color:{BLUE_PALETTE['text']};'>{int(value) if value % 1 == 0 else value:.1f} ({percent:.1f}%)</strong></div>"
        )

    st.markdown(
        f"""
        <div style="border:1px solid #D9E6F5;border-radius:8px;padding:14px 16px;background:#FFFFFF;margin:10px 0 16px;">
          <div style="font-weight:700;color:{BLUE_PALETTE['text']};margin-bottom:10px;">{escape(title or '')}</div>
          <div style="height:{chart_height}px;display:flex;align-items:center;gap:18px;">
            <div style="width:{pie_size}px;height:{pie_size}px;border-radius:50%;background:conic-gradient({', '.join(gradient_parts)});box-shadow:inset 0 0 0 32px #F8FBFF;flex:0 0 auto;"></div>
            <div style="flex:1;">{''.join(legend_parts)}</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_metric_line_comparison(metric_rows, title="4대 평가 지표 비교", compact=False, card_height=None):
    if not metric_rows:
        st.info("지표 비교 데이터를 찾을 수 없습니다.")
        return

    width = 720
    height = 250 if compact else 270
    padding_left = 54
    padding_right = 24
    padding_top = 28
    padding_bottom = 54
    chart_width = width - padding_left - padding_right
    chart_height = height - padding_top - padding_bottom
    max_score = 5
    point_count = max(len(metric_rows), 1)

    def point_x(index):
        if point_count == 1:
            return padding_left + chart_width / 2
        return padding_left + (chart_width / (point_count - 1)) * index

    def point_y(value):
        numeric_value = min(max(float(value or 0), 0), max_score)
        return padding_top + chart_height - (numeric_value / max_score * chart_height)

    def make_polyline(agent_key):
        return " ".join(
            f"{point_x(index):.1f},{point_y(row.get(agent_key, 0)):.1f}"
            for index, row in enumerate(metric_rows)
        )

    def make_points(agent_key, color):
        circles = []
        for index, row in enumerate(metric_rows):
            x = point_x(index)
            y = point_y(row.get(agent_key, 0))
            value = row.get(agent_key, 0)
            circles.append(
                f"<circle cx='{x:.1f}' cy='{y:.1f}' r='4.5' fill='{color}' stroke='white' stroke-width='2'>"
                f"<title>{escape(row['metric'])}: {value}</title></circle>"
            )
        return "".join(circles)

    horizontal_lines = []
    for score in range(0, max_score + 1):
        y = point_y(score)
        horizontal_lines.append(
            f"<line x1='{padding_left}' y1='{y:.1f}' x2='{width - padding_right}' y2='{y:.1f}' "
            "stroke='#D8E7F8' stroke-width='1'/>"
            f"<text x='{padding_left - 12}' y='{y + 4:.1f}' text-anchor='end' font-size='11' fill='#64748B'>{score}</text>"
        )

    x_labels = []
    for index, row in enumerate(metric_rows):
        x = point_x(index)
        x_labels.append(
            f"<text x='{x:.1f}' y='{height - 22}' text-anchor='middle' font-size='12' fill='#334155'>"
            f"{escape(row['metric'])}</text>"
        )

    rule_color = BLUE_PALETTE["dark"]
    api_color = BLUE_PALETTE["medium"]
    card_style = (
        f"height:{card_height}px;box-sizing:border-box;display:flex;flex-direction:column;"
        if card_height
        else ""
    )
    svg = f"""
    <div style="border:1px solid #D9E6F5;border-radius:8px;padding:14px 16px;background:#FFFFFF;margin:10px 0 16px;{card_style}">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;">
        <div style="font-weight:700;color:{BLUE_PALETTE['text']};">{escape(title)}</div>
        <div style="font-size:12px;color:#475569;">
          <span style="display:inline-flex;align-items:center;margin-right:12px;"><span style="width:18px;height:3px;background:{rule_color};display:inline-block;margin-right:5px;"></span>Rulebase</span>
          <span style="display:inline-flex;align-items:center;"><span style="width:18px;height:3px;background:{api_color};display:inline-block;margin-right:5px;"></span>API 기반</span>
        </div>
      </div>
      <svg viewBox="0 0 {width} {height}" style="width:100%;height:auto;display:block;background:#F8FBFF;border-radius:6px;">
        <text x="{width / 2}" y="18" text-anchor="middle" font-size="12" fill="#334155">Metric profile comparison</text>
        {''.join(horizontal_lines)}
        <line x1="{padding_left}" y1="{padding_top}" x2="{padding_left}" y2="{height - padding_bottom}" stroke="#AFC7E6" stroke-width="1"/>
        <line x1="{padding_left}" y1="{height - padding_bottom}" x2="{width - padding_right}" y2="{height - padding_bottom}" stroke="#AFC7E6" stroke-width="1"/>
        <polyline points="{make_polyline('rule_based')}" fill="none" stroke="{rule_color}" stroke-width="2.4"/>
        <polyline points="{make_polyline('api_based')}" fill="none" stroke="{api_color}" stroke-width="2.4"/>
        {make_points('rule_based', rule_color)}
        {make_points('api_based', api_color)}
        {''.join(x_labels)}
        <text x="16" y="{padding_top + chart_height / 2}" transform="rotate(-90 16 {padding_top + chart_height / 2})" text-anchor="middle" font-size="11" fill="#64748B">Score</text>
      </svg>
    </div>
    """
    st.markdown(svg, unsafe_allow_html=True)


def render_report_visual_summary(pipeline_outputs, rule_rate, api_rate, matched_rate):
    if not pipeline_outputs:
        return

    st.markdown("#### 결과 요약 차트")
    summary_data = pd.DataFrame(
        [
            {"항목": "규칙 기반 합격률", "비율": round(rule_rate, 1)},
            {"항목": "API 기반 합격률", "비율": round(api_rate, 1)},
            {"항목": "판정 일치율", "비율": round(matched_rate, 1)},
        ]
    )
    decision_data = build_decision_chart_data(pipeline_outputs)
    decision_summary = (
        decision_data.groupby("판정", as_index=False)["건수"].sum()
        if not decision_data.empty
        else pd.DataFrame(columns=["판정", "건수"])
    )

    row1_col1, row1_col2 = st.columns(2)
    with row1_col1:
        render_vertical_bar_chart(
            summary_data,
            "항목:N",
            "비율:Q",
            domain=[0, 100],
            title="합격률 및 판정 일치율",
            chart_height=170,
        )
    with row1_col2:
        render_pie_chart(
            decision_summary,
            "판정:N",
            "건수:Q",
            title="전체 판정 분포",
            chart_height=228,
            pie_size=190,
        )

    row2_col1, row2_col2 = st.columns(2)
    with row2_col1:
        render_metric_line_comparison(
            build_metric_profile_data(pipeline_outputs),
            title="Rulebase vs API 기반 지표 흐름",
            compact=True,
            card_height=318,
        )
    with row2_col2:
        render_grouped_vertical_bar_chart(
            build_category_chart_data(pipeline_outputs),
            "카테고리:N",
            "챗봇:N",
            "합격률:Q",
            domain=[0, 100],
            title="카테고리별 합격률",
            chart_height=160,
            card_height=318,
        )

    st.markdown("#### 4대 지표 평균")
    render_grouped_vertical_bar_chart(
        build_metric_chart_data(pipeline_outputs),
        "지표:N",
        "챗봇:N",
        "평균점수:Q",
        domain=[0, 5],
        title="지표별 평균 점수",
        chart_height=180,
        group_gap=34,
        inner_gap=1,
        bar_width=22,
        min_group_width=96,
    )


def render_agent_visual_summary(pipeline_outputs, agent_key):
    if not pipeline_outputs:
        return

    metrics = METRIC_DEFINITIONS
    if agent_key == "rule_based":
        st.info(
            "규칙 기반 평가는 기대 키워드 포함 여부만 검증하므로 정확성만 점수화합니다. "
            "근거성·유용성·안전성은 평가 대상이 아닙니다."
        )
        metrics = [metric for metric in METRIC_DEFINITIONS if metric["key"] == "accuracy"]

    selected_data = []
    for case in pipeline_outputs:
        row = {
            "케이스ID": case.get("case_id", ""),
            "판정": get_agent_decision(case, agent_key),
        }
        for metric in metrics:
            row[metric["label"]] = get_agent_metric_score(case, agent_key, metric["key"])
        selected_data.append(row)

    score_rows = []
    for row in selected_data:
        for metric in metrics:
            score_rows.append(
                {
                    "케이스ID": row["케이스ID"],
                    "지표": metric["label"],
                    "점수": row[metric["label"]],
                    "판정": row["판정"],
                }
            )

    decision_rows = pd.DataFrame(
        [
            {"판정": decision, "건수": sum(1 for row in selected_data if row["판정"] == decision)}
            for decision in ("PASS", "REVIEW", "FAIL")
        ]
    )
    chart_col1, chart_col2 = st.columns(2)
    with chart_col1:
        render_pie_chart(
            decision_rows,
            "판정:N",
            "건수:Q",
            title=f"{agent_label(agent_key)} 판정 분포",
        )
    with chart_col2:
        render_vertical_bar_chart(
            pd.DataFrame(score_rows),
            "케이스ID:N",
            "점수:Q",
            color_field="지표:N",
            domain=[0, 5],
            title=f"{agent_label(agent_key)} 케이스별 지표 점수",
        )


@st.dialog("테스트 수행 상세", width="large")
def show_execution_detail_dialog(history_item, focus_case_id=None):
    from testcase.helpers import get_execution_detail

    detail = get_execution_detail(history_item)
    stored_criteria = detail.get("quality_criteria") or history_item.get("quality_criteria")
    quality_criteria = get_quality_criteria(stored_criteria) if stored_criteria else LEGACY_CRITERIA
    total_count = max(history_item.get("total_count", 0), 1)
    rule_passed_count = detail["rule_passed_count"]
    api_passed_count = detail["api_passed_count"]
    matched_count = detail["matched_count"]
    pipeline_outputs = detail.get("pipeline_outputs", [])
    focused_case = next(
        (case for case in pipeline_outputs if str(case.get("case_id")) == str(focus_case_id)),
        None,
    )
    rule_rate = rule_passed_count / total_count * 100
    api_rate = api_passed_count / total_count * 100
    matched_rate = matched_count / total_count * 100
    release_decision, release_reason = compute_release_decision(
        pipeline_outputs, rule_rate, api_rate, quality_criteria
    )

    st.markdown(
        f"""
        <div class="detail-status">
            조회 중인 실행 결과: {history_item.get("executed_at", "-")} ·
            {history_item.get("total_count", 0)}건 ·
            규칙기반 {rule_rate:.1f}% / API기반 {api_rate:.1f}%
        </div>
        """,
        unsafe_allow_html=True,
    )

    if focus_case_id:
        if focused_case:
            st.warning(
                f"안전성 위반 연결 Case: **{focus_case_id}** · "
                f"{focused_case.get('category') or '미분류'} · "
                f"{focused_case.get('user_question') or '질문 정보 없음'}",
                icon=":material/policy_alert:",
            )
        else:
            st.warning(
                f"안전성 위반 Case `{focus_case_id}`가 이 실행의 저장된 상세 결과에서 확인되지 않습니다.",
                icon=":material/search_off:",
            )

    tab_compare, tab_rule, tab_api, tab_advanced, tab_result = st.tabs(
        ["전체 비교", "규칙 기반 챗봇", "API 기반 챗봇", "고도화 지표", "결과 보고서"]
    )

    with tab_compare:
        st.markdown("### 규칙 기반 vs API 기반 챗봇 - 전체 비교")
        st.caption(f"적용 판정 기준: {criteria_summary(quality_criteria)}")
        render_metric_definition_box()
        st.markdown(
            build_comparison_summary_html(
                rule_rate,
                rule_passed_count,
                api_rate,
                api_passed_count,
                total_count,
                release_decision,
                release_reason,
            ),
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div class="detail-note">전체 {total_count}개 케이스 중 두 방식의 판정이 일치한 케이스: '
            f'{matched_count}개 ({matched_rate:.1f}%)</div>',
            unsafe_allow_html=True,
        )
        render_report_visual_summary(pipeline_outputs, rule_rate, api_rate, matched_rate)
        st.markdown("#### 케이스별 판정 비교")
        st.dataframe(
            pd.DataFrame(detail["file_results"]),
            hide_index=True,
            use_container_width=True,
        )
        failed_rows = build_failed_case_rows(pipeline_outputs, quality_criteria)
        if failed_rows:
            st.markdown("#### 실패/위험 사례")
            st.dataframe(pd.DataFrame(failed_rows), hide_index=True, use_container_width=True)

    with tab_rule:
        render_agent_quality_report(
            pipeline_outputs,
            "rule_based",
            quality_criteria,
            {
                "run_id": history_item.get("id", "-"),
                "executed_at": history_item.get("executed_at", "-"),
                "target_files": history_item.get("target_files", "-"),
            },
        )

    with tab_api:
        render_agent_quality_report(
            pipeline_outputs,
            "api_based",
            quality_criteria,
            {
                "run_id": history_item.get("id", "-"),
                "executed_at": history_item.get("executed_at", "-"),
                "target_files": history_item.get("target_files", "-"),
            },
        )

    with tab_advanced:
        advanced_df = dataframe_from_pipeline_outputs(pipeline_outputs, quality_criteria)
        render_advanced_metrics_for_dataframe(
            advanced_df,
            f"분석 대상 실행: {history_item.get('id', '-')} · {history_item.get('executed_at', '-')}",
        )

    with tab_result:
        reports = detail.get("reports", {})
        render_report_tab(
            result_json_path=reports.get("json") if reports else None,
            run_id=history_item.get("id", "latest"),
            pipeline_outputs=pipeline_outputs,
            quality_criteria=quality_criteria.to_dict(),
        )

        report_rows = {
            "실행ID": history_item.get("id", "-"),
            "실행일시": history_item.get("executed_at", "-"),
            "대상파일": history_item.get("target_files", "-"),
            "실행폴더": history_item.get("run_dir", "-"),
            "로그파일": detail.get("log", "-"),
            "총 건수": history_item.get("total_count", 0),
            "성공": history_item.get("passed_count", 0),
            "실패": history_item.get("failed_count", 0),
            "소요시간(초)": history_item.get("duration_seconds", 0),
            "상태": history_item.get("status", "-"),
            "최종 판정": release_decision,
        }
        st.dataframe(
            pd.DataFrame([report_rows]),
            hide_index=True,
            use_container_width=True,
        )

        if reports:
            st.markdown("#### 생성 보고서")
            report_table = pd.DataFrame(
                [
                    {"구분": "JSON", "경로": reports.get("json", "")},
                    {"구분": "CSV", "경로": reports.get("csv", "")},
                    {"구분": "Markdown", "경로": reports.get("markdown", "")},
                    {"구분": "Archive", "경로": reports.get("archive", {}).get("run_dir", "") if isinstance(reports.get("archive"), dict) else ""},
                ]
            )
            st.dataframe(report_table, hide_index=True, use_container_width=True)

        inputs = detail.get("inputs", {})
        if inputs:
            st.markdown("#### 실행 입력 자료")
            input_table = pd.DataFrame(
                [
                    {"구분": "실행 테스트케이스", "경로": inputs.get("test_cases", "")},
                    {"구분": "선택 업로드 목록", "경로": inputs.get("selected_uploads", "")},
                ]
            )
            st.dataframe(input_table, hide_index=True, use_container_width=True)

        if pipeline_outputs:
            st.markdown("#### 전체 AI 답변 평가")
            for case in pipeline_outputs:
                rule_eval = case.get("rule_based", {}).get("evaluation_result", {})
                api_eval = case.get("api_based", {}).get("evaluation_result", {})
                with st.expander(f"{case.get('case_id')} · {case.get('category')} · {case.get('user_question')}"):
                    render_metric_line_comparison(
                        build_metric_profile_data(pipeline_outputs, case=case),
                        title=f"{case.get('case_id')} 지표별 Rulebase/API 점수 비교",
                    )
                    st.markdown("##### 규칙 기반 챗봇")
                    st.write(case.get("rule_based", {}).get("ai_answer", ""))
                    st.json(
                        {
                            "rule_validation": case.get("rule_based", {}).get("rule_validation", {}),
                            "evaluation_result": rule_eval,
                        },
                        expanded=False,
                    )

                    st.markdown("##### API 기반 챗봇")
                    st.write(case.get("api_based", {}).get("ai_answer", ""))
                    st.json(
                        {
                            "rule_validation": case.get("api_based", {}).get("rule_validation", {}),
                            "evaluation_result": api_eval,
                        },
                        expanded=False,
                    )


