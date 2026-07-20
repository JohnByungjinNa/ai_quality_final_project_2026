import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _path_from_env(name, default):
    value = os.getenv(name, "").strip()
    path = Path(value) if value else Path(default)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def _positive_int(name, default, minimum=1):
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    return value


@dataclass(frozen=True)
class ObserverSettings:
    data_dir: Path
    log_dir: Path
    reports_dir: Path
    contract_path: Path
    environment: str = "local"
    service_name: str = "qa-observer"
    target_service: str = "ai-quality-chatbot"
    sync_interval_seconds: int = 30
    event_retention_days: int = 90
    collector_retention_days: int = 30
    quality_retention_days: int = 365
    defect_retention_days: int = 730
    aggregate_retention_days: int = 730
    grafana_webhook_token: str = ""

    @classmethod
    def from_env(cls):
        environment = os.getenv("QA_OBSERVER_ENVIRONMENT", "local").strip().lower()
        if environment not in {"local", "dev", "stage", "prod"}:
            raise ValueError("QA_OBSERVER_ENVIRONMENT must be local, dev, stage, or prod")
        return cls(
            data_dir=_path_from_env("QA_OBSERVER_DATA_DIR", PROJECT_ROOT / "data" / "qa_observer"),
            log_dir=_path_from_env("QA_OBSERVER_LOG_DIR", PROJECT_ROOT / "logs" / "qa_observer"),
            reports_dir=_path_from_env("QA_OBSERVER_REPORTS_DIR", PROJECT_ROOT / "reports" / "test_runs"),
            contract_path=_path_from_env(
                "QA_OBSERVER_CONTRACT_PATH",
                PROJECT_ROOT / "contracts" / "qa_observer" / "event-envelope-v1.schema.json",
            ),
            environment=environment,
            service_name=os.getenv("QA_OBSERVER_SERVICE_NAME", "qa-observer").strip() or "qa-observer",
            target_service=os.getenv("QA_OBSERVER_TARGET_SERVICE", "ai-quality-chatbot").strip()
            or "ai-quality-chatbot",
            sync_interval_seconds=_positive_int("QA_OBSERVER_SYNC_INTERVAL_SECONDS", 30),
            event_retention_days=_positive_int("QA_OBSERVER_EVENT_RETENTION_DAYS", 90),
            collector_retention_days=_positive_int("QA_OBSERVER_COLLECTOR_RETENTION_DAYS", 30),
            quality_retention_days=_positive_int("QA_OBSERVER_QUALITY_RETENTION_DAYS", 365),
            defect_retention_days=_positive_int("QA_OBSERVER_DEFECT_RETENTION_DAYS", 730),
            aggregate_retention_days=_positive_int("QA_OBSERVER_AGGREGATE_RETENTION_DAYS", 730),
            grafana_webhook_token=os.getenv("QA_OBSERVER_GRAFANA_WEBHOOK_TOKEN", "").strip(),
        )
