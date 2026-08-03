from __future__ import annotations

from datetime import datetime
from html import escape

import pandas as pd
import streamlit as st

from core.paths import JIRA_REGISTERED_ISSUES_FILE
from core.storage import load_json_file, save_json_file
from services.jira_client import (
    JiraApiError,
    JiraConfigurationError,
    JiraIssueCreateError,
    build_issue_url,
    create_issue_for_fail_case,
    create_jira_issue,
    jira_environment_snapshot,
    list_project_issue_types,
    missing_jira_settings,
    search_jira_issues,
    test_jira_connection,
)


DEFAULT_JIRA_URL = (
    "https://byungjinna.atlassian.net/jira/software/projects/KAN/list"
    "?jql=project%20%3D%20KAN%20ORDER%20BY%20cf%5B10019%5D%20ASC"
)
DEFAULT_PRIORITIES = ["Highest", "High", "Medium", "Low", "Lowest"]
DEFAULT_ISSUE_TYPES = ["작업", "버그", "스토리", "에픽", "Task", "Bug"]


def render_jira_page(sub_menu: str) -> bool:
    _render_jira_css()
    _ensure_jira_state()

    if sub_menu == "Jira 현황":
        _render_jira_status_page()
    elif sub_menu == "Jira 등록":
        _render_jira_create_page()
    elif sub_menu == "등록 이력":
        _render_jira_history_page()
    elif sub_menu == "환경 설정":
        _render_jira_environment_page()
    else:
        return False
    return True


def _ensure_jira_state() -> None:
    st.session_state.setdefault(
        "jira_registered_issues",
        load_json_file(JIRA_REGISTERED_ISSUES_FILE, []),
    )


def _jira_sub_menu_label(sub_menu: str) -> str:
    return {
        "Jira 현황": "List",
        "Jira 등록": "Create",
        "등록 이력": "History",
        "환경 설정": "Settings",
    }.get(sub_menu, sub_menu)


def _render_jira_project_shell(sub_menu: str, *, title: str = "", description: str = "") -> None:
    snapshot = jira_environment_snapshot()
    project_key = snapshot.get("project_key") or "KAN"
    connection_class = "ready" if snapshot.get("ready") else "needs-config"
    connection_label = "Connected" if snapshot.get("ready") else "Setup required"
    tabs = [
        ("Summary", "dashboard"),
        ("Board", "view_kanban"),
        ("List", "table_rows"),
        ("Calendar", "calendar_month"),
        ("Timeline", "view_timeline"),
        ("Forms", "dynamic_form"),
        ("Issues", "bug_report"),
        ("Reports", "query_stats"),
    ]
    active_tab = "List" if sub_menu == "Jira 현황" else _jira_sub_menu_label(sub_menu)
    tab_html = "".join(
        f"""
        <span class="jira-tab {'active' if label == active_tab else ''}">
            <span class="jira-material">{"●" if label == active_tab else "○"}</span>{escape(label)}
        </span>
        """
        for label, _icon in tabs
    )
    st.html(
        f"""
        <section class="jira-project-shell">
            <div class="jira-project-top">
                <div class="jira-project-avatar">{escape(project_key[:1])}</div>
                <div class="jira-project-copy">
                    <div class="jira-breadcrumb">Projects / {escape(project_key)} / {_jira_sub_menu_label(sub_menu)}</div>
                    <h2>{escape(title or "ai_quality_final_project_2026")}</h2>
                    <p>{escape(description or "Jira 이슈를 조회하고 등록합니다.")}</p>
                </div>
                <div class="jira-project-actions">
                    <span class="jira-connection {connection_class}">{connection_label}</span>
                    <a href="{escape(DEFAULT_JIRA_URL)}" target="_blank" rel="noreferrer">Open in Jira ↗</a>
                </div>
            </div>
            <div class="jira-tabs">{tab_html}</div>
        </section>
        """,
    )


def _render_jira_header(title: str, description: str, *, icon: str = "hub") -> None:
    snapshot = jira_environment_snapshot()
    icon_symbol = {
        "hub": "🔗",
        "query_stats": "📊",
        "edit_square": "✍️",
        "history": "↩",
        "settings": "⚙️",
    }.get(icon, "🔗")
    state_badge = (
        "<span class='jira-badge green'>연결 준비</span>"
        if snapshot["ready"]
        else "<span class='jira-badge orange'>설정 필요</span>"
    )
    st.html(
        f"""
        <section class="jira-hero">
            <div class="jira-hero-icon">{icon_symbol}</div>
            <div class="jira-hero-copy">
                <div class="jira-eyebrow">Jira 관리</div>
                <h2>{title}</h2>
                <p>{description}</p>
            </div>
            <div class="jira-hero-side">
                {state_badge}
                <small>{snapshot.get('project_key') or 'KAN'} 프로젝트</small>
            </div>
        </section>
        """,
    )


