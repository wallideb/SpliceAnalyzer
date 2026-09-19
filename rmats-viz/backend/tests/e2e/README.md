# End-to-end verification against a real PostgreSQL

Reproduces the closing-release verification of the Python backend: migrations from an empty
database, ingestion of the five rMATS event types (JC + JCEC duplicates, NA replicates, decimal
commas, near-duplicates, NAGNAG/RI/MXE pairs, an empty `summary.txt`), splice-feature computation
on a synthetic genome with planted GT/AG signals and branch points, MANE Select vs Plus Clinical
selection, deep analyses (pattern comparison, hnRNP seven regions, exact permutation), Excel/PDF
exports, cascade delete and the compute-status lifecycle. 124 assertions; expected values are
computed independently by `make_data.py` (written to `data/expected.json`).

External APIs are not required: with no network every annotation call must degrade gracefully,
and that is asserted too.

## Running inside the docker-compose stack (simplest)
```bash
# from the repository root, stack started with `docker compose up -d`
docker compose exec db psql -U rmats -d rmatsdb -c "CREATE DATABASE e2edb OWNER rmats;"
docker compose exec backend python -m pytest tests -q
docker compose exec -e DATABASE_URL=postgresql+asyncpg://rmats:rmats@db:5432/e2edb backend sh -c \
  'alembic upgrade head && alembic check && cd tests/e2e && python make_data.py && SAMTOOLS_BIN=samtools python run_e2e.py | tail -3'
```
The backend image ships the real `samtools` and `pytest`; `SAMTOOLS_BIN=samtools` bypasses the pysam wrapper and pysam is not needed inside the container (the scripts fall back to `samtools faidx`).

## Requirements (running on the host instead)
- PostgreSQL 16 binaries (`initdb`, `pg_ctl`, `psql`), run as a non-root user.
- Backend Python dependencies (`pip install -r ../../requirements.txt`) plus `pysam` (the
  `samtools` wrapper in this directory emulates `samtools faidx` / `--version` with pysam, so no
  samtools binary is needed).

## Run
```bash
# 1. temporary database on port 5433 (as a non-root user)
initdb -D /tmp/pgdata && pg_ctl -D /tmp/pgdata -o "-p 5433 -k /tmp" -l /tmp/pg.log start
psql -h /tmp -p 5433 -d postgres -c "CREATE ROLE rmats LOGIN PASSWORD 'rmats' SUPERUSER;" \
                                  -c "CREATE DATABASE rmatsdb OWNER rmats;"
export DATABASE_URL=postgresql+asyncpg://rmats:rmats@127.0.0.1:5433/rmatsdb

# 2. migrations (from rmats-viz/backend)
alembic upgrade head && alembic check

# 3. synthetic data, then the scenario
cd tests/e2e
chmod +x samtools
python make_data.py          # writes data/ (FASTA + .fai, MANE GFF3, rMATS files, expected.json)
python run_e2e.py            # prints every assertion; writes results.json, deep.pdf, deep.xlsx

# 4. stop the database
pg_ctl -D /tmp/pgdata stop
```
`run_e2e.py` sets `GRCH38_FASTA`, `SAMTOOLS_BIN`, `MANE_GFF3` and `MANE_CACHE_DB` itself;
`DATABASE_URL` is taken from the environment (default above). The generated `data/`, `results.json`,
`*.pdf`, `*.xlsx`, `mane_cache.db*` are ignored by git.
