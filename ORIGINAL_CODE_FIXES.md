# SpliceAnalyzer (original code) — exact list of defects and fixes

Scope: the current repository (`rmats-viz/backend`, `rmats-viz/frontend`), branch `dev` at commit `6d7d7a6`. Every entry gives the file and line (verified with `grep -n`), the offending code, the defect, and the exact correction. Paths are relative to `rmats-viz/backend/app/` (backend) and `rmats-viz/frontend/src/` (frontend). Nothing has been modified; this is the list to apply (or to carry into the in-browser port, see `SPLICEANALYZER_IN_BROWSER_SPEC.md`).

Severity: **A** = wrong or lost results (fix first) · **B** = documented behaviour differs from code (fix text or code) · **C** = robustness / performance · **D** = dead code and cleanup · **E** = scientific method improvement (not a bug, but should change).

---

## A. Wrong or lost results

### A1. A3SS and A5SS events lose their coordinates at import — `utils/composite_key.py:11-43`
```python
RAW_COL_MAP: dict[str, str] = {
    ...
    "exonStart_0base": "exon_start", "exonEnd": "exon_end",
    "2ndExonStart_0base": "second_exon_start", "2ndExonEnd": "second_exon_end",
    "riExonStart_0base": "exon_start", "riExonEnd": "exon_end",
}
REQUIRED_COLS = {"exon_start", "exon_end", "upstream_es", "upstream_ee", "downstream_es", "downstream_ee"}   # line 46
```
Defect: rMATS A3SS/A5SS files use `longExonStart_0base, longExonEnd, shortES, shortEE, flankingES, flankingEE`; none is mapped, so `exon_start … downstream_ee` are all null and `parse_rmats_file` (`services/parser.py`, `dropna(how="all")` on `REQUIRED_COLS`) drops every A3SS/A5SS row, or keeps them without coordinates. MXE files from recent rMATS versions use `1stExonStart_0base/1stExonEnd` (also unmapped).
Fix: add the six A3SS/A5SS columns and the two MXE aliases to the model (`models/event.py`: `long_exon_start, long_exon_end, short_es, short_ee, flanking_es, flanking_ee` BIGINT) + an Alembic migration, and map them:
```python
"longExonStart_0base": "long_exon_start", "longExonEnd": "long_exon_end",
"shortES": "short_es", "shortEE": "short_ee", "flankingES": "flanking_es", "flankingEE": "flanking_ee",
"1stExonStart_0base": "exon_start", "1stExonEnd": "exon_end",
```
Make `REQUIRED_COLS` type-dependent (A3SS/A5SS: the six long/short/flanking columns; RI: `exon_start, exon_end, upstream_*, downstream_*`; MXE: generic + `second_exon_*`). Keep `IncFormLen`/`SkipFormLen` (currently dropped) — they are needed to interpret JCEC counts.

### A2. Event type detected by substring of the filename — `services/parser.py:37-39` and `components/upload/FileUploadZone.tsx:8-9`
```python
for et in ["MXE", "A3SS", "A5SS", "RI", "SE"]:
    if et in upper:
        return et
```
Defect: any filename containing `RI` (e.g. `PRIMARY_SE.MATS.JC.txt`, `MYSERIES_SE.MATS.JC.txt`) is classified RI before SE is tested; `SE` also matches `SERIES`, `BASELINE` etc.
Fix (both files):
```python
m = re.search(r"(?:^|[._\-/ ])(SE|MXE|A3SS|A5SS|RI)\.MATS\.(JC|JCEC)\.txt$", name, re.I)
if m: return m.group(1).upper()            # also return m.group(2) as counting mode
# fallback: sniff the header: riExonStart_0base→RI, longExonStart_0base→A3SS/A5SS, 1stExonStart_0base→MXE, exonStart_0base→SE
```
For `fromGTF.*` files, detect the same token before `.txt`.

