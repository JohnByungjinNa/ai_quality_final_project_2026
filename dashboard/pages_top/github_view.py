import html
import subprocess
from pathlib import Path

import pandas as pd
import streamlit as st

from services.github_service import (
    build_project_source_archive,
    collect_git_environment,
    collect_repository_home,
    create_sync_backup_branch,
    clone_repository,
    configure_repository,
    create_branch,
    create_commit,
    download_project_from_github,
    fetch_origin,
    collect_sync_preflight,
    merge_origin_into_current_branch,
    pull_current_branch,
    push_current_branch,
    readiness_checks,
    run_git,
    run_github_sync_validation,
    save_project_to_github,
    stash_and_download_project_from_github,
    verify_remote_connection,
)


DEFAULT_GITHUB_REMOTE = (
    "https://github.com/JohnByungjinNa/ai_quality_final_project_2026.git"
)
GITHUB_TABS = [
    "Code",
    "Issues",
    "Pull requests",
    "Actions",
    "Security and quality",
    "Insights",
]


@st.cache_data(ttl=900, max_entries=1, show_spinner=False)
def _load_repository_home():
    """Reuse the local repository snapshot during a presentation session."""
    return collect_repository_home(refresh_remote=False)


def render_github_page(sub_menu):
    _render_github_css()
    snapshot = collect_git_environment()

    if sub_menu == "환경 설정":
        render_environment_setup(snapshot)
    elif sub_menu == "저장소 현황":
        render_repository_status()
    elif sub_menu == "프로젝트 동기화":
        render_project_sync_page()
    else:
        return False
    return True


