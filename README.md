# SpliceAnalyzer (rMATS-Viz)

<p align="center">
  <img src="assets/svg/DNA.svg" alt="DNA icon" width="48"/>
  &nbsp;&nbsp;&nbsp;
  <img src="assets/svg/CONNECT.svg" alt="Connect icon" width="48"/>
</p>

<p align="center">
  <strong>A web application for visualizing, exploring, and characterizing RNA alternative splicing events from rMATS output.</strong>
</p>

<p align="center">
  <a href="#quick-start">Quick Start</a> &bull;
  <a href="#features">Features</a> &bull;
  <a href="#architecture">Architecture</a> &bull;
  <a href="#api-reference">API Reference</a> &bull;
  <a href="#scientific-references">Scientific References</a>
</p>

---

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Quick Start](#quick-start)
  - [Prerequisites](#prerequisites)
  - [Installation](#installation)
  - [GRCh38 FASTA Setup](#grch38-fasta-setup)
- [Configuration](#configuration)
- [Usage Guide](#usage-guide)
  - [Creating an Analysis](#creating-an-analysis)
  - [Browsing Events](#browsing-events)
  - [Top-10 View](#top-10-view)
  - [Deep Splice Analysis](#deep-splice-analysis)
  - [Gene Annotations](#gene-annotations)
  - [Exporting Results](#exporting-results)
- [Internationalisation (i18n)](#internationalisation-i18n)
- [API Reference](#api-reference)
  - [Analyses & Events](#analyses--events)
  - [Splice Site Analysis](#splice-site-analysis)
  - [Gene Annotations API](#gene-annotations-api)
  - [Export](#export-endpoints)
  - [Diagnostics](#diagnostics)
- [Splice Feature Reference](#splice-feature-reference)
- [Scientific References](#scientific-references)
- [Technology Stack](#technology-stack)
- [Troubleshooting](#troubleshooting)
- [Assets](#assets)
- [Contributing](#contributing)

---

## Overview

**SpliceAnalyzer** (rMATS-Viz) provides a browser-based interface on top of [rMATS](https://rnaseq-mats.sourceforge.io/) junction-count output files (e.g., `SE.MATS.JC.txt`). It enables researchers to upload rMATS results, explore alternative splicing events interactively, characterize splice-site signals at single-event resolution, and export curated findings for publication or clinical review.

The application supports all five rMATS event types:

| Event Type | Full Name | Description |
|:----------:|-----------|-------------|
| **SE** | Skipped Exon | An exon is included or excluded from the mature mRNA |
| **A5SS** | Alternative 5' Splice Site | Two or more alternative 5' splice sites compete |
| **A3SS** | Alternative 3' Splice Site | Two or more alternative 3' splice sites compete |
| **MXE** | Mutually Exclusive Exons | One of two exons is retained, never both |
| **RI** | Retained Intron | An intron is retained in the mature transcript |

---

## Features

### Core Functionality

- **Drag-and-drop file upload** — Upload rMATS `.txt` junction-count files with automatic sample-group mapping and event-type inference from filename
- **Analysis management** — Create, list, navigate, and delete named analyses
- **Event browser** — Sortable, filterable, paginated table of all splicing events with support for filtering by event type, gene symbol, FDR threshold, P-value, and minimum |ΔΨ|
- **Top-10 ranking** — Events automatically ranked by statistical significance (FDR) and inclusion-level difference (|ΔΨ|)
- **Gene basket** — Collect genes of interest across analyses for batch annotation and export
- **Dark mode** — Toggle-able theme with persistent preference via `localStorage`
- **Internationalisation** — Full English / French language switcher; all UI strings are externalized

### Splice Site Analysis (SE events)

- **Donor (5'SS) and acceptor (3'SS) sequences** — 9 nt and 23 nt windows around splice junctions with GT-AG canonical check
- **Polypyrimidine tract (PPT)** — Score (C+T fraction) and longest consecutive pyrimidine run in the ~47 nt upstream of the 3'SS
- **Branch-point detection** — Rule-based YNYURAY motif search with positional scoring (0-7 scale) and distance to 3'SS
- **Exon and intron sizing** — Skipped exon length plus upstream and downstream intron sizes
- **Event clustering** — Union-Find algorithm deduplicates near-identical SE events sharing exon boundaries within a 50 bp threshold
- **Aggregate pattern analysis** — Position Weight Matrices (PWM), IUPAC consensus sequences, and statistical summaries across all SE events
- **Sequence source flexibility** — Primary extraction from local GRCh38 FASTA via `samtools faidx`, with automatic Ensembl REST API fallback when FASTA is unavailable

### MANE Frame Annotation

- Maps each skipped exon to its **MANE Select** transcript via the Ensembl REST API
- Classifies the frame impact: `in_frame` (exon length divisible by 3), `frameshift`, `non_coding` (UTR), or `partial`
- Caches successful lookups in a local SQLite database to minimize redundant API calls

### Gene Annotations & Interactions

- **Ensembl gene search** — Autocomplete by HUGO gene symbol (minimum 2 characters)
- **PanelApp disease panels** — Queries PanelApp Australia (with PanelApp UK fallback) for diagnostic gene panel membership and confidence ratings (green/amber/red)
- **Gene Ontology** — Retrieves GO terms (Biological Process, Molecular Function, Cellular Component) via mygene.info
- **UniProt** — Fetches reviewed protein function summaries
- **STRING-DB interactions** — Protein-protein interaction combined scores between gene pairs, with Europe PMC literature PMIDs

### Permutation Testing

- Per-event permutation test for ΔΨ significance by randomly permuting sample labels
- Multi-parameter permutation tests for auxiliary metrics: PPT score, exon size, frame fraction, and canonical splice-site fraction
- Empirical p-values with Phipson & Smyth continuity correction: `p = (k+1)/(N+1)`
- Pure Python implementation (no NumPy dependency)

### Export

- **PDF report** — Multi-page document including analysis summary, top SE events ranked by FDR and |ΔΨ|, methodology appendix, bibliographic references, and statistical methods
- **Parameterized Excel export** — Interactive modal for selecting annotation column groups (`core`, `panelapp`, `go`, `stringdb`) before download; optional groups are fetched in parallel at export time

### Scientific Provenance

- Collapsible `ScienceNote` widgets embedded in each analytical panel
- Every algorithm and formula links to its primary literature via PubMed or DOI
- Central reference registry in `frontend/src/lib/references.ts`

---

## Architecture

```
┌─────────────────────────────────────────────────┐
│                Browser (port 3000)               │
│             Next.js 14 / React 18                │
│       TypeScript · Tailwind CSS · TanStack       │
└────────────────────┬────────────────────────────┘
                     │ REST (JSON)
┌────────────────────▼────────────────────────────┐
│                API (port 8000)                   │
│           FastAPI 0.111 / Python 3.12            │
│      SQLAlchemy 2.0 async · Pydantic v2          │
│              samtools (FASTA I/O)                │
└────────────────────┬────────────────────────────┘
                     │ asyncpg
┌────────────────────▼────────────────────────────┐
│          PostgreSQL 16 (port 5432)               │
│              Docker volume                       │
└─────────────────────────────────────────────────┘
```

**External services** (outbound HTTPS from backend):

| Service | Purpose |
|---------|---------|
| [Ensembl REST](https://rest.ensembl.org/) | MANE Select transcript lookup, CDS intervals, gene search |
| [mygene.info](https://mygene.info/) | Gene Ontology terms |
| [UniProt](https://www.uniprot.org/) | Protein function summaries |
| [STRING-DB v12](https://string-db.org/) | Protein-protein interactions |
| [Europe PMC](https://europepmc.org/) | Literature PMIDs |
| [PanelApp AU](https://panelapp.agha.umccr.org/) / [PanelApp UK](https://panelapp.genomicsengland.co.uk/) | Disease gene panel membership |

All three application services are orchestrated with **Docker Compose**.

---

## Project Structure

```
SpliceAnalyzer/
├── README.md                           # This file
├── docker-compose.yml                  # Orchestration: PostgreSQL + Backend + Frontend
├── .env.example                        # Environment variable template
├── SE.MATS.JC.PUROMOINS.sig.txt       # Sample rMATS data (SE junction counts)
├── assets/
│   └── svg/
│       ├── DNA.svg                     # DNA helix icon
│       └── CONNECT.svg                 # Network connection diagram
└── rmats-viz/
    ├── backend/
    │   ├── Dockerfile                  # Python 3.12-slim + samtools
    │   ├── requirements.txt            # Python dependencies
    │   ├── alembic.ini                 # Database migration config
    │   ├── alembic/versions/           # Schema migration scripts (0001–0005)
    │   └── app/
    │       ├── main.py                 # FastAPI app entry point + CORS + health checks
    │       ├── config.py               # Pydantic settings (env vars)
    │       ├── database.py             # SQLAlchemy async engine + session factory
    │       ├── models/
    │       │   ├── analysis.py         # Analysis, SampleGroup
    │       │   ├── event.py            # SplicingEvent (12 indexes)
    │       │   └── splice.py           # EventCluster, EventSpliceFeature
    │       ├── routers/
    │       │   ├── analyses.py         # CRUD + file upload
    │       │   ├── events.py           # Event listing + Top-10
    │       │   ├── genes.py            # Gene search / autocomplete
    │       │   ├── annotations.py      # PanelApp, GO, UniProt, STRING
    │       │   ├── splice.py           # Splice feature compute + patterns
    │       │   └── export.py           # Excel + PDF generation
    │       ├── schemas/                # Pydantic request/response models
    │       │   ├── analysis.py
    │       │   ├── event.py
    │       │   ├── annotation.py
    │       │   ├── gene.py
    │       │   └── splice.py
    │       ├── services/               # Business logic layer
    │       │   ├── parser.py           # rMATS TSV parsing (handles French locale decimals)
    │       │   ├── event_selector.py   # Top-10 ranking by FDR / ΔΨ
    │       │   ├── event_cluster.py    # Union-Find SE event deduplication
    │       │   ├── sequence.py         # samtools faidx wrapper + UCSC↔RefSeq conversion
    │       │   ├── splice_features.py  # GT-AG, PPT score, branch-point computation
    │       │   ├── mane.py             # MANE Select transcript + frame classification
    │       │   ├── ensembl.py          # Ensembl REST API client
    │       │   ├── gene_ontology.py    # mygene.info → GO terms
    │       │   ├── uniprot.py          # UniProt → protein function
    │       │   ├── stringdb.py         # STRING-DB → PPI + PMIDs
    │       │   ├── panelapp.py         # PanelApp AU/UK → disease panels
    │       │   └── permutation.py      # Permutation tests for ΔΨ + splice metrics
    │       └── utils/
    │           └── composite_key.py    # Column mapping + deduplication rules
    ├── frontend/
    │   ├── Dockerfile                  # Node 20 Alpine
    │   ├── package.json                # Dependencies (Next.js, TanStack, Tailwind)
    │   ├── tailwind.config.ts
    │   ├── next.config.mjs             # API proxy rewrite → backend:8000
    │   └── src/
    │       ├── app/                    # Next.js App Router pages
    │       │   ├── layout.tsx
    │       │   └── analyses/
    │       │       ├── new/            # Upload page
    │       │       ├── [id]/           # Analysis detail (events, top10)
    │       │       └── [id]/deep-analysis/  # Advanced splice features
    │       ├── components/
    │       │   ├── top10/              # SpliceView, ExonDiagram, SpliceSiteTrack, PPTTrack, etc.
    │       │   ├── events/             # Event table + filtering controls
    │       │   ├── genes/              # Gene search + autocomplete
    │       │   ├── basket/             # Gene collection for batch export
    │       │   ├── layout/             # AppHeader, SidebarNav
    │       │   ├── upload/             # Drag-and-drop file uploader
    │       │   └── ExcelExportModal.tsx # Column group selection modal
    │       ├── contexts/
    │       │   └── LanguageContext.tsx  # i18n provider + useT() hook
    │       ├── lib/
    │       │   ├── api/                # API client functions
    │       │   ├── i18n/               # en.ts, fr.ts locale dictionaries
    │       │   └── references.ts       # Scientific citation registry
    │       └── types/                  # TypeScript interfaces
    └── data/                           # Docker volume mount → /data
        ├── GRCh38.fa                   # GRCh38 FASTA (user-provided)
        ├── GRCh38.fa.fai               # samtools index (generated)
        └── mane_cache.db               # MANE lookup cache (auto-created)
```

---

## Quick Start

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) (v20.10+) and [Docker Compose](https://docs.docker.com/compose/) (v2.0+)
- ~4 GB free disk space (images + dependencies)
- For full splice analysis: GRCh38 reference genome FASTA (~3 GB for full genome, or ~60 MB for chr19-only development)

### Installation

**1. Clone and configure**

```bash
git clone <repo-url>
cd SpliceAnalyzer
cp .env.example .env          # edit credentials if needed
```

**2. Start all services**

```bash
docker compose up --build
```

This will:
1. Pull and start **PostgreSQL 16** with a health check
2. Build the **FastAPI backend** — installs Python dependencies + samtools, runs Alembic migrations, then starts Uvicorn on port 8000
3. Build the **Next.js frontend** — installs npm packages, starts the dev server on port 3000

**3. Open the application**

| Service | URL |
|---------|-----|
| Frontend (UI) | http://localhost:3000 |
| API docs (Swagger) | http://localhost:8000/docs |
| Health check | http://localhost:8000/api/v1/health |
| FASTA diagnostics | http://localhost:8000/api/v1/debug/fasta |

**4. (Optional) Provide the GRCh38 FASTA** for splice-site sequence analysis. See [GRCh38 FASTA Setup](#grch38-fasta-setup) below.

> **Note:** The application runs without the FASTA — size-based features, MANE frame annotation, and all non-sequence features will still work. Sequence-dependent features (donor/acceptor sequences, PPT, branch-point) require the FASTA.

### GRCh38 FASTA Setup

The splice-site analysis and MANE frame annotation require a locally indexed GRCh38 FASTA mounted at `/data/GRCh38.fa` inside the backend container (mapped from `rmats-viz/data/` on the host).

#### Development (chr19 only, ~60 MB)

If your test data contains only chr19 events (like the included sample file):

```bash
cd rmats-viz/data

# Download chromosome 19
wget https://hgdownload.soe.ucsc.edu/goldenPath/hg38/chromosomes/chr19.fa.gz
gunzip chr19.fa.gz
mv chr19.fa GRCh38.fa

# Index inside the running container (no local samtools needed)
docker compose exec backend samtools faidx /data/GRCh38.fa
```

#### Production (full genome, ~3 GB compressed)

```bash
cd rmats-viz/data

# Option A: NCBI RefSeq headers (NC_000001.11 …) — supported natively
wget https://ftp.ncbi.nlm.nih.gov/genomes/all/GCA/000/001/405/GCA_000001405.15_GRCh38/...

# Option B: UCSC chr-style headers (chr1 … chrY) — auto-converted by the backend
# Download from UCSC and rename to GRCh38.fa

# Index
docker compose exec backend samtools faidx /data/GRCh38.fa
```

Both header naming conventions are supported: the backend auto-detects the style from the `.fai` index and converts rMATS UCSC names to RefSeq accessions when needed.

#### Verify FASTA setup

```bash
curl http://localhost:8000/api/v1/debug/fasta
```

Expected response: `fasta_exists: true`, `fai_exists: true`, `faidx_test_rc: 0`.

---

## Configuration

Copy `.env.example` to `.env` and adjust as needed:

| Variable | Default | Description |
|----------|---------|-------------|
| `POSTGRES_USER` | `rmats` | PostgreSQL username |
| `POSTGRES_PASSWORD` | `rmats` | PostgreSQL password |
| `POSTGRES_DB` | `rmatsdb` | PostgreSQL database name |
| `DATABASE_URL` | `postgresql+asyncpg://rmats:rmats@db:5432/rmatsdb` | SQLAlchemy async connection string |
| `CORS_ORIGINS` | `["http://localhost:3000"]` | Allowed CORS origins (JSON array) |
| `GRCH38_FASTA` | `/data/GRCh38.fa` | Path to indexed GRCh38 FASTA inside the container |
| `SAMTOOLS_BIN` | `samtools` | samtools binary name or full path |
| `MANE_CACHE_DB` | `/data/mane_cache.db` | SQLite cache for Ensembl MANE lookups |
| `SPLICE_WINDOW` | `50` | Intronic window (nt) around each splice site |

> **MANE cache behavior:** Successful Ensembl lookups are cached in `mane_cache.db` to avoid repeated API calls. Failed lookups (network errors, no MANE transcript found) are **not** cached and will be retried on the next compute run.

---

## Usage Guide

### Creating an Analysis

1. Navigate to the **New Analysis** page (`/analyses/new`)
2. Drag and drop one or more rMATS junction-count files (e.g., `SE.MATS.JC.txt`, `A5SS.MATS.JC.txt`)
3. The event type is automatically inferred from the filename
4. Define sample group names for your conditions
5. Click **Create** — the parser ingests the TSV, handles duplicate IDs and French-locale decimals, and stores events in PostgreSQL

### Browsing Events

The event browser (`/analyses/{id}`) provides a fully interactive table with:

- **Column sorting** — Click any header to sort ascending/descending
- **Filters** — Event type selector, gene symbol search, FDR max, P-value max, minimum |ΔΨ|
- **Pagination** — Configurable page size
- **Direction-of-effect badges** — Visual indicators for exon skipping vs. inclusion

### Top-10 View

The Top-10 view (`/analyses/{id}/top10`) displays the most significant events ranked by FDR and |ΔΨ|. Each event card includes:

- **SpliceView** — Schematic of the splicing event with inclusion/exclusion levels
- **ExonDiagram** — Interactive exon-intron diagram with donor/acceptor/PPT/branch-point annotations
- **SpliceSiteTrack** — All 4 SE splice sites (upstream, skipped 5', skipped 3', downstream)
- **Sequence source badge** — Indicates whether sequences come from local FASTA or Ensembl REST fallback
- **PermutationPanel** — Interactive permutation test results with multi-parameter tabs
- **ScienceNote** — Collapsible citation widgets linking to primary literature
- **AnnotatedCard** — Gene annotations (PanelApp, GO, UniProt, STRING-DB) in tabbed panels

### Deep Splice Analysis

The deep analysis page (`/analyses/{id}/deep-analysis`) provides aggregate statistics across all SE events:

- **Consensus logo panels** — PWM-derived sequence logos for donor and acceptor sites
- **Motif pattern analysis** — IUPAC consensus with significance thresholds
- **PPT distribution** — Score and pyrimidine run length across events
- **Frame classification** — Proportions of in-frame, frameshift, and non-coding exon skipping events
- **GT-AG canonical compliance** — Fraction of events with canonical splice sites

### Gene Annotations

Search for any gene by HUGO symbol using the Ensembl-backed autocomplete. The annotation panel fetches and displays:

- **PanelApp** — Disease panels and confidence level (green = diagnostic grade)
- **Gene Ontology** — Top 3 terms per category (BP, MF, CC)
- **UniProt** — Reviewed protein function summary
- **STRING-DB** — Interaction scores with other genes in the analysis, plus supporting literature PMIDs

### Exporting Results

#### Excel Export

1. Click the **Export Excel** button on the analysis detail page
2. A modal lets you select which column groups to include:

| Group | Columns | Source |
|-------|---------|--------|
| `core` *(always)* | Gene, Event type, Strand, Exon/Intron sizes, FDR, ΔΨ, Read counts, Frame class | Local DB |
| `panelapp` | PanelApp Confidence, PanelApp Panels (top 3) | PanelApp REST API |
| `go` | GO:BP, GO:MF, GO:CC (top 3 terms each) | mygene.info |
| `stringdb` | STRING Max Score (highest combined score vs. all mutated genes) | STRING-DB v12 |

3. Optional groups are fetched in parallel with `asyncio.gather` at export time
4. The resulting `.xlsx` file includes styled headers, row banding, and auto-sized columns

#### PDF Export

Click the **Export PDF** button to generate a multi-page report containing:

- Analysis summary table
- Top SE events ranked by FDR and |ΔΨ|
- Appendix A: Pipeline methodology
- Appendix B: Bibliographic references
- Appendix C: Statistical methods applied

---

## Internationalisation (i18n)

All user-visible strings are stored in locale dictionaries under `frontend/src/lib/i18n/`:

| File | Locale |
|------|--------|
| `en.ts` | English (default) |
| `fr.ts` | French |

The active locale is managed by `LanguageContext` (`frontend/src/contexts/LanguageContext.tsx`). The `useT()` hook returns a resolver `t(key, vars?)` that:

- Resolves dot-path keys (e.g., `"sidebarNav.tabs.spliceAnalysis"`) against the active locale object
- Supports `{{varName}}` interpolation for dynamic values
- Falls back to the key string if the translation is missing

The language selector is rendered in `AppHeader` and persists the user's choice in `localStorage`.

**Adding a new language:** Create a new `xx.ts` in `src/lib/i18n/`, export it from `index.ts`, and add the locale code to the `LanguageProvider` switch.

---

## API Reference

The backend exposes a versioned REST API under `/api/v1`. Full interactive documentation is available at **http://localhost:8000/docs** (Swagger UI).

### Analyses & Events

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/analyses` | Create a new analysis (multipart file upload) |
| `GET` | `/api/v1/analyses` | List all analyses (ordered by `created_at` DESC) |
| `GET` | `/api/v1/analyses/{id}` | Get analysis details + sample groups |
| `DELETE` | `/api/v1/analyses/{id}` | Delete analysis and all associated data |
| `GET` | `/api/v1/analyses/{id}/events` | Paginated, filterable event list |
| `GET` | `/api/v1/analyses/{id}/events/top10` | Top-10 events by FDR rank |

**Event query parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `event_type` | string | Filter by type: `SE`, `A5SS`, `A3SS`, `MXE`, `RI` |
| `gene_symbol` | string | Filter by gene symbol (exact match) |
| `fdr_max` | float | Maximum FDR threshold |
| `p_value_max` | float | Maximum P-value threshold |
| `delta_psi_min` | float | Minimum |ΔΨ| threshold |
| `sort_by` | string | Column to sort by |
| `sort_dir` | string | `asc` or `desc` |
| `page` | int | Page number (1-indexed) |
| `page_size` | int | Results per page |

### Splice Site Analysis

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/splice/compute/{analysis_id}` | Compute splice features + clusters for all SE events |
| `GET` | `/api/v1/splice/feature/{event_id}` | Per-event features (computed on-the-fly if not cached) |
| `GET` | `/api/v1/splice/patterns/{analysis_id}` | Aggregate pattern analysis (PWM, consensus, frame stats) |

> The compute endpoint is **idempotent** — re-running overwrites existing feature rows and refreshes clusters. It requires the GRCh38 FASTA for sequence features; if unavailable, size-only features are computed.

### Gene Annotations API

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/genes/search?q=` | Ensembl gene autocomplete (min 2 chars, max 25 results) |
| `GET` | `/api/v1/genes/lookup/{symbol}` | Exact gene lookup |
| `GET` | `/api/v1/annotations/gene/{symbol}` | PanelApp panels + GO terms + UniProt summary |
| `POST` | `/api/v1/annotations/interactions` | STRING-DB interactions + PMIDs between gene pairs |

### Export Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/export/{id}/pdf` | Download PDF report |
| `GET` | `/api/v1/export/{id}/excel?include=core,panelapp,go,stringdb` | Download Excel; `include` is comma-separated |

### Diagnostics

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/health` | Health check (DB ping) |
| `GET` | `/api/v1/debug/fasta` | FASTA + samtools availability check |

---

## Splice Feature Reference

The following features are computed for each SE (Skipped Exon) event:

### Size Features

| Feature | Description | Formula |
|---------|-------------|---------|
| `exon_size` | Skipped exon length (bp) | `exon_end - exon_start` |
| `upstream_intron_size` | Upstream intron length | `exon_start - upstream_EE` |
| `downstream_intron_size` | Downstream intron length | `downstream_ES - exon_end` |

### Splice Site Sequences

| Feature | Description |
|---------|-------------|
| `donor_seq` | 9 nt window at 5'SS: 3 nt exon + GT + 4 nt intron |
| `acceptor_seq` | 23 nt window at 3'SS: 20 nt intron + AG + 3 nt exon |
| `ppt_seq` | ~47 nt polypyrimidine tract upstream of 3'SS |
| `donor_is_gt` | Whether the donor dinucleotide is GT (canonical) |
| `acceptor_is_ag` | Whether the acceptor dinucleotide is AG (canonical) |

### PPT (Polypyrimidine Tract) Metrics

| Feature | Description |
|---------|-------------|
| `ppt_score` | Fraction of C+T nucleotides in PPT window (0.0–1.0) |
| `ppt_longest_run` | Length of the longest consecutive C/T run |

### Branch-Point Detection

| Feature | Description |
|---------|-------------|
| `bp_motif_found` | Whether a YNYURAY motif was found (score ≥ 4) |
| `bp_distance` | Distance (nt) from best motif center to 3'SS |
| `bp_score` | Positional match score (0–7): each position earns 1 point if it matches the consensus |

### MANE Frame Annotation

| Feature | Description |
|---------|-------------|
| `mane_transcript_id` | MANE Select transcript ID (from Ensembl REST) |
| `exon_rank` | Exon position in the MANE transcript (1-based) |
| `frame_region` | Genomic context: `CDS`, `UTR5`, `UTR3`, `partial`, or `unknown` |
| `frame_class` | Frame impact: `in_frame`, `frameshift`, `non_coding`, or `unknown` |
| `cds_exon_length` | Number of coding nucleotides in the skipped exon |

---

## Scientific References

Each analytical panel embeds collapsible `ScienceNote` widgets that cite the primary literature. All reference metadata is centralized in `frontend/src/lib/references.ts`.

### Reference Registry

| ID | Citation | Year | Used In |
|----|----------|:----:|---------|
| `rmats` | Shen S et al. *Proc Natl Acad Sci USA* | 2014 | SpliceView, PermutationPanel, main analysis page |
| `sequence_logos` | Schneider TD & Stephens RM. *Nucleic Acids Res* | 1990 | ConsensusLogoPanel, MotifPatternPanel |
| `shannon` | Shannon CE. *Bell Syst Tech J* | 1948 | ConsensusLogoPanel (information content) |
| `splice_sites` | Shapiro MB & Senapathy P. *Nucleic Acids Res* | 1987 | ConsensusLogoPanel, MotifPatternPanel |
| `maxent` | Yeo G & Burge CB. *J Comput Biol* | 2004 | ConsensusLogoPanel (MaxEntScan scoring) |
| `ppt` | Coolidge CJ et al. *Nucleic Acids Res* | 1997 | PPTTrack, MotifPatternPanel |
| `branch_point` | Padgett RA et al. *Annu Rev Biochem* | 1986 | PPTTrack, MotifPatternPanel |
| `permutation_phipson` | Phipson B & Smyth GK. *Stat Appl Genet Mol Biol* | 2010 | PermutationPanel |
| `benjamini_hochberg` | Benjamini Y & Hochberg Y. *J R Stat Soc Series B* | 1995 | SpliceView, PermutationPanel |
| `mane_select` | Morales J et al. *Nature* | 2022 | SpliceView, main analysis page |
| `gene_ontology` | Gene Ontology Consortium. *Nucleic Acids Res* | 2021 | AnnotatedCard (GO tab) |
| `stringdb` | Szklarczyk D et al. *Nucleic Acids Res* | 2023 | AnnotatedCard (STRING-DB tab) |
| `panelapp` | Martin AR et al. *Nat Genet* | 2019 | AnnotatedCard (PanelApp tab) |

### Key Formulas

| Formula | Expression | Reference |
|---------|------------|-----------|
| Information content | IC = 2 − H(**p**) bits, where H(**p**) = −Σ pᵢ log₂(pᵢ) | Schneider & Stephens (1990), Shannon (1948) |
| PPT score | Fraction of C+T in ~47 nt upstream of 3'SS | Coolidge et al. (1997) |
| Branch-point motif | YNYURAY (Y = C/T, N = any, R = A/G) | Padgett et al. (1986) |
| Permutation p-value | p = (k+1)/(N+1) with continuity correction | Phipson & Smyth (2010) |
| FDR correction | Benjamini-Hochberg step-up procedure | Benjamini & Hochberg (1995) |

---

## Technology Stack

### Backend

| Technology | Version | Purpose |
|------------|---------|---------|
| Python | 3.12 | Runtime |
| FastAPI | 0.111.0 | REST API framework |
| Uvicorn | 0.29.0 | ASGI server |
| SQLAlchemy | 2.0.30 | Async ORM (with asyncpg driver) |
| Alembic | 1.13.1 | Database migrations |
| Pydantic | 2.7.1 | Data validation and settings |
| Pandas | 2.2.2 | rMATS TSV parsing and data processing |
| httpx | 0.27.0 | Async HTTP client (external API calls) |
| openpyxl | 3.1.2 | Excel file generation |
| reportlab | 4.2.2 | PDF report generation |
| samtools | (system) | FASTA indexing and sequence extraction |

### Frontend

| Technology | Version | Purpose |
|------------|---------|---------|
| Next.js | 14.2.3 | React framework (App Router) |
| React | 18.x | UI library |
| TypeScript | — | Type safety |
| Tailwind CSS | 3.4.x | Utility-first CSS framework |
| TanStack Query | 5.x | Data fetching, caching, and synchronization |
| TanStack Table | 8.x | Headless table with sorting and filtering |
| Lucide React | 0.395.0 | Icon library |

### Infrastructure

| Technology | Version | Purpose |
|------------|---------|---------|
| PostgreSQL | 16 (Alpine) | Primary data store |
| Docker Compose | v2 | Service orchestration |
| Node.js | 20 (Alpine) | Frontend runtime |

---

## Troubleshooting

### Common Issues

**Services fail to start**
```bash
# Check service logs
docker compose logs backend
docker compose logs frontend
docker compose logs db
```

**Database connection errors**
- Ensure the `db` service is healthy: `docker compose ps`
- Verify `DATABASE_URL` in `.env` matches the PostgreSQL credentials

**FASTA not found / splice features unavailable**
```bash
# Run the diagnostic endpoint
curl http://localhost:8000/api/v1/debug/fasta
```
- Ensure `rmats-viz/data/GRCh38.fa` exists on the host
- Ensure the FASTA is indexed: `docker compose exec backend samtools faidx /data/GRCh38.fa`
- The application will still function without the FASTA — sequence-dependent features will be skipped

**Frontend can't reach the backend**
- The Next.js config proxies `/api` requests to `http://backend:8000` inside the Docker network
- If running outside Docker, update `next.config.mjs` to point to your backend URL

**French-locale decimal parsing errors**
- The parser automatically handles comma-as-decimal-separator (e.g., `"0,117"` → `0.117`)
- No user action required

### Resetting the Database

```bash
docker compose down -v          # removes the PostgreSQL volume
docker compose up --build       # recreates everything from scratch
```

---

## Assets

| File | Description |
|------|-------------|
| `assets/svg/DNA.svg` | DNA helix icon (36x36, Twemoji-style) |
| `assets/svg/CONNECT.svg` | Network connection diagram (512x512) |
| `rmats-viz/frontend/public/logo.svg` | Application logo |

---

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Make your changes
4. Ensure the application builds and runs: `docker compose up --build`
5. Commit with clear, descriptive messages
6. Open a Pull Request against the `dev` branch

### Development Tips

- **Backend hot-reload:** The backend volume mount (`./rmats-viz/backend:/app`) enables live code reloading with Uvicorn
- **Frontend hot-reload:** The frontend source mount (`./rmats-viz/frontend/src:/app/src`) enables Next.js Fast Refresh
- **API documentation:** Use Swagger UI at `http://localhost:8000/docs` to test endpoints interactively
- **Database migrations:** Create new migrations with `docker compose exec backend alembic revision --autogenerate -m "description"`
