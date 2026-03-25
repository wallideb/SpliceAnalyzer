# Future Event Types — Implementation Plan

> Roadmap for extending SpliceAnalyzer to MXE, A3SS, and A5SS event types.
> Each section describes the biology, the analytical approach, and what can
> be reused from the existing SE pipeline.

---

## Table of Contents

1. [Current SE Pipeline (baseline)](#1-current-se-pipeline-baseline)
2. [MXE — Mutually Exclusive Exons](#2-mxe--mutually-exclusive-exons)
3. [A3SS — Alternative 3' Splice Sites](#3-a3ss--alternative-3-splice-sites)
4. [A5SS — Alternative 5' Splice Sites](#4-a5ss--alternative-5-splice-sites)
5. [Shared Infrastructure](#5-shared-infrastructure)
6. [Implementation Priorities](#6-implementation-priorities)
7. [Key References](#7-key-references)

---

## 1. Current SE Pipeline (baseline)

The SE module serves as the template. Features currently computed per event:

| Feature | Method |
|---------|--------|
| 5'SS donor (skipped exon) | 9 nt PWM: 3 exonic + 6 intronic |
| 3'SS acceptor (skipped exon) | 23 nt PWM: 20 intronic + 3 exonic |
| 5'SS donor (upstream flanking) | 9 nt window |
| 3'SS acceptor (downstream flanking) | 23 nt window |
| Canonical GT/AG verification | Positions +1/+2 (donor), -2/-1 (acceptor) |
| PPT score | Pyrimidine fraction in 47 nt upstream of 3'SS |
| Branch point | YNYURAY motif search upstream of PPT |
| Reading frame | Exon size mod 3 vs MANE CDS phase |
| hnRNP motif enrichment | 19 motifs × 5 regions, z-test + BH FDR |
| Sig vs non-sig comparison | 13 individual tests (Welch t / proportion z) |

---

## 2. MXE — Mutually Exclusive Exons

### 2.1 Biology

Two exons are never co-included in the mature mRNA. Only one of the pair
(exon 1 or exon 2) is retained. Regulation mechanisms include:

- **RNA secondary structure**: Stem-loop structures that physically block
  simultaneous inclusion (e.g., *Dscam* in Drosophila — Graveley, 2005).
- **Steric interference**: The two exons' branch points or PPTs overlap
  or are too close, preventing dual recognition by U2 snRNP.
- **Competing RBP binding**: Tissue-specific RBPs (e.g., PTBP1/PTBP2,
  nPTB, NOVA, RBFOX) bind near one exon to repress it while the other
  is included by default.
- **Exon similarity**: MXE pairs often have high sequence similarity
  (paralogous duplication), particularly in ion channels, cytoskeletal
  proteins, and cell adhesion molecules.

### 2.2 Genomic Regions to Scan

```
                Upstream        Exon 1           Exon 2        Downstream
                 exon        (included)        (excluded)        exon
    ──────┤ ►  ├────────────┤ ►  ├────────────┤ ►  ├──────────┤ ►  ├──────
           5'SS    intron   3'SS  5'SS  intron  3'SS  5'SS  intron  3'SS
          (up)              (e1)  (e1)         (e2)  (e2)          (dn)
```

**7 genomic regions** (vs 5 for SE):

| # | Region | Definition |
|---|--------|------------|
| 1 | Upstream exon | 250 nt upstream of exon 1 3'SS (inside upstream intron) |
| 2 | Upstream intron | Full intron between upstream exon and exon 1 |
| 3 | Exon 1 body | Full exon 1 sequence |
| 4 | Middle intron | Intron between exon 1 and exon 2 |
| 5 | Exon 2 body | Full exon 2 sequence |
| 6 | Downstream intron | Full intron between exon 2 and downstream exon |
| 7 | Downstream exon | 250 nt downstream of exon 2 5'SS |

### 2.3 Event-Specific Analyses

#### Exon similarity score
- Pairwise alignment (Needleman-Wunsch or BLAST) of exon 1 vs exon 2
- Report % identity, alignment length, E-value
- High similarity suggests paralogous duplication (functional constraint)

#### Splice site strength comparison
- Compare 5'SS and 3'SS MaxEntScan scores for exon 1 vs exon 2
- Weaker splice sites on the regulated exon = more sensitive to RBP control
- Compare PPT scores for both exons' acceptor sites

#### Coordinated regulation
- Middle intron length: very short middle introns suggest steric occlusion
- Check for inverted complementary sequences flanking the two exons
  (potential RNA hairpin preventing dual inclusion)

#### Reading frame
- Both exons should preserve the reading frame (most MXE pairs are
  in-frame substitutions). Flag pairs where frame is disrupted.
- Report whether exon 1 and exon 2 produce the same frame shift
  (expected: same size or size difference divisible by 3).

### 2.4 Reuse from SE Pipeline

| Component | Reusable? | Notes |
|-----------|-----------|-------|
| Splice site extraction (faidx) | Yes | Need 4 donor + 4 acceptor sites instead of 2+2 |
| PWM / consensus logos | Yes | Render for each of the 4 splice junctions |
| PPT scoring | Yes | Apply to both exon 1 and exon 2 acceptor sites |
| Branch point search | Yes | Search upstream of both acceptors |
| Frame analysis | Partial | Need to compare exon 1 vs exon 2 frame equivalence |
| hnRNP motif scan | Yes | Expand to 7 regions |
| Statistical comparison | Yes | Same test framework, more features |

**New code needed:**
- Exon similarity scoring (sequence alignment)
- Middle intron analysis (length, secondary structure potential)
- MXE-specific schematic drawing (4 exons instead of 3)

---

## 3. A3SS — Alternative 3' Splice Sites

### 3.1 Biology

Two competing 3' splice sites (acceptors) on the same exon. The proximal
site (closer to the exon body) produces a shorter upstream intron; the
distal site (further upstream) produces a longer one, extending the exon.

```
                                 distal 3'SS    proximal 3'SS
                                     ▼               ▼
    ─────────┤ ►  ├─────────────AG──────────AG───────┤ ►  ├─────
     Upstream       Upstream intron     Extended      Core     Downstream
      exon                              region       exon       exon
```

Key regulators:

- **U2AF65/U2AF35**: Binds the polypyrimidine tract and AG dinucleotide.
  Differential affinity for the two PPTs determines site selection.
- **SF1/BBP**: Branch point recognition; different branch point positions
  upstream of proximal vs distal AG.
- **hnRNP A1**: Antagonises U2AF binding at proximal sites, promoting
  distal site usage (Caceres et al., 1994).
- **PTB (hnRNP I)**: Blocks proximal 3'SS by binding polypyrimidine
  tracts (Wagner & Garcia-Blanco, 2001).
- **SRSF1 (SF2/ASF)**: Promotes proximal 3'SS via exonic enhancers
  (Krainer et al., 1991).

### 3.2 Genomic Regions to Scan

**6 genomic regions:**

| # | Region | Definition |
|---|--------|------------|
| 1 | Upstream exon | 250 nt at 3' end of upstream exon |
| 2 | Common intron | Intron region from upstream 5'SS to distal 3'SS |
| 3 | Extended region | Sequence between distal and proximal 3'SS (the alternatively included segment) |
| 4 | Proximal PPT | ~47 nt upstream of proximal AG |
| 5 | Distal PPT | ~47 nt upstream of distal AG |
| 6 | Downstream exon | 250 nt at 5' end of the regulated exon |

### 3.3 Event-Specific Analyses

#### Competing 3'SS strength
- **MaxEntScan scores** for proximal vs distal acceptor sites
- 23 nt PWM for both sites — side-by-side comparison logos
- Canonical AG verification at both sites

#### PPT comparison
- PPT score, T-content, C-content for proximal vs distal PPTs
- PPT length comparison
- The PPT with higher pyrimidine content typically corresponds to
  the constitutively used site

#### U2AF binding prediction
- Score the PPT with a U2AF65 binding model (PSSM from Zamore et al., 1992;
  or use the Singh et al., 2013 model)
- Differential U2AF65 affinity is the primary determinant

#### Branch point analysis
- Search for YNYURAY motif upstream of each PPT
- Distance from BP to each 3'SS — canonical is 18-40 nt
- Different BP positions for each site

#### Extended region properties
- Length of the alternatively included segment (distal-to-proximal distance)
- Reading frame impact: does inclusion/exclusion of the extended region
  preserve the reading frame?
- Coding potential of the extended region

#### Reading frame
- The extended region length mod 3 determines frame impact
- In-frame extensions add/remove amino acids; frameshifts often trigger NMD

### 3.4 Reuse from SE Pipeline

| Component | Reusable? | Notes |
|-----------|-----------|-------|
| Splice site extraction | Yes | Extract at both AG positions |
| PWM / logos | Yes | Two acceptor logos side-by-side |
| PPT scoring | Yes | Score both PPTs independently |
| Branch point | Yes | Search upstream of both PPTs |
| Frame analysis | Partial | Analyse the extended region length |
| hnRNP motifs | Yes | Scan 6 regions instead of 5 |
| Statistical comparison | Yes | Additional comparative tests (proximal vs distal) |

**New code needed:**
- Proximal vs distal splice site strength comparison
- Dual PPT scoring and comparison
- Extended region analysis
- A3SS-specific schematic (showing both AG sites)

---

## 4. A5SS — Alternative 5' Splice Sites

### 4.1 Biology

Two competing 5' splice sites (donors) on the same exon. The proximal
site (closer to the exon body) produces a shorter downstream intron;
the distal site produces a longer downstream intron, shortening the exon.

```
              proximal 5'SS    distal 5'SS
                   ▼               ▼
    ────┤ ►  ├────GT──────────GT─────────────────┤ ►  ├─────
     Upstream  Core    Extended    Downstream     Downstream
      exon     exon    region       intron          exon
```

Key regulators:

- **U1 snRNA**: Base-pairs with the 5'SS. The degree of complementarity
  to U1 snRNA determines splice site strength (Roca et al., 2013).
- **SRSF1 (SF2/ASF)**: Promotes proximal 5'SS usage via exonic
  enhancers (Ge & Manley, 1990).
- **hnRNP A1**: Promotes distal 5'SS by antagonising SR proteins
  and spreading along the pre-mRNA (Mayeda & Krainer, 1992).
- **U1-70K / U1C**: U1 snRNP protein components that stabilise
  U1 binding; mutations shift 5'SS choice.
- **TIA-1/TIAR**: Bind U-rich sequences downstream of weak 5'SS
  to recruit U1 snRNP (Forch et al., 2000).

### 4.2 Genomic Regions to Scan

**6 genomic regions:**

| # | Region | Definition |
|---|--------|------------|
| 1 | Upstream exon | 250 nt at 3' end of the regulated exon |
| 2 | Core exon | Exon region upstream of the proximal 5'SS |
| 3 | Extended region | Sequence between proximal and distal 5'SS |
| 4 | Proximal downstream | 250 nt downstream of proximal GT (intronic) |
| 5 | Distal downstream | 250 nt downstream of distal GT (intronic) |
| 6 | Downstream exon | 250 nt at 5' end of downstream exon |

### 4.3 Event-Specific Analyses

#### Competing 5'SS strength
- **MaxEntScan scores** for proximal vs distal donor sites
- 9 nt PWM for both sites — side-by-side comparison logos
- Canonical GT verification at both sites

#### U1 snRNA complementarity
- Score each 5'SS against the U1 snRNA consensus (5'-AUACUUACCUG-3')
- Count mismatches in the critical +1 to +6 positions
- Higher complementarity = stronger site

#### Extended region properties
- Length of the alternatively included segment
- Reading frame impact
- ESE/ESS density in the extended region (exonic regulatory elements)

#### TIA-1 binding motifs
- Search for U-rich sequences (UUUUU, UUUCU) in the first 30 nt
  downstream of each 5'SS
- TIA-1/TIAR binding downstream of weak 5'SS can compensate for
  poor U1 complementarity

#### Reading frame
- Same as A3SS: extended region length mod 3

### 4.4 Reuse from SE Pipeline

| Component | Reusable? | Notes |
|-----------|-----------|-------|
| Splice site extraction | Yes | Extract at both GT positions |
| PWM / logos | Yes | Two donor logos side-by-side |
| PPT scoring | Partial | Only one 3'SS (downstream), so single PPT |
| Branch point | Partial | Only one acceptor site |
| Frame analysis | Partial | Analyse extended region length |
| hnRNP motifs | Yes | Scan 6 regions |
| Statistical comparison | Yes | Additional comparative tests |

**New code needed:**
- Proximal vs distal donor strength comparison
- U1 snRNA complementarity scoring
- TIA-1 binding motif search
- A5SS-specific schematic (showing both GT sites)

---

## 5. Shared Infrastructure

### 5.1 MaxEntScan Integration

All three event types benefit from **MaxEntScan** (Yeo & Burge, 2004)
splice site strength scoring. This should be implemented as a shared
service:

```
app/services/maxentscan.py
  - score_5ss(seq_9nt) -> float    # 9-mer: [-3, +6]
  - score_3ss(seq_23nt) -> float   # 23-mer: [-20, +3]
```

MaxEntScan uses maximum entropy models trained on human splice sites.
Pre-computed scoring matrices are available from the original publication.
This single addition unlocks splice site strength comparison for all
event types.

### 5.2 Generalised Motif Scanning

The current hnRNP scan uses 5 fixed SE regions. Generalise to accept
a list of named regions per event type:

```python
def scan_regions(
    event_type: str,       # "SE", "MXE", "A3SS", "A5SS"
    regions: list[BedRegion],
    region_names: list[str],
    ...
)
```

### 5.3 Event-Type Schematic Drawings

Each event type needs its own schematic for the PDF report:

| Event | Exons | Splice sites | Special elements |
|-------|-------|-------------|-----------------|
| SE | 3 (up, skip, down) | 4 (2 donor + 2 acceptor) | PPT, BP, skipping arc |
| MXE | 4 (up, e1, e2, down) | 6 (3 donor + 3 acceptor) | Similarity score, mutual exclusion arc |
| A3SS | 2 (up, regulated) | 3 (1 donor + 2 acceptor) | Proximal vs distal AG, dual PPT |
| A5SS | 2 (regulated, down) | 3 (2 donor + 1 acceptor) | Proximal vs distal GT |

### 5.4 Database Schema

The existing `EventSpliceFeature` model needs extension or event-type
specific child tables:

```
event_splice_features_mxe:
  - exon1_donor_seq, exon1_acceptor_seq
  - exon2_donor_seq, exon2_acceptor_seq
  - exon_similarity_score
  - middle_intron_size

event_splice_features_a3ss:
  - proximal_acceptor_seq, distal_acceptor_seq
  - proximal_ppt_score, distal_ppt_score
  - extended_region_size

event_splice_features_a5ss:
  - proximal_donor_seq, distal_donor_seq
  - u1_score_proximal, u1_score_distal
  - extended_region_size
```

---

## 6. Implementation Priorities

### Phase 1 — Foundation (recommended first)

1. **MaxEntScan service** — unlocks splice site strength for all types
2. **Generalise motif scanning** — parameterise region definitions
3. **A3SS support** — most similar to SE (same 3'SS biology, PPT/BP reuse)
   - Dual acceptor extraction + comparison
   - Extended region frame analysis
   - A3SS schematic

### Phase 2 — A5SS

4. **A5SS support** — mirrors A3SS on the donor side
   - Dual donor extraction + comparison
   - U1 complementarity scoring
   - TIA-1 motif search
   - A5SS schematic

### Phase 3 — MXE

5. **MXE support** — most complex, requires new analyses
   - 4-exon architecture
   - Exon similarity scoring (sequence alignment)
   - Middle intron analysis
   - 7-region motif scanning
   - MXE schematic

### Phase 4 — Cross-Event Comparison

6. **Meta-analysis** across event types within the same dataset
   - Are certain RBP motifs enriched in specific event types?
   - Splice site strength distributions by event type
   - Frame preservation rates by event type

---

## 7. Key References

### General Alternative Splicing

- **Wang ET et al.** Alternative isoform regulation in human tissue transcriptomes. *Nature*. 2008;456(7221):470-476.
- **Baralle FE, Giudice J.** Alternative splicing as a regulator of development and tissue identity. *Nat Rev Mol Cell Biol*. 2017;18(7):437-451.
- **Scotti MM, Swanson MS.** RNA mis-splicing in disease. *Nat Rev Genet*. 2016;17(1):19-32.

### Splice Site Scoring

- **Yeo G, Burge CB.** Maximum entropy modeling of short sequence motifs with applications to RNA splicing signals. *J Comput Biol*. 2004;11(2-3):377-394. — **MaxEntScan**
- **Roca X, Sachidanandam R, Krainer AR.** Intrinsic differences between authentic and cryptic 5' splice sites. *Nucleic Acids Res*. 2003;31(21):6321-6333.

### rMATS & rMAPS

- **Shen S et al.** rMATS: Robust and flexible detection of differential alternative splicing. *Proc Natl Acad Sci USA*. 2014;111(51):E5593-5601.
- **Hwang JY et al.** rMAPS2: an update of the RNA map analysis and plotting server for alternative splicing regulation. *Nucleic Acids Res*. 2020;48(W1):W300-W306.

### MXE

- **Graveley BR.** Mutually exclusive splicing of the insect Dscam pre-mRNA directed by competing intronic RNA secondary structures. *Cell*. 2005;123(1):65-73.
- **Yue Y et al.** Long-range RNA pairings contribute to mutually exclusive splicing. *RNA*. 2016;22(1):96-110.
- **Hatje K et al.** The landscape of human mutually exclusive splicing. *Mol Syst Biol*. 2017;13(12):959.

### A3SS / 3' Splice Site Selection

- **Smith CW, Valcárcel J.** Alternative pre-mRNA splicing: the logic of combinatorial control. *Trends Biochem Sci*. 2000;25(8):381-388.
- **Zamore PD, Green MR.** Identification, purification, and biochemical characterization of U2 small nuclear ribonucleoprotein auxiliary factor. *Proc Natl Acad Sci USA*. 1989;86(23):9243-9247. — **U2AF**
- **Singh R et al.** Distinct binding specificities and functions of higher eukaryotic polypyrimidine tract-binding proteins. *Science*. 1995;268(5214):1173-1176.
- **Wagner EJ, Garcia-Blanco MA.** Polypyrimidine tract binding protein antagonizes exon definition. *Mol Cell Biol*. 2001;21(10):3281-3288.

### A5SS / 5' Splice Site Selection

- **Roca X, Krainer AR, Eperon IC.** Pick one, but be quick: 5' splice sites and the problems of too many choices. *Genes Dev*. 2013;27(2):129-144.
- **Mayeda A, Krainer AR.** Regulation of alternative pre-mRNA splicing by hnRNP A1 and splicing factor SF2. *Cell*. 1992;68(2):365-375.
- **Ge H, Manley JL.** A protein factor, ASF, controls cell-specific alternative splicing of SV40 early pre-mRNA in vitro. *Cell*. 1990;62(1):25-34.
- **Forch P et al.** The apoptosis-promoting factor TIA-1 is a regulator of alternative pre-mRNA splicing. *Mol Cell*. 2000;6(5):1089-1098.

### RBP Motifs & Databases

- **Ray D et al.** A compendium of RNA-binding motifs for decoding gene regulation. *Nature*. 2013;499(7457):172-177. — **CISBP-RNA**
- **Martinez-Contreras R et al.** hnRNP proteins and splicing control. *Adv Exp Med Biol*. 2007;623:123-147.
- **Cartegni L et al.** ESEfinder: a web resource to identify exonic splicing enhancers. *Nucleic Acids Res*. 2003;31(13):3568-3571.

### Branch Point

- **Mercer TR et al.** Genome-wide discovery of human splicing branchpoints. *Genome Res*. 2015;25(2):290-303.
- **Coolidge TR, Segar RA, Patton JG.** Functional analysis of the polypyrimidine tract in pre-mRNA splicing. *Nucleic Acids Res*. 1997;25(4):888-896.

---

*This document was prepared as a research roadmap. Implementation should
follow the phased approach above, starting with MaxEntScan integration
and A3SS support as the lowest-hanging fruit.*
