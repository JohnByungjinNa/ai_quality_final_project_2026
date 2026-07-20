from concurrent.futures import ThreadPoolExecutor

import streamlit as st

from components.performance_design import (
    render_icon_cards,
    render_page_hero,
    render_performance_design_styles,
    render_section_header,
    service_icon_label,
    service_icon_name,
)
from services.service_control import (
    MODE_LABELS,
    RUNTIME_MODES,
    collect_runtime_status,
    collect_service_snapshot,
    run_service_action,
    save_service_config,
)


SERVICES = [
    ("docker", "Docker Engine"),
    ("grafana", "Grafana"),
    ("prometheus", "Prometheus"),
    ("fastapi", "FastAPI"),
]


@st.cache_data(ttl=5, max_entries=1, show_spinner=False)
def collect_management_snapshot():
    with ThreadPoolExecutor(max_workers=2) as executor:
        service_future = executor.submit(collect_service_snapshot)
        runtime_future = executor.submit(collect_runtime_status)
        return {
            "services": service_future.result(),
            "runtime": runtime_future.result(),
        }


def render_service_management_page():
    render_performance_design_styles()
    render_page_hero(
        "services",
        "서비스 관리",
        "Docker Engine, Grafana, Prometheus, FastAPI의 실행 기반과 생명주기를 구분하여 서비스별로 시작·중지합니다.",
    )

    action_result = st.session_state.pop("service_action_result", None)
    if action_result:
        if action_result.get("ok"):
            st.success(action_result.get("message", "서비스 작업을 완료했습니다."))
        else:
            st.error(action_result.get("message", "서비스 작업에 실패했습니다."))

    refresh_col, note_col = st.columns([0.55, 2.45], vertical_alignment="center")
    if refresh_col.button(":material/refresh: 상태 갱신", width="stretch"):
        collect_management_snapshot.clear()
        st.rerun()
    note_col.caption("서비스 상태는 endpoint 기준으로 병렬 확인하며 결과는 5초 동안 재사용합니다.")

    snapshot = collect_management_snapshot()
    render_runtime_summary(snapshot["runtime"])
    render_runtime_configuration(snapshot["runtime"])
    render_service_status(snapshot["services"], snapshot["runtime"])
    pending = st.session_state.get("service_pending_action")
    if pending:
        render_service_action_dialog(pending)


def render_runtime_summary(runtime):
    docker = runtime["docker"]
    config = runtime["config"]
    with st.container(border=True):
        render_section_header("docker", "실행 기반 요약", "서비스별 현재 실행 방식과 Docker Engine 상태")
        render_icon_cards(
            [
                ("docker", "Docker Engine", docker["label"], "컨테이너 실행 기반", "good" if docker["ok"] else "warn"),
                ("grafana", "Grafana 방식", MODE_LABELS[config["grafana"]], "시각화 서비스", ""),
                ("prometheus", "Prometheus 방식", MODE_LABELS[config["prometheus"]], "메트릭 수집 서비스", ""),
                ("fastapi", "FastAPI 방식", MODE_LABELS[config["fastapi"]], "애플리케이션 API", ""),
            ],
            columns=4,
        )
        st.caption(" / ".join(f"{name}: {url}" for name, url in runtime["urls"].items()))
        docker_services = [
            name
            for service_id, name in (("grafana", "Grafana"), ("prometheus", "Prometheus"), ("fastapi", "FastAPI"))
            if config[service_id] == "docker"
        ]
        if docker_services:
            st.info(
                f"{', '.join(docker_services)}는 현재 Docker Compose 방식입니다. "
                "서비스 컨테이너는 각각 제어되지만 실행 기반인 Docker Engine은 반드시 필요합니다. "
                "Docker Engine 없이 실행하려면 해당 서비스를 로컬 실행 방식으로 변경하고 로컬 실행 파일을 준비해야 합니다."
            )
        if not docker["ok"] and docker.get("message"):
            details = st.expander("Docker 연결 상세", on_change="rerun")
            if details.open:
                with details:
                    st.code(docker["message"], language="text")


