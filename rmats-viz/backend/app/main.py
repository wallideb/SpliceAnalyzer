from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.config import settings
from app.database import engine
from app.routers import analyses, annotations, events, genes

app = FastAPI(title="rMATS Visualizer API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(analyses.router, prefix="/api/v1")
app.include_router(events.router, prefix="/api/v1")
app.include_router(genes.router, prefix="/api/v1")
app.include_router(annotations.router, prefix="/api/v1")


@app.get("/api/v1/health")
async def health():
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"status": "ok", "db": "ok"}
    except Exception as exc:
        return {"status": "ok", "db": f"error: {exc}"}
