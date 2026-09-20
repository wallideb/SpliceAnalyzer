from pydantic_settings import BaseSettings
from typing import List
import json


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://rmats:rmats@db:5432/rmatsdb"
    CORS_ORIGINS: str = '["http://localhost:3000"]'

    # ── Splice pattern analysis ──────────────────────────────────────────────
    # Path to the GRCh38 FASTA file (must be indexed with samtools faidx).
    GRCH38_FASTA: str = "/data/GRCh38.fa"
    # samtools binary (full path or name if in PATH)
    SAMTOOLS_BIN: str = "samtools"
    # SQLite cache for MANE transcript lookups (avoids repeated Ensembl calls)
    MANE_CACHE_DB: str = "/data/mane_cache.db"
    # Local MANE GFF3 file — primary source for MANE annotation (no network needed).
    # Download from: https://ftp.ncbi.nlm.nih.gov/refseq/MANE/MANE_human/current/
    # Expected file: MANE.GRCh38.v*.ensembl_genomic.gff.gz
    MANE_GFF3: str = "/data/MANE.GRCh38.ensembl_genomic.gff.gz"
    # Optional directory where the deep-analysis PDF export also writes every
    # figure as a standalone SVG (one sub-directory per deep analysis).
    # None (default) disables the side-dump entirely.
    SVG_EXPORT_DIR: str | None = None

    # ── Chunked upload ───────────────────────────────────────────────────────
    # Browsers upload rMATS files through POST /analyses/uploads in ≤ 512 KB
    # requests (reverse proxies such as the Codespaces port forwarder or a
    # default nginx reject bodies > 1 MB with 413).  Chunks are assembled in
    # one sub-directory per upload session under this directory ...
    UPLOAD_TMP_DIR: str = "/tmp/spliceanalyzer_uploads"
    # ... and sessions older than this are purged (best effort) whenever a new
    # session is created, so an abandoned browser tab cannot fill the disk.
    UPLOAD_SESSION_TTL_HOURS: int = 24

    @property
    def cors_origins_list(self) -> List[str]:
        try:
            return json.loads(self.CORS_ORIGINS)
        except Exception:
            return [self.CORS_ORIGINS]

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
