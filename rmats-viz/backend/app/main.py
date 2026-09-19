import logging
import os
import shutil
import subprocess
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import func, text, update

from app.config import settings
from app.database import AsyncSessionLocal, engine
from app.models.analysis import Analysis
from app.routers import analyses, annotations, deep_analyses, events, export, genes, splice

logger = logging.getLogger(__name__)

# Provisioning of the reference genome is NOT done by the API process any more
# (it used to download ~800 MB in a worker thread at startup).  Run this script
# once (or as a compose init container) to create GRCH38_FASTA + .fai:
FASTA_SETUP_SCRIPT = "data/setup_grch38_fasta.sh"


def _log_fasta_readiness() -> None:
    """Log whether the FASTA, its .fai index and samtools are available.

    Purely informational: endpoints check ``fasta_available()`` on every call,
    so files that appear later are picked up without a restart.
    """
    fasta = settings.GRCH38_FASTA
    fasta_ok = os.path.isfile(fasta)
    fai_ok = os.path.isfile(fasta + ".fai")
    samtools_path = shutil.which(settings.SAMTOOLS_BIN)

    if fasta_ok and fai_ok and samtools_path:
        logger.info(
            "Sequence extraction ready: FASTA=%s (.fai present), samtools=%s",
            fasta, samtools_path,
        )
        return

    missing: list[str] = []
    if not fasta_ok:
        missing.append(f"FASTA file {fasta}")
    if not fai_ok:
        missing.append(f"index {fasta}.fai")
    if not samtools_path:
        missing.append(f"samtools binary '{settings.SAMTOOLS_BIN}' on PATH")
    logger.warning(
        "Sequence extraction NOT ready — missing: %s. "
        "Run `bash %s` (downloads GRCh38 and runs `samtools faidx`) and/or "
        "install samtools; the API keeps running and falls back to Ensembl REST "
        "for splice-site windows (hnRNP region scanning requires the local FASTA).",
        "; ".join(missing), FASTA_SETUP_SCRIPT,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    # On startup, reset any analyses stuck in 'deleting' (e.g. from a previous
    # container restart that cancelled in-flight background tasks).
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                update(Analysis)
                .where(Analysis.status == "deleting")
                .values(status="error", error_message="Deletion interrupted by restart — please retry")
                .returning(Analysis.id)
            )
            orphaned = result.scalars().all()
            await db.commit()
            if orphaned:
                logger.warning("Reset %d orphaned 'deleting' analyses to 'error': %s", len(orphaned), orphaned)
    except Exception:
        logger.exception("Failed to reset orphaned 'deleting' analyses on startup")

    # Likewise, a splice-feature computation that was 'running' when the
    # process died can never finish: mark it so the UI stops polling.  This
    # lifespan runs once per uvicorn worker, so only rows whose heartbeat
    # (updated_at, refreshed after every chunk by the background task) is
    # older than splice.COMPUTE_STALE_AFTER are reset — a computation that is
    # alive in another worker keeps its heartbeat fresh and is left alone.
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                update(Analysis)
                .where(
                    Analysis.compute_status == "running",
                    Analysis.updated_at < func.now() - splice.COMPUTE_STALE_AFTER,
                )
                .values(
                    compute_status="error",
                    compute_error="Splice feature computation interrupted by restart — please re-run",
                )
                .returning(Analysis.id)
            )
            interrupted = result.scalars().all()
            await db.commit()
            if interrupted:
                logger.warning(
                    "Reset %d stale (heartbeat > %s) splice computations to 'error': %s",
                    len(interrupted), splice.COMPUTE_STALE_AFTER, interrupted,
                )
    except Exception:
        logger.exception("Failed to reset interrupted splice computations on startup")

    _log_fasta_readiness()
    yield
    # Shutdown: nothing to clean up


app = FastAPI(title="rMATS Visualizer API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(analyses.router, prefix="/api/v1")
app.include_router(events.router, prefix="/api/v1")
app.include_router(deep_analyses.router, prefix="/api/v1")
app.include_router(genes.router, prefix="/api/v1")
app.include_router(annotations.router, prefix="/api/v1")
app.include_router(splice.router, prefix="/api/v1")
app.include_router(export.router, prefix="/api/v1")


@app.get("/api/v1/health")
async def health():
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"status": "ok", "db": "ok"}
    except Exception as exc:
        return JSONResponse(
            status_code=503,
            content={"status": "error", "db": f"error: {exc}"},
        )


@app.get("/api/v1/debug/fasta")
async def debug_fasta():
    """Diagnostic endpoint — checks FASTA + samtools availability inside the container."""
    fasta = settings.GRCH38_FASTA
    samtools_bin = settings.SAMTOOLS_BIN
    info: dict = {
        "grch38_fasta_setting": fasta,
        "samtools_bin_setting": samtools_bin,
        "fasta_exists": os.path.isfile(fasta),
        "fai_exists": os.path.isfile(fasta + ".fai"),
        "samtools_on_path": shutil.which(samtools_bin),
        "setup_script": FASTA_SETUP_SCRIPT,
    }
    # samtools version
    try:
        r = subprocess.run([samtools_bin, "--version"], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=5)
        info["samtools_version"] = r.stdout.split("\n")[0]
        info["samtools_rc"] = r.returncode
    except FileNotFoundError:
        info["samtools_version"] = "NOT FOUND"
        info["samtools_rc"] = -1
    except Exception as e:
        info["samtools_version"] = f"error: {e}"
    # fai contents
    if info["fai_exists"]:
        with open(fasta + ".fai") as f:
            info["fai_first_line"] = f.readline().strip()
    # quick faidx test if all present
    if info["fasta_exists"] and info["fai_exists"] and info.get("samtools_rc") == 0:
        try:
            r2 = subprocess.run(
                [samtools_bin, "faidx", fasta, "chr1:1000000-1000010"],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10,
            )
            info["faidx_test_rc"] = r2.returncode
            info["faidx_test_out"] = r2.stdout.strip()
            info["faidx_test_err"] = r2.stderr.strip()
        except Exception as e:
            info["faidx_test_rc"] = -1
            info["faidx_test_err"] = str(e)
    return info
