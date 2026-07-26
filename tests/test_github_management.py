import subprocess
import zipfile
from io import BytesIO

from streamlit.testing.v1 import AppTest

from dashboard.services.github_service import (
    build_project_source_archive,
    clone_repository,
    collect_repository_home,
    collect_git_environment,
    configure_repository,
    download_project_from_github,
    is_github_remote_url,
    readiness_checks,
    save_project_to_github,
    verify_remote_connection,
)


def test_github_remote_url_validation():
    assert is_github_remote_url("https://github.com/example/project.git")
    assert is_github_remote_url("git@github.com:example/project.git")
    assert is_github_remote_url("ssh://git@github.com/example/project.git")
    assert not is_github_remote_url("https://example.com/example/project.git")
    assert not is_github_remote_url("https://github.com/example")


def test_repository_setup_writes_only_local_identity(tmp_path):
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)

    result = configure_repository(
        "테스트 사용자",
        "tester@example.com",
        "https://github.com/example/project.git",
        project_dir=tmp_path,
    )

    assert result["ok"] is True
    snapshot = collect_git_environment(tmp_path)
    assert snapshot["local_user_name"] == "테스트 사용자"
    assert snapshot["local_user_email"] == "tester@example.com"
    assert snapshot["remote_url"] == "https://github.com/example/project.git"
    assert all(check["ready"] for check in readiness_checks(snapshot))


def test_zip_folder_requires_explicit_initialization(tmp_path):
    result = configure_repository(
        "테스트 사용자",
        "tester@example.com",
        "https://github.com/example/project.git",
        project_dir=tmp_path,
    )

    assert result["ok"] is False
    assert "초기화에 동의" in result["message"]
    assert not (tmp_path / ".git").exists()


def test_zip_folder_can_be_initialized_with_main_branch(tmp_path):
    result = configure_repository(
        "테스트 사용자",
        "tester@example.com",
        "https://github.com/example/project.git",
        initialize=True,
        project_dir=tmp_path,
    )

    assert result["ok"] is True
    snapshot = collect_git_environment(tmp_path)
    assert snapshot["is_repository"] is True
    head = subprocess.run(
        ["git", "symbolic-ref", "--short", "HEAD"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )
    assert head.stdout.strip() == "main"


def test_remote_verification_requires_origin(tmp_path):
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)

    result = verify_remote_connection(tmp_path)

    assert result["ok"] is False
    assert "origin" in result["message"]