### A3. Deduplication collapses genuine alternative-site events — `services/parser.py:201-224`
```python
group_cols = [c for c in ["event_type", "gene_id", "chr", "strand"] if c in df.columns]
...
start_near = (start is not None and ks is not None and abs(start - ks) <= overlap_bp)
end_near   = (end   is not None and ke is not None and abs(end   - ke) <= overlap_bp)
if start_near or end_near:
```
Defect: for A3SS/A5SS the two alternative sites differ by construction at one boundary, often by < 50 nt (NAGNAG = 3 nt), and for RI/MXE `exon_start/exon_end` have different meanings; the OR rule merges distinct events and is greedy/non-transitive.
Fix: apply the ±50 bp OR rule to SE only (and, if wanted, to RI/MXE on their defining exon with AND instead of OR); for A3SS/A5SS/MXE deduplicate on the full identity tuple (exact duplicates, i.e. JC vs JCEC of the same event) only; expose `overlap_bp` as an upload parameter; record the number of collapsed rows per file.

### A4. FASTA batch parser shifts sequences after an empty record — `services/sequence.py:185-196`
```python
if line.startswith(">"):
    if current:
        seqs.append("".join(current).upper())
    ...
if current:
    seqs.append("".join(current).upper())
...
for idx, seq in zip(chunk_idx, seqs):
```
Defect: `samtools faidx` emits a header with an empty sequence for a region beyond the contig end (or when `start+1 <= 0`); the `if current:` guard skips it, so every following sequence in the chunk is assigned to the wrong region (donor windows become acceptor windows, etc.).
Fix: append on every header (`seqs.append("".join(current).upper())` unconditionally after the first header, using a `seen_header` flag), then assert `len(seqs) == len(chunk_idx)` and blank the chunk if not; clamp `start` to `max(start, 0)` before building `f"{resolved}:{start + 1}-{end}"` (line 161).

### A5. Whole 5000-region chunk blanked on a single failure — `services/sequence.py:197-208`
Defect: `CalledProcessError` on one invalid region leaves 5000 regions as `""`.
Fix: on `CalledProcessError`, retry the chunk region by region (or in halves) so only invalid regions are blanked; log the invalid regions.

### A6. Ensembl CDS not filtered by transcript — `services/mane.py:190-193`
```python
cds = _ensembl_get(f"/overlap/id/{transcript_id}?feature=cds&content-type=application/json")
exons["CDS"] = cds if isinstance(cds, list) else []
```
Defect: `overlap/id/{tx}?feature=cds` returns CDS features of every transcript overlapping the span; `_frame_class` (lines 240-243) then takes `min(start)`/`max(end)` across isoforms, mis-classifying UTR/partial exons in the REST fallback path.
Fix: `cds = [c for c in cds if c.get("Parent") == transcript_id]`. Also compute the CDS overlap against the union of CDS segments rather than the span.

### A7. MANE Select chosen by file order — `services/mane_local.py:170-172`
```python
# first transcript per gene is usually MANE Select
if gene_id not in _gene_index:
    _gene_index[gene_id] = data
```
Defect: the GFF3 contains MANE Plus Clinical transcripts too (74 in v1.5); whichever comes first wins.
Fix: parse the `tag=` attribute of the `mRNA`/`transcript` line and index only `MANE_Select` (keep Plus Clinical in a separate map for display).

### A8. `pvalue_threshold` stored but never applied — `routers/deep_analyses.py:91-96` (and `routers/splice.py:1044-1049`)
```python
fdr_ok  = fdr is not None and fdr <= body.fdr_threshold
dpsi_ok = (inc_level_diff is not None and abs(inc_level_diff) >= body.delta_psi_min)
is_sig  = fdr_ok and dpsi_ok
```
Defect: the UI lets the user set a p-value maximum, the value is saved and printed in the auto-name, but significance ignores it; `run_permutation_test` has no such parameter either.
Fix: `pv_ok = body.pvalue_threshold is None or (ev.p_value is not None and ev.p_value <= body.pvalue_threshold)`; `is_sig = fdr_ok and dpsi_ok and pv_ok`; add the parameter to `run_permutation_test` and to `lib/api/splice.ts:51-59`; or remove the field from the UI.