def _render_jira_summary_cards(cards: list[dict]) -> None:
    columns = st.columns(len(cards), gap="small")
    for column, card in zip(columns, cards, strict=False):
        with column.container(border=True, height=104):
            st.caption(f":material/{card.get('icon', 'info')}: {card.get('label', '-')}")
            st.markdown(f"#### {card.get('value', '-')}")
            st.caption(card.get("detail", ""))


def _render_jira_issue_toolbar(result: dict, issues: list[dict]) -> None:
    status_counts = _issue_count_by(issues, "상태 분류")
    st.html(
        f"""
        <div class="jira-list-summary">
            <span><b>{int(result.get('total') or 0)}</b> issues</span>
            <span>To do <b>{status_counts.get('할 일', 0)}</b></span>
            <span>In progress <b>{status_counts.get('진행 중', 0)}</b></span>
            <span>Done <b>{status_counts.get('완료', 0)}</b></span>
        </div>
        """
    )


def _render_jira_issue_table(issues: list[dict]) -> None:
    if not issues:
        st.html(
            """
            <section class="jira-empty-list">
                <div class="jira-empty-icon">☑</div>
                <strong>No issues were found</strong>
                <p>현재 JQL 조건에 맞는 Jira 이슈가 없습니다. 새 이슈를 만들거나 조회 조건을 조정하세요.</p>
            </section>
            """
        )
        return

    rows = []
    for issue in issues:
        status_class = _jira_status_class(issue.get("상태 분류") or issue.get("상태"))
        priority_class = _jira_priority_class(issue.get("우선순위"))
        issue_type = str(issue.get("유형") or "-")
        issue_icon = _jira_issue_type_icon(issue_type)
        assignee = str(issue.get("담당자") or "미지정")
        avatar = "?" if assignee == "미지정" else assignee[:1].upper()
        url = str(issue.get("URL") or "")
        key = str(issue.get("키") or "-")
        key_html = (
            f'<a href="{escape(url)}" target="_blank" rel="noreferrer">{escape(key)}</a>'
            if url
            else escape(key)
        )
        rows.append(
            f"""
            <tr>
                <td class="jira-col-type"><span class="jira-issue-type">{escape(issue_icon)}</span></td>
                <td class="jira-col-key">{key_html}</td>
                <td class="jira-col-summary">{escape(str(issue.get('요약') or '-'))}</td>
                <td><span class="jira-status {status_class}">{escape(str(issue.get('상태') or '-'))}</span></td>
                <td><span class="jira-priority {priority_class}">{escape(str(issue.get('우선순위') or '-'))}</span></td>
                <td><span class="jira-avatar">{escape(avatar)}</span>{escape(assignee)}</td>
                <td>{escape(str(issue.get('수정일') or '-'))}</td>
            </tr>
            """
        )
    st.html(
        f"""
        <section class="jira-list-panel">
            <table class="jira-issue-table">
                <thead>
                    <tr>
                        <th></th>
                        <th>Key</th>
                        <th>Summary</th>
                        <th>Status</th>
                        <th>Priority</th>
                        <th>Assignee</th>
                        <th>Updated</th>
                    </tr>
                </thead>
                <tbody>{''.join(rows)}</tbody>
            </table>
        </section>
        """
    )