def render_environment_setup(snapshot):
    st.markdown(
        """
        <div class="gh-repo-hero gh-light">
            <div>
                <div class="gh-eyebrow">GitHub 관리</div>
                <div class="gh-title-row">
                    <span class="gh-repo-icon">⚙️</span>
                    <span class="gh-repo-name">Git 환경 설정</span>
                </div>
                <div class="gh-repo-desc">
                    저장소를 처음 받은 사용자도 이 프로젝트 전용 Git 정보를 안전하게 등록할 수 있습니다.
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    checks = readiness_checks(snapshot)
    incomplete = [check["item"] for check in checks if not check["ready"]]

    with st.container(border=True):
        st.markdown("#### :material/terminal: Git 환경 준비 상태 · 현재 감지된 환경")
        if incomplete:
            st.markdown(
                f":orange-badge[설정 필요] 먼저 설정할 항목: "
                f"**{', '.join(incomplete)}**"
            )
        else:
            st.markdown(
                ":green-badge[준비 완료] 이 프로젝트에서 Git을 사용할 "
                "기본 환경이 준비되었습니다."
            )

        status_icons = {
            "Git 설치": "deployed_code",
            "저장소": "folder_data",
            "사용자 정보": "person",
            "원격 저장소": "cloud",
        }
        status_columns = st.columns(4, gap="small")
        for column, check in zip(status_columns, checks):
            with column:
                icon = status_icons.get(check["item"], "info")
                state_icon = "check_circle" if check["ready"] else "warning"
                state_color = "green" if check["ready"] else "orange"
                st.caption(f":material/{icon}: {check['item']}")
                st.markdown(
                    f":{state_color}[:material/{state_icon}: "
                    f"**{'완료' if check['ready'] else '설정 필요'}**]"
                )
                st.caption(check["detail"])
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "구분": _environment_icon(check["item"]),
                        "항목": check["item"],
                        "상태": "완료" if check["ready"] else "설정 필요",
                        "감지 내용": check["detail"],
                    }
                    for check in checks
                ]
            ),
            hide_index=True,
            width="stretch",
        )

    if not snapshot["git_installed"]:
        st.error(
            "Git 설치 후 대시보드를 다시 실행해야 합니다.",
            icon=":material/error:",
        )
        st.link_button(
            "Git for Windows 다운로드",
            "https://git-scm.com/download/win",
            icon=":material/download:",
        )
        return

    st.subheader("이 프로젝트 전용 Git 정보 등록")
    st.caption(
        "입력한 이름과 이메일은 이 저장소의 .git/config에만 저장됩니다. "
        "운영체제의 전역 Git 설정은 변경하지 않습니다."
    )
    with st.form("github_environment_setup_form", border=True):
        user_name = st.text_input(
            "Git 사용자 이름",
            value=snapshot["local_user_name"] or snapshot["user_name"],
            placeholder="예: 홍길동",
        )
        user_email = st.text_input(
            "Git 사용자 이메일",
            value=snapshot["local_user_email"] or snapshot["user_email"],
            placeholder="예: user@example.com",
        )
        remote_url = st.text_input(
            "GitHub 원격 저장소(origin)",
            value=snapshot["remote_url"] or DEFAULT_GITHUB_REMOTE,
            help="HTTPS 또는 SSH 형식의 GitHub 저장소 주소를 입력하세요.",
        )
        initialize = False
        if not snapshot["is_repository"]:
            initialize = st.checkbox(
                "이 폴더를 Git 저장소로 초기화하고 기본 브랜치를 main으로 설정합니다.",
            )
        submitted = st.form_submit_button(
            "환경 정보 등록",
            type="primary",
            icon=":material/save:",
        )

    if submitted:
        with st.spinner("Git 환경 정보를 등록하는 중입니다..."):
            result = configure_repository(
                user_name,
                user_email,
                remote_url,
                initialize=initialize,
            )
        if result["ok"]:
            st.success(result["message"])
            st.rerun()
        else:
            st.error(result["message"])
            if result["steps"]:
                st.dataframe(pd.DataFrame(result["steps"]), hide_index=True)

    with st.container(border=True):
        st.markdown("#### GitHub 인증 준비")
        if snapshot["token_available"]:
            st.success(
                "향후 GitHub API 기능에서 사용할 GITHUB_TOKEN 또는 GH_TOKEN "
                "환경변수가 감지되었습니다."
            )
        elif snapshot["credential_helper"]:
            st.info(
                f"Git credential helper가 설정되어 있습니다: "
                f"`{snapshot['credential_helper']}`"
            )
        else:
            st.info(
                "토큰을 이 화면에 저장하지 않습니다. HTTPS push는 첫 실행 때 "
                "Git Credential Manager로 로그인하세요."
            )
        st.caption(
            "개인 액세스 토큰, 비밀번호와 같은 인증정보는 소스코드·.env 예제·화면 기록에 입력하지 마세요."
        )

        if st.button(
            "GitHub 연결 확인",
            icon=":material/cloud_sync:",
            disabled=not snapshot["is_repository"] or not snapshot["remote_url"],
        ):
            with st.spinner("origin 연결을 확인하는 중입니다..."):
                result = verify_remote_connection()
            _render_action_result(result)


def render_repository_status():
    # 원격 fetch는 사용자가 명시적으로 요청할 때만 수행한다. 단순 화면 진입에서
    # 네트워크를 기다리지 않아도 저장소의 로컬 상태와 마지막 원격 기준은 표시할 수 있다.
    snapshot = _load_repository_home()
    if not snapshot["git_installed"]:
        st.error("Git이 설치되어 있지 않습니다. 환경 설정 메뉴에서 설치 안내를 확인하세요.")
        return
    if not snapshot["is_repository"]:
        st.warning("Git 저장소가 아닙니다. 환경 설정 메뉴에서 저장소를 초기화하세요.")
        return

    _render_repo_header(snapshot)
    _render_action_result(st.session_state.pop("github_action_result", None))

    selected_tab = st.radio(
        "GitHub 저장소 탭",
        GITHUB_TABS,
        horizontal=True,
        label_visibility="collapsed",
        key="github_repo_tab",
    )

    if selected_tab == "Code":
        _render_code_tab(snapshot)
    elif selected_tab == "Issues":
        _render_issues_tab(snapshot)
    elif selected_tab == "Pull requests":
        _render_pull_requests_tab(snapshot)
    elif selected_tab == "Actions":
        _render_actions_tab(snapshot)
    elif selected_tab == "Security and quality":
        _render_security_tab(snapshot)
    elif selected_tab == "Insights":
        _render_insights_tab(snapshot)


def render_project_sync_page():
    snapshot = _load_repository_home()
    if not snapshot["git_installed"]:
        st.error("Git이 설치되어 있지 않습니다. 환경 설정 메뉴에서 설치 안내를 확인하세요.")
        return
    if not snapshot["is_repository"]:
        st.warning("Git 저장소가 아닙니다. 환경 설정 메뉴에서 저장소를 초기화하세요.")
        return

    _render_repo_header(snapshot)
    _render_action_result(st.session_state.pop("github_action_result", None))
    st.markdown("#### 프로젝트 저장·다운로드")
    st.caption("Git 관련 실행 기능은 이 화면에서 관리합니다. 현재 프로젝트를 GitHub에 저장하거나 GitHub 기준으로 다운로드하고, 소스 ZIP도 준비할 수 있습니다.")
    _render_project_sync_panel(snapshot)
    _render_git_command_guide(snapshot)
    with st.expander("로컬 상태 원문 보기", expanded=False):
        result = run_git(["status", "--short"])
        st.code(result["stdout"] or "변경사항 없음", language="text")


def _render_repo_header(snapshot):
    owner = snapshot["owner"] or "local"
    repo_name = snapshot["repo_name"] or Path(snapshot["repository_root"]).name
    visibility = "Public" if snapshot["is_github_remote"] else "Local"
    latest = snapshot.get("latest_commit") or {}
    latest_text = (
        f"{html.escape(latest.get('short_hash', ''))} · {html.escape(latest.get('age', ''))}"
        if latest
        else "커밋 없음"
    )
    changes = len(snapshot["changed_files"])
    remote_url = snapshot["remote_url"] or "origin 미등록"
    st.markdown(
        f"""
        <div class="gh-repo-hero">
            <div class="gh-repo-main">
                <div class="gh-title-row">
                    <span class="gh-repo-icon">🐙</span>
                    <span class="gh-owner">{html.escape(owner)}</span>
                    <span class="gh-slash">/</span>
                    <span class="gh-repo-name">{html.escape(repo_name)}</span>
                    <span class="gh-badge">{visibility}</span>
                </div>
                <div class="gh-repo-desc">Integrate AI QA, Monitoring, VOC Improve</div>
                <div class="gh-commit-line">최근 커밋 {latest_text} · 변경 파일 {changes}개 · {html.escape(remote_url)}</div>
            </div>
            <div class="gh-actions">
                <span class="gh-action-pill">🔔 Notifications</span>
                <span class="gh-action-pill">⑂ Fork 0</span>
                <span class="gh-action-pill">☆ Star 0</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_code_tab(snapshot):
    left, right = st.columns([3.05, 1.0], gap="large")
    with left:
        _render_code_toolbar(snapshot)
        _render_file_browser(snapshot)
    with right:
        _render_about_sidebar(snapshot)


def _render_code_toolbar(snapshot):
    branch_count = len(snapshot["branches"])
    tag_count = len(snapshot["tags"])
    toolbar_left, toolbar_search, toolbar_code = st.columns([1.45, 1.0, 0.42], gap="small")
    with toolbar_left:
        st.markdown(
            f"""
            <div class="gh-toolbar-left">
                <span class="gh-branch">⑂ {html.escape(snapshot['branch'] or 'main')}</span>
                <span class="gh-muted">⑂ {branch_count} Branches</span>
                <span class="gh-muted">◇ {tag_count} Tags</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with toolbar_search:
        st.text_input(
            "Go to file",
            key="github_file_search",
            placeholder="Go to file",
            label_visibility="collapsed",
        )
    with toolbar_code:
        with st.popover("Code", width="stretch"):
            st.markdown("##### Clone")
            st.code(snapshot["remote_url"] or str(snapshot["repository_root"]), language="text")
            st.caption("GitHub 인증은 토큰을 화면에 저장하지 않고 Git Credential Manager 또는 SSH 설정을 사용합니다.")


def _render_file_browser(snapshot):
    keyword = st.session_state.get("github_file_search", "").strip().lower()
    entries = snapshot.get("tree_entries") or snapshot["file_entries"]
    if keyword:
        entries = [
            entry
            for entry in entries
            if keyword in entry["name"].lower() or keyword in entry["path"].lower()
        ]

    latest = snapshot.get("latest_commit") or {}
    st.markdown(
        f"""
        <div class="gh-file-list">
            <div class="gh-file-head">
                <div><span class="gh-avatar">J</span> {html.escape(latest.get('author', 'JohnByungjinNa'))}</div>
                <div class="gh-file-status-head">최종 동기화 적용여부</div>
                <div class="gh-file-time-head">최종 적용 시간</div>
                <div class="gh-file-message">{html.escape(latest.get('message', '커밋 기록 없음'))}</div>
            </div>
            {''.join(_tree_row(entry) for entry in entries)}
        </div>
        """,
        unsafe_allow_html=True,
    )


def _tree_row(entry):
    status = entry.get("sync_status", "기록 없음")
    badge_class = _sync_badge_class(status)
    return f"""
    <div class="gh-file-row">
        <div class="gh-file-name" title="{html.escape(entry.get('path', ''))}">
            <span>{html.escape(entry.get('display_name') or entry.get('name', ''))}</span>
        </div>
        <div class="gh-file-status"><span class="gh-sync-badge {badge_class}">{html.escape(status)}</span></div>
        <div class="gh-file-age">{html.escape(entry.get('sync_time') or '-')}</div>
        <div class="gh-file-message" title="{html.escape(entry.get('path', ''))}">
            {html.escape(entry.get('commit_message') or '커밋 기록 없음')}
        </div>
    </div>
    """


def _sync_badge_class(status):
    return {
        "GitHub 반영": "ok",
        "Push 필요": "warn",
        "로컬 변경": "warn",
        "삭제 미반영": "danger",
        "추가 필요": "new",
        "원격 기준 없음": "muted",
        "기록 없음": "muted",
    }.get(status, "muted")


def _render_about_sidebar(snapshot):
    st.markdown(
        """
        <div class="gh-side-card">
            <div class="gh-side-title">About</div>
            <div class="gh-about-desc">Integrate AI QA, Monitoring, VOC Improve</div>
            <div class="gh-about-item">📖 Readme</div>
            <div class="gh-about-item">↻ Activity</div>
            <div class="gh-about-item">☆ 0 stars</div>
            <div class="gh-about-item">👁 0 watching</div>
            <div class="gh-about-item">⑂ 0 forks</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown('<div class="gh-side-card">', unsafe_allow_html=True)
    st.markdown("##### Releases")
    if snapshot["tags"]:
        st.caption(f"최근 태그: {snapshot['tags'][0]}")
    else:
        st.caption("No releases published")
    st.markdown("##### Contributors")
    if snapshot["contributors"]:
        for contributor in snapshot["contributors"][:4]:
            st.caption(f"👤 {contributor['name']} · {contributor['commits']} commits")
    else:
        st.caption("표시할 contributor가 없습니다.")
    st.markdown("##### Languages")
    _render_language_bar(snapshot["language_stats"])
    st.markdown("</div>", unsafe_allow_html=True)


def _render_language_bar(language_stats):
    if not language_stats:
        st.caption("언어 통계를 계산할 파일이 없습니다.")
        return
    segments = []
    colors = ["#2f81f7", "#8957e5", "#3fb950", "#f0883e", "#db6d28", "#a371f7"]
    for index, row in enumerate(language_stats[:6]):
        segments.append(
            f"<span style='width:{row['percent']}%;background:{colors[index % len(colors)]}'></span>"
        )
    st.markdown(
        f"<div class='gh-language-bar'>{''.join(segments)}</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        " ".join(
            f"<span class='gh-language-label'>● {html.escape(row['language'])} {row['percent']}%</span>"
            for row in language_stats[:6]
        ),
        unsafe_allow_html=True,
    )


def _render_issues_tab(snapshot):
    st.markdown("#### Issues")
    st.caption("GitHub API 없이 로컬 변경사항을 이슈 후보처럼 정리합니다.")
    status_entries = snapshot["status_entries"]
    cols = st.columns(4)
    cols[0].metric("열린 변경 후보", f"{len(status_entries)}건")
    cols[1].metric("추가 전 파일", f"{sum(1 for row in status_entries if row['status'] == '??')}건")
    cols[2].metric("수정 파일", f"{sum(1 for row in status_entries if 'M' in row['status'])}건")
    cols[3].metric("삭제 파일", f"{sum(1 for row in status_entries if 'D' in row['status'])}건")
    if not status_entries:
        st.success("이슈 후보로 볼 만한 로컬 변경사항이 없습니다.")
        return
    st.dataframe(
        pd.DataFrame(status_entries).rename(
            columns={"status": "상태코드", "label": "분류", "path": "파일"}
        ),
        hide_index=True,
        width="stretch",
    )


def _render_pull_requests_tab(snapshot):
    ahead = snapshot["ahead_behind"]["ahead"]
    behind = snapshot["ahead_behind"]["behind"]
    upstream = snapshot["ahead_behind"]["label"] or "upstream 미설정"
    cols = st.columns(4)
    cols[0].metric("현재 브랜치", snapshot["branch"] or "-")
    cols[1].metric("원격 기준", upstream)
    cols[2].metric("내 로컬 ahead", f"{ahead} commit")
    cols[3].metric("원격 behind", f"{behind} commit")
    st.markdown("#### Pull request 준비 체크")
    checklist = [
        {"항목": "원격 저장소 등록", "상태": "완료" if snapshot["remote_url"] else "필요"},
        {"항목": "커밋되지 않은 변경 정리", "상태": "필요" if snapshot["changed_files"] else "완료"},
        {"항목": "upstream 추적 브랜치", "상태": "완료" if upstream != "upstream 미설정" else "필요"},
        {"항목": "push 대상 커밋", "상태": "준비됨" if ahead > 0 else "없음"},
    ]
    st.dataframe(pd.DataFrame(checklist), hide_index=True, width="stretch")


def _render_actions_tab(snapshot):
    st.markdown("#### GitHub 동기화 명령")
    st.caption("현재 프로젝트 폴더에서 바로 실행 가능한 Git 명령입니다. 실행 결과는 상단에 성공/실패와 상세 로그로 표시됩니다.")
    _render_project_sync_panel(snapshot)
    _render_git_command_guide(snapshot)

    with st.container(border=True):
        st.markdown("##### :material/sync_alt: 원격 저장소 동기화")
        st.caption(
            "Fetch는 원격 정보만 가져오고, Get/Pull은 원격 변경을 현재 브랜치에 적용합니다. "
            "Push는 로컬 커밋을 GitHub에 올립니다."
        )
        action_cols = st.columns([0.9, 1.1, 1.1, 1.1, 1.35, 1.1], gap="small")
        with action_cols[0]:
            if st.button("새로고침", width="stretch", icon=":material/refresh:"):
                _load_repository_home.clear()
                st.rerun()
        with action_cols[1]:
            if st.button("Get 정보", width="stretch", icon=":material/cloud_download:", disabled=not snapshot["remote_url"]):
                _run_and_rerun(fetch_origin, "GitHub 최신 정보를 가져오는 중입니다...")
        with action_cols[2]:
            if st.button("Get 적용", width="stretch", icon=":material/download:", disabled=not snapshot["remote_url"]):
                _run_and_rerun(pull_current_branch, "GitHub 변경사항을 현재 프로젝트에 적용하는 중입니다...")
        with action_cols[3]:
            if st.button("Push하기", width="stretch", icon=":material/upload:", disabled=not snapshot["remote_url"]):
                _run_and_rerun(push_current_branch, "로컬 커밋을 GitHub에 Push하는 중입니다...")
        with action_cols[4]:
            if st.button("GitHub 연결 확인", width="stretch", icon=":material/cloud_sync:", disabled=not snapshot["remote_url"]):
                _run_and_rerun(verify_remote_connection, "GitHub 연결을 확인하는 중입니다...")
        with action_cols[5]:
            if st.button("화면 테스트", width="stretch", icon=":material/check_circle:"):
                _run_and_rerun(_run_local_pytest, "GitHub 관리 화면 테스트를 실행하는 중입니다...")

    with st.container(border=True):
        st.markdown("##### :material/save: 변경사항 커밋")
        st.caption(
            "현재 프로젝트의 변경 파일을 스테이징한 뒤 하나의 커밋으로 묶습니다. "
            "커밋 후 Push하기를 누르면 GitHub에 반영됩니다."
        )
        commit_cols = st.columns([2.4, 0.6], gap="small", vertical_alignment="bottom")
        with commit_cols[0]:
            message = st.text_input(
                "Commit message",
                key="github_commit_message",
                placeholder="예: Improve GitHub repository dashboard",
                label_visibility="collapsed",
            )
        with commit_cols[1]:
            if st.button(
                "Commit",
                type="primary",
                width="stretch",
                disabled=not snapshot["changed_files"],
            ):
                _run_and_rerun(lambda: create_commit(message), "변경사항을 커밋하는 중입니다...")

    with st.container(border=True):
        st.markdown("##### :material/account_tree: 브랜치 생성")
        st.caption("현재 작업을 main과 분리해서 관리하고 싶을 때 새 브랜치를 생성하고 즉시 전환합니다.")
        branch_cols = st.columns([2.4, 0.6], gap="small", vertical_alignment="bottom")
        with branch_cols[0]:
            branch_name = st.text_input(
                "New branch",
                key="github_new_branch",
                placeholder="feature/voc-github-dashboard",
                label_visibility="collapsed",
            )
        with branch_cols[1]:
            if st.button("Create", width="stretch"):
                _run_and_rerun(lambda: create_branch(branch_name), "새 브랜치를 생성하는 중입니다...")

    _render_clone_section(snapshot)

    with st.expander("로컬 상태 원문 보기", expanded=False):
        result = run_git(["status", "--short"])
        st.code(result["stdout"] or "변경사항 없음", language="text")


def _render_project_sync_panel(snapshot):
    changed_count = len(snapshot.get("changed_files", []))
    ready = snapshot.get("git_installed") and snapshot.get("is_repository")
    remote_ready = ready and bool(snapshot.get("remote_url"))
    branch = snapshot.get("branch") or "main"
    sync = snapshot.get("ahead_behind") or {}
    sync_label, sync_badge = _project_sync_state(sync)
    remote_refresh = snapshot.get("remote_refresh") or {}
    remote_note = (
        "GitHub 기준 확인 완료"
        if remote_refresh.get("ok") is True
        else "GitHub 기준 확인 필요"
        if remote_refresh.get("ok") is False
        else "GitHub 기준 미확인"
    )
    default_message = "Save project snapshot from GitHub management"
    st.session_state.setdefault("github_project_commit_message", default_message)

    with st.container(border=True):
        header_col, status_col = st.columns([1.35, 1.15], gap="small", vertical_alignment="center")
        with header_col:
            st.markdown("##### :material/sync: 프로젝트 저장·다운로드")
            st.caption("현재 개발 프로젝트의 GitHub 저장, GitHub 다운로드, 소스 ZIP 다운로드를 한 곳에서 수행합니다.")
        with status_col:
            st.markdown(
                f"""
                :blue-badge[{branch}] :{sync_badge}-badge[{sync_label}]
                :orange-badge[변경 {changed_count}개]
                {' :green-badge[origin 연결]' if remote_ready else ' :red-badge[origin 확인 필요]'}
                """
            )
            st.caption(
                f"{remote_note} · GitHub에만 {sync.get('behind', 0)}개 · "
                f"로컬에만 {sync.get('ahead', 0)}개 · 기준 {sync.get('label') or '-'}"
            )

        commit_message = st.text_input(
            "저장 메시지",
            key="github_project_commit_message",
            help="Git 저장을 누르면 현재 변경사항 전체를 이 메시지로 커밋한 뒤 GitHub에 push합니다.",
        )
        save_col, download_col, zip_col, zip_download_col = st.columns(
            [0.95, 0.95, 0.8, 1.25],
            gap="small",
            vertical_alignment="bottom",
        )
        with save_col:
            if st.button(
                "Git 저장",
                icon=":material/upload:",
                type="primary",
                width="stretch",
                disabled=not remote_ready,
                help="현재 프로젝트 변경사항 전체를 commit 후 push합니다. 이력이 갈라진 경우에는 자동 저장을 중단합니다.",
            ):
                _run_and_rerun(
                    lambda: save_project_to_github(commit_message),
                    "Git 저장을 수행하는 중입니다...",
                )
        with download_col:
            if st.button(
                "Git 다운로드",
                icon=":material/download:",
                width="stretch",
                disabled=not remote_ready,
                help="GitHub의 최신 변경사항을 현재 프로젝트 폴더에 pull합니다.",
            ):
                _run_and_rerun(download_project_from_github, "Git 다운로드를 수행하는 중입니다...")
        with zip_col:
            if st.button(
                "ZIP 준비",
                icon=":material/archive:",
                width="stretch",
                disabled=not ready,
                help="현재 프로젝트 소스 ZIP 파일을 준비합니다.",
            ):
                with st.status("프로젝트 ZIP 파일을 준비하는 중입니다...", expanded=True) as status:
                    archive_result = build_project_source_archive()
                    status.update(
                        label=(
                            "프로젝트 ZIP 파일 준비가 완료되었습니다."
                            if archive_result["ok"]
                            else "프로젝트 ZIP 파일 준비에 실패했습니다."
                        ),
                        state="complete" if archive_result["ok"] else "error",
                    )
                st.session_state.github_project_archive = archive_result
                st.session_state.github_action_result = {
                    "ok": archive_result["ok"],
                    "message": archive_result["message"],
                    "detail": "",
                }
                st.rerun()
        archive = st.session_state.get("github_project_archive")
        with zip_download_col:
            if archive and archive.get("ok"):
                st.download_button(
                    "프로젝트 ZIP 다운로드",
                    data=archive["data"],
                    file_name=archive["filename"],
                    mime="application/zip",
                    icon=":material/download:",
                    width="stretch",
                    key="github_project_archive_download",
                )
            else:
                st.button(
                    "프로젝트 ZIP 다운로드",
                    icon=":material/download:",
                    width="stretch",
                    disabled=True,
                    key="github_project_archive_download_disabled",
                )

        if not remote_ready:
            st.caption("Git 저장/다운로드를 사용하려면 GitHub 관리 > 환경 설정에서 origin 원격 저장소를 먼저 등록하세요.")
        st.caption("ZIP에는 .env, secrets, .git, .venv, 캐시, 실행 로그 폴더를 포함하지 않습니다.")
        _render_sync_preflight_panel(snapshot, remote_ready=remote_ready)
        _render_safe_sync_wizard(snapshot, remote_ready=remote_ready, changed_count=changed_count)


def _render_sync_preflight_panel(snapshot, *, remote_ready):
    if not remote_ready:
        return

    sync = snapshot.get("ahead_behind") or {}
    needs_detail = bool(snapshot.get("changed_files")) and (
        int(sync.get("behind") or 0) > 0 or sync.get("state") == "diverged"
    )
    if needs_detail:
        preflight = collect_sync_preflight(refresh_remote=False)
    else:
        local_count = len(snapshot.get("changed_files") or [])
        remote_count = int(sync.get("behind") or 0)
        local_commit_count = int(sync.get("ahead") or 0)
        recommendation = (
            "로컬 변경사항이 있습니다. Git 저장 또는 stash 백업 후 다운로드를 선택할 수 있습니다."
            if local_count
            else "GitHub에 새 커밋이 있습니다. Git 다운로드를 진행할 수 있습니다."
            if remote_count
            else "GitHub와 로컬 상태가 안정적입니다."
        )
        preflight = {
            "ok": True,
            "recommendation": recommendation,
            "counts": {
                "local": local_count,
                "remote": remote_count,
                "local_commits": local_commit_count,
                "actual_conflicts": 0,
                "conflict_candidates": 0,
            },
            "index_lock": {"exists": False},
            "conflict_candidates": [],
        }
    counts = preflight.get("counts", {})
    conflict_count = counts.get("conflict_candidates", 0)
    actual_conflict_count = counts.get("actual_conflicts", 0)
    index_lock = preflight.get("index_lock") or {}
    has_lock = bool(index_lock.get("exists"))
    risk_color = "red" if actual_conflict_count or has_lock else "orange" if conflict_count else "green"
    risk_label = (
        "실제 충돌"
        if actual_conflict_count
        else "잠금 확인"
        if has_lock
        else "충돌 가능"
        if conflict_count
        else "안정"
    )

    with st.container(border=True):
        title_col, action_col = st.columns([1.5, 0.75], gap="small", vertical_alignment="center")
        with title_col:
            st.markdown("##### :material/rule_settings: 동기화 사전 점검")
            st.caption("GitHub 다운로드·저장 전에 로컬 변경, GitHub 변경, 같은 파일 변경 여부를 먼저 확인합니다.")
        with action_col:
            if st.button(
                "사전 점검 새로고침",
                icon=":material/refresh:",
                width="stretch",
                key="github_sync_preflight_refresh",
            ):
                _load_repository_home.clear()
                st.rerun()

        metric_cols = st.columns(5, gap="small")
        metric_cols[0].metric("로컬 변경", f"{counts.get('local', 0)}건", border=True)
        metric_cols[1].metric("GitHub 변경", f"{counts.get('remote', 0)}건", border=True)
        metric_cols[2].metric("로컬 커밋", f"{counts.get('local_commits', 0)}건", border=True)
        metric_cols[3].metric("충돌 가능", f"{conflict_count}건", border=True)
        metric_cols[4].metric("판정", risk_label, border=True)

        st.markdown(f":{risk_color}-badge[{risk_label}] {preflight.get('recommendation', '')}")
        if has_lock:
            st.warning(
                f"Git 잠금 파일이 감지되었습니다. 실행 중인 Git 작업이 없다면 확인이 필요합니다: {index_lock.get('path')}",
                icon=":material/lock:",
            )

        candidates = preflight.get("conflict_candidates", [])
        if candidates:
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "파일": item["path"],
                            "위험도": item["risk"],
                            "로컬": item.get("local_status") or "-",
                            "GitHub": item.get("remote_status") or "-",
                            "로컬 커밋": item.get("local_commit_status") or "-",
                            "원인": item.get("reason") or "-",
                        }
                        for item in candidates
                    ]
                ),
                hide_index=True,
                width="stretch",
                column_config={
                    "파일": st.column_config.TextColumn("파일", pinned=True, width="medium"),
                    "원인": st.column_config.TextColumn("원인", width="large"),
                },
            )
            selected_path = st.selectbox(
                "상세 확인 파일",
                [item["path"] for item in candidates],
                key="github_sync_preflight_selected_path",
            )
            selected = next((item for item in candidates if item["path"] == selected_path), candidates[0])
            local_tab, remote_tab = st.tabs(["내 PC 변경", "GitHub 변경"])
            with local_tab:
                st.code(selected.get("local_diff") or "표시할 로컬 diff가 없습니다.", language="diff")
            with remote_tab:
                st.code(selected.get("remote_diff") or "표시할 GitHub diff가 없습니다.", language="diff")
        else:
            if counts.get("local", 0) and counts.get("remote", 0):
                st.info(
                    "로컬과 GitHub 양쪽에 변경이 있지만 같은 파일은 아닙니다. 그래도 다운로드 전 백업을 권장합니다.",
                    icon=":material/info:",
                )
            elif counts.get("local", 0):
                st.info("로컬 변경사항이 있습니다. Git 저장 또는 stash 백업 후 다운로드를 선택할 수 있습니다.", icon=":material/edit:")
            elif counts.get("remote", 0):
                st.info("GitHub에 새 변경사항이 있습니다. Git 다운로드를 진행할 수 있습니다.", icon=":material/download:")
            else:
                st.success("충돌 가능 파일이 없습니다.", icon=":material/check_circle:")

        action_cols = st.columns([1.0, 1.0, 1.2], gap="small")
        with action_cols[0]:
            if st.button(
                "내 변경 백업 후 Git 다운로드",
                icon=":material/safety_check:",
                width="stretch",
                disabled=not preflight.get("ok") or actual_conflict_count > 0 or has_lock,
                key="github_stash_then_download",
                help="현재 PC 변경사항을 git stash에 보관한 뒤 GitHub 최신 변경사항을 다운로드합니다.",
            ):
                _run_and_rerun(
                    stash_and_download_project_from_github,
                    "로컬 변경사항을 백업하고 GitHub 최신 변경사항을 다운로드하는 중입니다...",
                )
        with action_cols[1]:
            if st.button(
                "GitHub 변경만 다운로드",
                icon=":material/download:",
                width="stretch",
                disabled=not preflight.get("ok") or counts.get("local", 0) > 0,
                key="github_plain_download_from_preflight",
                help="로컬 변경사항이 없을 때만 GitHub 최신 변경사항을 다운로드합니다.",
            ):
                _run_and_rerun(download_project_from_github, "GitHub 최신 변경사항을 다운로드하는 중입니다...")
        with action_cols[2]:
            st.caption("stash 백업은 `git stash list`에서 다시 확인할 수 있습니다. 자동 덮어쓰기는 하지 않습니다.")


