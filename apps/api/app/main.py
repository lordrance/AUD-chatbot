"""FastAPI 应用入口：挂载 CORS 与各业务路由。"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError

from app.routers import consent_public, followup_public, health, sessions

app = FastAPI(title="SafeChat-AUD API", version="0.1.0")


@app.exception_handler(OperationalError)
async def _db_operational_error_handler(_request: Request, _exc: OperationalError) -> JSONResponse:
    """数据库不可达时返回 503，避免笼统500；常见原因是本机未启动 PostgreSQL。"""
    return JSONResponse(
        status_code=503,
        content={
            "detail": "database_unavailable",
            "message": (
                "Cannot connect to the database. Start PostgreSQL first "
                "(from the repo root: docker compose up db), then retry."
            ),
        },
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api/v1")
app.include_router(consent_public.router, prefix="/api/v1")
app.include_router(followup_public.router, prefix="/api/v1")
app.include_router(sessions.router, prefix="/api/v1")


@app.get("/")
def root() -> dict[str, str]:
    """根路径健康提示，指向 OpenAPI 文档。"""
    return {"service": "safechat-aud-api", "docs": "/docs"}
