from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import health, projects, snowflake


app = FastAPI(
    title="AI Writing Studio API",
    version="0.1.0",
    description="Backend API for a Snowflake-method AI long-form writing studio.",
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

