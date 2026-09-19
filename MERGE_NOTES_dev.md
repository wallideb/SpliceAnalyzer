# Merge request: `claude/compassionate-cerf-5o8rar` → `dev`

**Title:** Fix ingestion, sequence, statistics and report defects (ORIGINAL_CODE_FIXES A–E); add in-browser migration spec

**Scope:** 18 commits, 83 files (+8 541 / −3 163). Backend (FastAPI/Python), frontend (Next.js), README, two Alembic migrations (0016, 0017), 119 backend tests (was 12), frontend `tsc` + `next build` clean. Two independent adversarial reviews plus a high-effort automated code review were run and their findings fixed (see `ORIGINAL_CODE_FIXES.md`, "Status after the fix pass").

## Summary of changes

### Ingestion (`services/parser.py`, `utils/composite_key.py`, `models/event.py`, migration 0016)
- A3SS/A5SS files are now imported correctly: `longExonStart_0base, longExonEnd, shortES, shortEE, flankingES, flankingEE` are stored (new columns) and the generic `exon_*`/`upstream_*`/`downstream_*` columns are derived from them (long exon + flanking exon placed by genomic position). MXE `1stExonStart_0base/1stExonEnd` aliases accepted. `IncFormLen`/`SkipFormLen` and the counting mode (`JC`/`JCEC`) are stored.
- Event type detected from the exact `TYPE.MATS.{JC,JCEC}.txt` token (or `fromGTF[.novel*].TYPE.txt`), with header sniffing as fallback; substring matching removed (`PRIMARY_SE…` is no longer RI).
- Deduplication is type-aware: SE keeps the ±50 bp OR rule; RI and MXE require all boundaries within ±50 bp (MXE including the second exon); A3SS/A5SS collapse exact duplicates only (JC/JCEC merge). O(n log n) implementation; collapsed counts logged per type.
- Coverage filter averages over available replicates (NA ignored), tolerates unequal IJC/SJC lengths, counts drops per reason; empty files are skipped with a warning instead of failing the upload.
- Identity constraint extended with the MXE second exon and the A3SS/A5SS coordinates; inserted-row count returned (`RETURNING`).

### Sequence and features (`services/sequence.py`, `splice_features.py`, `mane.py`, `mane_local.py`, migration 0017)
- FASTA batch parser no longer shifts sequences after an empty record; failed or timed-out `samtools` chunks are retried by halving so only invalid regions are blanked; negative starts clamped; full-IUPAC reverse complement; one `splice_window_coords()` function for the three extraction paths.
- Branch point: yUnAy/YNYTRAY scan restricted to 18–44 nt upstream of the 3′SS, branch adenosine mandatory, distance measured from the adenosine to the exon start (was: motif centre to the end of the PPT window, 3 nt short), tie → closest to the 3′SS; new `bp_position`, `bp_motif` fields (persisted).
- PWM frequencies exclude non-ACGT from the denominator; canonical flags are `None` (unknown) for truncated windows instead of `False`.
- MANE: Ensembl fallback filters CDS by transcript `Parent` and uses the union of CDS segments; local GFF3 indexes the `tag=MANE_Select` transcript (MANE Plus Clinical kept separately); `chr` prefix handling fixed.

### Statistics (`services/stats.py` new, `hnrnp_motifs.py`, `permutation.py`, `routers/deep_analyses.py`)
- One shared implementation of the two-proportion z-test (≥ 5 events per group), Mann-Whitney U (tie + continuity correction), Benjamini-Hochberg and the normal CDF (previously duplicated with different conventions).
- hnRNP motif analysis follows the rMAPS2 seven-region design (250 nt after each 5′SS and before each 3′SS, 6/20-nt exclusion zones, exons unchanged): 19 motifs × 7 regions = 133 pairs; each pair gets a presence z-test and a density Mann-Whitney U test, BH per family; regulatory-effect labels mapped onto the new regions.
- Pattern comparison: 20 tests (7 Welch + 7 Mann-Whitney + 6 z), BH `q_value` and `significant_fdr`; unknown canonical flags excluded from denominators; frame percentages over known frames; branch-point rates over events with a PPT window everywhere (API, comparison, PDF).
- Permutation test: exact enumeration of all label splits when C(n, n1) ≤ 5000 (p = r/N, observed split included), Monte-Carlo (r+1)/(K+1) otherwise; `exact_fraction`, `min_p_attainable`, replicate design reported; observed ΔΨ = rMATS `IncLevelDifference`; global null histogram accumulated (no 60 M-float list).
- `pvalue_threshold` is now applied to significance (deep-analysis creation, `/splice/patterns`, `/splice/permutation`); `permutation_iterations` stored.

