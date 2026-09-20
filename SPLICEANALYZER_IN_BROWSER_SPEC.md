# SpliceAnalyzer — in-browser re-implementation specification

> Purpose: this document is the complete brief for a **new repository** and a **dedicated Claude Code session** that will rebuild SpliceAnalyzer as a pure static web application (no backend, no database, GitHub Pages), positioned as the downstream step of **Sashimi-viewer** (benjamin-cogne/Sashimi-viewer) in a fully in-browser suite:
>
> `RNA-seq BAM/CRAM → Sashimi-viewer (visual QC, junctions) → rMATS output → significant-event selection → SpliceAnalyzer (annotation + analysis) → reports`.
>
> It contains (1) a function-by-function re-evaluation of the current SpliceAnalyzer, (2) the inventory of every external API access with in-browser (CORS) feasibility, (3) the target architecture, (4) the design codes to copy from Sashimi-viewer, (5) the scientific module specifications with the exact constants to port, (6) the feature list for all rMATS event types (SE, A3SS, A5SS, RI, MXE), (7) the phased work breakdown, (8) the verification plan, (9) the open risks, and (10) a kickoff prompt for the new session.
>
> Evidence base: read-only audit of `wallideb/SpliceAnalyzer` (branch `dev`, 169 commits, ~26 k LOC), read-only clone of `benjamin-cogne/Sashimi-viewer` (`main` v1.0.0 + unreleased `dev`/`container` branches), web research dated 2026-09-18. Anything not verified is marked **(unverified)**. Nothing in Sashimi-viewer was modified.

---

## Table of contents