def _render_jira_status_page() -> None:
    snapshot = jira_environment_snapshot()
    _render_jira_project_shell(
        "Jira 현황",
        title="ai_quality_final_project_2026",
        description="KAN 프로젝트 이슈를 Jira List 화면처럼 조회하고 관리합니다.",
    )

    _render_environment_notice(snapshot)
    with st.container(border=True, key="jira_list_filter_bar"):
        filter_cols = st.columns([3.6, 0.75, 0.75, 0.75], gap="small", vertical_alignment="bottom")
        with filter_cols[0]:
            jql = st.text_input(
                "JQL",
                value=st.session_state.get("jira_status_jql", snapshot.get("default_jql", "")),
                key="jira_status_jql",
                placeholder="project = KAN ORDER BY cf[10019] ASC",
            )
        with filter_cols[1]:
            max_results = st.number_input(
                "Rows",
                min_value=1,
                max_value=100,
                value=int(st.session_state.get("jira_status_max_results", 50)),
                step=5,
                key="jira_status_max_results",
            )
        with filter_cols[2]:
            query_clicked = st.button(
                "Search",
                icon=":material/search:",
                type="primary",
                width="stretch",
                disabled=not snapshot["ready"],
            )
        with filter_cols[3]:
            if st.button("Create", icon=":material/add:", width="stretch", disabled=not snapshot["ready"]):
                st.session_state.current_sub_menu = "Jira 등록"
                st.rerun()

    if query_clicked or ("jira_status_result" not in st.session_state and snapshot["ready"]):
        with st.spinner("Jira 이슈를 조회하는 중입니다..."):
            try:
                st.session_state.jira_status_result = search_jira_issues(
                    jql,
                    max_results=int(max_results),
                )
                st.session_state.pop("jira_status_error", None)
            except (JiraConfigurationError, JiraApiError) as exc:
                st.session_state.jira_status_error = str(exc)

    if st.session_state.get("jira_status_error"):
        st.error(st.session_state["jira_status_error"], icon=":material/error:")
        return

    result = st.session_state.get("jira_status_result")
    if not result:
        st.info("Jira 설정을 완료하면 KAN 프로젝트 현황을 바로 조회할 수 있습니다.", icon=":material/info:")
        return

    issues = result.get("issues", [])
    _render_jira_issue_toolbar(result, issues)

    frame = pd.DataFrame(issues)
    if frame.empty:
        _render_jira_issue_table([])
        return

    _render_jira_issue_table(issues)
    with st.container(horizontal=True, horizontal_alignment="right"):
        csv_bytes = frame.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            "Export CSV",
            data=csv_bytes,
            file_name=f"jira_issues_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
            icon=":material/download:",
        )


def _render_jira_create_page() -> None:
    snapshot = jira_environment_snapshot()
    _render_jira_project_shell(
        "Jira 등록",
        title="Create issue",
        description="결함, 개선 요청, 작업 항목을 Jira 이슈로 직접 등록합니다.",
    )
    _render_environment_notice(snapshot)

    issue_types = _load_issue_type_names(snapshot["ready"])
    latest_result = st.session_state.pop("jira_create_notice", None)
    if isinstance(latest_result, dict):
        st.toast(
            f"Jira 이슈 {latest_result.get('issue_key', '-')}를 등록했습니다.",
            icon=":material/check_circle:",
        )
        if latest_result.get("issue_url"):
            with st.container(horizontal=True, horizontal_alignment="right"):
                st.caption(f"최근 등록 · {latest_result.get('issue_key', '-')}")
                st.link_button(
                    "Jira에서 열기",
                    latest_result["issue_url"],
                    icon=":material/open_in_new:",
                )

    with st.container(border=True, horizontal=True, vertical_alignment="center"):
        with st.container(gap=None):
            st.markdown("#### Jira 이슈 등록")
            st.caption("필요할 때만 등록 창을 열어 현재 화면의 공간을 작게 유지합니다.")
        with st.container(horizontal=True, horizontal_alignment="right", vertical_alignment="center"):
            with st.popover("작성 예시", icon=":material/lightbulb:", width="content"):
                _render_jira_create_examples()
            if st.button(
                "Jira 이슈 등록",
                icon=":material/add_task:",
                type="primary",
                width="content",
                key="open_jira_issue_create_dialog",
            ):
                _render_jira_create_dialog(snapshot, issue_types)


def _render_jira_create_examples() -> None:
    st.markdown(
        """
        - **결함**: `[VOC] TC-16 관련 VOC 근거 부족으로 답변 보류`
        - **개선 요청**: `[VOC] 타당성 평가 보완 입력 UX 개선`
        - **작업**: `[시연] 최종 인수·시연 화면 문구 정리`
        """
    )