### Routers, export, services
- Manhattan data in natural chromosome order; `GET /deep-analyses/{id}/events` paginated; compute status persisted in `analyses.compute_status/compute_error` with an atomic claim and a 30-min heartbeat (safe with several workers; stale runs reset at startup); 503 path without private attributes; MANE negative results retried at most every 24 h.
- PDF: acceptor logos use the last 23 nt (as the API), frame denominators exclude unknown, test counts derived from the data, permutation table at 50/100/250/500 (single row when everything is enumerated exactly), hnRNP tables/heatmap for 7 regions with both q-values, Enrichr top 10, methodology and statistics appendices rewritten accordingly, SVG side files only when `SVG_EXPORT_DIR` is set.
- Enrichr overlap `k/n` from library GMT sizes (no more GO ids in the overlap column); STRING returns no interaction when the pair does not match; PanelApp 6 h cache; in-process FASTA download at startup removed (use `data/setup_grch38_fasta.sh`); `numpy` pinned; dead code removed (`extract_region`, `motif_density`, `EVENT_TYPE_KEYWORDS`, `SPLICE_WINDOW`, `AnalysisCreate`, `VerticalBarChart`).

### Frontend
- File chips show the counting mode; upload warnings displayed; deep-analysis events fetched by pages; 503 detected by status; polling stops on error/done; single server-side sort (header clicks drive it, |ΔΨ| and ΔΨ headers map to `abs_inc_level_diff`); Interactions tab enabled in deep analyses; PanelApp sort implemented; one nucleotide palette (`lib/colors.ts`); branch-point marker placed on the adenosine with the correct exon-anchored positions; cohort schematic no longer fabricates an FDR; hnRNP panel with 7 regions and both q-values; permutation panel shows exact/Monte-Carlo information and the metric permutations; pattern comparison shows q-values and Mann-Whitney rows; dead components/keys/deps removed; `lang="fr"`.

### Documentation
- README fully realigned (methodology §1–§13, configuration, API reference, feature reference, references, troubleshooting); `ORIGINAL_CODE_FIXES.md` (defect list with status), `SPLICEANALYZER_IN_BROWSER_SPEC.md` (in-browser re-implementation brief), `check_cors.sh`; CRLF fixed in `setup_mane_gff3.sh` (the script did not run under bash).

## Deployment checklist
1. `alembic upgrade head` (0016 adds 9 columns and recreates `uq_splicing_event_identity`; 0017 adds `compute_status`, `compute_error`, `bp_position`, `bp_motif`). The new constraint is a superset of the old columns, so no existing row can violate it.
2. **Recompute splice features** for existing analyses (`POST /api/v1/splice/compute/{analysis_id}`) or truncate `event_splice_feature`: stored branch-point values use the old semantics and are not invalidated automatically.
3. **Re-import** analyses containing A3SS/A5SS files (their events were dropped or stored without coordinates before this change).
4. The backend no longer downloads the GRCh38 FASTA: run `data/setup_grch38_fasta.sh` (or provide `/data/GRCh38.fa` + `.fai`) before starting; check `GET /api/v1/debug/fasta`.
5. `pip install -r requirements.txt` (numpy pinned). Optional `SVG_EXPORT_DIR` if the PDF side-SVGs are wanted.
6. Saved deep analyses keep their event partition; their panels (pattern comparison, hnRNP, permutation) are recomputed on view and **will show different numbers** (see risks below).

## Verification performed
- Backend: `python -m pytest tests -q` → 119 passed (parser, event types, sequence/features/MANE, hnRNP, permutation, stats, PDF smoke build); `python -c "import app.main"`; `compileall`.
- Frontend: `npx tsc --noEmit`; `npx next build` (6 routes); i18n key parity script (460 keys, identical trees).
- Migrations: linear chain 0001 → 0017; model/migration column parity checked by review.
- Not verified here (needs a running stack): end-to-end upload → compute → export on real rMATS output; Ensembl/Enrichr/STRING/PanelApp live calls; PostgreSQL execution of the `RETURNING` insert and the `CASE` ordering (compiled against the PostgreSQL dialect only).

