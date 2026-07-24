from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import Body, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from qa_observer import __version__
from qa_observer.collectors.outbox import OutboxCollector
from qa_observer.collectors.test_reports import TestReportCollector
from qa_observer.logging_utils import configure_logging
from qa_observer.grafana_webhook import events_from_grafana_webhook
from qa_observer.metrics import ObserverMetrics
from qa_observer.query import ObserverQueryService
from qa_observer.scheduler import ObserverScheduler
from qa_observer.settings import ObserverSettings
from qa_observer.storage import EventConflictError, FileEventStore
from qa_observer.validation import EventContract, EventValidationError


def create_app(settings=None):
    settings = settings or ObserverSettings.from_env()
    logger = configure_logging(settings.log_dir)
    metrics = ObserverMetrics()
    contract = EventContract(settings.contract_path)
    store = FileEventStore(settings, logger=logger)
    query_service = ObserverQueryService(store)
    test_report_collector = TestReportCollector(settings, contract, store, logger=logger)
    outbox_collector = OutboxCollector(settings, contract, store, logger=logger)
    scheduler = ObserverScheduler(
        settings,
        contract,
        store,
        [outbox_collector, test_report_collector],
        metrics,
        logger,
    )

    @asynccontextmanager
    async def lifespan(app):
        store.initialize()
        metrics.set_gauge("qa_observer_up", 1)
        metrics.set_gauge("qa_observer_stored_event_keys", store.dedup_key_count)
        logger.info("qa-observer starting version=%s data_dir=%s", __version__, settings.data_dir)
        await scheduler.start()
        try:
            yield
        finally:
            await scheduler.stop()
            metrics.set_gauge("qa_observer_up", 0)
            logger.info("qa-observer stopped")

    app = FastAPI(
        title="QA Observer",
        version=__version__,
        docs_url="/docs",
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.contract = contract
    app.state.store = store
    app.state.metrics = metrics
    app.state.query_service = query_service
    app.state.scheduler = scheduler
    app.state.test_report_collector = test_report_collector
    app.state.outbox_collector = outbox_collector

    @app.get("/health")
    async def health(request: Request):
        writable = request.app.state.store.check_writable()
        scheduler_status = request.app.state.scheduler.status()
        healthy = (
            writable
            and scheduler_status["running"]
            and scheduler_status["last_error_type"] is None
        )
        return {
            "status": "healthy" if healthy else "degraded",
            "version": __version__,
            "storage": {"writable": writable, **request.app.state.store.stats()},
            "scheduler": scheduler_status,
        }

    @app.get("/metrics", response_class=PlainTextResponse)
    async def prometheus_metrics(request: Request):
        return PlainTextResponse(
            request.app.state.metrics.render(
                request.app.state.store.list_aggregates(
                    date_value=datetime.now(timezone.utc).date().isoformat()
                )
            ),
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )

    @app.post("/v1/events")
    async def ingest_event(request: Request, event: dict = Body(...)):
        event_type = str(event.get("event_type") or "unknown")
        try:
            request.app.state.contract.validate(event)
        except EventValidationError as exc:
            request.app.state.metrics.increment(
                "qa_observer_events_received_total", {"event_type": event_type, "status": "invalid"}
            )
            request.app.state.metrics.increment(
                "qa_observer_event_validation_errors_total",
                {"reason": exc.errors[0]["code"] if exc.errors else "unknown"},
            )
            raise HTTPException(status_code=422, detail={"code": "invalid_event", "errors": exc.errors})
        try:
            result = request.app.state.store.append(event)
        except EventConflictError:
            request.app.state.metrics.increment(
                "qa_observer_event_conflicts_total", {"event_type": event_type}
            )
            raise HTTPException(
                status_code=409,
                detail={"code": "event_conflict", "message": "event key already has another payload"},
            )

        status = "duplicate" if result["duplicate"] else "stored"
        request.app.state.metrics.increment(
            "qa_observer_events_received_total", {"event_type": event_type, "status": status}
        )
        if result["duplicate"]:
            request.app.state.metrics.increment(
                "qa_observer_event_duplicates_total", {"event_type": event_type}
            )
        else:
            request.app.state.metrics.increment(
                "qa_observer_events_stored_total", {"event_type": event_type}
            )
        request.app.state.metrics.set_gauge(
            "qa_observer_stored_event_keys", request.app.state.store.dedup_key_count
        )
        return result

    @app.get("/v1/aggregates")
    async def aggregates(
        request: Request,
        date_value: str | None = Query(None, alias="date"),
        date_from: str | None = None,
        date_to: str | None = None,
        environment: str | None = None,
        service: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        metric: str | None = None,
    ):
        rows = request.app.state.store.list_aggregates(
            date_value=date_value,
            date_from=date_from,
            date_to=date_to,
            environment=environment,
            service=service,
            provider=provider,
            model=model,
            metric=metric,
        )
        return {"count": len(rows), "items": rows}

    @app.get("/v1/timeseries")
    async def timeseries(
        request: Request,
        date_from: str | None = None,
        date_to: str | None = None,
        environment: str | None = None,
        service: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        metric: str | None = None,
    ):
        try:
            items = request.app.state.query_service.timeseries(
                date_from, date_to, environment, service, provider, model, metric
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail={"code": "invalid_date_range", "message": str(exc)})
        return {"count": len(items), "items": items}

    @app.get("/v1/dashboard/summary")
    async def dashboard_summary(
        request: Request,
        date_from: str | None = None,
        date_to: str | None = None,
        environment: str | None = None,
        service: str | None = None,
        provider: str | None = None,
        model: str | None = None,
    ):
        try:
            return request.app.state.query_service.dashboard_summary(
                date_from, date_to, environment, service, provider, model
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail={"code": "invalid_date_range", "message": str(exc)})

    @app.get("/v1/events")
    async def recent_events(
        request: Request,
        date_from: str | None = None,
        date_to: str | None = None,
        event_type: str | None = None,
        environment: str | None = None,
        service: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        limit: int = Query(100, ge=1, le=500),
    ):
        try:
            items = request.app.state.query_service.events(
                date_from, date_to, event_type, environment, service, provider, model, limit
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail={"code": "invalid_date_range", "message": str(exc)})
        return {"count": len(items), "items": items}

    @app.post("/v1/alerts/grafana")
    async def grafana_alert_webhook(
        request: Request,
        payload: dict = Body(...),
        authorization: str | None = Header(None),
    ):
        expected = request.app.state.settings.grafana_webhook_token
        if expected and authorization != f"Bearer {expected}":
            request.app.state.metrics.increment(
                "qa_observer_grafana_webhook_requests_total", {"status": "unauthorized"}
            )
            raise HTTPException(status_code=401, detail={"code": "unauthorized_webhook"})

        events = events_from_grafana_webhook(payload, request.app.state.settings)
        processed = 0
        duplicates = 0
        for event in events:
            try:
                request.app.state.contract.validate(event)
                result = request.app.state.store.append(event)
                if result["duplicate"]:
                    duplicates += 1
                else:
                    processed += 1
            except (EventValidationError, EventConflictError) as exc:
                request.app.state.metrics.increment(
                    "qa_observer_grafana_webhook_requests_total", {"status": "rejected"}
                )
                raise HTTPException(
                    status_code=422,
                    detail={"code": "invalid_grafana_alert", "error_type": type(exc).__name__},
                )
        request.app.state.metrics.increment(
            "qa_observer_grafana_webhook_requests_total", {"status": "accepted"}
        )
        request.app.state.metrics.set_gauge(
            "qa_observer_stored_event_keys", request.app.state.store.dedup_key_count
        )
        return {"processed": processed, "duplicates": duplicates, "received": len(events)}

    @app.post("/v1/collectors/test-reports/run")
    async def run_test_report_collector(request: Request):
        try:
            return await request.app.state.scheduler.run_once("test_reports")
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail={"code": "collector_failed", "error_type": type(exc).__name__},
            )

    return app


app = create_app()
