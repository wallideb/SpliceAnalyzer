#!/usr/bin/env python3
"""End-to-end verification of the rMATS-viz backend against a real PostgreSQL.

Runs the FastAPI app in-process (httpx ASGITransport, lifespan entered
manually) and asserts every step listed in the task.  Results are printed as
a table and written to results.json.
"""
from __future__ import annotations

import asyncio
import io
import json
import math
import os
import subprocess
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
BACKEND = os.path.abspath(os.path.join(HERE, "..", ".."))

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://rmats:rmats@127.0.0.1:5433/rmatsdb")
os.environ["GRCH38_FASTA"] = os.path.join(DATA, "genome.fa")
os.environ.setdefault("SAMTOOLS_BIN", os.path.join(HERE, "samtools"))
os.environ["MANE_GFF3"] = os.path.join(DATA, "MANE.GRCh38.ensembl_genomic.gff.gz")
os.environ["MANE_CACHE_DB"] = os.path.join(HERE, "mane_cache.db")
os.environ.pop("SVG_EXPORT_DIR", None)
os.environ.setdefault("UPLOAD_TMP_DIR", os.path.join(HERE, "uploads_tmp"))
if os.path.exists(os.environ["MANE_CACHE_DB"]):
    os.remove(os.environ["MANE_CACHE_DB"])
sys.path.insert(0, BACKEND)
os.chdir(BACKEND)

import shutil  # noqa: E402

try:  # pysam is optional: samtools is the fallback oracle
    import pysam  # noqa: E402
except ImportError:  # pragma: no cover
    pysam = None
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.main import app  # noqa: E402

EXP = json.load(open(os.path.join(DATA, "expected.json")))
_FA = os.path.join(DATA, "genome.fa")


class _SamtoolsFasta:
    """Minimal stand-in for pysam.FastaFile using the samtools binary."""

    def __init__(self, path: str) -> None:
        self.path = path
        self.bin = os.environ.get("SAMTOOLS_BIN") or shutil.which("samtools")
        if not self.bin:
            sys.exit("neither pysam nor samtools is available for the sequence oracle")

    def fetch(self, chrom: str, start: int, end: int) -> str:
        out = subprocess.run([self.bin, "faidx", self.path, f"{chrom}:{start + 1}-{end}"],
                             check=True, capture_output=True, text=True).stdout
        return "".join(line.strip() for line in out.splitlines() if not line.startswith(">"))


GENOME = pysam.FastaFile(_FA) if pysam is not None else _SamtoolsFasta(_FA)

RESULTS: list[dict] = []


def check(name: str, cond: bool, observed=None, expected=None) -> bool:
    RESULTS.append({"name": name, "pass": bool(cond), "observed": observed, "expected": expected})
    mark = "PASS" if cond else "FAIL"
    obs = "" if observed is None else f" observed={observed!r}"
    exp = "" if expected is None else f" expected={expected!r}"
    print(f"[{mark}] {name}{obs}{exp}")
    return bool(cond)


def rc(s: str) -> str:
    return s.translate(str.maketrans("ACGT", "TGCA"))[::-1]


def fetch(chrom: str, s: int, e: int) -> str:
    s = max(s, 0)
    return GENOME.fetch(chrom, s, e).upper() if e > s else ""


def expected_windows(chrom, strand, es, ee, ues, uee, des, dee):
    """Independent implementation of the documented window coordinates."""
    if strand == "+":
        return dict(
            donor=fetch(chrom, ee - 3, ee + 6), acceptor=fetch(chrom, es - 20, es + 3),
            ppt=fetch(chrom, es - 50, es - 3),
            up_donor=fetch(chrom, uee - 3, uee + 6), dn_acceptor=fetch(chrom, des - 20, des + 3),
        )
    return dict(
        donor=rc(fetch(chrom, es - 6, es + 3)), acceptor=rc(fetch(chrom, ee - 3, ee + 20)),
        ppt=rc(fetch(chrom, ee + 3, ee + 50)),
        up_donor=rc(fetch(chrom, des - 6, des + 3)), dn_acceptor=rc(fetch(chrom, uee - 3, uee + 20)),
    )


def psql(sql: str) -> str:
    """Run one SQL statement against DATABASE_URL and return the first column of
    the first row as text (psql -At style; multi-column rows are joined with '|').

    Uses asyncpg in a helper thread so it works from inside the running event
    loop and needs no psql binary (the backend image has none)."""
    import asyncpg  # noqa: E402
    import concurrent.futures

    dsn = os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")

    async def _run() -> str:
        conn = await asyncpg.connect(dsn)
        try:
            rows = await conn.fetch(sql)
        finally:
            await conn.close()
        if not rows:
            return ""
        return "\n".join("|".join("" if v is None else str(v) for v in r.values()) for r in rows)

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        return ex.submit(lambda: asyncio.run(_run())).result()


GENES = {g["idx"]: g for g in EXP["genes"]}
KEPT = {(r["chr"], r["es"], r["ee"]): r for r in EXP["kept_se"]}


async def main() -> None:
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test", timeout=600) as c:
            await run(c)