def _project_sync_state(sync):
    state = (sync or {}).get("state")
    ahead = int((sync or {}).get("ahead") or 0)
    behind = int((sync or {}).get("behind") or 0)
    if state == "diverged":
        return f"이력 갈라짐 · GitHub {behind} / 로컬 {ahead}", "red"
    if state == "local_ahead":
        return f"Push 필요 · {ahead}개", "orange"
    if state == "remote_ahead":
        return f"다운로드 필요 · {behind}개", "orange"
    if state == "synced":
        return "동기화 완료", "green"
    if state == "no_upstream":
        return "원격 기준 없음", "red"
    return "상태 확인 필요", "gray"


def _render_safe_sync_wizard(snapshot, *, remote_ready, changed_count):
    sync = snapshot.get("ahead_behind") or {}
    state = sync.get("state")
    if not remote_ready:
        return

    with st.expander("안전 동기화 가이드", expanded=True):
        st.caption(
            "GitHub와 로컬 이력이 다를 때 백업 → GitHub 변경 통합 → 검증 → Push 순서로 진행합니다. "
            "각 단계는 버튼을 눌러 하나씩 실행됩니다."
        )
        step_cols = st.columns(4, gap="small")
        steps = [
            ("1", "백업", "현재 커밋을 백업 브랜치로 보존"),
            ("2", "통합", "GitHub 기준 커밋을 로컬에 적용"),
            ("3", "검증", "문법과 GitHub 관리 테스트 실행"),
            ("4", "Push", "검증된 로컬 커밋을 GitHub에 반영"),
        ]
        for column, (number, title, desc) in zip(step_cols, steps):
            with column:
                st.markdown(f"**{number}. {title}**")
                st.caption(desc)

        if state == "diverged":
            st.warning(
                f"현재 이력이 갈라져 있습니다. GitHub에만 {sync.get('behind', 0)}개, "
                f"로컬에만 {sync.get('ahead', 0)}개 커밋이 있습니다.",
                icon=":material/warning:",
            )
        elif state == "remote_ahead":
            st.info(
                f"GitHub에만 {sync.get('behind', 0)}개 커밋이 있습니다. 먼저 통합 단계가 필요합니다.",
                icon=":material/download:",
            )
        elif state == "local_ahead":
            st.info(
                f"로컬에만 {sync.get('ahead', 0)}개 커밋이 있습니다. 검증 후 Push할 수 있습니다.",
                icon=":material/upload:",
            )
        elif state == "synced" and changed_count == 0:
            st.success("현재 GitHub 기준과 동기화되어 있습니다.", icon=":material/check_circle:")

        if changed_count:
            st.caption("커밋되지 않은 변경사항이 있으면 먼저 Git 저장 또는 Commit을 실행해야 백업·통합을 진행할 수 있습니다.")

        action_cols = st.columns(4, gap="small")
        with action_cols[0]:
            if st.button(
                "백업 브랜치 생성",
                icon=":material/account_tree:",
                width="stretch",
                disabled=changed_count > 0,
                key="github_safe_backup_branch",
            ):
                _run_and_rerun(create_sync_backup_branch, "안전 백업 브랜치를 생성하는 중입니다...")
        with action_cols[1]:
            if st.button(
                "GitHub 변경 통합",
                icon=":material/merge_type:",
                width="stretch",
                disabled=changed_count > 0 or state in {"synced", "local_ahead"},
                key="github_safe_merge_origin",
            ):
                _run_and_rerun(merge_origin_into_current_branch, "GitHub 변경사항을 통합하는 중입니다...")
        with action_cols[2]:
            if st.button(
                "검증 실행",
                icon=":material/rule:",
                width="stretch",
                disabled=changed_count > 0,
                key="github_safe_validation",
            ):
                _run_and_rerun(run_github_sync_validation, "동기화 전 검증을 실행하는 중입니다...")
        with action_cols[3]:
            if st.button(
                "안전 Push",
                icon=":material/upload:",
                type="primary",
                width="stretch",
                disabled=changed_count > 0 or state in {"diverged", "remote_ahead", "no_upstream", "unknown"},
                key="github_safe_push",
            ):
                _run_and_rerun(push_current_branch, "검증된 커밋을 GitHub에 Push하는 중입니다...")


