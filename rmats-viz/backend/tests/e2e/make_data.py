#!/usr/bin/env python3
"""Synthetic genome + MANE GFF3 + rMATS-turbo files for the end-to-end run.

Everything is deterministic (seed 42).  Writes into the directory given as
argv[1] (default: cwd):
  genome.fa (+ .fai)            chr1 200 kb, chr2 12 kb, chr10 12 kb
  MANE.GRCh38.ensembl_genomic.gff.gz
  SE.MATS.JC.txt / SE.MATS.JCEC.txt / A3SS.MATS.JC.txt / A5SS.MATS.JC.txt /
  RI.MATS.JC.txt / MXE.MATS.JC.txt / summary.txt (empty)
  expected.json                 independently computed expectations
"""
from __future__ import annotations

import gzip
import json
import os
import random
import sys

import pysam

OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(OUT, exist_ok=True)
rng = random.Random(42)

CHR_LEN = {"chr1": 200_000, "chr2": 12_000, "chr10": 12_000}
genome = {c: bytearray(rng.choice(b"ACGT") for _ in range(n)) for c, n in CHR_LEN.items()}


def rc(s: str) -> str:
    return s.translate(str.maketrans("ACGT", "TGCA"))[::-1]


def plant(chrom: str, es: int, ee: int, strand: str) -> None:
    """Plant canonical splice signals around exon [es, ee) (0-based half-open).

    + strand: ...PPT(47, pyrimidine, TACTAAC branch at -25)..C AG [exon] GTAAGT...
    - strand: the mirror image (reverse complement) so that, after RC, the
      transcript-oriented windows read exactly like the + strand ones.
    """
    g = genome[chrom]
    if strand == "+":
        ppt = "".join(rng.choice("CT") for _ in range(47))
        ppt = ppt[:20] + "TACTAAC" + ppt[27:]          # 7-mer at ppt index 20 -> branch A 25 nt from exon
        g[es - 50:es - 3] = ppt.encode()
        g[es - 3:es] = b"CAG"
        g[ee:ee + 6] = b"GTAAGT"
    else:
        ppt = "".join(rng.choice("CT") for _ in range(47))
        ppt = ppt[:20] + "TACTAAC" + ppt[27:]
        g[ee + 3:ee + 50] = rc(ppt).encode()          # genomic [ee+3, ee+50) RC'd = ppt in transcript sense
        g[ee:ee + 3] = rc("CAG").encode()             # "CTG"
        g[es - 6:es] = rc("GTAAGT").encode()          # "ACTTAC"


# ---------------------------------------------------------------------------
# Genes
# ---------------------------------------------------------------------------
genes: list[dict] = []


def add_gene(idx: int, chrom: str, strand: str, start: int, exon_lens: list[int], intron_lens: list[int],
             gene_id: str | None = None, symbol: str | None = None) -> dict:
    exons = []
    pos = start
    for i, L in enumerate(exon_lens):
        exons.append((pos, pos + L))
        pos += L
        if i < len(intron_lens):
            pos += intron_lens[i]
    for es, ee in exons:
        plant(chrom, es, ee, strand)
    gd = {
        "idx": idx,
        "gene_id": gene_id or f"ENSG{idx:011d}",
        "symbol": symbol or f"GENE{idx}",
        "chr": chrom, "strand": strand, "exons": exons,
        "tx_id": f"ENST{idx:011d}",
    }
    genes.append(gd)
    return gd


# 10 genes on chr1 (19.5 kb slots), 8 exons each; exon lengths mix of %3==0 / !=0
EXON_LEN_SETS = [
    [150, 120, 100, 93, 121, 87, 110, 200],
    [140, 99, 130, 121, 96, 88, 101, 180],
    [160, 111, 127, 90, 134, 97, 123, 210],
]
for k in range(10):
    strand = "+" if k % 2 == 0 else "-"
    if k == 1:
        strand = "-"
    lens = EXON_LEN_SETS[k % 3]
    introns = [rng.randint(1400, 2100) for _ in range(7)]
    gid = f"ENSG{k + 1:011d}"
    if k == 2:
        gid += ".4"            # versioned GeneID (as produced by GENCODE GTFs)
    add_gene(k + 1, "chr1", strand, 1000 + k * 19_500, lens, introns, gene_id=gid)
