"""
SE event clustering (Union-Find)
=================================
Groups SE events from the same gene (and strand) whose skipped-exon
boundaries differ by at most *threshold* bp on both sides:

  |e1.exon_start - e2.exon_start| ≤ threshold
  AND
  |e1.exon_end   - e2.exon_end  | ≤ threshold

The representative event of each cluster is the one with the lowest FDR
(then lowest p-value as tie-breaker).
"""

from __future__ import annotations

import statistics
import uuid
from dataclasses import dataclass, field
from typing import Any

CLUSTER_THRESHOLD = 50  # bp


# ---------------------------------------------------------------------------
# Union-Find (path-compressed, union-by-rank)
# ---------------------------------------------------------------------------

class _UF:
    def __init__(self, n: int):
        self.parent = list(range(n))
        self.rank   = [0] * n

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]  # path compression
            x = self.parent[x]
        return x

    def union(self, x: int, y: int) -> None:
        rx, ry = self.find(x), self.find(y)
        if rx == ry:
            return
        if self.rank[rx] < self.rank[ry]:
            rx, ry = ry, rx
        self.parent[ry] = rx
        if self.rank[rx] == self.rank[ry]:
            self.rank[rx] += 1


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

@dataclass
class EventClusterResult:
    cluster_id: uuid.UUID = field(default_factory=uuid.uuid4)
    gene_symbol: str | None = None
    chr: str | None = None
    strand: str | None = None
    exon_start: int | None = None   # median of cluster
    exon_end: int | None = None
    n_events: int = 0
    source_ids: list[str] = field(default_factory=list)   # event UUIDs as str
    rep_event_id: str | None = None  # UUID of representative event


def _get(obj: Any, *keys: str) -> Any:
    for k in keys:
        try:
            return getattr(obj, k)
        except AttributeError:
            pass
        try:
            return obj[k]
        except (KeyError, TypeError):
            pass
    return None


def cluster_se_events(
    events: list[Any],
    threshold: int = CLUSTER_THRESHOLD,
) -> list[EventClusterResult]:
    """Cluster a list of SE SplicingEvent objects (or dicts).

    Only events where event_type == 'SE' are processed.
    Non-SE events are silently skipped.
    """
    se = [e for e in events if _get(e, "event_type") == "SE"]
    if not se:
        return []

    n = len(se)
    uf = _UF(n)

    # Group by (gene_symbol, chr, strand) for O(k²) within groups instead of O(n²)
    from collections import defaultdict
    groups: dict[tuple, list[int]] = defaultdict(list)
    for i, ev in enumerate(se):
        key = (
            _get(ev, "gene_symbol") or "",
            _get(ev, "chr") or "",
            _get(ev, "strand") or "",
        )
        groups[key].append(i)

    for indices in groups.values():
        for a in range(len(indices)):
            for b in range(a + 1, len(indices)):
                ia, ib = indices[a], indices[b]
                ea, eb = se[ia], se[ib]
                s_a = _get(ea, "exon_start") or 0
                e_a = _get(ea, "exon_end")   or 0
                s_b = _get(eb, "exon_start") or 0
                e_b = _get(eb, "exon_end")   or 0
                if abs(s_a - s_b) <= threshold and abs(e_a - e_b) <= threshold:
                    uf.union(ia, ib)

    # Collect clusters
    from collections import defaultdict
    cluster_map: dict[int, list[int]] = defaultdict(list)
    for i in range(n):
        cluster_map[uf.find(i)].append(i)

    results = []
    for root, members in cluster_map.items():
        evs = [se[i] for i in members]

        # Representative = lowest FDR, then lowest p-value
        def _sort_key(ev: Any) -> tuple:
            fdr   = _get(ev, "fdr")   or 1.0
            pval  = _get(ev, "p_value") or 1.0
            return (fdr, pval)

        rep = min(evs, key=_sort_key)

        starts = [_get(e, "exon_start") for e in evs if _get(e, "exon_start") is not None]
        ends   = [_get(e, "exon_end")   for e in evs if _get(e, "exon_end")   is not None]

        results.append(EventClusterResult(
            gene_symbol  = _get(rep, "gene_symbol"),
            chr          = _get(rep, "chr"),
            strand       = _get(rep, "strand"),
            exon_start   = int(statistics.median(starts)) if starts else None,
            exon_end     = int(statistics.median(ends))   if ends   else None,
            n_events     = len(evs),
            source_ids   = [str(_get(e, "id")) for e in evs],
            rep_event_id = str(_get(rep, "id")),
        ))

    return results