def _render_git_command_guide(snapshot):
    remote_ready = "사용 가능" if snapshot["remote_url"] else "origin 필요"
    changed_count = len(snapshot["changed_files"])
    ahead = snapshot["ahead_behind"]["ahead"]
    cards = [
        {
            "icon": "↓",
            "title": "Get 정보",
            "command": "git fetch origin --prune",
            "state": remote_ready,
            "desc": "GitHub의 최신 브랜치와 커밋 정보를 가져옵니다. 내 파일은 바꾸지 않아서 가장 안전한 확인용 명령입니다.",
        },
        {
            "icon": "⇣",
            "title": "Get 적용",
            "command": "git pull --ff-only",
            "state": remote_ready,
            "desc": "GitHub에 올라간 변경사항을 현재 프로젝트 폴더에 적용합니다. 로컬 변경과 충돌하면 실패하고 직접 정리가 필요합니다.",
        },
        {
            "icon": "↑",
            "title": "Push하기",
            "command": f"git push -u origin {snapshot['branch'] or 'main'}",
            "state": f"대상 커밋 {ahead}개",
            "desc": "내 PC에서 만든 커밋을 GitHub 저장소로 올립니다. 인증이 필요한 경우 Git Credential Manager 또는 SSH 설정을 사용합니다.",
        },
        {
            "icon": "✓",
            "title": "Commit",
            "command": "git add -A && git commit -m ...",
            "state": f"변경 파일 {changed_count}개",
            "desc": "현재 변경된 파일을 하나의 이력으로 묶습니다. Push 전에는 반드시 커밋이 필요합니다.",
        },
        {
            "icon": "⧉",
            "title": "Clone 수행",
            "command": "git clone origin 새폴더",
            "state": remote_ready,
            "desc": "GitHub 저장소를 다른 폴더에 새로 복제합니다. 현재 프로젝트 내부에는 중첩 저장소가 생기지 않도록 차단합니다.",
        },
    ]
    for start in range(0, len(cards), 3):
        row_cards = cards[start : start + 3]
        columns = st.columns(len(row_cards), gap="small")
        for column, card in zip(columns, row_cards):
            with column.container(border=True, height=178):
                st.markdown(f"##### {card['icon']} {card['title']}")
                st.markdown(f":blue-badge[{card['state']}]")
                st.write(card["desc"])
                st.caption(f"실행 명령 · {card['command']}")


