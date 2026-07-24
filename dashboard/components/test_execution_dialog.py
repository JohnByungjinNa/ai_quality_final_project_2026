from datetime import datetime
from html import escape
import traceback

import pandas as pd
import streamlit as st

from components.report_visuals import summarize_pipeline_outputs
from core.paths import TESTCASE_RUNS_DIR
from core.storage import save_json_file, save_testcase_history
from quality_criteria import criteria_summary, get_quality_criteria
from services.dashboard_snapshot import build_dashboard_snapshot, save_dashboard_snapshot
from services.pipeline_runner import copy_run_input_artifacts, run_rule_pipeline_for_cases


DIALOG_RESULT_KEY = "test_execution_dialog_result"
STEP_RATIOS = {
    "챗봇 답변 생성": 0.18,
    "규칙 검증": 0.48,
    "AI 평가": 0.82,
}


def write_execution_log(log_path, message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with log_path.open("a", encoding="utf-8") as log_file:
        log_file.write(f"[{timestamp}] {message}\n")


def calculate_execution_progress(case_index, total_cases, step_name):
    total_cases = max(int(total_cases or 0), 1)
    case_index = min(max(int(case_index or 1), 1), total_cases)
    step_ratio = STEP_RATIOS.get(step_name, 0.1)
    progress = ((case_index - 1) + step_ratio) / total_cases
    return min(max(progress, 0.0), 0.98)


def build_progress_html(progress, case_id, case_index, total_cases, step_name, status="running"):
    percent = min(max(float(progress or 0) * 100, 0), 100)
    status_label = "실행 완료" if status == "complete" else "실행 실패" if status == "error" else "실행 중"
    status_class = "complete" if status == "complete" else "error" if status == "error" else "running"
    return f"""
    <div class="ted-progress-card">
      <div class="ted-progress-head">
        <div><span class="ted-live {status_class}"></span><b>{escape(status_label)}</b></div>
        <strong>{percent:.0f}%</strong>
      </div>
      <div class="ted-progress-track"><i style="width:{percent:.2f}%"></i></div>
      <div class="ted-progress-meta">
        <span><b>{escape(str(case_id))}</b> · {escape(str(step_name))}</span>
        <span>{int(case_index or 0)} / {int(total_cases or 0)} 케이스</span>
      </div>
    </div>
    """


def build_event_log_html(events):
    rows = []
    for event in list(events or [])[-10:]:
        state = event.get("state", "진행 중")
        state_class = "done" if state == "완료" else "error" if state == "실패" else "active"
        rows.append(
            f"<div class='ted-event'><span class='ted-event-dot {state_class}'></span>"
            f"<time>{escape(str(event.get('time', '')))}</time>"
            f"<b>{escape(str(event.get('case_id', '')))}</b>"
            f"<span>{escape(str(event.get('step', '')))}</span>"
            f"<em class='{state_class}'>{escape(state)}</em></div>"
        )
    if not rows:
        rows.append("<div class='ted-empty'>수행 내역을 준비하고 있습니다.</div>")
    return "<div class='ted-event-list'>" + "".join(rows) + "</div>"


def build_result_summary_html(result):
    total = int(result.get("total_count", 0))
    passed = int(result.get("passed_count", 0))
    not_passed = int(result.get("failed_count", 0))
    rule_passed = int(result.get("rule_passed_count", 0))
    api_passed = int(result.get("api_passed_count", 0))
    duration = float(result.get("duration_seconds", 0) or 0)
    return f"""
    <div class="ted-result-head"><div><span>테스트 실행 완료</span><h3>{escape(str(result.get('execution_id', '-')))}</h3></div><b>{duration:.2f}초</b></div>
    <div class="ted-result-grid">
      <div><span>전체</span><strong>{total}<small>건</small></strong></div>
      <div class="pass"><span>최종 PASS</span><strong>{passed}<small>건</small></strong></div>
      <div class="fail"><span>미통과</span><strong>{not_passed}<small>건</small></strong></div>
      <div><span>규칙 기반 PASS</span><strong>{rule_passed}<small>건</small></strong></div>
      <div><span>API 기반 PASS</span><strong>{api_passed}<small>건</small></strong></div>
    </div>
    """


def _render_dialog_styles():
    st.markdown(
        """
        <style>
        .ted-hero{display:flex;justify-content:space-between;align-items:flex-start;gap:18px;padding:4px 2px 14px;border-bottom:1px solid #d8e5f2;margin-bottom:14px}.ted-hero h2{margin:0 0 5px;color:#0d3f70;font-size:24px}.ted-hero p{margin:0;color:#60738a;font-size:12px}.ted-criteria{background:#edf5fc;color:#174d7d;border:1px solid #c7dcef;border-radius:999px;padding:6px 11px;font-size:11px;font-weight:700;white-space:nowrap}.ted-progress-card{border:1px solid #b9d2e9;border-radius:8px;padding:15px 16px;background:linear-gradient(145deg,#fff,#f7fbff);box-shadow:0 5px 16px rgba(20,76,123,.08)}.ted-progress-head,.ted-progress-meta{display:flex;justify-content:space-between;align-items:center}.ted-progress-head b{color:#173f68;font-size:13px}.ted-progress-head strong{color:#0b5592;font-size:20px}.ted-live{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:7px;background:#2385c7;box-shadow:0 0 0 5px rgba(35,133,199,.12)}.ted-live.complete{background:#2d9b58}.ted-live.error{background:#df463e}.ted-progress-track{height:26px;border-radius:13px;background:#dfebf6;overflow:hidden;margin:11px 0 8px;border:1px solid #c5d9eb}.ted-progress-track i{display:block;height:100%;border-radius:13px;background:linear-gradient(90deg,#0b477b,#1970b2 55%,#55a5dc);transition:width .2s ease}.ted-progress-meta{font-size:11px;color:#65788d}.ted-event-list{border:1px solid #d3e1ee;border-radius:7px;overflow:hidden;background:#fff;max-height:285px;overflow-y:auto}.ted-event{display:grid;grid-template-columns:13px 62px 95px 1fr 62px;gap:8px;align-items:center;padding:8px 11px;border-bottom:1px solid #edf2f7;font-size:11px}.ted-event:last-child{border:0}.ted-event-dot{width:8px;height:8px;border-radius:50%;background:#1c7bbb}.ted-event-dot.done{background:#2d9b58}.ted-event-dot.error{background:#df463e}.ted-event time{color:#8291a3}.ted-event b{color:#164b79}.ted-event em{font-style:normal;text-align:center;border-radius:999px;padding:2px 6px;color:#176493;background:#e5f2fb}.ted-event em.done{color:#237b45;background:#e5f5eb}.ted-event em.error{color:#bd3932;background:#fde9e7}.ted-empty{padding:24px;text-align:center;color:#8291a3;font-size:12px}.ted-result-head{display:flex;justify-content:space-between;align-items:center;padding:13px 16px;background:linear-gradient(90deg,#0d4f86,#176da9);color:#fff;border-radius:8px 8px 0 0}.ted-result-head span{font-size:11px;opacity:.8}.ted-result-head h3{margin:2px 0 0;font-size:17px}.ted-result-head>b{font-size:14px}.ted-result-grid{display:grid;grid-template-columns:repeat(5,1fr);border:1px solid #c7d9ea;border-top:0;border-radius:0 0 8px 8px;margin-bottom:14px}.ted-result-grid>div{padding:13px;text-align:center;border-right:1px solid #d9e5f0}.ted-result-grid>div:last-child{border:0}.ted-result-grid span{display:block;color:#60738a;font-size:10px}.ted-result-grid strong{display:block;color:#154d7d;font-size:23px;margin-top:4px}.ted-result-grid strong small{font-size:11px}.ted-result-grid .pass strong{color:#27884b}.ted-result-grid .fail strong{color:#d4433b}.ted-section-title{margin:15px 0 7px;color:#174d7d;font-size:13px;font-weight:800}@media(max-width:800px){.ted-hero{display:block}.ted-criteria{display:inline-block;margin-top:9px}.ted-result-grid{grid-template-columns:repeat(2,1fr)}.ted-event{grid-template-columns:12px 55px 75px 1fr}.ted-event em{display:none}}
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_dialog_header(selected_items, executable_cases, criteria):
    filenames = ", ".join(item.get("filename", "-") for item in selected_items)
    st.markdown(
        f"""
        <div class="ted-hero">
          <div><h2>테스트케이스 실행</h2><p>{escape(filenames)} · 총 {len(executable_cases)}개 케이스를 규칙/API 방식으로 평가합니다.</p></div>
          <span class="ted-criteria">{escape(criteria_summary(criteria))}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_cached_result(result):
    if result.get("status") == "error":
        st.error(f"테스트 실행 중 오류가 발생했습니다: {result.get('message', '알 수 없는 오류')}")
    else:
        st.markdown(build_result_summary_html(result), unsafe_allow_html=True)
        st.markdown('<div class="ted-section-title">케이스별 수행 결과</div>', unsafe_allow_html=True)
        rows = result.get("file_results", [])
        if rows:
            st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
        st.success(
            f"총 {result.get('total_count', 0)}건 실행 · 최종 PASS {result.get('passed_count', 0)}건 · "
            f"미통과 {result.get('failed_count', 0)}건"
        )

    if st.button("확인 및 닫기", type="primary", use_container_width=True):
        st.session_state.pop(DIALOG_RESULT_KEY, None)
        st.rerun()


@st.dialog("테스트케이스 실행", width="large")
def show_test_execution_dialog(selected_items, executable_cases, quality_criteria):
    criteria = get_quality_criteria(quality_criteria)
    _render_dialog_styles()
    _render_dialog_header(selected_items, executable_cases, criteria)

    cached_result = st.session_state.get(DIALOG_RESULT_KEY)
    if cached_result:
        _render_cached_result(cached_result)
        return

    progress_area = st.empty()
    st.markdown('<div class="ted-section-title">실시간 수행 내역</div>', unsafe_allow_html=True)
    event_area = st.empty()
    events = []

    started_at = datetime.now()
    execution_id = f"RUN-{started_at.strftime('%Y%m%d%H%M%S')}"
    run_dir = TESTCASE_RUNS_DIR / execution_id
    reports_dir = run_dir / "reports"
    inputs_dir = run_dir / "inputs"
    log_path = run_dir / "execution.log"
    inputs_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    progress_area.markdown(
        build_progress_html(0, "준비", 0, len(executable_cases), "입력 자료 준비"),
        unsafe_allow_html=True,
    )
    event_area.markdown(build_event_log_html(events), unsafe_allow_html=True)

    write_execution_log(log_path, f"테스트 실행 시작 - execution_id={execution_id}")
    write_execution_log(log_path, f"선택 파일 수={len(selected_items)}, 실행 테스트케이스 수={len(executable_cases)}")
    write_execution_log(log_path, f"품질 판정 기준={criteria_summary(criteria)}")
    for item in selected_items:
        write_execution_log(log_path, f"선택 파일 - {item.get('filename', '-')}, upload_id={item.get('id', '-')}")
    save_json_file(inputs_dir / "test_cases.json", executable_cases)
    save_json_file(inputs_dir / "quality_criteria.json", criteria.to_dict())
    selected_upload_manifest = copy_run_input_artifacts(selected_items, run_dir)
    write_execution_log(log_path, f"입력 아티팩트 저장 완료 - inputs_dir={inputs_dir}")

    def update_progress(case_index, total_cases, case_id, step_name):
        if events:
            events[-1]["state"] = "완료"
        events.append(
            {
                "time": datetime.now().strftime("%H:%M:%S"),
                "case_id": case_id,
                "step": step_name,
                "state": "진행 중",
            }
        )
        progress = calculate_execution_progress(case_index, total_cases, step_name)
        progress_area.markdown(
            build_progress_html(progress, case_id, case_index, total_cases, step_name),
            unsafe_allow_html=True,
        )
        event_area.markdown(build_event_log_html(events), unsafe_allow_html=True)
        write_execution_log(log_path, f"{case_id} - {step_name} ({case_index}/{total_cases})")

    try:
        run_result = run_rule_pipeline_for_cases(
            executable_cases,
            update_progress,
            report_output_dir=reports_dir,
            log_callback=lambda message: write_execution_log(log_path, message),
            quality_criteria=criteria,
            run_id=execution_id,
        )
    except Exception as exc:
        write_execution_log(log_path, f"테스트 실행 실패 - {exc}")
        write_execution_log(log_path, traceback.format_exc())
        if events:
            events[-1]["state"] = "실패"
        progress_area.markdown(
            build_progress_html(1, "오류", len(executable_cases), len(executable_cases), "실행 중단", "error"),
            unsafe_allow_html=True,
        )
        event_area.markdown(build_event_log_html(events), unsafe_allow_html=True)
        result = {"status": "error", "message": str(exc), "execution_id": execution_id}
        st.session_state[DIALOG_RESULT_KEY] = result
        _render_cached_result(result)
        return

    pipeline_outputs = run_result["pipeline_outputs"]
    summary = summarize_pipeline_outputs(pipeline_outputs, criteria)
    ended_at = datetime.now()
    duration_seconds = round((ended_at - started_at).total_seconds(), 2)
    passed_count = summary["combined_passed_count"]
    failed_count = summary["failed_count"]
    if events:
        events[-1]["state"] = "완료"
    events.append(
        {
            "time": ended_at.strftime("%H:%M:%S"),
            "case_id": "전체",
            "step": "결과 집계 및 보고서 저장",
            "state": "완료",
        }
    )
    progress_area.markdown(
        build_progress_html(1, "전체", len(executable_cases), len(executable_cases), "결과 저장 완료", "complete"),
        unsafe_allow_html=True,
    )
    event_area.markdown(build_event_log_html(events), unsafe_allow_html=True)

    write_execution_log(
        log_path,
        f"테스트 실행 완료 - duration_seconds={duration_seconds}, total={summary['total_count']}, "
        f"rule_passed={summary['rule_passed_count']}, api_passed={summary['api_passed_count']}, "
        f"combined_passed={passed_count}, failed={failed_count}",
    )
    dashboard_snapshot = build_dashboard_snapshot(
        pipeline_outputs,
        execution_id,
        started_at=started_at,
        ended_at=ended_at,
        reports_dir=reports_dir,
        quality_criteria=criteria,
    )
    dashboard_snapshot_path = save_dashboard_snapshot(run_dir, dashboard_snapshot)
    run_manifest = {
        "id": execution_id,
        "started_at": started_at.strftime("%Y-%m-%d %H:%M:%S"),
        "ended_at": ended_at.strftime("%Y-%m-%d %H:%M:%S"),
        "duration_seconds": duration_seconds,
        "selected_uploads": selected_upload_manifest,
        "test_case_count": summary["total_count"],
        "quality_criteria": criteria.to_dict(),
        "reports": run_result["reports"],
        "dashboard_snapshot": dashboard_snapshot_path,
        "log": str(log_path),
    }
    save_json_file(run_dir / "run_manifest.json", run_manifest)
    write_execution_log(log_path, f"실행 매니페스트 저장 완료 - {run_dir / 'run_manifest.json'}")

    history_item = {
        "id": execution_id,
        "executed_at": started_at.strftime("%Y-%m-%d %H:%M:%S"),
        "target_files": ", ".join(item["filename"] for item in selected_items),
        "file_count": len(selected_items),
        "total_count": summary["total_count"],
        "passed_count": passed_count,
        "failed_count": failed_count,
        "duration_seconds": duration_seconds,
        "status": "완료",
        "quality_criteria": criteria.to_dict(),
        "run_dir": str(run_dir),
        "detail": {
            "rule_passed_count": summary["rule_passed_count"],
            "api_passed_count": summary["api_passed_count"],
            "matched_count": summary["matched_count"],
            "combined_passed_count": summary["combined_passed_count"],
            "quality_criteria": criteria.to_dict(),
            "file_results": summary["file_results"],
            "pipeline_outputs": pipeline_outputs,
            "reports": run_result["reports"],
            "dashboard_snapshot": dashboard_snapshot_path,
            "log": str(log_path),
            "inputs": {
                "test_cases": str(inputs_dir / "test_cases.json"),
                "selected_uploads": str(inputs_dir / "selected_uploads.json"),
                "quality_criteria": str(inputs_dir / "quality_criteria.json"),
            },
        },
    }
    st.session_state.testcase_execution_history.insert(0, history_item)
    save_testcase_history()

    result = {
        "status": "complete",
        "execution_id": execution_id,
        "total_count": summary["total_count"],
        "passed_count": passed_count,
        "failed_count": failed_count,
        "rule_passed_count": summary["rule_passed_count"],
        "api_passed_count": summary["api_passed_count"],
        "duration_seconds": duration_seconds,
        "file_results": summary["file_results"],
    }
    st.session_state[DIALOG_RESULT_KEY] = result
    _render_cached_result(result)


def open_test_execution_dialog(selected_items, executable_cases, quality_criteria):
    st.session_state.pop(DIALOG_RESULT_KEY, None)
    show_test_execution_dialog(selected_items, executable_cases, quality_criteria)
