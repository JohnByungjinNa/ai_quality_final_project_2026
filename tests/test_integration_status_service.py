import json
from pathlib import Path

from dashboard.services.integration_status_service import (
    collect_integration_status,
    list_uploadable_evidence_runs,
    load_evidence_manifest,
)


def test_integration_snapshot_reports_configuration_without_exposing_secrets(tmp_path):
    project_dir = tmp_path / "project"
    home_dir = tmp_path / "home"
    (project_dir / "config" / "aws").mkdir(parents=True)
    (project_dir / "reports" / "voc_quality_runs" / "RUN-TEST" / "evidence").mkdir(parents=True)
    (home_dir / ".aws").mkdir(parents=True)

    secret = "sk-test-secret-value"
    (project_dir / ".env").write_text(
        f"OPENAI_API_KEY={secret}\nANTHROPIC_API_KEY=YOUR_KEY\nGOOGLE_API_KEY=gemini-secret\n",
        encoding="utf-8",
    )
    for name in ("voc-qa-bucket-policy.json", "voc-qa-lifecycle.json", "voc-qa-operator-policy.json"):
        (project_dir / "config" / "aws" / name).write_text("{}", encoding="utf-8")
    (home_dir / ".aws" / "config").write_text("[profile JohnNa-QA]\nregion=ap-northeast-2\n", encoding="utf-8")

    run_dir = project_dir / "reports" / "voc_quality_runs" / "RUN-TEST"
    (run_dir / "summary.json").write_text(
        json.dumps(
            {
                "run_id": "RUN-TEST",
                "status": "COMPLETED",
                "finished_at": "2026-08-03T12:00:00+09:00",
                "counts": {"PASS": 2, "ERROR": 1, "REVIEW_REQUIRED": 1},
                "deployment_decision": "REVISION_REQUIRED",
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "evidence" / "aws_s3_manifest.json").write_text(
        json.dumps({"run_id": "RUN-TEST", "generated_at_utc": "2026-08-03T03:00:00Z", "files": [{}, {}]}),
        encoding="utf-8",
    )

    snapshot = collect_integration_status(
        project_dir=project_dir,
        home_dir=home_dir,
        environ={"PATH": ""},
        verify_aws=False,
    )

    assert snapshot["ai"]["configured_count"] == 2
    assert snapshot["evidence"]["configuration_ready"] is True
    assert snapshot["evidence"]["upload_count"] == 1
    assert snapshot["evidence"]["latest"]["file_count"] == 2
    assert snapshot["voc"]["attention_count"] == 2
    assert snapshot["voc"]["deployment_decision"] == "REVISION_REQUIRED"
    assert snapshot["aws"]["profile_configured"] is True
    serialized = json.dumps(snapshot, ensure_ascii=False)
    assert secret not in serialized
    assert "gemini-secret" not in serialized


def test_placeholder_ai_keys_are_not_treated_as_configured(tmp_path):
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / ".env").write_text(
        "OPENAI_API_KEY=YOUR_OPENAI_API_KEY\nANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}\n",
        encoding="utf-8",
    )

    snapshot = collect_integration_status(
        project_dir=project_dir,
        home_dir=tmp_path / "home",
        environ={"PATH": ""},
        verify_aws=False,
    )

    assert snapshot["ai"]["configured_count"] == 0
    assert snapshot["voc"]["available"] is False


def test_powershell_bom_manifest_reports_uploaded_files(tmp_path):
    project_dir = tmp_path / "project"
    run_id = "RUN-20260716-110130-319110-c8fe"
    evidence_dir = project_dir / "reports" / "voc_quality_runs" / run_id / "evidence"
    evidence_dir.mkdir(parents=True)
    for name in ("step10_acceptance.json", "step10_acceptance.md"):
        (evidence_dir / name).write_text("evidence", encoding="utf-8")
    manifest = {
        "run_id": run_id,
        "generated_at_utc": "2026-08-03T03:55:39Z",
        "bucket": "test-bucket",
        "prefix": f"voc-quality-runs/{run_id}",
        "files": [
            {"name": "step10_acceptance.json", "key": "one", "size_bytes": 10, "sha256": "a"},
            {"name": "step10_acceptance.md", "key": "two", "size_bytes": 20, "sha256": "b"},
        ],
    }
    (evidence_dir / "aws_s3_manifest.json").write_text(
        json.dumps(manifest),
        encoding="utf-8-sig",
    )

    loaded = load_evidence_manifest(run_id, project_dir=project_dir)

    assert loaded["file_count"] == 2
    assert [item["name"] for item in loaded["files"]] == [
        "step10_acceptance.json",
        "step10_acceptance.md",
    ]
    assert list_uploadable_evidence_runs(project_dir=project_dir) == [run_id]