def _render_clone_section(snapshot):
    repository_root = Path(snapshot["repository_root"])
    default_clone_path = repository_root.parent / f"{snapshot['repo_name']}_clone"
    with st.container(border=True):
        st.markdown("##### :material/content_copy: Clone 수행")
        st.caption(
            "현재 GitHub origin을 다른 폴더에 새로 복제합니다. "
            "새 PC에서 작업 환경을 만들 때 수행하는 명령을 이 화면에서 직접 실행해볼 수 있습니다."
        )
        clone_cols = st.columns([2.4, 0.6], gap="small", vertical_alignment="bottom")
        with clone_cols[0]:
            target_directory = st.text_input(
                "Clone 대상 폴더",
                key="github_clone_target_directory",
                value=str(default_clone_path),
                help="대상 폴더는 비어 있어야 하며 현재 프로젝트 폴더 내부는 허용하지 않습니다.",
            )
        with clone_cols[1]:
            if st.button(
                "Clone 수행",
                width="stretch",
                icon=":material/content_copy:",
                disabled=not snapshot["remote_url"],
            ):
                _run_and_rerun(lambda: clone_repository(snapshot["remote_url"], target_directory))
        st.code(f"git clone {snapshot['remote_url'] or '<origin-url>'} \"{target_directory}\"", language="powershell")


