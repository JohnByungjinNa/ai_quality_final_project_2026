import json
import sys
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from core.paths import PROJECT_DIR, REPORTS_DIR


if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from quality.formal_report_generator import (  # noqa: E402
    generate_docx_report,
    generate_html_report,
    generate_pdf_report,
    load_pipeline_outputs,
    normalize_pipeline_outputs,
)
from services.dashboard_snapshot import build_dashboard_snapshot, save_dashboard_snapshot  # noqa: E402


DOCX_FILENAME = "QA_최종_테스트_결과_보고서.docx"
PDF_FILENAME = "QA_최종_테스트_결과_보고서.pdf"
HTML_FILENAME = "QA_최종_테스트_결과_보고서.html"
REPORT_DESIGN_VERSION = "image-layout-v4-docx"


def render_report_tab(result_json_path=None, run_id=None, pipeline_outputs=None, quality_criteria=None):
    run_key = run_id or "latest"
    result_path = Path(result_json_path) if result_json_path else REPORTS_DIR / "evaluation_result.json"

    header_cols = st.columns([3.4, 0.2, 1.1, 1.1, 1.1])
    with header_cols[0]:
        st.markdown("### 결과 보고서")

    include_appendix, appendix_options = render_appendix_options(run_key)

    if pipeline_outputs is None and not result_path.exists():
        st.error(f"보고서 입력 JSON 파일을 찾을 수 없습니다: {result_path}")
        return

    criteria_cache_key = json.dumps(quality_criteria or {}, ensure_ascii=False, sort_keys=True, default=str)
    report_cache_key = (
        f"{REPORT_DESIGN_VERSION}:{run_key}:{include_appendix}:"
        f"{sorted(appendix_options.items())}:{criteria_cache_key}"
    )
    state_run_id = st.session_state.get("report_tab_run_id")
    should_generate = state_run_id != report_cache_key or not st.session_state.get("report_tab_html")

    if should_generate:
        with st.spinner("결과 보고서를 생성하는 중입니다..."):
            try:
                outputs = (
                    normalize_pipeline_outputs(pipeline_outputs, quality_criteria)
                    if pipeline_outputs is not None
                    else load_pipeline_outputs(result_path, quality_criteria)
                )
                output_dir = REPORTS_DIR / "formal_reports" / run_key
                output_dir.mkdir(parents=True, exist_ok=True)
                ensure_dashboard_snapshot(run_key, outputs, quality_criteria)
                html_report = generate_html_report(
                    outputs,
                    include_appendix=include_appendix,
                    appendix_options=appendix_options,
                    run_id=run_key,
                    quality_criteria=quality_criteria,
                )
                docx_path = generate_docx_report(
                    outputs,
                    output_dir / DOCX_FILENAME,
                    include_appendix=include_appendix,
                    appendix_options=appendix_options,
                    run_id=run_key,
                    quality_criteria=quality_criteria,
                )
                pdf_path = generate_pdf_report(
                    outputs,
                    output_dir / PDF_FILENAME,
                    include_appendix=include_appendix,
                    appendix_options=appendix_options,
                    run_id=run_key,
                    quality_criteria=quality_criteria,
                )

                st.session_state.report_tab_html = html_report
                st.session_state.report_tab_html_bytes = (
                    "<!doctype html><html><head><meta charset='utf-8'></head><body>"
                    + html_report
                    + "</body></html>"
                ).encode("utf-8")
                st.session_state.report_tab_docx = docx_path.read_bytes()
                st.session_state.report_tab_pdf = pdf_path.read_bytes()
                st.session_state.report_tab_run_id = report_cache_key
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                st.error(f"보고서 생성에 실패했습니다: {exc}")
                return
            except Exception as exc:
                st.error(f"보고서 생성 중 예상치 못한 오류가 발생했습니다: {exc}")
                return

    docx_bytes = st.session_state.get("report_tab_docx")
    pdf_bytes = st.session_state.get("report_tab_pdf")
    html_bytes = st.session_state.get("report_tab_html_bytes")
    html_report = st.session_state.get("report_tab_html")

    with header_cols[2]:
        st.download_button(
            "HTML 다운로드",
            data=html_bytes or b"",
            file_name=HTML_FILENAME,
            mime="text/html",
            disabled=not html_bytes,
            key=f"download_html_{run_key}",
            width="stretch",
        )
    with header_cols[3]:
        st.download_button(
            "DOCX 다운로드",
            data=docx_bytes or b"",
            file_name=DOCX_FILENAME,
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            disabled=not docx_bytes,
            key=f"download_docx_{run_key}",
            width="stretch",
        )
    with header_cols[4]:
        st.download_button(
            "PDF 다운로드",
            data=pdf_bytes or b"",
            file_name=PDF_FILENAME,
            mime="application/pdf",
            disabled=not pdf_bytes,
            key=f"download_pdf_{run_key}",
            width="stretch",
        )

    if not html_report:
        st.info("보고서가 아직 생성되지 않았습니다.")
        return

    components.html(html_report, height=1400, scrolling=True)


def ensure_dashboard_snapshot(run_key, outputs, quality_criteria=None):
    if not run_key or run_key == "latest":
        return
    run_dir = REPORTS_DIR / "test_runs" / run_key
    snapshot_path = run_dir / "dashboard_snapshot.json"
    if snapshot_path.exists():
        return
    if quality_criteria is None:
        manifest_path = run_dir / "run_manifest.json"
        if manifest_path.exists():
            try:
                quality_criteria = json.loads(manifest_path.read_text(encoding="utf-8")).get("quality_criteria")
            except (OSError, json.JSONDecodeError):
                quality_criteria = None
    snapshot = build_dashboard_snapshot(
        outputs, run_key, reports_dir=run_dir / "reports", quality_criteria=quality_criteria
    )
    save_dashboard_snapshot(run_dir, snapshot)


def render_appendix_options(run_key):
    include_appendix = st.checkbox("부록 포함", value=True, key=f"include_appendix_{run_key}")
    default_options = {
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
    if not include_appendix:
        return False, default_options

    st.caption("부록에는 테스트 당시 저장된 대시보드 전체 스냅샷만 포함됩니다.")
    return True, default_options
