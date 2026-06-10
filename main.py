import logging
from contextlib import asynccontextmanager
from uuid import uuid4

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from api import admin, analytics, health, live, matches, model_info, predictions, reddit, sentiment, tipping
from config.settings import settings
from db.database import AsyncSessionLocal, init_db
from services.match_service import upsert_match_from_config
from utils.config_loader import discover_match_configs

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
)

log = structlog.get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    async with AsyncSessionLocal() as session:
        configs = list(discover_match_configs())
        log.info("registering_matches", count=len(configs))
        for cfg_path in configs:
            await upsert_match_from_config(session, cfg_path)
        await session.commit()

    # Sync live scores / statuses from worldcup26.ir API
    try:
        from services.wc_sync_service import sync_wc_data
        async with AsyncSessionLocal() as session:
            stats = await sync_wc_data(session)
            log.info("wc_api_sync", **stats)
    except Exception as exc:
        log.warning("wc_api_sync_failed", error=str(exc))

    # APScheduler hook — periodic auto-crawl of imminent matches
    scheduler = None
    if settings.enable_scheduler:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from services.scheduled_jobs import crawl_upcoming_matches
        scheduler = AsyncIOScheduler(timezone="UTC")
        scheduler.add_job(
            crawl_upcoming_matches,
            "interval",
            hours=settings.scheduler_interval_hours,
            id="auto_crawl_upcoming",
            replace_existing=True,
        )
        scheduler.start()
        log.info("scheduler_started", interval_h=settings.scheduler_interval_hours)

    if settings.use_mock_crawler:
        log.warning("mock_mode_active", hint="Set USE_MOCK_CRAWLER=false for live Reddit data")

    log.info(
        "api_ready",
        matches=len(configs),
        mock_crawler=settings.use_mock_crawler,
        use_factor_ensemble=settings.use_factor_ensemble,
        goal_model=settings.goal_model,
        scheduler=settings.enable_scheduler,
        db=settings.database_url,
        docs="http://localhost:8000/docs",
    )
    yield

    if scheduler is not None:
        scheduler.shutdown(wait=False)

    # BUG-06 fix: drain background crawl tasks instead of letting them get
    # cancelled silently as the event loop closes.
    try:
        from api.predictions import shutdown_pending_crawls
        await shutdown_pending_crawls()
    except Exception as exc:
        log.warning("crawl_shutdown_error", error=str(exc))

    # BUG-09 fix: release the cached httpx connection pool.
    try:
        from crawler.wc2026_api import close_client as close_wc_client
        await close_wc_client()
    except Exception as exc:
        log.warning("wc_client_shutdown_error", error=str(exc))

    # v3: release the data-source connector pools (openfootball, weather, RSS …).
    try:
        from data_sources.base import BaseConnector
        await BaseConnector.close_all()
    except Exception as exc:
        log.warning("datasource_client_shutdown_error", error=str(exc))


app = FastAPI(title="RedditOrakel WM 2026", version="2.1", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    """Bind a stable request_id into structlog context for the lifetime of
    this request, so concurrent crawls are easy to follow in the logs."""
    rid = request.headers.get("X-Request-ID") or str(uuid4())[:12]
    tokens = structlog.contextvars.bind_contextvars(
        request_id=rid,
        path=request.url.path,
    )
    try:
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        return response
    finally:
        structlog.contextvars.unbind_contextvars("request_id", "path")


app.include_router(health.router)
app.include_router(matches.router)
app.include_router(predictions.router)
app.include_router(predictions.batch_router)
app.include_router(sentiment.router)
app.include_router(reddit.router)
app.include_router(analytics.router)
app.include_router(analytics.stats_router)
app.include_router(live.router)
app.include_router(tipping.router)
app.include_router(model_info.router)
app.include_router(admin.router)
app.include_router(admin.sources_router)