### A9. Manhattan plot orders chromosomes as strings — `routers/events.py:111,120,134,147,153-156`
```python
.order_by(SplicingEvent.chr, SplicingEvent.exon_start)
...
key=lambda r: (r.chr or "", r.exon_start or 0)
```
Defect: chr1, chr10, chr11 … chr19, chr2, chr20 …; the frontend (`ManhattanPlot.tsx`) lays out chromosomes in its own order so the sampling budget per chromosome is skewed but the plot is correct; `Top10View` chr sort is fine.
Fix: sort with a natural key (`{chr1:1 … chr22:22, chrX:23, chrY:24, chrM:25}`) in Python, and in SQL order by a `CASE` expression or a computed column.

### A10. Enrichr gene-set size parsed from the term name — `services/enrichr.py:97-100`
```python
term_str = str(row[1])
if "(" in term_str and term_str.endswith(")"):
    geneset_size = term_str.rsplit("(", 1)[-1].rstrip(")")
    overlap_str = f"{len(overlap_genes)}/{geneset_size}"
```
Defect: for GO libraries the trailing parenthesis is the GO id (`mRNA Splicing (GO:0000398)` → `5/GO:0000398`); for KEGG there is no parenthesis; the `/enrich` endpoint does not return set sizes.
Fix: fetch set sizes once per library from `GET /Enrichr/geneSetLibrary?mode=text&libraryName={lib}` (GMT) and cache them, or use `/Enrichr/export` which includes the overlap `k/n`; show only `len(overlap_genes)` when the size is unknown.

### A11. STRING falls back to an unrelated pair — `services/stringdb.py:85-86`
```python
# If exact match not found, return the first result
return data[0] if data else None
```
Fix: return `None` when neither `(preferredName_A, preferredName_B)` nor the swapped pair matches the query (case-insensitive); the caller already handles `None` as "no interaction".

### A12. Branch-point distance and scoring — `services/splice_features.py:104,124-135,276-277`
```python
_BP_MIN_DISTANCE = 15
for i in range(n - 6):
    motif = upper[i : i + 7]
    distance = n - (i + 3)          # centre of the 7-mer to the END of ppt_seq
    if distance < _BP_MIN_DISTANCE: continue
    score = sum(fn(b) for fn, b in zip(_BP_CHECKS, motif))
...
res.bp_motif_found = bp_s >= 5
```
Defects: (a) `ppt_seq` ends 3 nt before the exon (`[exon_start-50, exon_start-3)`), so the reported `bp_distance` is 3 nt short of the true distance to the AG, and it is measured from the motif centre (position 4 of 7) instead of the branch adenosine (position 6); (b) a match with score ≥ 5 does not require the adenosine to be present (N counts as a match), so `YNYTRAY` with a non-A at position 6 can be "found"; (c) the window is −50…−3 whereas > 95 % of human BPs lie at −18…−44 (Leman 2020).
Fix: `distance_to_ag = (n + 3) - (i + 5)` (branch A index 5, 0-based); require `motif[5] == "A"` for `bp_motif_found`; restrict candidates to `18 <= distance_to_ag <= 44`; keep the 0–7 score for display; document the yUnAy consensus (Gao 2008). Update the README ("distance from the motif centre") accordingly.

### A13. PDF acceptor logos take the wrong 23-mer when a window is longer than 23 nt — `routers/export.py:945-947` vs `routers/splice.py:855` / `routers/deep_analyses.py:634`
```python
expected_len = 9 if site == "donor" else 23
sequences.append(seq[:expected_len].upper())      # export: first 23
acc_23.append(feat.acceptor_seq[-23:])            # routers: last 23
```
Fix: use `seq[-23:]` for acceptors and `seq[:9]` for donors in `export.py` (only matters when sequences deviate from 23 nt, but the two paths must agree).

### A14. Frame-breakdown percentages use a denominator that includes `unknown` — `routers/export.py:1593,1665,800,804` (and 2028/2032)
```python
n_f = len(subset_features)
frame_fig = _fig_frame_breakdown(n_if, n_fs, n_nc, n_f)
seg_w = (count / n_feat) * bar_w ; pct = count / n_feat * 100
```
Fix: pass `n_if + n_fs + n_nc` (events with a known frame) as the denominator and print "n unknown" beside the bar; do the same in the frontend `MotifPatternPanel` frame bars if they use `n_se_with_features`.