def render_runtime_configuration(runtime):
    config = runtime["config"]
    capabilities = runtime["capabilities"]
    settings = st.expander("서비스별 실행 방식 설정", on_change="rerun")
    if not settings.open:
        return

    with settings:
        st.info(
            "실행 방식 변경은 다음 시작·중지부터 적용됩니다. 이미 실행 중인 서비스는 자동으로 중지하거나 전환하지 않습니다."
        )
        with st.form("service_runtime_mode_form"):
            cols = st.columns(3)
            selected = {}
            for column, service_id, service_name in zip(
                cols,
                ("grafana", "prometheus", "fastapi"),
                ("Grafana", "Prometheus", "FastAPI"),
            ):
                with column:
                    selected[service_id] = st.selectbox(
                        f"{service_name} 실행 방식",
                        options=RUNTIME_MODES,
                        index=RUNTIME_MODES.index(config[service_id]),
                        format_func=lambda mode: MODE_LABELS[mode],
                        key=f"service_runtime_mode_{service_id}",
                    )
                    capability = capabilities[service_id]
                    if selected[service_id] == "local" and not capability["local_available"]:
                        st.warning(f"로컬 실행 파일이 없습니다. `{service_id.upper()}_EXECUTABLE` 설정이 필요합니다.")
                    elif selected[service_id] == "external":
                        st.caption("상태 조회만 제공하고 시작·중지는 비활성화됩니다.")
                    elif selected[service_id] == "docker":
                        st.caption(
                            "Docker Engine이 필수입니다. Engine을 자동 시작하지 않으며, "
                            "다른 컨테이너와 무관하게 해당 컨테이너만 제어합니다."
                        )
                    else:
                        st.caption(capability["local_executable"] or "로컬 실행 가능")
            saved = st.form_submit_button(":material/save: 실행 방식 저장", type="primary")

        if saved:
            save_service_config(selected)
            collect_management_snapshot.clear()
            st.session_state.service_action_message = "완료: 서비스별 실행 방식을 저장했습니다."
            st.rerun()


def render_service_status(snapshot, runtime):
    render_section_header(
        "services",
        "서비스별 상태 및 제어",
        "서비스별 상태를 확인하고 시작·중지하며 Docker 방식은 Engine 실행 기반을 공유합니다.",
    )
    render_status_styles()

    header_cols = st.columns([1.05, 1.15, 2.1, 0.8, 0.7, 0.7])
    header_cols[0].markdown("**서비스**")
    header_cols[1].markdown("**실행 방식**")
    header_cols[2].markdown("**상태·제어 기준**")
    header_cols[3].markdown("**상태**")
    header_cols[4].markdown("**시작**")
    header_cols[5].markdown("**중지**")

    docker = runtime["docker"]
    docker_service = {
        "running": docker["ok"],
        "checks": [{"name": "Docker Engine", "ok": docker["ok"]}],
        "mode": "desktop",
        "mode_label": MODE_LABELS["desktop"],
        "control_message": "다른 서비스를 자동으로 시작·중지하지 않고 Docker Engine만 제어합니다.",
    }
    render_service_row("docker", "Docker Engine", docker_service, docker)
    for service_id, service_name in SERVICES[1:]:
        render_service_row(service_id, service_name, snapshot[service_id], docker)


def render_service_row(service_id, service_name, service, docker):
    state = get_service_state(service)
    checks_text = " · ".join(
        f"{check['name']}:{'정상' if check['ok'] else '중지'}" for check in service.get("checks", [])
    )
    mode = service["mode"]
    start_disabled, stop_disabled = get_action_disabled(service_id, service, docker)

    with st.container(border=True):
        row_cols = st.columns([1.05, 1.15, 2.1, 0.8, 0.7, 0.7])
        row_cols[0].markdown(
            service_icon_label(service_name, service_icon_name(service_name)),
            unsafe_allow_html=True,
        )
        row_cols[1].markdown(service["mode_label"])
        row_cols[2].caption(f"{checks_text}\n\n{service.get('control_message', '')}")
        row_cols[3].markdown(
            f'<span class="service-state state-{state["level"]}">{state["label"]}</span>',
            unsafe_allow_html=True,
        )
        if row_cols[4].button(
            "시작",
            key=f"service_independent_start_{service_id}",
            disabled=start_disabled,
            width="stretch",
            type="primary",
        ):
            set_pending_action(service_id, service_name, "시작", mode, docker.get("ok", False))
            st.rerun()
        if row_cols[5].button(
            "중지",
            key=f"service_independent_stop_{service_id}",
            disabled=stop_disabled,
            width="stretch",
        ):
            set_pending_action(service_id, service_name, "중지", mode, docker.get("ok", False))
            st.rerun()


