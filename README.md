# SpliceAnalyzer

<p align="center">
  <img src="rmats-viz/frontend/public/logo.svg" alt="SpliceAnalyzer logo" width="120"/>
</p>

<p align="center">
  <strong>A web application for visualizing, exploring, and characterizing RNA alternative splicing events from rMATS output.</strong>
</p>

<p align="center">
  <a href="#quick-start">Quick Start</a> &bull;
  <a href="#scope-and-known-limitations">Scope</a> &bull;
  <a href="#features">Features</a> &bull;
  <a href="#methodology">Methodology</a> &bull;
  <a href="#api-reference">API Reference</a> &bull;
  <a href="#scientific-references">Scientific References</a>
</p>

---

## Table of Contents

- [Overview](#overview)
- [Scope and Known Limitations](#scope-and-known-limitations)
- [Features](#features)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Quick Start](#quick-start)
  - [Prerequisites](#prerequisites)
  - [The two compose files](#the-two-compose-files)
  - [Installation](#installation)
  - [GRCh38 FASTA Setup](#grch38-fasta-setup)
  - [MANE GFF3 Setup](#mane-gff3-setup)
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
  - [Analyses & Uploads](#analyses--uploads)
  - [Events](#events)
  - [Deep Analyses](#deep-analyses)
  - [Splice Site Analysis](#splice-site-analysis)
  - [Genes & Annotations API](#genes--annotations-api)
  - [Export Endpoints](#export-endpoints)
  - [Diagnostics](#diagnostics)
  - [Example Responses](#example-responses)
- [Splice Feature Reference](#splice-feature-reference)
- [Scientific References](#scientific-references)
- [Technology Stack](#technology-stack)
- [Testing](#testing)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [Related Documents](#related-documents)

---

## Overview

**SpliceAnalyzer** provides a browser-based interface on top of [rMATS](https://rnaseq-mats.sourceforge.io/) output files (e.g., `SE.MATS.JC.txt` or `SE.MATS.JCEC.txt`). It enables researchers to upload rMATS results, explore alternative splicing events interactively, characterize splice-site signals at single-event resolution, perform aggregate statistical analyses across event groups, and export curated findings in a report format.

> **Disclaimer:** This tool is experimental and intended for research use only. It has not been validated for clinical or diagnostic purposes. Users are solely responsible for the interpretation and use of any results.

> **Status of this version.** This is the **closing version of the Python / Docker application** (FastAPI backend, Next.js frontend, PostgreSQL). The application is being re-implemented as a pure in-browser tool; that successor is specified in [`SPLICEANALYZER_IN_BROWSER_SPEC.md`](SPLICEANALYZER_IN_BROWSER_SPEC.md) and is where the analysis of the non-SE event types (see below) will be delivered. The Python version documented here is kept as is.

The application imports all five rMATS event types, but only skipped-exon events receive the sequence-level study:

| Event Type | Full Name | Description | Analysed in this version |
|:----------:|-----------|-------------|--------------------------|
| **SE** | Skipped Exon | An exon is included or excluded from the mature mRNA | **Full study** (splice sites, PPT, branch point, MANE frame, hnRNP, permutation, pattern comparison, PDF/Excel) |
| **A5SS** | Alternative 5' Splice Site | Two or more alternative 5' splice sites compete | Import, type-aware dedup, native coordinates, table / Manhattan / Excel / deep-analysis partition |
| **A3SS** | Alternative 3' Splice Site | Two or more alternative 3' splice sites compete | Same as A5SS |
| **MXE** | Mutually Exclusive Exons | One of two exons is retained, never both | Same as A5SS (both exons stored) |
| **RI** | Retained Intron | An intron is retained in the mature transcript | Same as A5SS |

---

## Scope and Known Limitations

This section states precisely what the closing version does and does not do, so that results are not over-interpreted.

**Skipped-exon (SE) events — full study.** Every analysis of the Methodology section applies to SE events only: donor / acceptor / PPT windows and the branch-point search (§3–§6), MANE Select frame classification and exon-boundary correction (§7), the permutation test (§8), sequence logos (§9), hnRNP motif enrichment (§10), the significant vs non-significant pattern comparison (§12) and the "Top SE events" table of the PDF report.

**RI, A3SS, A5SS and MXE events — imported, not analysed.** These events are:

- **imported** from their rMATS files with the same coverage filter (`services/parser.py`), and **deduplicated with type-aware rules** (§2);
- stored with their **native coordinates**: A3SS / A5SS keep the long / short / flanking exon coordinates (`long_exon_start`, `long_exon_end`, `short_es`, `short_ee`, `flanking_es`, `flanking_ee`) and MXE keeps its second exon (`second_exon_start`, `second_exon_end`), in addition to the generic `exon_*` / `upstream_*` / `downstream_*` columns;
- listed in the **event table**, plotted on the **Manhattan plot**, counted in the **deep-analysis partition** (significant / non-significant tagging uses FDR, |ΔΨ| and the optional p-value maximum for every event type) and written to the **Excel export** (core columns; the splice-feature columns are empty for them);
- **not** sent through any sequence-feature analysis: `POST /api/v1/splice/compute/{analysis_id}` processes SE events only (and answers 404 when the analysis has none), `GET /api/v1/splice/feature/{event_id}` returns an `error` field for a non-SE event, the pattern endpoints, the permutation test, the pattern comparison and the hnRNP job select `event_type = "SE"`, and the PDF "Top events" table lists SE events only. In the deep-analysis view, non-SE significant events get an annotated card (gene annotations, PSI, ΔΨ) without splice-site tracks.

**Other limitations of this version**

- Upload parsing is synchronous inside the request; ingestion drop counts (low coverage, missing counts, collapsed duplicates) are logged but not returned in the upload response (only coarse `warnings`).
- No splice-site strength score (MaxEntScan) and no PTC / NMD prediction by translation; `frameshift` is a coding-length statement only (see §7).
- The hnRNP analysis does not split significant events by ΔΨ sign and does not produce the rMAPS2 50-nt sliding-window map.
- PanelApp per-gene lookups are best-effort (slow public API, host changes); large exports may have partly empty PanelApp columns (§13).

The in-browser successor ([`SPLICEANALYZER_IN_BROWSER_SPEC.md`](SPLICEANALYZER_IN_BROWSER_SPEC.md), §8–§9) specifies the feature set for all five event types.

---

## Features

### Core Functionality

- **Drag-and-drop file upload** &mdash; Upload rMATS `.txt` output files with automatic sample-group mapping. The event type **and** the counting mode are detected from a delimited `<TYPE>[._-]MATS[._-]<JC|JCEC>` token anywhere in the file name (any prefix or suffix, case-insensitive: `PRIMARY_SE.MATS.JC.txt` is SE, not RI; `SE.MATS.JC (1).txt`, `RI.MATS.JC - Copie.txt` and `SE_MATS_JC.txt` are recognised); `fromGTF[.novelJunction|.novelSpliceSite|.novelEvents].<TYPE>.txt` annotation files are recognised too. When the file name carries no such token the header is sniffed (`riExonStart_0base` &rarr; RI, `1stExonStart_0base` / `2ndExonStart_0base` &rarr; MXE, `exonStart_0base` &rarr; SE), helped by a loose delimited type token anywhere in the name (`results_A5SS.txt`); A3SS and A5SS share a header and therefore **need** an `A3SS` / `A5SS` token in the file name, otherwise the file is skipped with a warning. The counting mode falls back to a loose `JC` / `JCEC` token. Files must be plain-text TSV (compressed payloads are not decompressed). The upload response carries `warnings` (empty file, no event imported)
- **JC vs JCEC recorded** &mdash; The counting mode of each row is stored (`counting_mode` = `JC` / `JCEC`), together with `IncFormLen` / `SkipFormLen` (`inc_form_len`, `skip_form_len`), which are needed to interpret JCEC counts
- **Native coordinates for every event type** &mdash; A3SS / A5SS rows keep their long / short / flanking exon coordinates (`long_exon_start`, `long_exon_end`, `short_es`, `short_ee`, `flanking_es`, `flanking_ee`); the generic `exon_*` columns are derived from the long exon and the flanking exon is copied into `upstream_*` or `downstream_*` according to its genomic position. MXE `1stExon*` columns map to the generic exon columns and `2ndExon*` to `second_exon_*`. The event identity constraint includes the MXE second exon and the A3SS/A5SS long/short exons
- **Coverage filtering** &mdash; Events whose mean per-replicate junction coverage (IJC + SJC) over the *available* replicates is below 10X in either sample group are filtered out on import (NA replicates are ignored, unequal IJC/SJC replicate lists are paired on their common prefix); rows dropped for low coverage and for missing counts are counted separately. The filter runs on the combined frame of all uploaded files: annotation-only `fromGTF.*` rows uploaded **together with** count files are dropped as `missing_counts`; the filter is skipped only when no uploaded file has count columns
- **Analysis management** &mdash; Create, list, navigate, and delete named analyses
- **Event browser** &mdash; Sortable (one server-side sort on FDR, p-value, gene symbol or |&Delta;&Psi;|), filterable, paginated table (50 events per page) of all splicing events with support for filtering by event type, gene symbol, FDR threshold, P-value, and minimum |&Delta;&Psi;|; lazy-loaded Manhattan plot; show / hide toggle for the per-replicate PSI columns
- **Dark mode** &mdash; Toggle-able theme with persistent preference via `localStorage`
- **Internationalisation** &mdash; French (default) / English language switcher; all UI strings are externalized

### Splice Site Analysis (SE events)

- **Donor (5'SS) and acceptor (3'SS) sequences** &mdash; 9 nt and 23 nt windows around splice junctions with GT-AG canonical check
- **Polypyrimidine tract (PPT)** &mdash; Score (C+T fraction) and longest consecutive pyrimidine run in the ~47 nt upstream of the 3'SS
- **Branch-point detection** &mdash; Rule-based yUnAy / YNYTRAY motif search restricted to candidates whose branch adenosine lies 18&ndash;44 nt upstream of the 3'SS (branch A mandatory), with positional scoring (0&ndash;7 scale), the distance from the branch A to the exon start, and the matched 7-mer and its position
- **Exon and intron sizing** &mdash; Skipped exon length plus upstream and downstream intron sizes (both mean and median are computed; SVG exon diagrams and PDF comparison tables display **mean** values)
- **Aggregate pattern analysis** &mdash; Position Weight Matrices (PWM), IUPAC consensus sequences, and statistical summaries across all SE events
- **Sequence source flexibility** &mdash; Primary extraction from local GRCh38 FASTA via `samtools faidx` (batched, chunked at 5 000 regions per call, with chunk-halving retry on rejected **or timed-out** chunks so that only invalid regions are blanked), with automatic per-event Ensembl REST API fallback when FASTA is unavailable (used by both the per-event endpoint and the background computation)

### Deep Splice Analysis

A second-pass module that partitions events into **significant** and **non-significant** groups using user-defined FDR and |&Delta;&Psi;| thresholds (and an optional p-value maximum), then runs the following analyses across groups:

- **Pattern comparison** &mdash; Side-by-side group statistics: GT-AG canonical rates, PPT score distributions, exon/intron size distributions, frame-class breakdown, comparison sequence logos; 20 tests (Welch's t-test **and** Mann-Whitney U for each of the 7 continuous metrics, two-proportion z-test for the 6 proportions) with Benjamini-Hochberg q-values across the panel
- **hnRNP motif enrichment** &mdash; rMAPS2-inspired analysis scanning seven genomic regions around each SE event (both ends of each flanking intron) for 19 consensus hnRNP binding motifs; two tests per motif–region pair (presence two-proportion z-test and density Mann-Whitney U), each family Benjamini-Hochberg corrected (q &lt; 0.05) across the 133 pairs. The enrichment runs as a **background job** per deep analysis (in-process result cache, stage / progress reporting, explicit retry) so that large datasets no longer hit reverse-proxy request time-outs
- **Pathway enrichment (Enrichr)** &mdash; Significant-event gene symbols submitted to the Enrichr REST API against five curated gene-set libraries; top 10 terms per library by adjusted p-value, overlap reported as `k/n` from the library GMT sizes
- **Permutation testing** &mdash; Per-event |&Delta;&Psi;| significance testing against a null distribution of permuted sample labels: exact enumeration of every label split when C(n, n1) &le; 5000, Monte-Carlo sampling with the Phipson &amp; Smyth correction otherwise; the fraction of exact tests, the minimum attainable p-value and the replicate design are reported. Auxiliary **metric permutation tests** (PPT score, exon size, in-frame fraction, canonical-site score) compare the events with &Delta;&Psi; &lt; 0 and &Delta;&Psi; &gt; 0

### MANE Frame Annotation

- Maps each skipped exon to its **MANE Select** transcript via the local GFF3 file (transcripts indexed by their `tag=MANE_Select` attribute; MANE Plus Clinical transcripts are kept in a separate index) or the Ensembl REST API (CDS features filtered by their transcript `Parent`)
- Classifies the frame impact from the overlap of the exon with the **coding extent** of the transcript (start codon to stop codon): `in_frame` (coding length divisible by 3), `frameshift`, `non_coding`, or `unknown`; a companion `frame_region` (`CDS`, `partial`, `UTR5`, `UTR3`, `non_coding`, `unknown`) records the positional context
- Corrects the skipped-exon boundaries with the matching MANE exon before sequence extraction when the local GFF3 is loaded (overlap and flanking strategies, §3)
- Caches successful lookups in a local SQLite database (WAL mode for concurrent access) to minimize redundant API calls

### Gene Annotations & Interactions

- **Gene autocomplete** &mdash; Candidate ("mutated") genes are picked on the New-Analysis page with an autocomplete by HUGO symbol (minimum 2 characters) backed by **mygene.info** (wildcard prefix query) with an Ensembl REST exact-lookup fallback
- **PanelApp disease panels** &mdash; Queries PanelApp Australia (`panelapp-aus.org`, with PanelApp UK fallback) for diagnostic gene panel membership and confidence ratings (green/amber/red); circuit breaker prevents cascade timeouts on unreachable instances
- **Gene Ontology** &mdash; Retrieves GO terms (Biological Process, Molecular Function, Cellular Component) via mygene.info
- **UniProt** &mdash; Fetches reviewed protein function summaries
- **STRING-DB interactions** &mdash; Channel-level evidence between each candidate gene and each significant-event gene, with co-mentioning PMIDs from Europe PMC when text-mining evidence exists
- All external annotation calls are **best-effort**: on any failure the corresponding field is returned empty / null instead of failing the request (per-call read timeouts: PanelApp 12 s, UniProt 15 s, mygene.info 8 s, STRING / Europe PMC 10 s, Ensembl REST 8–15 s)

### Export

- **PDF report** &mdash; Multi-page PDF report with a **section selector modal** for choosing which sections to include (`sections=a,b,c,d,e,f,top_events`). Sections: global analysis summary, significant SE events with splice feature tables, deep analysis sections (pattern comparison with comparison logos, frame breakdown and a summary schematic on a landscape page; permutation table at K = 50 / 100 / 250 / 500 iterations, collapsed to a single "exact enumeration" row when every event is enumerated exactly; hnRNP motif enrichment with a best-motif-per-protein &times; region heatmap; pathway enrichment with significant p-values bolded and starred), top SE events, methodology appendix, bibliographic references (numbered in order of first appearance; the 18 hnRNP-only references are appended only when the hnRNP section is selected), and statistical methods. Each report ends with a closing note pointing to the SpliceAnalyzer repository. Two endpoints: one for a whole analysis, one scoped to a deep analysis. When `SVG_EXPORT_DIR` is set, every figure of the deep-analysis PDF is also written as a standalone SVG file. The export answers **409** while splice features are still being computed, and (deep-analysis PDF) while the hnRNP job is still running
- **Excel export (deep analysis only)** &mdash; Interactive modal for selecting annotation column groups (`core`, `panelapp`, `go`, `stringdb`) before download; optional groups are fetched in parallel at export time; a second "Summary" sheet records the thresholds and the per-type event counts

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
                     │ REST (JSON), proxied by Next.js (/api → API_URL)
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

**External services** (outbound HTTPS from backend, all best-effort):

| Service | Purpose |
|---------|---------|
| [Ensembl REST](https://rest.ensembl.org/) | MANE Select transcript lookup and CDS intervals (fallback when the local GFF3 is missing), genomic sequence fallback when the FASTA is unavailable, exact gene lookup |
| [mygene.info](https://mygene.info/) | Gene autocomplete (primary), Gene Ontology terms |
| [UniProt](https://www.uniprot.org/) | Protein function summaries |
| [STRING-DB v12](https://string-db.org/) | Protein-protein interactions |
| [Europe PMC](https://europepmc.org/) | Literature PMIDs |
| [PanelApp AU](https://panelapp-aus.org/) / [PanelApp UK](https://panelapp.genomicsengland.co.uk/) | Disease gene panel membership (AU first, UK fallback) |
| [Enrichr](https://maayanlab.cloud/Enrichr) | Pathway and gene-set enrichment |

All three application services are orchestrated with **Docker Compose** (see [The two compose files](#the-two-compose-files)).

---

## Project Structure

```
SpliceAnalyzer/
├── README.md
├── docker-compose.yml                   # canonical stack (downloads the MANE GFF3 at startup)
├── .env.example
├── check_cors.sh                        # CORS probe of the public APIs (for the in-browser successor)
├── MERGE_NOTES_dev.md                   # merge request text of this closing version
├── ORIGINAL_CODE_FIXES.md               # defect list of the original code and their status
├── SPLICEANALYZER_IN_BROWSER_SPEC.md    # specification of the in-browser successor
├── rMAPS2.pdf, gkaa237_supplemental_file.pdf   # rMAPS2 paper + supplement (motif catalogue source)
└── rmats-viz/
    ├── docker-compose.yml               # variant: backend health check, no MANE download
    ├── data/
    │   ├── setup_grch38_fasta.sh        # downloads + indexes GRCh38 (the only FASTA provisioning path)
    │   └── setup_mane_gff3.sh           # downloads the MANE GFF3 manually
    ├── backend/
    │   ├── Dockerfile                   # python:3.12-slim + samtools
    │   ├── requirements.txt
    │   ├── alembic.ini
    │   ├── alembic/versions/            # 0001 … 0018
    │   ├── tests/                       # pytest suite (11 files, 164 tests)
    │   │   ├── test_chunked_upload.py
    │   │   ├── test_export_pdf.py
    │   │   ├── test_hnrnp_jobs.py
    │   │   ├── test_hnrnp_motifs.py
    │   │   ├── test_mane_cache_concurrency.py
    │   │   ├── test_parser_coverage.py
    │   │   ├── test_parser_event_types.py
    │   │   ├── test_permutation.py
    │   │   ├── test_schema_drift.py
    │   │   ├── test_sequence_features.py
    │   │   ├── test_stats.py
    │   │   └── e2e/                     # end-to-end scenario on a real PostgreSQL (README inside)
    │   │       ├── make_data.py         # synthetic genome, MANE GFF3, rMATS files, expected values
    │   │       ├── run_e2e.py           # 136 assertions
    │   │       └── samtools             # pysam-based samtools emulation for hosts without samtools
    │   └── app/
    │       ├── main.py                  # app, lifespan (stale-state reset, FASTA readiness log), /health, /debug/fasta
    │       ├── config.py
    │       ├── database.py
    │       ├── models/
    │       │   ├── analysis.py          # Analysis (compute_status / compute_error), SampleGroup
    │       │   ├── event.py             # SplicingEvent
    │       │   ├── splice.py            # EventSpliceFeature
    │       │   └── deep_analysis.py     # DeepAnalysis, DeepAnalysisEvent
    │       ├── routers/
    │       │   ├── analyses.py          # Analysis CRUD + single-shot and chunked upload
    │       │   ├── events.py            # Event listing + Manhattan data
    │       │   ├── genes.py             # Gene search / lookup
    │       │   ├── annotations.py       # PanelApp, GO, UniProt, STRING
    │       │   ├── splice.py            # Splice feature compute + progress + patterns + permutation
    │       │   ├── deep_analyses.py     # Deep analysis CRUD + pattern comparison + hnRNP job endpoint + Enrichr
    │       │   └── export.py            # Excel + PDF generation
    │       ├── schemas/
    │       ├── utils/
    │       │   └── composite_key.py     # rMATS column map (SE/RI/MXE/A3SS/A5SS)
    │       └── services/
    │           ├── parser.py            # event-type detection, coverage filter, type-aware dedup
    │           ├── sequence.py          # samtools faidx wrapper (chunked batching, halving retry), Ensembl fallback
    │           ├── splice_features.py   # GT-AG, PPT score, branch-point (18–44 nt window), PWM / consensus
    │           ├── mane.py              # MANE Select annotation (SQLite cache, Ensembl REST fallback)
    │           ├── mane_local.py        # Local GFF3-based MANE annotation + exon boundary correction
    │           ├── ensembl.py           # mygene.info autocomplete + Ensembl REST lookup
    │           ├── gene_ontology.py     # mygene.info → GO terms
    │           ├── uniprot.py           # UniProt → protein function
    │           ├── stringdb.py          # STRING-DB → PPI + Europe PMC PMIDs
    │           ├── panelapp.py          # PanelApp AU/UK + circuit breaker + 6 h cache
    │           ├── stats.py             # shared z-test, Mann-Whitney U, BH, normal CDF
    │           ├── permutation.py       # Permutation tests for ΔΨ + splice metrics
    │           ├── hnrnp_motifs.py      # hnRNP motif enrichment (rMAPS2-inspired, 7 regions)
    │           ├── hnrnp_jobs.py        # background hnRNP jobs + in-process result cache
    │           └── enrichr.py           # Enrichr pathway enrichment
    └── frontend/
        ├── Dockerfile                   # node:20-alpine, `npm run dev`
        ├── next.config.mjs              # /api/* rewrite to API_URL, 10-min proxy timeout
        ├── package.json
        └── src/
            ├── app/
            │   ├── analyses/page.tsx                    # analysis list
            │   ├── analyses/new/page.tsx                # upload (chunked) + candidate genes
            │   ├── analyses/[id]/page.tsx               # event browser + Manhattan
            │   ├── analyses/[id]/deep-analysis/page.tsx # deep-analysis list + creation
            │   └── analyses/[id]/deep-analysis/[deepId]/page.tsx
            ├── components/
            │   ├── events/               # EventsTable, EventsTableColumns, ManhattanPlot, Top10View (deep-analysis card view)
            │   ├── upload/               # FileUploadZone (type / mode badges), GroupMappingDialog
            │   ├── genes/GeneAutocomplete.tsx
            │   ├── deep-analysis/PatternComparisonPanel.tsx
            │   ├── top10/
            │   │   ├── HnRNPMotifPanel.tsx   # hnRNP enrichment table + heatmap (7 regions), polls the background job
            │   │   ├── EnrichrPanel.tsx       # Enrichr pathway panel
            │   │   ├── PermutationPanel.tsx   # Exact / Monte-Carlo permutation results + metric permutations
            │   │   ├── ComputeProgressBar.tsx # splice-feature computation progress
            │   │   ├── SidebarNav.tsx         # Deep analysis sidebar
            │   │   ├── AnnotatedCard.tsx, SpliceView.tsx, ExonDiagram.tsx, SpliceSiteTrack.tsx, PPTTrack.tsx,
            │   │   ├── MANETranscriptTrack.tsx, ConsensusLogoPanel.tsx, MotifPatternPanel.tsx, MutatedGenePanel.tsx
            │   │   └── ...
            │   ├── PdfExportModal.tsx, ExcelExportModal.tsx, ScienceNote.tsx
            │   └── layout/AppHeader.tsx       # language + theme switchers
            ├── contexts/                # LanguageContext, ThemeContext
            ├── lib/
            │   ├── api/                 # one client module per router
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
- For full splice analysis: GRCh38 reference genome FASTA (~3 GB decompressed)

### The two compose files

| File | Role | Differences |
|------|------|-------------|
| `docker-compose.yml` (repository root) | **Canonical stack** | Backend command downloads the MANE GFF3 (~3 MB, NCBI release 1.4, then 1.3) into `rmats-viz/data/` when it is missing, runs `alembic upgrade head`, then starts Uvicorn |
| `rmats-viz/docker-compose.yml` | Variant | Backend health check on `/api/v1/health` (the frontend waits for it), `--log-level info`, **no MANE GFF3 download** (provision it with `rmats-viz/data/setup_mane_gff3.sh`), sets `NEXT_PUBLIC_BACKEND_URL` (unused by the code) |

Both bind-mount the backend and the frontend sources, mount `rmats-viz/data` at `/data`, and pass `CORS_ORIGINS='["http://localhost:3000","http://frontend:3000"]'` to the backend. Neither starts Uvicorn with `--reload` (see [Contributing](#contributing)).

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
2. Build the **FastAPI backend** &mdash; installs Python dependencies + samtools, downloads the MANE GFF3 annotation file if missing (root compose file only), runs Alembic migrations, then starts Uvicorn on port 8000
3. Build the **Next.js frontend** &mdash; installs npm packages, starts the dev server on port 3000
4. The GRCh38 FASTA is **not** downloaded by the backend. Provision it once with `bash rmats-viz/data/setup_grch38_fasta.sh` (see below); the backend only logs at startup whether the FASTA, its `.fai` index and `samtools` are available, and picks the files up as soon as they exist (no restart needed).

**3. Open the application**

| Service | URL |
|---------|-----|
| Frontend (UI) | http://localhost:3000 |
| API docs (Swagger) | http://localhost:8000/docs |
| Health check | http://localhost:8000/api/v1/health |
| FASTA diagnostics | http://localhost:8000/api/v1/debug/fasta |

> **Note:** The application runs without the FASTA. Size-based features and MANE frame annotation work as before; the splice-site windows (donor / acceptor / PPT, hence the branch point) are then fetched **per event from the Ensembl REST API** (slow, network-bound). Only the **hnRNP region scan** requires the local FASTA and is skipped without it.

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

### MANE GFF3 Setup

The local MANE annotation file (`MANE.GRCh38.ensembl_genomic.gff.gz`, ~3 MB) is read in full with `gzip` at first use; no tabix index is needed. The root compose file downloads it automatically when it is missing; with the variant compose file, or to refresh it, run:

```bash
bash rmats-viz/data/setup_mane_gff3.sh
```

Without the file every event falls back to the Ensembl REST API for its MANE annotation (2–3 calls per event) and no exon-boundary correction is applied.

---

## Configuration

Copy `.env.example` to `.env` and adjust as needed (the backend reads `.env` through pydantic-settings; the compose files pass the same variables explicitly):

| Variable | Default | Description |
|----------|---------|-------------|
| `POSTGRES_USER` | `rmats` | PostgreSQL username |
| `POSTGRES_PASSWORD` | `rmats` | PostgreSQL password |
| `POSTGRES_DB` | `rmatsdb` | PostgreSQL database name |
| `DATABASE_URL` | `postgresql+asyncpg://rmats:rmats@db:5432/rmatsdb` | SQLAlchemy async connection string |
| `CORS_ORIGINS` | `["http://localhost:3000"]` | Allowed CORS origins (JSON array); the compose files set `["http://localhost:3000","http://frontend:3000"]` |
| `GRCH38_FASTA` | `/data/GRCh38.fa` | Path to indexed GRCh38 FASTA inside the container |
| `SAMTOOLS_BIN` | `samtools` | samtools binary name or full path |
| `MANE_CACHE_DB` | `/data/mane_cache.db` | SQLite cache for MANE lookups |
| `MANE_GFF3` | `/data/MANE.GRCh38.ensembl_genomic.gff.gz` | Local MANE GFF3 annotation file |
| `SVG_EXPORT_DIR` | *(unset)* | Optional directory where the deep-analysis PDF export also writes every figure as a standalone SVG (one sub-directory per deep analysis). Unset (default) &rarr; no SVG side files are written |
| `UPLOAD_TMP_DIR` | `/tmp/spliceanalyzer_uploads` | Directory where the chunked browser uploads (`POST /api/v1/analyses/uploads`) are assembled, one sub-directory per upload session |
| `UPLOAD_SESSION_TTL_HOURS` | `24` | Upload sessions older than this (never finalized or aborted) are purged, best effort, whenever a new session is opened |
| `API_URL` *(frontend)* | `http://localhost:8000` | Target of the Next.js rewrite of `/api/*` (`next.config.mjs`); the compose files set `http://backend:8000` |

> **MANE cache behavior:** Successful lookups (local GFF3 or Ensembl) are cached in `mane_cache.db` (SQLite with WAL journal mode) to avoid repeated work. Failed lookups (network errors, no MANE transcript found, `unknown` frame class) are **not** cached there and are retried on the next compute run; the per-event endpoint (`GET /splice/feature/{id}`) additionally retries a missing MANE annotation at most once per 24 h, using the feature row's `computed_at` as a negative-result timestamp.

> **Compute state columns:** the splice-feature background computation persists its state in the `analyses` table (`compute_status` = `idle` | `running` | `done` | `error`, plus `compute_error`) rather than in process memory, so progress polling and the export readiness check are correct with several Uvicorn workers and after a crash. While it runs, the task refreshes `analyses.updated_at` after every 2 000-event chunk (heartbeat). On startup, every worker resets to `error` ("interrupted by restart") only the analyses left in `running` **whose heartbeat is older than 30 minutes**; a computation alive in another worker keeps its heartbeat fresh and is left alone. `POST /splice/compute` may likewise re-claim a stale `running` row.

---

## Usage Guide

### Creating an Analysis

1. Navigate to the **New Analysis** page (`/analyses/new`)
2. Drag and drop one or more rMATS output files (e.g., `SE.MATS.JC.txt`, `A5SS.MATS.JCEC.txt`)
3. The event type and the counting mode (JC / JCEC) are inferred from the `<TYPE>.MATS.<JC|JCEC>` token of the filename (the upload zone shows a badge for each); files whose name is uninformative are classified from their header by the backend (A3SS / A5SS files must carry the type in their name)
4. Define sample group names for your conditions and, optionally, the candidate ("mutated") genes of the cohort with the gene autocomplete
5. Click **Create** &mdash; the browser sends the files in **512 KB chunks** (progress bar with the percentage of bytes sent and the current file), then the parser ingests the TSV, filters low-coverage events (&lt;10X), deduplicates with the per-type rules of [§2](#2-ingestion-deduplication), and stores events in PostgreSQL ("Processing…"). The response reports the number of rows actually inserted and any `warnings`, which the upload page displays before opening the analysis

> **Why chunks?** Reverse proxies in front of the API &mdash; the GitHub Codespaces port-forwarding proxy, a default nginx `client_max_body_size` &mdash; reject request bodies larger than about 1 MB with HTTP 413, while rMATS outputs are typically 10–100 MB. The browser therefore opens an upload session, `PUT`s each file as a sequence of ≤ 512 KB raw chunks (sequential, retried up to 3 times; the server acknowledges a resent last chunk without appending it) and finalizes with the analysis metadata. Files are assembled under `UPLOAD_TMP_DIR` and the session directory is removed after finalize or abort, or purged after `UPLOAD_SESSION_TTL_HOURS`. The single-shot `POST /api/v1/analyses` (whole files in one multipart request) is unchanged and remains the simplest option for `curl` / API clients that talk to the backend directly.

### Browsing Events

The event browser (`/analyses/{id}`) provides a fully interactive table with:

- **Column sorting** &mdash; Click the FDR, gene symbol, &Delta;&Psi; or |&Delta;&Psi;| header to sort ascending/descending (the server has no signed &Delta;&Psi; sort, so both &Delta;&Psi; headers sort on |&Delta;&Psi;|); a sort drop-down offers the same keys plus p-value. Sorting is performed once, server-side (`sort_by` / `sort_dir`), there is no additional client-side re-ordering of the current page
- **Filters** &mdash; Event type selector, gene symbol search, and log-scale sliders for FDR max, P-value max and minimum |&Delta;&Psi;|; a reset button
- **Pagination** &mdash; 50 events per page (the API accepts 1–200)
- **Direction-of-effect badges** &mdash; Visual indicators for exon skipping vs. inclusion
- **PSI columns toggle** &mdash; Show / hide the per-replicate `IncLevel1` / `IncLevel2` columns
- **Manhattan plot** &mdash; Toggle button; the data (natural chromosome order, capped at 50 000 points, see [Events](#events)) is fetched only when the panel is opened
- Links to **Compute** (splice features), the **deep-analysis** list and **Delete**

### Deep Splice Analysis

The deep analysis page (`/analyses/{id}/deep-analysis`) enables a two-group partitioning of the events for comparative analysis of the SE events. The workflow is:

**1. Create a deep analysis** &mdash; Set FDR (default 0.05) and |&Delta;&Psi;| (default 0.1) thresholds and, optionally, a p-value maximum (applied when tagging events) to partition events into significant and non-significant groups. Pick the modules to show: `splice` (splice site analysis), `motifs` (motif patterns / PWM), `permutation`, `frame`, `hnrnp`, `enrichr`, `stringdb` (Interactions; enabled by default when the analysis has candidate genes). `splice`, `permutation` and `frame` are selected by default. The module list is stored with the deep analysis but only interpreted by the frontend (it decides which tabs and panels are shown); the backend endpoints are available regardless. Each configuration is saved as a named deep analysis object (with the requested `permutation_iterations`, when supplied) and can be reopened later.

**2. Explore the results** (`/analyses/{id}/deep-analysis/{deepId}`) via the sidebar navigation:

| Tab (English label) | Mode | Content |
|------|------|---------|
| **Annotated Events** | `gene` | Cards for the significant events only, with full per-event annotations (see below); fetched in pages of 200 from the paginated events endpoint |
| **Interactions** | `stringdb` | STRING-DB interactions between the analysis' candidate genes and the significant-event genes (when the `stringdb` module is enabled and candidate genes exist) |
| **Recur. Motifs** | `motifs` | Aggregate pattern panel of the significant SE events: donor / acceptor / flanking-site PWMs and IUPAC consensus, size distributions, frame breakdown (`GET /splice/patterns` restricted to the deep analysis) |
| **Consensus Sites** | `splice` | Pattern comparison panel: side-by-side aggregate statistics for significant vs. non-significant groups (logos, GT-AG rates, PPT scores, frame breakdown) with the 20 statistical tests, above the event cards |
| **hnRNP Motifs** | `hnrnp` | hnRNP motif enrichment analysis — presence / density table over seven regions and protein × region heatmap, fed by the background job |
| **Enrichr** | `enrichr` | Pathway enrichment results across five gene-set libraries |

The splice-feature computation progress bar is shown above the tabs when the `splice` module is enabled, and the **Permutation** panel is shown below the tabs when the `permutation` module is enabled.

#### Annotated Events

Each significant SE event is displayed as a card containing:

- **SpliceView** &mdash; Schematic of the splicing event with inclusion/exclusion levels per sample group
- **ExonDiagram** &mdash; Interactive exon-intron diagram annotated with donor/acceptor sites, PPT window, and branch-point position (marker on the branch adenosine)
- **SpliceSiteTrack** &mdash; All four SE splice sites (upstream donor, skipped 5'SS, skipped 3'SS, downstream acceptor) with sequence and canonical check
- **MANE transcript track** &mdash; Linear MANE Select transcript with the skipped exon highlighted (`GET /splice/mane_transcript/{event_id}`)
- **Sequence source badge** &mdash; Indicates whether sequences were extracted from the local GRCh38 FASTA or the Ensembl REST fallback
- **Gene annotation tabs** &mdash; GO terms (up to 4 per category), PanelApp badge and panel list, UniProt function summary for the host gene
- **ScienceNote** &mdash; Collapsible citation widgets linking each algorithm to its primary literature

Significant events of another type (RI, A3SS, A5SS, MXE) get the same card without the splice-site tracks (see [Scope](#scope-and-known-limitations)).

> **PermutationPanel** (per-event empirical |ΔΨ| p-values with null-distribution histogram; iteration slider 50–2 000 in steps of 50, used only for the Monte-Carlo path — designs with ≤ 5000 label splits are enumerated exactly and flagged with an *exact* badge; the panel also shows the fraction of exact tests, the replicate design, the minimum attainable p-value and the table of the auxiliary metric permutations) is a separate panel on the deep-analysis page, not embedded in individual event cards. The PDF report runs the test at 50, 100, 250 and 500 iterations (a single "exact enumeration" row when every event is enumerated exactly).

#### hnRNP Motif Panel

- The first request long-polls the background job for up to 15 s, so small datasets get their table in one round trip; while the job reports `status: running` the panel polls every 2 s and shows the stage (**Extracting sequences** / **Scanning motifs** / **Statistical tests**), the overall percentage and the elapsed time; on `status: error` the message is shown with a **Retry** button (`retry=true`)
- Filterable table of motif–region associations ranked by the smaller of the two adjusted p-values (presence z-test q and density Mann-Whitney q are both shown)
- Toggle: significant only (either test q &lt; 0.05) vs. all 133 (19 motifs × 7 regions) combinations
- Protein and region drop-downs for focused exploration
- Heatmap: protein family × genomic region, colour-coded by enrichment direction (red = enriched in significant, blue = depleted), cell borders carrying the established regulatory effect (ESE / ESS / ISE / ISS)

#### Enrichr Panel

- Results grouped by library (KEGG, GO BP, GO MF, Reactome, WikiPathways), bars scaled by combined score, expandable rows listing the overlapping genes
- Library filter drop-down

### Gene Annotations

There is no standalone gene-annotation page. Gene annotations appear in two places:

- **Candidate genes** are chosen on the New-Analysis page with the autocomplete (mygene.info prefix search, Ensembl REST fallback; `GET /api/v1/genes/search`) and drive the Interactions tab and the STRING column of the Excel export
- **Each significant event's gene** is annotated on its card (`GET /api/v1/annotations/gene/{symbol}`):
  - **PanelApp** &mdash; Disease panels and confidence level (green = diagnostic grade); the "view on PanelApp" link opens the UK site
  - **Gene Ontology** &mdash; Up to 4 terms per category (BP, MF, CC) are displayed (the service returns up to 8 per category)
  - **UniProt** &mdash; Reviewed protein function summary

### Exporting Results

#### Excel Export (Deep Analysis only)

Excel export is available exclusively from the **Deep Analysis** page. It exports only the significant events tagged in the deep analysis (all event types), enriched with optional external annotations.

1. Open a deep analysis and click the **Export Excel** button
2. A modal lets you select which column groups to include:

| Group | Columns | Source |
|-------|---------|--------|
| `core` *(always)* | Gene, Gene ID, Type, Chromosome, Strand, Exon Start, Exon End, Exon Size, p-value, FDR, ΔΨ, \|ΔΨ\|, PSI *group 1*, PSI *group 2*, Donor Site, Canonical GT, Acceptor Site, Canonical AG, PPT Score, Max Y Run, BP Found, BP Distance, Frame, Region, CDS Length, MANE Transcript, Exon Rank (splice-feature columns filled for SE events only) | Local DB |
| `panelapp` | PanelApp Confidence, PanelApp Panels (top 3) | PanelApp REST API |
| `go` | GO:BP, GO:MF, GO:CC (top 3 terms each) | mygene.info |
| `stringdb` | STRING Max Score (highest combined score vs. all candidate genes) | STRING-DB v12 |

3. Optional groups are fetched concurrently (semaphore-limited to 20 parallel requests); PanelApp lookups are capped at 25 s total to handle slow endpoints gracefully
4. The resulting `.xlsx` file (`rmats_<deep analysis name>_significant.xlsx`) includes styled headers, row banding, auto-sized columns and a **Summary** sheet (thresholds, number of significant events, count per event type)
5. Boolean feature columns (`donor_is_gt`, `acceptor_is_ag`, `bp_motif_found`) are stored as native Excel booleans — their display (`TRUE`/`FALSE` or locale equivalents) depends on your Excel locale setting
6. The Excel export has no readiness gate: it exports whatever features exist at that time

#### PDF Export

Click the **Export PDF** button to open the **section selector modal**, which lets you toggle individual report sections on or off before generating (query parameter `sections`, comma-separated keys; all sections when omitted). The analysis-level report (`/export/{id}/pdf`) covers all events of the analysis; the deep-analysis report (`/export/{id}/deep-analysis/{deep_id}/pdf`) is scoped to the events of the deep analysis. The report can include:

| Key | Section | Content |
|-----|---------|---------|
| `a` | Global Analysis Summary | Analysis metadata, event counts, SE splice feature statistics and figures (logos, size distributions, frame breakdown) for all events in scope |
| `b` | Significant Events *(deep only)* | The same statistics and figures for the significant events (FDR ≤ threshold, \|ΔΨ\| ≥ minimum) |
| `c` | Significant vs Non-Significant Comparison *(deep only)* | Feature comparison table (p and q for the 20 tests), frequency-mode donor / acceptor / flanking-site comparison logos, reading-frame comparison (pie charts of in-frame / frameshift / non-coding proportions per group), and the **Summary Schematic**: a landscape page with the exon-intron architecture, consensus splice-site sequences, PPT, branch point, in-frame %, intron sizes, mean ΔΨ and per-feature significance markers (★) |
| `d` | Permutation Test *(deep only)* | Percentage of significant events at p &lt; 0.05 / 0.01 for K = 50, 100, 250 and 500 iterations run on the significant events (seed 42), fraction of exactly enumerated tests, replicate design and minimum attainable p-value; a single "exact enumeration" row when every event is enumerated exactly |
| `e` | hnRNP Enrichment *(deep only)* | Top 30 motif–region associations significant in at least one test (presence or density, BH q &lt; 0.05), with both q-values; heatmap of the **best motif per protein × region**, coloured by the smaller of the two q-values (as in the web panel); list of non-significant associations. Taken from the background job's cached result (409 while the job is still running; skipped if the job failed) |
| `f` | Pathway Enrichment *(deep only)* | Top 10 terms per library; overlap shown as `k/n`; adjusted p-values &lt; 0.05 are **bolded and starred (★)** for quick identification |
| `top_events` | Top SE Events | The 20 SE events (significant ones in a deep report) ranked by FDR then \|ΔΨ\|: exon size, FDR, ΔΨ, GT/AG flags (`?` when a window is truncated), frame class; followed by the list (up to 30) of events whose skipped-exon coordinates were corrected with the MANE flanking method |
| — | Appendix A | Pipeline methodology (see below); always emitted, subsections follow the selected sections |
| — | Appendix B | Bibliographic references, numbered in order of first appearance. The always-on entries (rMATS, splice-site statistics, PPT [Coolidge 1997], branch point [Gao 2008, Leman 2020], MANE, Ensembl, Phipson & Smyth, Enrichr) are emitted first; the 18 hnRNP-only entries (Hwang 2020 … Witten & Ule 2011) are appended only when section `e` is selected. The list lives in `routers/export.py` |
| — | Appendix C | Statistical methods |
| — | Closing note | Italicised paragraph pointing to the SpliceAnalyzer repository for full documentation and methodology |

Both PDF endpoints answer **409 Conflict** while the splice-feature computation of the analysis is `running` and incomplete (the UI shows a "computation in progress" alert); once the task has finished, even partially, the export proceeds with what was computed.

The **Appendix A — Pipeline Methodology** section of the PDF covers:

1. **Input preprocessing** — Coverage filtering (≥ 10X mean junction coverage per group) and boundary-based deduplication of SE events (events sharing at least one boundary within ±50 bp are collapsed by retaining the lowest-FDR event; see [§2](#2-ingestion-deduplication) for the rules applied to the other event types)
2. **Splicing event detection** — rMATS likelihood-ratio test, JC vs JCEC modes
3. **Splice site annotation** — 5'SS/3'SS window extraction, GT-AG canonical check (truncated windows reported as unknown), PPT scoring, branch-point yUnAy / YNYURAY search (branch adenosine mandatory, candidates restricted to 18–44 nt upstream of the exon start, distance measured from the branch A)
4. **Sequence logos** — Frequency-mode PWM rendering (no information-content scaling)
5. **Reading frame classification** — MANE Select transcript mapping, in_frame/frameshift/non_coding classes, NMD caveat note (PTC > 50 nt upstream rule)
6. **MANE Select annotation** — Local GFF3 lookup with Ensembl REST fallback, exon boundary correction (overlap and flanking strategies)
7. **Deep analysis** *(when linked)* — Welch's t-test, Mann-Whitney U and two-proportion z-test for group comparison (test counts computed from the panel, BH q-values), permutation testing with exact enumeration or Phipson & Smyth correction
8. **hnRNP motif enrichment** *(when linked)* — rMAPS2-inspired framework, seven genomic regions, 19 motifs, presence z-test and density Mann-Whitney U test, BH FDR correction per test family, regulatory-effect annotations
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
- The filter runs once on the **combined** frame of all files of the upload. When the four count columns are absent altogether (an upload made only of annotation-only `fromGTF.*` files) the filter is skipped explicitly; when annotation-only rows are mixed with count files they have no counts and are dropped as `missing_counts`

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
- **Chunk-halving retry** — when samtools rejects a chunk (`CalledProcessError`) or the call times out (`TimeoutExpired`), the chunk is split in halves and retried recursively down to single regions, so only the offending regions are blanked (rejected and timed-out regions are logged separately); previously one invalid region blanked the whole 5 000-region chunk
- **Empty-record safety** — `samtools faidx` emits a header with no sequence for a region beyond the contig end; the parser appends one sequence per header (including empty ones) so the i-th sequence always belongs to the i-th region, and blanks the chunk if the record count does not match the request count instead of returning shifted sequences
- **Negative-start clamp** — a region starting before position 0 (exon close to the contig start) is clamped to 0 (the returned window is then shorter than requested); `end <= start` or an unknown contig yields an empty string

Chromosome name translation is handled automatically: rMATS uses UCSC names (`chr1`–`chr22`, `chrX`, `chrY`, `chrM`), while some FASTA files use RefSeq accessions (`NC_000001.11`…). The backend reads the `.fai` index on first use (re-read while empty, so a FASTA provisioned after startup is picked up) and translates names as needed. When the FASTA is unavailable, sequences are fetched per-event from the Ensembl REST API as a fallback (`/sequence/region/human/…`, 4 s timeout per window; up to five sequential calls per event), both by the per-event endpoint and by the background computation.

The five window intervals (donor, acceptor, PPT, upstream donor, downstream acceptor; see [§4](#4-splice-site-signals)) are defined once in the pure function `splice_window_coords()`, which the batched FASTA path, the per-event FASTA path and the Ensembl fallback all share, so the three paths cannot drift apart.

For minus-strand events, extracted sequences are reverse-complemented before all downstream analyses; the complement table covers the full IUPAC alphabet (`ACGTU RYSWKM BDHV N`, upper and lower case), so ambiguity codes in the reference are not passed through unchanged.

#### MANE Exon Boundary Correction

rMATS exon coordinates come from the alignment annotation (GTF), which can differ from the **MANE Select** transcript boundaries. When this happens, splice-site sequences may be extracted at the wrong genomic position — for example, the 3'SS acceptor of a minus-strand exon can be shifted by tens of nucleotides. To correct this, the pipeline looks up the corresponding MANE exon and uses its boundaries for splice-site window extraction. The correction requires the **local MANE GFF3** (it is not attempted through the Ensembl REST path). Two strategies are applied in order:

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

On the − strand the windows are the mirror image in genomic coordinates (donor `exon_start − 6 .. exon_start + 3`, acceptor `exon_end − 3 .. exon_end + 20`, PPT `exon_end + 3 .. exon_end + 50`; the rMATS "downstream" exon is the transcript-upstream flanking exon and vice versa) and every sequence is reverse-complemented after extraction, so the transcript-oriented windows read exactly like the + strand ones.

The **GT-AG canonical rule** is checked by inspecting positions +1/+2 of the donor window (must be `GT`) and positions −2/−1 of the acceptor window (must be `AG`). The boolean flags `donor_is_gt` and `acceptor_is_ag` are stored per event; they are `null` (unknown) when the window is too short to read the dinucleotide (truncated at a contig end).

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
| `bp_score` | Best positional score (0–7) among the candidates of the window; 0 when no candidate lies in the window |
| `bp_distance` | Distance (nt) from the **branch adenosine** to the exon start (3'SS); `null` when no branch point is called |
| `bp_position` | 0-based index of the matched 7-mer in `ppt_seq` (`null` when not found) |
| `bp_motif` | The matched 7-mer (`null` when not found) |

### 7. MANE Select Frame Classification

Each skipped exon is mapped to its **MANE Select** transcript (the clinically validated representative transcript per gene, from the MANE consortium). The lookup uses a two-tier approach:

1. **Local GFF3** — If `MANE.GRCh38.ensembl_genomic.gff.gz` is present, it is parsed directly with `gzip` (fast, no network, no tabix index required). Transcripts are indexed by the GFF3 `tag=` attribute: the transcript tagged `MANE_Select` is the one used for annotation, while `MANE_Plus_Clinical` transcripts are kept in a separate index (`get_mane_plus_clinical`) so that a Plus Clinical transcript listed first in the file can no longer be picked by mistake. Genes with no `MANE_Select` tag at all (old files) fall back to the first transcript seen (counted in the load log)
2. **Ensembl REST API** — Fallback when the GFF3 is unavailable; queries `/lookup/id/{gene_id}` + `/overlap/id/{transcript_id}` for exon and CDS features. `overlap/id/{tx}?feature=cds` returns the CDS of **every** transcript overlapping the span, so the CDS features are filtered by their transcript `Parent` before use

In both paths the coding length of the exon is its overlap with the **coding extent** of the MANE Select transcript, i.e. the interval from the start codon to the stop codon: the local GFF3 path takes the span from the first to the last CDS base of the transcript, the Ensembl path merges the CDS segments into a union of intervals; for a single exon both give the same exonic overlap.

The exon is classified (`frame_class`) by its relationship to the coding extent:

| Class | Condition |
|-------|-----------|
| `in_frame` | Coding length of the exon divisible by 3 (exon fully or partially within the coding extent) |
| `frameshift` | Coding length of the exon not divisible by 3 (exon fully or partially within the coding extent) |
| `non_coding` | Exon entirely within a UTR, or transcript without CDS |
| `unknown` | No MANE Select transcript found or lookup failed |

> **No heuristic fallback:** When MANE annotation is unavailable, frame_class is set to `unknown` without attempting an `exon_size % 3` heuristic. Without transcript annotation, it is impossible to distinguish CDS exons from UTR exons, so applying the divisibility rule would misclassify non-coding exons as `in_frame` or `frameshift`. The conservative `unknown` label is intentional.

A companion `frame_region` field records the positional context: `CDS` (the exon lies entirely within the coding extent), `partial` (part of the exon lies outside the coding extent), `UTR5` / `UTR3` (no coding overlap; side chosen with respect to transcript strand), `non_coding` (the transcript has no CDS at all), or `unknown`. Events with `frame_region = partial` still receive an `in_frame` or `frameshift` classification based on the coding portion of the exon length.

Results are cached in a local SQLite database with WAL journal mode to support concurrent access (schema initialisation serialised by a process-wide lock, so the 8 annotation threads of the background computation cannot race on a fresh cache file).

> **NMD caveat:** A `frameshift` classification does not imply nonsense-mediated decay (NMD). NMD depends on the position of the premature termination codon (PTC) relative to the last exon-exon junction (the "> 50 nt upstream" rule). The application displays this as an informational note in both the UI and the PDF methodology appendix — it is **not** a computed NMD prediction. Experimental validation is required to confirm NMD susceptibility.

### 8. Permutation Testing

A permutation test assesses the significance of |&Delta;&Psi;| for each SE event by testing whether the observed group difference is larger than expected by chance:

1. Per-sample PSI values are read from `IncLevel1` / `IncLevel2` (NA replicates dropped; n<sub>1</sub> and n<sub>2</sub> valid replicates) and pooled. There are `N = C(n1 + n2, n1)` distinct ways of splitting the pool into groups of size n<sub>1</sub> and n<sub>2</sub>
2. **Exact enumeration** — when `N ≤ 5000` (e.g. any design up to 7 vs 7 replicates), *all* label splits are enumerated and the null distribution is the complete set of permuted ΔΨ values. The two-tailed p-value is `p = r / N`, where `r` is the number of splits whose |ΔΨ| ≥ the observed |ΔΨ|. No +1 correction is needed: the observed split is one of the enumerated ones, so `r ≥ 1` and `p ≥ 1/N`. With 2 vs 2 replicates there are only 6 splits (minimum p ≈ 0.167), with 3 vs 3 there are 20 (minimum p = 0.05): the resolution is limited by the design, not by the number of iterations
3. **Monte-Carlo** — otherwise, `K` random label splits are drawn (numpy, vectorised) and the empirical two-tailed p-value uses the **Phipson & Smyth (2010)** correction `p = (r + 1) / (K + 1)`; the minimum attainable p is `1 / (K + 1)`

The result reports, per event, `exact` and `n_splits`, and globally `exact_fraction` (fraction of tested events on the exact path), `min_p_attainable` (smallest p the most common replicate design can produce) and `n_replicates_g1` / `n_replicates_g2` (mode of the replicate counts). The UI iteration slider (50–2 000, step 50) only affects the Monte-Carlo path; the PDF report runs the test at K = 50, 100, 250 and 500 on the significant events (seed 42) and prints the four rows, or a single "exact enumeration" row when every event is enumerated exactly (the exact path does not depend on K).

**Sign convention:** ΔΨ = mean(PSI<sub>group1</sub>) − mean(PSI<sub>group2</sub>), consistent with rMATS `IncLevelDifference`. The null distribution is built with the same group-ordering convention, so the sign is preserved and the two-tailed test compares |ΔΨ<sub>obs</sub>| against |ΔΨ<sub>null</sub>|.

**Observed ΔΨ:** the value *displayed* (`observed_delta_psi`, and the observed histogram) is rMATS' `IncLevelDifference` when present, i.e. the same number shown everywhere else in the application; the *test statistic* is always recomputed from the replicate values that feed the null distribution, so the observed labelling is exactly one of the enumerated splits. Events where either group has no valid PSI value are skipped.

**Memory:** the global null-distribution histogram is accumulated as 40 fixed-edge bin counts on [−1, 1] while events are processed; the individual permuted values are never kept (120 k events × 500 iterations would be 60 M floats).

**Reproducibility:** a fixed seed (42 by default) makes Monte-Carlo results reproducible across runs; the exact path is deterministic regardless of the seed.

When FDR and |&Delta;&Psi;| filters are applied in the deep analysis view, the **Sig. p&lt;0.05** and **Sig. p&lt;0.01** percentages are recomputed exclusively over the filtered event subset, ensuring the values shown in the UI and PDF report are always consistent with each other.

**Auxiliary metric permutations.** The same engine is applied to four scalar splice metrics, after splitting the tested events by the sign of their ΔΨ (G1: ΔΨ &lt; 0, G2: ΔΨ &gt; 0): the PPT score, the exon size (min-max normalised once over the pooled values, a monotone transform that leaves the two-sided p-value unchanged), the in-frame fraction (1 for `in_frame`, 0 for `frameshift`, `unknown` excluded) and the canonical-site score (mean of `donor_is_gt` and `acceptor_is_ag` over the known flags). The statistic is mean(G2) − mean(G1), the exact-enumeration / Monte-Carlo rule is the same, and each result carries a 30-bin null histogram; a metric is not tested when either group is empty or fewer than 4 values are available. The grouping variable is derived from the data, so these tests are exploratory; they are displayed in the permutation panel (`metric_results`).

### 9. Sequence Logos

Position Weight Matrices (PWMs) are computed from all extracted sequences per group. Logos are rendered in **frequency mode** (matching the web app display):

```
height(b, i) = f(b, i) × H_logo
```

where `f(b, i)` is the raw nucleotide frequency of base `b` at position `i` and `H_logo` is the fixed column height. Every column fills the full height, making all positions directly comparable regardless of conservation. No information-content (bits) scaling or small-sample correction is applied. The PWM denominator counts A/C/G/T only, so the frequencies of a column sum to 1 even when the reference contains `N` or other IUPAC characters.

**Base colours:** A = green (#22c55e), C = blue (#3b82f6), G = orange (#f97316), T = red (#ef4444), defined once in `src/lib/colors.ts`. Canonical GT (+1/+2) and AG (−2/−1) positions are highlighted.

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

The regions are computed in genomic coordinates (on the − strand the 5'SS of every intron is at its genomic high end and the windows are mirrored) and minus-strand sequences are reverse-complemented before scanning. The region scan requires the **local FASTA** (no Ensembl fallback).

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

#### Background job and performance

The enrichment runs as a **background job**, one per deep analysis (`services/hnrnp_jobs.py`):

- The first `GET /deep-analyses/{id}/hnrnp-motifs` starts the job; the event coordinates are snapshotted into plain records so the job outlives the request's database session. Every later call reports the job state; a finished payload (133 rows) is kept in memory for the lifetime of the worker process, because the result is deterministic for a given deep analysis (its significance tags are fixed at creation) and FASTA. Deleting the deep analysis discards the job; `retry=true` restarts a job that ended in error (a running or finished job is always reused)
- Three stages feed a 0–1 progress value: **extract** (weight 0.40; both groups extracted concurrently in worker threads with batched `samtools faidx`), **scan** (0.30; regex scan of the 19 motifs over the 7 regions, both groups concurrently) and **compare** (0.30; the 133 pairs of tests). The API long-polls the job for `wait` seconds (default 15 s, maximum 60 s) so that small datasets get their result in one request
- The scan itself is optimised for large datasets: events-outer loop (single pass, cache-local access to each `SERegions` object); sequences guaranteed uppercase by the FASTA parser (no redundant `.upper()`); `compiled.search` early exit so the overlapping-occurrence count is only computed for hits (~50–80% skip rate), misses append a shared `0.0` density; flat pre-allocated accumulators (one hit counter and one density list per motif × region cell); per-event densities are kept because the density test is rank-based
- Measured on a real dataset in a GitHub Codespace: **1 min 40 s** for the whole job on **99 495 SE events**, after which the web panel and the PDF section are served from the cache

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

All Enrichr HTTP calls (15 s timeout each) are issued inside `asyncio.to_thread` to avoid blocking the event loop. The five library GETs are dispatched in parallel (one thread per library via `ThreadPoolExecutor`), so total network time is ~1× latency rather than 5×. Gene-set library contents are retrieved live; for publication, record the date of the call alongside the results.

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
| GT canonical rate | Two-proportion z-test | k = events with GT, n = events with a ≥ 9 nt donor window **and a known flag** (windows truncated at a contig end have `donor_is_gt = null` and are excluded from numerator and denominator) — the same denominator as the summary sections of the report |
| AG canonical rate | Two-proportion z-test | Same rule with the ≥ 23 nt acceptor window and `acceptor_is_ag` |
| Upstream donor GT rate | Two-proportion z-test | Length ≥ 9 bp guard; unknown flags excluded |
| Downstream acceptor AG rate | Two-proportion z-test | Length ≥ 23 bp guard; unknown flags excluded |
| In-frame proportion | Two-proportion z-test | In-frame events vs. events with a **known** frame class (`unknown` excluded); the frame percentages of the UI and the PDF use the same known-frames denominator and print the number of unknown events beside the bar |
| Branch point found | Two-proportion z-test | k = events with a branch-point call, n = events with a PPT sequence (the branch point is searched in `ppt_seq`); the same denominator is used by the patterns endpoint and the exports |

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

Timeouts: connect 4 s, **read 12 s** (genes present in dozens of panels return several paginated pages of ~100 KB), write 4 s, pool 4 s; at most 10 result pages are followed per query. For large exports (many unique genes), all PanelApp lookups are additionally capped at **25 s total** via `asyncio.wait`; genes that do not resolve within the cap return empty panel data rather than blocking the export.

**Per-gene cache:** results (including empty ones) are cached in memory per gene symbol for **6 hours** (up to 20 000 entries; the oldest 10 % are evicted when the cap is reached), so an export with one row per event queries PanelApp once per gene. A negative result is cached only when at least one source was actually queried, so a transient backoff is not remembered for 6 h.

---

## Performance

### Splice Feature Computation (`POST /api/v1/splice/compute/{analysis_id}`)

Background task that runs once per analysis. SE events are processed in chunks of 2 000: one MANE boundary lookup per chunk (in-memory), a single batched samtools call per chunk (or per-event Ensembl fallback, 20 concurrent requests), feature arithmetic, MANE annotation in a bounded pool of 8 threads, then bulk `INSERT … ON CONFLICT DO UPDATE` writes sub-batched at 1 000 rows (asyncpg parameter limit), followed by a heartbeat on `analyses.updated_at`. A chunk that fails is logged and skipped; the task then ends in `error` with the count of failed chunks.

Order-of-magnitude expectations for a 100 k SE-event analysis (estimates, local FASTA and local MANE GFF3):

| Stage | Description | Expected Time |
|-------|-------------|:-------------:|
| Import + parse | DataFrame → dedup → bulk INSERT (500-row batches) | 2–5 s |
| Sequence extraction | 100 k × 5 = 500 k regions, ~100 samtools calls (5 k regions each) | 10–30 s |
| MANE annotation + feature compute | Local GFF3 lookup + per-event arithmetic (8 annotation threads per chunk) | 5–15 s |
| DB writes | Bulk upsert, 2 round-trips per 2 000-event chunk | 1–3 s |
| **Total (local FASTA + warm MANE cache)** | | **~20–55 s** |

> If the local MANE GFF3 is missing, each event falls back to the Ensembl REST API (2–3 calls per event). Ensure `MANE_GFF3` is provisioned to avoid this.

The per-event endpoint `GET /splice/feature/{event_id}` (used by the cards) is capped at 8 concurrent computations and answers 503 after waiting 0.5 s for a slot; the client retries.

### Deep Splice Analysis

Opening a deep analysis triggers the pattern comparison, the patterns endpoint, the permutation test and Enrichr on demand (each a few seconds to tens of seconds on a 100 k-event analysis, network-bound for Enrichr). The hnRNP enrichment is a **background job** (§10): the first request returns after at most 15 s with either the result or a `running` state, the panel then polls every 2 s. Measured on 99 495 SE events in a GitHub Codespace: **1 min 40 s** for the whole job (extraction of ~700 k regions in ~140 samtools calls, scan of 2 groups × 7 regions × 19 motifs, 133 pairs of rank tests), after which the panel and the PDF section are served from the in-process cache. The deep-analysis PDF waits up to 20 s for a running job and otherwise answers 409 with the job's stage and percentage.

FASTA extraction, motif scanning, rank tests, permutations and PDF rendering all run inside `asyncio.to_thread`, so the event loop remains responsive during computation.

---

## Internationalisation (i18n)

All user-visible strings are stored in locale dictionaries under `frontend/src/lib/i18n/`:

| File | Locale |
|------|--------|
| `fr.ts` | French (default) |
| `en.ts` | English |

The active locale is managed by `LanguageContext` (`frontend/src/contexts/LanguageContext.tsx`). The default is French (`<html lang="fr">`); the choice made with the selector in `AppHeader` is persisted in `localStorage` (`spliceanalyzer_lang`) and restored on load. The `useT()` hook returns a resolver `t(key, vars?)` that:

- Resolves dot-path keys (e.g., `"sidebarNav.tabs.hnrnp"`) against the active locale object
- Supports `{{varName}}` interpolation for dynamic values
- Falls back to the key string if the translation is missing

**Adding a new language:** Create a new `xx.ts` in `src/lib/i18n/`, export it from `index.ts`, and add the locale code to the `LanguageProvider` switch.

---

## API Reference

The backend exposes a versioned REST API under `/api/v1`. Full interactive documentation is available at **http://localhost:8000/docs** (Swagger UI). In the browser the frontend reaches it through the Next.js rewrite of `/api/*` (10-minute proxy timeout).

### Analyses & Uploads

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/analyses` | Create a new analysis (single-shot multipart upload; used by `curl` / API clients). Form fields: `name` (required), `group1_label` (default `Subjects`), `group2_label` (default `Controls`), `group1_samples`, `group2_samples`, `mutated_genes` (JSON lists), `files` (one or more) |
| `POST` | `/api/v1/analyses/uploads` | Open a chunked-upload session &rarr; `{"upload_id"}` (used by the browser: proxies often cap request bodies at ~1 MB, so files are sent in ≤ 512 KB pieces). Stale sessions (`UPLOAD_SESSION_TTL_HOURS`) are purged here |
| `PUT` | `/api/v1/analyses/uploads/{upload_id}/chunk?filename=&index=&total=` | Append one raw chunk (`Content-Type: application/octet-stream`, max 4 MiB &rarr; 413) to `filename` (basename, `[A-Za-z0-9._-]` only &rarr; 422). Chunks must be sequential: `index` must equal the number already received (409 with the `expected` index otherwise); resending the last received chunk returns 200 without appending, so retries are idempotent. An `index` outside `[0, total)`, a `total` different from the one first announced for the file, or a chunk for an already complete file &rarr; 422. Returns `{filename, received_chunks, total_chunks, received_bytes}` |
| `POST` | `/api/v1/analyses/uploads/{upload_id}/finalize` | Same form fields as `POST /api/v1/analyses` minus the files, plus `files` = JSON list of the uploaded filenames to import (in order). Every listed file must be complete (409 naming the incomplete file). Assembles the files, creates the analysis exactly like the single-shot endpoint (201 + `UploadResponse`) and removes the session directory, also on failure |
| `DELETE` | `/api/v1/analyses/uploads/{upload_id}` | Abort a session and remove its partial files (204; 404 if unknown) |
| `GET` | `/api/v1/analyses` | List all analyses (ordered by `created_at` DESC) |
| `GET` | `/api/v1/analyses/{id}` | Get analysis details + sample groups (`status` = `processing` / `ready` / `error` / `deleting`, `error_message`) |
| `DELETE` | `/api/v1/analyses/{id}` | Delete analysis and all associated data asynchronously (returns 204 immediately; deletion runs in a background task with explicit ordered deletes; status set to `deleting` during cleanup, reset to `error` on failure) |

The upload response (`UploadResponse`, returned by both `POST /api/v1/analyses` and `…/finalize`) contains `analysis_id`, `status`, `event_count` (rows actually inserted) and `warnings` (list of human-readable notes, e.g. an empty file or "no events were imported"). A parser failure is recorded on the analysis row (`status = error`, `error_message`) and answered with 500.

Chunked upload from the command line (what the browser does with 512 KB pieces):

```bash
SID=$(curl -s -X POST localhost:8000/api/v1/analyses/uploads | jq -r .upload_id)
split -b 512k -d SE.MATS.JC.txt part_ && N=$(ls part_* | wc -l) && i=0
for p in part_*; do
  curl -s -X PUT -H 'Content-Type: application/octet-stream' --data-binary @"$p" \
    "localhost:8000/api/v1/analyses/uploads/$SID/chunk?filename=SE.MATS.JC.txt&index=$i&total=$N"; i=$((i+1))
done
curl -s -X POST "localhost:8000/api/v1/analyses/uploads/$SID/finalize" \
  -F name="My cohort" -F group1_label=Patients -F group2_label=Controls -F files='["SE.MATS.JC.txt"]'
```

### Events

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/analyses/{id}/events` | Paginated, filterable event list (`{items, total, page, page_size, pages}`), all event types |
| `GET` | `/api/v1/analyses/{id}/events/manhattan` | Lightweight points (`id`, `event_type`, `gene_symbol`, `chr`, `position` = exon start, `fdr`, `inc_level_difference`) for the Manhattan plot in natural chromosome order (chr1 … chr22, X, Y, M, then other contigs); all FDR &lt; 0.05 events kept, the rest uniformly sampled above 50 000 points |

**Event query parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `event_type` | string | Filter by type: `SE`, `A5SS`, `A3SS`, `MXE`, `RI` |
| `gene_symbol` | string | Filter by gene symbol (case-insensitive substring match) |
| `fdr_max` | float | Maximum FDR threshold |
| `p_value_max` | float | Maximum P-value threshold |
| `delta_psi_min` | float | Minimum \|&Delta;&Psi;\| threshold |
| `sort_by` | string | Column to sort by: `fdr` (default), `p_value`, `abs_inc_level_diff`, `gene_symbol` (nulls last) |
| `sort_dir` | string | `asc` (default) or `desc` |
| `page` | int | Page number (1-indexed) |
| `page_size` | int | Results per page (default 50, max 200) |

### Deep Analyses

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/analyses/{id}/deep-analyses` | Create a deep analysis (tags every event of the analysis, all types, by FDR + ΔΨ (+ p-value) thresholds; `status` is always `ready`) |
| `GET` | `/api/v1/analyses/{id}/deep-analyses` | List saved deep analyses for an analysis (newest first) |
| `GET` | `/api/v1/deep-analyses/{deep_id}` | Get a deep analysis by ID |
| `DELETE` | `/api/v1/deep-analyses/{deep_id}` | Delete a deep analysis (also discards its cached hnRNP job) |
| `GET` | `/api/v1/deep-analyses/{deep_id}/events` | Paginated event list (`{items, total, page, page_size, pages}`, ordered by FDR); query params `significant` (bool filter), `page` (default 1), `page_size` (default 200, max 500) |
| `GET` | `/api/v1/deep-analyses/{deep_id}/pattern-comparison` | SE events only: sig vs non-sig group statistics + `statistical_tests` (20 tests with `p_value`, `q_value`, `significant`, `significant_fdr`) |
| `GET` | `/api/v1/deep-analyses/{deep_id}/hnrnp-motifs?wait=&retry=` | hnRNP motif enrichment **job** (SE events only). `wait` (seconds to wait for a running job before answering, default 15, 0–60), `retry` (bool, restart a job that ended in error). Response: `status` (`done` \| `running` \| `error`), `stage` (`extract` \| `scan` \| `compare`), `progress` (0–1), `elapsed_seconds`, `error`, `n_sig_events`, `n_bg_events`, `regions` (7 names in scanning order) and `results` (133 rows when `done`: per pair presence z-test and density Mann-Whitney fields, `regulatory_effect`). The first call starts the job; the finished result is cached for the worker's lifetime |
| `GET` | `/api/v1/deep-analyses/{deep_id}/enrichr` | Enrichr pathway enrichment results (`n_genes_submitted`, `terms` = top 10 per library with overlap `k/n`, `error` when nothing could be submitted) |

**Deep analysis create body:**

| Field | Type | Description |
|-------|------|-------------|
| `fdr_threshold` | float | FDR cutoff for significance (default `0.05`) |
| `delta_psi_min` | float | Minimum \|&Delta;&Psi;\| (default `0.1`) |
| `pvalue_threshold` | float? | Optional p-value cutoff; when set, an event is significant only if FDR ≤ `fdr_threshold` **and** \|ΔΨ\| ≥ `delta_psi_min` **and** p ≤ `pvalue_threshold` (it is applied in event tagging and shown in the auto-generated name) |
| `name` | string? | Optional name; auto-generated from candidate genes + thresholds + date if omitted |
| `modules` | list[string]? | Module names (`splice`, `motifs`, `permutation`, `frame`, `hnrnp`, `enrichr`, `stringdb`); stored and returned, interpreted by the frontend only |
| `permutation_iterations` | int? | Permutation iteration count (10–2000) recorded with the deep analysis; stored in `permutation_iterations` and returned by the detail endpoint |

### Splice Site Analysis

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/splice/compute/{analysis_id}` | Start the background computation of splice features for all SE events (202). 404 when the analysis has no SE event. The claim is atomic: when `compute_status` is already `running` with a fresh heartbeat, the endpoint answers 202 with `message: "Computation already in progress."` and starts nothing; a `running` row whose heartbeat is older than 30 min (dead worker) is re-claimed |
| `GET` | `/api/v1/splice/progress/{analysis_id}` | Progress of that computation: `n_se_events`, `n_computed`, `pct`, `done`, `status` (`idle` / `running` / `done` / `error`, mirrors `analyses.compute_status`) and `error` (message when `status = error`). `done` is true when every SE event has features **or** the task is no longer running, even if it failed |
| `GET` | `/api/v1/splice/feature/{event_id}` | Per-event features (computed on-the-fly if not cached; 503 when the server is busy — the client retries). For a non-SE event the response carries `error: "Splice site analysis only available for SE events"` and no features |
| `GET` | `/api/v1/splice/patterns/{analysis_id}` | Aggregate pattern analysis over the SE events (PWM, consensus, size and frame stats, `bp_found_pct`, flanking-site stats); query params `fdr_threshold`, `abs_delta_psi_min`, `pvalue_threshold` (optional p-value maximum) or `deep_analysis_id` (restricts to the significant events of that deep analysis; the thresholds are then informational) |
| `POST` | `/api/v1/splice/permutation/{analysis_id}` | Permutation test on all SE events; query params `n_iterations` (default 500, clamped to 10–2000, Monte-Carlo path only), `fdr_threshold`, `delta_psi_min`, `pvalue_threshold` (the three thresholds restrict the reported `pct_p05` / `pct_p01` and the observed histogram to the significant subset). Response: per-event `exact` / `n_splits` and null histograms, global `exact_fraction`, `min_p_attainable`, `n_replicates_g1`, `n_replicates_g2`, `n_events_tested` / `n_total_events`, and `metric_results` (auxiliary metric permutations, §8) |
| `GET` | `/api/v1/splice/mane_transcript/{event_id}` | MANE Select transcript structure for the exon diagram (`transcript_id`, `exons`, `n_exons`, `exon_rank`, `strand`, `skipped_start`, `skipped_end`) |

> The compute endpoint is **idempotent** &mdash; re-running overwrites existing feature rows. It requires the GRCh38 FASTA for fast sequence features; if unavailable, the windows are fetched per event from Ensembl REST, and size-only features are stored when that fails too. Its state lives in the database (`compute_status` / `compute_error`), so a task interrupted by a restart is reset to `error` at the next startup once its heartbeat is 30 min old, and the UI stops polling.

### Genes & Annotations API

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/genes/search?q=&species=&limit=` | Gene autocomplete: mygene.info prefix search with Ensembl REST fallback (`q` min 2 chars, `species` default `homo_sapiens`, `limit` default 10, max 25) |
| `GET` | `/api/v1/genes/lookup/{symbol}?species=` | Exact gene lookup via Ensembl REST (404 when unknown) |
| `GET` | `/api/v1/annotations/gene/{symbol}?ensembl_id=` | PanelApp panels + GO terms + UniProt summary, fetched in parallel; the optional `ensembl_id` makes the GO lookup exact; unavailable services yield empty / null fields |
| `GET` | `/api/v1/annotations/interactions?gene_a=&gene_b=&species=9606` | STRING-DB interaction between two genes (channel scores, combined score, `string_url`) + Europe PMC PMIDs when text-mining evidence exists; `has_interaction: false` when STRING returns no record for the pair |

### Export Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/export/{analysis_id}/pdf?sections=` | Download the PDF report of an analysis (`rmats_{id}.pdf`). `sections` = comma-separated keys among `a`, `b`, `c`, `d`, `e`, `f`, `top_events` (all when omitted; deep-only keys are ignored here). **409** while the splice-feature computation is running and incomplete |
| `GET` | `/api/v1/export/{analysis_id}/deep-analysis/{deep_analysis_id}/pdf?sections=` | Download the PDF report scoped to a deep analysis (`rmats_deep_{deep_id}.pdf`), with the comparison, permutation, hnRNP and Enrichr sections. **409** while the splice-feature computation is running and incomplete, and **409** (with stage and percentage) when section `e` is requested while the hnRNP job is still running after a 20 s wait; a failed hnRNP job or Enrichr call skips its section |
| `GET` | `/api/v1/export/{analysis_id}/deep-analysis/{deep_analysis_id}/excel?include=core,panelapp,go,stringdb` | Download Excel for a deep analysis (significant events only, all types); `include` is comma-separated (`core` always added; unknown group &rarr; 422). No readiness gate |

### Diagnostics

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/health` | Health check (DB ping; 503 when the database is unreachable) |
| `GET` | `/api/v1/debug/fasta` | FASTA + samtools availability check (`fasta_exists`, `fai_exists`, `samtools_on_path`, `samtools_version`, `faidx_test_rc`, `setup_script`) |

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
  "exon_rank": 5,
  "frame_class": "in_frame",
  "frame_region": "CDS",
  "cds_exon_length": 132,
  "fasta_available": true,
  "sequence_source": "fasta",
  "mane_exon_source": "overlap"
}
```

**`GET /api/v1/deep-analyses/{deep_id}/hnrnp-motifs`** while the job runs (abbreviated):

```json
{
  "status": "running",
  "stage": "scan",
  "progress": 0.57,
  "error": null,
  "elapsed_seconds": 48.3,
  "n_sig_events": 812,
  "n_bg_events": 98683,
  "regions": [],
  "results": []
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
| `upstream_intron_size` | Upstream intron length (transcript sense) | `exon_start - upstream_EE` (+ strand); `downstream_ES - exon_end` (− strand) |
| `downstream_intron_size` | Downstream intron length (transcript sense) | `downstream_ES - exon_end` (+ strand); `exon_start - upstream_EE` (− strand) |

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
| `upstream_donor_is_gt` | Canonical check for upstream flanking exon donor (same `null` rule) |
| `downstream_acceptor_is_ag` | Canonical check for downstream flanking exon acceptor (same `null` rule) |
| `sequence_source` | `fasta` (local GRCh38), `ensembl` (REST fallback) or `null` (size-only row) |

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
| `exon_rank` | Exon position in the MANE transcript (1-based, transcript order) |
| `frame_region` | Genomic context: `CDS`, `partial`, `UTR5`, `UTR3`, `non_coding` (transcript without CDS), or `unknown` |
| `frame_class` | Frame impact: `in_frame`, `frameshift`, `non_coding`, or `unknown` |
| `cds_exon_length` | Number of coding nucleotides in the skipped exon (overlap with the coding extent of the transcript) |
| `mane_exon_source` | How the MANE exon boundaries were matched: `overlap`, `flanking`, or `null` |

---

## Scientific References

Each analytical panel embeds collapsible `ScienceNote` widgets that cite the primary literature. All reference metadata is centralized in `frontend/src/lib/references.ts`. The PDF report numbers its references in order of first appearance (Appendix B); the numbered list lives in `rmats-viz/backend/app/routers/export.py`, and its hnRNP-only block of 18 entries is appended only when the hnRNP section is selected.

### Reference Registry

| ID | Citation | Year | Used In |
|----|----------|:----:|---------|
| `rmats` | Shen S et al. *Proc Natl Acad Sci USA* | 2014 | SpliceView, PermutationPanel; PDF |
| `sequence_logos` | Schneider TD & Stephens RM. *Nucleic Acids Res* | 1990 | ConsensusLogoPanel, MotifPatternPanel |
| `shannon` | Shannon CE. *Bell Syst Tech J* | 1948 | ConsensusLogoPanel |
| `splice_sites` | Shapiro MB & Senapathy P. *Nucleic Acids Res* | 1987 | ConsensusLogoPanel, MotifPatternPanel; PDF |
| `ppt` | Coolidge CJ et al. *Nucleic Acids Res* | 1997 | PPTTrack, MotifPatternPanel; PDF (PPT score) |
| `branch_point` | Padgett RA et al. *Annu Rev Biochem* | 1986 | PPTTrack, MotifPatternPanel |
| `permutation_phipson` | Phipson B & Smyth GK. *Stat Appl Genet Mol Biol* | 2010 | PermutationPanel; PDF |
| `benjamini_hochberg` | Benjamini Y & Hochberg Y. *J R Stat Soc Series B* | 1995 | SpliceView, PermutationPanel |
| `mane_select` | Morales J et al. *Nature* | 2022 | SpliceView; PDF |
| `gene_ontology` | Gene Ontology Consortium. *Nucleic Acids Res* | 2021 | AnnotatedCard (GO tab) |
| `stringdb` | Szklarczyk D et al. *Nucleic Acids Res* | 2023 | AnnotatedCard (STRING-DB tab) |
| `panelapp` | Martin AR et al. *Nat Genet* | 2019 | AnnotatedCard (PanelApp tab) |
| `rmaps2` | Hwang JY et al. *Nucleic Acids Res* | 2020 | HnRNPMotifPanel (hnRNP enrichment); PDF (hnRNP block) |
| `enrichr` | Chen EY et al. *BMC Bioinformatics* | 2013 | EnrichrPanel (pathway enrichment); PDF |
| `cisbp_rna` | Ray D et al. *Nature* | 2013 | HnRNPMotifPanel (motif catalogue); PDF (hnRNP block) |
| — | Gao K, Masuda A, Matsuura T, Ohno K. Human branch point consensus sequence is yUnAy. *Nucleic Acids Res* 36:2257–2267 | 2008 | README and PDF Appendix B (branch-point consensus of the heuristic); code docstrings |
| — | Mercer TR et al. Genome-wide discovery of human splicing branchpoints. *Genome Res* 25:290–303 | 2015 | README only (branch-point distance distribution) |
| — | Leman R et al. Assessment of branch point prediction tools to predict physiological branch points and their alteration by variants. *BMC Genomics* 21:86 | 2020 | README and PDF Appendix B (18–44 nt branch-point window); code docstrings |
| — | Mann HB & Whitney DR. On a test of whether one of two random variables is stochastically larger than the other. *Ann Math Stat* 18:50–60 | 1947 | README only (Mann-Whitney U test of §10 and §12; cited in the backend docstrings) |
| — | Kuleshov MV et al. Enrichr: a comprehensive gene set enrichment analysis web server 2016 update. *Nucleic Acids Res* 44:W90–W97; Xie Z et al. Gene set knowledge discovery with Enrichr. *Curr Protoc* 1:e90 | 2016; 2021 | PDF Appendix B (Enrichr) |

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
| SQLAlchemy | 2.0.30 | Async ORM |
| asyncpg | 0.29.0 | PostgreSQL driver |
| Alembic | 1.13.1 | Database migrations |
| Pydantic / pydantic-settings | 2.7.1 / 2.2.1 | Data validation and settings |
| python-multipart | 0.0.9 | Multipart form parsing (uploads) |
| Pandas | 2.2.2 | rMATS TSV parsing and data processing |
| NumPy | ≥ 1.26.4, &lt; 3 | Vectorised permutations |
| httpx | 0.27.0 | Async HTTP client (PanelApp, Ensembl, mygene.info, UniProt, STRING-DB) |
| requests | 2.32.3 | Synchronous HTTP client (Enrichr, run in thread) |
| openpyxl | 3.1.2 | Excel file generation |
| reportlab | 4.2.2 | PDF report generation |
| pytest | ≥ 8, &lt; 9 | Test runner (shipped in the image) |
| samtools | (system, Debian package) | FASTA indexing and sequence extraction |

### Frontend

| Technology | Version | Purpose |
|------------|---------|---------|
| Next.js | 14.2.3 | React framework (App Router) |
| React | 18.x | UI library |
| TypeScript | 5.x | Type safety |
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

## Testing

### Backend unit and integration tests

The pytest suite lives in `rmats-viz/backend/tests/` (**11 files, 164 tests**) and needs no database, network or samtools binary:

| File | Covers |
|------|--------|
| `test_parser_event_types.py` | Event type / counting mode detection (file name tokens, `fromGTF`, header sniffing), A3SS/A5SS derived coordinates, type-aware deduplication |
| `test_parser_coverage.py` | Coverage filter (NA replicates, unequal lists, missing counts, annotation-only files), empty files, decimal commas |
| `test_sequence_features.py` | `samtools faidx` output parsing (empty records, count mismatch), chunk halving, negative-start clamp, window coordinates on both strands, reverse complement (full IUPAC), PWM denominator, unknown GT-AG flags, branch point (18–44 nt window, mandatory A, tie-break), MANE Select tag selection (not file order), Ensembl CDS filtering by transcript and frame class |
| `test_mane_cache_concurrency.py` | SQLite cache schema initialisation under concurrent annotation threads |
| `test_stats.py` | Welch's t-test, z-test, Mann-Whitney U (ties, continuity), Benjamini-Hochberg (`None`-aware), natural chromosome order |
| `test_hnrnp_motifs.py` | Seven-region definition (both strands, short introns, missing flanks), motif scan densities (incl. degenerate motifs), small-group guards, two-test comparison with BH per family, shared statistics helpers, batched region extraction |
| `test_hnrnp_jobs.py` | Background job lifecycle (start, progress, cache, error and retry) |
| `test_permutation.py` | Exact enumeration vs Monte-Carlo (2v2, 3v3, 10v10), observed split included, observed ΔΨ from `IncLevelDifference`, seed reproducibility, design summary (mode, exact fraction), histograms, non-SE / invalid PSI skipped, metric permutations |
| `test_chunked_upload.py` | Chunk ordering rules, idempotent resend, filename sanitising, session purge |
| `test_export_pdf.py` | PDF smoke builds (plain analysis, unknown flags, deep analysis with every section, empty optional blocks), frame-breakdown denominator, permutation note (Monte-Carlo vs exact) |
| `test_schema_drift.py` | ORM models vs Alembic migrations |

```bash
# inside the compose stack (pytest and samtools are in the image)
docker compose exec backend python -m pytest tests -q

# or on the host
cd rmats-viz/backend && python -m pytest tests -q
```

### End-to-end scenario (real PostgreSQL)

`rmats-viz/backend/tests/e2e/` reproduces the closing-release verification against a real PostgreSQL 16 through the in-process ASGI client: migrations from an empty database (`alembic upgrade head` + `alembic check`), ingestion of the five event types (JC + JCEC duplicates, NA replicates, decimal commas, near-duplicates, NAGNAG / RI / MXE pairs, an empty `summary.txt`) through both the single-shot and the chunked upload path, splice-feature computation on a synthetic genome with planted GT/AG signals and branch points, MANE Select vs Plus Clinical selection, deep analyses (pattern comparison, hnRNP seven regions and job cache, exact permutation), Excel / PDF exports incl. the 409 gates, cascade delete and the compute-status lifecycle (stale-heartbeat re-claim). **136 assertions**; the expected values are computed independently by `make_data.py`. No external API is required: without network every annotation call must degrade gracefully, and that is asserted too. See `tests/e2e/README.md` for the two ways of running it (inside the compose stack with a dedicated `e2edb` database, or on the host with a temporary `initdb` cluster and the `pysam`-based `samtools` wrapper).

### Frontend

`npx tsc --noEmit` and `npx next build` (6 routes) are the checks used for the frontend; `en.ts` and `fr.ts` carry the same key tree.

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
- The application will still function without the FASTA &mdash; splice-site windows fall back to the Ensembl REST API (per event, slow) and hnRNP region scanning (local FASTA only) is skipped

**Frontend can't reach the backend (CORS errors in development)**
- The Next.js config proxies `/api` requests to `API_URL` (`http://backend:8000` inside the Docker network)
- If running outside Docker, set `API_URL` (or edit `next.config.mjs`) to point to your backend URL
- If you see CORS errors in the browser console, ensure `CORS_ORIGINS` in `.env` includes your frontend URL (e.g., `["http://localhost:3000"]`); restart the backend after changes

**MANE GFF3 missing / frame classification fails**
- The local MANE GFF3 file (`MANE.GRCh38.ensembl_genomic.gff.gz`) is read in full with `gzip` at first use; no tabix index is needed
- If the GFF3 is missing entirely, the **root** `docker-compose.yml` backend command downloads it before starting Uvicorn (the `rmats-viz/docker-compose.yml` variant does not: run `bash rmats-viz/data/setup_mane_gff3.sh`); ensure the container has outbound HTTPS access. Without it every event falls back to the Ensembl REST API and no exon-boundary correction is applied
- Genes absent from the GFF3 are retried against Ensembl at most once per 24 h per event from the per-event feature endpoint; a full re-run of the compute endpoint retries all of them

**Genome FASTA indexing errors (samtools)**
- Sequence extraction requires both the FASTA file and its `.fai` index
- If you see `[E::fai_build_core]` or samtools errors, regenerate the index: `samtools faidx /data/GRCh38.fa`
- Ensure `samtools` is installed and accessible (it is included in the Docker image by default; the backend never uses pysam)

**French-locale decimal parsing errors**
- The parser automatically handles comma-as-decimal-separator (e.g., `"0,117"` &rarr; `0.117`)
- No user action required

**hnRNP motif scan or FASTA extraction very slow on large analyses**
- Ensure `samtools` is available and the FASTA is properly indexed (`.fai` file present)
- Extraction is chunked at 5 000 regions/call; a 100 k event analysis runs ~100 chunks (splice windows) or ~140 chunks (seven hnRNP regions) sequentially
- The hnRNP enrichment runs as a background job: the panel shows its stage and progress and keeps polling; the result is cached once done (about 1 min 40 s for 100 k SE events)
- All stages run in worker threads; the app remains responsive during computation

**hnRNP panel shows an error / PDF export answers 409**
- An hnRNP job that failed (FASTA missing, samtools error) keeps its error message; click **Retry** in the panel (`retry=true`) after fixing the cause
- The PDF export answers 409 while splice features are still being computed, and (deep-analysis PDF with the hnRNP section) while the hnRNP job is still running: wait for the progress bar / panel to finish, or export without that section

**Analysis stuck in `deleting` state after a container restart**
- The backend resets any `deleting` analyses to `error` on startup, so you can retry deletion
- If a deletion fails, the status is reset to `error` with a message; click Delete again to retry
- Deletion runs as a background task: the UI removes the row optimistically and the backend cleans up child tables in dependency order before removing the analysis row

**Splice-feature computation stuck in `running` / progress bar never completes**
- The state is stored in `analyses.compute_status`; on startup the backend resets to `error` ("interrupted by restart") any analysis left in `running` whose heartbeat (`updated_at`) is older than 30 minutes; the progress endpoint then reports `done: true` with the `error` message and the UI stops polling
- Re-run **Compute** to start a new task; while a task is genuinely `running` (fresh heartbeat) the endpoint answers 202 "Computation already in progress." without starting a second one; a stale `running` row (dead worker) is re-claimed immediately
- The frontend stops polling on its own when the progress endpoint reports `done` or an error

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

This is the closing version of the Python application; fixes are still welcome, new analyses belong to the in-browser successor.

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Make your changes
4. Ensure the application builds and runs: `docker compose up --build`, and that `python -m pytest tests -q` (backend) and `npx tsc --noEmit` / `npx next build` (frontend) pass
5. Commit with clear, descriptive messages
6. Open a Pull Request

### Development Tips

- **Backend code changes:** the backend source is bind-mounted (`./rmats-viz/backend:/app`) but Uvicorn is **not** started with `--reload`, so restart the container after a change (`docker compose restart backend`) or add `--reload` to the compose command for a development session
- **Frontend hot-reload:** The frontend source mount (`./rmats-viz/frontend/src:/app/src`) enables Next.js Fast Refresh (`npm run dev`)
- **API documentation:** Use Swagger UI at `http://localhost:8000/docs` to test endpoints interactively
- **Database migrations:** Create new migrations with `docker compose exec backend alembic revision --autogenerate -m "description"`; `test_schema_drift.py` fails when the models and the migration chain diverge
- **Tests:** see [Testing](#testing)

---

## Related Documents

| File | Content |
|------|---------|
| [`SPLICEANALYZER_IN_BROWSER_SPEC.md`](SPLICEANALYZER_IN_BROWSER_SPEC.md) | Specification of the in-browser successor (no backend, all five event types, algorithms and constants to port, verification plan) |
| [`MERGE_NOTES_dev.md`](MERGE_NOTES_dev.md) | Merge-request text of this closing version: summary of changes, deployment checklist, verification performed, risk assessment of result changes |
| [`ORIGINAL_CODE_FIXES.md`](ORIGINAL_CODE_FIXES.md) | Defect list of the original code (wrong results, text/code mismatches, robustness, dead code, method changes) with the status of each item |
| `check_cors.sh` | Probe of the public APIs (UCSC, Ensembl, mygene.info, UniProt, STRING, PanelApp, Enrichr, Europe PMC, …) for CORS headers, for the successor |
| `rMAPS2.pdf`, `gkaa237_supplemental_file.pdf` | rMAPS2 paper (Hwang et al., 2020) and its supplement, source of the hnRNP E1/E2 motifs and of the seven-region design |
| `rmats-viz/backend/tests/e2e/README.md` | How to run the end-to-end scenario |
