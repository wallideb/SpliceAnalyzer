"""
PanelApp service
================
Queries gene disease panels from PanelApp. Tries PanelApp Australia (AGHA)
first, then falls back to PanelApp Genomics England (UK) if no results are
found. Both instances share the same REST API format.

External endpoints:
    PanelApp AU  – https://panelapp.agha.umccr.org/api/v1/genes/
    PanelApp UK  – https://panelapp.genomicsengland.co.uk/api/v1/genes/

Confidence levels (PanelApp convention):
    3 → Green  (high confidence – gene-disease association established)
    2 → Amber  (moderate confidence – limited evidence)
    1 → Red    (low confidence – disputed or very limited evidence)

Pagination:
    The API returns paginated results (default ~25 per page). All pages are
    fetched by following the ``next`` URL until None.

Circuit breaker:
    PanelApp AU is occasionally unreachable.  After a connection-level failure
    (ConnectError, ConnectTimeout) the source is placed in a backoff period
    (_BACKOFF_SECONDS) so subsequent requests skip it immediately instead of
    waiting for the full timeout on every call.  This prevents a flaky AU from
    adding ~8 s of latency per gene in large exports.
"""

from __future__ import annotations

import logging
import time

import httpx

logger = logging.getLogger(__name__)

# Separate connect and read timeouts: fail fast on connection issues (the most
# common failure mode for PanelApp AU) while allowing a generous read timeout
# for slow but live endpoints.
_TIMEOUT = httpx.Timeout(connect=4.0, read=4.0, write=4.0, pool=4.0)
_MAX_PAGES = 10  # safety limit to avoid infinite loops

# Primary and fallback PanelApp base URLs
_SOURCES: list[str] = [
    "https://panelapp.agha.umccr.org/api/v1",        # PanelApp Australia
    "https://panelapp.genomicsengland.co.uk/api/v1",  # PanelApp UK (fallback)
]

_CONFIDENCE_LABEL: dict[str, str] = {
    "3": "green",
    "2": "amber",
    "1": "red",
}

# ── Circuit breaker ──────────────────────────────────────────────────────────
# Maps source base-URL → monotonic timestamp until which the source is skipped.
_source_down_until: dict[str, float] = {}
_BACKOFF_SECONDS: float = 300.0  # 5 min backoff after a connection failure


def _is_source_available(base: str) -> bool:
    """Return True if *base* is not currently in its backoff window."""
    return time.monotonic() >= _source_down_until.get(base, 0.0)


def _mark_source_down(base: str) -> None:
    """Place *base* in backoff for _BACKOFF_SECONDS."""
    _source_down_until[base] = time.monotonic() + _BACKOFF_SECONDS
    logger.warning(
        "PanelApp: %s marked unavailable for %.0f s (connection failed)",
        base, _BACKOFF_SECONDS,
    )


async def _fetch_all_pages(client: httpx.AsyncClient, url: str, params: dict) -> list[dict]:
    """
    Fetch all paginated results for a PanelApp genes query.

    Follows the ``next`` field in each response until exhausted or
    ``_MAX_PAGES`` is reached.
    """
    results: list[dict] = []
    next_url: str | None = url

    for _ in range(_MAX_PAGES):
        if next_url is None:
            break
        resp = await client.get(next_url, params=params)
        if resp.status_code == 404:
            break
        resp.raise_for_status()
        data = resp.json()
        results.extend(data.get("results", []))
        next_url = data.get("next")  # None when last page
        params = {}  # subsequent pages use the full URL from `next`

    return results


async def _query_source(base: str, symbol: str) -> list[dict]:
    """
    Query one PanelApp instance for all panels related to *symbol*.

    Strategy:
      1. Exact match  – ``entity_name=SYMBOL``
      2. If empty, case-insensitive fallback – ``entity_name__icontains=SYMBOL``
         with post-filtering to keep only exact gene-symbol matches.

    Returns raw API result entries (empty list on error, no match, or when the
    source is currently in its circuit-breaker backoff period).
    """
    if not _is_source_available(base):
        logger.debug("PanelApp: skipping %s (in backoff window)", base)
        return []

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
            # ── 1. Exact match (most common, fastest) ──────────────────────
            entries = await _fetch_all_pages(
                client,
                f"{base}/genes/",
                params={"entity_name": symbol, "format": "json"},
            )

            # ── 2. Case-insensitive fallback ───────────────────────────────
            if not entries:
                logger.debug(
                    "PanelApp exact match empty for %r at %s – trying icontains", symbol, base
                )
                all_entries = await _fetch_all_pages(
                    client,
                    f"{base}/genes/",
                    params={"entity_name__icontains": symbol, "format": "json"},
                )
                # Keep only entries whose entity_name matches exactly (case-insensitive)
                entries = [
                    e for e in all_entries
                    if e.get("entity_name", "").upper() == symbol
                ]

        return entries

    except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
        # Connection-level failure → engage circuit breaker so subsequent
        # requests for other genes are not delayed by the same dead endpoint.
        _mark_source_down(base)
        logger.warning(
            "PanelApp connection failed (%s) for %r: %s", base, symbol, exc
        )
        return []
    except httpx.TimeoutException as exc:
        # Read/pool timeout: likely a slow endpoint rather than a dead one.
        # Don't trigger circuit breaker but do log and return empty.
        logger.warning(
            "PanelApp timeout (%s) for %r: %s", base, symbol, exc
        )
        return []
    except httpx.HTTPError as exc:
        logger.warning("PanelApp request failed (%s) for %r: %s", base, symbol, exc)
        return []


def _parse_entries(entries: list[dict]) -> list[dict]:
    """Convert raw PanelApp API entries into normalised panel dicts."""
    panels: list[dict] = []
    seen: set[str] = set()

    for entry in entries:
        panel = entry.get("panel", {})
        name = panel.get("name", "")
        if not name or name in seen:
            continue
        seen.add(name)

        conf_raw = entry.get("confidence_level", "")
        conf_str = str(conf_raw).strip()

        # relevant_disorders may live on the panel or directly on the entry
        disorders: list[str] = (
            panel.get("relevant_disorders")
            or entry.get("relevant_disorders")
            or []
        )
        if not isinstance(disorders, list):
            disorders = []

        panels.append(
            {
                "panel_name": name,
                "confidence_level": int(conf_str) if conf_str.isdigit() else 0,
                "confidence_label": _CONFIDENCE_LABEL.get(conf_str, "unknown"),
                "disorders": [str(d) for d in disorders[:5]],
            }
        )

    # Sort: green → amber → red → unknown
    _order = {"green": 0, "amber": 1, "red": 2, "unknown": 3}
    panels.sort(key=lambda p: (_order.get(p["confidence_label"], 3), p["panel_name"]))
    return panels


async def get_panels_for_gene(symbol: str) -> list[dict]:
    """
    Return all PanelApp panels for *symbol*, trying AU then UK.

    Each returned dict contains:
        panel_name        (str)       – human-readable panel title
        confidence_level  (int)       – 1 / 2 / 3
        confidence_label  (str)       – "red" / "amber" / "green"
        disorders         (list[str]) – relevant disorder names (up to 5)

    Returns an empty list if the gene is not found in either instance or
    both APIs are unreachable / in backoff.
    """
    symbol = symbol.upper()

    for base in _SOURCES:
        entries = await _query_source(base, symbol)
        if entries:
            panels = _parse_entries(entries)
            if panels:
                logger.debug(
                    "PanelApp: %d panel(s) for %r from %s", len(panels), symbol, base
                )
                return panels

    logger.info("PanelApp: no panels found for %r in any source", symbol)
    return []
