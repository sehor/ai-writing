from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.data import data_store
from app.routers import (
    canon,
    graph,
    health,
    manuscript,
    memory,
    projects,
    references,
    scenes,
    snowflake,
    wiki,
    writeback,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    data_store.init()
    yield


app = FastAPI(
    title="AI Writing Studio API",
    version="0.1.0",
    description="Backend API for a Snowflake-method AI long-form writing studio.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api")
app.include_router(projects.router, prefix="/api")
app.include_router(snowflake.router, prefix="/api")
app.include_router(canon.router, prefix="/api")
app.include_router(scenes.router, prefix="/api")
app.include_router(memory.router, prefix="/api")
app.include_router(graph.router, prefix="/api")
app.include_router(manuscript.router, prefix="/api")
app.include_router(wiki.router, prefix="/api")
app.include_router(writeback.router, prefix="/api")
app.include_router(references.router, prefix="/api")