# one gene on chr2 (+) and chr10 (-): 3 exons -> 1 SE event each (Manhattan ordering test)
add_gene(11, "chr2", "+", 2000, [120, 96, 150], [1500, 1600])
add_gene(12, "chr10", "-", 2000, [130, 101, 140], [1450, 1700])

# ---------------------------------------------------------------------------
# FASTA
# ---------------------------------------------------------------------------
fa_path = os.path.join(OUT, "genome.fa")
with open(fa_path, "w") as fh:
    for c in ("chr1", "chr2", "chr10"):
        fh.write(f">{c}\n")
        s = genome[c].decode()
        for i in range(0, len(s), 60):
            fh.write(s[i:i + 60] + "\n")
if os.path.exists(fa_path + ".fai"):
    os.remove(fa_path + ".fai")
pysam.faidx(fa_path)

# ---------------------------------------------------------------------------
# MANE GFF3 for genes 1-3 (gene 2 has a MANE_Plus_Clinical transcript listed FIRST)
# ---------------------------------------------------------------------------
MANE_GENES = {1, 2, 3}
CDS_START_OFFSET = 30   # CDS starts 30 nt into the first exon (transcript sense)
CDS_END_OFFSET = 40     # CDS ends 40 nt before the end of the last exon


def cds_intervals(gd: dict, exons: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Genomic CDS segments: from 30 nt into the first (transcript) exon to 40 nt before the last."""
    if gd["strand"] == "+":
        cds_lo = exons[0][0] + CDS_START_OFFSET
        cds_hi = exons[-1][1] - CDS_END_OFFSET
    else:
        cds_hi = exons[-1][1] - CDS_START_OFFSET   # first transcript exon = genomic last
        cds_lo = exons[0][0] + CDS_END_OFFSET
    out = []
    for es, ee in exons:
        lo, hi = max(es, cds_lo), min(ee, cds_hi)
        if hi > lo:
            out.append((lo, hi))
    return out


def gff_transcript_lines(gd: dict, tx_id: str, exons: list[tuple[int, int]], tag: str) -> list[str]:
    gid = gd["gene_id"].split(".")[0]
    c, st = gd["chr"], gd["strand"]
    lines = [
        f"{c}\t.\ttranscript\t{exons[0][0] + 1}\t{exons[-1][1]}\t.\t{st}\t.\t"
        f"ID={tx_id}.1;Parent={gid}.1;gene_id={gid}.1;transcript_id={tx_id}.1;gene_type=protein_coding;"
        f"gene_name={gd['symbol']};transcript_type=protein_coding;transcript_name={gd['symbol']}-201;tag={tag}"
    ]
    for n, (es, ee) in enumerate(exons, start=1):
        lines.append(
            f"{c}\t.\texon\t{es + 1}\t{ee}\t.\t{st}\t.\t"
            f"ID=exon:{tx_id}.1:{n};Parent={tx_id}.1;gene_id={gid}.1;transcript_id={tx_id}.1;exon_number={n}"
        )
    for (lo, hi) in cds_intervals(gd, exons):
        lines.append(
            f"{c}\t.\tCDS\t{lo + 1}\t{hi}\t.\t{st}\t0\t"
            f"ID=CDS:{tx_id}.1;Parent={tx_id}.1;gene_id={gid}.1;transcript_id={tx_id}.1"
        )
    return lines


gff_lines = ["##gff-version 3", "#!MANE synthetic test file"]
plus_clinical_exons: dict[int, list] = {}
for gd in genes:
    if gd["idx"] not in MANE_GENES:
        continue
    gid = gd["gene_id"].split(".")[0]
    ex = gd["exons"]
    gff_lines.append(
        f"{gd['chr']}\t.\tgene\t{ex[0][0] + 1}\t{ex[-1][1]}\t.\t{gd['strand']}\t.\t"
        f"ID={gid}.1;gene_id={gid}.1;gene_type=protein_coding;gene_name={gd['symbol']}"
    )
    if gd["idx"] == 2:
        # MANE Plus Clinical transcript FIRST: skips exon 5 (index 4) so its structure differs
        pc_exons = ex[:4] + ex[5:]
        plus_clinical_exons[2] = pc_exons
        gff_lines += gff_transcript_lines(gd, "ENST00000000022", pc_exons, "MANE_Plus_Clinical")
    gff_lines += gff_transcript_lines(gd, gd["tx_id"], ex, "MANE_Select")
with gzip.open(os.path.join(OUT, "MANE.GRCh38.ensembl_genomic.gff.gz"), "wt") as fh:
    fh.write("\n".join(gff_lines) + "\n")

# ---------------------------------------------------------------------------
# rMATS files
# ---------------------------------------------------------------------------
SE_HEADER = ("ID\tGeneID\tgeneSymbol\tchr\tstrand\texonStart_0base\texonEnd\tupstreamES\tupstreamEE\t"
             "downstreamES\tdownstreamEE\tID\tIJC_SAMPLE_1\tSJC_SAMPLE_1\tIJC_SAMPLE_2\tSJC_SAMPLE_2\t"
             "IncFormLen\tSkipFormLen\tPValue\tFDR\tIncLevel1\tIncLevel2\tIncLevelDifference")
ALT_HEADER = ("ID\tGeneID\tgeneSymbol\tchr\tstrand\tlongExonStart_0base\tlongExonEnd\tshortES\tshortEE\t"
              "flankingES\tflankingEE\tID\tIJC_SAMPLE_1\tSJC_SAMPLE_1\tIJC_SAMPLE_2\tSJC_SAMPLE_2\t"
              "IncFormLen\tSkipFormLen\tPValue\tFDR\tIncLevel1\tIncLevel2\tIncLevelDifference")
RI_HEADER = ("ID\tGeneID\tgeneSymbol\tchr\tstrand\triExonStart_0base\triExonEnd\tupstreamES\tupstreamEE\t"
             "downstreamES\tdownstreamEE\tID\tIJC_SAMPLE_1\tSJC_SAMPLE_1\tIJC_SAMPLE_2\tSJC_SAMPLE_2\t"
             "IncFormLen\tSkipFormLen\tPValue\tFDR\tIncLevel1\tIncLevel2\tIncLevelDifference")
MXE_HEADER = ("ID\tGeneID\tgeneSymbol\tchr\tstrand\t1stExonStart_0base\t1stExonEnd\t2ndExonStart_0base\t2ndExonEnd\t"
              "upstreamES\tupstreamEE\tdownstreamES\tdownstreamEE\tID\tIJC_SAMPLE_1\tSJC_SAMPLE_1\tIJC_SAMPLE_2\t"
              "SJC_SAMPLE_2\tIncFormLen\tSkipFormLen\tPValue\tFDR\tIncLevel1\tIncLevel2\tIncLevelDifference")


def psi_str(vals: list[float | None]) -> str:
    return ",".join("NA" if v is None else f"{v:.3f}" for v in vals)


def cnt_str(vals: list[int | None]) -> str:
    return ",".join("NA" if v is None else str(v) for v in vals)


def stats_block(kind: str, ijc1, sjc1, ijc2, sjc2, p, fdr, fdr_text=None, p_text=None) -> tuple[str, dict]:
    """Return the tab-joined count/stat columns and a dict of the parsed expectations."""
    psi1 = [None if (i is None or s is None) else round(i / (i + s), 3) for i, s in zip(ijc1, sjc1)]
    psi2 = [None if (i is None or s is None) else round(i / (i + s), 3) for i, s in zip(ijc2, sjc2)]
    m1 = sum(v for v in psi1 if v is not None) / len([v for v in psi1 if v is not None])
    m2 = sum(v for v in psi2 if v is not None) / len([v for v in psi2 if v is not None])
    diff = round(m1 - m2, 3)
    cols = "\t".join([
        cnt_str(ijc1), cnt_str(sjc1), cnt_str(ijc2), cnt_str(sjc2), "99", "50",
        p_text if p_text is not None else f"{p:g}", fdr_text if fdr_text is not None else f"{fdr:g}",
        psi_str(psi1), psi_str(psi2), f"{diff:g}",
    ])
    cov1 = [i + s for i, s in zip(ijc1, sjc1) if i is not None and s is not None]
    cov2 = [i + s for i, s in zip(ijc2, sjc2) if i is not None and s is not None]
    meta = {
        "p": p, "fdr": fdr, "dpsi": diff,
        "mean_cov1": sum(cov1) / len(cov1) if cov1 else None,
        "mean_cov2": sum(cov2) / len(cov2) if cov2 else None,
    }
    return cols, meta


def counts(inc_high: bool, lo: int = 30, hi: int = 90):
    """3 replicates per group; inc_high -> group 1 mostly inclusion."""
    ijc1 = [rng.randint(lo, hi) for _ in range(3)]
    sjc1 = [rng.randint(lo, hi) for _ in range(3)]
    ijc2 = [rng.randint(lo, hi) for _ in range(3)]
    sjc2 = [rng.randint(lo, hi) for _ in range(3)]
    if inc_high:
        ijc1 = [v + 60 for v in ijc1]; sjc2 = [v + 60 for v in sjc2]
    else:
        sjc1 = [v + 60 for v in sjc1]; ijc2 = [v + 60 for v in ijc2]
    return ijc1, sjc1, ijc2, sjc2


se_rows: list[dict] = []   # each: dict(cols..., meta)
rid = 0


def se_row(gd, es, ee, ues, uee, des, dee, p, fdr, *, sig=True, na_rep=None, low_cov=False, all_na=False,
           fdr_text=None, p_text=None, tag=""):
    global rid
    rid += 1
    ijc1, sjc1, ijc2, sjc2 = counts(inc_high=(rid % 2 == 0))
    if not sig:  # small difference between groups
        ijc1, sjc1, ijc2, sjc2 = counts(inc_high=True)
        ijc2 = [v + 60 for v in ijc2]; sjc1 = [v + 60 for v in sjc1]
    if low_cov:
        ijc2 = [3, 4, 2]; sjc2 = [2, 3, 5]      # mean cov group 2 = 6.3 < 10
    if na_rep is not None:
        ijc1[na_rep] = None; sjc1[na_rep] = None
    if all_na:
        ijc1 = [None, None, None]; sjc1 = [None, None, None]
    if all_na:
        # IncLevel1 would be all NA -> stats_block cannot average; use explicit strings
        cols = "\t".join([cnt_str(ijc1), cnt_str(sjc1), cnt_str(ijc2), cnt_str(sjc2), "99", "50",
                          f"{p:g}", f"{fdr:g}", "NA,NA,NA", psi_str([round(i / (i + s), 3) for i, s in zip(ijc2, sjc2)]), "NA"])
        meta = {"p": p, "fdr": fdr, "dpsi": None, "mean_cov1": None,
                "mean_cov2": sum(i + s for i, s in zip(ijc2, sjc2)) / 3}
    else:
        cols, meta = stats_block("SE", ijc1, sjc1, ijc2, sjc2, p, fdr, fdr_text, p_text)
    line = "\t".join([str(rid), f'"{gd["gene_id"]}"', f'"{gd["symbol"]}"', gd["chr"], gd["strand"],
                      str(es), str(ee), str(ues), str(uee), str(des), str(dee), str(rid), cols])
    row = dict(line=line, id=rid, gene=gd["gene_id"], symbol=gd["symbol"], chr=gd["chr"], strand=gd["strand"],
               es=es, ee=ee, ues=ues, uee=uee, des=des, dee=dee, tag=tag, **meta)
    se_rows.append(row)
    return row


# significance pattern: cycle through (p, fdr) tuples
SIG_STATS = [(1e-6, 1e-5), (0.0005, 0.004), (0.02, 0.04), (0.001, 0.02)]      # FDR < 0.05
NS_STATS = [(0.3, 0.6), (0.08, 0.2), (0.6, 0.9), (0.15, 0.35)]                 # FDR >= 0.05

base_events: list[dict] = []
n_se = 0
for gd in genes:
    ex = gd["exons"]
    internal = range(1, len(ex) - 1)
    for i in internal:
        es, ee = ex[i]
        ues, uee = ex[i - 1]
        des, dee = ex[i + 1]
        n_se += 1
        sig = (n_se % 3 != 0)          # 2/3 significant
        p, fdr = (SIG_STATS if sig else NS_STATS)[n_se % 4]
        kw = {}
        tag = f"g{gd['idx']}_ex{i + 1}"
        if gd["idx"] == 1 and i == 4:
            # rMATS coordinates offset from the MANE exon (start -12, end +9) -> MANE correction
            es, ee = es - 12, ee + 9
            tag += "_offset"
        if n_se in (7, 19, 31):
            kw["na_rep"] = n_se % 3       # one NA replicate in group 1 (still >= 10X on the others)
            tag += "_na"
        if n_se == 13:
            kw["fdr_text"], kw["p_text"] = "0,03", "0,002"    # decimal comma
            p, fdr = 0.002, 0.03
            tag += "_comma"
        if n_se in (10, 22, 40):
            kw["low_cov"] = True; tag += "_lowcov"
        if n_se == 28:
            kw["all_na"] = True; tag += "_allna"
        row = se_row(gd, es, ee, ues, uee, des, dee, p, fdr, sig=sig, tag=tag, **kw)
        base_events.append(row)

# near-duplicates (within +/-50 bp of an existing event of the same gene)
g2 = genes[1]; g5 = genes[4]
b = next(r for r in base_events if r["tag"] == "g2_ex3")
se_row(g2, b["es"] + 20, b["ee"] + 20, b["ues"], b["uee"], b["des"], b["dee"], 0.01, 0.045, tag="dup_g2_ex3_higherfdr")
b = next(r for r in base_events if r["tag"].startswith("g5_ex4"))
se_row(g5, b["es"] - 35, b["ee"] - 35, b["ues"], b["uee"], b["des"], b["dee"], 1e-4, 1e-3, tag="dup_g5_ex4_lowerfdr")
b = next(r for r in base_events if r["tag"].startswith("g8_ex6"))
se_row(genes[7], b["es"], b["ee"] + 40, b["ues"], b["uee"], b["des"], b["dee"], 0.5, 0.8, tag="dup_g8_ex6_endshift")

with open(os.path.join(OUT, "SE.MATS.JC.txt"), "w") as fh:
    fh.write(SE_HEADER + "\n")
    for r in se_rows:
        fh.write(r["line"] + "\n")

# JCEC: same events & counts, FDR halved for even IDs (JCEC wins) / x1.5 for odd IDs (JC wins)
jcec_rows = []
with open(os.path.join(OUT, "SE.MATS.JCEC.txt"), "w") as fh:
    fh.write(SE_HEADER + "\n")
    for r in se_rows:
        parts = r["line"].split("\t")
        fdr = r["fdr"]
        new_fdr = fdr / 2 if r["id"] % 2 == 0 else min(1.0, fdr * 1.5)
        parts[19] = f"{new_fdr:g}"
        # the comma row keeps the comma format in JCEC too
        if "comma" in r["tag"]:
            parts[19] = f"{new_fdr:g}".replace(".", ",")
        jcec_rows.append({**r, "fdr": new_fdr, "line": "\t".join(parts), "mode": "JCEC"})
        fh.write("\t".join(parts) + "\n")
for r in se_rows:
    r["mode"] = "JC"

# ---------------------------------------------------------------------------
# A3SS: NAGNAG pair on gene 3 (+) exon 4, one event on gene 4 (-), one exact duplicate
# ---------------------------------------------------------------------------
alt_rows = []
g3 = genes[2]; g4 = genes[3]
e3s, e3e = g3["exons"][2]; e4s, e4e = g3["exons"][3]
c1, m1 = stats_block("A3SS", *counts(True), 1e-4, 0.001)
c2, m2 = stats_block("A3SS", *counts(False), 0.002, 0.02)
c3, m3 = stats_block("A3SS", *counts(True), 0.2, 0.4)
c4, m4 = stats_block("A3SS", *counts(True), 0.3, 0.5)
a3 = [
    (f'1\t"{g3["gene_id"]}"\t"{g3["symbol"]}"\tchr1\t+\t{e4s - 3}\t{e4e}\t{e4s}\t{e4e}\t{e3s}\t{e3e}\t1\t{c1}', m1),
    (f'2\t"{g3["gene_id"]}"\t"{g3["symbol"]}"\tchr1\t+\t{e4s}\t{e4e}\t{e4s + 3}\t{e4e}\t{e3s}\t{e3e}\t2\t{c2}', m2),
]
# gene 4 (- strand): alternative 3'SS at the genomic END of exon 3; flanking = exon 4 (downstream)
f3s, f3e = g4["exons"][2]; f4s, f4e = g4["exons"][3]
a3.append((f'3\t"{g4["gene_id"]}"\t"{g4["symbol"]}"\tchr1\t-\t{f3s}\t{f3e + 3}\t{f3s}\t{f3e}\t{f4s}\t{f4e}\t3\t{c3}', m3))
a3.append((f'4\t"{g4["gene_id"]}"\t"{g4["symbol"]}"\tchr1\t-\t{f3s}\t{f3e + 3}\t{f3s}\t{f3e}\t{f4s}\t{f4e}\t4\t{c4}', m4))  # exact dup
with open(os.path.join(OUT, "A3SS.MATS.JC.txt"), "w") as fh:
    fh.write(ALT_HEADER + "\n" + "\n".join(l for l, _ in a3) + "\n")

# A5SS: gene 1 (+) exon 3 long end +4 (flanking = exon 4); gene 2 (-) exon 4 long start -5 (flanking = exon 3)
g1 = genes[0]; g2 = genes[1]
x3s, x3e = g1["exons"][2]; x4s, x4e = g1["exons"][3]
y3s, y3e = g2["exons"][2]; y4s, y4e = g2["exons"][3]
c5, m5 = stats_block("A5SS", *counts(True), 1e-3, 0.01)
c6, m6 = stats_block("A5SS", *counts(False), 0.4, 0.7)
a5 = [
    (f'1\t"{g1["gene_id"]}"\t"{g1["symbol"]}"\tchr1\t+\t{x3s}\t{x3e + 4}\t{x3s}\t{x3e}\t{x4s}\t{x4e}\t1\t{c5}', m5),
    (f'2\t"{g2["gene_id"]}"\t"{g2["symbol"]}"\tchr1\t-\t{y4s - 5}\t{y4e}\t{y4s}\t{y4e}\t{y3s}\t{y3e}\t2\t{c6}', m6),
]
with open(os.path.join(OUT, "A5SS.MATS.JC.txt"), "w") as fh:
    fh.write(ALT_HEADER + "\n" + "\n".join(l for l, _ in a5) + "\n")

# RI: gene 6 — two retained introns sharing the riExonStart boundary; one low-coverage row dropped
g6 = genes[5]
r2s, r2e = g6["exons"][1]; r3s, r3e = g6["exons"][2]; r4s, r4e = g6["exons"][3]
c7, m7 = stats_block("RI", *counts(True), 1e-5, 1e-4)
c8, m8 = stats_block("RI", *counts(False), 0.05, 0.1)
low = ([3, 2, 4], [1, 2, 3], [40, 50, 60], [30, 20, 10])
c9, m9 = stats_block("RI", *low, 0.5, 0.9)
ri = [
    (f'1\t"{g6["gene_id"]}"\t"{g6["symbol"]}"\tchr1\t-\t{r2s}\t{r3e}\t{r2s}\t{r2e}\t{r3s}\t{r3e}\t1\t{c7}', m7),
    (f'2\t"{g6["gene_id"]}"\t"{g6["symbol"]}"\tchr1\t-\t{r2s}\t{r4e}\t{r2s}\t{r2e}\t{r4s}\t{r4e}\t2\t{c8}', m8),
    (f'3\t"{g6["gene_id"]}"\t"{g6["symbol"]}"\tchr1\t-\t{r3s}\t{r4e}\t{r3s}\t{r3e}\t{r4s}\t{r4e}\t3\t{c9}', m9),  # low cov
]
with open(os.path.join(OUT, "RI.MATS.JC.txt"), "w") as fh:
    fh.write(RI_HEADER + "\n" + "\n".join(l for l, _ in ri) + "\n")

# MXE: gene 7 — same first exon (exon 3), different second exon (exon 4 vs exon 5)
g7 = genes[6]
q2, q3, q4, q5, q6 = g7["exons"][1:6]
c10, m10 = stats_block("MXE", *counts(True), 1e-4, 0.002)
c11, m11 = stats_block("MXE", *counts(False), 0.02, 0.06)
mxe = [
    (f'1\t"{g7["gene_id"]}"\t"{g7["symbol"]}"\tchr1\t+\t{q3[0]}\t{q3[1]}\t{q4[0]}\t{q4[1]}\t{q2[0]}\t{q2[1]}\t{q5[0]}\t{q5[1]}\t1\t{c10}', m10),
    (f'2\t"{g7["gene_id"]}"\t"{g7["symbol"]}"\tchr1\t+\t{q3[0]}\t{q3[1]}\t{q5[0]}\t{q5[1]}\t{q2[0]}\t{q2[1]}\t{q6[0]}\t{q6[1]}\t2\t{c11}', m11),
]
with open(os.path.join(OUT, "MXE.MATS.JC.txt"), "w") as fh:
    fh.write(MXE_HEADER + "\n" + "\n".join(l for l, _ in mxe) + "\n")

open(os.path.join(OUT, "summary.txt"), "w").close()

# ---------------------------------------------------------------------------
# Independent expectation: coverage filter (mean IJC+SJC >= 10 per group over
# parseable replicates; a group with no parseable replicate -> dropped), then
# SE dedup per (gene, chr, strand): sorted by FDR asc (NaN last), a row is a
# duplicate when a kept row has |start diff| <= 50 OR |end diff| <= 50; lowest FDR kept.
# ---------------------------------------------------------------------------
def passes_cov(m):
    return m["mean_cov1"] is not None and m["mean_cov2"] is not None and m["mean_cov1"] >= 10 and m["mean_cov2"] >= 10


all_se = [r for r in se_rows + jcec_rows]
se_pass = [r for r in all_se if passes_cov(r)]
se_dropped_cov = [r for r in all_se if not passes_cov(r)]
by_group: dict[tuple, list] = {}
for r in se_pass:
    by_group.setdefault((r["gene"], r["chr"], r["strand"]), []).append(r)
kept_se = []
for key, rows in by_group.items():
    rows = sorted(rows, key=lambda r: (r["fdr"], -abs(r["dpsi"] or 0)))
    kept: list[dict] = []
    for r in rows:
        if any(abs(r["es"] - k["es"]) <= 50 or abs(r["ee"] - k["ee"]) <= 50 for k in kept):
            continue
        kept.append(r)
    kept_se.extend(kept)

n_a3 = len({l.split("\t")[5:11].__str__() for l, m in a3 if passes_cov(m)})
n_a5 = len({str(l.split("\t")[5:11]) for l, m in a5 if passes_cov(m)})
n_ri = len({str(l.split("\t")[5:11]) for l, m in ri if passes_cov(m)})   # AND rule: pair shares only riExonStart -> both kept
n_mxe = len({str(l.split("\t")[5:13]) for l, m in mxe if passes_cov(m)})  # different 2nd exon -> both kept

sig_kept = [r for r in kept_se if r["fdr"] <= 0.05 and r["dpsi"] is not None and abs(r["dpsi"]) >= 0.1]
sig_kept_p01 = [r for r in sig_kept if r["p"] <= 0.01]
# all non-SE rows' significance (fdr<=0.05 & |dpsi|>=0.1)
other_meta = [m for l, m in a3[:3] + a5 + ri[:2] + mxe if passes_cov(m)]
other_sig = [m for m in other_meta if m["fdr"] <= 0.05 and abs(m["dpsi"]) >= 0.1]
other_sig_p01 = [m for m in other_sig if m["p"] <= 0.01]

expected = {
    "n_se_rows_jc": len(se_rows),
    "n_se_rows_total": len(all_se),
    "n_se_dropped_coverage": len(se_dropped_cov),
    "se_dropped_tags": sorted({r["tag"] for r in se_dropped_cov}),
    "n_se_kept": len(kept_se),
    "n_a3ss": n_a3, "n_a5ss": n_a5, "n_ri": n_ri, "n_mxe": n_mxe,
    "event_count": len(kept_se) + n_a3 + n_a5 + n_ri + n_mxe,
    "kept_se": [
        {"tag": r["tag"], "mode": r["mode"], "fdr": r["fdr"], "es": r["es"], "ee": r["ee"], "gene": r["gene"],
         "symbol": r["symbol"], "chr": r["chr"], "strand": r["strand"], "p": r["p"], "dpsi": r["dpsi"]}
        for r in sorted(kept_se, key=lambda r: (r["chr"], r["es"]))
    ],
    "n_sig_fdr05_dpsi01": len(sig_kept) + len(other_sig),
    "n_sig_fdr05_dpsi01_p001": len(sig_kept_p01) + len(other_sig_p01),
    "n_se_sig": len(sig_kept), "n_se_sig_p001": len(sig_kept_p01),
    "genes": [{"idx": g["idx"], "gene_id": g["gene_id"], "symbol": g["symbol"], "chr": g["chr"], "strand": g["strand"],
               "exons": g["exons"], "tx_id": g["tx_id"], "mane": g["idx"] in MANE_GENES,
               "cds": cds_intervals(g, g["exons"]) if g["idx"] in MANE_GENES else None} for g in genes],
    "plus_clinical": {"gene": 2, "tx_id": "ENST00000000022", "exons": plus_clinical_exons[2]},
}
with open(os.path.join(OUT, "expected.json"), "w") as fh:
    json.dump(expected, fh, indent=1)
print(json.dumps({k: v for k, v in expected.items() if k not in ("kept_se", "genes", "plus_clinical")}, indent=1))
print("kept SE by mode:", {m: sum(1 for r in kept_se if r["mode"] == m) for m in ("JC", "JCEC")})
