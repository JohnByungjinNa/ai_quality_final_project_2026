import importlib
import json
import shutil
import sys
import uuid
from pathlib import Path

from core.paths import RULE_PROJECT_DIR
from core.storage import save_json_file
from quality_criteria import criteria_summary, get_quality_criteria
from qa_observer.telemetry import content_fingerprint, emit, observation_context


_SCORE_NAMES = ("accuracy", "groundedness", "helpfulness", "safety")


def _emit_quality_result(evaluator_type, evaluation_result, answer):
    scores = evaluation_result.get("scores") or {
        name: evaluation_result.get(name, {}) for name in _SCORE_NAMES
    }
    normalized_scores = {}
    for name in _SCORE_NAMES:
        metric = scores.get(name, {})
        evaluated = bool(metric.get("evaluated", True))
        score = metric.get("score")
        normalized_scores[name] = {
            "evaluated": evaluated,
            "score": score if evaluated and score in {1, 2, 3, 4, 5} else None,
        }

    emit(
        "quality.evaluation.completed",
        {
            "evaluation_id": uuid.uuid4().hex,
            "evaluator_type": evaluator_type,
            "overall_decision": evaluation_result.get("overall_decision", "ERROR"),
            "summary_code": None,
            "safety_violation_severity": None,
            "scores": normalized_scores,
        },
        "pipeline-runner",
    )

    safety_score = normalized_scores["safety"]["score"]
    if safety_score in {1, 2}:
        emit(
            "safety.violation.detected",
            {
                "category": f"{evaluator_type}_safety_score",
                "severity": "critical" if safety_score == 1 else "high",
                "action": "review_required",
                "blocked": False,
                "content_fingerprint": content_fingerprint(answer),
                "policy_version": "quality-criteria-v1",
            },
            "pipeline-runner",
        )

def import_rule_pipeline_modules():
    if not RULE_PROJECT_DIR.exists():
        raise FileNotFoundError(f"규칙 기반 프로젝트 폴더를 찾을 수 없습니다: {RULE_PROJECT_DIR}")

    rule_project_path = str(RULE_PROJECT_DIR)
    if rule_project_path not in sys.path:
        sys.path.insert(0, rule_project_path)

    modules = {}
    for module_name in (
        "service_agent",
        "rule_validator",
        "judge_agent",
        "report_generator",
    ):
        modules[module_name] = importlib.import_module(module_name)
    return modules


def _metric(score, reason, evaluated=True):
    return {"score": score, "reason": reason, "evaluated": evaluated}


def _decision_from_scores(scores, quality_criteria=None):
    criteria = get_quality_criteria(quality_criteria)
    safety_score = scores[3] if len(scores) > 3 else 0
    if safety_score < criteria.safety_critical_min:
        return "FAIL"
    if min(scores or [0]) >= criteria.pass_min_score:
        return "PASS"
    if min(scores or [0]) >= criteria.review_min_score:
        return "REVIEW"
    return "FAIL"


def _build_rule_based_result(answer, rule_validation, quality_criteria=None):
    keyword_passed = bool(rule_validation.get("passed"))
    evaluated = rule_validation.get("evaluated", True)
    score = 5 if keyword_passed else 1
    reason = rule_validation.get("reason", "")
    not_evaluated_reason = "규칙 기반 검증에서는 이 품질 지표를 평가하지 않습니다."
    rule_metrics = rule_validation.get("metrics", {})
    if rule_metrics:
        evaluation_metrics = {
            metric_key: _metric(
                int(rule_metrics.get(metric_key, {}).get("score", 0) or 0),
                rule_metrics.get(metric_key, {}).get("reason", ""),
                evaluated=rule_metrics.get(metric_key, {}).get("evaluated", True),
            )
            for metric_key in ("accuracy", "groundedness", "helpfulness", "safety")
        }
        scores = [evaluation_metrics[key]["score"] for key in ("accuracy", "groundedness", "helpfulness", "safety")]
        overall_decision = _decision_from_scores(scores, quality_criteria)
        comment = " | ".join(
            f"{key}: {evaluation_metrics[key]['reason']}"
            for key in ("accuracy", "groundedness", "helpfulness", "safety")
        )
    else:
        evaluation_metrics = {
            "accuracy": _metric(score if evaluated else 0, reason, evaluated=evaluated),
            "groundedness": _metric(0, not_evaluated_reason, evaluated=False),
            "helpfulness": _metric(0, not_evaluated_reason, evaluated=False),
            "safety": _metric(0, not_evaluated_reason, evaluated=False),
        }
        overall_decision = "PASS" if keyword_passed else "FAIL"
        comment = reason

    normalized_validation = {
        **rule_validation,
        "keyword_passed": keyword_passed,
        "passed": overall_decision == "PASS",
        "rule_status": overall_decision,
    }
    return {
        "ai_answer": answer,
        "rule_validation": normalized_validation,
        "evaluation_result": {
            "overall_decision": overall_decision,
            **evaluation_metrics,
            "comment": comment,
        },
    }


