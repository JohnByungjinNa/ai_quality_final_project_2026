from __future__ import annotations

from html import escape

import streamlit as st

from services.integration_status_service import collect_integration_status


OPS_CARD_ICONS = {
    "AWS 세션": ":material/cloud:",
    "AI API": ":material/api:",
    "S3 증적": ":material/cloud_upload:",
    "최근 VOC Run": ":material/fact_check:",
}
AI_PROVIDER_ICONS = {
    "OpenAI": ":material/hub:",
    "Anthropic": ":material/psychology:",
    "Gemini": ":material/auto_awesome:",
}


@st.cache_data(ttl=30, max_entries=1, show_spinner=False)
def load_integration_status() -> dict:
    return collect_integration_status()


def render_integration_status(snapshot: dict, *, context: str) -> None:
    aws = snapshot.get("aws") or {}
    ai = snapshot.get("ai") or {}
    evidence = snapshot.get("evidence") or {}
    voc = snapshot.get("voc") or {}

    titles = {
        "overview": ("VOC 운영·외부 연동 준비도", "최신 VOC 판정과 AWS 증적·AI API 실행 준비 상태"),
        "voc": ("실행·증적 연동 준비도", ""),
        "ops": ("외부 연동 상태", "AWS 임시 인증과 AI Provider 구성 상태를 비밀값 노출 없이 확인"),
    }
    title, description = titles.get(context, titles["overview"])
    st.markdown(f"#### :material/hub: {title}")
    if description:
        st.caption(description)

    metrics = _metric_values(aws, ai, evidence, voc, context=context)
    if context == "ops":
        _render_ops_integration_cards(metrics, ai.get("providers", []))
    elif context == "overview":
        _render_overview_integration_cards(metrics)
    elif context == "voc":
        _render_voc_integration_cards(metrics, aws=aws, ai=ai, evidence=evidence, voc=voc)
    else:
        with st.container(horizontal=True):
            for label, value, detail in metrics:
                st.metric(label, value, detail, border=True)


def _render_voc_integration_cards(metrics, *, aws, ai, evidence, voc) -> None:
    tones = {
        "AWS 세션": (
            "good" if aws.get("authenticated")
            else "warn" if aws.get("session_status") == "login_required"
            else "bad"
        ),
        "AI API": (
            "good" if ai.get("all_configured")
            else "warn" if int(ai.get("configured_count") or 0) > 0
            else "bad"
        ),
        "S3 증적": (
            "good" if evidence.get("configuration_ready") else "warn"
        ),
        "최근 VOC Run": (
            "neutral" if not voc.get("available")
            else "good" if str(voc.get("status") or "").upper() == "COMPLETED"
            else "bad" if str(voc.get("status") or "").upper() in {"FAILED", "ERROR"}
            else "warn"
        ),
    }
    icons = {
        "AWS 세션": "cloud_upload",
        "AI API": "api",
        "S3 증적": "cloud_upload",
        "최근 VOC Run": "fact_check",
    }
    cards = "".join(
        (
            f"<article class='vqd-status-card {tones.get(label, 'neutral')}'>"
            f"<span class='vqd-status-icon'>{_integration_svg_icon(icons.get(label, 'link'))}</span>"
            f"<span class='vqd-status-label'>{escape(str(label))}</span>"
            f"<strong>{escape(str(value))}</strong>"
            f"<small>{escape(str(detail or ''))}</small>"
            "</article>"
        )
        for label, value, detail in metrics
    )
    st.markdown(
        f"<div class='vqd-status-row vqd-integration-row'>{cards}</div>",
        unsafe_allow_html=True,
    )

def _render_ops_integration_cards(metrics, providers) -> None:
    with st.container(horizontal=True):
        for label, value, detail in metrics:
            with st.container(border=True, height="stretch"):
                icon = OPS_CARD_ICONS.get(label, ":material/link:")
                if label == "AI API":
                    configured_count = sum(bool(provider.get("configured")) for provider in providers)
                    with st.container(
                        horizontal=True,
                        horizontal_alignment="distribute",
                        vertical_alignment="center",
                    ):
                        st.markdown(f"##### {icon} {label}")
                        st.markdown(f"##### {configured_count}/{len(providers)}")
                    with st.container(horizontal=True, gap="xsmall"):
                        for provider in providers:
                            name = str(provider.get("name") or "AI")
                            configured = bool(provider.get("configured"))
                            tone = "green" if configured else "gray"
                            provider_icon = AI_PROVIDER_ICONS.get(name, ":material/api:")
                            st.markdown(f":{tone}-badge[{provider_icon}]")
                    continue

                st.markdown(f"##### {icon} {label}")
                st.metric(
                    "상태 값",
                    value,
                    detail,
                    label_visibility="collapsed",
                    delta_arrow="off",
                )


def _render_overview_integration_cards(metrics) -> None:
    cards = "".join(
        _overview_integration_card_html(label, value, detail)
        for label, value, detail in metrics
    )
    st.markdown(
        f'<div class="aqd-kpi-row aqd-integration-row">{cards}</div>',
        unsafe_allow_html=True,
    )