@st.dialog(
    "Jira 이슈 등록",
    width="medium",
    icon=":material/add_task:",
    on_dismiss="rerun",
)
def _render_jira_create_dialog(snapshot: dict, issue_types: list[str]) -> None:
    project_key = snapshot.get("project_key") or "KAN"
    st.caption(f"Project {project_key} · 결함, 개선 요청 또는 작업 항목을 등록합니다.")
    _render_environment_notice(snapshot)

    with st.form("jira_issue_create_dialog_form", border=False):
        summary = st.text_input(
            "요약",
            placeholder="[VOC] TC-16 근거 부족 보완 필요",
            max_chars=255,
        )

        issue_cols = st.columns(2, gap="small")
        with issue_cols[0]:
            issue_type = st.selectbox("이슈 유형", issue_types or DEFAULT_ISSUE_TYPES, index=0)
        with issue_cols[1]:
            priority = st.selectbox("우선순위", [""] + DEFAULT_PRIORITIES, index=0)

        reference_cols = st.columns(2, gap="small")
        with reference_cols[0]:
            case_id = st.text_input("Case ID", placeholder="TC-16")
        with reference_cols[1]:
            run_id = st.text_input("Run ID", placeholder="RUN-...")

        labels_text = st.text_input("라벨", value="voc-quality,qa", placeholder="쉼표로 구분")
        description = st.text_area(
            "설명",
            height=180,
            placeholder=(
                "현상:\n"
                "- \n\n"
                "기대 결과:\n"
                "- \n\n"
                "재현/확인 방법:\n"
                "- "
            ),
        )
        submitted = st.form_submit_button(
            "Jira 이슈 등록",
            icon=":material/add_task:",
            type="primary",
            disabled=not snapshot.get("ready", False),
            width="stretch",
        )

    if not submitted:
        return

    labels = _split_labels(labels_text)
    if case_id.strip():
        labels.append(case_id.strip().replace(" ", "-"))
    full_description = _compose_issue_description(
        description=description,
        case_id=case_id,
        run_id=run_id,
    )
    with st.spinner("Jira 이슈를 등록하는 중입니다..."):
        try:
            created = create_jira_issue(
                summary=summary,
                description=full_description,
                issue_type=issue_type,
                priority=priority,
                labels=labels,
            )
        except (JiraConfigurationError, JiraIssueCreateError) as exc:
            st.error(str(exc), icon=":material/error:")
            return

    history_item = {
        "created_at": created.get("created_at", datetime.now().isoformat(timespec="seconds")),
        "issue_key": created.get("key", "-"),
        "issue_url": created.get("url", ""),
        "summary": summary,
        "issue_type": issue_type,
        "priority": priority or "-",
        "case_id": case_id,
        "run_id": run_id,
    }
    st.session_state.jira_registered_issues.insert(0, history_item)
    save_json_file(JIRA_REGISTERED_ISSUES_FILE, st.session_state.jira_registered_issues)
    st.session_state["jira_create_notice"] = history_item
    st.rerun()


def _render_jira_history_page() -> None:
    _render_jira_project_shell(
        "등록 이력",
        title="Created from this app",
        description="이 Streamlit 화면에서 Jira로 등록한 이슈 이력을 확인합니다.",
    )
    history = st.session_state.get("jira_registered_issues", [])
    _render_jira_summary_cards(
        [
            {
                "icon": "format_list_numbered",
                "label": "앱 등록 이력",
                "value": f"{len(history)}건",
                "detail": "로컬 기록 기준",
            },
            {
                "icon": "link",
                "label": "Jira 연결",
                "value": "사용 가능" if jira_environment_snapshot()["ready"] else "설정 필요",
                "detail": "API 토큰 설정 기준",
            },
        ]
    )
    if not history:
        st.info("아직 이 화면에서 등록한 Jira 이슈가 없습니다.", icon=":material/info:")
        return
    frame = pd.DataFrame(history)
    st.dataframe(
        frame,
        hide_index=True,
        width="stretch",
        column_config={
            "issue_url": st.column_config.LinkColumn("Jira 열기", display_text="열기"),
            "summary": st.column_config.TextColumn("요약", width="large"),
        },
    )
    st.download_button(
        "등록 이력 다운로드",
        data=frame.to_csv(index=False).encode("utf-8-sig"),
        file_name="jira_registered_issues.csv",
        mime="text/csv",
        icon=":material/download:",
    )


