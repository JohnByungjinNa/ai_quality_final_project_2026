from core import storage


def test_remove_upload_artifacts_uses_upload_id_when_saved_path_is_stale(tmp_path, monkeypatch):
    uploads_root = tmp_path / "uploads"
    upload_dir = uploads_root / "UP-001"
    upload_dir.mkdir(parents=True)
    (upload_dir / "source.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(storage, "TESTCASE_UPLOADS_DIR", uploads_root)

    removed = storage.remove_upload_artifacts(
        {"id": "UP-001", "storage_dir": r"C:\old-project\uploads\UP-001"}
    )

    assert removed is True
    assert not upload_dir.exists()


def test_remove_all_upload_artifacts_removes_orphan_directories(tmp_path, monkeypatch):
    uploads_root = tmp_path / "uploads"
    (uploads_root / "UP-001").mkdir(parents=True)
    (uploads_root / "UP-ORPHAN").mkdir()
    monkeypatch.setattr(storage, "TESTCASE_UPLOADS_DIR", uploads_root)

    removed_count = storage.remove_all_upload_artifacts()

    assert removed_count == 2
    assert list(uploads_root.iterdir()) == []


def test_remove_test_run_artifacts_removes_run_and_formal_report(tmp_path, monkeypatch):
    reports_root = tmp_path / "reports"
    runs_root = reports_root / "test_runs"
    run_dir = runs_root / "RUN-001"
    formal_dir = reports_root / "formal_reports" / "RUN-001"
    run_dir.mkdir(parents=True)
    formal_dir.mkdir(parents=True)
    (run_dir / "run_manifest.json").write_text("{}", encoding="utf-8")
    (formal_dir / "report.pdf").write_bytes(b"pdf")
    monkeypatch.setattr(storage, "TESTCASE_RUNS_DIR", runs_root)
    monkeypatch.setattr(storage, "REPORTS_DIR", reports_root)

    removed_count = storage.remove_test_run_artifacts({"id": "RUN-001"})

    assert removed_count == 2
    assert not run_dir.exists()
    assert not formal_dir.exists()


def test_remove_test_run_artifacts_rejects_path_traversal(tmp_path, monkeypatch):
    reports_root = tmp_path / "reports"
    runs_root = reports_root / "test_runs"
    outside = tmp_path / "outside"
    outside.mkdir()
    monkeypatch.setattr(storage, "TESTCASE_RUNS_DIR", runs_root)
    monkeypatch.setattr(storage, "REPORTS_DIR", reports_root)

    assert storage.remove_test_run_artifacts({"id": "../outside"}) == 0
    assert outside.exists()
