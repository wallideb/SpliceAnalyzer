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
    excelModal: {
      title: "Export Excel",
      description: "Select column groups to include in the spreadsheet. Splice analysis details are available in the PDF report.",
      groups: {
        core: "Core data",
        coreDesc: "Gene, coordinates, rMATS statistics (FDR, ΔΨ, PSI), splice features (GT-AG, PPT, branch point), MANE transcript, reading frame",
        panelapp: "PanelApp",
        panelappDesc: "Disease panel confidence and panel names from PanelApp Australia (Martin et al., 2019)",
        go: "Gene Ontology",
        goDesc: "Top GO terms (Biological Process / Molecular Function / Cellular Component) via mygene.info (GO Consortium, 2021)",
        stringdb: "STRING-DB",
        stringdbDesc: "Highest protein interaction score vs analysis mutated genes (Szklarczyk et al., 2023)",
      },
      spliceNote: "Splice-site logos, PPT tracks, and permutation test results are available in the PDF report — they cannot be exported to Excel.",
      download: "Download Excel",
      cancel: "Cancel",
    },
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
    noResults: "No results",
    downloadSvg: "Download logo as SVG",
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
          "GT-AG canonical sites, PPT score, branch point, reading frame — SE events only",
      },
      splice: {
        label: "Consensus Splice Sites",
        description: "Per-event 5′/3′ site sequences, PPT track & MANE transcript diagram",
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
    direction: {
      skippingUp: "↑ Exon skipping in {{group}}",
    },
  },
  motifPanel: {
    notComputed: "Pattern analysis not yet computed",
    notComputedDesc: "Compute splice features for the {{n}} SE events of this analysis to visualise recurring patterns (GT-AG sites, PPT, branch point, reading frame).",
    computeBtn: "Compute features",
    computing: "Computing…",
    computingDesc: "Fetching splice-site sequences via Ensembl REST — this may take a few tens of seconds.",
    computeError: "Computation error. Please retry.",
    thresholds: "Significance thresholds:",
    modify: "Modify",
    thresholdsTitle: "Significance thresholds — deep analysis",
    thresholdsDesc: "These thresholds define which SE events are considered significant (Y=1) vs non-significant (Y=0). This enables molecular pattern comparison between the two groups to identify splicing signatures.",
    significantChip: "Significant (Y=1)",
    notSignificantChip: "Non-sig. (Y=0)",
    nonSeNotice: "{{n}} non-SE event(s) excluded from motif/logo analysis (SE only)",
    close: "Close ×",
    fastaNotAvailable: "FASTA not available — sizes from coordinates only",
    summarySeEvents: "SE Events",
    summaryAnalyzed: "Analyzed (seq.)",
    summaryClusters: "Clusters",
    sectionConsensus: "Consensus exon — cohort overview",
    sectionExonSizes: "Skipped exon size distribution (nt)",
    statMean: "Mean",
    statMedian: "Med.",
    sectionDonor: "5'SS donor site — {{n}} sequences · {{pct}}% canonical GT",
    sectionAcceptor: "3'SS acceptor site — {{n}} sequences · {{pct}}% canonical AG",
    iupacConsensus: "IUPAC consensus:",
    sectionPpt: "PPT zone — mean score {{pct}}% · longest Y run: {{run}} nt",
    sectionFrame: "Reading frame class (skipped exon)",
    frameLabelNonCoding: "Non-coding",
    frameLabelUnknown: "Unknown",
    sectionBp: "Branch point detection (YNYURAY motif)",
    bpDetected: "detected",
    histogramAriaLabel: "Skipped exon size distribution",
    histogramBinTitle: "{{start}}–{{end}} nt: {{count}} events",
    histogramAxisTitle: "Size (nt)",
    histogramMeanLabel: "Avg. {{n}} nt",
    histogramMedianLabel: "Med. {{n}} nt",
    histogramLegendMean: "Mean",
    histogramLegendMedian: "Median",
    histogramTooltipEvents: "events",
  },
  spliceSiteTrack: {
    header: "Splice sites — 4 junctions of the skipped exon",
    skippedExon: "Skipped exon",
    flankingExons: "Flanking exons",
    notAvailable: "Sequences not available",
    notAvailableDesc: "Neither local FASTA nor Ensembl REST returned sequences for this event. Check network connectivity or index a local reference genome.",
    donor5ss: "5′SS donor — {{label}} → intron  (canonical GT at +1/+2)",
    acceptor3ss: "3′SS acceptor — intron → {{label}}  (canonical AG at −2/−1)",
    skippedExonLabel: "skipped exon",
    upstreamExonLabel: "upstream exon",
    downstreamExonLabel: "downstream exon",
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
  scienceNotes: {
    consensusLogo: {
      title: "Method — Sequence logos & information content",
      body:
        "Each column of the logo represents a position in the splice-site window. " +
        "Letter height is proportional to <b>p<sub>i</sub> × IC</b>, where " +
        "<b>IC = 2 − H(p)</b> bits and H(p) = −Σ p<sub>i</sub> log<sub>2</sub>(p<sub>i</sub>) " +
        "is the Shannon entropy at that position (Shannon, 1948). " +
        "The y-axis runs from 0 to 2 bits; a fully conserved position scores 2 bits. " +
        "The PWM (Position Weight Matrix) is computed from the observed base frequencies " +
        "at each position across all SE events in the analysis. " +
        "The canonical GT dinucleotide (positions +1/+2 of the 5′SS donor) and AG " +
        "(positions −2/−1 of the 3′SS acceptor) are highlighted in amber " +
        "(Shapiro &amp; Senapathy, 1987).",
    },
    pptTrack: {
      title: "Method — Polypyrimidine tract (PPT) & branch point",
      body:
        "The <b>polypyrimidine tract (PPT)</b> is a pyrimidine-rich region (~47 nt) " +
        "immediately upstream of the 3′ splice site. It is bound by U2AF65, which " +
        "recruits the spliceosome. The <b>PPT score</b> is the fraction of C or T " +
        "nucleotides in this window (Coolidge et al., 1997). " +
        "The longest consecutive pyrimidine run is annotated below the sequence. " +
        "The <b>branch point</b> is the adenosine involved in the first " +
        "transesterification step; it is detected by searching for the consensus " +
        "heptamer <b>YNYURAY</b> (Y=C/T, N=any, R=A/G) within the PPT region " +
        "(Padgett et al., 1986). Distance is reported as nucleotides upstream of the 3′SS.",
    },
    motifPattern: {
      title: "Method — Aggregate splice-signal analysis",
      body:
        "This panel aggregates splice-site signals across all SE events in the analysis. " +
        "Sequence logos use the WebLogo convention (Schneider &amp; Stephens, 1990): " +
        "IC = 2 − H(p) bits per position. " +
        "The exon-size histogram bins exon lengths in 25 nt intervals. " +
        "<b>Frame classification</b> is based on whether the CDS length of the skipped " +
        "exon is divisible by 3 (in_frame) or not (frameshift). " +
        "The PPT score distribution shows the fraction of pyrimidine nucleotides " +
        "per event in the ~47 nt window upstream of the 3′SS (Coolidge et al., 1997). " +
        "Branch-point detection uses the YNYURAY heptamer motif (Padgett et al., 1986).",
    },
    permutation: {
      title: "Method — Bilateral permutation test",
      body:
        "The empirical p-value is computed as <b>p = (k+1)/(N+1)</b>, where k is the " +
        "number of permuted statistics equal to or more extreme than the observed " +
        "statistic, and N is the total number of permutations. The +1 continuity " +
        "correction ensures that p is never exactly 0 (Phipson &amp; Smyth, 2010). " +
        "Under H₀, group labels are exchangeable (bilateral test). " +
        "For the ΔΨ tab, the observed statistic is the absolute mean ΔΨ across events. " +
        "For auxiliary metrics (PPT, exon size, frame, GT-AG), events are split into " +
        "G1 (ΔΨ &lt; 0) and G2 (ΔΨ &gt; 0), and the statistic is mean(G2) − mean(G1). " +
        "rMATS FDR values use the Benjamini-Hochberg correction " +
        "(Benjamini &amp; Hochberg, 1995).",
    },
    exonDiagram: {
      title: "Method — rMATS SE event definition",
      body:
        "A <b>Skipped Exon (SE)</b> event is defined by rMATS as a cassette exon " +
        "flanked by upstream and downstream constitutive exons. " +
        "<b>ΔΨ = PSI<sub>G2</sub> − PSI<sub>G1</sub></b>; positive values indicate " +
        "more inclusion in Group 2. PSI (Percent Spliced In) is estimated from " +
        "inclusion junction counts (IJC) and skipping junction counts (SJC) using " +
        "the rMATS probabilistic model (Shen et al., 2014). " +
        "FDR is the Benjamini-Hochberg-corrected p-value. " +
        "The MANE Select transcript (Morales et al., 2022) is used for exon mapping " +
        "and frame classification.",
    },
  },
  spliceView: {
    nonSeEventTitle: "{{type}} event",
    nonSeEventDesc: "Canonical site analysis (5′SS GT, 3′SS AG, PPT, branch point) is restricted to SE (exon skipping) events. Statistical data (FDR, ΔΨ) remain available in other tabs.",
    notComputed: "Features not yet computed for this event.",
    computing: "Computing…",
    computeBtn: "Compute features",
  },
  mutatedGenePanel: {
    noContext: "Analysis context not available.",
    noGoTerms: "No GO terms available.",
    noPanelApp: "No PanelApp panel found.",
    goCategories: {
      BP: "Biol. Process",
      MF: "Mol. Function",
      CC: "Cell. Component",
    },
    tabs: {
      gene: "Gene",
      go: "GO",
      panelapp: "PanelApp",
      scores: "rMATS Scores",
    },
    noGeneSelected: "No candidate gene selected for this analysis",
    noGeneSubtext: "Add a mutated gene when creating or editing the analysis to enable annotations and the STRING-DB Interactions tab.",
    candidateGene: "Candidate gene",
    candidateGenes: "Candidate genes",
    clickTabToExplore: "— click a tab to explore annotations",
    viewOnEnsembl: "View on Ensembl",
    sigEvents: "Significant events",
    totalEvents: "Total events",
    allCategories: "all categories",
    detailedScores: "Detailed scores available in the events table.",
    sectionLabel: "Candidate gene(s)",
  },
  consensusExon: {
    analyzed: "Analyzed",
    seEvents: "SE events",
    meanExon: "Mean exon",
    upstreamMedian: "Upstream ↑ med.",
    downstreamMedian: "Downstream ↓ med.",
    meanDeltaPsi: "Mean ΔΨ",
    meanPpt: "Mean PPT",
    consensusExonLabel: "Consensus fictional exon",
    noSeq: "(sequences unavailable — FASTA required)",
    frameLabelNonCoding: "Non-coding",
    sizeRange: "Sizes: {{min}}–{{max}} nt",
    description: "The consensus fictional exon represents the mean size of {{n}} SE events · introns = median · ΔΨ = mean · sequences = IUPAC consensus of the cohort PWM.",
  },
  exonDiagram: {
    upstreamFlankingExon: "Upstream flanking exon",
    downstreamFlankingExon: "Downstream flanking exon",
    hoverForSeq: "Hover to see full sequence",
    hoverForNuc: "Hover to see nucleotide composition",
    ariaLabel: "Skipped exon diagram",
    size: "Size: {{n}} nt",
    coords: "Coordinates: {{start}}–{{end}}",
    exonRank: "Exon rank: {{n}}",
    psiGroup1: "PSI group 1 (mean): {{v}}",
    psiGroup2: "PSI group 2 (mean): {{v}}",
    donor5ssCanonical: "5′SS donor site — canonical GT",
    donor5ssNonGt: "5′SS donor site ⚠ non-GT",
    donor5ss: "5′SS donor site",
    seq9nt: "9 nt sequence: {{seq}}",
    acceptor3ssCanonical: "3′SS acceptor site — canonical AG",
    acceptor3ssNonAg: "3′SS acceptor site ⚠ non-AG",
    acceptor3ss: "3′SS acceptor site",
    seq23nt: "23 nt sequence: {{seq}}",
    pptZone: "Polypyrimidine tract (PPT — 47 nt before 3′SS)",
    pptScore: "Y score: {{pct}}% — {{interp}}",
    pptSeq: "Sequence: {{seq}}",
    pptStrong: "Strong PPT",
    pptModerate: "Moderate PPT",
    pptWeak: "Weak PPT",
    bp: "Branch point (YNYURAY)",
    bpFound: "Found — ~{{dist}} nt before 3′SS",
    bpHoverDetail: "Hover to see detail",
    bpNotFound: "Not detected in PPT region",
    maneTranscript: "MANE transcript: {{id}}",
    maneNotFound: "MANE: not found",
  },
  deepAnalysis: {
    breadcrumb: "Deep Analysis",
    title: "Deep Analysis",
    backToEvents: "Back to events",
    top10AlwaysIncluded: "Top 10 — always included",
    basketCount: "+{{n}} from basket",
    optionalModulesActive: "{{n}} optional module active",
    optionalModulesActivePlural: "{{n}} optional modules active",
    eventTypes: "Event types:",
    seOnlyNotice: "Sequence analysis (motifs, logos, PPT) — SE events only",
    loading: "Loading events…",
    noEvents:
      "No events to display. Add events to the basket or verify that the analysis has data.",
    permutationTitle: "Significance by permutation",
  },
};

export type Translations = typeof en;
