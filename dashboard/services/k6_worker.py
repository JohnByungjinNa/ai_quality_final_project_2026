import sys
from pathlib import Path


DASHBOARD_DIR = Path(__file__).resolve().parents[1]
if str(DASHBOARD_DIR) not in sys.path:
    sys.path.insert(0, str(DASHBOARD_DIR))

from services.k6_service import run_k6_worker  # noqa: E402


def main():
    if len(sys.argv) != 2:
        return 2
    return run_k6_worker(sys.argv[1])


if __name__ == "__main__":
    raise SystemExit(main())
