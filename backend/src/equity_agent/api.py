"""FastAPI application. Run with `uvicorn equity_agent.api:create_app --factory` (see the root package.json).

Importing this module loads the data layer (about 10 s); uvicorn calls the factory before it binds the port, and the
lifespan starts the filing-parser worker and opens the Claude connection, so the first request pays for neither.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from pydantic.json_schema import models_json_schema
from starlette.exceptions import HTTPException as StarletteHTTPException

from equity_agent.config import AgentName, Effort, Settings, load_settings
from equity_agent.data.market import try_normalize_ticker
from equity_agent.models import (
    AnalystView,
    CompsTable,
    FinancialProfile,
    NewsItem,
    PipelineEvent,
    ResearchReport,
    RiskReport,
    Scorecard,
    Snapshot,
    StageError,
)
from equity_agent.pipeline import Services, cached_report, live_services
from equity_agent.streaming import SSE_HEADERS, RunRegistry, sse_stream

logger = logging.getLogger(__name__)

PARSER_WARM_TIMEOUT_S = 60
# Payload types of the stream's events, added to the OpenAPI schema for the generated frontend types.
EVENT_MODELS: tuple[type[BaseModel], ...] = (
    PipelineEvent,
    Snapshot,
    FinancialProfile,
    CompsTable,
    RiskReport,
    NewsItem,
    Scorecard,
    AnalystView,
    StageError,
    ResearchReport,
)


class AgentModel(BaseModel):
    model: str
    effort: Effort


class Credentials(BaseModel):
    anthropic: bool
    tavily: bool
    edgar_identity: bool


class Health(BaseModel):
    status: str
    offline: bool  # the offline demo: reports replay the recording in backend/demo/
    agents: dict[AgentName, AgentModel]
    credentials: Credentials


class ErrorBody(BaseModel):
    message: str


ERRORS: dict[int | str, dict[str, Any]] = {code: {"model": ErrorBody} for code in (400, 404, 422)}


def _services(request: Request) -> Services:
    return request.app.state.services


def _registry(request: Request) -> RunRegistry:
    return request.app.state.registry


def create_app(settings: Settings | None = None, services: Services | None = None) -> FastAPI:
    """Build the app. Without explicit settings they are loaded from backend/.env, and a ConfigError stops startup.

    Without `services` the lifespan builds the live ones; tests pass fakes.
    """
    settings = settings or load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if app.state.services is None:
            app.state.services = live_services(settings)
            app.state.registry = RunRegistry(app.state.services)
        live: Services = app.state.services
        try:
            await asyncio.wait_for(asyncio.wrap_future(live.data.sec.start_parser()), PARSER_WARM_TIMEOUT_S)
        except Exception as error:  # noqa: BLE001 - parsing falls back to inline or restarts the worker
            logger.warning("Filing parser warm-up failed: %s", type(error).__name__)
        try:
            await live.llm.warm()
        except Exception as error:  # noqa: BLE001 - the first agent call opens the connection instead
            logger.warning("Claude warm-up failed: %s: %s", type(error).__name__, settings.redact(str(error)))
        try:
            yield
        finally:
            await app.state.registry.close()
            live.data.close()
            await live.llm.close()

    app = FastAPI(title="Equity Research Agent", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.services = services
    app.state.registry = RunRegistry(services) if services is not None else None

    # No GZipMiddleware: it buffers streamed bodies and would hold server-sent events back.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"message": str(exc.detail)})

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError) -> JSONResponse:
        problems = "; ".join(f"{'.'.join(str(p) for p in e['loc'][1:])}: {e['msg']}" for e in exc.errors())
        return JSONResponse(status_code=422, content={"message": f"invalid request: {problems}"})

    @app.exception_handler(Exception)
    async def unhandled_error(request: Request, exc: Exception) -> JSONResponse:
        # Log the type and a redacted message only; never return stack traces or key values to clients.
        logger.error("Unhandled error on %s: %s: %s", request.url.path, type(exc).__name__, settings.redact(str(exc)))
        return JSONResponse(status_code=500, content={"message": "Internal server error"})

    @app.get("/api/health", response_model=Health)
    async def health() -> Health:
        return Health(
            status="ok",
            offline=settings.offline,
            agents={name: AgentModel(model=cfg.model, effort=cfg.effort) for name, cfg in settings.agents.items()},
            credentials=Credentials(
                anthropic=bool(settings.anthropic_api_key),
                tavily=bool(settings.tavily_api_key),
                edgar_identity=bool(settings.edgar_identity),
            ),
        )

    # Declared before /api/research/{ticker}, which would otherwise match "stream".
    @app.get(
        "/api/research/stream",
        response_class=StreamingResponse,
        responses={
            200: {
                "description": "Server-sent events: stage, partial, narrative, report, error",
                "content": {"text/event-stream": {"schema": {"$ref": "#/components/schemas/PipelineEvent"}}},
            },
            422: ERRORS[422],
        },
    )
    async def research_stream(
        ticker: str = Query(min_length=1, max_length=20),
        refresh: bool = False,
        registry: RunRegistry = Depends(_registry),
    ) -> StreamingResponse:
        """Run research for a ticker (or join the run in progress) and stream its events.

        A `partial` carries a whole section; a later one with the same key replaces it (comps arrive twice).
        The stream ends after `report` or an `error` with `terminal: true`.
        """
        events = registry.subscribe(ticker, refresh=refresh)
        return StreamingResponse(sse_stream(events), media_type="text/event-stream", headers=SSE_HEADERS)

    @app.get("/api/research/{ticker}", response_model=ResearchReport, responses={400: ERRORS[400], 404: ERRORS[404]})
    async def research_report(ticker: str, services: Services = Depends(_services)) -> ResearchReport:
        """The latest report for a ticker, while it is cached (1 hour)."""
        normalized = try_normalize_ticker(ticker)
        if normalized is None:
            raise HTTPException(status_code=400, detail="invalid ticker")
        report = cached_report(services.data.cache, normalized)
        if report is None:
            raise HTTPException(status_code=404, detail=f"no cached report for {normalized}")
        return report

    def openapi() -> dict[str, Any]:
        if app.openapi_schema is None:
            schema = get_openapi(title=app.title, version=app.version, routes=app.routes)
            _, defs = models_json_schema(
                [(m, "serialization") for m in EVENT_MODELS], ref_template="#/components/schemas/{model}"
            )
            schema.setdefault("components", {}).setdefault("schemas", {}).update(defs.get("$defs", {}))
            app.openapi_schema = schema
        return app.openapi_schema

    app.openapi = openapi  # type: ignore[method-assign]
    return app
