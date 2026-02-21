"""
PanelApp Australia service
==========================
Queries the PanelApp Australia (AGHA) API for disease panels associated
with a given gene symbol.

External endpoint:
    GET https://panelapp.agha.umccr.org/api/v1/genes/?entity_name={symbol}

Confidence levels (PanelApp convention):
    3 → Green  (high confidence – gene-disease association established)
    2 → Amber  (moderate confidence – limited evidence)
    1 → Red    (low confidence – disputed or very limited evidence)
"""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

_BASE = "https://panelapp.agha.umccr.org/api/v1"
_TIMEOUT = 8.0

_CONFIDENCE_LABEL: dict[str, str] = {
    "3": "green",
    "2": "amber",
    "1": "red",
}


async def get_panels_for_gene(symbol: str) -> list[dict]:
    """
    Return the list of PanelApp panels for a gene symbol.

    Each entry contains:
        panel_name        (str)   – human-readable panel title
        confidence_level  (int)   – 1 / 2 / 3
        confidence_label  (str)   – "red" / "amber" / "green"
        disorders         (list[str]) – relevant disorder names

    Returns an empty list if the gene is not found or the API is unreachable.
    """
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                f"{_BASE}/genes/",
                params={"entity_name": symbol.upper(), "format": "json"},
            )
            if resp.status_code == 404:
                return []
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as exc:
        logger.warning("PanelApp request failed for %r: %s", symbol, exc)
        return []

    panels: list[dict] = []
    seen: set[str] = set()

    for entry in data.get("results", []):
        panel = entry.get("panel", {})
        name = panel.get("name", "")
        if not name or name in seen:
            continue
        seen.add(name)

        conf_str = str(entry.get("confidence_level", ""))
        disorders = panel.get("relevant_disorders") or []

        panels.append(
            {
                "panel_name": name,
                "confidence_level": int(conf_str) if conf_str.isdigit() else 0,
                "confidence_label": _CONFIDENCE_LABEL.get(conf_str, "unknown"),
                "disorders": disorders[:5],  # cap to avoid very long lists
            }
        )

    # Sort: green first, then amber, then red
    _order = {"green": 0, "amber": 1, "red": 2, "unknown": 3}
    panels.sort(key=lambda p: _order.get(p["confidence_label"], 3))
    return panels