def _build_api_based_result(answer, rule_validation, judge_result, quality_criteria=None):
    scores = [
        int(judge_result.get("accuracy", 0) or 0),
        int(judge_result.get("groundedness", 0) or 0),
        int(judge_result.get("helpfulness", 0) or 0),
        int(judge_result.get("safety", 0) or 0),
    ]
    comment = judge_result.get("comment", "")
    return {
        "ai_answer": answer,
        "rule_validation": rule_validation,
        "evaluation_result": {
            "overall_decision": _decision_from_scores(scores, quality_criteria),
            "accuracy": _metric(scores[0], comment),
            "groundedness": _metric(scores[1], comment),
            "helpfulness": _metric(scores[2], comment),
            "safety": _metric(scores[3], comment),
            "comment": comment,
        },
    }


def _flatten_for_report(pipeline_outputs):
    rows = []
    for item in pipeline_outputs:
        api_eval = item.get("api_based", {}).get("evaluation_result", {})
        rule_result = item.get("rule_based", {})
        rule_validation = rule_result.get("rule_validation") or item.get("api_based", {}).get("rule_validation", {})
        rule_decision = rule_result.get("evaluation_result", {}).get("overall_decision")
        rows.append(
            {
                "case_id": item.get("case_id", ""),
                "category": item.get("category", ""),
                "test_type": item.get("test_type", ""),
                "user_question": item.get("user_question", ""),
                "response": item.get("api_based", {}).get("ai_answer", ""),
                "rule_passed": rule_decision == "PASS" if rule_decision else rule_validation.get("passed", False),
                "rule_reason": rule_result.get("evaluation_result", {}).get("comment") or rule_validation.get("reason", ""),
                "accuracy": api_eval.get("accuracy", {}).get("score", 0),
                "groundedness": api_eval.get("groundedness", {}).get("score", 0),
                "helpfulness": api_eval.get("helpfulness", {}).get("score", 0),
                "safety": api_eval.get("safety", {}).get("score", 0),
                "comment": api_eval.get("comment", ""),
            }
        )
    return rows


def copy_run_input_artifacts(selected_items, run_dir):
    inputs_dir = run_dir / "inputs"
    uploads_dir = inputs_dir / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)

    upload_manifest = []
    for item in selected_items:
        copied_source = ""
        source_path = item.get("source_path")
        if source_path and Path(source_path).exists():
            target_dir = uploads_dir / item["id"]
            target_dir.mkdir(parents=True, exist_ok=True)
            target_path = target_dir / Path(source_path).name
            shutil.copy2(source_path, target_path)
            copied_source = str(target_path)

        upload_manifest.append(
            {
                "id": item["id"],
                "filename": item["filename"],
                "file_type": item.get("file_type", ""),
                "row_count": item.get("row_count", 0),
                "uploaded_at": item.get("uploaded_at", ""),
                "source_path": item.get("source_path", ""),
                "run_source_path": copied_source,
            }
        )

    save_json_file(inputs_dir / "selected_uploads.json", upload_manifest)
    return upload_manifest


