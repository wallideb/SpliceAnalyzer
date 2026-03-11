# Pipeline Simplification Plan

## Current vs Target Flow

### Current (confusing)
```
Import → Auto top-10 rank → View events → Filter → Add to basket (localStorage)
                               ↓
                         Top-10 page (hardcoded)
                               ↓
                    Deep analysis (ephemeral, top-N + basket)
```

### Target (clean)
```
A. Import → Annotate on entry (unchanged)
      ↓
B. View events → Filter by thresholds (FDR/p-value/ΔPSI)
   → "Mark as significant" → Events above threshold = significant
   → Events below = non-significant (for this analysis context)
      ↓
C. Launch Deep Analysis (saved to DB)
   → Permutation: patients vs controls (per-event ΔΨ)
   → Pattern comparison: significant vs non-significant
     (exon size, PPT, canonical sites, frame, branch point)
   → Event cards for all significant events (replaces top-10 view)
      ↓
D. Saved deep analyses with exportable methodology
   → Parameters recorded (thresholds, date, modules)
   → PDF export includes methodology section
```

---

## Changes Required

### Phase 1: Backend — New DeepAnalysis model & remove top_rank

**1.1 New DB model: `DeepAnalysis`**
- File: `backend/app/models/deep_analysis.py` (new)
```
DeepAnalysis:
  id              UUID PK
  analysis_id     FK → Analysis
  name            Text (auto-generated or user-provided)
  fdr_threshold   Float (e.g. 0.05)
  pvalue_threshold Float (nullable)
  delta_psi_min   Float (e.g. 0.1)
  modules         JSONB (list of active module names)
  created_at      Timestamp
  status          String (pending/computing/ready/error)
  n_significant   Integer
  n_not_significant Integer
  permutation_iterations Integer (nullable)
```

**1.2 New DB model: `DeepAnalysisEvent`** (junction table)
- Links events to a deep analysis with significance flag
```
DeepAnalysisEvent:
  deep_analysis_id  FK → DeepAnalysis
  event_id          FK → SplicingEvent
  is_significant    Boolean
```

**1.3 Remove `top_rank` from SplicingEvent**
- Drop column `top_rank` from events table
- Remove `event_selector.py` service
- Remove `select_top10()` call from parser.py
- Remove `getTop10()` API endpoint
- Remove index `ix_events_analysis_top_rank`

**1.4 New router: `backend/app/routers/deep_analyses.py`**
- `POST /analyses/{id}/deep-analyses` — Create a deep analysis
  - Accepts: `fdr_threshold`, `pvalue_threshold`, `delta_psi_min`, `modules`
  - Tags events as significant/non-significant based on thresholds
  - Stores in DB, triggers splice computation if "splice"/"motifs" module active
  - Returns deep analysis ID
- `GET /analyses/{id}/deep-analyses` — List saved deep analyses
- `GET /deep-analyses/{id}` — Get deep analysis detail + events
- `DELETE /deep-analyses/{id}` — Delete a saved deep analysis
- `GET /deep-analyses/{id}/events?significant=true|false` — Get events by significance

**1.5 Update permutation service**
- Currently compares G1 (ΔΨ<0) vs G2 (ΔΨ>0) for auxiliary metrics
- Add new comparison mode: **significant vs non-significant** for:
  - Exon size distribution
  - PPT score
  - Canonical site percentage
  - Frame class proportions
  - Branch point detection rate
- Keep existing per-event ΔΨ permutation (patients vs controls)

**1.6 Update splice patterns endpoint**
- Accept `deep_analysis_id` as parameter instead of ad-hoc thresholds
- Use pre-tagged significance from DeepAnalysisEvent table

**1.7 Alembic migration**
- Add `deep_analyses` and `deep_analysis_events` tables
- Remove `top_rank` column from `splicing_events`

---

### Phase 2: Frontend — Simplified UI flow

**2.1 Remove top-10 page entirely**
- Delete: `src/app/analyses/[id]/top10/page.tsx`
- Remove "Top 10" button from analysis detail header
- Remove `highlightTop10`, `hideTop10` state and UI
- Remove `getTop10()` API calls
- Remove `Top10View.tsx` component (replaced by new deep-analysis view)

