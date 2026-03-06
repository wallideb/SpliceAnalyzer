from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.config import settings
from app.database import engine
from app.routers import analyses, annotations, events, export, genes, splice

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
app.include_router(splice.router, prefix="/api/v1")
app.include_router(export.router, prefix="/api/v1")


@app.get("/api/v1/health")
async def health():
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"status": "ok", "db": "ok"}
    except Exception as exc:
        return {"status": "ok", "db": f"error: {exc}"}


@app.get("/api/v1/debug/fasta")
async def debug_fasta():
    """Diagnostic endpoint — checks FASTA + samtools availability inside the container."""
    import os, shutil, subprocess
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
                [samtools_bin, "faidx", fasta, "NC_000019.10:1000000-1000010"],
                capture_output=True, text=True, timeout=10,
            )
            info["faidx_test_rc"] = r2.returncode
            info["faidx_test_out"] = r2.stdout.strip()
            info["faidx_test_err"] = r2.stderr.strip()
        except Exception as e:
            info["faidx_test_rc"] = -1
            info["faidx_test_err"] = str(e)
    return info
