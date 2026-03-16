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
  - [Event Cards](#event-cards)
  - [Deep Splice Analysis](#deep-splice-analysis)
  - [Gene Annotations](#gene-annotations)
  - [Exporting Results](#exporting-results)
- [Methodology](#methodology)
  - [Coverage Filtering](#1-coverage-filtering)
  - [Event Clustering](#2-event-clustering)
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

**SpliceAnalyzer** provides a browser-based interface on top of [rMATS](https://rnaseq-mats.sourceforge.io/) junction-count output files (e.g., `SE.MATS.JC.txt`). It enables researchers to upload rMATS results, explore alternative splicing events interactively, characterize splice-site signals at single-event resolution, perform aggregate statistical analyses across event groups, and export curated findings for publication or clinical review.

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

- **Drag-and-drop file upload** &mdash; Upload rMATS `.txt` junction-count files with automatic sample-group mapping and event-type inference from filename
- **Coverage filtering** &mdash; Events with mean per-replicate junction coverage (IJC + SJC) below 10X in either sample group are automatically filtered out on import
- **Analysis management** &mdash; Create, list, navigate, and delete named analyses
- **Event browser** &mdash; Sortable, filterable, paginated table of all splicing events with support for filtering by event type, gene symbol, FDR threshold, P-value, and minimum |&Delta;&Psi;|
- **Event ranking** &mdash; Significant events ranked by statistical significance (FDR) and inclusion-level difference (|&Delta;&Psi;|), displayed as annotated cards
- **Gene basket** &mdash; Collect genes of interest across analyses for batch annotation and export
- **Dark mode** &mdash; Toggle-able theme with persistent preference via `localStorage`
- **Internationalisation** &mdash; Full English / French language switcher; all UI strings are externalized

### Splice Site Analysis (SE events)

- **Donor (5'SS) and acceptor (3'SS) sequences** &mdash; 9 nt and 23 nt windows around splice junctions with GT-AG canonical check
- **Polypyrimidine tract (PPT)** &mdash; Score (C+T fraction) and longest consecutive pyrimidine run in the ~47 nt upstream of the 3'SS
- **Branch-point detection** &mdash; Rule-based YNYURAY motif search with positional scoring (0&ndash;7 scale) and distance to 3'SS
- **Exon and intron sizing** &mdash; Skipped exon length plus upstream and downstream intron sizes
- **Event clustering** &mdash; Union-Find algorithm deduplicates near-identical SE events sharing exon boundaries within a 50 bp threshold
- **Aggregate pattern analysis** &mdash; Position Weight Matrices (PWM), IUPAC consensus sequences, and statistical summaries across all SE events
- **Sequence source flexibility** &mdash; Primary extraction from local GRCh38 FASTA via `samtools faidx` (batched, chunked at 5 000 regions per call), with automatic Ensembl REST API fallback when FASTA is unavailable

### Deep Splice Analysis

A second-pass module that partitions events into **significant** and **non-significant** groups using user-defined FDR and |&Delta;&Psi;| thresholds, then runs the following analyses across groups:

- **Pattern comparison** &mdash; Side-by-side group statistics: GT-AG canonical rates, PPT score distributions, exon/intron size distributions, frame-class breakdown, comparison sequence logos; Welch's t-test and two-proportion z-test for each metric
- **hnRNP motif enrichment** &mdash; rMAPS2-inspired analysis scanning five genomic regions around each SE event for 17 consensus hnRNP binding motifs; two-proportion z-test per motif–region pair with Bonferroni correction
- **Pathway enrichment (Enrichr)** &mdash; Significant-event gene symbols submitted to the Enrichr REST API against five curated gene-set libraries; top terms per library by adjusted p-value
- **Permutation testing** &mdash; Per-event |&Delta;&Psi;| significance testing against a null distribution of permuted sample labels

### MANE Frame Annotation

- Maps each skipped exon to its **MANE Select** transcript via local GFF3 file or Ensembl REST API
- Classifies the frame impact: `in_frame` (exon length divisible by 3), `frameshift`, `non_coding` (UTR), or `partial`
- Caches successful lookups in a local SQLite database (WAL mode for concurrent access) to minimize redundant API calls

### Gene Annotations & Interactions

- **Ensembl gene search** &mdash; Autocomplete by HUGO gene symbol (minimum 2 characters)
- **PanelApp disease panels** &mdash; Queries PanelApp Australia (with PanelApp UK fallback) for diagnostic gene panel membership and confidence ratings (green/amber/red); circuit breaker prevents cascade timeouts on unreachable instances
- **Gene Ontology** &mdash; Retrieves GO terms (Biological Process, Molecular Function, Cellular Component) via mygene.info
- **UniProt** &mdash; Fetches reviewed protein function summaries
- **STRING-DB interactions** &mdash; Protein-protein interaction combined scores between gene pairs, with Europe PMC literature PMIDs

### Export

- **PDF report** &mdash; Multi-page publication-ready document including: analysis summary, significant SE events with splice feature tables, deep analysis sections (hnRNP motif enrichment, pathway enrichment with significant p-values bolded and starred, pattern comparison), frequency-mode sequence logos, methodology appendix, bibliographic references, and statistical methods. Optionally includes deep analysis results when a deep analysis object is linked
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
    │   │   └── test_parser_coverage.py
    │   └── app/
    │       ├── main.py
    │       ├── config.py
    │       ├── database.py
    │       ├── models/
    │       │   ├── analysis.py          # Analysis, SampleGroup
    │       │   ├── event.py             # SplicingEvent
    │       │   ├── splice.py            # EventCluster, EventSpliceFeature
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
    │       └── services/
    │           ├── parser.py            # rMATS TSV parsing + coverage filter
    │           ├── event_selector.py    # Event ranking by FDR / ΔΨ
    │           ├── event_cluster.py     # Union-Find SE event deduplication
    │           ├── sequence.py          # samtools faidx wrapper (chunked batching)
    │           ├── splice_features.py   # GT-AG, PPT score, branch-point
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
            │   │   ├── HnRNPMotifPanel.tsx   # hnRNP enrichment table + heatmap
            │   │   ├── EnrichrPanel.tsx       # Enrichr pathway panel
            │   │   ├── SpliceSequenceLogo.tsx # Frequency-mode SVG logo
            │   │   ├── SidebarNav.tsx         # Deep analysis sidebar
            │   │   └── ...
            │   └── deep-analysis/
            ├── contexts/
            ├── lib/
            │   ├── i18n/                # en.ts, fr.ts
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
4. The backend will attempt to **download the full GRCh38 FASTA** in the background (~800 MB compressed). The server starts immediately; sequence features become available once the download completes.

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

The backend downloads the full genome automatically on first startup. To set it up manually instead:

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
| `MANE_GFF3` | `/data/MANE.GRCh38.ensembl_genomic.gff.gz` | Local MANE GFF3 annotation file |
| `SPLICE_WINDOW` | `50` | Intronic window (nt) around each splice site |

> **MANE cache behavior:** Successful Ensembl lookups are cached in `mane_cache.db` (SQLite with WAL journal mode) to avoid repeated API calls. Failed lookups (network errors, no MANE transcript found) are **not** cached and will be retried on the next compute run.

---

## Usage Guide

### Creating an Analysis

1. Navigate to the **New Analysis** page (`/analyses/new`)
2. Drag and drop one or more rMATS junction-count files (e.g., `SE.MATS.JC.txt`, `A5SS.MATS.JC.txt`)
3. The event type is automatically inferred from the filename
4. Define sample group names for your conditions
5. Click **Create** &mdash; the parser ingests the TSV, filters low-coverage events (&lt;10X), deduplicates, and stores events in PostgreSQL

### Browsing Events

The event browser (`/analyses/{id}`) provides a fully interactive table with:

- **Column sorting** &mdash; Click any header to sort ascending/descending
- **Filters** &mdash; Event type selector, gene symbol search, FDR max, P-value max, minimum |&Delta;&Psi;|
- **Pagination** &mdash; Configurable page size
- **Direction-of-effect badges** &mdash; Visual indicators for exon skipping vs. inclusion

### Event Cards

The event cards view displays significant events ranked by FDR and |&Delta;&Psi;|. Each event card includes:

- **SpliceView** &mdash; Schematic of the splicing event with inclusion/exclusion levels
- **ExonDiagram** &mdash; Interactive exon-intron diagram with donor/acceptor/PPT/branch-point annotations
- **SpliceSiteTrack** &mdash; All 4 SE splice sites (upstream, skipped 5', skipped 3', downstream)
- **Sequence source badge** &mdash; Indicates whether sequences come from local FASTA or Ensembl REST fallback
- **PermutationPanel** &mdash; Interactive permutation test results (per-event |&Delta;&Psi;| empirical p-values at multiple iteration counts)
- **ScienceNote** &mdash; Collapsible citation widgets linking to primary literature
- **AnnotatedCard** &mdash; Gene annotations (PanelApp, GO, UniProt, STRING-DB) in tabbed panels

### Deep Splice Analysis

The deep analysis page (`/analyses/{id}/deep-analysis`) enables a two-group partitioning of SE events for comparative analysis. The workflow is:

**1. Create a deep analysis** &mdash; Set FDR and |&Delta;&Psi;| thresholds to partition events into significant and non-significant groups. Each configuration is saved as a named deep analysis object and can be reopened later.

**2. Explore the results** via the sidebar navigation:

| Tab | Content |
|-----|---------|
| **Annotated Events** | Cards for the significant events only, with full per-event annotations |
| **Splice** | Pattern comparison panel: side-by-side aggregate statistics for significant vs. non-significant groups (logos, GT-AG rates, PPT scores, frame breakdown), with statistical tests |
| **Motifs** | IUPAC recurrent motif analysis across SE events |
| **hnRNP** | hnRNP motif enrichment analysis — frequency table and protein × region heatmap |
| **Enrichr** | Pathway enrichment results across five gene-set libraries |

#### hnRNP Motif Panel

- Filterable table of motif–region associations ranked by adjusted p-value
- Toggle: significant only vs. all 85 (motif × region) combinations
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
- **STRING-DB** &mdash; Interaction scores with other genes in the analysis, plus supporting literature PMIDs

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

Click the **Export PDF** button to generate a multi-page, publication-ready report. The report includes:

| Section | Content |
|---------|---------|
| Summary | Analysis metadata, event counts, thresholds |
| Significant Events | Per-event table with splice features, GT-AG rate, frame class, PSI values |
| Comparison Logos | Frequency-mode donor and acceptor logos: significant vs. non-significant (when deep analysis present) |
| Frame Breakdown | Pie charts of in-frame / frameshift / non-coding proportions per group |
| hnRNP Enrichment | Top 20 significant motif–region associations (when deep analysis present) |
| Pathway Enrichment | Top 5 terms per library; adjusted p-values &lt; 0.05 are **bolded and starred (★)** for quick identification (when deep analysis present) |
| Appendix A | Full pipeline methodology |
| Appendix B | Bibliographic references |
| Appendix C | Statistical methods |

> Sequence logos in the PDF use **frequency mode**: every column fills the full height and letter height is proportional to raw nucleotide frequency, matching the web app display.

---

## Methodology

### 1. Coverage Filtering

On import, each rMATS event is evaluated for read support. For each sample group, the mean per-replicate junction coverage is computed as:

```
coverage = mean(IJC_i + SJC_i)   for all replicates i in the group
```

Events where either group has `coverage < 10` are discarded. This threshold prevents low-confidence events from inflating significant hit lists and is applied once at ingestion time.

### 2. Event Clustering

Near-identical SE events (arising from overlapping transcripts or minor coordinate differences) are deduplicated using a **Union-Find (Disjoint Set Union)** algorithm. Two events are merged into the same cluster if they share the same chromosome and strand, and all four boundary coordinates (upstream exon end, skipped exon start, skipped exon end, downstream exon start) differ by at most 50 bp. The representative event per cluster is the one with the lowest FDR.

### 3. Splice Site Sequence Extraction

Genomic sequences are extracted using `samtools faidx` from a locally indexed GRCh38 FASTA. Coordinates follow the rMATS/BED convention (0-based start, exclusive end); these are converted to the 1-based inclusive format expected by samtools.

For performance at scale (up to 120 k events), extraction uses a single batched subprocess call per chunk:
- All regions for a batch of events are passed as positional arguments to one `samtools faidx` invocation
- Chunks are capped at **5 000 regions per call** to stay within the Linux ARG_MAX (~2 MB) limit
- Timeout per chunk: `max(30, chunk_size // 100)` seconds

Chromosome name translation is handled automatically: rMATS uses UCSC names (`chr1`–`chr22`, `chrX`, `chrY`, `chrM`), while some FASTA files use RefSeq accessions (`NC_000001.11`…). The backend reads the `.fai` index at startup and translates names as needed. When the FASTA is unavailable, sequences are fetched per-event from the Ensembl REST API as a fallback.

For minus-strand events, extracted sequences are reverse-complemented before all downstream analyses.

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

The branch-point adenosine is identified by scanning the PPT region for the **YNYURAY** consensus motif (Y = C/T; N = any; R = A/G; U → T in genomic DNA). The search window is the 47 nt upstream of the 3'SS. Each candidate match receives a **positional score** (0–7): one point for each degenerate position that matches the consensus nucleotide. The best match (highest score, tie-broken by proximity to 3'SS) is reported.

| Output | Description |
|--------|-------------|
| `bp_motif_found` | `True` if any match with score ≥ 4 is found |
| `bp_score` | Best positional score (0–7) |
| `bp_distance` | Distance (nt) from the motif center to the 3'SS |

### 7. MANE Select Frame Classification

Each skipped exon is mapped to its **MANE Select** transcript (the clinically validated representative transcript per gene, from the MANE consortium). The lookup uses a two-tier approach:

1. **Local GFF3** — If `MANE.GRCh38.ensembl_genomic.gff.gz` is present, CDS intervals are parsed directly (fast, no network required)
2. **Ensembl REST API** — Fallback when the GFF3 is unavailable; queries `/lookup/id/{gene_id}` + `/overlap/id/{transcript_id}` for exon and CDS features

The exon is classified by its overlap with the CDS:

| Class | Condition |
|-------|-----------|
| `in_frame` | Exon fully within CDS; `cds_exon_length % 3 == 0` |
| `frameshift` | Exon fully within CDS; `cds_exon_length % 3 != 0` |
| `non_coding` | Exon entirely within UTR5 or UTR3 |
| `partial` | Exon spans a CDS boundary |
| `unknown` | No MANE transcript found or lookup failed |

Results are cached in a local SQLite database with WAL journal mode to support concurrent access.

### 8. Permutation Testing

A permutation test assesses the significance of |&Delta;&Psi;| for each SE event by testing whether the observed group difference is larger than expected by chance:

1. Sample labels are randomly permuted (keeping group sizes fixed)
2. A null distribution of |&Delta;&Psi;| is built from `N` permutations (50, 100, 250, or 500 iterations)
3. The empirical two-tailed p-value uses the **Phipson & Smyth (2010)** continuity correction: `p = (k + 1) / (N + 1)`, where `k` is the number of permuted |&Delta;&Psi;| values ≥ the observed value

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

Five regions are extracted per event (per rMAPS2 convention, with exclusion zones at splice signals):

| Region | Extraction rule | Default length |
|--------|----------------|----------------|
| Upstream exon | Last 250 nt of the upstream flanking exon | ≤ 250 nt |
| Upstream intron | 250 nt after the 5'SS, excluding first 6 nt (splice signal) | ≤ 244 nt |
| Skipped exon | Full exon body | variable |
| Downstream intron | 250 nt before the downstream exon, excluding last 20 nt | ≤ 230 nt |
| Downstream exon | First 250 nt of the downstream flanking exon | ≤ 250 nt |

Minus-strand events are reverse-complemented before scanning.

#### Motif catalogue

18 consensus motifs for 8 hnRNP protein families (RNA U → DNA T for genomic scanning):

| Protein | Motifs | Basis |
|---------|--------|-------|
| hnRNP A1/A2 | TAGG, TAGGG, TAGGGA, AGG | CISBP-RNA; Martinez-Contreras et al. (2006) |
| hnRNP E1 (PCBP1) | CCWWHCC `[CC[AT][AT][ACT]CC]` | rMAPS2 Suppl. Table S2 (Homo sapiens); Chkheidze et al. (1999); Makeyev & Liebhaber (2002) |
| hnRNP F/H | GGGG, GGG | G-quadruplex / G-run binding |
| hnRNP K | CCCC, TCCC | Poly-C binding |
| hnRNP C | TTTTT, TTTT | Poly-U/T binding |
| hnRNP L | CACA, ACAC | CA-repeat binding |
| hnRNP M | TGTG, GTGT | GU-rich elements |
| PTB (hnRNP I) | TCTT, TCTCT, CTCT | UCUU/UCUCU consensus |

#### Statistical test

For each of the 85 (motif, region) pairs:

1. Compute **hit rate** = fraction of events with ≥ 1 motif occurrence
2. Compare significant vs. background groups using a **two-proportion z-test** (pooled proportion estimator)
3. Apply **Bonferroni correction** across all 90 tests: `p_adj = min(p × 90, 1.0)`
4. Report associations with `p_adj < 0.05` as significant

Mean motif density (fraction of nucleotides covered by overlapping motif hits) is also reported per group.

#### Key differences vs. rMAPS2

| Aspect | rMAPS2 | SpliceAnalyzer |
|--------|--------|----------------|
| Test statistic | Wilcoxon rank-sum on per-window density | Two-proportion z-test on binary hit rate |
| Resolution | Nucleotide-level sliding window | Five discrete genomic sub-regions |
| Correction | Per-comparison | Bonferroni across all 85 pairs |
| Groups | Up-regulated, down-regulated, background | Significant, non-significant |

#### Performance

The scan is optimised for large datasets (tested at 120 k events):
- Events-outer loop (single pass, cache-local access to each `SERegions` object)
- Sequences are guaranteed uppercase from the FASTA parser; no redundant `.upper()` calls
- `pattern in seq` early exit: density is only computed for hits (~50–80% skip rate)
- Flat pre-allocated accumulators instead of per-region list allocations

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

3. Return top 10 terms per library by adjusted p-value

The **combined score** = |z-score| × log(p-value), where z-score measures deviation from a random gene-list background (Enrichr's internal model) and p-value is from Fisher's exact test. FDR adjustment uses Benjamini-Hochberg correction applied internally by Enrichr.

All Enrichr HTTP calls are issued inside `asyncio.to_thread` to avoid blocking the event loop. The five library GETs are dispatched in parallel (one thread per library via `ThreadPoolExecutor`), so total network time is ~1× latency rather than 5×.

### 12. Pattern Comparison (Sig vs Non-Sig)

The pattern comparison endpoint computes aggregate splice statistics for both the significant and non-significant event groups, then applies statistical tests to each metric:

| Metric | Test | Notes |
|--------|------|-------|
| PPT score distribution | Welch's t-test | Unequal-variance two-sample t-test |
| Exon size distribution | Welch's t-test | |
| Upstream/downstream intron sizes | Welch's t-test | |
| GT canonical rate | Two-proportion z-test | k=events with GT, n=events with donor seq |
| AG canonical rate | Two-proportion z-test | |
| Upstream donor GT rate | Two-proportion z-test | Length ≥ 9 bp guard applied |
| Downstream acceptor AG rate | Two-proportion z-test | Length ≥ 23 bp guard applied |
| Frame class fractions | Two-proportion z-test | Separate test per class |

Welch's t-test and the two-tailed p-value are computed in pure Python (no NumPy/SciPy) using the Welch-Satterthwaite degrees-of-freedom formula and a regularized incomplete beta function approximation (Lentz's continued-fraction algorithm).

Comparison sequence logos (frequency mode) are generated independently for each group.

### 13. PanelApp Circuit Breaker

PanelApp Australia is occasionally unreachable. A module-level circuit breaker prevents cascade latency in large exports:

- After any `ConnectError` or `ConnectTimeout`, the AU source is placed in a **300-second backoff window**
- Subsequent requests during the window skip AU immediately and go straight to PanelApp UK
- Read/pool timeouts do **not** trigger the circuit breaker (endpoint is live but slow)
- The breaker resets automatically after the backoff period

Connect timeout: 4 s; read timeout: 4 s. For large exports (many unique genes), all PanelApp lookups are additionally capped at **25 s total** via `asyncio.wait`; genes that do not resolve within the cap return empty panel data rather than blocking the export.

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
| Event clustering | Union-Find across all SE events | <1 s |
| **Total (local FASTA + warm MANE cache)** | | **~20–55 s** |

> If the local MANE GFF3 is missing, each event falls back to the Ensembl REST API (3 calls per event). Ensure `MANE_GFF3` is configured at startup to avoid this.

### Deep Splice Analysis (page load)

Expected wall-clock times when a deep-analysis tab is first opened for a 100 k event analysis:

| Stage | Description | Expected Time |
|-------|-------------|:-------------:|
| Deep analysis creation | Bulk-insert junction rows (5 000-row batches) | <1 s |
| FASTA extraction | 100 k × 5 = 500 k regions, chunked into ~100 × 5 k samtools calls | 60–120 s |
| hnRNP scan | 2 groups × 100 k events × 5 regions × 17 motifs ≈ 17 M inner iterations | 30–60 s |
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
| `GET` | `/api/v1/analyses/{id}/events/top10` | Ranked significant events by FDR |

**Event query parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `event_type` | string | Filter by type: `SE`, `A5SS`, `A3SS`, `MXE`, `RI` |
| `gene_symbol` | string | Filter by gene symbol (exact match) |
| `fdr_max` | float | Maximum FDR threshold |
| `p_value_max` | float | Maximum P-value threshold |
| `delta_psi_min` | float | Minimum |&Delta;&Psi;| threshold |
| `sort_by` | string | Column to sort by |
| `sort_dir` | string | `asc` or `desc` |
| `page` | int | Page number (1-indexed) |
| `page_size` | int | Results per page |

### Deep Analyses

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/analyses/{id}/deep-analyses` | Create a deep analysis (tag events by FDR + ΔΨ thresholds) |
| `GET` | `/api/v1/analyses/{id}/deep-analyses` | List saved deep analyses for an analysis |
| `GET` | `/api/v1/deep-analyses/{deep_id}` | Get a deep analysis by ID |
| `DELETE` | `/api/v1/deep-analyses/{deep_id}` | Delete a deep analysis |
| `GET` | `/api/v1/deep-analyses/{deep_id}/events` | Paginated event list with significance tags |
| `GET` | `/api/v1/deep-analyses/{deep_id}/pattern-comparison` | Sig vs non-sig group statistics + statistical tests |
| `GET` | `/api/v1/deep-analyses/{deep_id}/hnrnp-motifs` | hnRNP motif enrichment results |
| `GET` | `/api/v1/deep-analyses/{deep_id}/enrichr` | Enrichr pathway enrichment results |

**Deep analysis create body:**

| Field | Type | Description |
|-------|------|-------------|
| `fdr_threshold` | float | FDR cutoff for significance (e.g. `0.05`) |
| `delta_psi_min` | float | Minimum |&Delta;&Psi;| (e.g. `0.1`) |
| `pvalue_threshold` | float? | Optional p-value cutoff (stored for labeling; not used in event tagging) |
| `name` | string? | Optional name; auto-generated from thresholds + date if omitted |
| `modules` | list[string]? | Modules to enable: `["hnrnp", "enrichr"]` |

### Splice Site Analysis

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/splice/compute/{analysis_id}` | Compute splice features + clusters for all SE events |
| `GET` | `/api/v1/splice/feature/{event_id}` | Per-event features (computed on-the-fly if not cached) |
| `GET` | `/api/v1/splice/patterns/{analysis_id}` | Aggregate pattern analysis (PWM, consensus, frame stats) |

> The compute endpoint is **idempotent** &mdash; re-running overwrites existing feature rows and refreshes clusters. It requires the GRCh38 FASTA for sequence features; if unavailable, size-only features are computed.

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
| `GET` | `/api/v1/export/{id}/deep/{deep_id}/excel?include=core,panelapp,go,stringdb` | Download Excel for a deep analysis (significant events only); `include` is comma-separated |

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
| `upstream_donor_seq` | 9 nt window at the upstream flanking exon 5'SS |
| `downstream_acceptor_seq` | 23 nt window at the downstream flanking exon 3'SS |
| `donor_is_gt` | Whether the donor dinucleotide is GT (canonical) |
| `acceptor_is_ag` | Whether the acceptor dinucleotide is AG (canonical) |
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
| `bp_motif_found` | Whether a YNYURAY motif was found (score &ge; 4) |
| `bp_distance` | Distance (nt) from best motif center to 3'SS |
| `bp_score` | Positional match score (0&ndash;7): each position earns 1 point if it matches the consensus |

### MANE Frame Annotation

| Feature | Description |
|---------|-------------|
| `mane_transcript_id` | MANE Select transcript ID (from local GFF3 or Ensembl REST) |
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

### Key Formulas

| Formula | Expression | Reference |
|---------|------------|-----------|
| Frequency logo height | `height(b,i) = f(b,i) × H_logo` | Frequency mode (no IC scaling) |
| PPT score | Fraction of C+T in ~47 nt upstream of 3'SS | Coolidge et al. (1997) |
| Branch-point motif | YNYURAY (Y = C/T, N = any, R = A/G) | Padgett et al. (1986) |
| Permutation p-value | `p = (k+1)/(N+1)` with continuity correction | Phipson & Smyth (2010) |
| FDR correction | Benjamini-Hochberg step-up procedure | Benjamini & Hochberg (1995) |
| hnRNP hit-rate z-test | Two-proportion z-test with Bonferroni (n=90) | Agresti (2002) |
| Welch t-test df | Welch-Satterthwaite approximation | Welch (1947) |
| Enrichr combined score | `CS = \|z\| × log(p)` | Chen et al. (2013) |

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
- The application will still function without the FASTA &mdash; sequence-dependent features will be skipped

**Frontend can't reach the backend**
- The Next.js config proxies `/api` requests to `http://backend:8000` inside the Docker network
- If running outside Docker, update `next.config.mjs` to point to your backend URL

**French-locale decimal parsing errors**
- The parser automatically handles comma-as-decimal-separator (e.g., `"0,117"` &rarr; `0.117`)
- No user action required

**hnRNP motif scan or FASTA extraction very slow on large analyses**
- Ensure `samtools` is available and the FASTA is properly indexed (`.fai` file present)
- Extraction is chunked at 5 000 regions/call; a 100 k event analysis runs ~100 chunks sequentially
- Both stages run in worker threads; the app remains responsive during computation

**Analysis stuck in `deleting` state after a container restart**
- The backend resets any `deleting` analyses to `error` on startup, so you can retry deletion
- If a deletion fails, the status is reset to `error` with a message; click Delete again to retry
- Deletion runs as a background task: the UI removes the row optimistically and the backend cleans up child tables in dependency order before removing the analysis row

**PanelApp columns empty in Excel export**
- PanelApp AU/UK may be temporarily unreachable; the circuit breaker places the failing source in a 5-minute backoff
- For large exports, lookups are capped at 25 s total — genes not resolved within the cap get empty panel data
- Re-run the export after a few minutes to retry

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
- **Tests:** Run parser tests with `cd rmats-viz/backend && python -m pytest tests/ -v`
