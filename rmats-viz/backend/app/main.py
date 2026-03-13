import asyncio
import gzip
import logging
import os
import shutil
import subprocess
import urllib.request
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.config import settings
from app.database import engine
from app.routers import analyses, annotations, deep_analyses, events, export, genes, splice

logger = logging.getLogger(__name__)

GRCH38_GENOME_URL = (
    "https://ftp.ncbi.nlm.nih.gov/genomes/all/GCA/000/001/405/"
    "GCA_000001405.15_GRCh38/seqs_for_alignment_pipelines.ucsc_ids/"
    "GCA_000001405.15_GRCh38_no_alt_analysis_set.fna.gz"
)


def _setup_fasta() -> None:
    """Download and index full GRCh38 FASTA if not already present (runs inside container).

    If the FASTA exists but the .fai index is missing, only the indexing step runs.
    """
    fasta = settings.GRCH38_FASTA
    fai = fasta + ".fai"

    if os.path.isfile(fasta) and os.path.isfile(fai):
        logger.info("FASTA already present: %s", fasta)
        return

    data_dir = os.path.dirname(fasta)
    os.makedirs(data_dir, exist_ok=True)

    # Download only if the FASTA file itself is missing
    if not os.path.isfile(fasta):
        logger.info("Downloading full GRCh38 genome FASTA (~800 MB compressed) ...")
        try:
            req = urllib.request.Request(GRCH38_GENOME_URL, headers={"User-Agent": "rmats-viz/1.0"})
            with urllib.request.urlopen(req, timeout=1800) as resp, open(fasta, "wb") as out_f:
                with gzip.GzipFile(fileobj=resp) as gz_in:
                    shutil.copyfileobj(gz_in, out_f)
        except Exception as exc:
            logger.error("FASTA download/decompress failed: %s", exc)
            if os.path.isfile(fasta):
                os.remove(fasta)
            return
        logger.info("Download complete.")
    else:
        logger.info("FASTA exists but index is missing — indexing only.")

    logger.info("Indexing with samtools faidx ...")
    try:
        subprocess.run(
            [settings.SAMTOOLS_BIN, "faidx", fasta],
            check=True, timeout=600,
        )
    except Exception as exc:
        logger.error("samtools faidx failed: %s", exc)
        return

    logger.info("FASTA setup complete: %s (+ .fai)", fasta)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Fire-and-forget: download FASTA in the background so the server starts
    # accepting requests immediately.  fasta_available() checks the filesystem
    # on every call, so endpoints automatically pick up the file once ready.
    asyncio.get_event_loop().run_in_executor(None, _setup_fasta)
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
    }
    # samtools version
    try:
        r = subprocess.run([samtools_bin, "--version"], capture_output=True, text=True, timeout=5)
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
    if info["fasta_exists"] and info["fai_exists"] and info["samtools_rc"] == 0:
        try:
            r2 = subprocess.run(
                [samtools_bin, "faidx", fasta, "chr1:1000000-1000010"],
                capture_output=True, text=True, timeout=10,
            )
            info["faidx_test_rc"] = r2.returncode
            info["faidx_test_out"] = r2.stdout.strip()
            info["faidx_test_err"] = r2.stderr.strip()
        except Exception as e:
            info["faidx_test_rc"] = -1
            info["faidx_test_err"] = str(e)
    return info