def _render_security_tab(snapshot):
    st.markdown("#### Security and quality")
    root = Path(snapshot["repository_root"])
    gitignore_text = ""
    gitignore_path = root / ".gitignore"
    if gitignore_path.exists():
        gitignore_text = gitignore_path.read_text(encoding="utf-8", errors="replace")
    checks = [
        {
            "항목": ".env 커밋 방지",
            "상태": "양호" if ".env" in gitignore_text else "확인 필요",
            "설명": ".gitignore에 .env 패턴이 포함되어 있는지 확인합니다.",
        },
        {
            "항목": "원격 저장소",
            "상태": "양호" if snapshot["remote_url"] else "확인 필요",
            "설명": "origin 원격 저장소가 등록되어 있어야 협업 흐름이 안정적입니다.",
        },
        {
            "항목": "로컬 변경사항",
            "상태": "확인 필요" if snapshot["changed_files"] else "양호",
            "설명": "시연 전에는 변경사항을 커밋하거나 의도적으로 남겨둔 상태인지 확인하세요.",
        },
        {
            "항목": "토큰 노출",
            "상태": "양호",
            "설명": "이 화면은 토큰 값을 읽거나 표시하지 않습니다.",
        },
    ]
    st.dataframe(pd.DataFrame(checks), hide_index=True, width="stretch")