def _overview_integration_card_html(label: str, value: str, detail: str) -> str:
    icon_name = {
        "최근 VOC Run": "fact_check",
        "배포 판정": "deployment",
        "AWS 증적": "cloud_upload",
        "AI API": "api",
    }.get(label, "link")
    tooltip = f"{label}의 현재 연동 준비 상태입니다.\n현재 표시: {value}"
    if detail:
        tooltip += f" · {detail}"
    escaped_tooltip = escape(tooltip, quote=True)
    return (
        f"<article class='aqd-kpi' tabindex='0' data-tooltip='{escaped_tooltip}' "
        f"aria-label='{escape(label, quote=True)}. {escaped_tooltip}'>"
        f"<div class='aqd-kpi-icon'>{_integration_svg_icon(icon_name)}</div>"
        f"<div><span class='aqd-kpi-label'>{escape(label)}<i aria-hidden='true'>ⓘ</i></span>"
        f"<strong>{escape(str(value))}</strong><small>{escape(str(detail or ''))}</small></div>"
        "</article>"
    )


def _integration_svg_icon(name: str) -> str:
    paths = {
        "fact_check": "<path d='M7 4h10l2 3v13H5V7l2-3Z'/><path d='m8 12 2 2 4-4m-6 7h8'/>",
        "deployment": "<path d='M4 19h16M7 16V8h10v8M9 8V5h6v3'/><path d='m10 12 2 2 3-4'/>",
        "cloud_upload": "<path d='M7 18H6a4 4 0 0 1-.5-8A6 6 0 0 1 17 8a4 4 0 0 1 1 7.9'/><path d='m9 14 3-3 3 3m-3-3v9'/>",
        "api": "<path d='M8 8 4 12l4 4m8-8 4 4-4 4M14 5l-4 14'/>",
        "link": "<path d='M10 13a5 5 0 0 0 7.5.5l2-2a5 5 0 0 0-7-7l-1 1'/><path d='M14 11a5 5 0 0 0-7.5-.5l-2 2a5 5 0 0 0 7 7l1-1'/>",
    }
    return (
        "<svg viewBox='0 0 24 24' aria-hidden='true' fill='none' stroke='currentColor' "
        "stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'>"
        + paths[name]
        + "</svg>"
    )


def _metric_values(aws: dict, ai: dict, evidence: dict, voc: dict, *, context: str):
    ai_value = f"{int(ai.get('configured_count') or 0)} / {int(ai.get('total_count') or 0)} 설정"
    ai_names = ", ".join(
        provider.get("name", "")
        for provider in ai.get("providers", [])
        if provider.get("configured")
    ) or "사용 가능한 Provider 없음"
    aws_value, aws_detail = _aws_label(aws)
    upload_count = int(evidence.get("upload_count") or 0)
    evidence_value = f"업로드 {upload_count}건" if upload_count else (
        "구성 완료" if evidence.get("configuration_ready") else "구성 필요"
    )
    latest_evidence = evidence.get("latest") or {}
    evidence_detail = (
        f"최근 {latest_evidence.get('run_id')} · 파일 {int(latest_evidence.get('file_count') or 0)}개"
        if latest_evidence else "아직 S3 업로드 증적 없음"
    )

    if context == "overview":
        if voc.get("available"):
            voc_value = _run_status_label(voc.get("status"))
            voc_detail = f"통과 {int(voc.get('pass_count') or 0)} · 확인 필요 {int(voc.get('attention_count') or 0)}"
            decision_value = _decision_label(voc.get("deployment_decision"))
            decision_detail = str(voc.get("run_id") or "최근 Run")
        else:
            voc_value, voc_detail = "이력 없음", "VOC 품질진단 실행 필요"
            decision_value, decision_detail = "미판정", "최근 Run 없음"
        return [
            ("최신 VOC Run", voc_value, voc_detail),
            ("배포 판정", decision_value, decision_detail),
            ("AWS 증적", evidence_value, evidence_detail),
            ("AI API", ai_value, ai_names),
        ]

    return [
        ("AWS 세션", aws_value, aws_detail),
        ("AI API", ai_value, ai_names),
        ("S3 증적", evidence_value, evidence_detail),
        (
            "최근 VOC Run",
            _run_status_label(voc.get("status")) if voc.get("available") else "이력 없음",
            str(voc.get("run_id") or "VOC 품질진단 실행 필요"),
        ),
    ]


def _aws_label(aws: dict) -> tuple[str, str]:
    if aws.get("authenticated"):
        return "연결됨", f"{aws.get('profile')} · {aws.get('region')}"
    status = aws.get("session_status")
    if status == "cli_missing":
        return "CLI 미설치", "워크스테이션 초기 설정 필요"
    if status == "profile_missing":
        return "프로필 없음", "JohnNa-QA 프로필 설정 필요"
    if status == "unexpected_principal":
        return "사용자 확인", "JohnNa-QA로 다시 로그인 필요"
    return "로그인 필요", "브라우저 임시 인증 세션 없음"


def _decision_label(value: str | None) -> str:
    return {
        "PASS": "배포 가능",
        "APPROVED": "승인 완료",
        "REVISION_REQUIRED": "보완 필요",
        "REJECTED": "배포 불가",
        "NOT_VERIFIED": "미판정",
    }.get(str(value or "NOT_VERIFIED").upper(), str(value or "미판정"))


def _run_status_label(value: str | None) -> str:
    return {
        "COMPLETED": "완료",
        "RUNNING": "수행 중",
        "FAILED": "실패",
        "STOPPED": "중지",
        "ERROR": "오류",
    }.get(str(value or "UNKNOWN").upper(), str(value or "미확인"))