def _render_jira_environment_page() -> None:
    snapshot = jira_environment_snapshot()
    _render_jira_project_shell(
        "환경 설정",
        title="Jira connection settings",
        description="Jira REST API 연결에 필요한 설정 상태를 확인합니다.",
    )

    _render_jira_summary_cards(
        [
            {
                "icon": "cloud",
                "label": "Jira 주소",
                "value": "설정됨" if snapshot["base_url"] else "필요",
                "detail": snapshot["base_url"] or "JIRA_BASE_URL",
            },
            {
                "icon": "alternate_email",
                "label": "계정 이메일",
                "value": "설정됨" if snapshot["email_configured"] else "필요",
                "detail": "값은 화면에 표시하지 않음",
            },
            {
                "icon": "key",
                "label": "API Key/Token",
                "value": "설정됨" if snapshot["api_token_configured"] else "필요",
                "detail": snapshot.get("credential_source") or "JIRA_API_KEY 사용 가능",
            },
            {
                "icon": "inventory_2",
                "label": "Project",
                "value": snapshot["project_key"] or "필요",
                "detail": "예: KAN",
            },
        ]
    )

    with st.container(border=True):
        st.markdown("#### :material/check_circle: 연결 테스트")
        if snapshot["missing"]:
            st.warning(f"누락 설정: {', '.join(snapshot['missing'])}", icon=":material/warning:")
        else:
            if st.button("Jira 연결 테스트", type="primary", icon=":material/lan:", width="stretch"):
                with st.spinner("Jira 계정과 프로젝트 접근 권한을 확인하는 중입니다..."):
                    try:
                        result = test_jira_connection()
                    except (JiraConfigurationError, JiraApiError) as exc:
                        st.error(str(exc), icon=":material/error:")
                    else:
                        st.success(
                            f"{result['account_display_name']} 계정으로 "
                            f"{result['project_key']} · {result['project_name']} 프로젝트에 연결되었습니다.",
                            icon=":material/check_circle:",
                        )

    with st.container(border=True):
        st.markdown("#### :material/tune: .env 설정 예시")
        st.code(
            """JIRA_BASE_URL=https://byungjinna.atlassian.net
JIRA_EMAIL=your-email@example.com
JIRA_API_KEY=your-atlassian-api-token
JIRA_PROJECT_KEY=KAN
JIRA_DEFAULT_JQL=project = KAN ORDER BY cf[10019] ASC""",
            language="dotenv",
        )
        st.caption(
            "브라우저 로그인 세션은 Streamlit 서버에서 사용할 수 없으므로 API 토큰이 필요합니다. "
            "이 프로젝트는 JIRA_API_KEY와 JIRA_API_TOKEN 이름을 모두 지원합니다. "
            "비밀값은 .env에만 저장하고 GitHub/Notion/보고서에는 기록하지 않습니다."
        )
        st.link_button("Jira KAN 목록 열기", DEFAULT_JIRA_URL, icon=":material/open_in_new:")


def _render_environment_notice(snapshot: dict) -> None:
    if snapshot.get("ready"):
        return
    missing = ", ".join(snapshot.get("missing") or [])
    st.warning(
        f"Jira API 설정이 필요합니다. 누락: {missing}",
        icon=":material/warning:",
    )


def _load_issue_type_names(ready: bool) -> list[str]:
    if not ready:
        return DEFAULT_ISSUE_TYPES
    if "jira_issue_type_names" not in st.session_state:
        try:
            rows = list_project_issue_types()
            names = [item["name"] for item in rows]
        except (JiraConfigurationError, JiraApiError):
            names = []
        st.session_state.jira_issue_type_names = names or DEFAULT_ISSUE_TYPES
    return st.session_state.jira_issue_type_names