async def run(c: AsyncClient) -> None:
    # ── health ──────────────────────────────────────────────────────────
    r = await c.get("/api/v1/health")
    check("health db ok", r.status_code == 200 and r.json().get("db") == "ok", r.json())
    r = await c.get("/api/v1/debug/fasta")
    dbg = r.json()
    check("debug/fasta: samtools wrapper + fai visible", dbg.get("samtools_rc") == 0 and dbg.get("fai_exists"),
          {k: dbg.get(k) for k in ("samtools_version", "fai_exists", "faidx_test_rc")})

    # ── a. upload ──────────────────────────────────────────────────────
    names = ["SE.MATS.JC.txt", "SE.MATS.JCEC.txt", "A3SS.MATS.JC.txt", "A5SS.MATS.JC.txt",
             "RI.MATS.JC.txt", "MXE.MATS.JC.txt", "summary.txt"]
    files = [("files", (n, open(os.path.join(DATA, n), "rb").read(), "text/plain")) for n in names]
    data = {"name": "e2e synthetic", "group1_label": "Patients", "group2_label": "Controls",
            "group1_samples": json.dumps(["P1", "P2", "P3"]), "group2_samples": json.dumps(["C1", "C2", "C3"]),
            "mutated_genes": json.dumps([{"symbol": "GENE1", "ensembl_id": "ENSG00000000001", "display": "GENE1"}])}
    r = await c.post("/api/v1/analyses", data=data, files=files)
    check("a. POST /analyses -> 201", r.status_code == 201, r.status_code, 201)
    up = r.json()
    aid = up["analysis_id"]
    check("a. event_count == expected (coverage filter + dedup)", up["event_count"] == EXP["event_count"],
          up["event_count"], EXP["event_count"])
    check("a. warnings mention the empty summary.txt", any("summary.txt" in w and "empty" in w for w in up["warnings"]),
          up["warnings"])
    r = await c.get(f"/api/v1/analyses/{aid}")
    check("a. GET /analyses/{id} status ready", r.status_code == 200 and r.json()["status"] == "ready",
          r.json().get("status"), "ready")
    check("a. sample groups round-trip", [g["group_label"] for g in r.json()["sample_groups"]] == ["Patients", "Controls"],
          [g["group_label"] for g in r.json()["sample_groups"]])
    r = await c.get("/api/v1/analyses")
    check("a. GET /analyses lists it", any(a["id"] == aid for a in r.json()), len(r.json()))

    # ── a2. chunked upload (browser path: ≤ 512 KB requests, here 200 KB) ──
    CHUNK = 200 * 1024
    r = await c.post("/api/v1/analyses/uploads")
    check("a2. POST /analyses/uploads -> 201 with upload_id", r.status_code == 201 and "upload_id" in r.json(), r.status_code, 201)
    uid = r.json()["upload_id"]
    n_chunks = n_ok = 0
    sizes_ok = True
    n_expected = sum(max(1, math.ceil(os.path.getsize(os.path.join(DATA, n)) / CHUNK)) for n in names)
    for n in names:
        blob = open(os.path.join(DATA, n), "rb").read()
        total = max(1, math.ceil(len(blob) / CHUNK))          # an empty file is one empty chunk
        last = None
        for i in range(total):
            piece = blob[i * CHUNK:(i + 1) * CHUNK]
            last = await c.put(f"/api/v1/analyses/uploads/{uid}/chunk",
                               params={"filename": n, "index": i, "total": total},
                               content=piece, headers={"Content-Type": "application/octet-stream"})
            n_chunks += 1
            n_ok += last.status_code == 200
        body = last.json() if last.status_code == 200 else {}
        sizes_ok &= body.get("received_bytes") == len(blob) and body.get("received_chunks") == body.get("total_chunks") == total
    check("a2. every 200 KB chunk accepted (200), count == client-side slicing", n_ok == n_chunks == n_expected, (n_ok, n_chunks), n_expected)
    check("a2. received_bytes / chunks reported per file == client sizes", sizes_ok)
    r = await c.put(f"/api/v1/analyses/uploads/{uid}/chunk", params={"filename": names[0], "index": 5, "total": 2},
                    content=b"x", headers={"Content-Type": "application/octet-stream"})
    check("a2. chunk with a different total -> 422", r.status_code == 422, r.status_code)
    r = await c.post(f"/api/v1/analyses/uploads/{uid}/finalize", data={**data, "name": "e2e chunked", "files": json.dumps(names)})
    check("a2. POST finalize -> 201", r.status_code == 201, (r.status_code, r.text[:200]), 201)
    up2 = r.json()
    aid2 = up2["analysis_id"]
    check("a2. chunked event_count == single-shot event_count == expected", up2["event_count"] == up["event_count"] == EXP["event_count"],
          up2["event_count"], EXP["event_count"])
    check("a2. chunked warnings == single-shot warnings (empty summary.txt)", up2["warnings"] == up["warnings"], up2["warnings"])
    check("a2. upload session directory removed after finalize", not os.path.exists(os.path.join(os.environ["UPLOAD_TMP_DIR"], uid)))
    r = await c.get(f"/api/v1/analyses/{aid2}")
    check("a2. GET chunked analysis: status ready, groups round-trip", r.status_code == 200 and r.json()["status"] == "ready"
          and [g["group_label"] for g in r.json()["sample_groups"]] == ["Patients", "Controls"], r.json().get("status"))
    r = await c.delete(f"/api/v1/analyses/{aid2}")
    check("a2. DELETE chunked analysis -> 204", r.status_code == 204, r.status_code)

    # ── b. events ──────────────────────────────────────────────────────
    r = await c.get(f"/api/v1/analyses/{aid}/events", params={"page_size": 200})
    all_ev = r.json()
    check("b. GET events total == event_count", all_ev["total"] == EXP["event_count"], all_ev["total"], EXP["event_count"])
    items = all_ev["items"]
    by_type = {}
    for e in items:
        by_type[e["event_type"]] = by_type.get(e["event_type"], 0) + 1
    check("b. per-type counts", by_type == {"SE": EXP["n_se_kept"], "A3SS": EXP["n_a3ss"], "A5SS": EXP["n_a5ss"],
                                            "RI": EXP["n_ri"], "MXE": EXP["n_mxe"]},
          by_type, {"SE": EXP["n_se_kept"], "A3SS": EXP["n_a3ss"], "A5SS": EXP["n_a5ss"], "RI": EXP["n_ri"], "MXE": EXP["n_mxe"]})
    check("b. gene_symbol / gene_id unquoted", all(not e["gene_symbol"].startswith('"') and not e["gene_id"].startswith('"') for e in items),
          items[0]["gene_symbol"])
    se_items = [e for e in items if e["event_type"] == "SE"]
    # counting_mode recorded and JC/JCEC merge kept the lowest FDR
    mode_ok, fdr_ok, missing = 0, 0, []
    for e in se_items:
        key = (e["chr"], e["exon_start"], e["exon_end"])
        exp = KEPT.get(key)
        if exp is None:
            missing.append(key); continue
        mode_ok += e["counting_mode"] == exp["mode"]
        fdr_ok += math.isclose(e["fdr"], exp["fdr"], rel_tol=1e-9)
    check("b. every kept SE event matches an expected (chr,start,end)", not missing and len(se_items) == len(KEPT), missing[:5])
    check("b. JC+JCEC SE merge kept the lowest-FDR copy (fdr)", fdr_ok == len(KEPT), fdr_ok, len(KEPT))
    check("b. counting_mode of the kept copy is the lower-FDR file (JC/JCEC)", mode_ok == len(KEPT), mode_ok, len(KEPT))
    modes = {e["counting_mode"] for e in items}
    check("b. counting_mode values are JC/JCEC only", modes <= {"JC", "JCEC"}, modes)
    comma = [e for e in se_items if KEPT[(e["chr"], e["exon_start"], e["exon_end"])]["tag"].endswith("comma")]
    check("b. decimal-comma FDR row parsed (0,03 / 0,045 -> lowest kept)", len(comma) == 1 and math.isclose(comma[0]["fdr"], 0.03),
          comma[0]["fdr"] if comma else None, 0.03)
    dup_kept = [KEPT[(e["chr"], e["exon_start"], e["exon_end"])]["tag"] for e in se_items if "dup" in KEPT[(e["chr"], e["exon_start"], e["exon_end"])]["tag"]]
    check("b. +/-50 bp near-duplicates: only the lower-FDR shifted copy survives", dup_kept == ["dup_g5_ex4_lowerfdr"], dup_kept)
    na = [e for e in se_items if "NA" in (e["ijc_sample_1"] or "")]
    check("b. rows with an NA replicate kept (coverage on remaining replicates)", len(na) == 3, len(na), 3)
    # A3SS / A5SS coordinates
    a3 = [e for e in items if e["event_type"] == "A3SS"]
    a5 = [e for e in items if e["event_type"] == "A5SS"]
    ok = all(e["long_exon_start"] is not None and e["long_exon_end"] is not None and e["short_es"] is not None
             and e["short_ee"] is not None and e["flanking_es"] is not None and e["flanking_ee"] is not None
             and e["exon_start"] == e["long_exon_start"] and e["exon_end"] == e["long_exon_end"] for e in a3 + a5)
    check("b. A3SS/A5SS rows carry long/short/flanking + derived exon_start/exon_end", ok,
          [(e["event_type"], e["strand"], e["long_exon_start"], e["short_es"], e["flanking_es"], e["exon_start"]) for e in a3 + a5])
    plus = [e for e in a3 + a5 if e["strand"] == "+" and e["event_type"] == "A3SS"]
    check("b. + strand A3SS: flanking exon copied to upstream_* (flanking_ee <= long start), downstream null",
          all(e["upstream_es"] == e["flanking_es"] and e["upstream_ee"] == e["flanking_ee"] and e["downstream_es"] is None for e in plus),
          [(e["upstream_es"], e["flanking_es"], e["downstream_es"]) for e in plus])
    minus = [e for e in a3 if e["strand"] == "-"]
    check("b. - strand A3SS (flanking downstream): copied to downstream_*, upstream null",
          all(e["downstream_es"] == e["flanking_es"] and e["upstream_es"] is None for e in minus),
          [(e["downstream_es"], e["flanking_es"], e["upstream_es"]) for e in minus])
    g3 = GENES[3]
    nag = sorted((e["long_exon_start"], e["short_es"]) for e in a3 if e["gene_symbol"] == "GENE3")
    e4s = g3["exons"][3][0]
    check("b. NAGNAG A3SS pair (3 nt apart) both survive", nag == [(e4s - 3, e4s), (e4s, e4s + 3)], nag, [(e4s - 3, e4s), (e4s, e4s + 3)])
    ri = sorted((e["exon_start"], e["exon_end"]) for e in items if e["event_type"] == "RI")
    check("b. RI pair sharing riExonStart both survive", len(ri) == 2 and ri[0][0] == ri[1][0] and ri[0][1] != ri[1][1], ri)
    mxe = sorted((e["exon_start"], e["exon_end"], e["second_exon_start"], e["second_exon_end"]) for e in items if e["event_type"] == "MXE")
    check("b. MXE pair same 1st exon / different 2nd exon both survive",
          len(mxe) == 2 and mxe[0][:2] == mxe[1][:2] and mxe[0][2:] != mxe[1][2:], mxe)
    check("b. inc_form_len/skip_form_len stored", all(e["inc_form_len"] == 99 and e["skip_form_len"] == 50 for e in items),
          (items[0]["inc_form_len"], items[0]["skip_form_len"]))
    # filters / sorts / pagination
    n_fdr = sum(1 for e in items if e["fdr"] is not None and e["fdr"] <= 0.05)
    r = await c.get(f"/api/v1/analyses/{aid}/events", params={"fdr_max": 0.05, "page_size": 200})
    check("b. filter fdr_max=0.05", r.json()["total"] == n_fdr, r.json()["total"], n_fdr)
    n_p = sum(1 for e in items if e["p_value"] is not None and e["p_value"] <= 0.01)
    r = await c.get(f"/api/v1/analyses/{aid}/events", params={"p_value_max": 0.01, "page_size": 200})
    check("b. filter p_value_max=0.01", r.json()["total"] == n_p, r.json()["total"], n_p)
    n_d = sum(1 for e in items if e["abs_inc_level_diff"] is not None and e["abs_inc_level_diff"] >= 0.1)
    r = await c.get(f"/api/v1/analyses/{aid}/events", params={"delta_psi_min": 0.1, "page_size": 200})
    check("b. filter delta_psi_min=0.1", r.json()["total"] == n_d, r.json()["total"], n_d)
    r = await c.get(f"/api/v1/analyses/{aid}/events", params={"event_type": "a3ss"})
    check("b. filter event_type case-insensitive", r.json()["total"] == EXP["n_a3ss"], r.json()["total"], EXP["n_a3ss"])
    r = await c.get(f"/api/v1/analyses/{aid}/events", params={"gene_symbol": "gene1", "page_size": 200})
    n_g1 = sum(1 for e in items if "GENE1" in e["gene_symbol"])   # GENE1, GENE10, GENE11, GENE12 (substring ilike)
    check("b. filter gene_symbol ilike (%gene1% -> GENE1/GENE10/GENE11/GENE12)", r.json()["total"] == n_g1
          and all("GENE1" in e["gene_symbol"] for e in r.json()["items"]), (r.json()["total"], sorted({e["gene_symbol"] for e in r.json()["items"]})), n_g1)
    r = await c.get(f"/api/v1/analyses/{aid}/events", params={"sort_by": "abs_inc_level_diff", "sort_dir": "desc", "page_size": 200})
    vals = [e["abs_inc_level_diff"] for e in r.json()["items"] if e["abs_inc_level_diff"] is not None]
    check("b. sort abs_inc_level_diff desc", vals == sorted(vals, reverse=True), vals[:3])
    r = await c.get(f"/api/v1/analyses/{aid}/events", params={"sort_by": "gene_symbol", "sort_dir": "asc", "page_size": 200})
    syms = [e["gene_symbol"] for e in r.json()["items"]]
    check("b. sort gene_symbol asc", syms == sorted(syms), syms[:3])
    r = await c.get(f"/api/v1/analyses/{aid}/events", params={"page": 2, "page_size": 10, "sort_by": "fdr"})
    pg = r.json()
    check("b. pagination page=2 page_size=10", pg["page"] == 2 and len(pg["items"]) == 10 and pg["pages"] == math.ceil(EXP["event_count"] / 10),
          (pg["page"], len(pg["items"]), pg["pages"]), (2, 10, math.ceil(EXP["event_count"] / 10)))
    r = await c.get(f"/api/v1/analyses/{aid}/events", params={"page": 99, "page_size": 10})
    check("b. pagination beyond last page -> empty items", r.status_code == 200 and r.json()["items"] == [], len(r.json()["items"]))
    r = await c.get(f"/api/v1/analyses/{aid}/events", params={"sort_by": "bogus"})
    check("b. invalid sort_by -> 422", r.status_code == 422, r.status_code, 422)
    r = await c.get("/api/v1/analyses/00000000-0000-0000-0000-000000000000/events")
    check("b. unknown analysis -> 404", r.status_code == 404, r.status_code, 404)

    # ── c. manhattan ──────────────────────────────────────────────────
    r = await c.get(f"/api/v1/analyses/{aid}/events/manhattan")
    pts = r.json()
    chrs = [p["chr"] for p in pts]
    order = []
    for ch in chrs:
        if not order or order[-1] != ch:
            order.append(ch)
    check("c. manhattan natural chromosome order chr1 < chr2 < chr10", order == ["chr1", "chr2", "chr10"], order)
    pos1 = [p["position"] for p in pts if p["chr"] == "chr1"]
    check("c. manhattan positions ascending within chr1", pos1 == sorted(pos1), len(pos1))
    check("c. manhattan point count == event_count", len(pts) == EXP["event_count"], len(pts), EXP["event_count"])

    # ── d. compute ───────────────────────────────────────────────────
    r = await c.post(f"/api/v1/splice/compute/{aid}")
    check("d. POST /splice/compute -> 202", r.status_code == 202, r.status_code, 202)
    check("d. compute response fasta_available + started message", r.json()["fasta_available"] and "started" in r.json()["message"].lower(),
          r.json()["message"])
    t0 = time.time()
    while True:
        r = await c.get(f"/api/v1/splice/progress/{aid}")
        prog = r.json()
        if prog["done"] or time.time() - t0 > 300:
            break
        await asyncio.sleep(0.5)
    check("d. progress done, status 'done', no error", prog["done"] and prog["status"] == "done" and prog["error"] is None, prog)
    check("d. n_computed == n_se_events == expected kept SE", prog["n_computed"] == prog["n_se_events"] == EXP["n_se_kept"],
          (prog["n_computed"], prog["n_se_events"]), EXP["n_se_kept"])
    check("d. DB compute_status == 'done' (psql)", psql(f"select compute_status from analyses where id='{aid}'") == "done",
          psql(f"select compute_status, compute_error from analyses where id='{aid}'"))

    # features for every SE event vs independent window extraction
    id_by_key = {(e["chr"], e["exon_start"], e["exon_end"]): e for e in se_items}
    n_seq_ok = n_bp = n_gt = n_ag = 0
    frame_counts = {"in_frame": 0, "frameshift": 0, "unknown": 0, "non_coding": 0}
    feats = {}
    for key, e in id_by_key.items():
        r = await c.get(f"/api/v1/splice/feature/{e['id']}")
        f = r.json()
        feats[key] = f
        tag = KEPT[key]["tag"]
        gidx = int(tag.split("_")[0].lstrip("g")) if not tag.startswith("dup") else int(tag.split("_")[1].lstrip("g"))
        g = GENES[gidx]
        es, ee = e["exon_start"], e["exon_end"]
        if g["mane"]:
            # MANE-corrected boundaries: the exon of the MANE transcript with best overlap
            mes, mee = max(g["exons"], key=lambda x: max(0, min(ee, x[1]) - max(es, x[0])))
        else:
            mes, mee = es, ee
        w = expected_windows(e["chr"], e["strand"], mes, mee, e["upstream_es"], e["upstream_ee"], e["downstream_es"], e["downstream_ee"])
        same = (f["donor_seq"] == w["donor"] and f["acceptor_seq"] == w["acceptor"] and f["ppt_seq"] == w["ppt"]
                and f["upstream_donor_seq"] == w["up_donor"] and f["downstream_acceptor_seq"] == w["dn_acceptor"])
        n_seq_ok += same
        n_gt += bool(f["donor_is_gt"]); n_ag += bool(f["acceptor_is_ag"]); n_bp += bool(f["bp_motif_found"])
        frame_counts[f["frame_class"]] = frame_counts.get(f["frame_class"], 0) + 1
        if not same:
            print("   seq mismatch", tag, {k: (f.get(k2), w[k]) for k, k2 in
                                           [("donor", "donor_seq"), ("acceptor", "acceptor_seq"), ("ppt", "ppt_seq")]})
    check("d. all 5 windows of every SE feature equal the independent FASTA extraction", n_seq_ok == len(id_by_key), n_seq_ok, len(id_by_key))
    # every planted (non-shifted-dup) event must show GT / AG / TACTAAC at -25
    planted = [k for k in id_by_key if not KEPT[k]["tag"].startswith("dup")]
    bad = []
    for k in planted:
        f = feats[k]
        ok = (f["donor_seq"][3:5] == "GT" and f["acceptor_seq"][18:20] == "AG" and f["donor_is_gt"] and f["acceptor_is_ag"]
              and f["upstream_donor_is_gt"] and f["downstream_acceptor_is_ag"]
              and f["bp_motif_found"] and 18 <= f["bp_distance"] <= 44 and f["bp_distance"] == 25
              and f["bp_motif"] == "TACTAAC" and f["bp_motif"].endswith("AC") and f["bp_position"] == 20
              and f["ppt_seq"][f["bp_position"]:f["bp_position"] + 7] == f["bp_motif"]
              and f["bp_score"] == 7 and f["ppt_score"] >= 0.9 and f["sequence_source"] == "fasta")
        if not ok:
            bad.append((KEPT[k]["tag"], f["donor_seq"], f["acceptor_seq"], f["bp_distance"], f["bp_motif"], f["bp_position"]))
    check("d. planted signals: donor[3:5]==GT, acceptor[18:20]==AG, flanking GT/AG, BP TACTAAC at -25 (bp_position 20, ppt[pos:pos+7]==motif), both strands",
          not bad, bad[:3], f"{len(planted)} planted events")
    n_plus = sum(1 for k in planted if id_by_key[k]["strand"] == "+")
    n_minus = len(planted) - n_plus
    check("d. planted events cover both strands", n_plus > 10 and n_minus > 10, {"+": n_plus, "-": n_minus})
    # sizes
    size_ok = all(feats[k]["exon_size"] == k[2] - k[1] for k in id_by_key)
    check("d. exon_size == exon_end - exon_start", size_ok)
    intron_ok = True
    for k, e in id_by_key.items():
        f = feats[k]
        if e["strand"] == "+":
            exp_up, exp_dn = e["exon_start"] - e["upstream_ee"], e["downstream_es"] - e["exon_end"]
        else:
            exp_up, exp_dn = e["downstream_es"] - e["exon_end"], e["exon_start"] - e["upstream_ee"]
        intron_ok &= (f["upstream_intron_size"], f["downstream_intron_size"]) == (exp_up, exp_dn)
    check("d. strand-aware intron sizes", intron_ok)
    # MANE annotation
    mane_bad = []
    for k in planted:
        f, e = feats[k], id_by_key[k]
        tag = KEPT[k]["tag"]
        gidx = int(tag.split("_")[0].lstrip("g"))
        g = GENES[gidx]
        if g["mane"]:
            ex_i = [i for i, x in enumerate(g["exons"]) if max(0, min(e["exon_end"], x[1]) - max(e["exon_start"], x[0])) > 0][0]
            L = g["exons"][ex_i][1] - g["exons"][ex_i][0]
            if "offset" in tag:
                L = e["exon_end"] - e["exon_start"]   # rMATS coords are used for the frame (extends 21 nt = 7 codons)
            exp_frame = "in_frame" if L % 3 == 0 else "frameshift"
            exp_rank = ex_i + 1 if g["strand"] == "+" else len(g["exons"]) - ex_i
            ok = (f["mane_transcript_id"] == g["tx_id"] and f["frame_class"] == exp_frame and f["frame_region"] == "CDS"
                  and f["cds_exon_length"] == L and f["exon_rank"] == exp_rank and f["mane_exon_source"] == "overlap")
        else:
            ok = f["mane_transcript_id"] is None and f["frame_class"] == "unknown" and f["mane_exon_source"] is None
        if not ok:
            mane_bad.append((tag, f["mane_transcript_id"], f["frame_class"], f["frame_region"], f["cds_exon_length"], f["exon_rank"], f["mane_exon_source"]))
    check("d. MANE: transcript id (MANE_Select, not Plus Clinical), frame_class by CDS len %3, exon_rank strand-aware, mane_exon_source 'overlap'; non-MANE genes unknown",
          not mane_bad, mane_bad[:4])
    g2 = GENES[2]
    k2 = next(k for k in planted if KEPT[k]["tag"].startswith("g2_ex3"))
    check("d. gene 2 uses ENST00000000002 (MANE_Select) although ENST00000000022 (Plus Clinical) is listed first",
          feats[k2]["mane_transcript_id"] == "ENST00000000002", feats[k2]["mane_transcript_id"])
    koff = next(k for k in planted if "offset" in KEPT[k]["tag"])
    check("d. rMATS exon offset from MANE (-12/+9) is corrected: GT/AG found, source overlap",
          feats[koff]["donor_is_gt"] and feats[koff]["acceptor_is_ag"] and feats[koff]["mane_exon_source"] == "overlap",
          (feats[koff]["donor_seq"], feats[koff]["acceptor_seq"][15:23], feats[koff]["mane_exon_source"]))
    kv = next(k for k in planted if KEPT[k]["tag"].startswith("g3_ex4"))
    check("d. versioned GeneID (ENSG…3.4) resolves in the MANE index", feats[kv]["mane_transcript_id"] == "ENST00000000003", feats[kv]["mane_transcript_id"])
    r = await c.get(f"/api/v1/splice/mane_transcript/{id_by_key[k2]['id']}")
    mt = r.json()
    check("d. GET /splice/mane_transcript: 8 exons of ENST00000000002 with strand/rank",
          mt["transcript_id"] == "ENST00000000002" and mt["n_exons"] == 8 and [(x["start"], x["end"]) for x in mt["exons"]] == [tuple(x) for x in g2["exons"]]
          and mt["strand"] == "-" and mt["exon_rank"] == feats[k2]["exon_rank"] and mt["skipped_start"] == k2[1],
          {k: mt[k] for k in ("transcript_id", "n_exons", "strand", "exon_rank")})
    a3_id = a3[0]["id"]
    r = await c.get(f"/api/v1/splice/feature/{a3_id}")
    check("d. feature on non-SE event returns error field (no crash)", r.status_code == 200 and "only available for SE" in (r.json().get("error") or ""),
          r.json().get("error"))
    r = await c.get(f"/api/v1/splice/mane_transcript/{a3_id}")
    check("d. mane_transcript on event without features -> empty structure", r.status_code == 200 and r.json()["transcript_id"] is None and r.json()["exons"] == [])
    r = await c.get("/api/v1/splice/feature/00000000-0000-0000-0000-000000000000")
    check("d. feature unknown event -> 404", r.status_code == 404, r.status_code)

    # ── e. patterns ──────────────────────────────────────────────────
    r = await c.get(f"/api/v1/splice/patterns/{aid}")
    pat = r.json()
    kept = EXP["kept_se"]
    n_sig05 = sum(1 for x in kept if x["fdr"] <= 0.05 and x["dpsi"] is not None and abs(x["dpsi"]) >= 0.05)
    check("e. patterns n_se_events / n_analyzed == kept SE", pat["n_se_events"] == pat["n_analyzed"] == EXP["n_se_kept"],
          (pat["n_se_events"], pat["n_analyzed"]), EXP["n_se_kept"])
    check("e. patterns n_significant (fdr<=0.05,|dpsi|>=0.05) computed independently", pat["n_significant"] == n_sig05 and
          pat["n_not_significant"] == EXP["n_se_kept"] - n_sig05, (pat["n_significant"], pat["n_not_significant"]), (n_sig05, EXP["n_se_kept"] - n_sig05))
    r = await c.get(f"/api/v1/splice/patterns/{aid}", params={"pvalue_threshold": 0.01})
    pat_p = r.json()
    n_sig05_p = sum(1 for x in kept if x["fdr"] <= 0.05 and x["dpsi"] is not None and abs(x["dpsi"]) >= 0.05 and x["p"] <= 0.01)
    check("e. patterns pvalue_threshold=0.01 reduces n_significant", pat_p["n_significant"] == n_sig05_p < pat["n_significant"],
          pat_p["n_significant"], n_sig05_p)
    d = pat["donor_sites"]
    check("e. donor: n_sequences, n_canonical, pct denominators", d["n_sequences"] == EXP["n_se_kept"] and d["n_canonical"] == n_gt
          and d["pct_canonical"] == round(n_gt / EXP["n_se_kept"] * 100, 1), (d["n_sequences"], d["n_canonical"], d["pct_canonical"]), (EXP["n_se_kept"], n_gt))
    check("e. donor PWM 9 positions, each summing to 1, G at pos 3 and T at pos 4 dominant",
          len(d["pwm"]) == 9 and all(abs(sum(p.values()) - 1) < 0.01 for p in d["pwm"]) and d["pwm"][3]["G"] >= 0.98 and d["pwm"][4]["T"] >= 0.98,
          (len(d["pwm"]), d["pwm"][3]["G"], d["pwm"][4]["T"]))
    a = pat["acceptor_sites"]
    check("e. acceptor PWM 23 positions, A at 18 / G at 19 dominant, consensus ends with AG+3",
          len(a["pwm"]) == 23 and a["pwm"][18]["A"] >= 0.98 and a["pwm"][19]["G"] >= 0.98 and a["consensus"][18:20] == "AG"
          and a["n_canonical"] == n_ag, (len(a["pwm"]), a["consensus"]))
    check("e. bp_found_pct == n_bp / n_with_ppt_seq", pat["bp_found_pct"] == round(n_bp / EXP["n_se_kept"] * 100, 1), pat["bp_found_pct"],
          round(n_bp / EXP["n_se_kept"] * 100, 1))
    check("e. frame counts match per-event features", pat["frame"] == {k: frame_counts.get(k, 0) for k in ("in_frame", "frameshift", "non_coding", "unknown")},
          pat["frame"], frame_counts)
    exp_frames = {"in_frame": 0, "frameshift": 0}
    for k in planted:
        tag = KEPT[k]["tag"]; g = GENES[int(tag.split("_")[0].lstrip("g"))]
        if g["mane"]:
            exp_frames["in_frame" if (k[2] - k[1]) % 3 == 0 else "frameshift"] += 1
    check("e. frame in_frame/frameshift == MANE genes' kept exons by length %3", pat["frame"]["in_frame"] == exp_frames["in_frame"]
          and pat["frame"]["frameshift"] == exp_frames["frameshift"], (pat["frame"]["in_frame"], pat["frame"]["frameshift"]), exp_frames)
    check("e. upstream/downstream flanking site stats present with 100% canonical",
          pat["upstream_donor_sites"]["pct_canonical"] == 100.0 and pat["downstream_acceptor_sites"]["pct_canonical"] == 100.0
          and pat["upstream_donor_sites"]["n_sequences"] == EXP["n_se_kept"],
          (pat["upstream_donor_sites"]["pct_canonical"], pat["downstream_acceptor_sites"]["pct_canonical"]))
    check("e. exon size stats", pat["exon_sizes"]["min"] == min(k[2] - k[1] for k in id_by_key) and pat["exon_sizes"]["max"] == max(k[2] - k[1] for k in id_by_key)
          and sum(b["count"] for b in pat["exon_sizes"]["distribution"]) == EXP["n_se_kept"], (pat["exon_sizes"]["min"], pat["exon_sizes"]["max"]))
    r = await c.get(f"/api/v1/splice/patterns/{aid}", params={"pvalue_threshold": 2})
    check("e. patterns pvalue_threshold out of range -> 422", r.status_code == 422, r.status_code)

    # ── i. concurrency / claim logic ─────────────────────────────────
    r1, r2 = await asyncio.gather(c.post(f"/api/v1/splice/compute/{aid}"), c.post(f"/api/v1/splice/compute/{aid}"))
    msgs = sorted([r1.json()["message"], r2.json()["message"]])
    check("i. two concurrent POST /splice/compute: one starts, one 'already in progress'",
          r1.status_code == r2.status_code == 202 and sum("already in progress" in m for m in msgs) == 1, msgs)
    while not (await c.get(f"/api/v1/splice/progress/{aid}")).json()["done"]:
        await asyncio.sleep(0.3)
    check("i. after re-run compute_status 'done' (psql)", psql(f"select compute_status from analyses where id='{aid}'") == "done")
    psql(f"update analyses set compute_status='running', compute_error=null, updated_at=now() where id='{aid}'")
    r = await c.post(f"/api/v1/splice/compute/{aid}")
    check("i. fresh 'running' row is not re-claimed", "already in progress" in r.json()["message"] and
          psql(f"select compute_status from analyses where id='{aid}'") == "running", r.json()["message"])
    r = await c.get(f"/api/v1/splice/progress/{aid}")
    check("i. progress while running reports status 'running' (done=True only because all features exist)", r.json()["status"] == "running", r.json())
    r = await c.get(f"/api/v1/export/{aid}/pdf", params={"sections": "a"})
    check("i. export while running with all features computed -> allowed (200)", r.status_code == 200, r.status_code)
    psql(f"delete from event_splice_feature where event_id in (select id from splicing_events where analysis_id='{aid}' and event_type='SE') and event_id = (select id from splicing_events where analysis_id='{aid}' and event_type='SE' limit 1)")
    r = await c.get(f"/api/v1/export/{aid}/pdf", params={"sections": "a"})
    check("i. export while running with incomplete features -> 409", r.status_code == 409, (r.status_code, r.json().get("detail", "")[:80]))
    psql(f"update analyses set updated_at=now() - interval '31 minutes' where id='{aid}'")
    r = await c.post(f"/api/v1/splice/compute/{aid}")
    check("i. stale 'running' row (heartbeat > 30 min) is re-claimed", "started" in r.json()["message"].lower(), r.json()["message"])
    while not (await c.get(f"/api/v1/splice/progress/{aid}")).json()["done"]:
        await asyncio.sleep(0.3)
    st = psql(f"select compute_status, compute_error is null, (now()-updated_at) < interval '1 minute' from analyses where id='{aid}'").replace("True", "t").replace("False", "f")
    check("i. re-claimed run finished: status done, no error, heartbeat refreshed (psql)", st == "done|t|t", st)
    n_feat = int(psql(f"select count(*) from event_splice_feature where event_id in (select id from splicing_events where analysis_id='{aid}')"))
    check("i. all SE features present again after re-run", n_feat == EXP["n_se_kept"], n_feat, EXP["n_se_kept"])
    cs = psql("select distinct compute_status from analyses")
    check("i. compute_status column values in DB are within the allowed set", set(cs.split("\n")) <= {"idle", "running", "done", "error"}, cs)

    # ── f. deep analyses ─────────────────────────────────────────────
    r = await c.post(f"/api/v1/analyses/{aid}/deep-analyses", json={"fdr_threshold": 0.05, "delta_psi_min": 0.1, "permutation_iterations": 200})
    check("f. POST deep-analyses -> 201", r.status_code == 201, r.status_code)
    d1 = r.json()
    check("f. n_significant (fdr 0.05, dpsi 0.1) == independent expectation", d1["n_significant"] == EXP["n_sig_fdr05_dpsi01"] and
          d1["n_significant"] + d1["n_not_significant"] == EXP["event_count"], (d1["n_significant"], d1["n_not_significant"]), EXP["n_sig_fdr05_dpsi01"])
    check("f. permutation_iterations recorded, pvalue_threshold null, auto-name has gene+FDR",
          d1["permutation_iterations"] == 200 and d1["pvalue_threshold"] is None and d1["name"].startswith("GENE1-FDR0.05"), d1["name"])
    r = await c.post(f"/api/v1/analyses/{aid}/deep-analyses", json={"fdr_threshold": 0.05, "delta_psi_min": 0.1, "pvalue_threshold": 0.01, "permutation_iterations": 200})
    d2 = r.json()
    check("f. pvalue_threshold 0.01 reduces n_significant", d2["n_significant"] == EXP["n_sig_fdr05_dpsi01_p001"] < d1["n_significant"],
          d2["n_significant"], EXP["n_sig_fdr05_dpsi01_p001"])
    did = d2["id"]
    r = await c.get(f"/api/v1/analyses/{aid}/deep-analyses")
    check("f. list deep analyses (newest first)", [x["id"] for x in r.json()] == [d2["id"], d1["id"]], len(r.json()))
    r = await c.get(f"/api/v1/deep-analyses/{did}")
    check("f. GET deep analysis detail", r.status_code == 200 and r.json()["pvalue_threshold"] == 0.01)
    r = await c.get(f"/api/v1/deep-analyses/{did}/events", params={"page_size": 5})
    pg = r.json()
    check("f. deep events page_size=5 pagination", len(pg["items"]) == 5 and pg["total"] == EXP["event_count"] and pg["pages"] == math.ceil(EXP["event_count"] / 5)
          and pg["page"] == 1, (len(pg["items"]), pg["total"], pg["pages"]))
    r = await c.get(f"/api/v1/deep-analyses/{did}/events", params={"page_size": 5, "page": pg["pages"]})
    check("f. deep events last page item count", len(r.json()["items"]) == EXP["event_count"] - 5 * (pg["pages"] - 1), len(r.json()["items"]))
    r = await c.get(f"/api/v1/deep-analyses/{did}/events", params={"significant": "true", "page_size": 500})
    check("f. deep events significant=true total == n_significant", r.json()["total"] == d2["n_significant"], r.json()["total"], d2["n_significant"])
    fdrs = [e["fdr"] for e in r.json()["items"]]
    check("f. deep events ordered by FDR asc", fdrs == sorted(fdrs))
    r = await c.get(f"/api/v1/deep-analyses/{did}/pattern-comparison")
    pc = r.json()
    tests = pc["statistical_tests"]
    check("f. pattern-comparison: 20 statistical tests", len(tests) == 20, len(tests), 20)
    check("f. pattern-comparison: 7 _mwu entries, q_value key present on all, significant_fdr bool",
          sum(t["feature"].endswith("_mwu") for t in tests) == 7 and all("q_value" in t and isinstance(t["significant_fdr"], bool) for t in tests),
          [(t["feature"], t["p_value"], t["q_value"]) for t in tests][:4])
    check("f. pattern-comparison group sizes == SE sig / non-sig", pc["significant"]["n_events"] == EXP["n_se_sig_p001"] and
          pc["not_significant"]["n_events"] == EXP["n_se_kept"] - EXP["n_se_sig_p001"], (pc["significant"]["n_events"], pc["not_significant"]["n_events"]),
          (EXP["n_se_sig_p001"], EXP["n_se_kept"] - EXP["n_se_sig_p001"]))
    offenders = [(t["feature"], t["p_value"], t["q_value"]) for t in tests
                 if t["p_value"] is not None and not (0 <= t["p_value"] <= 1 and t["q_value"] >= t["p_value"] - 5e-7)]
    check("f. pattern-comparison: p in [0,1] where present, q >= p (q rounded to 6 dp)", not offenders, offenders)
    # blocked-network annotation endpoints must degrade gracefully
    r = await c.get("/api/v1/annotations/gene/GENE1", params={"ensembl_id": "ENSG00000000001"})
    check("x. GET /annotations/gene (network blocked): 200 with empty panels/GO/None protein", r.status_code == 200 and r.json()["panels"] == []
          and r.json()["go_terms"] == [] and r.json()["protein_function"] is None, (r.status_code, r.json() if r.status_code == 200 else r.text[:100]))
    r = await c.get("/api/v1/annotations/interactions", params={"gene_a": "GENE1", "gene_b": "GENE2"})
    check("x. GET /annotations/interactions (network blocked): 200 dict, no exception", r.status_code == 200 and isinstance(r.json(), dict),
          (r.status_code, str(r.json())[:120]))
    r = await c.get("/api/v1/genes/search", params={"q": "GENE"})
    check("x. GET /genes/search (network blocked): 200 with empty results", r.status_code == 200 and r.json()["results"] == [], (r.status_code, r.text[:100]))
    r = await c.get("/api/v1/genes/lookup/GENE1")
    check("x. GET /genes/lookup (network blocked): 404 not found (no 500)", r.status_code == 404, (r.status_code, r.text[:100]))
    r = await c.get(f"/api/v1/splice/patterns/{aid}", params={"deep_analysis_id": did})
    check("e/f. patterns with deep_analysis_id restricts to significant SE + uses DA counts",
          r.status_code == 200 and r.json()["n_se_events"] == EXP["n_se_sig_p001"] and r.json()["n_significant"] == d2["n_significant"],
          (r.json().get("n_se_events"), r.json().get("n_significant")))
    r = await c.get(f"/api/v1/deep-analyses/{did}/hnrnp-motifs")
    hn = r.json()
    check("f. hnrnp-motifs: background job finished within the default long-poll (status done, elapsed reported)",
          r.status_code == 200 and hn["status"] == "done" and isinstance(hn.get("elapsed_seconds"), (int, float)),
          (r.status_code, hn.get("status"), hn.get("stage"), hn.get("error")))
    r2 = await c.get(f"/api/v1/deep-analyses/{did}/hnrnp-motifs", params={"wait": 0})
    check("f. hnrnp-motifs: second call served from the job cache (same rows, no wait)",
          r2.status_code == 200 and r2.json()["results"] == hn["results"], r2.status_code)
    check("f. hnrnp-motifs: regions list has 7 names", hn["regions"] == ["upstream_exon", "upstream_intron_5ss", "upstream_intron_3ss", "skipped_exon",
                                                                        "downstream_intron_5ss", "downstream_intron_3ss", "downstream_exon"], hn["regions"])
    check("f. hnrnp-motifs: 133 result rows (19 motifs x 7 regions)", len(hn["results"]) == 133, len(hn["results"]), 133)
    check("f. hnrnp-motifs: group sizes", hn["n_sig_events"] == EXP["n_se_sig_p001"] and hn["n_bg_events"] == EXP["n_se_kept"] - EXP["n_se_sig_p001"],
          (hn["n_sig_events"], hn["n_bg_events"]))
    rr = hn["results"]
    check("f. hnrnp-motifs: density fields are floats in [0,1], totals == group sizes, p/q None-or-[0,1]",
          all(isinstance(x["sig_density"], float) and 0 <= x["sig_density"] <= 1 and 0 <= x["bg_density"] <= 1 and x["sig_total"] == hn["n_sig_events"]
              and x["bg_total"] == hn["n_bg_events"] and (x["p_value"] is None or 0 <= x["p_value"] <= 1)
              and (x["density_p_value"] is None or 0 <= x["density_p_value"] <= 1) for x in rr),
          {k: rr[0][k] for k in ("motif_name", "region", "sig_density", "bg_density", "p_value", "density_p_value", "regulatory_effect")})
    check("f. hnrnp-motifs: motifs actually hit (some densities > 0)", any(x["sig_density"] > 0 for x in rr))
    # tiny group: no exception
    r = await c.post(f"/api/v1/analyses/{aid}/deep-analyses", json={"fdr_threshold": 1e-9, "delta_psi_min": 0.1})
    dtiny = r.json()
    r = await c.get(f"/api/v1/deep-analyses/{dtiny['id']}/pattern-comparison")
    check("f. pattern-comparison with 0 significant events: 200, tests present with None p-values",
          r.status_code == 200 and len(r.json()["statistical_tests"]) == 20 and all(t["p_value"] is None for t in r.json()["statistical_tests"]),
          (r.status_code, dtiny["n_significant"]))
    r = await c.get(f"/api/v1/deep-analyses/{dtiny['id']}/hnrnp-motifs")
    check("f. hnrnp-motifs with 0 significant events: 200, 133 rows, None stats", r.status_code == 200 and len(r.json()["results"]) == 133
          and all(x["p_value"] is None for x in r.json()["results"]), r.status_code)
    r = await c.get(f"/api/v1/deep-analyses/{dtiny['id']}/enrichr")
    check("f. enrichr with network blocked: graceful (200, error string or no genes)", r.status_code == 200 and (r.json()["error"] or r.json()["terms"] == []),
          (r.json().get("n_genes_submitted"), (r.json().get("error") or "")[:60]))
    r = await c.get(f"/api/v1/deep-analyses/{did}/enrichr")
    # Network-agnostic: without network Enrichr must degrade to an error string;
    # with network the synthetic gene names yield a (possibly empty) term list.
    j = r.json()
    check("f. enrichr (genes submitted): 200, genes counted, and either an error string (offline) or a term list (online)",
          r.status_code == 200 and j.get("n_genes_submitted", 0) > 0 and (bool(j.get("error")) or isinstance(j.get("terms"), list)),
          (j.get("n_genes_submitted"), (j.get("error") or "")[:80], len(j.get("terms") or [])))
    r = await c.delete(f"/api/v1/deep-analyses/{dtiny['id']}")
    check("f. DELETE deep analysis -> 204 then 404", r.status_code == 204 and (await c.get(f"/api/v1/deep-analyses/{dtiny['id']}")).status_code == 404)
    # permutation
    r = await c.post(f"/api/v1/splice/permutation/{aid}", params={"n_iterations": 100, "fdr_threshold": 0.05, "delta_psi_min": 0.1})
    pm = r.json()
    check("f. permutation: exact_fraction 1.0, min_p_attainable 0.05, 3v3", pm["exact_fraction"] == 1.0 and pm["min_p_attainable"] == 0.05
          and pm["n_replicates_g1"] == 3 and pm["n_replicates_g2"] == 3, {k: pm[k] for k in ("exact_fraction", "min_p_attainable", "n_replicates_g1", "n_replicates_g2", "n_iterations")})
    ev3 = [e for e in pm["events"] if e["n1"] == 3 and e["n2"] == 3]
    ev2 = [e for e in pm["events"] if (e["n1"], e["n2"]) == (2, 3)]
    check("f. permutation: n_splits 20 for 3v3 events, 10 for the 3 NA-replicate (2v3) events, all exact",
          all(e["n_splits"] == 20 and e["exact"] for e in ev3) and len(ev2) == 3 and all(e["n_splits"] == 10 for e in ev2),
          (len(ev3), len(ev2), sorted({e["n_splits"] for e in pm["events"]})))
    check("f. permutation: n_total_events == kept SE, n_events_tested == SE sig (fdr .05, dpsi .1), p >= 1/n_splits",
          pm["n_total_events"] == EXP["n_se_kept"] and pm["n_events_tested"] == EXP["n_se_sig"]
          and all(e["empirical_p_value"] >= 1 / e["n_splits"] - 1e-12 for e in pm["events"]),
          (pm["n_total_events"], pm["n_events_tested"]), (EXP["n_se_kept"], EXP["n_se_sig"]))
    check("f. permutation: pct_p05 present, histograms non-empty, metric_results present",
          pm["pct_p05"] is not None and len(pm["global_null_hist_bins"]) > 0 and len(pm["observed_hist_counts"]) > 0 and len(pm["metric_results"]) > 0,
          (pm["pct_p05"], pm["pct_p01"], len(pm["metric_results"])))
    r = await c.post(f"/api/v1/splice/permutation/{aid}", params={"n_iterations": 100, "fdr_threshold": 0.05, "delta_psi_min": 0.1, "pvalue_threshold": 0.01})
    check("f. permutation with pvalue_threshold narrows n_events_tested", r.json()["n_events_tested"] == EXP["n_se_sig_p001"], r.json()["n_events_tested"], EXP["n_se_sig_p001"])

    # ── g. exports ────────────────────────────────────────────────────
    r = await c.get(f"/api/v1/export/{aid}/deep-analysis/{did}/excel", params={"include": "core"})
    check("g. excel export 200 + xlsx content-type", r.status_code == 200 and "spreadsheetml" in r.headers.get("content-type", ""),
          (r.status_code, r.headers.get("content-type")))
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(r.content))
    ws = wb[wb.sheetnames[0]]
    headers = [c_.value for c_ in ws[1]]
    check("g. excel headers include core columns", {"FDR", "p-value", "ΔΨ", "|ΔΨ|"} <= set(headers), headers[:14])
    check("g. excel rows == n_significant of the deep analysis", ws.max_row - 1 == d2["n_significant"], ws.max_row - 1, d2["n_significant"])
    open(os.path.join(HERE, "deep.xlsx"), "wb").write(r.content)
    r = await c.get(f"/api/v1/export/{aid}/deep-analysis/{did}/excel", params={"include": "core,bogus"})
    check("g. excel unknown include group -> 422", r.status_code == 422, r.status_code)
    t0 = time.time()
    r = await c.get(f"/api/v1/export/{aid}/deep-analysis/{did}/pdf", params={"sections": "a,b,c,d,e,top_events"})
    check("g. deep-analysis PDF (a,b,c,d,e,top_events): 200, %PDF header, > 20 kB", r.status_code == 200 and r.content[:5] == b"%PDF-" and len(r.content) > 20_000,
          (r.status_code, r.content[:8], len(r.content), f"{time.time() - t0:.1f}s"))
    open(os.path.join(HERE, "deep.pdf"), "wb").write(r.content)
    r = await c.get(f"/api/v1/export/{aid}/pdf", params={"sections": "a,top_events"})
    check("g. analysis PDF (a,top_events): 200, %PDF header, > 20 kB", r.status_code == 200 and r.content[:5] == b"%PDF-" and len(r.content) > 20_000,
          (r.status_code, r.content[:8], len(r.content)))
    open(os.path.join(HERE, "analysis.pdf"), "wb").write(r.content)
    check("g. PDF ends with %%EOF", b"%%EOF" in r.content[-64:])

    # ── h. delete ─────────────────────────────────────────────────────
    r = await c.delete(f"/api/v1/analyses/{aid}")
    check("h. DELETE /analyses/{id} -> 204", r.status_code == 204, r.status_code)
    t0 = time.time()
    while time.time() - t0 < 30:
        r = await c.get(f"/api/v1/analyses/{aid}")
        if r.status_code == 404:
            break
        await asyncio.sleep(0.5)
    check("h. GET after background delete -> 404", r.status_code == 404, r.status_code)
    left = psql(f"select (select count(*) from splicing_events where analysis_id='{aid}')||'|'||(select count(*) from deep_analyses where analysis_id='{aid}')"
                f"||'|'||(select count(*) from event_splice_feature f join splicing_events e on e.id=f.event_id where e.analysis_id='{aid}')"
                f"||'|'||(select count(*) from deep_analysis_events x join deep_analyses d on d.id=x.deep_analysis_id where d.analysis_id='{aid}')"
                f"||'|'||(select count(*) from sample_groups where analysis_id='{aid}')")
    check("h. child rows removed (events|deep|features|dae|groups)", left == "0|0|0|0|0", left)
    r = await c.delete(f"/api/v1/analyses/{aid}")
    check("h. DELETE again -> 404", r.status_code == 404, r.status_code)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception:
        traceback.print_exc()
        RESULTS.append({"name": "UNHANDLED EXCEPTION", "pass": False, "observed": traceback.format_exc()[-800:]})
    json.dump(RESULTS, open(os.path.join(HERE, "results.json"), "w"), indent=1, default=str)
    n_fail = sum(1 for r in RESULTS if not r["pass"])
    for r in RESULTS:
        if not r["pass"]:
            print(f"  FAILED: {r['name']} | observed={str(r.get('observed'))[:200]} | expected={str(r.get('expected'))[:120]}")
    print(f"\n{len(RESULTS) - n_fail}/{len(RESULTS)} assertions passed, {n_fail} failed")
    sys.exit(1 if n_fail else 0)