**2.2 Simplify analysis detail page (`[id]/page.tsx`)**
- Keep: Event table, filters (FDR/p-value/ΔPSI sliders), Manhattan plot
- Remove: Top-10 highlighting, hide-top-10 toggle
- Add: "Launch Deep Analysis" button (replaces basket + top-10 link)
  - Uses current filter thresholds as significance criteria
  - Shows preview: "X events significant, Y non-significant"
  - Opens modal to confirm thresholds + select modules
- Keep basket for manual event curation (optional override)

**2.3 Restructure deep-analysis page**
- Route: `/analyses/[id]/deep-analysis/[deepId]` (saved, not ephemeral)
- Show: methodology bar at top (thresholds used, date, modules)
- Tabs:
  1. **Overview**: Summary stats (n significant, n non-significant, thresholds)
  2. **Event Cards**: Scrollable annotated cards for significant events
     (gene info, GO terms, PanelApp, rMATS scores, STRING-DB)
  3. **Pattern Analysis**: Aggregate motif/splice comparison
     (significant vs non-significant side-by-side)
  4. **Permutation**: Statistical tests
  5. **Splice Sites**: Per-event consensus site details
- Remove: SidebarNav multi-mode system (too many tabs)
- Replace with: Simpler top-level section tabs

**2.4 Deep analysis list view**
- On analysis detail page, add section showing saved deep analyses
- Each card: name, thresholds, date, n_significant, status
- Click → opens deep analysis detail
- Delete button with confirmation

**2.5 Update BasketContext**
- Keep localStorage basket for event curation
- But significance tagging now driven by thresholds, not manual basket
- Basket becomes optional: "add extra events to deep analysis"

**2.6 PDF export update**
- Include methodology section with:
  - Thresholds used (FDR ≤ X, |ΔΨ| ≥ Y)
  - Date of analysis
  - Active modules
  - Number of significant/non-significant events
  - Permutation parameters (iterations count)

---

### Phase 3: Pattern comparison (significant vs non-significant)

**3.1 Backend: dual-group pattern analysis**
- New endpoint or extended `/splice/patterns`:
  `GET /deep-analyses/{id}/patterns`
- Returns TWO sets of stats side-by-side:
  - `significant`: exon_sizes, donor_sites, acceptor_sites, ppt, frame, bp
  - `not_significant`: same structure
- Frontend renders them in a comparison layout

**3.2 Frontend: comparison visualization**
- Side-by-side exon size histograms
- Side-by-side sequence logos (5'SS, 3'SS)
- Comparative PPT score distributions
- Frame class proportions compared
- Statistical test (chi-square or Fisher) for proportional differences

---

## Files to Delete
- `frontend/src/app/analyses/[id]/top10/page.tsx`
- `backend/app/services/event_selector.py`
- References to `top_rank` throughout

## Files to Create
- `backend/app/models/deep_analysis.py`
- `backend/app/routers/deep_analyses.py`
- `backend/app/schemas/deep_analysis.py`
- `frontend/src/app/analyses/[id]/deep-analysis/[deepId]/page.tsx`
- `frontend/src/components/deep-analysis/OverviewPanel.tsx`
- `frontend/src/components/deep-analysis/PatternComparisonPanel.tsx`
- `frontend/src/components/deep-analysis/EventCardsPanel.tsx`
- Alembic migration file

## Files to Modify Heavily
- `frontend/src/app/analyses/[id]/page.tsx` (remove top-10 refs, add launch deep analysis)
- `frontend/src/app/analyses/[id]/deep-analysis/page.tsx` (now lists saved analyses)
- `backend/app/routers/events.py` (remove top-10 endpoint)
- `backend/app/routers/splice.py` (accept deep_analysis_id)
- `backend/app/services/parser.py` (remove top_rank assignment)
- `backend/app/services/permutation.py` (add sig vs non-sig comparison)

## Estimated Scope
- ~15 files modified, ~8 files created, ~2 files deleted
- Backend: new model + migration + 2 routers + service updates
- Frontend: page restructure + new components + remove top-10

## Suggested Implementation Order
1. Backend model + migration + CRUD router (foundation)
2. Remove top_rank from backend (clean break)
3. Frontend: remove top-10 page + references
4. Frontend: add "Launch Deep Analysis" flow on events page
5. Frontend: restructure deep-analysis detail page
6. Backend: dual-group pattern comparison endpoint
7. Frontend: pattern comparison visualization
8. PDF methodology export update
