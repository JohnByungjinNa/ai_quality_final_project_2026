"""
config.py
- 프로젝트 경로 관리
- .env 파일 읽기
- API Key 읽기
- 결과 저장 폴더 자동 생성
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# 프로젝트 루트 경로
BASE_DIR = Path(__file__).resolve().parent

# .env 파일 로드
load_dotenv(BASE_DIR / ".env")

# API Key
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
JIRA_BASE_URL = os.getenv("JIRA_BASE_URL", "https://byungjinna.atlassian.net").strip().rstrip("/")
JIRA_EMAIL = os.getenv("JIRA_EMAIL", "").strip()
_JIRA_API_TOKEN_ENV = os.getenv("JIRA_API_TOKEN", "").strip()
JIRA_API_KEY = os.getenv("JIRA_API_KEY", "").strip()
JIRA_API_TOKEN = _JIRA_API_TOKEN_ENV or JIRA_API_KEY
JIRA_API_TOKEN_SOURCE = "JIRA_API_TOKEN" if _JIRA_API_TOKEN_ENV else ("JIRA_API_KEY" if JIRA_API_KEY else "")
JIRA_PROJECT_KEY = os.getenv("JIRA_PROJECT_KEY", "KAN").strip()
JIRA_DEFAULT_JQL = os.getenv(
    "JIRA_DEFAULT_JQL",
    f"project = {JIRA_PROJECT_KEY or 'KAN'} ORDER BY cf[10019] ASC",
).strip()
PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://localhost:9090").rstrip("/")
GRAFANA_URL = os.getenv("GRAFANA_URL", "http://localhost:3000").rstrip("/")
GRAFANA_DASHBOARD_URL = os.getenv("GRAFANA_DASHBOARD_URL", "")
K6_SUMMARY_FILE = os.getenv("K6_SUMMARY_FILE", "reports/k6_summary.json")

# 주요 경로
DATA_DIR = BASE_DIR / "data"
REPORTS_DIR = BASE_DIR / "reports"
DASHBOARD_DIR = BASE_DIR / "dashboard"
UPLOADS_DIR = DATA_DIR / "uploads"
TESTCASE_UPLOADS_DIR = DATA_DIR / "testcases" / "uploads"
TESTCASE_RUNS_DIR = REPORTS_DIR / "test_runs"

TEST_CASES_PATH = DATA_DIR / "test_cases.json"
EVAL_RESULT_JSON = REPORTS_DIR / "evaluation_result.json"
EVAL_RESULT_CSV = REPORTS_DIR / "evaluation_result.csv"
FINAL_REPORT_MD = REPORTS_DIR / "final_quality_report.md"


def ensure_dirs():
    """결과 저장 폴더 자동 생성"""
    for d in (DATA_DIR, REPORTS_DIR, DASHBOARD_DIR, UPLOADS_DIR, TESTCASE_UPLOADS_DIR, TESTCASE_RUNS_DIR):
        d.mkdir(parents=True, exist_ok=True)


if __name__ == "__main__":
    ensure_dirs()
    print(f"BASE_DIR: {BASE_DIR}")
    print(f"OPENAI_API_KEY 로드 여부: {bool(OPENAI_API_KEY)}")
