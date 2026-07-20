import json
import subprocess

import pandas as pd
import streamlit as st

from core.paths import PROJECT_DIR


SERVICE_LINKS = [
    {"서비스": "FastAPI", "URL": "http://localhost:8000", "역할": "/ask, /health, /metrics 제공"},
    {"서비스": "Streamlit", "URL": "http://localhost:8501", "역할": "품질 대시보드 화면"},
    {"서비스": "Prometheus", "URL": "http://localhost:9090", "역할": "FastAPI /metrics 수집"},
    {"서비스": "Grafana", "URL": "http://localhost:3000", "역할": "Prometheus 지표 시각화"},
]


def render_docker_page(sub_menu):
    if "Docker" not in str(sub_menu):
        return False

    st.markdown(
        """
        <div class="section-card">
            <div class="section-title">Docker 통합 실행</div>
            <p class="section-desc">FastAPI, Streamlit, Prometheus, Grafana의 Docker Compose 상태를 읽기 전용으로 확인합니다.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    render_docker_status()
    render_service_links()
    render_compose_status()
    render_compose_logs()
    render_manual_commands()
    return True


def render_docker_status():
    st.markdown("#### Docker 상태")
    docker_result = run_command(["docker", "version", "--format", "{{.Server.Version}}"])
    compose_result = run_command(["docker", "compose", "version", "--short"])

    cols = st.columns(3)
    cols[0].metric("Docker Engine", "실행 중" if docker_result["ok"] else "연결 안 됨")
    cols[1].metric("Docker Version", docker_result["stdout"] or "-")
    cols[2].metric("Compose Version", compose_result["stdout"] or "-")

    if not docker_result["ok"]:
        st.warning(
            "현재 Streamlit이 Docker 컨테이너 안에서 실행 중이면 컨테이너 내부의 docker CLI 또는 "
            "호스트 Docker 소켓이 없어 상태 조회가 실패할 수 있습니다. 서비스 접속 주소는 그대로 사용할 수 있습니다."
        )


def render_service_links():
    st.markdown("#### 서비스 접속 주소")
    link_cols = st.columns(4)
    for index, service in enumerate(SERVICE_LINKS):
        with link_cols[index]:
            st.markdown(f"**{service['서비스']}**")
            st.caption(service["역할"])
            st.link_button("열기", service["URL"], use_container_width=True)


def render_compose_status():
    st.markdown("#### Compose 서비스 상태")
    result = run_command(["docker", "compose", "ps", "--all", "--format", "json"])
    if not result["ok"]:
        st.info(
            "Compose 서비스 상태를 조회할 수 없습니다. Docker로 실행 중인 경우 Streamlit 컨테이너 안에서 "
            "호스트 Docker 명령을 사용할 수 없어 이 정보가 비어 보일 수 있습니다."
        )
        if result["stderr"]:
            st.code(result["stderr"], language="text")
        return

    rows = parse_compose_json(result["stdout"])
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    else:
        st.code(result["stdout"] or "표시할 Compose 서비스가 없습니다.", language="text")


def render_compose_logs():
    st.markdown("#### 최근 로그")
    result = run_command(["docker", "compose", "logs", "--tail", "80", "--no-color"])
    if not result["ok"]:
        st.info("Compose 로그를 조회할 수 없습니다. Docker로 실행 중이면 호스트 터미널에서 로그를 확인하세요.")
        return
    with st.expander("최근 로그 80줄 보기", expanded=False):
        st.code(result["stdout"] or "로그가 없습니다.", language="text")


def render_manual_commands():
    with st.expander("수동 명령 참고", expanded=False):
        st.caption("이 화면에는 전체 실행/중지/재시작 버튼을 두지 않았습니다. 필요한 경우 터미널에서 직접 실행하세요.")
        st.code(
            """cd C:\\qaeduc\\ai_quality_final_project_2026
docker compose up -d --build
docker compose ps
docker compose logs --tail 100
docker compose down""",
            language="powershell",
        )


def run_command(command):
    try:
        completed = subprocess.run(
            command,
            cwd=PROJECT_DIR,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=8,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "stdout": "", "stderr": str(exc)}

    return {
        "ok": completed.returncode == 0,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def parse_compose_json(output):
    if not output:
        return []
    try:
        data = json.loads(output)
        items = data if isinstance(data, list) else [data]
    except json.JSONDecodeError:
        items = []
        for line in output.splitlines():
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError:
                return []

    rows = []
    for item in items:
        rows.append(
            {
                "서비스": item.get("Service") or item.get("Name") or "-",
                "컨테이너": item.get("Name") or "-",
                "상태": item.get("State") or item.get("Status") or "-",
                "포트": format_publishers(item.get("Publishers")),
            }
        )
    return rows


def format_publishers(publishers):
    if not publishers:
        return "-"
    if isinstance(publishers, str):
        return publishers
    ports = []
    for item in publishers:
        published = item.get("PublishedPort")
        target = item.get("TargetPort")
        if published and target:
            ports.append(f"{published}->{target}")
    return ", ".join(ports) if ports else "-"