def _render_insights_tab(snapshot):
    st.markdown("#### Insights")
    columns = st.columns(5)
    columns[0].metric("Branches", len(snapshot["branches"]))
    columns[1].metric("Tags", len(snapshot["tags"]))
    columns[2].metric("Changed", len(snapshot["changed_files"]))
    columns[3].metric("Contributors", len(snapshot["contributors"]))
    columns[4].metric("Languages", len(snapshot["language_stats"]))

    left, right = st.columns([1.2, 1.0], gap="large")
    with left:
        st.markdown("##### 최근 커밋")
        recent_rows = []
        for commit in snapshot["recent_commits"]:
            parts = commit.split("|", 3)
            if len(parts) == 4:
                recent_rows.append(
                    {
                        "커밋": parts[0],
                        "일자": parts[1],
                        "작성자": parts[2],
                        "메시지": parts[3],
                    }
                )
        if recent_rows:
            st.dataframe(pd.DataFrame(recent_rows), hide_index=True, width="stretch")
        else:
            st.info("표시할 커밋이 없습니다.")
    with right:
        st.markdown("##### 언어 구성")
        _render_language_bar(snapshot["language_stats"])
        if snapshot["language_stats"]:
            st.dataframe(
                pd.DataFrame(snapshot["language_stats"]).rename(
                    columns={"language": "언어", "bytes": "바이트", "percent": "비율"}
                ),
                hide_index=True,
                width="stretch",
            )


def _run_and_rerun(handler, label="Git 작업을 수행하는 중입니다..."):
    with st.status(label, expanded=True) as status:
        result = handler()
        status.update(
            label=result["message"],
            state="complete" if result.get("ok") else "error",
        )
        st.session_state.github_action_result = result
    _load_repository_home.clear()
    st.rerun()


def _environment_icon(item):
    return {
        "Git 설치": "터미널",
        "저장소": "폴더",
        "사용자 정보": "사용자",
        "원격 저장소": "클라우드",
    }.get(item, "정보")


def _render_action_result(result):
    if not result:
        return
    if result["ok"]:
        st.success(result["message"])
    else:
        st.error(result["message"])
    if result.get("detail"):
        with st.expander("상세 결과", expanded=False):
            st.code(result["detail"], language="text")