0. [How to use this document, hard rules](#0-how-to-use-this-document-hard-rules)
1. [Context, goal, position in the suite](#1-context-goal-position-in-the-suite)
2. [Re-evaluation of the current SpliceAnalyzer, function by function](#2-re-evaluation-of-the-current-spliceanalyzer-function-by-function)
3. [External API accesses: current inventory and in-browser feasibility](#3-external-api-accesses-current-inventory-and-in-browser-feasibility)
4. [Target architecture](#4-target-architecture)
5. [Design codes (copied from Sashimi-viewer)](#5-design-codes-copied-from-sashimi-viewer)
6. [Data layer: rMATS ingestion, genome, MANE, caches](#6-data-layer-rmats-ingestion-genome-mane-caches)
7. [Functional specification (pages and flows)](#7-functional-specification-pages-and-flows)
8. [Scientific module specifications (algorithms and constants to port)](#8-scientific-module-specifications-algorithms-and-constants-to-port)
9. [Feature list per rMATS event type (SE, A3SS, A5SS, RI, MXE, cross-type)](#9-feature-list-per-rmats-event-type)
10. [Work breakdown (everything that has to be done)](#10-work-breakdown-everything-that-has-to-be-done)
11. [Verification and parity plan](#11-verification-and-parity-plan)
12. [Risks, licences, open questions](#12-risks-licences-open-questions)
13. [References](#13-references)
14. [Kickoff prompt for the new Claude Code session](#14-kickoff-prompt-for-the-new-claude-code-session)

---

## 0. How to use this document, hard rules

1. Create a new empty repository (suggested name: `SpliceAnalyzer-web` or `spliceanalyzer-viewer`). Copy this file to its root as `SPEC.md` and add a short `CLAUDE.md` that says: "Read SPEC.md first. Follow its hard rules. Work through section 10 in order."
2. Start a Claude Code session in that repository with the kickoff prompt of section 14.
3. **Hard rules for the implementation session** (they are not negotiable; they mirror the constraints of this brief):
   - **No backend, no database, no server-side code.** Everything runs in the browser from one static HTML file deployed on GitHub Pages, exactly like Sashimi-viewer.
   - **Genome sequence comes from the UCSC REST API** (`https://api.genome.ucsc.edu/getData/sequence`), with an optional local FASTA (+ `.fai`) as an accelerator for large batches, and Ensembl REST as fallback. Never fetch NCBI FTP at runtime.
   - **Design identical to Sashimi-viewer**: same stack (Vite + React 18 + TypeScript strict + Tailwind 3.4 default theme + `vite-plugin-singlefile`), same palette, typography, spacing, radii, component recipes, SVG chart conventions, header/footer structure, light theme only, no icon library, no CDN, no Google Fonts. Section 5 is the source of truth; do not "improve" it.
   - **Never modify the Sashimi-viewer repository.** Interoperate through URL deep links and JSON files only (section 7.9).
   - **Scientific honesty**: every computed value must be traceable to a formula in section 8 with a citation in section 13; when a value cannot be computed, display "unknown" (never a heuristic fallback silently). Keep the caveats of the original app (no NMD without a computed PTC position, exploratory statistics without multiple-testing correction flagged as such).
   - **All five rMATS event types are first-class** (SE, A3SS, A5SS, RI, MXE) in parsing, tables, diagrams and sequence features. SE-only shortcuts of the old app must not be carried over.
   - Coordinates: rMATS/BED 0-based half-open everywhere internally; convert only at API boundaries (UCSC `start` is 0-based; Ensembl regions are 1-based inclusive).
   - Every fix listed in section 2 marked **FIX** must be applied in the port; every item marked **DROP** must not be ported.
   - Commit small, test each scientific module against the Python fixtures (section 11) before moving on.

---

## 1. Context, goal, position in the suite

### 1.1 What SpliceAnalyzer does today (rmats-viz)
- Stack: Next.js 14 frontend (React 18, TanStack Query/Table, Tailwind shadcn tokens, hand-written SVG charts, EN/FR i18n, dark mode) + FastAPI/Python 3.12 backend (SQLAlchemy async, PostgreSQL 16, Alembic, pandas, numpy, openpyxl, reportlab, `samtools faidx` subprocess) + Docker Compose. Requires a local GRCh38 FASTA (~3 GB) and the MANE GFF3.
- Pipeline: upload rMATS `*.MATS.JC.txt` files → event-type detection from filename → coverage filter (mean IJC+SJC ≥ 10 per group) → ±50 bp boundary dedup (lowest FDR wins) → events table/Manhattan plot → "deep analysis" = partition significant vs non-significant by FDR and |ΔΨ| → SE-only splice features (9-nt donor, 23-nt acceptor, 47-nt PPT, flanking sites, GT/AG check, PPT score, YNYURAY branch point, MANE frame class) → pattern comparison (Welch t / two-proportion z), sequence logos, hnRNP motif enrichment (19 motifs × 5 regions, z-test + BH), permutation test, Enrichr, gene annotations (MyGene GO, UniProt, PanelApp, STRING + Europe PMC) → Excel/PDF reports (server-side).
- Documented limitations: SE-only for sequence/motif analyses; A3SS/A5SS coordinates are actually lost at ingestion (bug, section 2.1); no splice-site strength model (no MaxEntScan); permutation test uninformative with 2–3 replicates; hnRNP test loses direction; heavy infrastructure.

### 1.2 What Sashimi-viewer is (the design and architecture reference)
- Single self-contained HTML (`sashimi-viewer.html`, ~1 MB) built by Vite 5 + `vite-plugin-singlefile` from a React 18 + TypeScript 5.9 source (~7.4 k LOC), deployed by GitHub Actions to GitHub Pages, CC BY-NC 4.0, author Benjamin Cogné (CHU Nantes), "made with Claude Opus 5 and Fable 5.1".
- Loads BAM/CRAM (+index) and FASTA locally via `@gmod/bam`, `@gmod/cram`, `@gmod/indexedfasta` over `File.slice`; annotation and sequence from UCSC REST (`getData/track` for `ncbiRefSeqCurated|ncbiRefSeq|ncbiRefSeqSelect|mane|dbSnp155Common|unipDomain|ucscGenePfam`, `getData/sequence`, `/search`) with Ensembl REST fallback; GTEx portal API v2 for tissue tracks.
- Draws sashimi tracks, transcript model, junction arcs with read-count pills and frame glyphs, HGVS c./r. positions, ψ (junction), DEXSeq-like depth usage, NMD verdict (55-nt rule), protein diff, an animated "splicing cartoon". Exports SVG/PNG. Deep links `#locus=…&label=…&gene=…&build=…`. `dev` branch adds session JSON, groups, intron retention, exported HTML with embedded data.
- **It does not read rMATS output** (main or dev). The author's own rMATS notebooks (`RNU4-2_transcriptomics`) filter events by `FDR ≤ x AND |ΔPSI| ≥ y AND mean(IJC) ≥ c AND mean(SJC) ≥ c`, call frame as `(exonEnd − exonStart) % 3`, keep one best event per gene by lowest FDR, and run PCA of PSI values.

### 1.3 Goal of the new app
A static page, visually indistinguishable from Sashimi-viewer, that:
1. ingests rMATS output files (JC and/or JCEC, all five types, plus optional `summary.txt`) dropped by the user;
2. filters and marks significant events (same rules as the author's notebooks plus SpliceAnalyzer thresholds);
3. annotates every event in the browser: MANE Select model (bundled JSON), sequence windows (UCSC API), splice-site strength (MaxEntScan port), PPT, branch point, frame/PTC/NMD, gene annotations (MyGene, UniProt, Ensembl, PanelApp, STRING, gnomAD);
4. runs the cohort analyses (significant vs non-significant patterns, logos, RBP/hnRNP positional maps, enrichment, permutation) in Web Workers;
5. exports TSV/XLSX/SVG/PNG/PDF and a session JSON, and links every event to Sashimi-viewer (`#locus=…`) and back.

---

## 2. Re-evaluation of the current SpliceAnalyzer, function by function

Legend of verdicts: **PORT** = re-implement as is in TypeScript · **PORT+FIX** = re-implement with the listed correction · **REPLACE** = same purpose, different mechanism (browser) · **DROP** = do not carry over · **NEW** = does not exist today, required by this spec.

### 2.1 `backend/app/services/parser.py` + `utils/composite_key.py` (rMATS ingestion)

| Function | What it does | Verdict and notes |
|---|---|---|
| `detect_event_type(filename)` | Uppercases filename, returns first of `MXE, A3SS, A5SS, RI, SE` found as substring | **PORT+FIX**: substring match misdetects (`MYSERIES.txt` → RI, `PRIMARY_SE…` → RI). Use a token regex `(^|[._-])(SE|MXE|A3SS|A5SS|RI)\.MATS\.(JC|JCEC)\.txt$` and, as fallback, detect from the header columns (`riExonStart_0base` → RI, `longExonStart_0base` → A3SS/A5SS disambiguated by filename or by geometry, `1stExonStart_0base` → MXE, `exonStart_0base` → SE). Record JC vs JCEC. |
| `_rename_columns(df)` / `RAW_COL_MAP` | Maps rMATS headers to internal names; drops unmapped columns | **PORT+FIX**: the map has no entry for `longExonStart_0base, longExonEnd, shortES, shortEE, flankingES, flankingEE` (A3SS/A5SS) nor `1stExonStart_0base/1stExonEnd` (MXE uses `exonStart_0base` alias only in some versions) → **A3SS/A5SS events lose all coordinates** and are dropped by the all-null rule. New schema in section 6.1 keeps type-specific coordinates. Also keep `IncFormLen`, `SkipFormLen` (needed for JCEC interpretation). |
| `filter_low_coverage(df, min_coverage=10)` | Per group: mean over replicates of `IJC_i + SJC_i` must be ≥ 10 in both groups; NA/unparseable/mismatched replicate counts → dropped | **PORT** (parameter exposed in UI, default 10). Also offer the Sashimi-viewer author's rule (`mean(IJC) ≥ c AND mean(SJC) ≥ c` per group) as a second, selectable filter. |
| `_coerce_types(df)` | Int64 coordinates; French decimal comma → dot for `p_value, fdr, inc_level_difference` | **PORT** (apply the comma fix to every numeric column, including the comma-separated lists only after splitting). |
| `parse_rmats_file(bytes, type, id)` | `read_csv(sep="\t", na_values=["NA","nan",""])`, rename, coerce, drop rows where all required coords are null, add `abs_inc_level_diff` | **REPLACE** by Papa Parse streaming in a Web Worker (section 6.1). |
| `deduplicate_with_overlap(df, overlap_bp=50)` | Sort by FDR asc (NaN last) then |ΔΨ| desc; within `(event_type, gene_id, chr, strand)` a candidate is a duplicate of any kept event if `|start−kept_start| ≤ 50 OR |end−kept_end| ≤ 50`; greedy | **PORT+FIX**: (a) apply to SE/RI/MXE only on their defining exon; (b) for A3SS/A5SS the alternative sites differ by construction at one boundary (often < 50 bp, e.g. NAGNAG = 3 nt) → dedup must key on the **full coordinate tuple** (exact duplicates only, JC vs JCEC merge) and never on ±50 bp; (c) make the window a parameter; (d) keep the JC/JCEC provenance of the retained row. |
| `_df_to_records`, `parse_and_store` | Bulk insert into Postgres with `ON CONFLICT DO NOTHING` on the identity tuple | **REPLACE** by in-memory typed arrays + IndexedDB persistence (section 6.4); identity key = string `${type}|${gene_id}|${chr}|${strand}|${coords…}` including type-specific coordinates. |
| `EVENT_TYPE_KEYWORDS` | Unused constant | **DROP** |
| `tests/test_parser_coverage.py` | Vectors: mean = 10 kept, 9 dropped; 3-replicate means; dedup `1000-1100` vs `1030-1100` collapses; FDR 0.001 wins | **PORT** as unit tests (section 11). |

### 2.2 `services/sequence.py` (sequence windows)

| Function | What it does | Verdict |
|---|---|---|
| `_UCSC_TO_REFSEQ` map, `_fai_contig_set`, `_resolve_chrom` | UCSC `chrN` → RefSeq `NC_…` aliases for FASTA files with RefSeq names | **PORT** (needed for the optional local FASTA path; table in section 6.2). |
| `reverse_complement(seq)` | `ACGTacgtNn` translate + reverse | **PORT+FIX**: complement the full IUPAC alphabet (`RYSWKMBDHVN`). |
| `extract_regions_batch(regions, fasta)` | `samtools faidx` in chunks of 5000 regions, parses multi-FASTA | **REPLACE**: (i) UCSC `getData/sequence` per merged window (section 6.2), (ii) optional JS faidx over a local `File` (`@gmod/indexedfasta`, same lib as Sashimi-viewer), (iii) Ensembl `POST sequence/region` (≤ 50 regions) fallback. The original has a misalignment bug (empty records skipped shift subsequent sequences) and blanks 5000 regions on one failure: do not reproduce. |
| `extract_region` | Single region | **DROP** (dead code). |
| `SpliceWindows` dataclass, `get_splice_windows(…)`, `get_splice_windows_batch`, `get_splice_windows_from_ensembl` | Defines the 5 SE windows on + strand and their minus-strand mirrors, RC for minus strand; MANE-corrected skipped-exon boundaries; flanks at rMATS coordinates | **PORT+GENERALISE**: one window generator per event type (section 8.1) returning transcript-sense sequences; three duplicated implementations become one. |
| `fasta_available` | Checks file + samtools | **REPLACE** by "local FASTA loaded?" flag. |

### 2.3 `services/splice_features.py` (per-event features)

| Function | Logic | Verdict |
|---|---|---|
| `ppt_score`, `ppt_t_content`, `ppt_c_content`, `longest_y_run` | Fractions of C/T, T, C; longest C/T run | **PORT** (store T and C content, they were computed but not persisted). |
| `find_branch_point(seq)` | Scan 7-mers for `Y N Y T R A Y`; skip candidates whose centre is < 15 nt from the window end; score = number of matching positions (0–7, N always 1); first max wins; `bp_motif_found = score ≥ 5`; `bp_distance = len − (pos+3)` | **PORT+FIX**: the reported distance is to the end of the PPT window (3 nt before the exon) → true distance to the AG is `bp_distance + 3`; make the branch A (position 6) mandatory for a "found" call; restrict to 18–44 nt upstream of the 3′ss (Leman 2020, Mercer 2015); add the CTRAY 5-mer scan and, later, the BPP model port (section 8.4). Cite Gao 2008 for yUnAy. |
| `compute_features(event, windows)` | Sizes (strand-aware intron sizes), `donor_is_gt = donor[3:5]=="GT"`, `acceptor_is_ag = acc[18:20]=="AG"`, PPT stats (4 dp), BP | **PORT+GENERALISE** to all event types (section 8.2); also flag GC-AG and AT-AC (U12) donors instead of treating them as "non-canonical" only. |
| `compute_pwm(seqs)` | Per-column base frequencies over min length; total counts include N | **PORT+FIX**: exclude non-ACGT from the denominator; also compute information content (bits) with small-sample correction, as the old frontend did. |
| `iupac_consensus(seqs, threshold=0.40)` | Bases with freq ≥ 0.40 → IUPAC code, else N | **PORT** (threshold parameter). |

### 2.4 `services/hnrnp_motifs.py` (rMAPS2-like motif enrichment)

| Item | Logic | Verdict |
|---|---|---|
| `HNRNP_MOTIFS` (19) | hnRNP A1/A2 `TAGG, TAGGG, TAGGGA, AGG`; PCBP1 `CC[AT][AT][ACT]CC`; PCBP2 `CC[CT][CT]CC[ACT]`; F/H `GGGG, GGG`; K `CCCC, TCCC`; C `TTTTT, TTTT`; L `CACA, ACAC`; M `TGTG, GTGT`; PTB `TCTT, TCTCT, CTCT` | **PORT** as the default "hnRNP consensus" catalogue, plus **NEW** PWM catalogue (CisBP-RNA CC-BY 4.0) and hexamer ESE/ESS sets (section 8.6). |
| `REGULATORY_EFFECTS` | Protein × region → ESE/ESS/ISE/ISS labels | **PORT** but display only when the direction (inclusion vs skipping) is known, i.e. run the test separately for ΔΨ>0 and ΔΨ<0 significant sets (rMAPS2 design). |
| `define_se_regions(...)` | 5 regions: upstream exon (last 250 nt), upstream intron (250 nt after the upstream 5′ss, 6-nt exclusion, bounded by exon_start−20), skipped exon, downstream intron (250 nt after the skipped-exon 5′ss, bounded by downstream_es−20), downstream exon (first 250 nt); minus-strand mirrored; empty when `iend ≤ istart` | **PORT+FIX**: the code scans the 5′ss-proximal half of each intron only; rMAPS2 scans **both** intron ends (250 nt after each 5′ss and 250 nt before each 3′ss) → use 4 intronic + 3 exonic regions for SE and the equivalents for other types (section 8.6). Docstring/README are wrong about this today. |
| `scan_group`, `count_motif_occurrences`, `motif_density` | Presence per event/region, density = `min(1, hits·len/seq_len)` | **PORT** scan; **DROP** the two dead helpers; add a 50-nt sliding-window density map (rMAPS2). |
| `compare_groups`, `_proportion_z_test`, `_bh_adjust`, `_normal_cdf` | Pooled two-proportion z on presence, BH over 95 pairs, `q < 0.05` | **PORT** as the "region-level presence test" (documented as SpliceAnalyzer-specific) and **NEW** rMAPS2 positional Wilcoxon rank-sum per window (section 8.6). Short motifs (`AGG`, `GGG`, `TTTT`, `CTCT`) saturate a presence test on 250-nt regions: keep density as the primary statistic. |

### 2.5 `services/permutation.py`

| Item | Logic | Verdict |
|---|---|---|
| `_parse_psi` | Comma list → finite floats in [0,1] | **PORT** (done once at import). |
| `run_permutation(events, features, n_iterations=500, seed=42)` | Per event: pool PSI, permute labels K times, `p = (r+1)/(K+1)` (Phipson & Smyth 2010), histograms | **PORT** in a Web Worker with **FIX**: enumerate all distinct label splits exactly when `C(n1+n2, n1) ≤ 5000` (2v2 → 6, 3v3 → 20, 4v4 → 70, 5v5 → 252) and report the minimum attainable p-value; display a warning that with n ≤ 3 per group the per-event test cannot reach 0.05. Do not accumulate all null values (60 M floats at 120 k events): accumulate histogram counts. Seeded PRNG (mulberry32/xoshiro), not bit-identical to numpy. |
| `_compute_metric_permutations` | Groups by sign of ΔΨ; metrics PPT score, normalised exon size, in-frame, canonical sites | **PORT** as "exploratory", frontend never displayed it → show it in the permutation panel (or DROP if not wanted; recommendation: keep, it is cheap). |
| `_make_histogram` | 40 bins on [−1, 1] | **PORT**. |

### 2.6 `services/mane.py` + `services/mane_local.py` (MANE Select annotation)

| Item | Logic | Verdict |
|---|---|---|
| SQLite caches | `mane_cache`, `mane_exon_cache` | **REPLACE** by the bundled MANE JSON + IndexedDB. |
| `_get_mane_transcript` (Ensembl `lookup/id?expand=1`, flag `is_mane_select`/`mane_select`, fallback `overlap/region?feature=transcript`) | | **PORT** as fallback only (`mane=1` parameter of Ensembl lookup; verify field name live). |
| `_get_transcript_structure` (`lookup/id/{tx}?expand=1` + `overlap/id/{tx}?feature=cds`) | | **PORT+FIX**: filter CDS features by `Parent == transcript` (today the CDS span is the union of all overlapping isoforms → wrong UTR/partial calls). |
| `_frame_class` / `annotate_from_local` | Exon rank by max overlap (reversed on minus); no CDS → `non_coding`; overlap with CDS span → `cds_exon_length`, `CDS`/`partial`, `in_frame` if `cod_len % 3 == 0` else `frameshift`; UTR5/UTR3 by side and strand | **PORT** (single implementation) + **NEW** PTC/NMD computation by actual translation (section 8.5). |
| `load_mane_gff3` / `_do_parse` | Parses GFF3, first transcript per gene assumed MANE Select | **REPLACE** by a build-time script producing `mane.v1.5.json` (section 6.3) that uses the `tag=MANE_Select` attribute, not file order. |
| `get_mane_exon_boundaries(gene, es, ee, uee, des)` | Reciprocal overlap ≥ 50 % → `"overlap"`; else MANE exon inside `[upstream_ee, downstream_es]` → `"flanking"` (closest size if several) | **PORT** for all types (applied to the regulated exon(s)); keep `mane_exon_source` in the UI and reports. |

### 2.7 Gene-annotation services (`ensembl.py`, `uniprot.py`, `stringdb.py`, `panelapp.py`, `enrichr.py`, `gene_ontology.py`)
All are thin HTTP clients without keys; all **PORT** to `fetch` with a promise cache + IndexedDB cache, with these fixes:
- `enrichr.py`: `overlap` string is built from the trailing parenthesised token of the term (breaks on GO terms `(GO:0000398)`) → take set sizes from bundled GMT libraries; submit a background list (Speedrichr) or, preferably, compute the hypergeometric test locally (section 8.8).
- `stringdb.py`: fallback `data[0]` may return a non-requested pair → require both names to match; `caller_identity=spliceanalyzer-web`.
- `panelapp.py`: keep AU→UK order and a simple 300 s circuit breaker (in memory), cap disorders at 5; treat 429 with exponential backoff.
- `gene_ontology.py` (MyGene `fields=go`): keep 8 terms per aspect; also request `summary, genomic_pos, refseq, ensembl, uniprot, pfam, interpro, pathway, alias, name, HGNC, MIM` in the same call (one request per gene instead of four services).
- `uniprot.py`: query `gene_exact:{SYM} AND organism_id:9606 AND reviewed:true`, add `fields=ft_domain,xref_pfam,xref_interpro,length,sequence` for protein-domain mapping.
- Europe PMC co-citation (only when STRING `tscore > 0`): PORT.

### 2.8 Router-level logic (`routers/*.py`) that must survive as pure functions

| Router function | Logic | Verdict |
|---|---|---|
| `events.list_events` | Filters `event_type`, `gene_symbol ILIKE`, `fdr ≤`, `p_value ≤`, `|ΔΨ| ≥`; sort `fdr|p_value|abs_inc_level_diff|gene_symbol`; page 50 | **PORT** as in-memory filter/sort over typed arrays (virtualised table). |
| `events.get_manhattan` | All points if ≤ 50 000 else all `fdr < 0.05` + systematic sample of the rest; sorted lexicographically by chr (bug: chr10 before chr2) | **PORT+FIX** natural chromosome order (1..22, X, Y, M). |
| `deep_analyses.create` | `is_sig = fdr ≤ fdr_thr AND |ΔΨ| ≥ dpsi_min` (p-value threshold stored but ignored; `modules` never used) | **PORT+FIX**: apply p-value threshold when set; add the coverage rule; keep the auto-name `{genes}-FDR{x}-PSI{y}-{date}`. |
| `deep_analyses._compute_group_stats` | Means/medians, canonical %, PPT, frame counts, BP %, PWMs, consensus, intron sizes | **PORT** (one implementation shared by UI and reports). |
| `deep_analyses._compute_stat_tests` | 13 tests (PDF text says 9, README ~9): Welch on ΔΨ, exon size, PPT score, PPT T content, PPT C content, upstream intron size, downstream intron size; two-proportion z on GT, AG, in-frame, BP found, upstream GT, downstream AG; no correction | **PORT+FIX**: add Mann-Whitney U for skewed sizes (documented limitation), report BH-adjusted q alongside raw p, state "13 tests" (see ORIGINAL_CODE_FIXES.md #18c). |
| `_welch_t_test`, `_regularized_beta` (Lentz), `_proportion_z_test`, `_normal_cdf` | Pure-Python statistics | **PORT** (or use `jstat` for the incomplete beta; keep the erfc-based Φ). |
| `splice._run_compute_background` | Chunks of 2000 events: MANE boundaries → windows → features → MANE frame → upsert | **REPLACE** by a Web Worker pipeline with progress events (section 4.4). |
| `splice.get_splice_patterns` | Size bins of 25 nt capped at 500, donor `[:9]`, acceptor `[-23:]`, `n_gt/n_ag`, PPT scores (first 100), BP %, IUPAC consensus, PWM, frame counts | **PORT**. |
| `splice.get_mane_transcript` | Exons of the MANE transcript + rank | **PORT** from the bundled JSON. |
| `export.py` (3194 lines, reportlab/openpyxl) | Excel: "Significant Events" sheet (27 core columns + PanelApp/GO/STRING optional) + "Summary" sheet; PDF: title page, sections A–F, top events, MANE flanking-correction note, landscape summary schematic, appendices A (methodology), B (references [1]–[10] + [11]–[28] hnRNP), C (statistics), closing note | **REPLACE** with client-side generation: SheetJS/exceljs for XLSX (same columns), jsPDF + svg2pdf.js for the PDF with the same section structure and the same methodology/reference text (section 7.8). Fix the text/code mismatches: "9 tests" (13 are run), permutation "50/100/250/500" (only 500 was run), hnRNP "groups < 5 events skipped" (not implemented), Enrichr "top 10" (PDF shows 5), frame-breakdown denominators including `unknown`. The SVG side-dump to `/data/svg_exports` becomes a user download. |
| `analyses.*`, `genes.*`, `annotations.*` | CRUD and proxies | **REPLACE** by local state; proxies disappear (direct fetch). |
| `main._setup_fasta`, `/debug/fasta`, `/health` | Server plumbing | **DROP**. |

### 2.9 Frontend components (`rmats-viz/frontend/src`)

| Component | Keep? | Notes for the port |
|---|---|---|
| `FileUploadZone`, `GroupMappingDialog`, `GeneAutocomplete` | PORT | Restyle as Sashimi-viewer drop zone / header chips; group labels default "Subjects"/"Controls"; gene autocomplete via MyGene `symbol:{q}*`. |
| `EventsTable`, `EventsTableColumns`, `EventTypeBadge` | PORT+FIX | Single sort control (today client and server sorts coexist); virtualised rows; type badges restyled (section 5.9). |
| `ManhattanPlot` (custom SVG, GRCh38 chromosome sizes, `-log10(FDR)`, FDR 0.05 line, event-type colours, mutated-gene markers, tooltip, click → detail card) | PORT | Recolour with Sashimi-viewer chart conventions (section 5.8); natural chr order; add ΔΨ volcano view. |
| `EventDetailCard` | PORT | As Sashimi-viewer popover recipe. |
| `Top10View` + `SidebarNav` | REPLACE | Sashimi-viewer has no sidebar: use the segmented switch and view tabs of its `dev` branch. Drop the `pathways`/`stringdb` dead modes. |
| `AnnotatedCard` (gene, GO, PanelApp, UniProt tooltip, STRING interaction diagram) | PORT | Restyle; one MyGene call per gene; STRING diagram keeps the 7 channel colours (section 5.10). |
| `SpliceView` + `ExonDiagram` (1072 lines, SE-only cassette topology, arcs, site boxes, PPT bar, BP circle, hover nucleotide strips, frame badge) | REPLACE | New event-type-aware diagram (SE, A3SS, A5SS, RI, MXE) drawn with Sashimi-viewer's transcript/arc conventions (section 7.5). |
| `SpliceSiteTrack`, `PPTTrack`, `MANETranscriptTrack` | PORT | Base colours switch to IGV convention used by Sashimi-viewer (A green, C blue, G orange, T red: `#1a9e37 #2452d6 #d9861c #d6332b`); MANE track = Sashimi-viewer transcript panel. |
| `ConsensusLogoPanel` (freq/bits modes, small-sample correction, SVG export) | PORT | Keep both modes; letters stacked with `transform scale`. |
| `SpliceSequenceLogo` | DROP | Dead code. |
| `ConsensusExonView` (cohort-mean diagram with a pseudo-FDR derived from % canonical) | DROP the pseudo-FDR | Keep the cohort schematic, drive dashes by "canonical < 95 %" explicitly. |
| `MotifPatternPanel` (876 lines: patterns, size histogram, logos, PPT bars, frame bars, comparison table) | PORT | Split into small components. |
| `HnRNPMotifPanel` (table + protein × region heatmap, enhancer/silencer rings) | PORT+NEW | Add the rMAPS2 positional line plots. |
| `EnrichrPanel`, `PermutationPanel` (dual histogram), `MutatedGenePanel`, `PatternComparisonPanel` | PORT | |
| `ExcelExportModal`, `PdfExportModal` | PORT | Sections a–f + top events; generation is local. |
| `ScienceNote` + `lib/references.ts` | PORT | Registry of 18 references + the 18 hnRNP references + new ones (section 13). |
| `ZoomableContainer` | DROP | Sashimi-viewer uses Ctrl+drag / Ctrl+wheel on the SVG itself; reuse that interaction model. |
| `ThemeContext` (dark mode) | DROP | Sashimi-viewer is light-only (`darkMode={false}`, "always light theme for readability"). |
| `LanguageContext` (EN/FR, 485 keys) | DROP by default | Sashimi-viewer is English-only with typographic punctuation (·, ′, →, ≥, ψ). Keep the FR strings out of the first release; an i18n layer can be added later without design impact. |
| TanStack Query, Next.js routing, `app/api/v1` proxy | DROP | No server; state in React + workers + IndexedDB (section 4). |

### 2.10 Other findings worth recording
- `sample_groups.sample_names` is stored but never used: rMATS `SAMPLE_1/SAMPLE_2` are positional. The new app must let the user name replicates (from `summary.txt` or the rMATS `-b1/-b2` lists if provided) purely for display.
- `permutation.observed_delta` recomputes ΔΨ from PSI strings instead of using `IncLevelDifference`; keep rMATS' value as the displayed ΔΨ and use the recomputed one only inside the permutation.
- The PDF bibliography numbering [1]–[28] (see `HNRNP_REMOVED_REFERENCES.md`) must be reproduced.
- `plan.md` (pipeline simplification) is implemented; `FUTURE_EVENT_TYPES_PLAN.md` (MXE/A3SS/A5SS roadmap) is the seed of section 9 and is superseded by it.

---

## 3. External API accesses: current inventory and in-browser feasibility

### 3.1 Every external access of the current application (exact URLs)

| # | Service | Endpoint(s) as called today | Used by | Auth |
|---|---|---|---|---|
| 1 | NCBI FTP (GRCh38 FASTA) | `https://ftp.ncbi.nlm.nih.gov/genomes/all/GCA/000/001/405/GCA_000001405.15_GRCh38/seqs_for_alignment_pipelines.ucsc_ids/GCA_000001405.15_GRCh38_no_alt_analysis_set.fna.gz` (~800 MB) | `main._setup_fasta`, `data/setup_grch38_fasta.sh` | none |
| 2 | NCBI FTP (MANE GFF3) | `https://ftp.ncbi.nlm.nih.gov/refseq/MANE/MANE_human/{current|release_1.4|release_1.3}/MANE.GRCh38.v1.x.ensembl_genomic.gff.gz` | docker-compose startup, `data/setup_mane_gff3.sh` | none |
| 3 | Ensembl REST | `GET /sequence/region/human/{chr}:{s}..{e}?content-type=application/json` (chr without `chr`, M→MT); `GET /lookup/id/{ENSG}?expand=1`; `GET /overlap/region/human/{chr}:{s}-{e}?feature=transcript`; `GET /lookup/id/{ENST}?expand=1`; `GET /overlap/id/{ENST}?feature=cds`; `GET /lookup/symbol/{species}/{symbol}` | `sequence.py`, `mane.py`, `ensembl.py` | none, UA `rmats-viz/1.0` |
| 4 | MyGene.info | `GET https://mygene.info/v3/query?q=symbol:{Q}*&species=human&fields=symbol,ensembl.gene&size={n}&sort=_score`; `GET …/query?q=ensembl.gene:{ENSG}|symbol:{SYM}&fields=go,symbol&species=human&size=1` | `ensembl.py` (autocomplete), `gene_ontology.py` | none |
| 5 | UniProt | `GET https://rest.uniprot.org/uniprotkb/search?query=gene_exact:{SYM} AND organism_id:9606 AND reviewed:true&fields=cc_function,protein_name,accession&format=json&size=1` | `uniprot.py` | none |
| 6 | STRING | `GET https://string-db.org/api/json/network?identifiers={A}%0D{B}&species=9606&caller_identity=rmats-viz` (+ UI link `https://string-db.org/cgi/network?identifiers=…`) | `stringdb.py` | none |
| 7 | Europe PMC | `GET https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=("A" AND "B") SRC:MED&format=json&pageSize=5&resultType=lite&sort=RELEVANCE&synonym=TRUE` (fallback `A AND B AND SRC:MED`) | `stringdb.py` (only if `tscore > 0`) | none |
| 8 | PanelApp Australia | `GET https://panelapp.agha.umccr.org/api/v1/genes/?entity_name={SYM}&format=json` (fallback `entity_name__icontains`), paginated `next`, ≤ 10 pages | `panelapp.py` | none |
| 9 | PanelApp UK | `GET https://panelapp.genomicsengland.co.uk/api/v1/genes/?entity_name={SYM}&format=json` | `panelapp.py` | none |
| 10 | Enrichr | `POST https://maayanlab.cloud/Enrichr/addList` (multipart `list`, `description`); `GET https://maayanlab.cloud/Enrichr/enrich?userListId={id}&backgroundType={lib}` for `KEGG_2021_Human, GO_Biological_Process_2023, GO_Molecular_Function_2023, Reactome_2022, WikiPathway_2023_Human` | `enrichr.py` | none |
| 11 | Local binaries/files | `samtools faidx /data/GRCh38.fa`, `/data/mane_cache.db` (SQLite), `/data/MANE.GRCh38.ensembl_genomic.gff.gz`, `/data/svg_exports/{deep_id}/*.svg` | backend | — |
| 12 | Frontend UI links | `https://www.ensembl.org/Homo_sapiens/Gene/Summary?g={ENSG}`, `https://www.uniprot.org/uniprotkb/{acc}`, `https://panelapp.agha.umccr.org/panels/entities/{symbol}/`, QuickGO term links, PubMed links | frontend | — |

No API key exists anywhere in the current code base. The only server-only dependencies are the FASTA + samtools, the MANE GFF3 parser and PostgreSQL.

### 3.2 In-browser feasibility (CORS) of every API the new app will call

The research session could not observe live CORS headers (egress policy). Evidence grades: **S** = server source sets `Access-Control-Allow-Origin`; **D** = official documentation; **C** = public client-side JS calls it directly from browsers; **U** = unverified. **Task 10.0.3 of the work breakdown is to re-run the header check from a normal machine** (`curl -sI -H "Origin: https://<user>.github.io" <url> | grep -i access-control`).

| API | Base URL | In-browser | Evidence | Limits / notes |
|---|---|---|---|---|
| UCSC REST | `https://api.genome.ucsc.edu` | **yes (likely)** | C (React apps fetch it directly); header set at Apache level (not in hubApi C code) | ~1 request/s recommended, ~5 000/day, HTTP 429 with `Retry-After: 30`; `maxItemsOutput ≤ 1 000 000`; `start` 0-based; genome `hg38`; `getData/sequence` returns `{dna, chrom, start, end, genome}`; `getData/track;track=mane` = bigGenePred (fields `chromStart, chromEnd, name, strand, thickStart, thickEnd, blockCount, blockSizes, chromStarts, name2, exonFrames, geneName…`), MANE Plus Clinical rows included; `phyloP100way` bigWig queryable; Sashimi-viewer already uses this API from the browser (strong practical evidence). |
| Ensembl REST | `https://rest.ensembl.org` (GRCh37: `https://grch37.rest.ensembl.org`) | **yes** | D: "returns `Access-Control-Allow-Origin: *` when any Origin header is sent" | 55 000 req/h (≈ 15/s), headers `X-RateLimit-*`, 429 + `Retry-After`; `POST lookup/symbol|id` ≤ 1000; `POST sequence/region` ≤ 50 regions, slice ≤ 10 Mb; `lookup/id?expand=1&mane=1`; `overlap/region?feature=mane|transcript|exon|cds` ≤ 5 Mb; `overlap/translation/{ENSP}?feature=protein_feature` (domains). |
| MyGene.info | `https://mygene.info/v3` | **yes** | S (BioThings sets `ACAO: *`) | `GET /query?q=symbol:X&species=human&fields=…`; `POST /query` batches of 1000 (`q=a,b,c&scopes=symbol`); `POST /gene` batches; fields `go, summary, genomic_pos, exons, refseq, ensembl, uniprot, pfam, interpro, pathway.{kegg,reactome,wikipathways}, alias, name, HGNC, MIM`. No MANE flag, no PanelApp. |
| UniProt REST | `https://rest.uniprot.org` | **yes** | S (filter adds `ACAO: *`) | search with `fields=accession,protein_name,cc_function,ft_domain,xref_pfam,xref_interpro,length,sequence`; cursor pagination; 429 on abuse. |
| gnomAD GraphQL | `https://gnomad.broadinstitute.org/api` | **yes** | S (`app.use(cors())`) | `POST` `{gene(gene_symbol:"X", reference_genome: GRCh38){gnomad_constraint{pli oe_lof oe_lof_upper oe_mis lof_z mis_z}}}`; IP rate limit. |
| Enrichr | `https://maayanlab.cloud/Enrichr` | **yes (likely)** | C (Ma'ayan Lab's own browser code posts cross-origin) | limits undocumented; Speedrichr for background lists (`/speedrichr/api/addList|addbackground|backgroundenrich`); GMT libraries `geneSetLibrary?mode=text&libraryName=…` (bundle at build time). |
| STRING | `https://string-db.org/api` (pinned `https://version-12-0.string-db.org/api`) | probably, **verify** | C | `json|tsv|image|svg / network|interaction_partners|enrichment|ppi_enrichment`; `caller_identity` required by etiquette. |
| PanelApp UK / AU (**do not query per gene at runtime**; see note below the table) | `https://panelapp.genomicsengland.co.uk/api/v1`, `https://panelapp-aus.org/api/v1` (AU domain reported by the research; the old code used `panelapp.agha.umccr.org` — check which one answers, **unverified**) | probably, **verify** | C (OpenCB jsorolla web components) | 429 on per-IP bursts; `genes/{symbol}/`, `genes/?entity_name=`. |
| Europe PMC | `https://www.ebi.ac.uk/europepmc/webservices/rest` | probably, **verify** | C | used only for co-citation of gene pairs. |
| QuickGO | `https://www.ebi.ac.uk/QuickGO/services` | probably, **verify** | C | optional (MyGene GO suffices). |
| Reactome ContentService | `https://reactome.org/ContentService` | probably, **verify** | C | optional pathway links. |
| HGNC | `https://rest.genenames.org` | probably, **verify** | C | 10 req/s; optional symbol normalisation. |
| NCBI E-utilities | `https://eutils.ncbi.nlm.nih.gov/entrez/eutils` | partial, **verify** | C for `elink` only | 3 req/s (10 with key); prefer MyGene. |
| SpliceAI-lookup API | `https://spliceailookup-api.broadinstitute.org` | **no for batch** | S (CORS on) but "several requests per user per minute" | variant-centric; may be offered as an on-demand link per event, never batch. |
| OMIM | — | **no** | D: API key required | link out only (`https://omim.org/search?search={symbol}`). |
| NCBI FTP (MANE, FASTA) | — | **no at runtime** | U | build-time only. |
| GTEx portal API v2 | `https://gtexportal.org/api/v2` | yes (Sashimi-viewer uses it from the browser) | C | optional: median junction/exon expression for context. |

**PanelApp decision (2026-09-20, from the closing tests of the Python version):** per-gene PanelApp queries do not scale to rMATS datasets (tens of thousands of genes, paginated responses, timeouts, quick host exclusion, the AU host changed domain). The in-browser version must **bundle a panel snapshot** built at build time instead: download the panels of interest (at least the PanelApp Australia/Genomics England *Mendeliome* panel and any user-selected panels) once with a build script (`scripts/build-panels.mjs`: `GET /api/v1/panels/{id}/genes/?format=json`, all pages, keep `entity_name`, `confidence_level`, `mode_of_inheritance`, `phenotypes`), emit `panels.<date>.json.gz` (gene symbol → list of {panel, confidence, moi}), and look genes up locally in the browser. Live PanelApp calls are at most an optional "refresh" action, never part of the analysis path. The same bulk-first rule applies to any other per-gene service that proves slow (STRING pairs, UniProt): batch endpoints or bundled tables first, per-gene calls only on demand from an open card.

Design rule: every remote call goes through one `api/` module with a promise cache (`Map<string, Promise<T>>`, delete on reject), an IndexedDB persistent cache keyed by URL with a TTL, a per-host concurrency limiter (UCSC 2 parallel, Ensembl 6, others 4), exponential backoff on 429/5xx honouring `Retry-After`, and a "network status" chip in the header (same as Sashimi-viewer's notes row).

---

## 4. Target architecture

### 4.1 Stack (identical to Sashimi-viewer)
- Node ≥ 20 (`.nvmrc` = `22`), Vite 5.4 + `@vitejs/plugin-react` 4.7 + `vite-plugin-singlefile` 2.3 (`assetsInlineLimit: 100_000_000`, `target: 'esnext'`, `sourcemap: false`, `esbuild.drop: ['debugger']`, dev port 3000), TypeScript 5.9 strict (`jsx: react-jsx`, `moduleResolution: bundler`, `target ES2020`), React 18.3, Tailwind 3.4 default theme (no `extend`, no plugins; `content: ["./index.html","./src/**/*.{js,ts,jsx,tsx}"]`), PostCSS 8 + autoprefixer, `.editorconfig` (2 spaces, LF, utf-8).
- Build: `npm run build` = `tsc && vite build && node scripts/finish.mjs` (copies `dist/index.html` to `dist/spliceanalyzer.html` and `./spliceanalyzer.html`, committed and checked for staleness in CI like Sashimi-viewer).
- Runtime dependencies (keep the list short, all MIT/ISC/Apache unless stated): `react`, `react-dom`, `papaparse` (TSV streaming), `comlink` (worker RPC), `idb` (IndexedDB), `@gmod/indexedfasta` + `generic-filehandle2` (optional local FASTA, same libs as Sashimi-viewer), `jspdf` + `svg2pdf.js` (vector PDF), `xlsx` (SheetJS CE, Apache-2.0) or `exceljs` (styled XLSX), `simple-statistics` (Mann-Whitney, permutation helpers), `jstat` (incomplete beta, hypergeometric) or hand-written equivalents (the old backend implemented Welch/Lentz/erfc in pure Python: port them, they are small). No chart library: all plots are hand-written React SVG, as in Sashimi-viewer.
- Web Workers: `parse.worker.ts` (Papa Parse + coverage filter + dedup), `features.worker.ts` (windows, MaxEnt, PPT, BP, frame/NMD), `motifs.worker.ts` (RBP scan, rMAPS2 maps), `stats.worker.ts` (permutations, pattern tests, enrichment). Main thread never blocks.
- Static assets bundled at build time (`src/data/`): `mane.grch38.v1.5.json.gz` (section 6.3), MaxEntScan tables as Float32 binary (~400 KB), motif catalogues (hnRNP consensus, CisBP-RNA PWM subset, RESCUE-ESE/FAS-ESS/ESRseq hexamers), GMT libraries (KEGG 2021, GO BP 2023, Reactome 2022; ~5–10 MB gz total, lazy-loaded), MIDB/IAOD minor-intron list, GRCh38 chromosome sizes.
- Size budget: single HTML ≤ 6 MB without lazy assets; lazy assets fetched relative to the page (`./data/*.json.gz`) when GitHub Pages serves the folder, with an inline fallback for the single-file distribution (offer both like Sashimi-viewer's release asset).

### 4.2 Repository layout
```
spliceanalyzer-web/
  index.html                  # shell + plain-script fallback box (copy Sashimi-viewer pattern)
  spliceanalyzer.html         # built single-file artefact (tracked)
  package.json  vite.config.ts  tailwind.config.js  postcss.config.js  tsconfig.json  .nvmrc  .editorconfig
  .github/workflows/{build.yml, pages.yml, dev-preview.yml}   # copied and renamed from Sashimi-viewer
  scripts/finish.mjs          # dist copy
  scripts/build-mane.mjs      # NCBI GFF3 → mane.json.gz (build time)
  scripts/build-motifs.mjs    # CisBP-RNA / hexamer sets → json
  scripts/build-maxent.mjs    # MaxEntScan tables → Float32 binary
  docs/logo/                  # SpliceAnalyzer mark derived from the Sashimi-viewer mark (section 5.4)
  src/
    index.css                 # verbatim Sashimi-viewer index.css
    standalone/main.tsx       # page shell (header, chips, drop zone, footer)
    app/{App.tsx, state.ts, session.ts, link.ts}
    rmats/{parse.ts, schema.ts, dedup.ts, coverage.ts, types.ts}
    genome/{ucsc.ts, ensembl.ts, fasta.ts, windows.ts, revcomp.ts}
    mane/{mane.ts, frame.ts, translate.ts, nmd.ts}
    features/{maxent.ts, ppt.ts, branchpoint.ts, event-features.ts}
    motifs/{catalogue.ts, scan.ts, rmaps.ts, hexamers.ts}
    stats/{welch.ts, ztest.ts, mwu.ts, bh.ts, permutation.ts, hypergeom.ts}
    annotation/{mygene.ts, uniprot.ts, string.ts, panelapp.ts, gnomad.ts, enrichr.ts, europepmc.ts, cache.ts}
    components/{EventTable, Manhattan, Volcano, EventCard, EventDiagram, SpliceSiteTrack, PPTTrack, TranscriptTrack, Logo, PatternPanel, RbpMapPanel, PermutationPanel, EnrichmentPanel, GenePanel, ExportModal, …}.tsx
    workers/{parse.worker.ts, features.worker.ts, motifs.worker.ts, stats.worker.ts}
    export/{xlsx.ts, pdf.ts, svg.ts, png.ts, tsv.ts}
    data/                     # bundled static data (built by scripts/)
  test/                       # vitest: fixtures from the Python implementation (section 11)
```

### 4.3 State model (replaces PostgreSQL)
```ts
type EventType = 'SE'|'A3SS'|'A5SS'|'RI'|'MXE';
interface Analysis { id: string; name: string; createdAt: string; build: 'GRCh38';
  groups: [{label: string; samples: string[]}, {label: string; samples: string[]}];
  candidateGenes: {symbol: string; ensemblId?: string}[];
  files: {name: string; type: EventType; counting: 'JC'|'JCEC'; rows: number; kept: number}[];
  params: {minCoverage: number; dedupWindowBp: number; coverageRule: 'ijc+sjc'|'ijc&sjc'} }
interface Event {            // columnar storage: one typed array per field, index = event id
  id: number; type: EventType; rmatsId: number; geneId: string; symbol: string; chr: string; strand: '+'|'-';
  // generic (SE, RI, MXE): exonStart, exonEnd, upstreamES, upstreamEE, downstreamES, downstreamEE
  // MXE: exon2Start, exon2End   (1st exon = exonStart/End)
  // A3SS/A5SS: longStart, longEnd, shortStart, shortEnd, flankStart, flankEnd
  ijc1: number[]; sjc1: number[]; ijc2: number[]; sjc2: number[]; incFormLen: number; skipFormLen: number;
  pValue: number; fdr: number; psi1: number[]; psi2: number[]; deltaPsi: number; absDeltaPsi: number;
  counting: 'JC'|'JCEC'; identityKey: string }
interface Features { /* section 8.2, one record per event, filled by features.worker */ }
interface DeepAnalysis { id; analysisId; name; fdrThreshold; pValueThreshold?; deltaPsiMin; coverageRule; modules: string[];
  isSignificant: Uint8Array /* aligned with events */; nSignificant; nNotSignificant; createdAt; results: {...cached panels} }
```
Persistence: IndexedDB database `spliceanalyzer` with stores `analyses`, `events` (one blob per analysis, columnar, compressed with `CompressionStream('gzip')`), `features`, `deepAnalyses`, `apiCache` (url → {json, fetchedAt}), `sequenceCache` (`${chr}:${start}-${end}` → dna). `localStorage` only for UI conveniences (last build, favourites), as Sashimi-viewer does for GTEx favourites.

### 4.4 Processing pipeline (worker-driven, with progress)
1. Drop files → `parse.worker`: Papa Parse stream (`worker: true`, tab delimiter), per row: type-aware column mapping, numeric coercion (decimal comma), coverage filter, identity key, JC/JCEC merge, dedup → columnar arrays → main thread (`Transferable`) → IndexedDB.
2. "Annotate" (automatic after import, cancellable): batch MANE lookup from the bundled JSON (gene id → transcript, exons, CDS) → per event: MANE boundary correction, window coordinates for all splice sites of the event type → merged genomic intervals (union of all windows ±0) → **UCSC `getData/sequence` requests coalesced by gene locus** (one request per gene span ≤ 1 Mb instead of 5 per event; typical 20 k-event dataset ≈ 8 k genes ≈ 8 k requests ≈ 1–2 h at 1–2 req/s — hence the optional local FASTA accelerator and the persistent sequence cache; the UI must show throughput and allow "annotate significant events first") → `features.worker` (MaxEnt, PPT, BP, GC, frame, translation/NMD) → IndexedDB.
3. Deep analysis: `stats.worker` (pattern comparison, permutation), `motifs.worker` (region extraction from cached sequences, scans, rMAPS2 maps), enrichment (local hypergeometric on bundled GMT, optional Enrichr live), gene annotations lazily per visible card (MyGene batch of ≤ 1000 symbols first, then UniProt/PanelApp/STRING per card on demand).
4. Reports: generated from the same in-memory results.

---

## 5. Design codes (copied from Sashimi-viewer)

Source: `benjamin-cogne/Sashimi-viewer` `main` (v1.0.0, commit 292a390) — `src/index.css`, `src/standalone/main.tsx`, `src/components/SashimiViewer.tsx`, `src/components/sashimi/SpliceCartoon.tsx`, `docs/logo/generate.mjs`, `tailwind.config.js`, `index.html`; plus the `dev` branch for the segmented switch and status pills. The live GitHub Pages page is the built copy of the same source (no external assets), so the source is authoritative. Licence: CC BY-NC 4.0 (attribute "Benjamin Cogné, CHU Nantes" in the footer and README of the new app).

### 5.1 Global CSS (`src/index.css`, copy verbatim)
```css
@tailwind base;
@tailwind components;
@tailwind utilities;

body {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Oxygen',
    'Ubuntu', 'Cantarell', 'Fira Sans', 'Droid Sans', 'Helvetica Neue',
    sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

/* Custom scrollbar for dark mode */
::-webkit-scrollbar { width: 8px; height: 8px; }
::-webkit-scrollbar-track { background: #1f2937; }
::-webkit-scrollbar-thumb { background: #4b5563; border-radius: 4px; }
::-webkit-scrollbar-thumb:hover { background: #6b7280; }
```
`tailwind.config.js`: `{ content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"], theme: { extend: {} }, plugins: [] }`. **Light theme only**; no CSS variables; no `prefers-color-scheme` handling.

### 5.2 Typography
- UI: system stack above (Tailwind `font-sans`); SVG plots: `const FONT = 'Inter, ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif'` (Inter is **not** loaded, falls back to system); mono: Tailwind `font-mono`.
- Scale used: `text-2xl` (close ×), `text-xl` (drop-zone title), `text-lg font-bold` (h1/h2), `text-base`, `text-sm` (inputs, primary button), `text-xs` (almost everything), `text-[12px] text-[11px] text-[10.5px] text-[10px]`; weights 400/500/600/700; `tracking-wide`/`tracking-wider` on uppercase 10 px micro-labels.
- SVG text sizes: 13 (notes), 12 (row labels), 11 (messages, exon numbers), 10.5 (sample label), 10 (track headers), 9.5 (pills, ruler, legend), 9 (axis, markers), 8.5 (chips, rotated axis titles, `letterSpacing 0.3`), 8 (tiny rotated labels).
- Typographic punctuation in all UI strings: `·`, `′`, `→`, `≥`, `≤`, `ψ`, `Δ`, `≈`; British spelling in comments and UI ("colour", "favourites").

### 5.3 Colour palette (Tailwind utilities, hex for SVG)
- Neutral: gray-50 `#f9fafb`, gray-100 `#f3f4f6` (**page background** `body.bg-gray-100`), gray-200 `#e5e7eb` (borders, grid), gray-300 `#d1d5db` (input borders, strong grid), gray-400 `#9ca3af` (faint), gray-500 `#6b7280` (muted text), gray-600 `#4b5563`, gray-700 `#374151`, gray-800 `#1f2937` (SVG text), gray-900 `#111827` (text).
- Primary indigo: 50 `#eef2ff` (hover, primary chip bg, HGVS block), 100 `#e0e7ff`, 200 `#c7d2fe`, 300 `#a5b4fc` (chip/drop-zone borders), 400 `#818cf8`, 500 `#6366f1` (crosshair, selection), **600 `#4f46e5` (primary button, `accent-indigo-600`)**, 700 `#4338ca` (hover), 800 `#3730a3` (primary chip text, logo ink), 900 `#312e81` (HGVS block text).
- Emerald: 50 `#ecfdf5`, 100 `#d1fae5`, 300 `#6ee7b7`, 600 `#059669`, 700 `#047857`, 800 `#065f46` (FASTA chip `bg-emerald-50 border-emerald-300 text-emerald-800`).
- Amber: 100 `#fef3c7`, 500 `#f59e0b`, 600 `#d97706`, 700 `#b45309` (clinical warning text, "cryptic").
- Red: 50 `#fef2f2`, 100 `#fee2e2`, 300 `#fca5a5`, 400 `#f87171`, 500 `#ef4444`, 600 `#dc2626`, 700 `#b91c1c`. Green: 50 `#f0fdf4`, 300 `#86efac`, 700 `#15803d`. Orange-600 `#ea580c`. Blue-700 `#1d4ed8`. Rose (dev): 50 `#fff1f2`, 300 `#fda4af`, 400 `#fb7185`, 700 `#be123c`, 900 `#881337`. Slate-700 `#334155`.
- Overlays: viewer modal backdrop `bg-black/70 backdrop-blur-sm`; cartoon backdrop `bg-slate-900/80`; tooltip `bg-white/95`; dark tooltip `bg-gray-900/90 text-white`.

### 5.4 SVG chart constants (copy verbatim)
```ts
export const TRACK_COLORS = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#4a3aa7']; // CVD-validated, adjacent ΔE ≥ 8
export const UNIQUE_COLOR = '#e34948'; // "unique to primary sample" red; red is never used as a track colour
export const INK = { bg: '#ffffff', text: '#1f2937', muted: '#6b7280', faint: '#9ca3af', grid: '#e5e7eb', gridStrong: '#d1d5db',
  exon: '#334155', utr: '#94a3b8', intron: '#94a3b8', geneBand: 'rgba(99, 102, 241, 0.035)', select: '#6366f1' };
export const FONT = 'Inter, ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif';
export const BASE_COLORS = { A: '#1a9e37', C: '#2452d6', G: '#d9861c', T: '#d6332b', N: '#6b7280' }; // IGV convention
export const READ_FILL = '#c8cdd6'; export const INSERTION_COLOR = '#7c3aed'; export const STAR_COLOR = '#f59e0b'; // star stroke '#92400e'
export const SNP_SNV_COLOR = '#2563eb'; export const SNP_INDEL_COLOR = '#b45309';
export const SAME_SENSE_COLOR = '#475569'; export const ANTISENSE_COLOR = '#7c3aed';
export const FRAME_IN_COLOR = '#16a34a'; export const FRAME_OUT_COLOR = '#dc2626'; export const FRAME_UTR_COLOR = '#9ca3af'; export const FRAME_GLYPH_R = 6.5;
export const AA_FILLS = ['#cbd5e1', '#94a3b8']; export const AA_START_COLOR = '#16a34a'; export const AA_STOP_COLOR = '#dc2626';
export const KNOWN_VARIANT_COLORS = { snv: '#dc2626', indel: '#dc2626', ins: '#06b6d4', del: '#a855f7', dup: '#10b981', inv: '#f59e0b', cnv: '#ec4899', bnd: '#64748b', other: '#dc2626' };
// dev branch: PSEUDO_EXON_COLOR '#7c3aed', RETENTION_COLOR '#0d9488' (intron retention, teal "IR" pills), READ_DISCORDANT_FILL '#fcd34d', PAIR_LINK_COLOR '#9ca3af'
// cartoon: DOMAIN_COLORS = ['#2a78d6','#1baf7a','#eda100','#e87ba4','#4a3aa7','#008300','#eb6834']; scene gradient '#f8fafc' → '#eef2ff' rx 14; drop shadow feDropShadow dy 1.5 stdDeviation 1.5 '#0f172a' @0.18
// layout: PLOT_LEFT 64, PLOT_RIGHT_PAD 36, RULER_H 42, COVERAGE_H 130, TRACK_LABEL_H 20, JUNC_BASE_H 30, JUNC_LEVEL_STEP 17, LABEL_H 15, TRACK_GAP 10,
//         TRANSCRIPT_H 78, NEIGHBOUR_ROW_H 22, ALT_TX_ROW_H 18, ALT_TX_HEADER_H 22, SNP_PANEL_H 46, LEGEND_ROW_H 22, panel frames rect fill=none stroke=#e5e7eb rx=4, baseline #d1d5db
```
Chart conventions: white background rect; light-grey panel frames; per-track axis ticks on the left (`text-anchor: end`, 9 px muted) with dashed gridlines `#e5e7eb` `stroke-dasharray 2 4` at 50 % and 100 %; rotated axis title 8.5 px faint; coverage fill = track colour at 26 % alpha with 1.3 px stroke; arcs = cubic Bézier `M x1,y1 C x1,cy x2,cy x2,y2` with apex `18 + (level−1)·17` px above the higher endpoint, stroke width `min(4.5, 1 + log2(count)·0.55)`, white halo under each arc, **dashed `5 3.5` for non-canonical**, read-count pill (white, 15 px high, rounded 7, border = arc colour, bold 9.5 px) with a frame glyph (green disc "=" in frame `#16a34a`, red disc with white bar frameshift `#dc2626`, grey UTR `#9ca3af`, r 6.5); transcript model: CDS 18 px tall `#334155`, UTR 9 px `#94a3b8`, intron line with chevrons, exon numbers in white inside CDS, header "GENE  NM_… · MANE Select · + strand · N exons"; reverse-strand genes drawn 5′→3′ left→right with a red "reverse strand, axis flipped" warning; gene band `rgba(99,102,241,0.035)`; interactive-only elements tagged `data-export="skip"` so SVG exports are clean; legend rows 22 px at the bottom.

### 5.5 Logo, favicon
Sashimi-viewer mark (64×64): three indigo exons `#3730a3` (rects `x=4|25|46 y=46 w=14 h=10 rx=1.5`), two canonical arcs `M11 46 Q21.5 14 32 46` and `M32 46 Q42.5 14 53 46` (stroke 3.5, round caps), one dashed red aberrant arc `M11 46 Q32 -26 53 46` (`#dc2626`, `stroke-dasharray 5 4`), intron ticks `M18 51 H25 M39 51 H46`. Palette light `{ink:'#3730a3', red:'#dc2626', text:'#1c1b33', muted:'#5f5e7a'}`, dark `{ink:'#a5b4fc', red:'#f87171', text:'#eceaf6', muted:'#9b99b5'}`; lockup wordmark IBM Plex Sans 600 + 400 at 30 px outlined to paths; favicon = heavier cut inlined as `data:` SVG; PNGs 16–512; `social-preview.png`.
**SpliceAnalyzer mark**: same construction and palette, same 64×64 grid, with a distinguishing element that keeps the family look: keep the three exons and the two canonical arcs, replace the dashed red skipping arc by a red dashed **alternative acceptor bracket** on the middle exon (`M25 46 h-6` red dashed + small red AG tick) or simply keep the red arc and add a small magnifier ring `#3730a3` at the apex; wordmark "Splice" (600) + "analyzer" (400). Generate with a copy of `docs/logo/generate.mjs`.

### 5.6 Layout structure
- `body.bg-gray-100`; root `div.min-h-screen.bg-gray-100.text-gray-900`; optional DEV banner (`repeating-linear-gradient(135deg, #b91c1c 0 14px, #dc2626 14px 28px)`, white text, `[DEV]` tab title, red favicon) when built with `VITE_DEV_MODE=1`.
- `<header class="bg-white border-b border-gray-200 px-5 py-3 flex flex-wrap items-center gap-x-6 gap-y-2">`: logo (34 px, `shrink-0`) + title block (`h1 text-lg font-bold` "Splice<span class=font-normal>analyzer</span>", two subtitle lines `text-xs text-gray-500`: privacy note "Files never leave your computer…" and the amber warning `text-amber-700` "⚠ Research use only — check every annotation before it goes into a report"); **Build** select; **"+ Add rMATS files"** secondary button; file chips; gene/candidate-gene input + indigo **Open**/**Add** button with `ml-auto`.
- Notes row `px-5 py-2 text-xs space-y-0.5` (unmatched files, missing MANE, network status; errors `text-red-600`, info `text-indigo-600`).
- Content: either the empty-state drop zone (`m-6 p-10 border-2 border-dashed border-indigo-300 rounded-2xl bg-white text-center`, title `text-xl font-semibold text-indigo-700` "Drop rMATS output files here", instructions `text-sm text-gray-600`, status line `text-xs text-gray-500`) or `div.p-3` containing the workspace `bg-white text-gray-900 w-full` with its own toolbar `flex flex-wrap items-center justify-between gap-x-4 gap-y-2 px-5 py-3 border-b border-gray-200`, body `relative overflow-x-auto px-2 pb-2 pt-1`, hint line `px-5 pb-2 text-[10.5px] text-gray-500`.
- Page footer `px-5 py-3 text-[11px] text-gray-500 flex flex-wrap gap-x-3 gap-y-1`: "Author (institution, year) · made with Claude … · GitHub (underline decoration-dotted) · licence · design after Sashimi-viewer (Benjamin Cogné, CHU Nantes, CC BY-NC 4.0)".
- **No sidebar, single column, full width, no responsive breakpoints** (no `sm:/md:/lg:` anywhere); responsiveness via `flex-wrap`, dropdowns that flip side when overflowing, SVG width tracking the container (`ResizeObserver`, min 480 px).
- Spacing scale used: 0.5, 1, 1.5, 2, 2.5, 3, 4, 5, 6, 10. Radii: `rounded` 4 px (inputs, small buttons, HGVS block), `rounded-md` 6 px (tooltips), `rounded-lg` 8 px (dropdowns, popovers), `rounded-xl` 12 px (modal), `rounded-2xl` 16 px (drop zone, big modal card), `rounded-full` (chips, pills, play button), `rounded-sm` 2 px (swatches). Shadows: `shadow` (round button), `shadow-lg` (tooltips), `shadow-xl` (dropdowns), `shadow-2xl` (popover, modals). Motion: `transition-colors` (150 ms) on buttons; `transition-opacity duration-700` for verdict badges; spinners `w-3 h-3 rounded-full border-2 border-indigo-500 border-t-transparent animate-spin`; `animate-pulse` badges. No toasts; errors as red text; loading states as faint text ("loading…", "updating…", "computing…" in `text-indigo-600`).

### 5.7 Component recipes (Tailwind classes to copy verbatim)
- Primary button: `px-3 py-1 text-sm rounded bg-indigo-600 text-white disabled:opacity-40 hover:bg-indigo-700`
- Secondary/file button: `px-3 py-1 text-xs rounded border border-gray-300 bg-white hover:bg-indigo-50 cursor-pointer font-medium`
- Toolbar button: `px-2 py-0.5 text-xs rounded border border-gray-200 hover:bg-indigo-50 hover:border-indigo-300 transition-colors` (wider: `px-3 py-1 font-medium`; success `bg-green-50 border-green-300 text-green-700`; error `bg-red-50 border-red-300 text-red-700`)
- Text input: `border border-gray-300 rounded px-2 py-1 text-sm w-48 bg-white` (header) / `bg-white text-gray-800 border-gray-300 w-40 px-2 py-0.5 text-xs rounded border` (toolbar; `border-red-400` on error); number `w-14 px-1.5 py-0.5`; select `border border-gray-300 rounded px-1 py-0.5 text-xs bg-white`
- Checkbox toggle: `<label class="flex items-center gap-1 text-xs text-gray-500 select-none"><input type="checkbox" class="accent-indigo-600">…</label>` (disabled `text-gray-300`)
- Chip: `flex items-center gap-1 px-2 py-0.5 rounded-full text-xs border`; primary `bg-indigo-50 border-indigo-300 text-indigo-800`; neutral `bg-gray-50 border-gray-300 text-gray-700 hover:border-indigo-300 cursor-pointer`; emerald data chip `bg-emerald-50 border-emerald-300 text-emerald-800`; rose variant chip `bg-rose-50 border-rose-300 text-rose-900`
- Dropdown: `absolute top-full left-0 mt-1 bg-white border-gray-200 border rounded-lg shadow-xl z-20 w-64 max-h-60 overflow-hidden`; search `border-b w-full px-3 py-2 text-xs`; rows `w-full text-left px-3 py-1.5 text-xs hover:bg-indigo-50`; section label `px-3 pt-1.5 text-[10px] uppercase tracking-wide text-gray-500`
- Tooltip: `pointer-events-none absolute z-20 min-w-[190px] rounded-md border border-gray-200 bg-white/95 px-2.5 py-1.5 text-xs shadow-lg`; dark: `rounded-md bg-gray-900/90 text-white text-[11px] px-2.5 py-1.5 shadow-lg max-w-[320px]`
- Popover (event detail): `absolute z-30 w-[540px] max-w-[95%] rounded-lg border border-gray-300 bg-white shadow-2xl text-xs`; code block `mx-3 mt-2 rounded bg-indigo-50 px-2 py-1.5 font-mono text-[11px] text-indigo-900`; table `mx-3 my-2 w-[calc(100%-1.5rem)] border-collapse`, caption `text-left text-[10.5px] font-semibold text-gray-700 pb-0.5`, `th text-left text-[10px] font-semibold uppercase tracking-wide text-gray-500 py-1 pr-2`, `tr border-t border-gray-100`, `td py-1 pr-2` (first column `text-gray-800`, numbers `font-mono text-gray-900`); note `px-3 pb-2 text-[10px] text-gray-500`
- Pill buttons: solid `px-2 py-0.5 rounded-full bg-indigo-600 text-white text-[11px] font-semibold hover:bg-indigo-700`; outline `px-2.5 py-1 rounded-full border text-xs font-semibold border-indigo-300 text-indigo-700 hover:bg-indigo-50` (active `bg-indigo-600 border-indigo-600 text-white`); neutral `px-2 py-0.5 rounded-full border border-gray-300 text-gray-600 hover:bg-gray-50`
- Status pills: ok `bg-emerald-100 text-emerald-700`, bad `bg-red-100 text-red-700`, warn `bg-amber-100 text-amber-700` (`px-1.5 rounded-full text-[10px] font-semibold`)
- Segmented switch (dev): wrapper `inline-flex items-center rounded-full bg-gray-100 border border-gray-200 p-0.5 text-xs select-none`; option `flex items-center gap-1.5 px-2.5 py-0.5 rounded-full transition-all`; active `bg-white text-indigo-700 font-semibold shadow-sm ring-1 ring-indigo-200`; inactive `text-gray-500 hover:text-gray-800`; 12×12 inline stroke icons (`currentColor`, strokeWidth 1.5)
- View tabs (dev): active `bg-indigo-600 border-indigo-600 text-white`; banner `mx-5 mt-2 px-3 py-2 text-xs rounded-lg border border-indigo-200 bg-indigo-50 text-indigo-900`; export button `border-emerald-300 bg-emerald-50 text-emerald-900 hover:bg-emerald-100`; tiny badge `px-1 rounded text-[9px] font-bold leading-4 bg-emerald-600 text-white`
- Close ×: `text-gray-400 hover:text-gray-700 text-2xl leading-none px-1`; modal backdrop `fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-start justify-center p-4 overflow-y-auto`; modal card `bg-white rounded-2xl shadow-2xl` (big) or `rounded-xl shadow-2xl border border-gray-200` (viewer)
- Icons: **no icon library**; Unicode glyphs (★ ✎ × ⚠ ▶ ❚❚ 🔍 📷 🎬 ⛔ ✓ ✂ →) and hand-drawn inline SVG only.
- Fallback error box in `index.html` (plain script, shown if `#root` is empty after 2.5 s or on `error`/`unhandledrejection`): amber `#fffbeb` background, `#fbbf24` border, error rows `#fee2e2`/`#991b1b`, warning rows `#fef3c7`/`#92400e`, `ui-monospace, Consolas, monospace` 12 px.

### 5.8 Mapping of SpliceAnalyzer visuals onto these codes
- Group 1 / group 2 colours: `TRACK_COLORS[0]` `#2a78d6` and `TRACK_COLORS[1]` `#eb6834` (never the old red/blue pair); ΔΨ < 0 (more skipping in group 1) and ΔΨ > 0 use the two group colours, not red/blue.
- Event-type colours (badges, Manhattan): SE `#2a78d6`, A5SS `#eda100`, A3SS `#1baf7a`, MXE `#4a3aa7`, RI `#0d9488` (the `RETENTION_COLOR` teal of the dev branch); badge recipe = chip with 10×10 colour square + label, as sample chips.
- Significance: FDR line and significant points use `#6366f1` (`INK.select`), "unique/aberrant" emphasis uses `UNIQUE_COLOR` `#e34948`; never a green/amber/red traffic light for p-values — use `font-semibold` + the status pills.
- Splice-site sequences: `BASE_COLORS` (IGV). Canonical GT/AG columns: light indigo band `rgba(99,102,241,0.12)` (the region-zoom overlay colour) instead of the old yellow.
- Frame: `FRAME_IN_COLOR / FRAME_OUT_COLOR / FRAME_UTR_COLOR` glyphs, as on Sashimi arcs.
- Exon/UTR/intron in diagrams: `INK.exon / INK.utr / INK.intron`; the regulated exon highlighted with `INK.select` stroke; alternative sites (A3SS/A5SS) as amber `#b45309` dashed "cryptic" outline; retained intron filled `#0d9488` at 26 % alpha.
- Logos: letter colours = `BASE_COLORS`; axis and gridlines as charts above.
- Heatmaps (motif × region): sequential indigo scale (`#eef2ff → #4f46e5`) for enrichment, `#fee2e2 → #dc2626` for depletion; enhancer/silencer rings `#059669` / `#ea580c` (kept from the old app, they are within the palette).
- STRING evidence channels keep STRING's own colours (`nscore #2CA02C, fscore #D62728, pscore #1F77B4, ascore #333333, escore #E377C2, dscore #17BECF, tscore #FFC000`), the two gene nodes use `TRACK_COLORS[3]` `#eda100` and `TRACK_COLORS[0]` `#2a78d6`.

### 5.9 Code conventions (copy from Sashimi-viewer)
TypeScript strict, React function components + hooks, `type` imports, module-level `SCREAMING_CASE` constants grouped under `// ==================== Section ====================` banners, dense JSDoc with method references on every exported symbol, JSX inline `style` only for dynamic values, Tailwind classes otherwise, promise caches per API client, request sequence numbers for stale-response protection, `useMemo` for layouts, rAF-throttled mouse handlers, `ResizeObserver` for widths, coordinates documented as 0-based half-open internally and 1-based inclusive at API boundaries, `_internal` exports for tests, CI = `tsc` + `vite build` (+ vitest for this project).

---

## 6. Data layer: rMATS ingestion, genome, MANE, caches

### 6.1 rMATS files and columns (rmats-turbo README conventions)
- Accepted: `{SE,MXE,A3SS,A5SS,RI}.MATS.{JC,JCEC}.txt` (the statistical tables), optionally `fromGTF.{type}.txt` / `fromGTF.novelJunction|novelSpliceSite.{type}.txt` (annotation only; rows without counts are kept as "unquantified" instead of being dropped), `summary.txt` (event counts per type shown in the intake panel), `b1.txt`/`b2.txt` sample lists (names only). JC vs JCEC recorded per event; when both are loaded the user chooses the primary counting mode (default JC for SE/A3SS/A5SS/MXE, **JCEC recommended for RI** as junction-only counts cannot support intron retention well).
- Shared columns: `ID, GeneID, geneSymbol, chr, strand, IJC_SAMPLE_1, SJC_SAMPLE_1, IJC_SAMPLE_2, SJC_SAMPLE_2, IncFormLen, SkipFormLen, PValue, FDR, IncLevel1, IncLevel2, IncLevelDifference` (= mean(IncLevel1) − mean(IncLevel2), sign convention of the old app: ΔΨ < 0 = more skipping in group 1).
- Type-specific coordinates (all `*_0base` starts 0-based, ends 1-based = BED half-open):
  - **SE**: `exonStart_0base, exonEnd, upstreamES, upstreamEE, downstreamES, downstreamEE`; inclusion isoform = target exon.
  - **MXE**: `1stExonStart_0base, 1stExonEnd, 2ndExonStart_0base, 2ndExonEnd, upstreamES, upstreamEE, downstreamES, downstreamEE`; **inclusion = 1st exon on "+", 2nd exon on "−"** (rMATS convention; the two exons are listed in genomic order).
  - **A3SS / A5SS**: `longExonStart_0base, longExonEnd, shortES, shortEE, flankingES, flankingEE`; inclusion = long exon; long and short share one boundary; the alternative sites are `longExonStart_0base` vs `shortES` (A3SS on +, A5SS on −) or `longExonEnd` vs `shortEE` (A5SS on +, A3SS on −). The differential segment = `[min(longStart, shortStart), max(longStart, shortStart))` or the end-side equivalent; its length is the "alternative site distance" (3 nt = NAGNAG).
  - **RI**: `riExonStart_0base, riExonEnd, upstreamES, upstreamEE, downstreamES, downstreamEE`; retained intron = `[upstreamEE, downstreamES)`; inclusion = intron retained.
- `upstream*`/`downstream*` are genomic order regardless of strand (as today); transcript-sense 5′/3′ flanks are derived from strand.
- Identity key per type (exact dedup / JC-JCEC merge): SE `SE|gene|chr|strand|es|ee|ues|uee|des|dee`; MXE adds `e2s|e2e`; A3SS/A5SS `type|gene|chr|strand|ls|le|ss|se|fs|fe`; RI `RI|gene|chr|strand|ris|rie|ues|uee|des|dee`.
- Coverage filter (default on, parameter): rule A (old app) `mean_i(IJC_i + SJC_i) ≥ 10` in both groups; rule B (Sashimi-viewer author) `mean(IJC) ≥ c AND mean(SJC) ≥ c` in each group. Both are shown in the methodology text with their exact formula.
- Dedup (parameter, default on): SE/RI/MXE greedy ±50 bp boundary rule within `(type, gene, chr, strand)`, lowest FDR then largest |ΔΨ|; A3SS/A5SS exact identity only. The count of collapsed rows is reported per file.
- Decimal comma tolerance for every numeric field; `NA`, `nan`, empty → null; per-replicate lists parsed once into `Float32Array`/`Uint32Array`.
- Test fixtures: the header of `tests/test_parser_coverage.py` (`ID GeneID geneSymbol chr strand exonStart_0base exonEnd upstreamES upstreamEE downstreamES downstreamEE IJC_SAMPLE_1 SJC_SAMPLE_1 IJC_SAMPLE_2 SJC_SAMPLE_2 IncFormLen SkipFormLen PValue FDR IncLevel1 IncLevel2 IncLevelDifference`) plus real rMATS-turbo example outputs for the four other types.

### 6.2 Genome sequence
- Primary: `GET https://api.genome.ucsc.edu/getData/sequence?genome=hg38;chrom={chr};start={0-based};end={excl}` → `{dna}` uppercase. Requests coalesced per gene locus (union of all windows of all events of the gene, padded 300 nt, capped at 1 Mb, split otherwise), 2 in flight, ≥ 500 ms spacing, 429 → wait `Retry-After`; cached in IndexedDB (`sequenceCache`) so re-analyses are instant. Minus-strand windows: fetch +, reverse-complement locally (full IUPAC).
- Accelerator: local FASTA + `.fai` (+ `.gzi` for bgzip) dropped by the user, read with `@gmod/indexedfasta` over `File.slice` (Sashimi-viewer already does this); chromosome aliasing UCSC→RefSeq: `chr1→NC_000001.11, chr2→NC_000002.12, chr3→NC_000003.12, chr4→NC_000004.12, chr5→NC_000005.10, chr6→NC_000006.12, chr7→NC_000007.14, chr8→NC_000008.11, chr9→NC_000009.12, chr10→NC_000010.11, chr11→NC_000011.10, chr12→NC_000012.12, chr13→NC_000013.11, chr14→NC_000014.9, chr15→NC_000015.10, chr16→NC_000016.10, chr17→NC_000017.11, chr18→NC_000018.10, chr19→NC_000019.10, chr20→NC_000020.11, chr21→NC_000021.9, chr22→NC_000022.11, chrX→NC_000023.11, chrY→NC_000024.10, chrM/chrMT→NC_012920.1`.
- Fallback: `POST https://rest.ensembl.org/sequence/region/human` with `{"regions":["1:101..200:1", …]}` (≤ 50 per call, `Accept: application/json`), chromosome without `chr`, `M→MT`.
- Optional: `hg38.2bit` over HTTP Range requests (`https://hgdownload.soe.ucsc.edu/goldenPath/hg38/bigZips/hg38.2bit`) with a 2bit reader (igv.js has one) — **unverified CORS**, evaluate in task 10.0.3 as a third source.

### 6.3 MANE Select bundle (build time)
- Script `scripts/build-mane.mjs`: download `https://ftp.ncbi.nlm.nih.gov/refseq/MANE/MANE_human/current/MANE.GRCh38.v1.5.ensembl_genomic.gff.gz` (≈ 9 MB; 19 363 MANE Select + 74 MANE Plus Clinical) and the `summary.txt.gz`; keep transcripts with `tag=MANE_Select` (store Plus Clinical separately, flagged); emit `mane.grch38.v1.5.json.gz`: `{ version, built, genes: { ENSG: { symbol, ensg, enst, nm, np?, chr, strand, txStart, txEnd, cdsStart, cdsEnd, exons: [[start,end],…] /* 0-based half-open, genomic order */ } }, bySymbol: {SYMBOL: ENSG} }` (~1–1.5 MB gzipped, estimate). Runtime fallbacks per gene: UCSC `getData/track;track=mane` (bigGenePred: `chromStart + chromStarts[i]`, `blockSizes[i]`, `thickStart/thickEnd`), then Ensembl `lookup/id/{ENSG}?expand=1&mane=1` + `overlap/id/{ENST}?feature=cds` filtered by `Parent`.
- Also bundled: GRCh38 chromosome sizes (for Manhattan layout), CDS phase per exon derived at load.

### 6.4 Caches and sessions
- IndexedDB stores (section 4.3). Cache TTL: sequences and MANE never expire (versioned by build/assembly), annotation APIs 30 days, enrichment results per deep analysis.
- Session file `spliceanalyzer-session-{name}-{date}.json`: `{ app: 'spliceanalyzer', version: 1, saved, build, analysis: {name, groups, candidateGenes, params, files: [{name, type, counting, sha256?}]}, deepAnalyses: [{thresholds, modules, sigIds}], view: {filters, sort, page, selectedEventKey}, sashimi?: SashimiSessionSubset }` — the event data itself is not embedded (re-drop the rMATS files, matched by name/hash), mirroring Sashimi-viewer's `SessionFile` v1 design (`app`, `version`, `saved`, `build`, files matched by relative path then name). Optionally an "Export HTML with embedded results" like Sashimi-viewer dev (`<script id="spliceanalyzer-embedded" type="application/json">`).

---

## 7. Functional specification (pages and flows)

The app is a single page (no router; views switch like Sashimi-viewer's tabs). Deep links `#…` restore state (section 7.9).

### 7.1 Intake (header + drop zone)
- Drop or pick rMATS files (multi-select, folders accepted via `webkitdirectory` like Sashimi-viewer dev). Chips per file: type badge, JC/JCEC, rows, kept after filters, × remove. Unknown files listed in the notes row.
- Group labels (default "Subjects" / "Controls"), replicate names (optional, from `b1.txt`/`b2.txt` or typed), candidate genes (autocomplete via MyGene `symbol:{q}*`, chips in indigo).
- Parameters: min coverage (10), coverage rule A/B, dedup on/off + window (50), counting mode per type, genome build (GRCh38 only in v1; GRCh37 later via `grch37.rest.ensembl.org` + `hg19`).
- "Analyse" → parse worker with progress; summary line "N events kept of M (X removed by coverage, Y collapsed)"; `summary.txt` counts displayed if provided.
- Optional local FASTA chip (emerald) as in Sashimi-viewer.

### 7.2 Events view (table + plots)
- Toolbar (Sashimi-viewer toolbar recipe): event-type multi-select chips, gene filter input, FDR / p-value / |ΔΨ| numeric inputs with the old log-scale sliders re-styled as `accent-indigo-600` ranges, "significant only" toggle, sort select, columns toggle (PSI per replicate), "Mark significant" → creates a deep analysis.
- Table (virtualised, 50 rows/page, Sashimi popover table recipe): type badge, gene, chr:coords (type-aware column set), FDR, ΔΨ (group colour + sign), direction ("↑ skipping in {g1}", "↑ inclusion in {g1}", for A3SS/A5SS "↑ proximal/distal site in {g1}", RI "↑ retention", MXE "↑ exon 1/2"), |ΔΨ|, mean PSI per group, coverage, counting, feature summary chips once annotated (MaxEnt Δ, frame glyph, NMD, PPT, BP). Row click → event popover; ⟶ "Open in Sashimi-viewer" link; ★ pin.
- Manhattan plot (hand-written SVG, natural chr order, `-log10(FDR)`, FDR line at 1.301, event-type colours of section 5.8, candidate-gene markers, hover tooltip, click → popover) and a volcano plot (ΔΨ vs `-log10(FDR)`), both exportable as SVG/PNG.
- Per-gene event map: all events of a gene on the MANE model (Sashimi-viewer transcript panel) with arcs per event type, to see cross-type overlaps.

### 7.3 Event popover (540 px card)
Title `GENE · SE · chr:start-end`, HGVS-like description using the MANE transcript (exon numbers, "exon 4 skipped", "3′ss shifted by 3 nt", "intron 5 retained", "exon 2 ⇄ exon 3"), rMATS stats table (`sample | IJC | SJC | PSI` per replicate, group means, ΔΨ, p, FDR), feature block (5′ss/3′ss MaxEnt for each site, PPT, BP, frame, PTC/NMD verdict with the Sashimi-viewer verdict badges, protein consequence, domains hit), buttons: "Diagram", "Sashimi-viewer ↗", "Copy HGVS", "Report card".

### 7.4 Gene panel (per event or candidate gene)
MyGene summary, GO (BP/MF/CC ≤ 8 each), UniProt function + domains, PanelApp panels (green/amber/red pills using the status-pill recipe), gnomAD constraint (pLI, LOEUF), STRING interaction with each candidate gene (7-channel diagram + Europe PMC co-citations), links (Ensembl, UniProt, PanelApp, OMIM search, gnomAD, GTEx).

### 7.5 Event diagram (replaces `ExonDiagram`, event-type aware)
Drawn with the Sashimi-viewer transcript conventions (CDS 18 px `#334155`, UTR 9 px, intron line with chevrons, exon numbers, equal-intron option) and arc conventions (Bézier, count pills, frame glyphs, dashed non-canonical):
- SE: upstream exon – skipped exon – downstream exon; inclusion arcs (two) vs skipping arc; pills show mean IJC/SJC per group.
- A3SS/A5SS: flanking exon + long/short exon with both sites marked; arcs to proximal and distal sites; differential segment hatched amber (`#fff7ed` + `#b45309` lines, the cartoon's "cryptic" pattern); nt distance label; NAGNAG badge.
- RI: two exons, retained intron filled teal 26 %; arc = splicing, block = retention.
- MXE: four exons; two mutually exclusive paths; exon 1/2 lengths and identity %.
- All: splice-site boxes with MaxEnt scores (`+8.2`), PPT bar, BP marker, frame glyph, PTC marker with distance to last junction, hover nucleotide strips (`BASE_COLORS`), Ctrl+wheel zoom / drag pan / double-click reset (Sashimi-viewer interaction model), SVG/PNG export (`data-export="skip"` for interactive-only elements).

### 7.6 Deep analysis (significant vs non-significant)
Created from current thresholds (FDR ≤, p ≤ optional, |ΔΨ| ≥, coverage rule) with modules toggles (Features, Patterns, RBP maps, Permutation, Enrichment, Gene annotations). Saved in IndexedDB; list with auto-name, counts, date. Views (tabs, active `bg-indigo-600 … text-white`):
1. **Overview**: thresholds, counts per type, direction split (ΔΨ<0 / >0), annotation coverage (% events with sequence, with MANE), methodology text.
2. **Cards**: significant events as compact cards (gene, type, ΔΨ, FDR, feature chips, PanelApp pill), expandable to the diagram; sort by FDR / |ΔΨ| / chromosome / PanelApp confidence (implement it, the old one was a stub).
3. **Patterns**: per type, significant vs non-significant: size histograms (25-nt bins, mean/median lines), 5′ss/3′ss logos (freq/bits toggle, canonical columns banded), MaxEnt score distributions, PPT/BP stats, frame proportions (stacked bars in `FRAME_*` colours), NMD proportions, GC content, tests table (Welch + Mann-Whitney + two-proportion z, raw p and BH q), cohort schematic.
4. **RBP maps**: rMAPS2-style positional plots (x = position relative to each splice site, y = motif density in 50-nt windows, three lines up/down/background in `TRACK_COLORS[0]`, `TRACK_COLORS[1]`, `INK.muted`, significance ticks where Wilcoxon p < 0.05) for the selected motif catalogue; plus the region-level presence/density table and heatmap of the old app; enhancer/silencer annotation shown only in the direction-specific panels.
5. **Permutation**: iterations (50–2000), dual histogram (null in `TRACK_COLORS[0]` 45 %, observed in `TRACK_COLORS[1]` outline), exact-enumeration notice and minimum attainable p when n ≤ 4 per group, top events table, metric permutations.
6. **Enrichment**: local hypergeometric on bundled libraries (KEGG 2021, GO BP/MF 2023, Reactome 2022, WikiPathways 2023) with BH; optional "Run on Enrichr" (live) with combined score; term rows expandable to genes; background = all genes with tested events (not the genome) by default.
7. **Genes**: candidate-gene cards (rMATS counts sig/total per gene, annotations, STRING with all significant genes).

### 7.7 Sample-level views (new, cheap, informative)
PSI heatmap of significant events × replicates (rows clustered, group colour bar), PCA of PSI (the Sashimi-viewer author's notebook practice) with group colours, replicate concordance scatter (PSI group means).

### 7.8 Exports
- TSV (current filtered table), XLSX ("Significant Events" with the old 27 core columns extended per type + optional PanelApp/GO/STRING columns, header fill `BDD7EE`, banding `F2F2F2`, freeze `A2`, autofilter; "Summary" sheet), SVG/PNG of every plot (2× PNG), PDF report (jsPDF + svg2pdf.js, A4 portrait with a landscape schematic page; sections: title, A global summary, B significant events, C comparison, D permutation, E RBP/hnRNP, F enrichment, top events, MANE flanking-correction note, schematic, Appendix A methodology, Appendix B references [1]–[10] always + [11]–[28] when E is included, Appendix C statistics, closing note with repository URL), session JSON, "Export HTML with embedded results" (optional).
- Methodology text is generated from the actual parameters used (thresholds, iterations actually run, number of tests actually performed).

### 7.9 Interoperability with Sashimi-viewer (read-only on their side)
- **Out-links per event** (main branch, stable): `https://benjamin-cogne.github.io/Sashimi-viewer/#locus={chr}:{start+1}-{end}&pad={n}&label={GENE}%20{TYPE}%20FDR%3D{fdr}&gene={GENE}&build=GRCh38` (`locus` = the event span from the upstream exon end to the downstream exon start; `label` comma-separated; `reads=1` optional). Sashimi-viewer persists nothing between sessions, so the user adds their BAM/CRAM files there after the page opens on the locus (or loads a Sashimi-viewer session JSON, `dev` branch).
- **In-links accepted by SpliceAnalyzer** (same parameter names): `#gene=`, `#locus=`, `#build=`, `#label=`, plus `#event=` (identity key) and `#fdr=&dpsi=` thresholds; a query string is accepted as fallback, as in `link.ts`.
- **Session bridge**: read Sashimi-viewer session JSON v1 (`app: 'sashimi-viewer'`) to import `gene`, `build`, `knownVariants` (as candidate loci) and sample names; write a Sashimi-viewer-compatible session JSON (`samples: []`, `gene`, `knownVariants: [{text, label}]` for the selected events) that the user can load in Sashimi-viewer.
- **Selected-events file**: `spliceanalyzer-selection.tsv` with the rMATS columns of the marked events (the natural handoff if Sashimi-viewer later gains rMATS input; it does not today).

---

## 8. Scientific module specifications (algorithms and constants to port)

### 8.1 Sequence windows per splice site (transcript sense)
Definitions on the + strand in genomic 0-based half-open coordinates; on the − strand mirror the intervals and reverse-complement (exactly as `sequence.py` does: donor `[start−6, start+3)`, acceptor `[end−3, end+20)`, PPT `[end+3, end+50)`, then RC).
- 5′ss (donor) window: `[exonEnd − 3, exonEnd + 6)` → 9 nt = 3 exonic + `GT` + 4 intronic (MaxEnt 5′ input).
- 3′ss (acceptor) window: `[exonStart − 20, exonStart + 3)` → 23 nt = 20 intronic (AG at index 18–19) + 3 exonic (MaxEnt 3′ input).
- PPT window: `[exonStart − 50, exonStart − 3)` → 47 nt; branch-point search window `[exonStart − 44, exonStart − 18)` inside it (Leman 2020: > 95 % of BPs between −18 and −44).
- Canonical checks: donor `seq[3:5] == 'GT'` (also report `GC`, and `AT` with acceptor `AC` = U12 AT-AC); acceptor `seq[18:20] == 'AG'`.
- Sites per event type: SE = donor/acceptor of the skipped exon + upstream donor + downstream acceptor; A3SS = shared donor of the flanking exon + proximal and distal acceptors (+ two PPT windows, two BP searches); A5SS = proximal and distal donors + shared acceptor of the flanking exon; RI = donor and acceptor of the retained intron (+ PPT/BP); MXE = donor/acceptor of exon 1 and exon 2 + upstream donor + downstream acceptor.
- MANE boundary correction (reciprocal overlap ≥ 50 % → `overlap`; else the MANE exon inside the flanking interval → `flanking`; closest size if several) applied to the regulated exon(s) before windowing; flanks stay at rMATS coordinates (junction-defined); `maneExonSource` recorded.

### 8.2 Per-event feature record (all types)
`exonSize` (regulated exon; for A3SS/A5SS long and short; RI intron length; MXE both exons), `upstreamIntronSize`, `downstreamIntronSize` (strand-aware), per site: `seq`, `isCanonical`, `dinucleotide`, `maxEnt` score; `pptSeq`, `pptScore` (C+T fraction), `pptT`, `pptC`, `pptLongestRun`; `bp`: {found, score, positionFromAG, motif (yUnAy/CTRAY), bppScore?}; `gcExon`, `gcUpIntron`, `gcDownIntron`; `microexon` (≤ 27 nt); `altSiteDistance` and `isNagNag` (A3SS/A5SS); `mxeIdentity` (MXE); `mane`: {transcript, exonRank(s), frameRegion CDS|partial|UTR5|UTR3|non_coding|unknown, frameClass in_frame|frameshift|non_coding|unknown, cdsExonLength, maneExonSource}; `protein`: {ptc: boolean, ptcDistanceToLastJunction, nmd: 'degraded'|'escape_last_exon'|'escape_start_proximal'|'none'|'unknown', deltaAA, domainsAffected[]}; `u12` flag; `sequenceSource` ucsc|fasta|ensembl.

### 8.3 MaxEntScan port (Yeo & Burge 2004) — required, no JS port exists
- Tables: `me2x5` (16 384 lines), `splice5sequences` (16 384 7-mers), `me2x3acc1..5` (16 384 each), `me2x3acc6/8` (64), `me2x3acc7/9` (256); originals at `http://hollywood.mit.edu/burgelab/maxent/download/fordownload.tar.gz`; a mirror with the tables exists at `github.com/esebesty/maxentscan` (**no licence file; ask the Burge lab before redistributing**; the Ensembl VEP plugin points users to the original download). Total ≈ 1.27 MB text, ≈ 490 KB gz, ≈ 393 KB as Float32.
- Background `bgd = {A:0.27, C:0.23, G:0.23, T:0.27}`; base-4 index `A=0, C=1, G=2, T=3`.
- 5′ss (9-mer `s0..s8`): `cons1 = {A:.004, C:.0032, G:.9896, T:.0032}` at `s3`, `cons2 = {A:.0034, C:.0039, G:.0042, T:.9884}` at `s4`; `consensus = cons1[s3]·cons2[s4] / (bgd[s3]·bgd[s4])`; `rest = s0 s1 s2 s5 s6 s7 s8`; `score5 = log2(consensus × me2x5[index(rest)])`.
- 3′ss (23-mer): `cons1 = {A:.9903, C:.0032, G:.0034, T:.0030}` at `s18`, `cons2 = {A:.0027, C:.0037, G:.9905, T:.0030}` at `s19`; `rest = s[0..18) + s[20..23)` (21-mer `r`); with `h()` the base-4 hash: `sc0=acc1[h(r[0:7])], sc1=acc2[h(r[7:14])], sc2=acc3[h(r[14:21])], sc3=acc4[h(r[4:11])], sc4=acc5[h(r[11:18])], sc5=acc6[h(r[4:7])], sc6=acc7[h(r[7:11])], sc7=acc8[h(r[11:14])], sc8=acc9[h(r[14:18])]`; `score3 = log2(consensus × (sc0·sc1·sc2·sc3·sc4)/(sc5·sc6·sc7·sc8))`.
- Validate against `score5.pl`/`score3.pl` outputs on the mirror's `test/` sequences (fixtures in `test/maxent/`). Report Δ between competing sites (A3SS/A5SS) and vs flanking constitutive sites.

### 8.4 PPT and branch point
- PPT: C+T fraction, T and C content, longest C/T run on the 47-nt window; thresholds shown as labels only (≥ 0.7 strong, ≥ 0.5 moderate — keep the old labels but cite them as heuristics).
- Branch point (must-have): scan −44…−18 for 7-mer `YNYTRAY` (score = matches, A at position 6 mandatory, found if ≥ 5) and 5-mer `CTRAY`; report best position (distance to AG = `exonStart − (pos+5)` for the branch A), distance to the PPT, and whether a BP lies between the two AGs of an A3SS event. Nice-to-have: port BPP (Zhang 2017, mixture-model BPS motif + weighted octanucleotide PPT term) or a PWM trained on the Mercer 2015 high-confidence set.

### 8.5 Frame, PTC and NMD (all types)
- Build both isoforms on the MANE Select CDS: inclusion and skipping (SE), long/short (A3SS/A5SS), retained/spliced (RI), exon-1/exon-2 (MXE). Translate from the MANE start codon; find the first stop; PTC if the stop is not the MANE stop.
- NMD rule: PTC ≥ 50–55 nt upstream of the last exon-exon junction → "degraded by NMD"; escape if in the last exon or < 50 nt from the last junction; flag start-proximal PTC (< 150 nt from AUG) and long 3′UTR (> 1 kb) as caveats (the same four rules as Sashimi-viewer's `spliceModel.ts`). Show the same verdict badges as Sashimi-viewer (⛔ degraded, ✓ normal protein, ✎ altered protein, ✂ truncated).
- `frameClass` as today (`cds_exon_length % 3`), `frameRegion`, plus `deltaAA` and affected domains (UniProt `ft_domain` / Ensembl `overlap/translation` mapped to CDS coordinates).
- When MANE is missing: `unknown` everywhere (no `% 3` heuristic on the exon length alone), as the old README insists.

### 8.6 RBP / hnRNP motif analysis
- Regions (rMAPS2 windows): for every splice site of the event, 250 nt intronic beyond the site (excluding the 6-nt donor / 20-nt acceptor signal zones) and 50 nt exonic inside the site; for SE that gives 4 intronic + 3 exonic regions (upstream exon 3′ end, upstream intron 5′ part, upstream intron 3′ part, skipped exon 5′/3′ ends, downstream intron 5′ part, downstream intron 3′ part, downstream exon 5′ start); A3SS/A5SS/RI/MXE analogues (differential segment as its own region for A3SS/A5SS). Introns shorter than the exclusion zones contribute nothing to that region (report N per region, as today).
- Catalogues: (1) hnRNP consensus list of the old app (19 regex, section 2.4); (2) CisBP-RNA PWMs (CC-BY 4.0) for a curated set of splicing RBPs (hnRNP A1/A2B1/C/F/H1/K/L/M, PTBP1/2, PCBP1/2, SRSF1/2/3/5/6/7/9/10, TRA2A/B, RBFOX1/2, CELF1/2, MBNL1/2, QKI, TIA1/TIAL1, ELAVL1, NOVA1/2, ESRP1/2, SFPQ, U2AF2, KHDRBS1); (3) hexamer sets RESCUE-ESE (238), FAS-ESS (103), ESRseq scores (4096); (4) user-supplied motif list/PWM (MEME or plain).
- Statistics: (a) rMAPS2: 50-nt sliding window, motif score = % nucleotides covered by hits, three groups (ΔΨ > 0 significant, ΔΨ < 0 significant, background = non-significant), Wilcoxon rank-sum per window vs background, plot with significance ticks (p < 0.05 unadjusted as rMAPS2, plus BH per motif available); (b) the old region-level presence z-test with BH (q < 0.05 over motif × region), kept as a secondary table; (c) direction-aware regulatory annotation (ESE/ESS/ISE/ISS) displayed only in the direction-specific panels.

### 8.7 Pattern comparison statistics
Welch t-test (13 tests today, see ORIGINAL_CODE_FIXES.md; Welch-Satterthwaite df, p via regularised incomplete beta with Lentz's continued fraction, max 200 iterations, tol 3e-7), Mann-Whitney U (normal approximation with tie correction, `simple-statistics` or hand-written), two-proportion pooled z-test (`z = (p̂₁−p̂₂)/√[p̂(1−p̂)(1/n₁+1/n₂)]`, `Φ(x) = 0.5·erfc(−x/√2)`), Fisher exact for small counts (< 5 in a cell), BH step-up with cumulative-minimum monotonicity. Report raw p and q, state the number of tests, keep the skewness caveat.

### 8.8 Permutation test
As in section 2.5: labels permuted K times (default 500, 50–2000), `p = (r+1)/(K+1)`, exact enumeration when `C(n, n1) ≤ 5000`, histograms 40 bins on [−1, 1], `pct_p05/p01`, seeded PRNG; metric permutations (PPT score, normalised exon size, in-frame, canonical sites; groups by sign of ΔΨ; requires n ≥ 4).

### 8.9 Enrichment
Hypergeometric test `P(X ≥ k)` with `N` = background size (genes with at least one tested event, or library universe on request), `K` = set size, `n` = significant genes, `k` = overlap; BH per library; combined score `ln(p) × z` only when Enrichr live is used (cite Chen 2013). Libraries bundled as GMT (`geneSetLibrary?mode=text&libraryName=…` at build time; ~0.5–5 MB each). Enrichr live: `POST addList` then `GET enrich?userListId&backgroundType` × 5 libraries with `Promise.all`; Speedrichr with background list when available.

### 8.10 Sequence logos
Frequency mode `height(b,i) = f(b,i) × H` (default, matches the PDF) and bits mode `IC = 2 − H − e_n`, `e_n = 3/(2·ln2·n)` (Schneider & Stephens 1990); N excluded from denominators; canonical columns banded; SVG export at 2×.

---

## 9. Feature list per rMATS event type

Priority: **M** = must-have for v1, **N** = nice-to-have, **X** = explicitly out of scope in-browser. Each line: feature — rationale — reference (section 13 ids).

### 9.1 Common to all types
- M: strand-aware parsing of the five coordinate schemas, JC/JCEC provenance, identity keys — everything depends on it — [rmats].
- M: MANE Select model per gene (bundled), exon ranks, CDS phase — frame/NMD/domains need it — [mane].
- M: sequence windows from UCSC with cache, MaxEnt 5′/3′ scores for every site of the event, Δ vs competing/flanking sites — splice-site strength is the single most informative sequence feature and was absent — [maxent], [shapiro].
- M: PPT metrics and branch-point scan (−18…−44, yUnAy/CTRAY) — [coolidge], [gao2008], [mercer2015], [leman2020].
- M: frame, PTC and NMD verdict by translation of both isoforms — [nagy1998], [lewis2003], [splicetools].
- M: GC content (regulated segment vs flanking introns), intron lengths, exon/intron definition context — [amit2012].
- M: direction of change per group, PSI per replicate, coverage, FDR — [rmats].
- M: significant vs non-significant pattern comparison with logos, tests, BH — [schneider], [benjamini].
- M: RBP maps (rMAPS2 windows, Wilcoxon) + hexamer ESE/ESS density — [rmaps2], [rescue_ese], [fas_ess], [esrseq], [cisbp].
- M: gene annotation (MyGene batch, UniProt, Ensembl domains), PanelApp from a **bundled panel snapshot** (Mendeliome and selected panels, built at build time, no per-gene live calls), STRING with candidate genes — [go], [uniprot], [panelapp], [stringdb].
- M: enrichment (local hypergeometric on bundled libraries; Enrichr optional) — [enrichr].
- M: exports TSV/XLSX/SVG/PNG/PDF with methodology and bibliography; session JSON; Sashimi-viewer deep links.
- N: gnomAD constraint (pLI/LOEUF) per gene — prioritisation — [gnomad].
- N: conservation (phyloP100way mean over the regulated segment and ±10 nt of each site) via UCSC bigWig API — [ucsc_api].
- N: minor (U12) intron flag from bundled MIDB/IAOD list and sequence rule (`/RTATCCTT` 5′ss, `TCCTTRAC` BP, AT-AC or GT-AG) — [midb], [iaod], [turunen2013].
- N: cross-type overlap clustering per gene (same exon in SE and A3SS/MXE), gene-level event map.
- N: ENCODE RBP-knockdown ΔPSI lookup per event from a pre-digested table (build time) — [encode_rbp].
- N: PSI heatmap, PCA, replicate concordance (section 7.7).
- N: "Open in SpliceAI-lookup" per splice site (interactive only) — [spliceai].
- X: SpliceAI/Pangolin batch scoring (model size, licence), IRFinder-style coverage metrics (need BAMs), OMIM (key), runtime NCBI FTP.

### 9.2 SE (skipped exon)
- M: exon length, symmetric (length % 3) flag, microexon flag (≤ 27 nt) — [magen2005], [irimia2014].
- M: MaxEnt of the skipped exon's 5′ss and 3′ss vs the flanking constitutive sites; weak-site flag — [maxent].
- M: PPT/BP of the skipped exon's 3′ss — [coolidge], [gao2008].
- M: frame class + PTC/NMD by removing the exon from the MANE CDS — [nagy1998].
- M: 7-region RBP map (section 8.6) — [rmaps2].
- N: protein domain overlap of the exon (UniProt `ft_domain`, Pfam/InterPro via Ensembl) — [maser], [isoformswitch].
- N: conservation of the exon vs flanks.

### 9.3 A3SS (alternative 3′ splice site)
- M: alternative-site distance (`|longStart − shortStart|` or end-side equivalent), NAGNAG flag (3 nt), frame consequence of the differential segment (Δ % 3), in-frame stop inside the segment — [hiller2004], [bradley2012].
- M: MaxEnt of proximal vs distal acceptor and their difference; canonical AG check at both — [maxent].
- M: two PPT windows (one per AG) with score, length, longest run; BP position relative to each AG and "BP between the two AGs" flag (favours the distal site) — [coolidge], [gao2008], [smith2000].
- M: PTC/NMD of the long vs short isoform — [nagy1998].
- M: RBP/hexamer density in the differential segment ±50 nt and in the shared intron; PTB/U2AF65-related motifs (`TCTT`, `CTCT`, poly-Y) highlighted — [rmaps2], [wagner2001].
- N: U2AF65 binding model on each PPT (PSSM) — [zamore1989], [singh1995].
- N: coding potential / domain hit of the differential segment.
- N: A3SS diagram with both AG sites and dual PPT bars (section 7.5).

### 9.4 A5SS (alternative 5′ splice site)
- M: alternative-site distance, tandem-donor flag (≤ 4 nt), frame consequence of the differential segment, in-frame stop — [hiller2004].
- M: MaxEnt of proximal vs distal donor and their difference; canonical GT/GC check — [maxent], [roca2013].
- M: U1 snRNA complementarity: mismatches to `CAG|GTAAGT` at −3…+6 for each donor — [roca2013].
- M: PTC/NMD of long vs short isoform.
- M: RBP/hexamer density in the differential segment (exonic: SR vs hnRNP A1 balance) and in the first 30 nt downstream of each GT (TIA-1 U-rich `TTTTT`, `TTTCT`) — [forch2000], [mayeda1992], [ge1990].
- N: A5SS diagram with both GT sites.

### 9.5 RI (retained intron)
- M: intron length, GC content of intron vs flanking exons, MaxEnt of the intron's 5′ss and 3′ss (retained introns are shorter, GC-richer, weaker) — [braunschweig2014].
- M: PPT/BP of the intron's 3′ss.
- M: frame of the intron length, first in-frame stop inside the intron, PTC/NMD of the retained isoform; note the "detained/nuclear intron" caveat — [braunschweig2014].
- M: counting-mode advice: prefer JCEC for RI; rMATS tests only annotated introns (`--novelSS` does not add RI) — [rmats_issue65].
- M: U12 flag (RI events are enriched in minor introns).
- N: RI-specific RBP map (intron 5′ and 3′ 250 nt + exonic 50 nt).
- X: coverage-uniformity / IRratio (IRFinder) — needs BAMs; instead link the event to Sashimi-viewer where intron coverage is visible — [irfinder].

### 9.6 MXE (mutually exclusive exons)
- M: mutual-exclusivity sanity (non-overlapping, ordered between flanks), length equality, per-exon frame, "same frame shift" flag (|len1 − len2| % 3 == 0) — [hatje2017], [pillmann2011].
- M: MaxEnt of all four sites; PPT/BP of both acceptors; inclusion convention (1st exon on +, 2nd on −).
- M: PTC/NMD of both isoforms; ΔAA between the two proteins; domains hit by each exon.
- N: sequence identity between exon 1 and exon 2 (Needleman-Wunsch or k-mer Jaccard) as tandem-duplication evidence — [hatje2017].
- N: middle-intron length and inverted-repeat / complementary-sequence scan between the flanking introns (RNA pairing hypothesis) — [graveley2005], [yue2016].
- N: 7-region RBP map (upstream exon, upstream intron, exon 1, middle intron, exon 2, downstream intron, downstream exon).
- N: MXE diagram with the two paths.

---

## 10. Work breakdown (everything that has to be done)

Ordered phases; each task is a checkbox for the implementation session. Estimated size in parentheses (S ≤ 0.5 day, M ≈ 1–2 days, L ≈ 3–5 days of focused agent work).

### Phase 0 — Bootstrap and verification (do first)
- [ ] 0.1 Create the repository, `CLAUDE.md` pointing to this spec, MIT or CC BY-NC licence decision (section 12), README skeleton with attribution to Sashimi-viewer (S).
- [ ] 0.2 Copy the Sashimi-viewer toolchain: `package.json` scripts, `vite.config.ts` (singlefile), `tsconfig*.json`, `tailwind.config.js`, `postcss.config.js`, `.nvmrc`, `.editorconfig`, `scripts/finish.mjs`, `.github/workflows/{build,pages,dev-preview}.yml` (renamed artefact `spliceanalyzer.html`), `index.html` shell with the fallback error box, `src/index.css` verbatim (S).
- [ ] 0.3 **CORS verification** from a normal machine for every API of section 3.2 marked "verify" (STRING, PanelApp UK/AU, Europe PMC, QuickGO, Reactome, HGNC, E-utilities, Enrichr, UCSC); record the observed `Access-Control-Allow-Origin` headers in `docs/api-cors.md`; decide fallbacks for any failure (S).
- [ ] 0.4 Obtain the MaxEntScan tables (original download or mirror) and clarify redistribution with the Burge lab; commit `scripts/build-maxent.mjs` producing the binary asset; keep the Perl scripts as test oracles only (S).
- [ ] 0.5 `scripts/build-mane.mjs` (GFF3 → JSON.gz, `tag=MANE_Select`), `scripts/build-motifs.mjs` (CisBP-RNA subset, hexamer sets), GMT download script; document versions and dates in `docs/data-provenance.md` (M).
- [ ] 0.6 Vitest setup with fixtures generated from the current Python code (section 11) (S).

### Phase 1 — Shell and intake (design parity)
- [ ] 1.1 `main.tsx` page shell: header (logo, title, subtitles, build select, add-files button, chips, gene input), notes row, drop zone, footer, DEV banner support (M).
- [ ] 1.2 SpliceAnalyzer logo derived from the Sashimi mark, favicon data-URI, PNG set, `generate.mjs` (S).
- [ ] 1.3 `parse.worker.ts`: Papa Parse streaming, type detection (regex + header), type-specific column mapping, numeric coercion, coverage rules A/B, identity keys, JC/JCEC merge, dedup, columnar arrays, progress messages (L).
- [ ] 1.4 IndexedDB layer (`idb`): analyses/events/features/deepAnalyses/apiCache/sequenceCache; gzip via `CompressionStream` (M).
- [ ] 1.5 Intake parameters UI + summary line + `summary.txt` display + candidate-gene autocomplete (MyGene) (M).

### Phase 2 — Events view
- [ ] 2.1 Virtualised events table with type-aware columns, filters, single sort, pagination, PSI columns toggle, direction wording per type (L).
- [ ] 2.2 Manhattan plot (natural chr order, event-type colours, candidate markers, tooltip, click) and volcano plot, SVG/PNG export (M).
- [ ] 2.3 Event popover (540 px recipe) with rMATS stats table and links; "Open in Sashimi-viewer" deep link builder (M).
- [ ] 2.4 Per-gene event map on the MANE model (Sashimi transcript panel port) (M).
- [ ] 2.5 Deep links in (`#gene/#locus/#event/#fdr/#dpsi`) and session JSON save/load (M).

### Phase 3 — Annotation engine (workers)
- [ ] 3.1 `mane.ts`: load bundled JSON, lookup by ENSG/symbol, UCSC `mane` track fallback, Ensembl fallback with `Parent`-filtered CDS; MANE boundary correction (M).
- [ ] 3.2 `windows.ts`: per-type site enumeration and window coordinates (+/− strand), locus coalescing (M).
- [ ] 3.3 `ucsc.ts` sequence client with limiter/backoff/cache; `fasta.ts` local accelerator (`@gmod/indexedfasta`, RefSeq aliasing); `ensembl.ts` batch fallback; `revcomp.ts` full IUPAC (M).
- [ ] 3.4 `maxent.ts` port + tests against Perl oracle outputs (M).
- [ ] 3.5 `ppt.ts`, `branchpoint.ts` (yUnAy/CTRAY, −18…−44, A mandatory), GC content, microexon, alt-site distance/NAGNAG, MXE identity (M).
- [ ] 3.6 `frame.ts`, `translate.ts`, `nmd.ts`: isoform construction per type, translation, PTC, 50–55-nt rule, escape rules, ΔAA, domain mapping (L).
- [ ] 3.7 `features.worker.ts` orchestration with progress, "significant first" ordering, cancellation, persistence (M).
- [ ] 3.8 Event diagram component per type with Sashimi conventions, hover strips, zoom/pan, export (L).
- [ ] 3.9 Splice-site track, PPT track, MANE transcript track, logo component (freq/bits) (M).

### Phase 4 — Deep analysis
- [ ] 4.1 Deep analysis creation (thresholds incl. p-value, coverage rule, modules), auto-name, persistence, list (M).
- [ ] 4.2 `stats/*`: Welch, Lentz incomplete beta, erfc, two-proportion z, Mann-Whitney U, Fisher exact, BH, hypergeometric; unit tests vs Python outputs (M).
- [ ] 4.3 Pattern comparison per type (group stats, tests table with q, size histograms, logos sig vs non-sig, MaxEnt distributions, frame/NMD bars, cohort schematic) (L).
- [ ] 4.4 `motifs.worker.ts`: region extraction from cached sequences per type, catalogues (hnRNP regex, CisBP PWM subset, hexamers, user motifs), presence/density scan, 50-nt sliding maps, Wilcoxon per window, BH; RBP map panel (line plots + table + heatmap) (L).
- [ ] 4.5 Permutation panel in worker (exact enumeration when small, histograms, metric permutations) (M).
- [ ] 4.6 Enrichment: local hypergeometric on bundled GMT + optional Enrichr live (addList/enrich, Speedrichr background) (M).
- [ ] 4.7 Gene panels: MyGene batch, UniProt, PanelApp from the bundled snapshot (`scripts/build-panels.mjs`, Mendeliome + selected panels; optional manual refresh), STRING + Europe PMC diagram, gnomAD constraint, links (M).
- [ ] 4.8 Sample-level views: PSI heatmap, PCA (power iteration or SVD in JS), concordance (M).
- [ ] 4.9 Cards view with sorting incl. PanelApp confidence (M).

### Phase 5 — Reports and interoperability
- [ ] 5.1 TSV + XLSX export (SheetJS/exceljs; columns and styling of the old export, per-type columns) (M).
- [ ] 5.2 PDF report with jsPDF + svg2pdf.js: same section structure, dynamic methodology, bibliography [1]–[28] (L).
- [ ] 5.3 Sashimi-viewer session JSON read/write bridge; selection TSV; "Export HTML with embedded results" (M).
- [ ] 5.4 README (usage, privacy note, limits, methods, references, attribution), `docs/methods.md` generated from the same strings as the PDF appendix (M).

### Phase 6 — Nice-to-have (after v1)
- [ ] 6.1 Conservation via UCSC bigWig API; 6.2 U12 list; 6.3 ENCODE RBP-KD table; 6.4 BPP port; 6.5 U2AF65 PSSM (A3SS); 6.6 U1 complementarity refinements and TIA-1 scan (A5SS); 6.7 MXE identity/pairing scans; 6.8 GRCh37 support (hg19 + grch37 Ensembl + MANE lift caveats); 6.9 EN/FR i18n layer; 6.10 `.spliceanalyzer` container with embedded sequences for reviewers (mirrors Sashimi-viewer's `.sashimi` idea).

---

## 11. Verification and parity plan

- **Fixtures from the Python implementation** (generate once with the current backend in Docker before it is retired): for 200 real SE events and 50 of each other type (once the parser fix exists, the Python parser can be run with patched `RAW_COL_MAP` to produce reference windows) dump JSON with: windows sequences, `compute_features` output, `find_branch_point`, `compute_pwm`, `iupac_consensus`, `define_se_regions`, `scan_group`/`compare_groups` results, `_welch_t_test`/`_proportion_z_test`/`_bh_adjust` on canned vectors, `run_permutation` with seed 42 (compare distributions, not values), Excel column headers, PDF section titles and appendix text.
- **MaxEnt**: 1 000 random 9-mers and 23-mers scored with the Perl scripts; JS must match to 1e-4.
- **Parser**: the four vectors of `test_parser_coverage.py`; a synthetic file per type with known duplicates, decimal commas, NA replicates, JC+JCEC pairs; a file named `MYSERIES_SE.MATS.JC.txt` must be detected as SE.
- **Coordinates**: for 20 events per type on both strands, check that the extracted donor windows contain `GT` at index 3–4 and acceptors `AG` at 18–19 for MANE-annotated canonical sites (> 95 % expected).
- **NMD**: compare verdicts with Sashimi-viewer's `spliceModel.ts` on shared cases (same 55-nt rule) and with SpliceTools `SETranslateNMD` on a handful of events.
- **Design parity**: screenshot checklist against Sashimi-viewer (header, chips, drop zone, toolbar, popover, tooltip, dropdown, tabs, pills, arcs, transcript panel, legend); no colour outside section 5 allowed (lint rule: grep for hex values not in the palette file).
- **Performance targets**: parse 120 k rows < 10 s; feature computation for 5 k significant events < 1 min once sequences are cached; RBP scan 20 k events × 7 regions × 40 motifs < 30 s in a worker; UI never blocks > 50 ms.
- **CI**: `tsc`, `vite build`, `vitest`, stale-artefact check, palette lint.

---

## 12. Risks, licences, open questions

1. **UCSC API throughput** for large datasets (≈ 1–2 req/s recommended, ~5 000/day mentioned on the UCSC list): coalescing per gene locus and the persistent cache mitigate; the local FASTA accelerator is the answer for 100 k-event runs; consider `hg38.2bit` over Range requests (**unverified** CORS) or a bundled "sequence pack" exported from a run and shared with colleagues.
2. **CORS unverified** for STRING, PanelApp, Europe PMC, QuickGO, Reactome, HGNC, Enrichr (C-grade evidence only). Each must degrade gracefully (panel shows "not available from the browser, open link ↗").
3. **MaxEntScan tables licence**: no explicit licence in the mirrors; contact the Burge lab or instruct users to drop the `fordownload.tar.gz` file themselves (the app can read it locally, like a FASTA) if redistribution is refused.
4. **Sashimi-viewer is CC BY-NC 4.0**: copying its design and code fragments requires attribution and non-commercial use; choose CC BY-NC 4.0 for the new app too (simplest), and credit Benjamin Cogné in README, footer and `CITATION.cff`.
5. **CisBP-RNA is CC-BY 4.0** (fine); oRNAment is CC BY-NC; ATtRACT/RBPmap/mCross licences unstated → bundle only CisBP-RNA and the published hexamer sets.
6. **Statistical caveats** to keep visible: per-event permutation with 2–3 replicates is uninformative (minimum p ≈ 0.33 / 0.10), pattern tests are exploratory (13 tests, BH reported), background = non-significant events of the same dataset (rMAPS2 practice), presence tests saturate for short motifs.
7. **Scientific choices to confirm with the coworker**: coverage rule default (A or B), dedup defaults, NAGNAG threshold, BP window (−18…−44), which RBP subset, which enrichment libraries and background, whether to keep EN-only UI.
8. **Browser limits**: IndexedDB quota (typically ≥ 1 GB), single-file HTML size (< 10 MB keeps GitHub Pages and e-mail sharing practical), Safari worker/`CompressionStream` support (Safari ≥ 16.4).
9. **Assembly**: GRCh38 only in v1; rMATS runs on GRCh37 need `hg19` + `grch37.rest.ensembl.org` and MANE has no GRCh37 exons (only lift-over) → flag as unsupported until 6.8.

---

## 13. References

Registry ids used above (keep the same ids in `src/lib/references.ts`; PubMed/DOI as in the old app where known).

- [rmats] Shen S et al. rMATS: robust and flexible detection of differential alternative splicing from replicate RNA-Seq data. PNAS 2014;111(51):E5593–E5601. doi:10.1073/pnas.1419161111. rmats-turbo README: https://github.com/Xinglab/rmats-turbo
- [rmats_issue65] rmats-turbo issue #65 (RI limited to annotated introns): https://github.com/Xinglab/rmats-turbo/issues/65
- [rmaps2] Hwang JY et al. rMAPS2: an update of the RNA map analysis and plotting server for alternative splicing regulation. NAR 2020;48(W1):W300–W306. doi:10.1093/nar/gkaa237
- [maxent] Yeo G, Burge CB. Maximum entropy modeling of short sequence motifs with applications to RNA splicing signals. J Comput Biol 2004;11(2-3):377–394. doi:10.1089/1066527041410418. Download: http://hollywood.mit.edu/burgelab/maxent/
- [shapiro] Shapiro MB, Senapathy P. RNA splice junctions of different classes of eukaryotes. NAR 1987;15(17):7155–7174.
- [burge1997] Burge C, Karlin S. Prediction of complete gene structures in human genomic DNA. J Mol Biol 1997;268:78–94.
- [coolidge] Coolidge CJ, Seely RJ, Patton JG. Functional analysis of the polypyrimidine tract in pre-mRNA splicing. NAR 1997;25(4):888–896.
- [padgett] Padgett RA et al. Splicing of messenger RNA precursors. Annu Rev Biochem 1986;55:1119–1150.
- [gao2008] Gao K et al. Human branch point consensus sequence is yUnAy. NAR 2008;36(7):2257–2267.
- [mercer2015] Mercer TR et al. Genome-wide discovery of human splicing branchpoints. Genome Res 2015;25(2):290–303.
- [leman2020] Leman R et al. Assessment of branch point prediction tools to predict physiological branch points and their alteration by variants. BMC Genomics 2020;21:86.
- [bpp] Zhang Q et al. BPP: a sequence-based algorithm for branch point prediction. Bioinformatics 2017;33(20):3166–3172. https://github.com/zhqingit/BPP
- [mane] Morales J et al. A joint NCBI and EMBL-EBI transcript set for clinical genomics and research. Nature 2022;604:310–315. doi:10.1038/s41586-022-04558-8
- [ensembl] Cunningham F et al. Ensembl 2022. NAR 2022;50(D1):D988–D995. REST CORS: https://github.com/Ensembl/ensembl-rest/wiki/CORS-And-JSONP ; rate limits: https://github.com/Ensembl/ensembl-rest/wiki/Rate-Limits
- [ucsc_api] UCSC Genome Browser REST API help: https://genome.ucsc.edu/goldenPath/help/api.html
- [nagy1998] Nagy E, Maquat LE. A rule for termination-codon position within intron-containing genes. Trends Biochem Sci 1998;23(6):198–199.
- [lewis2003] Lewis BP, Green RE, Brenner SE. Evidence for the widespread coupling of alternative splicing and nonsense-mediated mRNA decay in humans. PNAS 2003;100(1):189–192.
- [splicetools] Flemington EK et al. SpliceTools, a suite of downstream RNA splicing analysis tools. NAR 2023;51(7):e42. https://github.com/flemingtonlab/SpliceTools
- [magen2005] Magen A, Ast G. The importance of being divisible by three in alternative splicing. NAR 2005;33(17):5574–5582.
- [irimia2014] Irimia M et al. A highly conserved program of neuronal microexons is misregulated in autistic brains. Cell 2014;159(7):1511–1523.
- [amit2012] Amit M et al. Differential GC content between exons and introns establishes distinct strategies of splice-site recognition. Cell Rep 2012;1(5):543–556.
- [hiller2004] Hiller M et al. Widespread occurrence of alternative splicing at NAGNAG acceptors contributes to proteome plasticity. Nat Genet 2004;36:1255–1257.
- [bradley2012] Bradley RK et al. Alternative splicing of RNA triplets is often regulated and accelerates proteome evolution. PLoS Biol 2012;10(1):e1001229.
- [smith2000] Smith CW, Valcárcel J. Alternative pre-mRNA splicing: the logic of combinatorial control. Trends Biochem Sci 2000;25(8):381–388.
- [zamore1989] Zamore PD, Green MR. Identification, purification, and biochemical characterization of U2 snRNP auxiliary factor. PNAS 1989;86:9243–9247.
- [singh1995] Singh R, Valcárcel J, Green MR. Distinct binding specificities and functions of higher eukaryotic polypyrimidine tract-binding proteins. Science 1995;268:1173–1176.
- [wagner2001] Wagner EJ, Garcia-Blanco MA. Polypyrimidine tract binding protein antagonizes exon definition. Mol Cell Biol 2001;21(10):3281–3288.
- [roca2013] Roca X, Krainer AR, Eperon IC. Pick one, but be quick: 5′ splice sites and the problems of too many choices. Genes Dev 2013;27(2):129–144.
- [mayeda1992] Mayeda A, Krainer AR. Regulation of alternative pre-mRNA splicing by hnRNP A1 and splicing factor SF2. Cell 1992;68:365–375.
- [ge1990] Ge H, Manley JL. A protein factor, ASF, controls cell-specific alternative splicing of SV40 early pre-mRNA in vitro. Cell 1990;62:25–34.
- [forch2000] Förch P et al. The apoptosis-promoting factor TIA-1 is a regulator of alternative pre-mRNA splicing. Mol Cell 2000;6:1089–1098.
- [braunschweig2014] Braunschweig U et al. Widespread intron retention in mammals functionally tunes transcriptomes. Genome Res 2014;24(11):1774–1786.
- [irfinder] Middleton R et al. IRFinder: assessing the impact of intron retention on mammalian gene expression. Genome Biol 2017;18:51.
- [hatje2017] Hatje K et al. The landscape of human mutually exclusive splicing. Mol Syst Biol 2017;13(12):959.
- [pillmann2011] Pillmann H et al. Predicting mutually exclusive spliced exons based on exon length, splice site and reading frame conservation, and exon sequence homology. BMC Bioinformatics 2011;12:270.
- [graveley2005] Graveley BR. Mutually exclusive splicing of the insect Dscam pre-mRNA directed by competing intronic RNA secondary structures. Cell 2005;123(1):65–73.
- [yue2016] Yue Y et al. Long-range RNA pairings contribute to mutually exclusive splicing. RNA 2016;22(1):96–110.
- [turunen2013] Turunen JJ et al. The significant other: splicing by the minor spliceosome. WIREs RNA 2013;4(1):61–76.
- [midb] Olthof AM et al. Minor intron splicing revisited: identification of new minor intron-containing genes and tissue-dependent retention and alternative splicing of minor introns. BMC Genomics 2019;20:686. https://midb.pnb.uconn.edu/
- [iaod] Moyer DC et al. Comprehensive database and evolutionary dynamics of U12-type introns. NAR 2020;48(13):7066–7078. https://github.com/Devlin-Moyer/IAOD
- [cisbp] Ray D et al. A compendium of RNA-binding motifs for decoding gene regulation. Nature 2013;499:172–177; CisBP-RNA 2026 update (CC-BY 4.0): https://cisbp-rna.ccbr.utoronto.ca/
- [rescue_ese] Fairbrother WG et al. Predictive identification of exonic splicing enhancers in human genes. Science 2002;297:1007–1013.
- [fas_ess] Wang Z et al. Systematic identification and analysis of exonic splicing silencers. Cell 2004;119:831–845.
- [esrseq] Ke S et al. Quantitative evaluation of all hexamers as exonic splicing elements. Genome Res 2011;21(8):1360–1374.
- [martinez2006] Martinez-Contreras R et al. Intronic binding sites for hnRNP A/B and hnRNP F/H proteins stimulate pre-mRNA splicing. PLoS Biol 2006;4(2):e21; and hnRNP proteins and splicing control. Adv Exp Med Biol 2007;623:123–147.
- [hnrnp_refs] The 18 hnRNP references [11]–[28] of `HNRNP_REMOVED_REFERENCES.md` (Hwang 2020, Ray 2013, Martinez-Contreras 2007, Chkheidze 1999, Makeyev 2002, Zhu 2001, Damgaard 2002, Kashima 2007, Chen 1999, Erkelenz 2013, König 2010, Zarnack 2013, House 2006, Hui 2005, Huelga 2012, Xue 2009, Wagner 2001, Witten 2011) — reproduce verbatim in the PDF appendix.
- [encode_rbp] Van Nostrand EL et al. A large-scale binding and functional map of human RNA-binding proteins. Nature 2020;583:711–719.
- [spliceai] Jaganathan K et al. Predicting splicing from primary sequence with deep learning. Cell 2019;176:535–548 (models CC BY-NC 4.0); SpliceAI-lookup: https://github.com/broadinstitute/SpliceAI-lookup
- [schneider] Schneider TD, Stephens RM. Sequence logos: a new way to display consensus sequences. NAR 1990;18(20):6097–6100.
- [shannon] Shannon CE. A mathematical theory of communication. Bell Syst Tech J 1948;27:379–423.
- [phipson] Phipson B, Smyth GK. Permutation P-values should never be zero. Stat Appl Genet Mol Biol 2010;9(1):39.
- [benjamini] Benjamini Y, Hochberg Y. Controlling the false discovery rate. J R Stat Soc B 1995;57(1):289–300.
- [welch] Welch BL. The generalization of "Student's" problem when several different population variances are involved. Biometrika 1947;34:28–35. Abramowitz & Stegun 1972 (incomplete beta, Lentz CF). Agresti A. Categorical Data Analysis, 2002 (two-proportion z).
- [enrichr] Chen EY et al. Enrichr. BMC Bioinformatics 2013;14:128; Kuleshov MV et al. NAR 2016;44:W90–W97; Xie Z et al. Curr Protoc 2021;1:e90. API: https://maayanlab.cloud/Enrichr/help#api
- [go] Gene Ontology Consortium. The Gene Ontology resource: enriching a GOld mine. NAR 2021;49(D1):D325–D334.
- [uniprot] UniProt Consortium. NAR 2023;51(D1):D523–D531. REST: https://www.uniprot.org/help/api
- [stringdb] Szklarczyk D et al. The STRING database in 2023. NAR 2023;51(D1):D638–D646. API: https://string-db.org/help/api/
- [panelapp] Martin AR et al. PanelApp crowdsources expert knowledge to establish consensus diagnostic gene panels. Nat Genet 2019;51:1560–1565. API: https://panelapp.genomicsengland.co.uk/api/docs/
- [gnomad] Karczewski KJ et al. The mutational constraint spectrum quantified from variation in 141,456 humans. Nature 2020;581:434–443. GraphQL: https://gnomad.broadinstitute.org/api
- [mygene] Xin J et al. High-performance web services for querying gene and variant annotation. Genome Biol 2016;17:91. https://docs.mygene.info/
- [maser] Veiga DFT. maser: Mapping Alternative Splicing Events to pRoteins. Bioconductor.
- [isoformswitch] Vitting-Seerup K, Sandelin A. IsoformSwitchAnalyzeR. Bioinformatics 2019;35(21):4469–4471.
- [sashimi_viewer] Cogné B. Sashimi-viewer (2026). https://github.com/benjamin-cogne/Sashimi-viewer (CC BY-NC 4.0). Parent project cited in its CITATION.cff: "RNA-Seq Outlier Explorer".
- [gmod] `@gmod/bam`, `@gmod/cram`, `@gmod/indexedfasta`, `generic-filehandle2` (GMOD, MIT).
- JS libraries: Papa Parse 5.7 (MIT), comlink 4.4 (Apache-2.0), idb 8 (ISC), jsPDF 4.2 (MIT), svg2pdf.js 2.8 (MIT), SheetJS CE 0.18.5 (Apache-2.0), exceljs 4.4 (MIT), simple-statistics 7.12 (ISC), jstat 1.9.6 (MIT), logojs-react 2.1 (MIT, optional).

---

## 14. Kickoff prompt for the new Claude Code session

Paste this as the first message in the new repository (after adding `SPEC.md` = this file):

```
You are building SpliceAnalyzer-web: a pure in-browser (no backend) re-implementation of SpliceAnalyzer
(https://github.com/wallideb/SpliceAnalyzer) whose design, design codes and architecture must be identical to
Sashimi-viewer (https://github.com/benjamin-cogne/Sashimi-viewer, read-only, never modify it).
Read SPEC.md entirely before doing anything. Its section 0 lists hard rules that you must follow; section 5 is
the only allowed design system; section 8 gives the exact algorithms and constants; section 10 is your ordered
task list; section 11 is the test plan.

Start with Phase 0: bootstrap the toolchain exactly like Sashimi-viewer (Vite + React 18 + TypeScript strict +
Tailwind 3.4 default theme + vite-plugin-singlefile, GitHub Pages workflow, committed single-file artefact),
then run the CORS verification (task 0.3) and record results in docs/api-cors.md, then build the data assets
(MANE JSON, MaxEntScan binary, motif catalogues, GMT libraries) with build-time scripts.
Then proceed phase by phase; after each task: run tsc, vitest and the palette lint, commit with a clear message.
Never invent a biological constant: if it is not in SPEC.md or a cited source, ask or mark it "unknown".
Genome sequence comes from the UCSC API (getData/sequence) with a persistent IndexedDB cache; a local FASTA is
an optional accelerator; Ensembl REST is the fallback.
All five rMATS event types (SE, A3SS, A5SS, RI, MXE) are first-class everywhere.
Report progress against section 10 checkboxes in PROGRESS.md.
```