### A15. Coverage filter drops rows with unequal or missing replicate lists silently — `services/parser.py:76-77,82-89,103`
```python
if not needed.issubset(df.columns): return df          # no filtering when any count column is missing
if len(ijc_vals) != len(sjc_vals) or not ijc_vals: return float("nan")
mask = (mean_cov_1 >= min_coverage) & (mean_cov_2 >= min_coverage)
```
Defect: after `pd.concat` of a `fromGTF.*` file (no count columns) with a `*.MATS.JC.txt` file, the columns exist with NaN for the GTF rows, which are then dropped without any message; rows with a single `NA` replicate are dropped too.
Fix: count and report dropped rows per reason (`missing_counts`, `low_coverage`, `unequal_replicates`); compute the mean over available replicates (ignore `NA`) instead of dropping; skip the filter for annotation-only files explicitly.

### A16. Upload returns the number of attempted, not inserted, rows — `services/parser.py:311-319`
```python
insert(SplicingEvent).values(batch).on_conflict_do_nothing(constraint="uq_splicing_event_identity")
...
return len(records)
```
Fix: use `.returning(SplicingEvent.id)` and sum the returned rows, or count after commit with `SELECT count(*) WHERE analysis_id = …`.

---

## B. Text that does not match the code (fix the text, or the code, and the README)