def _issue_count_by(issues: list[dict], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for issue in issues:
        key = str(issue.get(field) or "-")
        counts[key] = counts.get(key, 0) + 1
    return counts


def _jira_status_class(value: object) -> str:
    text = str(value or "").strip().lower()
    if text in {"완료", "done", "closed", "resolved"}:
        return "done"
    if text in {"진행 중", "in progress", "indeterminate", "review", "검토"}:
        return "progress"
    if text in {"할 일", "to do", "open", "new", "대기"}:
        return "todo"
    return "neutral"


def _jira_priority_class(value: object) -> str:
    text = str(value or "").strip().lower()
    if text in {"highest", "high", "critical"}:
        return "high"
    if text in {"lowest", "low"}:
        return "low"
    return "medium"


def _jira_issue_type_icon(value: object) -> str:
    text = str(value or "").strip().lower()
    if text in {"bug", "버그", "결함"}:
        return "●"
    if text in {"story", "스토리"}:
        return "◆"
    if text in {"epic", "에픽"}:
        return "⬟"
    return "■"


def _split_labels(labels_text: str) -> list[str]:
    return [
        label.strip().replace(" ", "-")
        for label in str(labels_text or "").split(",")
        if label.strip()
    ]


def _compose_issue_description(*, description: str, case_id: str, run_id: str) -> str:
    lines = []
    if case_id.strip():
        lines.append(f"Case ID: {case_id.strip()}")
    if run_id.strip():
        lines.append(f"Run ID: {run_id.strip()}")
    if lines:
        lines.append("")
    lines.append(description.strip() or "-")
    return "\n".join(lines)


def _build_issue_url(result: dict) -> str:
    key = result.get("key", "")
    if key:
        return build_issue_url(key)
    self_url = result.get("self", "")
    if not self_url:
        return ""
    return self_url.split("/rest/api/", 1)[0]


def _render_jira_css() -> None:
    st.html(
        """
        <style>
        .jira-project-shell{
            margin:0 0 12px;padding:14px 16px 0;border:1px solid #dfe1e6;border-radius:12px;
            background:#ffffff;font-family:'Segoe UI','Malgun Gothic',sans-serif;
            box-shadow:0 2px 8px rgba(9,30,66,.04);
        }
        .jira-project-top{display:grid;grid-template-columns:42px 1fr auto;gap:12px;align-items:center}
        .jira-project-avatar{
            display:grid;place-items:center;width:38px;height:38px;border-radius:8px;background:#0052cc;
            color:#fff;font-size:18px;font-weight:900;text-transform:uppercase;
        }
        .jira-project-copy{min-width:0}.jira-breadcrumb{color:#6b778c;font-size:11px;font-weight:700}
        .jira-project-copy h2{margin:1px 0;color:#172b4d;font-size:24px;line-height:1.15;letter-spacing:-.03em}
        .jira-project-copy p{margin:0;color:#5e6c84;font-size:12px}
        .jira-project-actions{display:flex;align-items:center;gap:8px;justify-content:flex-end}
        .jira-project-actions a{
            display:inline-flex;align-items:center;height:30px;padding:0 10px;border:1px solid #dfe1e6;
            border-radius:4px;background:#f4f5f7;color:#172b4d;text-decoration:none;font-size:11px;font-weight:800;
        }
        .jira-connection{
            display:inline-flex;align-items:center;height:24px;padding:0 8px;border-radius:999px;
            font-size:10px;font-weight:900;border:1px solid transparent;white-space:nowrap;
        }
        .jira-connection.ready{background:#e3fcef;color:#006644;border-color:#abf5d1}
        .jira-connection.needs-config{background:#fffae6;color:#974f0c;border-color:#ffe380}
        .jira-tabs{display:flex;align-items:center;gap:2px;margin-top:13px;border-bottom:1px solid #dfe1e6;overflow-x:auto}
        .jira-tab{
            display:inline-flex;align-items:center;gap:5px;height:34px;padding:0 10px;border-bottom:2px solid transparent;
            color:#42526e;font-size:12px;font-weight:800;white-space:nowrap;
        }
        .jira-tab.active{color:#0052cc;border-bottom-color:#0052cc}
        .jira-material{font-size:8px;color:#6b778c}.jira-tab.active .jira-material{color:#0052cc}
        .jira-list-summary{
            display:flex;align-items:center;justify-content:flex-end;gap:8px;margin:8px 0 6px;
            color:#5e6c84;font-family:'Segoe UI','Malgun Gothic',sans-serif;font-size:11px;
        }
        .jira-list-summary span{
            display:inline-flex;align-items:center;gap:4px;height:24px;padding:0 8px;border-radius:999px;
            background:#f4f5f7;border:1px solid #ebecf0;white-space:nowrap;
        }
        .jira-list-summary b{color:#172b4d}
        .jira-list-panel{
            margin:0 0 10px;border:1px solid #dfe1e6;border-radius:8px;background:#fff;
            overflow:hidden;font-family:'Segoe UI','Malgun Gothic',sans-serif;
        }
        .jira-issue-table{width:100%;border-collapse:collapse;table-layout:fixed}
        .jira-issue-table thead th{
            height:34px;padding:0 10px;border-bottom:1px solid #dfe1e6;background:#f7f8f9;
            color:#44546f;font-size:11px;text-align:left;font-weight:900;
        }
        .jira-issue-table tbody td{
            height:42px;padding:0 10px;border-bottom:1px solid #ebecf0;color:#172b4d;
            font-size:12px;vertical-align:middle;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
        }
        .jira-issue-table tbody tr:hover{background:#f4f8ff}
        .jira-issue-table tbody tr:last-child td{border-bottom:none}
        .jira-col-type{width:34px}.jira-col-key{width:86px}.jira-col-summary{width:auto}
        .jira-col-key a{color:#0052cc;text-decoration:none;font-weight:900}
        .jira-issue-type{
            display:grid;place-items:center;width:18px;height:18px;border-radius:4px;background:#deebff;color:#0052cc;
            font-size:9px;font-weight:900;
        }
        .jira-status{
            display:inline-flex;align-items:center;height:22px;padding:0 8px;border-radius:3px;
            font-size:10px;font-weight:900;text-transform:uppercase;
        }
        .jira-status.todo{background:#ebecf0;color:#42526e}
        .jira-status.progress{background:#deebff;color:#0747a6}
        .jira-status.done{background:#e3fcef;color:#006644}
        .jira-status.neutral{background:#f4f5f7;color:#5e6c84}
        .jira-priority{
            display:inline-flex;align-items:center;height:22px;padding:0 7px;border-radius:4px;font-size:10px;font-weight:900;
            background:#f4f5f7;color:#42526e;
        }
        .jira-priority.high{background:#ffebe6;color:#bf2600}
        .jira-priority.medium{background:#fffae6;color:#974f0c}
        .jira-priority.low{background:#e3fcef;color:#006644}
        .jira-avatar{
            display:inline-grid;place-items:center;width:22px;height:22px;margin-right:6px;border-radius:999px;
            background:#dfe1e6;color:#172b4d;font-size:10px;font-weight:900;vertical-align:middle;
        }
        .jira-empty-list{
            display:grid;place-items:center;min-height:220px;margin:0 0 10px;padding:20px;border:1px solid #dfe1e6;
            border-radius:8px;background:#fff;font-family:'Segoe UI','Malgun Gothic',sans-serif;text-align:center;
        }
        .jira-empty-icon{display:grid;place-items:center;width:46px;height:46px;border-radius:14px;background:#deebff;color:#0052cc;font-size:22px;margin-bottom:8px}
        .jira-empty-list strong{color:#172b4d;font-size:18px}.jira-empty-list p{margin:5px 0 0;color:#5e6c84;font-size:12px}
        .jira-hero{
            display:grid;grid-template-columns:44px 1fr auto;gap:14px;align-items:center;
            min-height:86px;margin:0 0 12px;padding:15px 16px;border:1px solid #c8d9ee;
            border-left:5px solid #155a96;border-radius:14px;background:linear-gradient(135deg,#f7fbff,#ffffff);
            box-shadow:0 4px 12px rgba(22,78,128,.05);font-family:'Segoe UI','Malgun Gothic',sans-serif;
        }
        .jira-hero-icon{display:grid;place-items:center;width:38px;height:38px;border-radius:12px;background:#e7f1fb;color:#155a96;font-size:20px}
        .jira-eyebrow{font-size:10px;font-weight:900;color:#4f6a86;letter-spacing:.04em}
        .jira-hero h2{margin:2px 0 2px;color:#073b72;font-size:25px;line-height:1.15;letter-spacing:-.04em}
        .jira-hero p{margin:0;color:#52677d;font-size:12px}
        .jira-hero-side{display:flex;flex-direction:column;align-items:flex-end;gap:4px}
        .jira-hero-side small{color:#708096;font-size:10px;font-weight:800}
        .jira-badge{display:inline-flex;align-items:center;justify-content:center;height:25px;padding:0 10px;border-radius:999px;font-size:10px;font-weight:900;border:1px solid transparent}
        .jira-badge.green{background:#eaf7ef;color:#176b35;border-color:#a9d7b8}
        .jira-badge.orange{background:#fff7e6;color:#92550a;border-color:#e8c47b}
        @media(max-width:780px){
            .jira-project-top{grid-template-columns:38px 1fr}.jira-project-actions{grid-column:1/3;justify-content:flex-start}
            .jira-hero{grid-template-columns:38px 1fr}.jira-hero-side{grid-column:1/3;align-items:flex-start}
        }
        </style>
        """,
    )