## Risk assessment: which results change, and by how much

| Area | What changes | Expected magnitude | Direction |
|---|---|---|---|
| Event counts (A3SS/A5SS) | Events were dropped or coordinate-less; now imported and never merged by proximity | **Large**: from ~0 to the full rMATS count for these two types | more events |
| Event counts (RI, MXE) | AND rule instead of OR; MXE second exon considered | Small to moderate: fewer collapses | more events |
| Event counts (all types) | Coverage filter tolerates NA replicates; empty files skipped | Small: rows with one NA replicate are kept | more events |
| Event type assignment | Token-based detection | Only files whose names contained `RI`/`SE` as substrings were misfiled before | corrected |
| Branch point (`bp_motif_found`, `bp_distance`) | Window −18…−44 instead of −50…−3 (after +3 offset), adenosine mandatory, distance from the A to the exon start | **Large**: the old scan accepted score ≥ 5/7 anywhere in 47 nt with N free, so most PPTs "found" a BP; the detection rate will drop markedly and distances shift by +1 to +2 nt | fewer BP calls, larger distances |
| Canonical GT/AG percentages | `None` for truncated windows, excluded from denominators | Small (contig-edge events only) | slightly higher % |
| PWM / logos | N excluded from the denominator | Negligible unless the FASTA contains N runs | frequencies sum to 1 |
| MANE frame class | `tag=MANE_Select` used (file order before); REST fallback CDS filtered by transcript and CDS union | Small: genes whose Plus Clinical transcript was listed first, and events annotated through the REST path | some `partial`/`UTR` ↔ `in_frame`/`frameshift` flips |
| Significance partition | `pvalue_threshold` now applied | Only for deep analyses created with a p-value maximum: fewer significant events | fewer |
| Pattern comparison | 20 tests instead of 13, z-test unrounded before BH, ≥ 5 per group, MWU rows, `q_value` added; in-frame % over known frames; BP rate over PPT-eligible events | p-values of existing Welch/z tests essentially unchanged (rounding only); q-values are new; small groups (< 5) now report no z-test; frame % higher when many `unknown` | mostly presentation, some denominators |
| hnRNP enrichment | 133 pairs instead of 95 (larger BH family), two new 3′SS-proximal regions, density Mann-Whitney test, significance = either test | **Moderate to large**: q-values of the original 95 pairs rise (larger family); PTB/hnRNP C/U2AF-type motifs now tested where they act (3′SS side); density test has power where the presence test saturated (`AGG`, `GGG`, `TTTT`, `CTCT`) | more significant pairs overall, some previous ones lose significance |
| Permutation test | Exact enumeration for ≤ 5000 splits (typical rMATS designs), observed ΔΨ from rMATS | For 2v2/3v3 designs p-values move from Monte-Carlo estimates (K=500) to exact k/6 or k/20; the smallest attainable p for 3v3 is 0.05, which is not < 0.05, so `pct_p05` **drops to 0** for 3v3 designs where the old Monte-Carlo estimate sometimes fell just below 0.05 (the UI and PDF now state the minimum attainable p) | fewer "significant" events in small designs, honest reporting |
| Enrichr | Overlap shown as `k/n`; PDF top 10 | Presentation only | — |
| PDF / Excel | Text and denominators corrected; `?` for unknown flags; four (or one) permutation rows | Presentation; frame-breakdown bars now fill to 100 % of known frames | — |

**Bottom line:** results change most for (1) A3SS/A5SS events (now present), (2) branch-point calls (far fewer, now biologically constrained), (3) hnRNP q-values (larger family, new regions, new test), and (4) small-design permutation p-values (exact). Splice-site sequences, PPT scores, exon/intron sizes, ΔΨ, FDR and the significant/non-significant partition (without a p-value threshold) are unchanged for SE, and all previous behaviours are documented in the README diff. Any manuscript figure produced with the previous version should be regenerated and the methods text updated from the new PDF appendix.

## Not included (deferred, documented)
Synchronous upload parsing (C6), ingestion drop counts in the upload response (A15), STRING batching (C13), ΔΨ-sign split and 50-nt sliding maps for the RBP analysis (E2), MaxEntScan splice-site strength (E4), PTC/NMD by translation (E5), replicate names in reports (E12).