| # | Location | Text | Code | Fix |
|---|---|---|---|---|
| B1 | `routers/export.py:2547` | "No multiple-testing correction is applied within the comparison (9 tests)" | `_compute_stat_tests` runs **13** tests (`routers/deep_analyses.py:494-612`: mean_delta_psi, exon_size, ppt_score, ppt_t_content, ppt_c_content, canonical_gt, canonical_ag, in_frame_pct, bp_found, upstream_canonical_gt, downstream_canonical_ag, upstream_intron_size, downstream_intron_size) | Compute the count from the list (`len(tests)`) in the PDF and README (README §12 lists ~9 metrics). |
| B2 | `routers/export.py:2560,2851` | "counts (50, 100, 250, 500) to assess convergence" / "run at 50, 100, 250 and 500 iterations" | `export.py:3136-3146`: single run, `n_iterations=500` | Either run the four sizes in the export (cheap) or change the text to "500 iterations (Phipson & Smyth correction)". README §8 says "50, 100, 250, or 500" and the UI slider is 50–2000 step 50. |
| B3 | `routers/export.py:2872` | "groups with fewer than 5 events are skipped" | no such guard (`_proportion_z_test` at `deep_analyses.py:443`, `hnrnp_motifs.py:586-587` only checks `n < 1`) | Add `if n1 < 5 or n2 < 5: return None, None` in both z-tests (recommended), or delete the sentence. |
| B4 | `routers/export.py:2645` vs `2248,2279` | "The top 10 terms per library by adjusted p-value are…" | `[:5]` and caption "Top 5 terms per library shown" | Make both 10 or both 5. |
| B5 | `services/hnrnp_motifs.py:19` (docstring) and README §10 | "Downstream intron: 250 nt from the 3'SS, excluding the last 20 nt" | lines 331-341: the region starts at the skipped exon's 5'SS (`exon_end + 6`) and is bounded by `downstream_es - 20` | Either fix the docstring/README (current behaviour = 5'SS-proximal 250 nt of each intron) or implement rMAPS2's design (both intron ends), see E1. |
| B6 | `services/uniprot.py:12` vs `:41` | docstring `query=gene:{symbol}` | code `gene_exact:` | Fix the docstring. |
| B7 | README "Technology stack" | "Lucide icons" | `lucide-react` never imported (all icons inline SVG) | Fix README or use the library. |
| B8 | README §7 / UI | `bp_distance` "distance from the motif centre to the 3'SS" | see A12 | Update after A12. |
| B9 | `schemas/analysis.py:30-33` | `AnalysisCreate` defaults `"Subjects PCBP1"` / `"Contrôles"` | unused class; router uses Form fields with "Subjects"/"Controls" | Delete the class (D). |

---

## C. Robustness and performance

| # | Location | Code | Defect | Fix |
|---|---|---|---|---|
| C1 | `services/permutation.py:261,293-294` | `all_null_values: list[float] = []` … `all_null_values.extend(null_deltas)` | n_events × n_iterations floats kept in memory (120 k × 500 = 60 M) | Accumulate the 40-bin histogram counts per event (`np.histogram` with fixed edges) and sum them. |
| C2 | `services/permutation.py:271-277` | `observed_delta = (_mean(psi1) or 0.0) - (_mean(psi2) or 0.0)` | ΔΨ recomputed from the PSI strings (differs from `IncLevelDifference` when NA replicates exist); `or 0.0` turns a true mean of 0.0 into… 0.0 (harmless) but hides `None` | Use `ev.inc_level_difference` for display and the recomputed value only inside the test; skip events where either mean is `None`. |
| C3 | `services/permutation.py:286-291` | vectorised permutations for every group size | with 2–3 replicates per group there are only 6 / 20 distinct label splits; 500 iterations overstate resolution, minimum p ≈ 0.33 / 0.10 | Enumerate all `C(n1+n2, n1)` splits exactly when ≤ 5000, report the minimum attainable p, and warn in the UI/PDF. |
| C4 | `routers/splice.py:70` | `_active_computes: dict[uuid.UUID, bool] = {}` | in-process state: wrong with > 1 uvicorn worker; `progress.done` becomes true if the background task crashes | Store status in `analyses` (new column `compute_status`) or Redis; mark `error` in `finally`. |
| C5 | `routers/deep_analyses.py:202-226` | `list_deep_analysis_events` returns all rows | unbounded response (100 k+ rows) rendered as cards by `Top10View` | Add `page/page_size` (as `list_events`) and virtualise the card list. |
| C6 | `routers/analyses.py:101,132-133` | `event_count = await parse_and_store(...)` inside the request | large uploads block the request (10-min client timeout in `analyses.ts`) | Move parsing to `BackgroundTasks` with `status="processing"` polling (the status field already exists). |
| C7 | `main.py:29,48-51,96` | `_setup_fasta` downloads 800 MB in the default executor at startup | failure only logged; blocks a thread for up to 30 min | Move to the setup script / compose init container; keep only a readiness check. |
| C8 | `routers/export.py:3178` | `svg_dir = os.path.join("/data", "svg_exports", str(deep_analysis_id))` | hardcoded path, unbounded disk growth on every export | Make it a setting (`SVG_EXPORT_DIR`, default off) or return the SVGs in a zip on demand. |
| C9 | `routers/splice.py:663-676` | re-tries `annotate_mane` (network) on every `GET /splice/feature/{id}` when MANE is missing | latency on each card load for genes absent from the GFF3 | Cache negative results with a TTL (`mane_cache` row with `frame_class='unknown'` + timestamp). |
| C10 | `routers/splice.py:631-632` | `if not _ENDPOINT_SEM._value: raise HTTPException(503)` | private attribute; frontend matches `"503"` in the error string (`SpliceView.tsx:90-92`) | Use `asyncio.wait_for(sem.acquire(), timeout)`; frontend: read `error.status` (already set for 409 in `analyses.ts`). |
| C11 | `lib/api/analyses.ts:55` | ``return `http://localhost:8000/api/v1/analyses/${id}`;`` | bypasses the Next.js proxy; breaks on any other port | Use `${BASE}/analyses/${id}` like every other call (the 10-min timeout is handled by `next.config.mjs proxyTimeout`). |
| C12 | `components/top10/MotifPatternPanel.tsx:283,297-305` | `refetchInterval: isPolling ? 4_000 : false` stopped only when `data` arrives | polls forever if compute fails | Stop polling on error or when `getComputeProgress().done` is true. |
| C13 | `services/panelapp.py` / `routers/export.py` Excel | one PanelApp call per gene (up to 10 pages + icontains fallback) and one STRING call per (gene × candidate) | thousands of HTTP calls per export | Batch: PanelApp `genes/?entity_name__in=` is not available, so cache per gene in SQLite (like MANE) with a TTL; STRING `network?identifiers=` accepts many identifiers in one call. |
| C14 | `services/parser.py:201-224` | O(n²) Python loop per dedup group | slow at 120 k events | Sort by start and use a sliding window (`bisect`) per group. |

---

## D. Dead code and cleanup

| # | Location | Item |
|---|---|---|
| D1 | `services/sequence.py:212-251` | `extract_region` (only mentioned in a docstring at line 145) |
| D2 | `services/hnrnp_motifs.py:371,391` | `count_motif_occurrences`, `motif_density` (no callers) |
| D3 | `services/parser.py` | `EVENT_TYPE_KEYWORDS` constant |
| D4 | `config.py:22` | `SPLICE_WINDOW: int = 50` (windows are hard-coded in `sequence.py`) |
| D5 | `routers/export.py:414` | `from reportlab.graphics.charts.barcharts import VerticalBarChart` |
| D6 | `schemas/analysis.py:30` | `AnalysisCreate` (no importer) |
| D7 | `requirements.txt` | add `numpy` (imported by `services/permutation.py`); document `samtools` (only in the Dockerfile) |
| D8 | `services/splice_features.py` | `ppt_t_content`, `ppt_c_content` computed but not persisted (recomputed from `ppt_seq` in three places): persist them or drop them from the dataclass |
| D9 | `models/deep_analysis.py` | `permutation_iterations` never written; `modules` never read server-side (`routers/deep_analyses.py:110`) |
| D10 | `components/top10/SpliceSequenceLogo.tsx` | never imported |
| D11 | `types/splice.ts:137` | `metric_results` never displayed by `PermutationPanel.tsx` (either render it or drop it from the API) |
| D12 | `lib/references.ts:72,159,173,189,247` | `maxent`, `gene_ontology`, `stringdb`, `panelapp`, `cisbp_rna` never passed to `<ScienceNote refs>`; cite them in AnnotatedCard (GO/PanelApp/STRING tabs) and HnRNPMotifPanel, or remove |
| D13 | `lib/i18n/en.ts:212-229, 230-266, 406-429` (+ `fr.ts:213,231`) | dead sections `basket`, `analysisOptions`, `permutation.tabs` |
| D14 | `package.json:17,20` | `class-variance-authority`, `lucide-react` unused |
| D15 | `components/top10/AnnotatedCard.tsx` | `ComingSoonView` / `pathways` mode unreachable |
| D16 | `app/api/v1/analyses/[id]/route.ts` | redundant with the `next.config.mjs` rewrite |
| D17 | `services/sequence.py:268-570` | three copies of the window definitions (`get_splice_windows`, `get_splice_windows_batch`, `get_splice_windows_from_ensembl`): factor one `window_coords(...)` function |
| D18 | `routers/deep_analyses.py` / `services/hnrnp_motifs.py` | `_proportion_z_test` + `_normal_cdf` duplicated with different guards/rounding; `_build_regions` duplicated in `deep_analyses.get_hnrnp_motifs` and `export._compute_hnrnp`; PWM computed inline in `export.py` instead of `compute_pwm` |
| D19 | `services/mane.py:170` | `chrom.lstrip("chr")` strips characters, not the prefix (works by luck: no chromosome starts with c/h/r after removal): use `removeprefix("chr")` and map `M→MT` |
| D20 | `services/sequence.py:59` | `_COMP = str.maketrans("ACGTacgtNn", "TGCAtgcaNn")`: extend to IUPAC (`RYSWKMBDHV` ↔ `YRSWMKVHDB`) |
| D21 | `services/splice_features.py:295-297` | `compute_pwm` divides by the column size including non-ACGT characters (frequencies do not sum to 1): count only A/C/G/T in `total` |
| D22 | `services/splice_features.py:258,264` | `acceptor_is_ag` returns `False` (not `None`) for windows shorter than 23 nt near contig ends: return `None` when `len(a) < 20` |

---

## E. Scientific method changes (recommended, not strictly bugs)

| # | Location | Current behaviour | Recommended change |
|---|---|---|---|
| E1 | `services/hnrnp_motifs.py:306-341` | Intronic regions = the 250 nt following each 5′ss (upstream-exon 5′ss and skipped-exon 5′ss); the 3′ss-proximal intron ends (PPT/PTB/hnRNP C territory) are scanned only when the intron is < ~276 nt | Follow rMAPS2: 4 intronic regions per SE event (250 nt after each 5′ss and 250 nt before each 3′ss, with the 6/20-nt exclusions) and 50 nt exonic flanks; keep the full skipped exon as a fifth exonic region if wanted. |
| E2 | `services/hnrnp_motifs.py` `compare_groups` | Binary presence per region, significant vs non-significant, direction ignored | Presence saturates for `AGG`, `GGG`, `TTTT`, `CTCT` on 250-nt regions (hit rate ≈ 100 % in both groups → no power); test the density (Mann-Whitney) and split the significant set by ΔΨ sign so the `REGULATORY_EFFECTS` (ESE/ESS/ISE/ISS) labels become interpretable. Add rMAPS2's 50-nt sliding-window Wilcoxon map. |
| E3 | `routers/deep_analyses.py:480-618` | 13 Welch/z tests, no correction, Welch on right-skewed sizes | Add Mann-Whitney U for sizes and PPT, report BH-adjusted q next to p, state the number of tests programmatically. |
| E4 | `services/splice_features.py` | No splice-site strength score (only GT/AG) | Port MaxEntScan (Yeo & Burge 2004) — see the spec §8.3; also flag `GC` donors and `AT-AC` (U12) pairs instead of "non-canonical". |
| E5 | `services/mane.py:240-243` / `mane_local.py` | `in_frame` = `cds_exon_length % 3 == 0`; no PTC/NMD | Translate both isoforms on the MANE CDS and apply the 50–55-nt rule (as Sashimi-viewer's `spliceModel.ts`); keep "no heuristic without MANE". |
| E6 | `components/top10/ConsensusExonView.tsx:74-76` | `pseudoFdr = max(0.001, 1 − meanCanonical/100)` drives the dashed arc | Do not fabricate an FDR; pass an explicit `dashed = meanCanonical < 95` prop. |
| E7 | `components/top10/ExonDiagram.tsx:131-134` vs `SpliceSiteTrack.tsx:25-30`, `ConsensusLogoPanel.tsx:47-52`, `PPTTrack.tsx` | Three nucleotide palettes (A orange/G violet/C blue/T cyan; A green/C blue/G orange/T red; pyrimidine blue/purine orange) | One palette everywhere (IGV convention A `#1a9e37` C `#2452d6` G `#d9861c` T `#d6332b` if aligning with Sashimi-viewer). |
| E8 | `components/events/EventsTable.tsx:46-49` + `app/analyses/[id]/page.tsx:48,66-67` | Client-side sort of the current page coexists with the server sort select | Set `manualSorting: true` and route header clicks to the server sort. |
| E9 | `components/events/Top10View.tsx:82-84,108-109` + `app/analyses/[id]/deep-analysis/page.tsx:28-35` | `showStringDB` requires `activeModules.has("stringdb")` but `MODULES` has no `stringdb` → the Interactions tab never shows in a deep analysis; "panelapp" sort actually sorts by FDR | Add `stringdb` to `MODULES` (or drop the condition); implement the PanelApp sort using the annotation query cache (confidence 3 > 2 > 1 > none). |
| E10 | `components/events/Top10View.tsx:87-90` | `ensemblHints` rebuilt every render | `useMemo` on `mutatedGenes`. |
| E11 | `app/layout.tsx:13` vs `contexts/LanguageContext.tsx:56,66` | `<html lang="en">` while the default language is `fr` | Set the default consistently (or read `localStorage` before hydration). |
| E12 | `models/analysis.py` `SampleGroup.sample_names` | stored, never used | Use them as replicate labels in the PSI columns and PDF, or remove the field. |

---

## Suggested order of application on the original code (if the Python app is kept alive)
1. A1 + A2 + A3 + A15 + A16 (ingestion) — with a migration and updated `tests/test_parser_coverage.py` (add A3SS/A5SS/MXE/RI fixtures and a `MYSERIES_SE.MATS.JC.txt` case).
2. A4 + A5 (sequence extraction) — unit test with a region past a contig end.
3. A6 + A7 + D19 (MANE) — test on a gene with a MANE Plus Clinical transcript listed first (e.g. check v1.5 for such genes).
4. A8 + A9 + A12 + A13 + A14 (analysis/report correctness).
5. B1–B9 (text/code consistency) and README.
6. C1–C14, then D and E as time allows.

---

## Status after the fix pass (branch `claude/compassionate-cerf-5o8rar`, 2026-09-19)

Verified by two independent adversarial reviews (backend, frontend), the `code-review` skill at high effort, and the test suites (backend pytest, frontend `tsc` + `next build`).

| Item | Status | Notes |
|---|---|---|
| A1–A14, A16 | **done** | see the per-file summaries in the commit history; A12 changes `bp_distance` semantics (branch A → exon start, 18–44 nt window) |
| A15 | **partial** | mean over available replicates, NA ignored, per-reason counts logged; annotation-only (`fromGTF`) rows mixed with count files are still dropped (counted, no longer silent); counts not yet returned in `UploadResponse` |
| B1–B6, B9 | **done** | PDF/README text derived from code (test count = `len(tests)`, 50/100/250/500 actually run unless all events are enumerated exactly, ≥ 5 events per group enforced, top 10) |
| B7, B8 | **done** | README rewritten to match the code |
| C1–C5, C7–C10, C14 | **done** | |
| C6 | **not done** | upload parsing still synchronous in the request (design change deferred; `error_message` now stores parser errors) |
| C11, C12 | **done** | |
| C13 | **partial** | PanelApp: in-process 6 h cache; STRING: per-pair calls deduplicated only |
| D1–D22 | **done** | D18 completed by the review: one shared `services/stats.py` (z-test, Mann-Whitney U with tie + continuity correction, BH, normal CDF), one `build_se_regions` |
| E1 | **done** | rMAPS2 seven-region design (both ends of each intron) |
| E2 | **partial** | density Mann-Whitney U added per (motif, region) with its own BH family; the ΔΨ-sign split and the 50-nt sliding-window map are not implemented |
| E3 | **done** | 20 tests (7 Welch + 7 MWU + 6 z), BH `q_value` / `significant_fdr` |
| E4 (MaxEntScan), E5 (PTC/NMD by translation) | **not done** | new features, not defects; specified in `SPLICEANALYZER_IN_BROWSER_SPEC.md` §8.3 and §8.5 |
| E6–E11 | **done** | |
| E12 | **not done** | `sample_names` still unused (cosmetic) |

Additional defects found and fixed by the review pass (not in the original list): two divergent Mann-Whitney implementations (different p-values for the same data); branch-point marker placed 5 nt too far 5′ in the UI (`bp_position` is the 7-mer start, the adenosine is at +5); `None` canonical flags printed as "!GT/!AG" in the PDF; PDF text claiming non-overlapping intron windows; EventsTable server-sort mapping; stale compute-progress cache stopping the poll; upload warnings not displayed; hnRNP `regions` list not typed; empty uploaded file failing the whole upload; per-worker startup reset killing running computations (stale-heartbeat rule); `TimeoutExpired` blanking a whole FASTA chunk; duplicated Ensembl chromosome mapping; inconsistent branch-point denominators (now `ppt_seq` eligibility everywhere); pre-existing ORM/migration drift (timestamps NOT NULL, undeclared indexes → migration 0018); pre-existing race in the MANE SQLite cache initialisation across annotation threads (`no such table: mane_cache` → intermittent `frame_class = unknown`), found by repeating the end-to-end scenario.