def _render_github_css():
    st.markdown(
        """
        <style>
        .gh-repo-hero {
            display:flex;
            justify-content:space-between;
            gap:16px;
            align-items:flex-start;
            background:#0d1117;
            border:1px solid #30363d;
            border-radius:12px;
            color:#f0f6fc;
            padding:18px 20px;
            margin-bottom:14px;
        }
        .gh-light {
            background:#ffffff;
            color:#0f172a;
            border-color:#c7d8ef;
        }
        .gh-eyebrow {
            color:#7d8590;
            font-size:12px;
            font-weight:700;
            margin-bottom:6px;
        }
        .gh-title-row {
            display:flex;
            gap:6px;
            align-items:center;
            flex-wrap:wrap;
            font-size:21px;
            font-weight:700;
        }
        .gh-repo-icon {
            font-size:20px;
        }
        .gh-owner {
            color:#2f81f7;
            font-weight:500;
        }
        .gh-slash {
            color:#8b949e;
            font-weight:400;
        }
        .gh-repo-name {
            color:#2f81f7;
            font-weight:700;
        }
        .gh-badge {
            color:#8b949e;
            border:1px solid #30363d;
            border-radius:999px;
            font-size:12px;
            padding:1px 7px;
            margin-left:4px;
        }
        .gh-repo-desc {
            color:#c9d1d9;
            margin-top:10px;
            font-size:14px;
            max-width:620px;
        }
        .gh-light .gh-repo-desc {
            color:#4b5563;
        }
        .gh-commit-line {
            color:#8b949e;
            margin-top:8px;
            font-size:12px;
        }
        .gh-actions {
            display:flex;
            gap:8px;
            flex-wrap:wrap;
            justify-content:flex-end;
        }
        .gh-action-pill {
            background:#21262d;
            border:1px solid #30363d;
            border-radius:6px;
            padding:7px 10px;
            color:#f0f6fc;
            font-size:12px;
            font-weight:700;
            white-space:nowrap;
        }
        .gh-toolbar-left {
            display:flex;
            align-items:center;
            gap:12px;
            height:38px;
            color:#57606a;
            font-size:13px;
        }
        .gh-branch {
            background:#f6f8fa;
            border:1px solid #d0d7de;
            border-radius:6px;
            padding:7px 12px;
            font-weight:700;
            color:#24292f;
        }
        .gh-muted {
            color:#57606a;
            font-weight:700;
        }
        .gh-file-list {
            border:1px solid #d0d7de;
            border-radius:8px;
            overflow:hidden;
            margin-top:12px;
            background:#ffffff;
            max-height:560px;
            overflow-y:auto;
        }
        .gh-file-head,
        .gh-file-row {
            display:grid;
            grid-template-columns: 38% 17% 17% 28%;
            align-items:center;
            gap:12px;
            min-height:41px;
            padding:0 14px;
            border-bottom:1px solid #d8dee4;
            font-size:13px;
        }
        .gh-file-head {
            background:#f6f8fa;
            font-weight:700;
            position:sticky;
            top:0;
            z-index:1;
        }
        .gh-file-row:last-child {
            border-bottom:0;
        }
        .gh-file-name {
            color:#0969da;
            font-weight:700;
            overflow:hidden;
            text-overflow:ellipsis;
            white-space:nowrap;
        }
        .gh-file-message {
            color:#57606a;
            overflow:hidden;
            text-overflow:ellipsis;
            white-space:nowrap;
        }
        .gh-file-status,
        .gh-file-status-head,
        .gh-file-time-head {
            color:#57606a;
            overflow:hidden;
            text-overflow:ellipsis;
            white-space:nowrap;
        }
        .gh-file-age {
            color:#57606a;
            white-space:nowrap;
        }
        .gh-sync-badge {
            display:inline-flex;
            align-items:center;
            justify-content:center;
            border-radius:999px;
            padding:3px 9px;
            font-size:12px;
            font-weight:800;
            border:1px solid transparent;
            white-space:nowrap;
        }
        .gh-sync-badge.ok {
            color:#116329;
            background:#dafbe1;
            border-color:#aceebb;
        }
        .gh-sync-badge.warn {
            color:#9a6700;
            background:#fff8c5;
            border-color:#f0d98c;
        }
        .gh-sync-badge.danger {
            color:#cf222e;
            background:#ffebe9;
            border-color:#ffcecb;
        }
        .gh-sync-badge.new {
            color:#0969da;
            background:#ddf4ff;
            border-color:#b6e3ff;
        }
        .gh-sync-badge.muted {
            color:#57606a;
            background:#f6f8fa;
            border-color:#d8dee4;
        }
        .gh-avatar {
            display:inline-flex;
            justify-content:center;
            align-items:center;
            width:22px;
            height:22px;
            border-radius:50%;
            background:#d1242f;
            color:#fff;
            font-size:12px;
            margin-right:6px;
        }
        .gh-side-card {
            border:1px solid #d0d7de;
            border-radius:10px;
            padding:16px;
            margin-bottom:12px;
            background:#ffffff;
        }
        .gh-side-title {
            font-weight:800;
            font-size:16px;
            margin-bottom:10px;
        }
        .gh-about-desc {
            font-weight:700;
            color:#24292f;
            margin-bottom:12px;
        }
        .gh-about-item {
            color:#57606a;
            font-size:13px;
            margin:7px 0;
        }
        .gh-language-bar {
            display:flex;
            width:100%;
            height:8px;
            overflow:hidden;
            border-radius:999px;
            background:#d8dee4;
            margin:7px 0 8px;
        }
        .gh-language-bar span {
            display:block;
            height:100%;
        }
        .gh-language-label {
            display:inline-block;
            margin-right:8px;
            color:#57606a;
            font-size:12px;
            font-weight:700;
        }
        div[data-testid="stRadio"] > label {
            display:none;
        }
        div[data-testid="stRadio"] div[role="radiogroup"] {
            gap: 4px;
            border-bottom:1px solid #d0d7de;
            margin-bottom:16px;
        }
        div[data-testid="stRadio"] div[role="radiogroup"] label {
            padding:10px 12px 9px;
            border-bottom:2px solid transparent;
            margin-bottom:-1px;
            font-weight:700;
        }
        div[data-testid="stRadio"] div[role="radiogroup"] label:has(input:checked) {
            border-bottom-color:#fd8c73;
            color:#24292f;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _run_local_pytest():
    try:
        completed = subprocess.run(
            ["python", "-m", "pytest", "tests/test_github_management.py", "-q"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "message": "테스트 실행에 실패했습니다.", "detail": str(exc)}
    return {
        "ok": completed.returncode == 0,
        "message": "GitHub 관리 테스트를 통과했습니다." if completed.returncode == 0 else "GitHub 관리 테스트가 실패했습니다.",
        "detail": completed.stdout.strip() or completed.stderr.strip(),
    }