def test_repository_home_snapshot_collects_github_like_metadata(tmp_path):
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "테스트 사용자"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "tester@example.com"], cwd=tmp_path, check=True)
    (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")
    (tmp_path / "app.py").write_text("print('demo')\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial demo"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )

    snapshot = collect_repository_home(tmp_path)

    assert snapshot["repo_name"] == tmp_path.name
    assert any(entry["name"] == "README.md" for entry in snapshot["file_entries"])
    assert any(row["language"] == "Python" for row in snapshot["language_stats"])


def test_repository_home_tree_entries_show_sync_status_and_time(tmp_path):
    remote = tmp_path / "remote.git"
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
    subprocess.run(["git", "symbolic-ref", "HEAD", "refs/heads/main"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "테스트 사용자"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "tester@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "remote", "add", "origin", str(remote)], cwd=repo, check=True)
    (repo / "src").mkdir()
    (repo / "src" / "app.py").write_text("print('synced')\n", encoding="utf-8")
    assert save_project_to_github("Initial synced tree", project_dir=repo)["ok"] is True
    (repo / "src" / "local_only.py").write_text("print('local')\n", encoding="utf-8")

    snapshot = collect_repository_home(repo)
    rows_by_path = {row["path"]: row for row in snapshot["tree_entries"]}

    assert rows_by_path["src/app.py"]["sync_status"] == "GitHub 반영"
    assert rows_by_path["src/app.py"]["sync_time"] != "-"
    assert rows_by_path["src/local_only.py"]["sync_status"] == "추가 필요"


def test_clone_repository_runs_outside_current_project(tmp_path):
    source = tmp_path / "source"
    clone_target = tmp_path / "source_clone"
    source.mkdir()
    subprocess.run(["git", "init", str(source)], check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "테스트 사용자"], cwd=source, check=True)
    subprocess.run(["git", "config", "user.email", "tester@example.com"], cwd=source, check=True)
    (source / "README.md").write_text("# Demo\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=source, check=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial demo"],
        cwd=source,
        check=True,
        capture_output=True,
    )

    result = clone_repository(str(source), str(clone_target), project_dir=source)

    assert result["ok"] is True
    assert (clone_target / "README.md").exists()


def test_clone_repository_blocks_nested_target(tmp_path):
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    nested_target = tmp_path / "nested_clone"

    result = clone_repository("https://github.com/example/project.git", str(nested_target), project_dir=tmp_path)

    assert result["ok"] is False
    assert "현재 프로젝트 폴더 안" in result["message"]


def test_save_project_to_github_commits_and_pushes_to_origin(tmp_path):
    remote = tmp_path / "remote.git"
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
    subprocess.run(["git", "symbolic-ref", "HEAD", "refs/heads/main"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "테스트 사용자"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "tester@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "remote", "add", "origin", str(remote)], cwd=repo, check=True)
    (repo / "README.md").write_text("# Demo\n", encoding="utf-8")

    result = save_project_to_github("Initial save", project_dir=repo)

    assert result["ok"] is True
    log = subprocess.run(
        ["git", "--git-dir", str(remote), "log", "--oneline", "main"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "Initial save" in log.stdout


def test_download_project_from_github_pulls_remote_changes(tmp_path):
    remote = tmp_path / "remote.git"
    source = tmp_path / "source"
    work = tmp_path / "work"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
    subprocess.run(["git", "init", str(source)], check=True, capture_output=True)
    subprocess.run(["git", "symbolic-ref", "HEAD", "refs/heads/main"], cwd=source, check=True)
    subprocess.run(["git", "config", "user.name", "테스트 사용자"], cwd=source, check=True)
    subprocess.run(["git", "config", "user.email", "tester@example.com"], cwd=source, check=True)
    subprocess.run(["git", "remote", "add", "origin", str(remote)], cwd=source, check=True)
    (source / "README.md").write_text("# Demo\n", encoding="utf-8")
    assert save_project_to_github("Initial save", project_dir=source)["ok"] is True
    subprocess.run(["git", "clone", "--branch", "main", str(remote), str(work)], check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "테스트 사용자"], cwd=work, check=True)
    subprocess.run(["git", "config", "user.email", "tester@example.com"], cwd=work, check=True)
    (source / "README.md").write_text("# Demo\n\nRemote update\n", encoding="utf-8")
    assert save_project_to_github("Remote update", project_dir=source)["ok"] is True

    result = download_project_from_github(project_dir=work)

    assert result["ok"] is True
    assert "Remote update" in (work / "README.md").read_text(encoding="utf-8")


def test_project_source_archive_excludes_secrets_and_runtime_dirs(tmp_path):
    (tmp_path / "app.py").write_text("print('safe')\n", encoding="utf-8")
    (tmp_path / ".env").write_text("SECRET=1\n", encoding="utf-8")
    (tmp_path / ".env.example").write_text("SECRET=\n", encoding="utf-8")
    runtime = tmp_path / "voc_quality_runtime" / "Runs" / "RUN-1"
    runtime.mkdir(parents=True)
    (runtime / "trace.json").write_text("{}", encoding="utf-8")

    result = build_project_source_archive(project_dir=tmp_path)
    names = zipfile.ZipFile(BytesIO(result["data"])).namelist()

    assert result["ok"] is True
    assert "app.py" in names
    assert ".env.example" in names
    assert ".env" not in names
    assert "voc_quality_runtime/Runs/RUN-1/trace.json" not in names


def test_github_environment_page_renders():
    app = AppTest.from_file(
        "tests/fixtures/github_management_app.py",
        default_timeout=15,
    )

    app.run()

    assert not app.exception
    markdown_values = [element.value for element in app.markdown]
    assert any(
        "Git 환경 준비 상태 · 현재 감지된 환경" in value
        and ":material/terminal:" in value
        for value in markdown_values
    )
    assert any(
        ":green-badge[준비 완료]" in value
        or ":orange-badge[설정 필요]" in value
        for value in markdown_values
    )
    assert any(button.label == "환경 정보 등록" for button in app.button)
    assert any(button.label == "GitHub 연결 확인" for button in app.button)


def test_github_repository_status_page_renders():
    app = AppTest.from_file(
        "tests/fixtures/github_management_app.py",
        default_timeout=20,
    )
    app.session_state["github_fixture_sub_menu"] = "저장소 현황"

    app.run()

    assert not app.exception
    assert any("Code" in radio.options for radio in app.radio)
    assert any("최종 동기화 적용여부" in element.value for element in app.markdown)


def test_github_project_sync_page_renders():
    app = AppTest.from_file(
        "tests/fixtures/github_management_app.py",
        default_timeout=20,
    )
    app.session_state["github_fixture_sub_menu"] = "프로젝트 동기화"

    app.run()

    assert not app.exception
    assert any("Git 저장" == button.label for button in app.button)
    assert any("Git 다운로드" == button.label for button in app.button)
    assert any("ZIP 준비" == button.label for button in app.button)


def test_full_app_routes_to_github_repository_status_page():
    app = AppTest.from_file("dashboard/streamlit_app.py", default_timeout=30)

    app.run()
    app.button("btn_GitHub 관리").click().run()

    assert not app.exception
    assert "GitHub 관리" in app.session_state["current_menu"]
    assert app.session_state["current_sub_menu"] == "저장소 현황"
