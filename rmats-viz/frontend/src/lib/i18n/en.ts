/**
 * English locale dictionary — source of truth for all UI strings.
 * All other locales must mirror this exact structure.
 */
export const en = {
  meta: {
    description: "Differential splicing event explorer",
  },
  nav: {
    analyses: "Analyses",
  },
  header: {
    themeLight: "Switch to light mode",
    themeDark: "Switch to dark mode",
    toggleTheme: "Toggle theme",
    userAccount: "User account (authentication coming soon)",
  },
  analyses: {
    title: "My Analyses",
    subtitle: "Explore and manage your rMATS differential splicing analyses",
    newAnalysis: "New Analysis",
    loading: "Loading...",
    error: "Error: {{message}}",
    empty: {
      title: "No analyses",
      subtitle: "Import your rMATS files to get started.",
      cta: "Create my first analysis",
    },
    mutatedGenes: "Mutated gene(s):",
    share: {
      copy: "Share analysis (copy link)",
      copied: "Link copied!",
    },
    delete: "Delete analysis",
    confirmDelete: "Delete analysis «{{name}}»?",
    status: {
      ready: "Ready",
      processing: "Processing",
      error: "Error",
    },
  },
  newAnalysis: {
    title: "New Analysis",
    subtitle: "Import your rMATS files and configure your analysis",
    steps: {
      filesGenes: "Files & Genes",
      groups: "Groups",
    },
    form: {
      analysisName: "Analysis name",
      analysisNamePlaceholder: "e.g. PCBP1 cohort 2024",
      mutatedGenes: "Mutated gene(s) in the cohort",
      mutatedGenesNomenclature: "(HUGO nomenclature)",
      mutatedGenesDescription:
        "These genes will be displayed in the analysis even if they do not appear in the detected splicing anomalies. The Ensembl ID (ENSG) is retrieved automatically.",
      rMATSFiles: "rMATS files",
      next: "Next",
      back: "Back",
      launchAnalysis: "Launch Analysis",
      groupLabels: "Group Labels",
      groupLabelsDescription:
        "These labels will appear in the IncLevel1 / IncLevel2 columns.",
      selectedGenes: "Selected mutated gene(s)",
    },
    loading: {
      title: "Analysis in progress…",
      subtitle:
        "Please wait, removing duplicates and prioritising splicing events…",
    },
  },
  analysisDetail: {
    breadcrumb: "Analyses",
    mutatedGenes: "Mutated gene(s):",
    highlightTop10: "Highlight Top 10",
    hideTop10: "Hide Top 10",
    showTop10: "Show Top 10 in list",
    top10Hidden: "Top 10 hidden",
    excel: "Excel",
    pdf: "PDF",
    top10: "Top 10",
    excelError: "Error during Excel export. Please try again.",
    pdfError: "Error generating PDF. Please try again.",
    loading: "Loading events…",
    filters: {
      allTypes: "All types",
      genePlaceholder: "Gene (e.g. PCBP1)",
      sortFdrAsc: "FDR ↑ ascending",
      sortFdrDesc: "FDR ↓ descending",
      sortPvalAsc: "p-value ↑",
      sortPvalDesc: "p-value ↓",
      sortDpsiDesc: "|ΔPSI| ↓ largest",
      sortDpsiAsc: "|ΔPSI| ↑ smallest",
      sortGeneAz: "Gene A→Z",
      incLevelVisible: "IncLevel visible",
      incLevelHidden: "IncLevel hidden",
      showIncLevel: "Show inclusion levels",
      hideIncLevel: "Hide inclusion levels",
      noFilter: "no filter",
      reset: "Reset",
    },
    top10Notice:
      "The <strong>Top 10 events ◈</strong> are selected using default rMATS thresholds (FDR &lt; 0.05, |ΔPSI| ≥ 0.1), ranked by FDR then |ΔPSI|. They are filtered like all other events when statistical thresholds are active. Use the <strong>Hide Top 10</strong> button to exclude them from the list.",
    legend: {
      deltaLabel: "ΔPSI:",
      positive: "positive → ↑ {{group}}",
      negative: "negative → ↑ {{group}}",
    },
    events: "event",
    eventsPlural: "events",
    candidateGenes: "Candidate genes",
    basket: {
      selected: "selected",
      deselect: "Deselect all",
      add: "Add ({{n}})",
      alreadyInBasket: "Already in basket",
      alreadyInBasketTitle: "All these events are already in the basket",
    },
  },
  eventTable: {
    rank: "◈",
    type: "Type",
    gene: "Gene",
    chr: "Chr",
    strand: "Strand",
    exonStart: "Exon start",
    exonEnd: "Exon end",
    fdr: "FDR",
    deltaPsi: "ΔPSI",
    direction: "Direction",
    absDeltaPsi: "|ΔPSI|",
    incLevel1: "IncLevel1",
    incLevel2: "IncLevel2",
  },
  basket: {
    openBasket: "Open basket",
    title: "Basket",
    header: "Basket — {{n}} event",
    headerPlural: "Basket — {{n}} events",
    subtitle: "Select events then launch deep analysis.",
    close: "Close",
    top10Notice:
      "The <strong>Top 10 events</strong> will always be included in the continued analysis, regardless of the basket events.",
    empty: {
      title: "The basket is empty.",
      subtitle:
        "Select events from the list and click <strong>Add to basket</strong>.",
    },
    event: "event",
    eventPlural: "events",
    remove: "Remove from basket",
    continueAnalysis: "Continue Analysis",
    clearBasket: "Empty basket",
  },
  analysisOptions: {
    title: "Continue Analysis",
    alwaysIncluded: "Always included",
    alwaysIncludedModules: {
      gene: "Gene & Location",
      go: "Gene Ontology (GO)",
      panelapp: "PanelApp Australia",
      scores: "rMATS Scores",
    },
    optionalModules: "Optional modules",
    modules: {
      stringdb: {
        label: "STRING-DB & protein interactions",
        description:
          "Interaction network between the mutated gene and genes carrying events",
      },
      pathways: {
        label: "Molecular Pathways",
        description: "Pathway enrichment (KEGG / Reactome) — coming soon",
      },
      motifs: {
        label: "Recurrent Motifs",
        description:
          "Recurrent splicing motif analysis on the selection — coming soon",
      },
      splice: {
        label: "Consensus Splice Sites",
        description: "5′/3′ site strength and branch point — coming soon",
      },
    },
    basketEventsPrefix: "{{n}} basket event",
    basketEventsPrefixPlural: "{{n}} basket events",
    top10AlwaysIncluded:
      "will always be included in the deep analysis.",
    cancel: "Cancel",
    launch: "Launch Analysis",
  },
  sidebarNav: {
    collapse: "Collapse panel",
    expand: "Expand panel",
    tabs: {
      gene: "Gene",
      go: "GO / Ontology",
      scores: "rMATS Scores",
      interactions: "Interactions",
      pathways: "Mol. Pathways",
      motifs: "Recur. Motifs",
      splice: "Consensus Sites",
    },
  },
  annotatedCard: {
    gene: {
      ensg: "ENSG:",
      chr: "Chr:",
      exon: "Exon:",
      upstream: "Upstream:",
      downstream: "Downstream:",
      strand: "(strand {{s}})",
      viewEnsembl: "View on Ensembl",
    },
    go: {
      categories: {
        BP: "Biological Process",
        MF: "Molecular Function",
        CC: "Cellular Component",
      },
      noTerms: "No GO terms available.",
    },
    panelapp: {
      noPanel: "No PanelApp panel found.",
      diseasePanels: "Disease panels",
      viewPanelApp: "View on PanelApp AU",
      morePanels: "+{{n}} panel",
      morePanelsPlural: "+{{n}} panels",
    },
    scores: {
      meanPsi1: "Mean PSI G1",
      meanPsi2: "Mean PSI G2",
      counts: "Counts (first 3 samples)",
    },
    stringdb: {
      noSymbol: "Gene symbol not available.",
      selfInteraction:
        "The event gene is identical to the mutated gene — no interaction to display.",
      error: "Error retrieving STRING-DB data.",
      noInteraction: "No STRING-DB interaction found between these two genes.",
      combinedScore: "STRING combined score:",
      evidence: "Interaction evidence",
      publications: "Associated publications",
      openStringDB: "Open in STRING-DB",
    },
    comingSoon: "Coming soon",
    comingSoonModule: "The <strong>{{label}}</strong> module is under development.",
    basketEvent: "Basket event",
  },
  permutation: {
    iterations: "Number of iterations",
    moreIterations: "More iterations = more precise null distribution.",
    launch: "Run permutation test",
    running: "Computing ({{n}} iter.)…",
    error: "Computation error. Check that PSI data are available.",
    tabs: {
      delta_psi: {
        label: "ΔΨ",
        description: "PSI inclusion difference per event (per-event test).",
      },
      ppt_score: {
        label: "PPT Score",
        description:
          "Mean polypyrimidine score (% C/T in the 47 nt before 3′SS).",
      },
      exon_size: {
        label: "Exon Size",
        description: "Skipped exon size (normalised over observed range).",
      },
      frame_in_frame: {
        label: "Phase / In-frame",
        description: "Fraction of events predicted in-frame (skip of 3n nt).",
      },
      canonical_sites: {
        label: "GT-AG Sites",
        description:
          "Mean canonical splice site score (GT donor, AG acceptor).",
      },
    },
    results: {
      eventsTested: "Events tested",
      iterations: "Iterations",
      sig05: "Sig. p<0.05",
      sig01: "Sig. p<0.01",
      nullDistribution: "Null distribution of ΔΨ vs observed",
      topEvents: "Top most significant events",
      interpretation:
        "<strong>Interpretation:</strong> The blue distribution represents the null distribution under H₀ (random labels). The orange distribution represents the observed ΔΨ values. A shift toward extreme values (±1) indicates a genuine biological signal.",
      interpretationMetric:
        "<strong>Interpretation:</strong> The test compares events with ΔΨ &lt; 0 (exon more skipped in condition 2, group G1) vs ΔΨ &gt; 0 (exon more included, group G2). The observed statistic is mean(G2) − mean(G1). If the orange line falls in the tail of the blue distribution, the difference between the two groups is statistically significant.",
      method:
        "Bilateral permutation test — H₀: group labels are exchangeable — empirical p = (k+1)/(N+1) with continuity correction (Phipson & Smyth 2010). For auxiliary metrics, G1 (ΔΨ < 0) and G2 (ΔΨ > 0) groups are defined by the sign of the observed ΔΨ.",
      validEvents: "Valid events",
      g1: "G1 (ΔΨ<0)",
      g2: "G2 (ΔΨ>0)",
      observedDelta: "Observed Δ",
      empiricalP: "Empirical p",
      nullDistLabel: "Null distribution — {{label}}",
      insufficientData:
        "Insufficient data for this parameter (n={{n}} events with value).",
      requiresPermutation:
        "Run the permutation test to see this parameter. Splice features must be available (FASTA required for PPT).",
      gene: "Gene",
      observedDeltaPsi: "Observed ΔΨ",
      empiricalPValue: "Empirical p",
      nGroups: "N groups",
      significant: "Significant",
    },
    empty: {
      main: "Run the test to estimate the empirical significance of ΔΨ and splice signal properties.",
      params: "5 parameters tested: ΔΨ · PPT score · exon size · phase · GT-AG sites.",
    },
  },
};

export type Translations = typeof en;