def run_rule_pipeline_for_cases(
    test_cases,
    progress_callback=None,
    report_output_dir=None,
    log_callback=None,
    quality_criteria=None,
    run_id=None,
):
    criteria = get_quality_criteria(quality_criteria)
    modules = import_rule_pipeline_modules()
    get_response = modules["service_agent"].get_response
    validate = modules["rule_validator"].validate
    evaluate = modules["judge_agent"].evaluate
    generate_all = modules["report_generator"].generate_all

    pipeline_outputs = []
    total_cases = len(test_cases)
    if log_callback:
        log_callback(f"테스트 파이프라인 시작: 총 {total_cases}건")
        log_callback(f"품질 판정 기준: {criteria_summary(criteria)}")

    for index, case in enumerate(test_cases, start=1):
        case_id = case.get("case_id", f"TC-{index:03d}")
        category = case.get("category", "")
        user_question = case.get("user_question", "")
        expected_keyword = case.get("expected_keyword", "")
        expected_policy = case.get("expected_policy", "")
        trace_id = uuid.uuid4().hex
        if log_callback:
            log_callback(f"[{case_id}] 시작 - category={category}, question={user_question}")

        if progress_callback:
            progress_callback(index, total_cases, case_id, "챗봇 답변 생성")
        with observation_context(run_id=run_id, case_id=case_id, trace_id=trace_id):
            answer = get_response(user_question)
        if log_callback:
            log_callback(f"[{case_id}] 챗봇 답변 생성 완료 - answer_length={len(answer or '')}")

        if progress_callback:
            progress_callback(index, total_cases, case_id, "규칙 검증")
        with observation_context(run_id=run_id, case_id=case_id, trace_id=trace_id):
            rule_validation = validate(
                answer,
                expected_keyword,
                expected_policy=expected_policy,
                user_question=user_question,
                test_type=case.get("test_type", ""),
                category=category,
            )
        if log_callback:
            log_callback(
                f"[{case_id}] 규칙 검증 완료 - passed={rule_validation.get('passed')}, "
                f"reason={rule_validation.get('reason', '')}"
            )

        if progress_callback:
            progress_callback(index, total_cases, case_id, "AI 평가")
        with observation_context(run_id=run_id, case_id=case_id, trace_id=trace_id):
            judge_result = evaluate(user_question, answer, expected_policy)
            rule_based_result = _build_rule_based_result(answer, rule_validation, criteria)
            api_based_result = _build_api_based_result(answer, rule_validation, judge_result, criteria)
            _emit_quality_result("rule", rule_based_result["evaluation_result"], answer)
            _emit_quality_result("llm_judge", api_based_result["evaluation_result"], answer)
        if log_callback:
            rule_eval = rule_based_result["evaluation_result"]
            log_callback(
                f"[{case_id}] 규칙 지표 평가 완료 - decision={rule_eval['overall_decision']}, "
                f"accuracy={rule_eval['accuracy']['score']}, groundedness={rule_eval['groundedness']['score']}, "
                f"helpfulness={rule_eval['helpfulness']['score']}, safety={rule_eval['safety']['score']}"
            )
            log_callback(
                f"[{case_id}] AI 평가 완료 - "
                f"decision={api_based_result['evaluation_result']['overall_decision']}, "
                f"accuracy={api_based_result['evaluation_result']['accuracy']['score']}, "
                f"groundedness={api_based_result['evaluation_result']['groundedness']['score']}, "
                f"helpfulness={api_based_result['evaluation_result']['helpfulness']['score']}, "
                f"safety={api_based_result['evaluation_result']['safety']['score']}"
            )

        pipeline_outputs.append(
            {
                "case_id": case_id,
                "category": category,
                "test_type": case.get("test_type"),
                "user_question": user_question,
                "rule_based": rule_based_result,
                "api_based": api_based_result,
            }
        )
        if log_callback:
            log_callback(f"[{case_id}] 완료")

    output_dir = Path(report_output_dir) if report_output_dir else None
    if log_callback:
        log_callback("결과 보고서 생성 시작")
    report_paths = generate_all(_flatten_for_report(pipeline_outputs), output_dir=output_dir)
    structured_reports = report_paths.get("structured", {})
    if log_callback:
        log_callback(
            "결과 보고서 생성 완료 - "
            f"json={structured_reports.get('json', '')}, "
            f"csv={structured_reports.get('csv', '')}, "
            f"markdown={structured_reports.get('markdown', '')}"
        )

    return {
        "pipeline_outputs": pipeline_outputs,
        "quality_criteria": criteria.to_dict(),
        "reports": {
            "json": structured_reports.get("json", ""),
            "csv": structured_reports.get("csv", ""),
            "markdown": structured_reports.get("markdown", ""),
            "archive": "",
        },
    }


