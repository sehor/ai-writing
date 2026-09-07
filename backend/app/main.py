from contextlib import asynccontextmanager
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.data import get_data_store
from app.http_errors import install_application_error_handlers
from app.observability import bind_request_id, log_event, new_request_id
from app.outbox.dispatcher import build_app_outbox_dispatcher
from app.routers import (
    analysis,
    backup,
    canon,
    graph,
    health,
    manuscript,
    memory,
    models,
    narrative,
    outbox,
    projects,
    references,
    scenes,
    snowflake,
    wiki,
    writeback,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Tests and local integrations must initialize the same store that their
    # routes/dispatcher use, never the developer's default database.
    data_store = app.dependency_overrides.get(get_data_store, get_data_store)()
    data_store.init()
    # Recovery must precede all readers and background file writers. A damaged
    # journal aborts startup instead of serving mixed database/file state.
    backup_factory = app.dependency_overrides.get(backup.get_backup_service)
    backup_service = backup_factory() if backup_factory else backup.get_backup_service(data_store)
    backup_service.recover_interrupted_imports()
    # P1-03: post-commit jobs are dispatched by this app-owned background
    # loop instead of inside mutation requests.
    dispatcher = build_app_outbox_dispatcher(app)
    app.state.outbox_dispatcher = dispatcher
    dispatcher.start()
    try:
        yield
    finally:
        await dispatcher.stop()


app = FastAPI(
    title="AI Writing Studio API",
    version="0.1.0",
    description="Backend API for a Snowflake-method AI long-form writing studio.",
    lifespan=lifespan,
)

install_application_error_handlers(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def observability_middleware(request: Request, call_next):
    """Assign a request id and emit one structured HTTP access event."""
    request_id = request.headers.get("x-request-id") or new_request_id()
    bind_request_id(request_id)
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception as exc:
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        log_event(
            "http_request",
            operation=f"{request.method} {request.url.path}",
            duration_ms=duration_ms,
            result="error",
            error_code=type(exc).__name__,
        )
        raise
    duration_ms = round((time.perf_counter() - started) * 1000, 2)
    route_path = getattr(request.scope.get("route"), "path", request.url.path)
    path_params = request.scope.get("path_params") or {}
    log_event(
        "http_request",
        operation=f"{request.method} {route_path}",
        project_id=str(path_params.get("project_id", "")),
        status=response.status_code,
        duration_ms=duration_ms,
        result="ok"
        if response.status_code < 400
        else "client_error"
        if response.status_code < 500
        else "server_error",
        error_code=f"http_{response.status_code}" if response.status_code >= 400 else "",
    )
    response.headers["x-request-id"] = request_id
    return response


app.include_router(health.router, prefix="/api")
app.include_router(projects.router, prefix="/api")
app.include_router(backup.router, prefix="/api")
app.include_router(snowflake.router, prefix="/api")
app.include_router(canon.router, prefix="/api")
app.include_router(scenes.router, prefix="/api")
app.include_router(memory.router, prefix="/api")
app.include_router(models.router, prefix="/api")
app.include_router(narrative.router, prefix="/api")
app.include_router(graph.router, prefix="/api")
app.include_router(manuscript.router, prefix="/api")
app.include_router(wiki.router, prefix="/api")
app.include_router(writeback.router, prefix="/api")
app.include_router(references.router, prefix="/api")
app.include_router(analysis.router, prefix="/api")
app.include_router(outbox.router, prefix="/api")
