# SpliceAnalyzer

<p align="center">
  <img src="rmats-viz/frontend/public/logo.svg" alt="SpliceAnalyzer logo" width="120"/>
</p>

<p align="center">
  <strong>A web application for visualizing, exploring, and characterizing RNA alternative splicing events from rMATS output.</strong>
</p>

<p align="center">
  <a href="#quick-start">Quick Start</a> &bull;
  <a href="#features">Features</a> &bull;
  <a href="#methodology">Methodology</a> &bull;
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
  - [Deep Splice Analysis](#deep-splice-analysis)
  - [Gene Annotations](#gene-annotations)
  - [Exporting Results](#exporting-results)
- [Methodology](#methodology)
  - [Coverage Filtering](#1-coverage-filtering)
  - [Ingestion Deduplication](#2-ingestion-deduplication)
  - [Splice Site Sequence Extraction](#3-splice-site-sequence-extraction)
  - [Splice Site Signals](#4-splice-site-signals)
  - [Polypyrimidine Tract](#5-polypyrimidine-tract-ppt)
  - [Branch-Point Detection](#6-branch-point-detection)
  - [MANE Frame Classification](#7-mane-select-frame-classification)
  - [Permutation Testing](#8-permutation-testing)
  - [Sequence Logos](#9-sequence-logos)
  - [hnRNP Motif Enrichment](#10-hnrnp-motif-enrichment)
  - [Pathway Enrichment (Enrichr)](#11-pathway-enrichment-enrichr)
  - [Pattern Comparison (Sig vs Non-Sig)](#12-pattern-comparison-sig-vs-non-sig)
  - [PanelApp Circuit Breaker](#13-panelapp-circuit-breaker)
- [Performance](#performance)
- [Internationalisation (i18n)](#internationalisation-i18n)
- [API Reference](#api-reference)
  - [Analyses & Events](#analyses--events)
  - [Deep Analyses](#deep-analyses)
  - [Splice Site Analysis](#splice-site-analysis)
  - [Gene Annotations API](#gene-annotations-api)
  - [Export Endpoints](#export-endpoints)
  - [Diagnostics](#diagnostics)
- [Splice Feature Reference](#splice-feature-reference)
- [Scientific References](#scientific-references)
- [Technology Stack](#technology-stack)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)

---

## Overview

**SpliceAnalyzer** provides a browser-based interface on top of [rMATS](https://rnaseq-mats.sourceforge.io/) output files (e.g., `SE.MATS.JC.txt` or `SE.MATS.JCEC.txt`). It enables researchers to upload rMATS results, explore alternative splicing events interactively, characterize splice-site signals at single-event resolution, perform aggregate statistical analyses across event groups, and export curated findings in a report format.

> **Disclaimer:** This tool is experimental and intended for research use only. It has not been validated for clinical or diagnostic purposes. Users are solely responsible for the interpretation and use of any results.

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

- **Drag-and-drop file upload** &mdash; Upload rMATS `.txt` output files with automatic sample-group mapping. The event type **and** the counting mode are detected from the exact `<TYPE>.MATS.<JC|JCEC>.txt` token (any prefix followed by a separator is accepted, so `PRIMARY_SE.MATS.JC.txt` is SE, not RI); `fromGTF[.novelJunction|.novelSpliceSite].<TYPE>.txt` annotation files are recognised too. When the filename is uninformative the header is sniffed (`riExonStart_0base` &rarr; RI, `1stExonStart_0base`/`2ndExonStart_0base` &rarr; MXE, `exonStart_0base` &rarr; SE; A3SS and A5SS share a header and therefore need the filename). The upload response carries `warnings` (empty file, no event imported)
- **JC vs JCEC recorded** &mdash; The counting mode of each row is stored (`counting_mode` = `JC` / `JCEC`), together with `IncFormLen` / `SkipFormLen` (`inc_form_len`, `skip_form_len`), which are needed to interpret JCEC counts
- **Native coordinates for every event type** &mdash; A3SS / A5SS rows keep their long / short / flanking exon coordinates (`long_exon_start`, `long_exon_end`, `short_es`, `short_ee`, `flanking_es`, `flanking_ee`); the generic `exon_*` columns are derived from the long exon and the flanking exon is copied into `upstream_*` or `downstream_*` according to its genomic position. MXE `1stExon*` columns map to the generic exon columns and `2ndExon*` to `second_exon_*`. The event identity constraint includes the MXE second exon and the A3SS/A5SS long/short exons
- **Coverage filtering** &mdash; Events whose mean per-replicate junction coverage (IJC + SJC) over the *available* replicates is below 10X in either sample group are filtered out on import (NA replicates are ignored, unequal IJC/SJC replicate lists are paired on their common prefix); rows dropped for low coverage and for missing counts are counted separately
- **Analysis management** &mdash; Create, list, navigate, and delete named analyses
- **Event browser** &mdash; Sortable (single server-side sort on FDR, gene symbol or |&Delta;&Psi;|), filterable, paginated table of all splicing events with support for filtering by event type, gene symbol, FDR threshold, P-value, and minimum |&Delta;&Psi;|
- **Dark mode** &mdash; Toggle-able theme with persistent preference via `localStorage`
- **Internationalisation** &mdash; Full English / French language switcher; all UI strings are externalized

### Splice Site Analysis (SE events)

- **Donor (5'SS) and acceptor (3'SS) sequences** &mdash; 9 nt and 23 nt windows around splice junctions with GT-AG canonical check
- **Polypyrimidine tract (PPT)** &mdash; Score (C+T fraction) and longest consecutive pyrimidine run in the ~47 nt upstream of the 3'SS
- **Branch-point detection** &mdash; Rule-based yUnAy / YNYTRAY motif search restricted to candidates whose branch adenosine lies 18&ndash;44 nt upstream of the 3'SS (branch A mandatory), with positional scoring (0&ndash;7 scale), the distance from the branch A to the exon start, and the matched 7-mer and its position
- **Exon and intron sizing** &mdash; Skipped exon length plus upstream and downstream intron sizes (both mean and median are computed; SVG exon diagrams and PDF comparison tables display **mean** values)
- **Aggregate pattern analysis** &mdash; Position Weight Matrices (PWM), IUPAC consensus sequences, and statistical summaries across all SE events
- **Sequence source flexibility** &mdash; Primary extraction from local GRCh38 FASTA via `samtools faidx` (batched, chunked at 5 000 regions per call, with chunk-halving retry so that only invalid regions are blanked), with automatic Ensembl REST API fallback when FASTA is unavailable

### Deep Splice Analysis

A second-pass module that partitions events into **significant** and **non-significant** groups using user-defined FDR and |&Delta;&Psi;| thresholds, then runs the following analyses across groups:

- **Pattern comparison** &mdash; Side-by-side group statistics: GT-AG canonical rates, PPT score distributions, exon/intron size distributions, frame-class breakdown, comparison sequence logos; 20 tests (Welch's t-test **and** Mann-Whitney U for each of the 7 continuous metrics, two-proportion z-test for the 6 proportions) with Benjamini-Hochberg q-values across the panel
- **hnRNP motif enrichment** &mdash; rMAPS2-inspired analysis scanning seven genomic regions around each SE event (both ends of each flanking intron) for 19 consensus hnRNP binding motifs; two tests per motif–region pair (presence two-proportion z-test and density Mann-Whitney U), each family Benjamini-Hochberg corrected (q &lt; 0.05) across the 133 pairs
- **Pathway enrichment (Enrichr)** &mdash; Significant-event gene symbols submitted to the Enrichr REST API against five curated gene-set libraries; top 10 terms per library by adjusted p-value, overlap reported as `k/n` from the library GMT sizes
- **Permutation testing** &mdash; Per-event |&Delta;&Psi;| significance testing against a null distribution of permuted sample labels: exact enumeration of every label split when C(n, n1) &le; 5000, Monte-Carlo sampling with the Phipson &amp; Smyth correction otherwise; the fraction of exact tests, the minimum attainable p-value and the replicate design are reported

### MANE Frame Annotation

- Maps each skipped exon to its **MANE Select** transcript via the local GFF3 file (transcripts indexed by their `tag=MANE_Select` attribute; MANE Plus Clinical transcripts are kept in a separate index) or the Ensembl REST API (CDS features filtered by their transcript `Parent`)
- Classifies the frame impact from the union of the CDS segments overlapping the exon: `in_frame` (coding length divisible by 3), `frameshift`, `non_coding`, or `unknown`; a companion `frame_region` (`CDS`, `partial`, `UTR5`, `UTR3`, `non_coding`, `unknown`) records the positional context
- Caches successful lookups in a local SQLite database (WAL mode for concurrent access) to minimize redundant API calls

### Gene Annotations & Interactions

- **Ensembl gene search** &mdash; Autocomplete by HUGO gene symbol (minimum 2 characters)
- **PanelApp disease panels** &mdash; Queries PanelApp Australia (with PanelApp UK fallback) for diagnostic gene panel membership and confidence ratings (green/amber/red); circuit breaker prevents cascade timeouts on unreachable instances
- **Gene Ontology** &mdash; Retrieves GO terms (Biological Process, Molecular Function, Cellular Component) via mygene.info
- **UniProt** &mdash; Fetches reviewed protein function summaries

### Export

- **PDF report** &mdash; Multi-page PDF report with a **section selector modal** for choosing which sections to include. Sections: analysis summary, significant SE events with splice feature tables, deep analysis sections (hnRNP motif enrichment, pathway enrichment with significant p-values bolded and starred, pattern comparison, permutation table at K = 50 / 100 / 250 / 500, summary schematic on a landscape page), frequency-mode sequence logos, methodology appendix, bibliographic references (numbered in order of first appearance; the hnRNP-only references `[11]`–`[28]` are appended only when the hnRNP panel is selected), and statistical methods. Each report ends with a closing note pointing to the SpliceAnalyzer repository for full documentation and methodology. Optionally includes deep analysis results when a deep analysis object is linked. When `SVG_EXPORT_DIR` is set, every figure of the deep-analysis PDF is also written as a standalone SVG file
- **Excel export (deep analysis only)** &mdash; Interactive modal for selecting annotation column groups (`core`, `panelapp`, `go`, `stringdb`) before download; optional groups are fetched in parallel at export time

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
| [Enrichr](https://maayanlab.cloud/Enrichr) | Pathway and gene-set enrichment |

All three application services are orchestrated with **Docker Compose**.

---

## Project Structure

```
SpliceAnalyzer/
├── README.md
├── docker-compose.yml
├── .env.example
└── rmats-viz/
    ├── backend/
    │   ├── Dockerfile
    │   ├── requirements.txt
    │   ├── alembic.ini
    │   ├── alembic/versions/
    │   ├── tests/
    │   │   ├── test_parser_coverage.py
    │   │   ├── test_parser_event_types.py
    │   │   ├── test_sequence_features.py
    │   │   ├── test_hnrnp_motifs.py
    │   │   ├── test_permutation.py
    │   │   └── test_stats.py
    │   └── app/
    │       ├── main.py
    │       ├── config.py
    │       ├── database.py
    │       ├── models/
    │       │   ├── analysis.py          # Analysis, SampleGroup
    │       │   ├── event.py             # SplicingEvent
    │       │   ├── splice.py            # EventSpliceFeature
    │       │   └── deep_analysis.py     # DeepAnalysis, DeepAnalysisEvent
    │       ├── routers/
    │       │   ├── analyses.py          # Analysis CRUD + file upload
    │       │   ├── events.py            # Event listing + ranking
    │       │   ├── genes.py             # Gene search / autocomplete
    │       │   ├── annotations.py       # PanelApp, GO, UniProt, STRING
    │       │   ├── splice.py            # Splice feature compute + patterns
    │       │   ├── deep_analyses.py     # Deep analysis CRUD + hnRNP + Enrichr + comparison
    │       │   └── export.py            # Excel + PDF generation
    │       ├── schemas/
    │       ├── utils/
    │       │   └── composite_key.py     # rMATS column map (SE/RI/MXE/A3SS/A5SS)
    │       └── services/
    │           ├── parser.py            # event-type detection, coverage filter, type-aware dedup
    │           ├── sequence.py          # samtools faidx wrapper (chunked batching, halving retry)
    │           ├── splice_features.py   # GT-AG, PPT score, branch-point (18–44 nt window)
    │           ├── mane.py              # MANE Select transcript + frame class
    │           ├── mane_local.py        # Local GFF3-based MANE annotation
    │           ├── ensembl.py           # Ensembl REST API client
    │           ├── gene_ontology.py     # mygene.info → GO terms
    │           ├── uniprot.py           # UniProt → protein function
    │           ├── stringdb.py          # STRING-DB → PPI + PMIDs
    │           ├── panelapp.py          # PanelApp AU/UK + circuit breaker
    │           ├── permutation.py       # Permutation tests for ΔΨ + splice metrics
    │           ├── hnrnp_motifs.py      # hnRNP motif enrichment (rMAPS2-inspired)
    │           └── enrichr.py           # Enrichr pathway enrichment
    └── frontend/
        ├── Dockerfile
        ├── package.json
        └── src/
            ├── app/
            ├── components/
            │   ├── events/
            │   ├── top10/
            │   │   ├── HnRNPMotifPanel.tsx   # hnRNP enrichment table + heatmap (7 regions)
            │   │   ├── EnrichrPanel.tsx       # Enrichr pathway panel
            │   │   ├── PermutationPanel.tsx   # Exact / Monte-Carlo permutation results
            │   │   ├── SidebarNav.tsx         # Deep analysis sidebar
            │   │   └── ...
            │   └── deep-analysis/
            ├── contexts/
            ├── lib/
            │   ├── i18n/                # en.ts, fr.ts
            │   ├── colors.ts            # Single nucleotide colour palette (A/C/G/T)
            │   └── references.ts        # Central reference registry
            └── types/
```

---

## Quick Start

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) (v20.10+) and [Docker Compose](https://docs.docker.com/compose/) (v2.0+)
- ~4 GB free disk space (images + dependencies)
- For full splice analysis: GRCh38 reference genome FASTA (~3 GB compressed)

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
2. Build the **FastAPI backend** &mdash; installs Python dependencies + samtools, runs Alembic migrations, downloads the MANE GFF3 annotation file, then starts Uvicorn on port 8000
3. Build the **Next.js frontend** &mdash; installs npm packages, starts the dev server on port 3000
4. The GRCh38 FASTA is **not** downloaded by the backend. Provision it once with `bash rmats-viz/data/setup_grch38_fasta.sh` (see below); the backend only logs at startup whether the FASTA, its `.fai` index and `samtools` are available, and picks the files up as soon as they exist (no restart needed).

**3. Open the application**

| Service | URL |
|---------|-----|
| Frontend (UI) | http://localhost:3000 |
| API docs (Swagger) | http://localhost:8000/docs |
| Health check | http://localhost:8000/api/v1/health |
| FASTA diagnostics | http://localhost:8000/api/v1/debug/fasta |

> **Note:** The application runs without the FASTA &mdash; size-based features, MANE frame annotation, and all non-sequence features will still work. Sequence-dependent features (donor/acceptor sequences, PPT, branch-point, hnRNP motif scan) require the FASTA.

### GRCh38 FASTA Setup

The splice-site analysis requires a locally indexed GRCh38 FASTA mounted at `/data/GRCh38.fa` inside the backend container (mapped from `rmats-viz/data/` on the host).

The backend never downloads the genome itself (the former in-process background download has been removed). Provision it once, on the host, before or after starting the stack:

```bash
cd rmats-viz/data

# Option A: Use the provided setup script
bash setup_grch38_fasta.sh

# Option B: Manual download from NCBI (~800 MB compressed, ~3 GB decompressed)
wget https://ftp.ncbi.nlm.nih.gov/genomes/all/GCA/000/001/405/GCA_000001405.15_GRCh38/seqs_for_alignment_pipelines.ucsc_ids/GCA_000001405.15_GRCh38_no_alt_analysis_set.fna.gz
gunzip GCA_000001405.15_GRCh38_no_alt_analysis_set.fna.gz
mv GCA_000001405.15_GRCh38_no_alt_analysis_set.fna GRCh38.fa

# Index (inside the running container if no local samtools)
docker compose exec backend samtools faidx /data/GRCh38.fa
```

Both UCSC (`chr1`, `chr2`, ...) and RefSeq (`NC_000001.11`, ...) header naming conventions are supported: the backend auto-detects the style from the `.fai` index and converts rMATS UCSC names to RefSeq accessions when needed.

#### Verify FASTA setup

```bash
curl http://localhost:8000/api/v1/debug/fasta
```

Expected response: `fasta_exists: true`, `fai_exists: true`, `faidx_test_rc: 0`. The response also reports `samtools_on_path` and `setup_script` (the provisioning script to run when something is missing).

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
| `MANE_GFF3` | `/data/MANE.GRCh38.ensembl_genomic.gff.gz` | Local MANE GFF3 annotation file |
| `SVG_EXPORT_DIR` | *(unset)* | Optional directory where the deep-analysis PDF export also writes every figure as a standalone SVG (one sub-directory per deep analysis). Unset (default) &rarr; no SVG side files are written |

> **MANE cache behavior:** Successful Ensembl lookups are cached in `mane_cache.db` (SQLite with WAL journal mode) to avoid repeated API calls. Failed lookups (network errors, no MANE transcript found) are **not** cached there and are retried on the next compute run; the per-event endpoint (`GET /splice/feature/{id}`) additionally retries a missing MANE annotation at most once per 24 h, using the feature row's `computed_at` as a negative-result timestamp.

> **Compute state columns:** the splice-feature background computation persists its state in the `analyses` table (`compute_status` = `idle` | `running` | `done` | `error`, plus `compute_error`) rather than in process memory, so progress polling and the export readiness check are correct with several Uvicorn workers and after a crash. On startup any analysis left in `running` is reset to `error` ("interrupted by restart").

---

## Usage Guide

### Creating an Analysis

1. Navigate to the **New Analysis** page (`/analyses/new`)
2. Drag and drop one or more rMATS output files (e.g., `SE.MATS.JC.txt`, `A5SS.MATS.JCEC.txt`)
3. The event type and the counting mode (JC / JCEC) are inferred from the `<TYPE>.MATS.<JC|JCEC>.txt` token of the filename (the upload zone shows a badge for each); files whose name is uninformative are classified from their header by the backend
4. Define sample group names for your conditions
5. Click **Create** &mdash; the parser ingests the TSV, filters low-coverage events (&lt;10X), deduplicates with the per-type rules of [§2](#2-ingestion-deduplication), and stores events in PostgreSQL. The response reports the number of rows actually inserted and any `warnings`, which the upload page displays before opening the analysis

### Browsing Events

The event browser (`/analyses/{id}`) provides a fully interactive table with:

- **Column sorting** &mdash; Click the FDR, gene symbol or |&Delta;&Psi;| header to sort ascending/descending; sorting is performed once, server-side (`sort_by` / `sort_dir`), there is no additional client-side re-ordering of the current page
- **Filters** &mdash; Event type selector, gene symbol search, FDR max, P-value max, minimum |&Delta;&Psi;|
- **Pagination** &mdash; Configurable page size
- **Direction-of-effect badges** &mdash; Visual indicators for exon skipping vs. inclusion

### Deep Splice Analysis

The deep analysis page (`/analyses/{id}/deep-analysis`) enables a two-group partitioning of SE events for comparative analysis. The workflow is:

**1. Create a deep analysis** &mdash; Set FDR and |&Delta;&Psi;| thresholds (and, optionally, a p-value maximum, which is now applied when tagging events) to partition events into significant and non-significant groups. Each configuration is saved as a named deep analysis object (with the requested `permutation_iterations`, when supplied) and can be reopened later.

**2. Explore the results** via the sidebar navigation:

| Tab | Content |
|-----|---------|
| **Annotated Events** | Cards for the significant events only, with full per-event annotations (see below); loaded page by page from the paginated events endpoint |
| **Interactions** | STRING-DB interactions between the analysis' mutated genes and the significant-event genes (when the `stringdb` module is enabled) |
| **Splice** | Pattern comparison panel: side-by-side aggregate statistics for significant vs. non-significant groups (logos, GT-AG rates, PPT scores, frame breakdown), with statistical tests |
| **Motifs** | IUPAC recurrent motif analysis across SE events |
| **hnRNP** | hnRNP motif enrichment analysis — presence / density table over seven regions and protein × region heatmap |
| **Enrichr** | Pathway enrichment results across five gene-set libraries |

#### Annotated Events

Each significant SE event is displayed as a card containing:

- **SpliceView** &mdash; Schematic of the splicing event with inclusion/exclusion levels per sample group
- **ExonDiagram** &mdash; Interactive exon-intron diagram annotated with donor/acceptor sites, PPT window, and branch-point position
- **SpliceSiteTrack** &mdash; All four SE splice sites (upstream donor, skipped 5'SS, skipped 3'SS, downstream acceptor) with sequence and canonical check
- **Sequence source badge** &mdash; Indicates whether sequences were extracted from the local GRCh38 FASTA or the Ensembl REST fallback
- **Gene annotation tabs** &mdash; PanelApp disease panels, GO terms, and UniProt function summary for the host gene
- **ScienceNote** &mdash; Collapsible citation widgets linking each algorithm to its primary literature

> **PermutationPanel** (per-event empirical |ΔΨ| p-values with null-distribution histogram; iteration slider 50–2 000 in steps of 50, used only for the Monte-Carlo path — designs with ≤ 5000 label splits are enumerated exactly and flagged with an *exact* badge; the panel also shows the fraction of exact tests, the replicate design and the minimum attainable p-value) is a separate panel available across several deep analysis tabs, not embedded in individual event cards. The PDF report runs the test at 50, 100, 250 and 500 iterations.

#### hnRNP Motif Panel

- Filterable table of motif–region associations ranked by the smaller of the two adjusted p-values (presence z-test q and density Mann-Whitney q are both shown)
- Toggle: significant only (either test q &lt; 0.05) vs. all 133 (19 motifs × 7 regions) combinations
- Protein and region drop-downs for focused exploration
- Heatmap: protein family × genomic region, colour-coded by enrichment direction (red = enriched in significant, blue = depleted)

#### Enrichr Panel

- Results grouped by library (KEGG, GO BP, GO MF, Reactome, WikiPathways)
- Sortable by adjusted p-value or combined score
- Library filter drop-down

### Gene Annotations

Search for any gene by HUGO symbol using the Ensembl-backed autocomplete. The annotation panel fetches and displays:

- **PanelApp** &mdash; Disease panels and confidence level (green = diagnostic grade)
- **Gene Ontology** &mdash; Top 3 terms per category (BP, MF, CC)
- **UniProt** &mdash; Reviewed protein function summary

### Exporting Results

#### Excel Export (Deep Analysis only)

Excel export is available exclusively from the **Deep Analysis** page. It exports only the significant events tagged in the deep analysis, enriched with optional external annotations.

1. Open a deep analysis and click the **Export Excel** button
2. A modal lets you select which column groups to include:

| Group | Columns | Source |
|-------|---------|--------|
| `core` *(always)* | Gene, Event type, Strand, Exon/Intron sizes, FDR, &Delta;&Psi;, Read counts, Frame class | Local DB |
| `panelapp` | PanelApp Confidence, PanelApp Panels (top 3) | PanelApp REST API |
| `go` | GO:BP, GO:MF, GO:CC (top 3 terms each) | mygene.info |
| `stringdb` | STRING Max Score (highest combined score vs. all mutated genes) | STRING-DB v12 |

3. Optional groups are fetched concurrently (semaphore-limited to 20 parallel requests); PanelApp lookups are capped at 25 s total to handle slow endpoints gracefully
4. The resulting `.xlsx` file includes styled headers, row banding, and auto-sized columns
5. Boolean feature columns (`donor_is_gt`, `acceptor_is_ag`, `bp_motif_found`) are stored as native Excel booleans — their display (`TRUE`/`FALSE` or locale equivalents) depends on your Excel locale setting

#### PDF Export

Click the **Export PDF** button to open the **section selector modal**, which lets you toggle individual report sections on or off before generating. The report can include:

| Section | Content |
|---------|---------|
| Summary | Analysis metadata, event counts, thresholds |
| Significant Events | Per-event table with splice features, GT-AG rate, frame class, PSI values |
| Comparison Logos | Frequency-mode donor and acceptor logos: significant vs. non-significant (when deep analysis present) |
| Frame Breakdown | Pie charts of in-frame / frameshift / non-coding proportions per group |
| Permutation Test | Percentage of significant events at p &lt; 0.05 / 0.01 for K = 50, 100, 250 and 500 iterations, fraction of exactly enumerated tests, replicate design and minimum attainable p-value (when deep analysis present) |
| hnRNP Enrichment | Top 30 motif–region associations significant in at least one test (presence or density, BH q &lt; 0.05), with both q-values (when deep analysis present) |
| Pathway Enrichment | Top 10 terms per library; overlap shown as `k/n`; adjusted p-values &lt; 0.05 are **bolded and starred (★)** for quick identification (when deep analysis present) |
| Summary Schematic | Landscape-page exon-intron architecture diagram with consensus splice-site sequences, PPT, branch-point, in-frame %, intron sizes, mean ΔΨ, and per-feature significance markers (★) (when deep analysis present) |
| Appendix A | Pipeline methodology (see below) |
| Appendix B | Bibliographic references — entries `[1]`–`[10]` are always emitted (one per citation in the always-on sections) and `[11]`–`[28]` are appended only when the hnRNP enrichment panel is selected. See `HNRNP_REMOVED_REFERENCES.md` for the canonical list of conditional entries |
| Appendix C | Statistical methods |
| Closing note | Italicised paragraph pointing to the SpliceAnalyzer repository for full documentation and methodology |

The **Appendix A — Pipeline Methodology** section of the PDF covers:

1. **Input preprocessing** — Coverage filtering (≥ 10X mean junction coverage per group) and boundary-based deduplication of SE events (events sharing at least one boundary within ±50 bp are collapsed by retaining the lowest-FDR event; see [§2](#2-ingestion-deduplication) for the rules applied to the other event types)
2. **Splicing event detection** — rMATS likelihood-ratio test, JC vs JCEC modes
3. **Splice site annotation** — 5'SS/3'SS window extraction, GT-AG canonical check (truncated windows reported as unknown), PPT scoring, branch-point yUnAy / YNYURAY search (branch adenosine mandatory, candidates restricted to 18–44 nt upstream of the exon start, distance measured from the branch A)
4. **Sequence logos** — Frequency-mode PWM rendering (no information-content scaling)
5. **Reading frame classification** — MANE Select transcript mapping, in_frame/frameshift/non_coding classes, NMD caveat note (PTC > 50 nt upstream rule)
6. **MANE Select annotation** — Local GFF3 lookup with Ensembl REST fallback, exon boundary correction (overlap and flanking strategies)
7. **Deep analysis** *(when linked)* — Welch's t-test, Mann-Whitney U and two-proportion z-test for group comparison (test counts computed from the panel, BH q-values), permutation testing with exact enumeration or Phipson & Smyth correction
8. **hnRNP motif enrichment** *(when linked)* — rMAPS2-inspired framework, seven genomic regions, 19 motifs, presence z-test and density Mann-Whitney U test, BH FDR correction per test family
9. **Pathway enrichment** *(when linked)* — Enrichr submission and library results

> Sequence logos in the PDF use **frequency mode**: every column fills the full height and letter height is proportional to raw nucleotide frequency, matching the web app display.

---

## Methodology

### 1. Coverage Filtering

On import, each rMATS event is evaluated for read support. For each sample group, the mean per-replicate junction coverage is computed over the **available** replicates:

```
coverage = mean(IJC_i + SJC_i)   for all replicates i in the group whose IJC_i and SJC_i are both parseable
```

- Replicates whose IJC or SJC entry is `NA` / unparseable are ignored rather than causing the row to be dropped
- When the IJC and SJC lists have different lengths, only the first `min(len)` pairs are used (the number of such rows is logged)
- Rows where a group has **no** parseable replicate at all are dropped and counted as `missing_counts`; rows where either group has `coverage < 10` are dropped and counted as `low_coverage` — the two counts are reported separately in the import log
- When the four count columns are absent altogether (annotation-only `fromGTF.*` files) the filter is skipped explicitly

This threshold prevents low-confidence events from inflating significant hit lists and is applied once at ingestion time.

### 2. Ingestion Deduplication

Event deduplication runs in a single, **type-aware** stage during TSV ingestion (`parser.py`). Within each (event type, gene, chromosome, strand) group, events are processed in order of increasing FDR (missing FDR last; ties broken by largest |ΔΨ|) and a candidate is dropped when it is a near-duplicate of an already kept event according to the rule of its type:

| Event type | Rule | Rationale |
|------------|------|-----------|
| **SE** | Skipped-exon start within ±50 bp **OR** skipped-exon end within ±50 bp of a kept event | Intentionally conservative: two exons sharing one boundary but differing by more than 50 bp on the other are still collapsed |
| **RI** | Both boundaries of the retained-intron exon within ±50 bp (**AND**) | `exon_start` / `exon_end` describe the whole retained-intron exon; a single shared boundary is not evidence of the same event |
| **MXE** | All four boundaries (first **and** second exon start/end) within ±50 bp (**AND**) | A different second exon is a distinct event |
| **A3SS / A5SS** | Exact identity of the full (`long_exon_start`, `long_exon_end`, `short_es`, `short_ee`, `flanking_es`, `flanking_ee`) tuple only | The two alternative sites differ by construction at one boundary, often by a few nt (NAGNAG = 3 nt): only the JC and JCEC versions of the same event are merged |

Rows with a null boundary are always kept for the AND rules. The SE rule uses two sorted lists of kept starts and ends (bisect), the AND rules a sorted list keyed on the first boundary, so the stage is O(n log n) per group. The number of collapsed rows is recorded per event type (`n_collapsed_by_type`) and logged.

A separate exact-coordinate pass is not needed for SE/RI/MXE: identical coordinates are within ±50 bp on every boundary. At insert time the database identity constraint (`analysis_id`, `event_type`, `gene_id`, `chr`, `strand`, the six generic coordinates, `second_exon_start`, `second_exon_end`, `long_exon_start`, `long_exon_end`, `short_es`, `short_ee`) silently skips any remaining exact duplicate, and the upload response counts the rows actually inserted.

> **Methods statement:** Events were deduplicated in a single, type-aware stage within each (event_type, gene_id, chr, strand) group, retaining the event with the lowest FDR (ties broken by the largest absolute ΔΨ). Skipped-exon events sharing at least one boundary (exon start or end) within ±50 bp were collapsed; retained-intron and mutually-exclusive-exon events were collapsed only when all boundaries of the defining exon(s) (both exons for MXE) lay within ±50 bp; alternative 3'/5' splice-site events were collapsed only when the long exon, short exon and flanking exon coordinates were identical, so that alternative sites a few nucleotides apart were kept as distinct events.

### 3. Splice Site Sequence Extraction

Genomic sequences are extracted using `samtools faidx` from a locally indexed GRCh38 FASTA. Coordinates follow the rMATS/BED convention (0-based start, exclusive end); these are converted to the 1-based inclusive format expected by samtools.

For performance at scale (up to 120 k events), extraction uses a single batched subprocess call per chunk:
- All regions for a batch of events are passed as positional arguments to one `samtools faidx` invocation
- Chunks are capped at **5 000 regions per call** to stay within the Linux ARG_MAX (~2 MB) limit
- Timeout per chunk: `max(30, chunk_size // 100)` seconds
- **Chunk-halving retry** — when samtools rejects a chunk (`CalledProcessError`), the chunk is split in halves and retried recursively down to single regions, so only the offending regions are blanked (they are logged); previously one invalid region blanked the whole 5 000-region chunk
- **Empty-record safety** — `samtools faidx` emits a header with no sequence for a region beyond the contig end; the parser appends one sequence per header (including empty ones) so the i-th sequence always belongs to the i-th region, and blanks the chunk if the record count does not match the request count instead of returning shifted sequences
- **Negative-start clamp** — a region starting before position 0 (exon close to the contig start) is clamped to 0 (the returned window is then shorter than requested); `end <= start` or an unknown contig yields an empty string

Chromosome name translation is handled automatically: rMATS uses UCSC names (`chr1`–`chr22`, `chrX`, `chrY`, `chrM`), while some FASTA files use RefSeq accessions (`NC_000001.11`…). The backend reads the `.fai` index on first use (re-read while empty, so a FASTA provisioned after startup is picked up) and translates names as needed. When the FASTA is unavailable, sequences are fetched per-event from the Ensembl REST API as a fallback.

The five window intervals (donor, acceptor, PPT, upstream donor, downstream acceptor; see [§4](#4-splice-site-signals)) are defined once in the pure function `splice_window_coords()`, which the batched FASTA path, the per-event FASTA path and the Ensembl fallback all share, so the three paths cannot drift apart.

For minus-strand events, extracted sequences are reverse-complemented before all downstream analyses; the complement table covers the full IUPAC alphabet (`ACGTU RYSWKM BDHV N`, upper and lower case), so ambiguity codes in the reference are not passed through unchanged.

#### MANE Exon Boundary Correction

rMATS exon coordinates come from the alignment annotation (GTF), which can differ from the **MANE Select** transcript boundaries. When this happens, splice-site sequences may be extracted at the wrong genomic position — for example, the 3'SS acceptor of a minus-strand exon can be shifted by tens of nucleotides. To correct this, the pipeline looks up the corresponding MANE exon and uses its boundaries for splice-site window extraction. Two strategies are applied in order:

1. **Overlap matching** — The MANE exon with the largest reciprocal overlap (≥ 50% of both the rMATS and MANE exon sizes) is selected. This is the primary strategy and works for the vast majority of events.

2. **Flanking-based fallback** — When overlap matching fails (e.g. the rMATS exon coordinates diverge too far from MANE), the pipeline identifies the MANE exon that lies between the upstream and downstream flanking exon boundaries (`upstream_EE` .. `downstream_ES`). These flanking boundaries come from junction reads and are always accurate. The MANE exon contained within this interval is the consensual skipped exon. If multiple MANE exons fall in the interval, the one closest in size to the rMATS exon is chosen.

Only the **skipped-exon** splice-site windows (donor, acceptor, PPT) are corrected. Flanking exon windows remain at their original coordinates because their boundaries are defined by junction reads (always accurate).

The correction method used per event is tracked in the `mane_exon_source` field:
- `"overlap"` — standard reciprocal overlap matching
- `"flanking"` — flanking-based fallback (rMATS coordinates differ from MANE)
- `null` — no MANE correction applied (rMATS coordinates used as-is)

Events corrected via the flanking fallback are listed in the PDF report with a warning that their rMATS coordinates differed from the MANE Select transcript.

### 4. Splice Site Signals

For each SE event, five sequence windows are defined around the skipped exon:

| Window | Coordinates (+ strand) | Length |
|--------|------------------------|--------|
| Donor (5'SS) | `exon_end − 3` .. `exon_end + 6` | 9 nt (3 nt exon + GT + 4 nt intron) |
| Acceptor (3'SS) | `exon_start − 20` .. `exon_start + 3` | 23 nt (20 nt intron + AG + 3 nt exon) |
| PPT | `exon_start − 50` .. `exon_start − 3` | 47 nt upstream of 3'SS |
| Upstream flanking donor | `upstream_EE − 3` .. `upstream_EE + 6` | 9 nt |
| Downstream flanking acceptor | `downstream_ES − 20` .. `downstream_ES + 3` | 23 nt |

The **GT-AG canonical rule** is checked by inspecting positions +1/+2 of the donor window (must be `GT`) and positions −2/−1 of the acceptor window (must be `AG`). The boolean flags `donor_is_gt` and `acceptor_is_ag` are stored per event.

### 5. Polypyrimidine Tract (PPT)

Two metrics are computed on the 47 nt PPT window:

- **PPT score** — fraction of C or T nucleotides in the window: `(count_C + count_T) / len(window)`
- **Longest pyrimidine run** — length of the longest uninterrupted C/T stretch

Both metrics are reported as splice-site quality indicators and are included in the pattern comparison statistics between significant and non-significant event groups.

### 6. Branch-Point Detection

The branch-point adenosine is identified by scanning the PPT window (47 nt, `[exon_start − 50, exon_start − 3)`) for the 7-mer **YNYTRAY** — the human branch-point consensus **yUnAy** (Gao et al., 2008) extended to 7 nt, i.e. YNYURAY with U → T in genomic DNA (Y = C/T; N = any; R = A/G). Each 7-mer receives a **positional score** (0–7): one point for each position that matches the consensus (the N position always matches). Two constraints are applied before scoring:

1. **The branch adenosine is mandatory** — position 6 of the 7-mer (0-based index 5) must be an `A`; a candidate without it is never reported, whatever its score.
2. **Distance window** — the distance from the branch A to the exon start (the 3'SS `AG` boundary) is computed as `(len(ppt_seq) + 3) − (i + 5)` (the PPT window ends 3 nt before the exon), and only candidates whose branch A lies **18–44 nt** upstream of the exon start are considered (> 95 % of human branch points map to −18…−44; Leman et al., 2020; see also Mercer et al., 2015).

Among the remaining candidates the highest score wins; ties are broken in favour of the candidate **closest to the 3'SS**. A branch point is called (`bp_motif_found`) when the best candidate scores ≥ 5/7.

| Output | Description |
|--------|-------------|
| `bp_motif_found` | `True` if a candidate with an `A` at the branch position, within the 18–44 nt window, scores ≥ 5 |
| `bp_score` | Best positional score (0–7) |
| `bp_distance` | Distance (nt) from the **branch adenosine** to the exon start (3'SS); `null` when no branch point is called |
| `bp_position` | 0-based index of the matched 7-mer in `ppt_seq` (`null` when not found) |
| `bp_motif` | The matched 7-mer (`null` when not found) |

### 7. MANE Select Frame Classification

Each skipped exon is mapped to its **MANE Select** transcript (the clinically validated representative transcript per gene, from the MANE consortium). The lookup uses a two-tier approach:

1. **Local GFF3** — If `MANE.GRCh38.ensembl_genomic.gff.gz` is present, it is parsed directly with `gzip` (fast, no network, no tabix index required). Transcripts are indexed by the GFF3 `tag=` attribute: the transcript tagged `MANE_Select` is the one used for annotation, while `MANE_Plus_Clinical` transcripts are kept in a separate index (`get_mane_plus_clinical`) so that a Plus Clinical transcript listed first in the file can no longer be picked by mistake. Genes with no `MANE_Select` tag at all (old files) fall back to the first transcript seen, with a warning
2. **Ensembl REST API** — Fallback when the GFF3 is unavailable; queries `/lookup/id/{gene_id}` + `/overlap/id/{transcript_id}` for exon and CDS features. `overlap/id/{tx}?feature=cds` returns the CDS of **every** transcript overlapping the span, so the CDS features are filtered by their transcript `Parent` before use

In both paths the coding length of the exon is the sum of its overlaps with the **union** of the transcript's CDS segments (merged intervals), not with the CDS span from the first to the last CDS base.

The exon is classified (`frame_class`) by its relationship to the CDS:

| Class | Condition |
|-------|-----------|
| `in_frame` | CDS-overlapping exon length divisible by 3 (exon fully or partially within CDS) |
| `frameshift` | CDS-overlapping exon length not divisible by 3 (exon fully or partially within CDS) |
| `non_coding` | Exon entirely within UTR or no CDS overlap |
| `unknown` | No MANE Select transcript found or lookup failed |

> **No heuristic fallback:** When MANE annotation is unavailable, frame_class is set to `unknown` without attempting an `exon_size % 3` heuristic. Without transcript annotation, it is impossible to distinguish CDS exons from UTR exons, so applying the divisibility rule would misclassify non-coding exons as `in_frame` or `frameshift`. The conservative `unknown` label is intentional.

A companion `frame_region` field records the positional context: `CDS` (the exon is entirely covered by CDS segments), `partial` (any part of the exon lies outside the CDS union — beyond its span or in a gap between segments), `UTR5` / `UTR3` (no CDS overlap; side chosen with respect to transcript strand), `non_coding` (the transcript has no CDS at all), or `unknown`. Events with `frame_region = partial` still receive an `in_frame` or `frameshift` classification based on the coding portion of the exon length.

Results are cached in a local SQLite database with WAL journal mode to support concurrent access.

> **NMD caveat:** A `frameshift` classification does not imply nonsense-mediated decay (NMD). NMD depends on the position of the premature termination codon (PTC) relative to the last exon-exon junction (the "> 50 nt upstream" rule). The application displays this as an informational note in both the UI and the PDF methodology appendix — it is **not** a computed NMD prediction. Experimental validation is required to confirm NMD susceptibility.

### 8. Permutation Testing

A permutation test assesses the significance of |&Delta;&Psi;| for each SE event by testing whether the observed group difference is larger than expected by chance:

1. Per-sample PSI values are read from `IncLevel1` / `IncLevel2` (NA replicates dropped; n<sub>1</sub> and n<sub>2</sub> valid replicates) and pooled. There are `N = C(n1 + n2, n1)` distinct ways of splitting the pool into groups of size n<sub>1</sub> and n<sub>2</sub>
2. **Exact enumeration** — when `N ≤ 5000` (e.g. any design up to 7 vs 7 replicates), *all* label splits are enumerated and the null distribution is the complete set of permuted ΔΨ values. The two-tailed p-value is `p = r / N`, where `r` is the number of splits whose |ΔΨ| ≥ the observed |ΔΨ|. No +1 correction is needed: the observed split is one of the enumerated ones, so `r ≥ 1` and `p ≥ 1/N`. With 2 vs 2 replicates there are only 6 splits (minimum p ≈ 0.167), with 3 vs 3 there are 20 (minimum p = 0.05): the resolution is limited by the design, not by the number of iterations
3. **Monte-Carlo** — otherwise, `K` random label splits are drawn (numpy, vectorised) and the empirical two-tailed p-value uses the **Phipson & Smyth (2010)** correction `p = (r + 1) / (K + 1)`; the minimum attainable p is `1 / (K + 1)`

The result reports, per event, `exact` and `n_splits`, and globally `exact_fraction` (fraction of tested events on the exact path), `min_p_attainable` (smallest p the most common replicate design can produce) and `n_replicates_g1` / `n_replicates_g2` (mode of the replicate counts). The UI iteration slider (50–2 000, step 50) only affects the Monte-Carlo path; the PDF report runs the test at K = 50, 100, 250 and 500 and prints the four rows (identical when every event is enumerated exactly).

**Sign convention:** ΔΨ = mean(PSI<sub>group1</sub>) − mean(PSI<sub>group2</sub>), consistent with rMATS `IncLevelDifference`. The null distribution is built with the same group-ordering convention, so the sign is preserved and the two-tailed test compares |ΔΨ<sub>obs</sub>| against |ΔΨ<sub>null</sub>|.

**Observed ΔΨ:** the value *displayed* (`observed_delta_psi`, and the observed histogram) is rMATS' `IncLevelDifference` when present, i.e. the same number shown everywhere else in the application; the *test statistic* is always recomputed from the replicate values that feed the null distribution, so the observed labelling is exactly one of the enumerated splits. Events where either group has no valid PSI value are skipped.

**Memory:** the global null-distribution histogram is accumulated as 40 fixed-edge bin counts on [−1, 1] while events are processed; the individual permuted values are never kept (120 k events × 500 iterations would be 60 M floats).

When FDR and |&Delta;&Psi;| filters are applied in the deep analysis view, the **Sig. p&lt;0.05** and **Sig. p&lt;0.01** percentages are recomputed exclusively over the filtered event subset, ensuring the values shown in the UI and PDF report are always consistent with each other.

### 9. Sequence Logos

Position Weight Matrices (PWMs) are computed from all extracted sequences per group. Logos are rendered in **frequency mode** (matching the web app display):

```
height(b, i) = f(b, i) × H_logo
```

where `f(b, i)` is the raw nucleotide frequency of base `b` at position `i` and `H_logo` is the fixed column height. Every column fills the full height, making all positions directly comparable regardless of conservation. No information-content (bits) scaling or small-sample correction is applied.

**Base colours:** A = green (#22c55e), C = blue (#3b82f6), G = orange (#f97316), T = red (#ef4444). Canonical GT (+1/+2) and AG (−2/−1) positions are highlighted in yellow.

### 10. hnRNP Motif Enrichment

Inspired by rMAPS2 (Hwang et al., 2020), this module tests whether known hnRNP binding motifs are enriched in the genomic regions flanking significant vs. non-significant SE events.

#### Genomic regions

Seven regions are extracted per event, in transcript order, following the rMAPS2 design of scanning **both ends of each flanking intron** (250 nt after its 5'SS and 250 nt before its 3'SS), with exclusion zones at the splice signals (first 6 nt after the 5'SS = GURAGU donor signal; last 20 nt before the 3'SS = branch point / PPT / AG zone):

| # | Region | Extraction rule | Max length |
|---|--------|----------------|------------|
| 1 | `upstream_exon` | Last 250 nt of the upstream flanking exon (intron-proximal end) | 250 nt |
| 2 | `upstream_intron_5ss` | Upstream intron, 5'SS side: `[5'SS + 6, 5'SS + 6 + 250)` clipped at `3'SS − 20` | 250 nt |
| 3 | `upstream_intron_3ss` | Upstream intron, 3'SS side: `[3'SS − 20 − 250, 3'SS − 20)` clipped at `5'SS + 6` (the PPT / PTB / hnRNP C territory immediately upstream of the skipped exon) | 250 nt |
| 4 | `skipped_exon` | Full exon body | variable |
| 5 | `downstream_intron_5ss` | Downstream intron, 5'SS side (after the skipped exon's donor), same rule as 2 | 250 nt |
| 6 | `downstream_intron_3ss` | Downstream intron, 3'SS side (before the downstream exon's acceptor), same rule as 3 | 250 nt |
| 7 | `downstream_exon` | First 250 nt of the downstream flanking exon (intron-proximal end) | 250 nt |

The regions are computed in genomic coordinates (on the − strand the 5'SS of every intron is at its genomic high end and the windows are mirrored) and minus-strand sequences are reverse-complemented before scanning.

> **Short introns**
>
> The two windows of one intron are clipped to the intron body minus the two exclusion zones. For introns shorter
> than 6 + 250 + 250 + 20 = **526 nt** the 5'SS and 3'SS windows therefore **overlap** (the same nucleotides are
> scanned in both windows; e.g. a 300-nt intron gives two 250-nt windows sharing 226 nt). This is intentional and
> mirrors rMAPS2, which also scans each intron end independently; the two windows of one intron are not
> independent tests and should be read together.
>
> After applying both exclusion zones (6 nt + 20 nt = **26 nt total**), an intron that is **≤ 26 nt** long yields
> **no extractable sequence** for either of its windows. Such events are silently excluded from those intronic
> regions only — they still contribute to all exonic region analyses. This behaviour is identical to rMAPS2.
>
> **Practical consequence:** the effective sample size *N* reported in each cell of the hnRNP result table
> can be lower than the total number of SE events. If you observe, for example, that an upstream or
> downstream intron window N is substantially smaller than the total event count, it means a fraction of events
> have very short flanking introns (or missing flanking exon coordinates) that provide no scannable
> intronic sequence. This is expected and not a software error.

#### Motif catalogue

19 consensus motifs for 8 hnRNP protein families (RNA U → DNA T for genomic scanning):

| Protein | Motifs | Basis |
|---------|--------|-------|
| hnRNP A1/A2 | TAGG, TAGGG, TAGGGA, AGG | CISBP-RNA; Martinez-Contreras et al. (2006) |
| hnRNP E1 (PCBP1) | CCWWHCC `[CC[AT][AT][ACT]CC]` | rMAPS2 Suppl. Table S2, Homo sapiens (ENSG00000169564); Chkheidze et al. (1999); Makeyev & Liebhaber (2002) |
| hnRNP E2 (PCBP2) | CCYYCCH `[CC[CT][CT]CC[ACT]]` | rMAPS2 Suppl. Table S2, Homo sapiens (ENSG00000197111) |
| hnRNP F/H | GGGG, GGG | G-quadruplex / G-run binding |
| hnRNP K | CCCC, TCCC | Poly-C binding |
| hnRNP C | TTTTT, TTTT | Poly-U/T binding |
| hnRNP L | CACA, ACAC | CA-repeat binding |
| hnRNP M | TGTG, GTGT | GU-rich elements |
| PTB (hnRNP I) | TCTT, TCTCT, CTCT | UCUU/UCUCU consensus |

#### Statistical tests

For each of the 133 (19 motifs × 7 regions) pairs, **two** complementary tests are run between the significant and background groups:

1. **Presence test** — the **hit rate** (fraction of events with ≥ 1 motif occurrence, binary) is compared with a **standard pooled two-proportion z-test** (large-sample normal approximation). It is run only when both groups contain **at least 5 events** with a non-empty region and the pooled proportion is neither 0 nor 1 (`z_stat`, `p_value`, `p_adjusted`, `significant`)
2. **Density test** — the per-event **motif density** (overlapping occurrences × motif length / region length, capped at 1; 0 when the motif is absent) is compared with a two-sided **Mann-Whitney U test** (mid-ranks, normal approximation with tie-corrected variance and a 0.5 continuity correction as in R's `wilcox.test` / SciPy `use_continuity=True`, same ≥ 5 events per group requirement; when every pooled value is tied the pair is not testable). Presence saturates for short motifs (AGG, GGG, TTTT, CTCT are present in almost every 250-nt window of both groups), whereas the density still discriminates; rMAPS2 uses the same rank test on per-window densities (`density_u_stat`, `density_p_value`, `density_p_adjusted`, `density_significant`)
3. **Benjamini-Hochberg FDR correction** (step-up procedure) is applied **separately to each family** of raw p-values across all testable (motif × region) pairs, on the unrounded p-values; adjusted q-values are enforced monotone by a cumulative-minimum scan from largest rank back to smallest
4. A pair is reported as **significant when either test** has q < 0.05 — this is a **discovery-oriented screen**, not a confirmatory test in the strict FWER sense; BH FDR controls the expected proportion of false discoveries rather than the family-wise error rate

Mean motif density is also reported per group (`sig_density`, `bg_density`), and each result carries the established regulatory effect of the protein family in that zone (`regulatory_effect`: ESE / ESS / ISE / ISS or `null`; the label of an intron applies to both of its windows).

#### Key differences vs. rMAPS2

| Aspect | rMAPS2 | SpliceAnalyzer |
|--------|--------|----------------|
| Test statistic | Wilcoxon rank-sum on per-window density | Two tests per pair: two-proportion z-test on binary presence **and** Mann-Whitney U on per-event density |
| Resolution | Nucleotide-level sliding window (50 nt) | Seven discrete genomic sub-regions (both ends of each flanking intron, per the rMAPS2 region design) |
| Correction | Per-comparison | Benjamini-Hochberg FDR (q &lt; 0.05) per test family across all 133 pairs; significant if either q &lt; 0.05 |
| Minimum group size | — | ≥ 5 events per group for both tests |
| Groups | Up-regulated, down-regulated, background | Significant, non-significant |

#### Performance

The scan is optimised for large datasets (tested at 120 k events):
- Events-outer loop (single pass, cache-local access to each `SERegions` object)
- Sequences are guaranteed uppercase from the FASTA parser; no redundant `.upper()` calls
- `compiled.search` early exit: the overlapping-occurrence count is only computed for hits (~50–80% skip rate); misses append a shared `0.0` density
- Flat pre-allocated accumulators (one hit counter and one density list per motif × region cell); per-event densities are kept because the density test is rank-based

### 11. Pathway Enrichment (Enrichr)

Unique HGNC gene symbols from significant events are submitted to the **Enrichr REST API** (Ma'ayan Lab). The workflow:

1. POST gene list to `/addList`
2. GET enrichment for each of five libraries:

| Library | Focus |
|---------|-------|
| KEGG 2021 Human | Metabolic and signalling pathways |
| GO Biological Process 2023 | Biological functions |
| GO Molecular Function 2023 | Molecular activities |
| Reactome 2022 | Curated human pathways |
| WikiPathways 2023 Human | Community-annotated pathways |

3. Return top 10 terms per library by adjusted p-value (the PDF report also shows the top 10)

The **overlap** of each term is reported as `k/n`, where `k` is the number of submitted genes in the set and `n` the size of the gene set. Because the `/enrich` endpoint does not return set sizes, `n` is read from the library GMT (`GET /geneSetLibrary?mode=text&libraryName=…`), fetched **once per library per process** and cached (a failed fetch is cached as empty so it is not retried on every run); when the size is unknown only `k` is shown. The term name is never parsed for the size (GO terms end with their GO id, KEGG terms have no parenthesis).

The **combined score** = log(p) × z (Chen et al., 2013), where log is the natural logarithm, p is the unadjusted Fisher's exact test p-value for overlap, and z is Enrichr's deviation-from-expected-rank z-score. Adjusted p-values are reported separately by Enrichr within each library.

All Enrichr HTTP calls are issued inside `asyncio.to_thread` to avoid blocking the event loop. The five library GETs are dispatched in parallel (one thread per library via `ThreadPoolExecutor`), so total network time is ~1× latency rather than 5×.

### 12. Pattern Comparison (Sig vs Non-Sig)

The pattern comparison endpoint computes aggregate splice statistics for both the significant and non-significant event groups, then applies **20 tests** (7 Welch's t-tests + 7 Mann-Whitney U tests + 6 two-proportion z-tests) to the metrics below. Every continuous metric is tested twice — the Welch row is keyed by the feature name, the Mann-Whitney row by `<feature>_mwu`:

| Metric | Tests | Notes |
|--------|-------|-------|
| Mean ΔΨ | Welch's t-test + Mann-Whitney U | Unequal-variance two-sample t-test; rank test on the same values |
| Exon size distribution | Welch's t-test + Mann-Whitney U | |
| PPT score distribution | Welch's t-test + Mann-Whitney U | |
| PPT T content | Welch's t-test + Mann-Whitney U | Fraction of T in the PPT window |
| PPT C content | Welch's t-test + Mann-Whitney U | Fraction of C in the PPT window |
| Upstream intron size (mean) | Welch's t-test + Mann-Whitney U | Both mean and median are computed; the Welch comparison uses the mean |
| Downstream intron size (mean) | Welch's t-test + Mann-Whitney U | |
| GT canonical rate | Two-proportion z-test | k = events with GT, n = events with a ≥ 9 nt donor window **and a known flag** (windows truncated at a contig end have `donor_is_gt = null` and are excluded from numerator and denominator) |
| AG canonical rate | Two-proportion z-test | Same rule with the ≥ 23 nt acceptor window and `acceptor_is_ag` |
| Upstream donor GT rate | Two-proportion z-test | Length ≥ 9 bp guard; unknown flags excluded |
| Downstream acceptor AG rate | Two-proportion z-test | Length ≥ 23 bp guard; unknown flags excluded |
| In-frame proportion | Two-proportion z-test | In-frame events vs. events with a **known** frame class (`unknown` excluded); the frame percentages of the UI and the PDF use the same known-frames denominator and print the number of unknown events beside the bar |
| Branch point found | Two-proportion z-test | k = events with bp match, n = events with a donor sequence |

Welch's t-test and its two-tailed p-value are computed in pure Python (no SciPy) using the Welch-Satterthwaite degrees-of-freedom formula and the numerically evaluated regularized incomplete beta function (Lentz's continued-fraction algorithm). The Mann-Whitney U test uses mid-ranks and the normal approximation with tie-corrected variance and a 0.5 continuity correction (as in R's `wilcox.test` / SciPy `use_continuity=True`). The z-test, the U test, the normal CDF and the BH adjustment are a single shared implementation (`services/stats.py`) used by both this panel and the hnRNP module, so identical inputs give identical statistics. Both the z-test and the U test require **≥ 5 observations per group** (and the U test some non-tied values); otherwise the test is reported with `p_value = null` and is excluded from `m`.

**Multiple testing:** Benjamini-Hochberg q-values are computed across the whole panel (`m` = number of evaluable tests) and returned next to the raw p-values as `q_value`, with `significant_fdr` (q < 0.05) alongside the raw `significant` (p < 0.05) call. The UI shows both; the PDF comparison table lists p and q, marks raw p < 0.05 with ★ and q < 0.05 with †, and states the number of tests computed from the panel rather than a hard-coded figure. The panel remains exploratory: the raw-p criterion is kept for continuity with the interactive view, but q < 0.05 is the criterion to prefer when several features are examined.

**Skewness:** Welch's t-test assumes approximately normal sampling distributions of the mean. Exon sizes and especially intron sizes are typically right-skewed (long-tailed); with small sample sizes the t-test p-values may be inaccurate. The test is reasonably robust to moderate skewness when both groups have n ≥ 30 (by the Central Limit Theorem), but for smaller or heavily skewed groups the Welch p-values should be interpreted with caution. The rank-based **Mann-Whitney U test is implemented** as a companion for every continuous metric and is the one to read for the size distributions.

> **PDF footnote:** The comparison table of the PDF states that continuous features are tested with both Welch's t-test and the Mann-Whitney U test (robust to the right-skew of size distributions) and that proportion tests require ≥ 5 events per group. The same information is in the backend docstring of the pattern-comparison endpoint.

Comparison sequence logos (frequency mode) are generated independently for each group.

### 13. PanelApp Circuit Breaker

PanelApp Australia is occasionally unreachable. A module-level circuit breaker prevents cascade latency in large exports:

- After any `ConnectError` or `ConnectTimeout`, the AU source is placed in a **300-second backoff window**
- Subsequent requests during the window skip AU immediately and go straight to PanelApp UK
- Read/pool timeouts do **not** trigger the circuit breaker (endpoint is live but slow)
- The breaker resets automatically after the backoff period

Connect timeout: 4 s; read timeout: 4 s. For large exports (many unique genes), all PanelApp lookups are additionally capped at **25 s total** via `asyncio.wait`; genes that do not resolve within the cap return empty panel data rather than blocking the export.

**Per-gene cache:** results (including empty ones) are cached in memory per gene symbol for **6 hours** (up to 20 000 entries; the oldest 10 % are evicted when the cap is reached), so an export with one row per event queries PanelApp once per gene. A negative result is cached only when at least one source was actually queried, so a transient backoff is not remembered for 6 h.

---

## Performance

### Splice Feature Computation (`POST /api/v1/splice/compute/{analysis_id}`)

Background task that runs once per analysis. Events are processed in chunks of 2 000 with a single batched samtools call per chunk, and all DB writes use bulk `INSERT … ON CONFLICT DO UPDATE` (one round-trip per 2 000-event chunk).

| Stage | Description | Expected Time |
|-------|-------------|:-------------:|
| Import + parse | DataFrame → dedup → bulk INSERT (500-row batches) | 2–5 s |
| Sequence extraction | 100 k × 5 = 500 k regions, ~100 samtools calls (5 k regions each) | 10–30 s |
| MANE annotation + feature compute | Local GFF3 lookup + per-event arithmetic (parallel, semaphore 20) | 5–15 s |
| DB writes | Bulk upsert, 1 round-trip per 2 000-event chunk | 1–3 s |
| **Total (local FASTA + warm MANE cache)** | | **~20–55 s** |

> If the local MANE GFF3 is missing, each event falls back to the Ensembl REST API (3 calls per event). Ensure `MANE_GFF3` is configured at startup to avoid this.

### Deep Splice Analysis (page load)

Expected wall-clock times when a deep-analysis tab is first opened for a 100 k event analysis:

| Stage | Description | Expected Time |
|-------|-------------|:-------------:|
| Deep analysis creation | Bulk-insert junction rows (5 000-row batches) | <1 s |
| FASTA extraction (hnRNP regions) | 100 k × 7 = 700 k regions, chunked into ~140 × 5 k samtools calls | 60–120 s |
| hnRNP scan | 2 groups × 100 k events × 7 regions × 19 motifs ≈ 27 M inner iterations | 30–60 s |
| Enrichr submission | POST + 5 × GET in parallel (network bound) | 5–10 s |
| DB queries + rest | Pattern stats, frame data, permutation tests | 10–20 s |
| **Total** | | **~2–3 min** |

Both FASTA extraction and the motif scan run inside `asyncio.to_thread`, so the event loop remains responsive during computation.

---

## Internationalisation (i18n)

All user-visible strings are stored in locale dictionaries under `frontend/src/lib/i18n/`:

| File | Locale |
|------|--------|
| `en.ts` | English (default) |
| `fr.ts` | French |

The active locale is managed by `LanguageContext` (`frontend/src/contexts/LanguageContext.tsx`). The `useT()` hook returns a resolver `t(key, vars?)` that:

- Resolves dot-path keys (e.g., `"sidebarNav.tabs.hnrnp"`) against the active locale object
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
| `DELETE` | `/api/v1/analyses/{id}` | Delete analysis and all associated data asynchronously (returns 204 immediately; deletion runs in a background task with explicit ordered deletes; status set to `deleting` during cleanup, reset to `error` on failure) |
| `GET` | `/api/v1/analyses/{id}/events` | Paginated, filterable event list |
| `GET` | `/api/v1/analyses/{id}/events/manhattan` | Lightweight points for the Manhattan plot in natural chromosome order (chr1 … chr22, X, Y, M, then other contigs); all FDR &lt; 0.05 events kept, the rest uniformly sampled above 50 000 points |

The upload response (`UploadResponse`) contains `analysis_id`, `status`, `event_count` (rows actually inserted) and `warnings` (list of human-readable notes, e.g. an empty file or "no events were imported").

**Event query parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `event_type` | string | Filter by type: `SE`, `A5SS`, `A3SS`, `MXE`, `RI` |
| `gene_symbol` | string | Filter by gene symbol (case-insensitive substring match) |
| `fdr_max` | float | Maximum FDR threshold |
| `p_value_max` | float | Maximum P-value threshold |
| `delta_psi_min` | float | Minimum \|&Delta;&Psi;\| threshold |
| `sort_by` | string | Column to sort by: `fdr` (default), `p_value`, `abs_inc_level_diff`, `gene_symbol` |
| `sort_dir` | string | `asc` or `desc` |
| `page` | int | Page number (1-indexed) |
| `page_size` | int | Results per page (default 50, max 200) |

### Deep Analyses

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/analyses/{id}/deep-analyses` | Create a deep analysis (tag events by FDR + ΔΨ thresholds) |
| `GET` | `/api/v1/analyses/{id}/deep-analyses` | List saved deep analyses for an analysis |
| `GET` | `/api/v1/deep-analyses/{deep_id}` | Get a deep analysis by ID |
| `DELETE` | `/api/v1/deep-analyses/{deep_id}` | Delete a deep analysis |
| `GET` | `/api/v1/deep-analyses/{deep_id}/events` | Paginated event list (`{items, total, page, page_size, pages}`, ordered by FDR); query params `significant` (bool filter), `page` (default 1), `page_size` (default 200, max 500) |
| `GET` | `/api/v1/deep-analyses/{deep_id}/pattern-comparison` | Sig vs non-sig group statistics + `statistical_tests` (20 tests with `p_value`, `q_value`, `significant`, `significant_fdr`) |
| `GET` | `/api/v1/deep-analyses/{deep_id}/hnrnp-motifs` | hnRNP motif enrichment results (`regions` in scanning order; per pair presence z-test and density Mann-Whitney fields) |
| `GET` | `/api/v1/deep-analyses/{deep_id}/enrichr` | Enrichr pathway enrichment results (top 10 per library, overlap `k/n`) |

**Deep analysis create body:**

| Field | Type | Description |
|-------|------|-------------|
| `fdr_threshold` | float | FDR cutoff for significance (e.g. `0.05`) |
| `delta_psi_min` | float | Minimum \|&Delta;&Psi;\| (e.g. `0.1`) |
| `pvalue_threshold` | float? | Optional p-value cutoff; when set, an event is significant only if FDR ≤ `fdr_threshold` **and** \|ΔΨ\| ≥ `delta_psi_min` **and** p ≤ `pvalue_threshold` (it is applied in event tagging and shown in the auto-generated name) |
| `name` | string? | Optional name; auto-generated from thresholds + date if omitted |
| `modules` | list[string]? | Modules to enable: `["hnrnp", "enrichr", "stringdb"]` |
| `permutation_iterations` | int? | Permutation iteration count (10–2000) recorded with the deep analysis; stored in `permutation_iterations` and returned by the detail endpoint |

### Splice Site Analysis

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/splice/compute/{analysis_id}` | Start the background computation of splice features for all SE events (202; refused while `compute_status` is `running`) |
| `GET` | `/api/v1/splice/progress/{analysis_id}` | Progress of that computation: `n_se_events`, `n_computed`, `pct`, `done`, `status` (`idle` / `running` / `done` / `error`, mirrors `analyses.compute_status`) and `error` (message when `status = error`). `done` is true when every SE event has features **or** the task is no longer running, even if it failed |
| `GET` | `/api/v1/splice/feature/{event_id}` | Per-event features (computed on-the-fly if not cached; 503 when the server is busy — the client retries) |
| `GET` | `/api/v1/splice/patterns/{analysis_id}` | Aggregate pattern analysis (PWM, consensus, frame stats); query params `fdr_threshold`, `abs_delta_psi_min`, `pvalue_threshold` (optional p-value maximum) or `deep_analysis_id` (restricts to the significant events of that deep analysis) |
| `POST` | `/api/v1/splice/permutation/{analysis_id}` | Permutation test on all SE events; query params `n_iterations` (default 500, clamped to 10–2000, Monte-Carlo path only), `fdr_threshold`, `delta_psi_min`, `pvalue_threshold` (the three thresholds restrict the reported `pct_p05` / `pct_p01` and the observed histogram to the significant subset). Response: per-event `exact` / `n_splits`, and global `exact_fraction`, `min_p_attainable`, `n_replicates_g1`, `n_replicates_g2` |
| `GET` | `/api/v1/splice/mane_transcript/{event_id}` | MANE Select transcript structure for the exon diagram |

> The compute endpoint is **idempotent** &mdash; re-running overwrites existing feature rows. It requires the GRCh38 FASTA for sequence features; if unavailable, size-only features are computed. Its state lives in the database (`compute_status` / `compute_error`), so a task interrupted by a restart is reset to `error` at the next startup and the UI stops polling.

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
| `GET` | `/api/v1/export/{id}/pdf` | Download PDF report (pass `deep_analysis_id` query param to include deep analysis sections) |
| `GET` | `/api/v1/export/{analysis_id}/deep-analysis/{deep_analysis_id}/excel?include=core,panelapp,go,stringdb` | Download Excel for a deep analysis (significant events only); `include` is comma-separated |

### Diagnostics

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/health` | Health check (DB ping) |
| `GET` | `/api/v1/debug/fasta` | FASTA + samtools availability check |

### Example Responses

**`POST /api/v1/analyses`** (multipart upload — returns created analysis):

```json
{
  "analysis_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "ready",
  "event_count": 4523,
  "warnings": []
}
```

**`GET /api/v1/splice/feature/{event_id}`** (per-event splice features):

```json
{
  "event_id": "evt-001",
  "event_type": "SE",
  "gene_symbol": "BRCA1",
  "exon_size": 132,
  "upstream_intron_size": 4521,
  "downstream_intron_size": 8903,
  "donor_seq": "AAGgtaagt",
  "acceptor_seq": "ttttcttttcccccccccagGAA",
  "donor_is_gt": true,
  "acceptor_is_ag": true,
  "ppt_score": 0.72,
  "ppt_longest_run": 9,
  "bp_motif_found": true,
  "bp_distance": 28,
  "bp_score": 6,
  "bp_position": 19,
  "bp_motif": "CTCTAAC",
  "mane_transcript_id": "ENST00000357654.9",
  "frame_class": "in_frame",
  "frame_region": "CDS",
  "fasta_available": true,
  "sequence_source": "fasta",
  "mane_exon_source": "overlap"
}
```

**`GET /api/v1/deep-analyses/{deep_id}/pattern-comparison`** (abbreviated):

```json
{
  "significant": {
    "n_events": 312,
    "n_se_with_features": 298,
    "exon_size_mean": 142.5, "exon_size_median": 120.0,
    "upstream_intron_size_mean": 8934.2, "upstream_intron_size_median": 4521.0,
    "downstream_intron_size_mean": 12045.8, "downstream_intron_size_median": 6230.0,
    "ppt_mean_score": 0.74,
    "frame_in_frame": 180, "frame_frameshift": 95, "frame_non_coding": 37
  },
  "not_significant": { "..." : "same structure" },
  "statistical_tests": [
    { "feature": "ppt_score",     "test_name": "Welch's t-test",     "statistic": 2.41,   "p_value": 0.016, "q_value": 0.107, "significant": true,  "significant_fdr": false },
    { "feature": "ppt_score_mwu", "test_name": "mann_whitney_u",     "statistic": 48210,  "p_value": 0.021, "q_value": 0.107, "significant": true,  "significant_fdr": false },
    { "feature": "canonical_gt",  "test_name": "Proportion z-test",  "statistic": -1.12,  "p_value": 0.263, "q_value": 0.526, "significant": false, "significant_fdr": false }
  ]
}
```

> Full response schemas are available interactively at **http://localhost:8000/docs** (Swagger UI).

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
| `upstream_donor_seq` | 9 nt window at the upstream flanking exon 5'SS |
| `downstream_acceptor_seq` | 23 nt window at the downstream flanking exon 3'SS |
| `donor_is_gt` | Whether the donor dinucleotide is GT (canonical); `null` when the window is truncated (< 5 nt, contig end) |
| `acceptor_is_ag` | Whether the acceptor dinucleotide is AG (canonical); `null` when the window is truncated (< 20 nt) |
| `upstream_donor_is_gt` | Canonical check for upstream flanking exon donor |
| `downstream_acceptor_is_ag` | Canonical check for downstream flanking exon acceptor |

### PPT (Polypyrimidine Tract) Metrics

| Feature | Description |
|---------|-------------|
| `ppt_score` | Fraction of C+T nucleotides in PPT window (0.0&ndash;1.0) |
| `ppt_longest_run` | Length of the longest consecutive C/T run |

### Branch-Point Detection

| Feature | Description |
|---------|-------------|
| `bp_motif_found` | Whether a YNYTRAY (yUnAy) candidate with an `A` at the branch position and its branch A 18&ndash;44 nt upstream of the exon start scores &ge; 5 |
| `bp_distance` | Distance (nt) from the branch adenosine of the best candidate to the exon start (3'SS); `null` when not found |
| `bp_score` | Positional match score (0&ndash;7): each position earns 1 point if it matches the consensus (the A position always matches) |
| `bp_position` | 0-based index of the matched 7-mer in `ppt_seq`; `null` when not found |
| `bp_motif` | The matched 7-mer; `null` when not found |

### MANE Frame Annotation

| Feature | Description |
|---------|-------------|
| `mane_transcript_id` | MANE Select transcript ID (from local GFF3 or Ensembl REST) |
| `exon_rank` | Exon position in the MANE transcript (1-based) |
| `frame_region` | Genomic context: `CDS`, `partial`, `UTR5`, `UTR3`, `non_coding` (transcript without CDS), or `unknown` |
| `frame_class` | Frame impact: `in_frame`, `frameshift`, `non_coding`, or `unknown` |
| `cds_exon_length` | Number of coding nucleotides in the skipped exon (overlap with the union of the CDS segments) |
| `mane_exon_source` | How the MANE exon boundaries were matched: `overlap`, `flanking`, or `null` |

---

## Scientific References

Each analytical panel embeds collapsible `ScienceNote` widgets that cite the primary literature. All reference metadata is centralized in `frontend/src/lib/references.ts`.

### Reference Registry

| ID | Citation | Year | Used In |
|----|----------|:----:|---------|
| `rmats` | Shen S et al. *Proc Natl Acad Sci USA* | 2014 | SpliceView, PermutationPanel |
| `sequence_logos` | Schneider TD & Stephens RM. *Nucleic Acids Res* | 1990 | ConsensusLogoPanel, MotifPatternPanel |
| `shannon` | Shannon CE. *Bell Syst Tech J* | 1948 | ConsensusLogoPanel |
| `splice_sites` | Shapiro MB & Senapathy P. *Nucleic Acids Res* | 1987 | ConsensusLogoPanel, MotifPatternPanel |
| `maxent` | Yeo G & Burge CB. *J Comput Biol* | 2004 | ConsensusLogoPanel |
| `ppt` | Coolidge CJ et al. *Nucleic Acids Res* | 1997 | PPTTrack, MotifPatternPanel |
| `branch_point` | Padgett RA et al. *Annu Rev Biochem* | 1986 | PPTTrack, MotifPatternPanel |
| `permutation_phipson` | Phipson B & Smyth GK. *Stat Appl Genet Mol Biol* | 2010 | PermutationPanel |
| `benjamini_hochberg` | Benjamini Y & Hochberg Y. *J R Stat Soc Series B* | 1995 | SpliceView, PermutationPanel |
| `mane_select` | Morales J et al. *Nature* | 2022 | SpliceView |
| `gene_ontology` | Gene Ontology Consortium. *Nucleic Acids Res* | 2021 | AnnotatedCard (GO tab) |
| `stringdb` | Szklarczyk D et al. *Nucleic Acids Res* | 2023 | AnnotatedCard (STRING-DB tab) |
| `panelapp` | Martin AR et al. *Nat Genet* | 2019 | AnnotatedCard (PanelApp tab) |
| `rmaps2` | Hwang JY et al. *Nucleic Acids Res* | 2020 | HnRNPMotifPanel (hnRNP enrichment) |
| `enrichr` | Chen EY et al. *BMC Bioinformatics* | 2013 | EnrichrPanel (pathway enrichment) |
| `cisbp_rna` | Ray D et al. *Nature* | 2013 | HnRNPMotifPanel (motif catalogue) |
| `pcbp1_chkheidze` | Chkheidze AN et al. *Mol Cell Biol* | 1999 | HnRNPMotifPanel (hnRNP E1 motifs) |
| `pcbp1_makeyev` | Makeyev AV & Liebhaber SA. *RNA* | 2002 | HnRNPMotifPanel (hnRNP E1 motifs) |
| — | Gao K, Masuda A, Matsuura T, Ohno K. Human branch point consensus sequence is yUnAy. *Nucleic Acids Res* 36:2257–2267 | 2008 | README/PDF only (branch-point consensus; cited inline in the PDF methodology, not in `references.ts`) |
| — | Mercer TR et al. Genome-wide discovery of human splicing branchpoints. *Genome Res* 25:290–303 | 2015 | README only (branch-point distance distribution) |
| — | Leman R et al. Assessment of branch point prediction tools to predict physiological branch points and their alteration by variants. *BMC Genomics* 21:86 | 2020 | README/PDF only (18–44 nt branch-point window; cited inline in the PDF methodology) |
| — | Mann HB & Whitney DR. On a test of whether one of two random variables is stochastically larger than the other. *Ann Math Stat* 18:50–60 | 1947 | README/PDF only (Mann-Whitney U test of §10 and §12; cited in the backend docstrings) |

### Key Formulas

| Formula | Expression | Reference |
|---------|------------|-----------|
| Frequency logo height | `height(b,i) = f(b,i) × H_logo` | Frequency mode (no IC scaling) |
| PPT score | Fraction of C+T in ~47 nt upstream of 3'SS | Coolidge et al. (1997) |
| Branch-point motif | YNYURAY / yUnAy (Y = C/T, N = any, R = A/G), branch A mandatory, branch A 18–44 nt upstream of the exon start | Padgett et al. (1986); Gao et al. (2008); Leman et al. (2020) |
| Permutation p-value (exact) | `p = r/N`; N = C(n₁+n₂, n₁) ≤ 5000 enumerated splits, r = splits with \|ΔΨ\| ≥ observed (observed split included) | — |
| Permutation p-value (Monte-Carlo) | `p = (r+1)/(K+1)`; r = permuted \|ΔΨ\| ≥ observed, K = iterations | Phipson & Smyth (2010) |
| FDR correction | Benjamini-Hochberg step-up procedure; monotonicity via cumulative minimum from largest rank | Benjamini & Hochberg (1995) |
| hnRNP presence z-test | Two-proportion z-test on binary presence + Benjamini-Hochberg FDR (q &lt; 0.05, n = 133 pairs) | Agresti (2002); Benjamini &amp; Hochberg (1995) |
| hnRNP density U test | Mann-Whitney U on per-event density; `z = (U₁ − n₁n₂/2 ∓ 0.5) / √[n₁n₂/12 × ((N+1) − Σ(t³−t)/(N(N−1)))]`, tie-corrected, 0.5 continuity correction; BH FDR per family | Mann &amp; Whitney (1947); Benjamini &amp; Hochberg (1995) |
| Welch t-test df | Welch-Satterthwaite approximation | Welch (1947) |
| Welch t-test p-value | `p = 2 × P(T ≥ \|t\|)` via numerically evaluated regularized incomplete beta (Lentz's CF) | Abramowitz & Stegun (1972) |
| Mann-Whitney U (pattern comparison) | Same statistic as above, run next to each Welch's t-test; BH q-values across the 20-test panel | Mann &amp; Whitney (1947) |
| Two-proportion z-test | `z = (p̂₁−p̂₂) / √[p̂(1−p̂)(1/n₁+1/n₂)]`; large-sample normal approximation, ≥ 5 events per group | Agresti (2002) |
| Normal CDF | `Φ(x) = 0.5 × erfc(−x/√2)`; identity exact, precision from C-library `erfc` | — |
| Enrichr combined score | `CS = log(p) × z` (log = natural logarithm) | Chen et al. (2013) |

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
| NumPy | ≥ 1.26.4, &lt; 3 | Vectorised permutations and Mann-Whitney ranking |
| httpx | 0.27.0 | Async HTTP client (PanelApp, Ensembl, STRING-DB) |
| requests | 2.32.3 | Synchronous HTTP client (Enrichr, run in thread) |
| openpyxl | 3.1.2 | Excel file generation |
| reportlab | 4.2.2 | PDF report generation |
| samtools | (system) | FASTA indexing and sequence extraction |

### Frontend

| Technology | Version | Purpose |
|------------|---------|---------|
| Next.js | 14.2.3 | React framework (App Router) |
| React | 18.x | UI library |
| TypeScript | &mdash; | Type safety |
| Tailwind CSS | 3.4.x | Utility-first CSS framework |
| TanStack Query | 5.x | Data fetching, caching, and synchronization |
| TanStack Table | 8.x | Headless table (`manualSorting`: a single server-side sort, no client-side re-ordering) |

Icons are inline SVG (no icon library). The nucleotide colour palette (A / C / G / T) is defined once in `src/lib/colors.ts` and shared by the exon diagram, splice-site tracks, logos and PPT track.

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
- The backend does **not** download the genome: run `bash rmats-viz/data/setup_grch38_fasta.sh` once so that `rmats-viz/data/GRCh38.fa` and `GRCh38.fa.fai` exist on the host (the startup log and `/debug/fasta` name the script when something is missing)
- If only the index is missing: `docker compose exec backend samtools faidx /data/GRCh38.fa`
- No restart is needed: the FASTA is checked on every request and picked up as soon as it exists
- The application will still function without the FASTA &mdash; splice-site windows fall back to the Ensembl REST API and hnRNP region scanning (local FASTA only) is skipped

**Frontend can't reach the backend (CORS errors in development)**
- The Next.js config proxies `/api` requests to `http://backend:8000` inside the Docker network
- If running outside Docker, update `next.config.mjs` to point to your backend URL
- If you see CORS errors in the browser console, ensure `CORS_ORIGINS` in `.env` includes your frontend URL (e.g., `["http://localhost:3000"]`); restart the backend after changes

**MANE GFF3 missing / frame classification fails**
- The local MANE GFF3 file (`MANE.GRCh38.ensembl_genomic.gff.gz`) is read in full with `gzip` at first use; no tabix index is needed
- If the GFF3 is missing entirely, the `docker compose` backend command downloads it before starting Uvicorn (or run `bash rmats-viz/data/setup_mane_gff3.sh`); ensure the container has outbound HTTPS access. Without it every event falls back to the Ensembl REST API
- Genes absent from the GFF3 are retried against Ensembl at most once per 24 h per event from the per-event feature endpoint; a full re-run of the compute endpoint retries all of them

**Genome FASTA indexing errors (pysam / samtools)**
- Sequence extraction requires both the FASTA file and its `.fai` index
- If you see `[E::fai_build_core]` or samtools errors, regenerate the index: `samtools faidx /data/GRCh38.fa`
- Ensure `samtools` is installed and accessible (it is included in the Docker image by default)

**French-locale decimal parsing errors**
- The parser automatically handles comma-as-decimal-separator (e.g., `"0,117"` &rarr; `0.117`)
- No user action required

**hnRNP motif scan or FASTA extraction very slow on large analyses**
- Ensure `samtools` is available and the FASTA is properly indexed (`.fai` file present)
- Extraction is chunked at 5 000 regions/call; a 100 k event analysis runs ~100 chunks (splice windows) or ~140 chunks (seven hnRNP regions) sequentially
- Both stages run in worker threads; the app remains responsive during computation

**Analysis stuck in `deleting` state after a container restart**
- The backend resets any `deleting` analyses to `error` on startup, so you can retry deletion
- If a deletion fails, the status is reset to `error` with a message; click Delete again to retry
- Deletion runs as a background task: the UI removes the row optimistically and the backend cleans up child tables in dependency order before removing the analysis row

**Splice-feature computation stuck in `running` / progress bar never completes**
- The state is stored in `analyses.compute_status`; on startup the backend resets any analysis left in `running` to `error` ("interrupted by restart"), the progress endpoint then reports `done: true` with the `error` message and the UI stops polling
- Re-run **Compute** to start a new task; the endpoint refuses to start while a task is genuinely `running`
- The frontend stops polling on its own when the progress endpoint reports `done`, errors, or after a maximum number of polls

**PanelApp columns empty in Excel export**
- PanelApp AU/UK may be temporarily unreachable; the circuit breaker places the failing source in a 5-minute backoff
- For large exports, lookups are capped at 25 s total — genes not resolved within the cap get empty panel data
- Results are cached in memory for 6 h per gene (negative results included, unless every source was in backoff); re-run the export after a few minutes to retry

**Enrichr returns empty results for a library**
- The Enrichr API is occasionally rate-limited or the library name may have changed
- Check current library names at https://maayanlab.cloud/Enrichr/#libraries

### Resetting the Database

```bash
docker compose down -v          # removes the PostgreSQL volume
docker compose up --build       # recreates everything from scratch
```

---

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Make your changes
4. Ensure the application builds and runs: `docker compose up --build`
5. Commit with clear, descriptive messages
6. Open a Pull Request

### Development Tips

- **Backend hot-reload:** The backend volume mount (`./rmats-viz/backend:/app`) enables live code reloading with Uvicorn
- **Frontend hot-reload:** The frontend source mount (`./rmats-viz/frontend/src:/app/src`) enables Next.js Fast Refresh
- **API documentation:** Use Swagger UI at `http://localhost:8000/docs` to test endpoints interactively
- **Database migrations:** Create new migrations with `docker compose exec backend alembic revision --autogenerate -m "description"`
- **Tests:** Run the backend suite (parser / event-type detection, coverage filter, sequence extraction and branch point, hnRNP motifs, permutation, statistics) with `cd rmats-viz/backend && python -m pytest tests/ -v`
