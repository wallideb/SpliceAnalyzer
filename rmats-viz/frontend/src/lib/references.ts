/**
 * references.ts
 * =============
 * Central registry of all scientific, mathematical, and statistical references
 * used in rMATS-Viz, with exact bibliographic citations and DOIs.
 *
 * Each entry is keyed by a stable string ID used in ScienceNote components.
 */

export interface Reference {
  id: string;
  /** Short citation shown inline (Author, Year) */
  short: string;
  /** Full citation in APA-ish style */
  full: string;
  /** DOI or URL */
  doi?: string;
  /** PMID for PubMed links */
  pmid?: number;
}

export const REFERENCES: Record<string, Reference> = {

  // ─────────────────────────────────────────────────────────────────────────
  // rMATS — splicing event detection
  // ─────────────────────────────────────────────────────────────────────────
  rmats: {
    id: "rmats",
    short: "Shen et al., 2014",
    full:
      "Shen S, Park JW, Lu ZX, Lin L, Henry MD, Wu YN, Zhou Q, Xing Y. " +
      "rMATS: Robust and flexible detection of differential alternative splicing " +
      "from replicate RNA-Seq data. " +
      "Proc Natl Acad Sci USA. 2014;111(51):E5593–E5601.",
    doi: "10.1073/pnas.1419161111",
    pmid: 25480548,
  },

  // ─────────────────────────────────────────────────────────────────────────
  // Sequence logos / Information content
  // ─────────────────────────────────────────────────────────────────────────
  sequence_logos: {
    id: "sequence_logos",
    short: "Schneider & Stephens, 1990",
    full:
      "Schneider TD, Stephens RM. " +
      "Sequence logos: a new way to display consensus sequences. " +
      "Nucleic Acids Res. 1990;18(20):6097–6100.",
    doi: "10.1093/nar/18.20.6097",
    pmid: 2172928,
  },

  // ─────────────────────────────────────────────────────────────────────────
  // Splice site consensus / GT-AG rule
  // ─────────────────────────────────────────────────────────────────────────
  splice_sites: {
    id: "splice_sites",
    short: "Shapiro & Senapathy, 1987",
    full:
      "Shapiro MB, Senapathy P. " +
      "RNA splice junctions of different classes of eukaryotes: sequence " +
      "statistics and functional implications in gene expression. " +
      "Nucleic Acids Res. 1987;15(17):7155–7174.",
    doi: "10.1093/nar/15.17.7155",
    pmid: 3658675,
  },

  // ─────────────────────────────────────────────────────────────────────────
  // MaxEnt / splice site scoring model
  // ─────────────────────────────────────────────────────────────────────────
  maxent: {
    id: "maxent",
    short: "Yeo & Burge, 2004",
    full:
      "Yeo G, Burge CB. " +
      "Maximum entropy modeling of short sequence motifs with applications to " +
      "RNA splicing signals. " +
      "J Comput Biol. 2004;11(2-3):377–394.",
    doi: "10.1089/1066527041410418",
    pmid: 15285897,
  },

  // ─────────────────────────────────────────────────────────────────────────
  // Branch point motif (YNYURAY)
  // ─────────────────────────────────────────────────────────────────────────
  branch_point: {
    id: "branch_point",
    short: "Padgett et al., 1986",
    full:
      "Padgett RA, Grabowski PJ, Konarska MM, Seiler S, Sharp PA. " +
      "Splicing of messenger RNA precursors. " +
      "Annu Rev Biochem. 1986;55:1119–1150.",
    doi: "10.1146/annurev.bi.55.070186.005351",
    pmid: 3527048,
  },

  // ─────────────────────────────────────────────────────────────────────────
  // Polypyrimidine tract (PPT)
  // ─────────────────────────────────────────────────────────────────────────
  ppt: {
    id: "ppt",
    short: "Coolidge et al., 1997",
    full:
      "Coolidge CJ, Seely RJ, Patton JG. " +
      "Functional analysis of the polypyrimidine tract in pre-mRNA splicing. " +
      "Nucleic Acids Res. 1997;25(4):888–896.",
    doi: "10.1093/nar/25.4.888",
    pmid: 9016643,
  },

  // ─────────────────────────────────────────────────────────────────────────
  // Permutation test / empirical p-value with continuity correction
  // ─────────────────────────────────────────────────────────────────────────
  permutation_phipson: {
    id: "permutation_phipson",
    short: "Phipson & Smyth, 2010",
    full:
      "Phipson B, Smyth GK. " +
      "Permutation P-values should never be zero: calculating exact P-values " +
      "when permutations are randomly drawn. " +
      "Stat Appl Genet Mol Biol. 2010;9(1):Article 39.",
    doi: "10.2202/1544-6115.1585",
    pmid: 21044043,
  },

  // ─────────────────────────────────────────────────────────────────────────
  // Benjamini-Hochberg FDR correction
  // ─────────────────────────────────────────────────────────────────────────
  benjamini_hochberg: {
    id: "benjamini_hochberg",
    short: "Benjamini & Hochberg, 1995",
    full:
      "Benjamini Y, Hochberg Y. " +
      "Controlling the false discovery rate: a practical and powerful approach " +
      "to multiple testing. " +
      "J R Stat Soc Series B. 1995;57(1):289–300.",
    doi: "10.1111/j.2517-6161.1995.tb02031.x",
  },

  // ─────────────────────────────────────────────────────────────────────────
  // MANE Select transcript
  // ─────────────────────────────────────────────────────────────────────────
  mane_select: {
    id: "mane_select",
    short: "Morales et al., 2022",
    full:
      "Morales J, Pujar S, Loveland JE, Astashyn A, Bennett R, Berry A, " +
      "Cox E, Davidson C, Ermolaeva O, et al. " +
      "A joint NCBI and EMBL-EBI transcript set for clinical genomics and research. " +
      "Nature. 2022;604(7905):310–315.",
    doi: "10.1038/s41586-022-04558-8",
    pmid: 35388217,
  },

  // ─────────────────────────────────────────────────────────────────────────
  // Gene Ontology
  // ─────────────────────────────────────────────────────────────────────────
  gene_ontology: {
    id: "gene_ontology",
    short: "Gene Ontology Consortium, 2021",
    full:
      "Gene Ontology Consortium. " +
      "The Gene Ontology resource: enriching a GOld mine. " +
      "Nucleic Acids Res. 2021;49(D1):D325–D334.",
    doi: "10.1093/nar/gkaa1113",
    pmid: 33290552,
  },

  // ─────────────────────────────────────────────────────────────────────────
  // STRING-DB protein interactions
  // ─────────────────────────────────────────────────────────────────────────
  stringdb: {
    id: "stringdb",
    short: "Szklarczyk et al., 2023",
    full:
      "Szklarczyk D, Kirsch R, Koutrouli M, Nastou K, Mehryary F, Hachilif R, " +
      "Gable AL, Fang T, Doncheva NT, Pyysalo S, Bork P, Jensen LJ, von Mering C. " +
      "The STRING database in 2023: protein–protein association networks and " +
      "functional enrichment analyses for any of 12 479 organisms. " +
      "Nucleic Acids Res. 2023;51(D1):D638–D646.",
    doi: "10.1093/nar/gkac1000",
    pmid: 36370105,
  },

  // ─────────────────────────────────────────────────────────────────────────
  // PanelApp Australia
  // ─────────────────────────────────────────────────────────────────────────
  panelapp: {
    id: "panelapp",
    short: "Martin et al., 2019",
    full:
      "Martin AR, Williams E, Foulger RE, Leigh S, Daugherty LC, Niblock O, " +
      "Leong IUS, Smith KR, Gerasimenko O, Haraldsdottir E, et al. " +
      "PanelApp crowdsources expert knowledge to establish consensus diagnostic " +
      "gene panels. " +
      "Nat Genet. 2019;51(11):1560–1565.",
    doi: "10.1038/s41588-019-0528-2",
    pmid: 31676867,
  },

  // ─────────────────────────────────────────────────────────────────────────
  // Shannon entropy / information theory
  // ─────────────────────────────────────────────────────────────────────────
  shannon: {
    id: "shannon",
    short: "Shannon, 1948",
    full:
      "Shannon CE. " +
      "A mathematical theory of communication. " +
      "Bell Syst Tech J. 1948;27(3):379–423.",
    doi: "10.1002/j.1538-7305.1948.tb01338.x",
  },

  // ─────────────────────────────────────────────────────────────────────────
  // rMAPS2 — RNA map analysis for splicing regulation
  // ─────────────────────────────────────────────────────────────────────────
  rmaps2: {
    id: "rmaps2",
    short: "Hwang et al., 2020",
    full:
      "Hwang JY, Jung S, Bhutada S, Park JW. " +
      "rMAPS2: an update of the RNA map analysis and plotting server " +
      "for alternative splicing regulation. " +
      "Nucleic Acids Res. 2020;48(W1):W300–W306.",
    doi: "10.1093/nar/gkaa237",
    pmid: 32313960,
  },

  // ─────────────────────────────────────────────────────────────────────────
  // Enrichr — gene-set enrichment analysis
  // ─────────────────────────────────────────────────────────────────────────
  enrichr: {
    id: "enrichr",
    short: "Chen et al., 2013",
    full:
      "Chen EY, Tan CM, Kou Y, Duan Q, Wang Z, Meirelles GV, Clark NR, Ma'ayan A. " +
      "Enrichr: interactive and collaborative HTML5 gene list enrichment analysis tool. " +
      "BMC Bioinformatics. 2013;14:128.",
    doi: "10.1186/1471-2105-14-128",
    pmid: 23586463,
  },

  // ─────────────────────────────────────────────────────────────────────────
  // CISBP-RNA — RNA-binding protein motif database
  // ─────────────────────────────────────────────────────────────────────────
  cisbp_rna: {
    id: "cisbp_rna",
    short: "Ray et al., 2013",
    full:
      "Ray D, Kazan H, Cook KB, Weirauch MT, Najafabadi HS, Li X, " +
      "Gueroussov S, Albu M, Zheng H, Yang A, Na H, et al. " +
      "A compendium of RNA-binding motifs for decoding gene regulation. " +
      "Nature. 2013;499(7457):172–177.",
    doi: "10.1038/nature12311",
    pmid: 23846655,
  },

};

/** Return the PubMed URL for a reference, if a PMID is available. */
export function pubmedUrl(ref: Reference): string | null {
  return ref.pmid ? `https://pubmed.ncbi.nlm.nih.gov/${ref.pmid}/` : null;
}

/** Return the DOI URL for a reference, if a DOI is available. */
export function doiUrl(ref: Reference): string | null {
  return ref.doi ? `https://doi.org/${ref.doi}` : null;
}