def get_action_disabled(service_id, service, docker):
    running = service.get("running", False)
    mode = service.get("mode")
    if service_id == "docker":
        return running, not running
    if mode == "external":
        return True, True
    if mode == "docker":
        container_running = service.get("container_running", False)
        return running or container_running, not container_running
    locally_managed = service.get("locally_managed", False)
    return running or locally_managed, not locally_managed


@st.dialog(
    "서비스 제어 확인",
    width="large",
    icon=":material/power_settings_new:",
    on_dismiss=lambda: clear_pending_action(),
)
def render_service_action_dialog(pending):
    confirm_text = f"{pending['service_name']} {pending['action']}"
    guard_key = f"service_guard_{pending['service_id']}_{pending['action']}"
    if pending["service_id"] == "docker" and pending["action"] == "중지":
        st.error("Docker Engine을 중지하면 현재 실행 중인 모든 Docker 컨테이너가 함께 중지됩니다.")
    docker_ready = True
    if (
        pending["service_id"] != "docker"
        and pending["mode"] == "docker"
        and pending["action"] == "시작"
    ):
        docker_ready = pending.get("docker_running", False)
        if docker_ready:
            st.info("Docker Engine은 이미 실행 중입니다. 선택한 서비스 컨테이너만 시작하며 다른 컨테이너는 시작하지 않습니다.")
        else:
            st.error(
                "실행할 수 없습니다. 선택한 서비스는 Docker Compose 방식이므로 Docker Engine이 필요합니다. "
                "이 작업은 Docker Engine을 자동으로 시작하지 않습니다. 팝업을 닫고 Docker Engine을 별도로 시작하거나, "
                "로컬 실행 파일을 준비한 뒤 실행 방식을 로컬 실행으로 변경하세요."
            )
    if (
        pending["service_id"] == "prometheus"
        and pending["mode"] == "docker"
        and pending["action"] == "시작"
        and docker_ready
    ):
        st.info(
            "서비스 관리에서 시작하는 동안에만 Windows 로컬 FastAPI·qa-observer 수집용 임시 설정을 적용합니다. "
            "원본 docker/prometheus.yml은 변경하지 않으며 Prometheus 또는 시스템 종료 시 임시 설정을 제거합니다."
        )
    st.warning(
        f"{confirm_text} 작업을 실행하려면 확인 절차를 완료하세요. 선택 방식: {MODE_LABELS[pending['mode']]}"
    )
    st.markdown(
        "1. **오조작 방지 확인**을 선택합니다.\n"
        "2. 실행 버튼을 누르면 실제 서비스 상태가 확인될 때까지 기다립니다."
    )
    guard_checked = st.checkbox("오조작 방지 확인", key=guard_key)
    can_execute = docker_ready and guard_checked
    action_col, cancel_col = st.columns(2)
    if action_col.button("실행", disabled=not can_execute, width="stretch", type="primary"):
        action_id = "start" if pending["action"] == "시작" else "stop"
        with st.spinner(f"{confirm_text} 후 실제 상태를 확인하고 있습니다..."):
            result = run_service_action(pending["service_id"], action_id, pending["mode"])
        st.session_state.service_action_result = result
        collect_management_snapshot.clear()
        clear_pending_action()
        st.rerun(scope="app")
    if cancel_col.button("취소", width="stretch"):
        clear_pending_action()
        st.rerun(scope="app")


def set_pending_action(service_id, service_name, action, mode, docker_running=False):
    st.session_state.service_pending_action = {
        "service_id": service_id,
        "service_name": service_name,
        "action": action,
        "mode": mode,
        "docker_running": docker_running,
    }


def clear_pending_action():
    st.session_state.pop("service_pending_action", None)


def get_service_state(service):
    checks = service.get("checks", [])
    ok_count = sum(1 for check in checks if check.get("ok"))
    if ok_count == len(checks) and checks:
        return {"label": "실행중", "level": "ok"}
    if ok_count == 0:
        return {"label": "중지", "level": "stopped"}
    return {"label": "비정상", "level": "bad"}


def render_status_styles():
    st.markdown(
        """
        <style>
        .service-state {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 100%;
            min-height: 30px;
            border-radius: 8px;
            font-size: 13px;
            font-weight: 800;
        }
        .state-ok { background: #dcfce7; color: #166534; border: 1px solid #bbf7d0; }
        .state-stopped { background: #f1f5f9; color: #475569; border: 1px solid #e2e8f0; }
        .state-bad { background: #fee2e2; color: #991b1b; border: 1px solid #fecaca; }
        </style>
        """,
        unsafe_allow_html=True,
    )
