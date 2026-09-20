/**
 * French locale dictionary — mirrors the English structure exactly.
 */
import type { Translations } from "./en";

export const fr: Translations = {
  header: {
    themeLight: "Passer en mode clair",
    themeDark: "Passer en mode sombre",
    toggleTheme: "Basculer le thème",
    userAccount: "Compte utilisateur (authentification à venir)",
  },
  analyses: {
    title: "Mes analyses",
    subtitle: "Explorez et gérez vos analyses d'épissage différentiel rMATS",
    newAnalysis: "Nouvelle analyse",
    loading: "Chargement...",
    error: "Erreur : {{message}}",
    empty: {
      title: "Aucune analyse",
      subtitle: "Importez vos fichiers rMATS pour commencer.",
      cta: "Créer ma première analyse",
    },
    mutatedGenes: "Gène(s) candidat(s) :",
    share: {
      copy: "Partager l'analyse (copier le lien)",
      copied: "Lien copié !",
    },
    delete: "Supprimer l'analyse",
    confirmDelete: "Supprimer l'analyse « {{name}} » ?",
    status: {
      ready: "Prête",
      processing: "En cours",
      error: "Erreur",
    },
  },
  newAnalysis: {
    title: "Nouvelle analyse",
    subtitle: "Importez vos fichiers rMATS et configurez votre analyse",
    steps: {
      filesGenes: "Fichiers & gènes",
      groups: "Groupes",
    },
    form: {
      analysisName: "Nom de l'analyse",
      analysisNamePlaceholder: "Ex: PCBP1 cohort 2024",
      mutatedGenes: "Gène(s) candidat(s) dans la cohorte",
      mutatedGenesNomenclature: "(nomenclature HUGO)",
      mutatedGenesDescription:
        "Ces gènes seront affichés dans l'analyse même s'ils n'apparaissent pas dans les anomalies d'épissage détectées. L'identifiant Ensembl (ENSG) est récupéré automatiquement.",
      rMATSFiles: "Fichiers rMATS",
      next: "Suivant",
      back: "Retour",
      launchAnalysis: "Lancer l'analyse",
      groupLabels: "Labels des groupes",
      groupLabelsDescription:
        "Ces labels apparaîtront dans les colonnes IncLevel1 / IncLevel2.",
      selectedGenes: "Gène(s) candidat(s) sélectionné(s)",
    },
    warnings: {
      title: "Remarques d'import",
      subtitle: "L'analyse a été créée, mais l'import a signalé les points suivants :",
      open: "Ouvrir l'analyse",
    },
    loading: {
      title: "Analyse en cours…",
      subtitle:
        "Veuillez patienter, suppression des duplicats et priorisation des événements d'épissage…",
      uploading: "Envoi des fichiers… {{percent}} %",
      uploadHint:
        "Les fichiers sont envoyés par petits morceaux afin que les sorties rMATS volumineuses passent les proxys limitant la taille des requêtes.",
      sending: "Envoi de {{file}} ({{sent}} / {{total}})",
      processing: "Traitement en cours… {{total}} reçus, le serveur analyse et enregistre les événements.",
    },
  },
  analysisDetail: {
    breadcrumb: "Analyses",
    mutatedGenes: "Gène(s) candidat(s) :",
    excel: "Excel",
    pdf: "PDF",
    deepAnalysis: "Analyse approfondie",
    excelError: "Erreur lors de l'export Excel. Veuillez réessayer.",
    pdfError: "Erreur lors de la génération du PDF. Veuillez réessayer.",
    pdfComputeInProgress: "Le calcul des features de splicing est encore en cours. Le PDF sera disponible une fois terminé.",
    pdfModal: {
      title: "Export du rapport PDF",
      description: "Sélectionnez les sections à inclure dans le rapport PDF généré. Les sections désélectionnées et leurs calculs associés seront ignorés.",
      selectAll: "Sélectionner / désélectionner tout",
      sections: {
        a: "A. Résumé global de l'analyse",
        aDesc: "Statistiques résumées, figures de distribution et logos de sites d'épissage pour tous les événements",
        b: "B. Résumé des événements significatifs",
        bDesc: "Statistiques et figures restreintes aux événements significatifs (seuils FDR/PSI)",
        c: "C. Comparaison significatif vs non-significatif",
        cDesc: "Tableau de comparaison des caractéristiques et logos entre les groupes significatifs et non-significatifs",
        d: "D. Test de permutation",
        dDesc: "Significativité empirique de la distribution des scores ΔΨ observés (500 itérations)",
        e: "E. Enrichissement en motifs hnRNP",
        eDesc: "Analyse d'enrichissement des motifs de protéines de liaison à l'ARN hnRNP inspirée de rMAPS2 avec heatmap",
        f: "F. Enrichissement Enrichr",
        fDesc: "Enrichissement de jeux de gènes contre les bibliothèques KEGG, GO, Reactome et WikiPathways",
        topEvents: "Tableau des événements d'épissage principaux",
        topEventsDesc: "Top 20 des événements SE significatifs classés par FDR et |ΔΨ|",
      },
      download: "Télécharger PDF",
      cancel: "Annuler",
    },
    excelModal: {
      title: "Export Excel",
      description: "Sélectionnez les groupes de colonnes à inclure dans le tableur. Les détails de l'analyse d'épissage sont disponibles dans le rapport PDF.",
      groups: {
        core: "Données de base",
        coreDesc: "Gène, coordonnées, statistiques rMATS (FDR, ΔΨ, PSI), features d'épissage (GT-AG, PPT, point de branchement), transcrit MANE, cadre de lecture",
        panelapp: "PanelApp",
        panelappDesc: "Confiance du panel de maladie et noms des panels depuis PanelApp Australia (Martin et al., 2019)",
        go: "Gene Ontology",
        goDesc: "Termes GO principaux (Processus biologique / Fonction moléculaire / Composant cellulaire) via mygene.info (GO Consortium, 2021)",
        stringdb: "STRING-DB",
        stringdbDesc: "Score d'interaction protéique maximal vs gènes candidats de l'analyse (Szklarczyk et al., 2023)",
      },
      spliceNote: "Les logos de sites d'épissage, les tracks PPT et les tests de permutation sont disponibles dans le rapport PDF — ils ne peuvent pas être exportés en Excel.",
      download: "Télécharger Excel",
      cancel: "Annuler",
    },
    loading: "Chargement des événements…",
    loadingAnalysis: "Récupération des métadonnées…",
    loadingEvents: "Chargement de la première page…",
    filters: {
      allTypes: "Tous les types",
      genePlaceholder: "Gène (ex: PCBP1)",
      sortFdrAsc: "FDR ↑ croissant",
      sortFdrDesc: "FDR ↓ décroissant",
      sortPvalAsc: "p-value ↑",
      sortPvalDesc: "p-value ↓",
      sortDpsiDesc: "|ΔΨ| ↓ plus grand",
      sortDpsiAsc: "|ΔΨ| ↑ plus petit",
      sortGeneAz: "Gène A→Z",
      sortGeneZa: "Gène Z→A",
      incLevelVisible: "IncLevel visible",
      incLevelHidden: "IncLevel masqué",
      showIncLevel: "Afficher les niveaux d'inclusion",
      hideIncLevel: "Masquer les niveaux d'inclusion",
      noFilter: "aucun filtre",
      reset: "Réinitialiser",
    },
    legend: {
      deltaLabel: "ΔΨ :",
      positive: "positif → ↑ {{group}}",
      negative: "négatif → ↑ {{group}}",
    },
    events: "événement",
    eventsPlural: "événements",
    candidateGenes: "Gènes candidats",
  },
  eventTable: {
    type: "Type",
    gene: "Gène",
    chr: "Chr",
    strand: "Brin",
    exonStart: "Exon start",
    exonEnd: "Exon end",
    fdr: "FDR",
    deltaPsi: "ΔΨ",
    direction: "Direction",
    absDeltaPsi: "|ΔΨ|",
    incLevel1: "IncLevel1",
    incLevel2: "IncLevel2",
    noResults: "Aucun résultat",
    downloadSvg: "Télécharger le logo en SVG",
    result: "résultat",
    resultPlural: "résultats",
    firstPage: "Première page",
    prev: "Préc.",
    next: "Suiv.",
    lastPage: "Dernière page",
    loading: "Chargement…",
  },
  top10View: {
    noEvents: "Aucun événement trouvé.",
    modeLabels: {
      gene: "Événements annotés",
      stringdb: "Interactions STRING-DB avec le gène candidat",
      motifs: "Patterns d'épissage récurrents",
      splice: "Sites consensus d'épissage",
      hnrnp: "Enrichissement de motifs hnRNP (inspiré rMAPS2)",
      enrichr: "Enrichissement de voies Enrichr",
    },
    sortBy: "Trier par :",
    sortOptions: {
      default: "Ordre par défaut",
      fdr: "FDR (croissant)",
      pvalue: "p-value (croissant)",
      deltaPsi: "|ΔΨ| (décroissant)",
      chr: "Chromosome",
      panelapp: "Confiance PanelApp",
    },
    noAnalysisId: "analysisId non disponible pour ce contexte.",
    noDeepAnalysis: "Cette analyse nécessite une analyse approfondie sauvegardée.",
    stringdbSource: "Source :",
    stringdbDesc: "STRING-DB v12 · réseau de preuve d'interaction protéine–protéine · cliquez sur l'image pour ouvrir STRING.",
  },
  sidebarNav: {
    collapse: "Masquer le volet",
    expand: "Afficher le volet",
    tabs: {
      gene: "Événement",
      annotatedEvents: "Événements annotés",
      interactions: "Interactions",
      motifs: "Motifs récur.",
      splice: "Sites consensus",
      hnrnp: "Motifs hnRNP",
      enrichr: "Enrichr",
    },
  },
  annotatedCard: {
    gene: {
      ensg: "ENSG :",
      chr: "Chr :",
      exon: "Exon :",
      upstream: "Upstream :",
      downstream: "Downstream :",
      strand: "(brin {{s}})",
      viewEnsembl: "Voir sur Ensembl",
    },
    go: {
      categories: {
        BP: "Processus biologique",
        MF: "Fonction moléculaire",
        CC: "Composant cellulaire",
      },
      noTerms: "Aucun terme GO disponible.",
    },
    panelapp: {
      noPanel: "Aucun panel PanelApp trouvé.",
      diseasePanels: "Panels de maladie",
      viewPanelApp: "Voir sur PanelApp AU",
      morePanels: "+{{n}} panel",
      morePanelsPlural: "+{{n}} panels",
    },
    scores: {
      meanPsi1: "PSI moy. G1",
      meanPsi2: "PSI moy. G2",
      counts: "Comptages (3 premiers échantillons)",
    },
    stringdb: {
      noSymbol: "Symbole du gène non disponible.",
      selfInteraction:
        "Le gène porteur de l'événement est identique au gène candidat — pas d'interaction à afficher.",
      error: "Erreur lors de la récupération des données STRING-DB.",
      noInteraction:
        "Aucune interaction STRING-DB trouvée entre ces deux gènes.",
      combinedScore: "Score combiné STRING :",
      evidence: "Preuves d'interaction",
      publications: "Publications associées",
      openStringDB: "Ouvrir dans STRING-DB",
    },
    direction: {
      skippingUp: "↑ Saut chez {{group}}",
    },
    splice: {
      showDiagram: "Afficher le diagramme",
      hideDiagram: "Masquer le diagramme",
    },
  },
  motifPanel: {
    notComputed: "Analyse de patterns non calculée",
    notComputedDesc: "Calculez les features d'épissage pour les {{n}} événements SE de cette analyse afin de visualiser les patterns récurrents (sites GT-AG, PPT, point de branchement, classe de cadre de lecture).",
    computeBtn: "Calculer les features",
    computing: "Calcul en cours…",
    computingDesc: "Requêtes aux sites d'épissage via Ensembl REST — cette opération peut prendre quelques dizaines de secondes.",
    computeError: "Erreur lors du calcul. Réessayez.",
    computeFailed: "Le calcul en arrière-plan s'est terminé avec une erreur : {{error}}",
    thresholds: "Seuils de significativité :",
    significantOnly: "événements significatifs uniquement",
    modify: "Modifier",
    thresholdsTitle: "Seuils de significativité — analyse approfondie",
    thresholdsDesc: "Ces seuils définissent quels événements SE sont considérés comme significatifs (Y=1) vs non-significatifs (Y=0). Ils permettront de comparer les patterns moléculaires entre les deux groupes pour identifier des signatures d'épissage.",
    significantChip: "Significatifs (Y=1)",
    notSignificantChip: "Non-sig. (Y=0)",
    nonSeNotice: "{{n}} événement(s) non-SE exclus de l'analyse motifs/logos (SE uniquement)",
    close: "Fermer ×",
    fastaNotAvailable: "FASTA non disponible — tailles depuis coords uniquement",
    summarySeEvents: "Événements SE",
    summaryAnalyzed: "Analysés (seq.)",
    sectionConsensus: "Exon consensus — vue d'ensemble cohorte",
    sectionExonSizes: "Distribution des tailles d'exons sautés (nt)",
    statMean: "Moy.",
    statMedian: "Méd.",
    sectionDonor: "Site donneur 5'SS — {{n}} séquences · {{pct}}% GT canonique",
    sectionAcceptor: "Site accepteur 3'SS — {{n}} séquences · {{pct}}% AG canonique",
    iupacConsensus: "Consensus IUPAC :",
    sectionPpt: "Zone PPT — score moyen {{pct}}% · run Y le plus long : {{run}} nt",
    sectionFrame: "Classe de cadre de lecture (exon sauté)",
    frameLabelNonCoding: "Non-codant",
    frameLabelUnknown: "Inconnu",
    sectionComparison: "Comparaison — Significatifs vs Non-significatifs",
    sectionFrameComparison: "Cadre de lecture — Significatifs vs Non-significatifs",
    sectionBp: "Branch point detection (YNYURAY motif)",
    bpDetected: "détectés",
    histogramAriaLabel: "Distribution des tailles d'exons sautés",
    histogramBinTitle: "{{start}}–{{end}} nt : {{count}} événements",
    histogramAxisTitle: "Taille (nt)",
    histogramMeanLabel: "Moy. {{n}} nt",
    histogramMedianLabel: "Méd. {{n}} nt",
    histogramLegendMean: "Moyenne",
    histogramLegendMedian: "Médiane",
    histogramTooltipEvents: "évén.",
    colPValue: "p-value",
    colQValue: "q (BH)",
    mwuSuffix: "(Mann-Whitney)",
    legendQ: "q < 0,05 (BH)",
    legendTests: "{{n}} tests, correction BH · survolez p pour le nom du test",
  },
  spliceSiteTrack: {
    header: "Sites d'épissage — 4 jonctions de l'exon sauté",
    skippedExon: "Exon sauté",
    flankingExons: "Exons flanquants",
    notAvailable: "Séquences non disponibles",
    notAvailableDesc: "Ni FASTA local ni Ensembl REST n'ont retourné de séquences pour cet événement. Vérifiez la connexion réseau ou indexez un génome de référence local.",
    donor5ss: "5'SS donneur — {{label}} → intron  (GT canonique en +1/+2)",
    acceptor3ss: "3'SS accepteur — intron → {{label}}  (AG canonique en −2/−1)",
    skippedExonLabel: "exon sauté",
    upstreamExonLabel: "exon amont",
    downstreamExonLabel: "exon aval",
  },
  pptTrack: {
    bpDetected: "✓ Point de branchement ({{motif}}) détecté — BP −{{dist}} nt du début de l'exon (3′SS)",
    bpNotDetected: "— Point de branchement (YNYURAY) non détecté dans la fenêtre PPT",
    bpCellTitle: "Adénosine du point de branchement — motif {{motif}} — {{dist}} nt en amont du début de l'exon",
  },
  maneTrack: {
    title: "Transcrit MANE Select",
    notFound: "Transcrit MANE non trouvé pour cet événement.",
    structureNotAvailable: "Structure du transcrit non disponible.",
    skippedExon: "Exon sauté",
    otherExons: "Autres exons",
    widthNote: "Largeur ∝ taille exon · introns compressés",
    exonLabel: "Exon {{rank}} / {{total}}",
    sizeLabel: "Taille : {{size}} nt",
    coordsLabel: "Coordonnées : {{start}}–{{end}}",
    skippedLabel: "★ Exon sauté",
  },
  permutation: {
    iterations: "Nombre d'itérations",
    moreIterations: "Plus d'itérations = distribution nulle plus précise.",
    launch: "Lancer le test de permutation",
    running: "Calcul en cours ({{n}} itér.)…",
    error:
      "Erreur lors du calcul. Vérifiez que les données PSI sont disponibles.",
    results: {
      eventsTested: "Événements testés",
      totalEvents: "Total événements (permutés)",
      iterations: "Itérations",
      sig05: "Sig. p<0.05",
      sig01: "Sig. p<0.01",
      nullDistribution: "Distribution des ΔΨ sous H₀ vs observés",
      topEvents: "Top événements les plus significatifs",
      interpretation:
        "<strong>Interprétation :</strong> La distribution bleue représente la distribution nulle sous H₀ (labels aléatoires). La distribution orange représente les ΔΨ observés. Un déplacement vers des valeurs extrêmes (±1) indique un signal biologique réel.",
      interpretationMetric:
        "<strong>Interprétation :</strong> La statistique observée (ligne orange) est comparée à la distribution nulle (bleue). Si la ligne orange est dans la queue de la distribution bleue, la différence observée est statistiquement significative.",
      method:
        "Test de permutation bilatéral — H₀ : les étiquettes de groupe sont interchangeables — p empirique = (k+1)/(N+1) avec correction de continuité (Phipson & Smyth 2010).",
      validEvents: "Événements valides",
      observedDelta: "Δ observé",
      empiricalP: "p empirique",
      metric: "Métrique",
      metricTitle: "Tests de permutation sur métriques agrégées",
      exactBadge: "exact",
      exactSplits: "énumération exacte des {{n}} répartitions d'étiquettes",
      exactFraction: "Énumération exacte",
      exactFractionHint: "{{pct}} % des événements testés avec énumération de toutes les répartitions (sans tirage Monte-Carlo)",
      minPAttainable: "p min. atteignable",
      replicates: "Réplicats G1 / G2",
      lowResolution:
        "Avec n₁={{n1}} et n₂={{n2}} réplicats, seules {{n}} permutations distinctes existent ; la plus petite p-value atteignable est {{p}}. Les p-values par événement ne peuvent pas atteindre les seuils de significativité usuels — interprétez plutôt la distribution nulle globale.",
      gene: "Gène",
      observedDeltaPsi: "ΔΨ observé",
      empiricalPValue: "p empirique",
      nGroups: "N groupes",
      significant: "Significatif",
    },
    empty: {
      main: "Lancez le test pour estimer la significativité empirique de la distribution des scores ΔΨ.",
      params: "",
    },
  },
  scienceNotes: {
    consensusLogo: {
      title: "Méthode — Logos de séquences & contenu informationnel",
      body:
        "Chaque colonne du logo représente une position dans la fenêtre du site d'épissage. " +
        "La hauteur des lettres est proportionnelle à <b>p<sub>i</sub> × IC</b>, où " +
        "<b>IC = 2 − H(p)</b> bits et H(p) = −Σ p<sub>i</sub> log<sub>2</sub>(p<sub>i</sub>) " +
        "est l'entropie de Shannon à cette position (Shannon, 1948). " +
        "L'axe Y va de 0 à 2 bits ; une position entièrement conservée score 2 bits. " +
        "La PWM (Position Weight Matrix) est calculée à partir des fréquences de bases " +
        "observées à chaque position sur l'ensemble des événements SE de l'analyse. " +
        "Le dinucléotide canonique GT (positions +1/+2 du site donneur 5′SS) et AG " +
        "(positions −2/−1 du site accepteur 3′SS) sont surlignés en ambre " +
        "(Shapiro &amp; Senapathy, 1987).",
    },
    pptTrack: {
      title: "Méthode — Tract polypyrimidique (PPT) & point de branchement",
      body:
        "Le <b>tract polypyrimidique (PPT)</b> est une région riche en pyrimidines (~47 nt) " +
        "immédiatement en amont du site d'épissage 3′. Il est lié par U2AF65, qui " +
        "recrute le spliceosome. Le <b>score PPT</b> est la fraction de nucléotides " +
        "C ou T dans cette fenêtre (Coolidge et al., 1997). " +
        "La plus longue série consécutive de pyrimidines est annotée sous la séquence. " +
        "Le <b>point de branchement</b> est l'adénosine impliquée dans la première " +
        "étape de transestérification ; il est détecté par recherche du motif consensus " +
        "heptamère <b>YNYURAY</b> (Y=C/T, N=quelconque, R=A/G) dans la région PPT " +
        "(Padgett et al., 1986). La distance est indiquée en nucléotides en amont du 3′SS.",
    },
    motifPattern: {
      title: "Méthode — Analyse agrégée des signaux d'épissage",
      body:
        "Ce panneau agrège les signaux de sites d'épissage sur l'ensemble des événements SE de l'analyse. " +
        "Les logos de séquences suivent la convention WebLogo (Schneider &amp; Stephens, 1990) : " +
        "IC = 2 − H(p) bits par position. " +
        "L'histogramme de taille d'exon regroupe les longueurs en intervalles de 25 nt. " +
        "La <b>classification du cadre</b> est basée sur la divisibilité par 3 de la longueur " +
        "CDS de l'exon sauté (in_frame) ou non (frameshift). " +
        "Note : un frameshift n'implique pas le NMD (nonsense-mediated decay) ; le NMD dépend de " +
        "la position du codon stop prématuré par rapport à la dernière jonction exon-exon. " +
        "La distribution du score PPT montre la fraction de nucléotides pyrimidiques " +
        "par événement dans la fenêtre ~47 nt en amont du 3′SS (Coolidge et al., 1997). " +
        "La détection du point de branchement utilise le motif heptamère YNYURAY (Padgett et al., 1986).",
    },
    permutation: {
      title: "Méthode — Test de permutation bilatéral",
      body:
        "La p-value empirique est calculée comme <b>p = (k+1)/(N+1)</b>, où k est le nombre " +
        "de statistiques permutées égales ou plus extrêmes que la statistique observée, " +
        "et N est le nombre total de permutations. La correction de continuité +1 garantit " +
        "que p n'est jamais exactement 0 (Phipson &amp; Smyth, 2010). " +
        "Sous H₀, les étiquettes de groupe sont interchangeables (test bilatéral). " +
        "La statistique observée est la moyenne absolue des ΔΨ sur les événements. " +
        "Les valeurs FDR de rMATS utilisent la correction de Benjamini-Hochberg " +
        "(Benjamini &amp; Hochberg, 1995).",
    },
    hnrnpMotifs: {
      title: "Méthode — Analyse d'enrichissement de motifs hnRNP",
      body:
        "Inspirée de rMAPS2 (Hwang et al., NAR 2020 ; 48:W300-W306), cette analyse recherche " +
        "dans sept régions génomiques autour de chaque exon sauté (jusqu'à 250 nt flanquants des exons amont " +
        "et aval, corps de l'exon sauté, et pour chaque intron flanquant les 250 nt après le 5′ss " +
        "et les 250 nt avant le 3′ss) 19 motifs consensus connus de protéines " +
        "de liaison à l'ARN de la famille hnRNP, réparties en huit familles protéiques. " +
        "Les motifs incluent hnRNP A1/A2 (TAGG, TAGGG, TAGGGA, AGG), " +
        "hnRNP E — PCBP1/E1 (CCWWHCC = CC[AT][AT][ACT]CC) et PCBP2/E2 (CCYYCCH = CC[CT][CT]CC[ACT], " +
        "tous deux issus du Tableau S2 supplémentaire de rMAPS2, Homo sapiens), " +
        "hnRNP F/H (GGGG, GGG), hnRNP K (CCCC, TCCC), hnRNP C (TTTTT, TTTT), " +
        "hnRNP L (CACA, ACAC), hnRNP M (TGTG, GTGT) et PTB/hnRNP I (TCTT, TCTCT, CTCT). " +
        "Les séquences de motifs proviennent de CISBP-RNA (Ray et al., Nature 2013) et d'études " +
        "publiées (Martinez-Contreras et al., 2006 ; Chkheidze et al., Mol Cell Biol 1999 ; " +
        "Makeyev &amp; Liebhaber, RNA 2002). " +
        "Les régions introniques excluent les 6 nt du 5'SS et les 20 nt du 3'SS, suivant la convention " +
        "rMAPS2 (ces régions sont fortement contraintes par les signaux de sites d'épissage). " +
        "rMAPS2 utilise une fenêtre glissante (50 pb) avec test de Wilcoxon sur la densité de motifs ; " +
        "notre implémentation applique deux tests par motif × région : un test z de deux proportions " +
        "sur la présence du motif (qui sature pour les motifs courts sur des régions de 250 nt) et un " +
        "test de Mann-Whitney U sur la densité de motifs par événement. Les deux sont corrigés par " +
        "Benjamini-Hochberg ; une paire est déclarée significative si l'un des deux q < 0,05.",
    },
    geneOntology: {
      title: "Source — Annotations Gene Ontology",
      body:
        "Les termes GO (Processus biologique, Fonction moléculaire, Composant cellulaire) sont " +
        "récupérés pour le symbole du gène via mygene.info. Seuls les premiers termes de chaque " +
        "catégorie sont affichés ; le code de preuve apparaît au survol (GO Consortium, 2021).",
    },
    panelapp: {
      title: "Source — Panels de maladie PanelApp Australia",
      body:
        "Les panels proviennent de PanelApp Australia. La confiance gène–panel suit la notation " +
        "PanelApp : <b>vert</b> = niveau diagnostique (niveau 3), <b>ambre</b> = limite (niveau 2), " +
        "<b>rouge</b> = preuves insuffisantes (niveau 1) (Martin et al., 2019).",
    },
    stringdb: {
      title: "Source — Interactions protéine–protéine STRING",
      body:
        "L'interaction entre chaque gène candidat et le gène porteur de l'événement est interrogée " +
        "dans STRING v12. Le score combiné (0–1) intègre les canaux de preuve (expériences, bases " +
        "curatées, co-expression, fouille de texte, …) ; l'épaisseur des arcs est proportionnelle au " +
        "score de chaque canal (Szklarczyk et al., 2023). L'absence d'interaction dans STRING n'est " +
        "pas une preuve d'absence.",
    },
    enrichr: {
      title: "Méthode — Enrichissement de voies Enrichr",
      body:
        "Les symboles de gènes des événements significatifs sont soumis à l'API REST Enrichr " +
        "(Ma'ayan Lab, Icahn School of Medicine). L'enrichissement est calculé par rapport à des " +
        "bibliothèques de jeux de gènes curatées (KEGG 2021, GO Processus biologique, GO Fonction " +
        "moléculaire, Reactome 2022, WikiPathways 2023). Le score combiné intègre le z-score et " +
        "la p-value pour le classement. Référence : Chen et al., Enrichr, BMC Bioinformatics 2013.",
    },
    exonDiagram: {
      title: "Méthode — Définition d'un événement SE dans rMATS",
      body:
        "Un événement <b>Exon Sauté (SE)</b> est défini par rMATS comme un exon cassette " +
        "flanqué d'exons constitutifs amont et aval. " +
        "<b>ΔΨ = PSI<sub>G2</sub> − PSI<sub>G1</sub></b> ; les valeurs positives indiquent " +
        "une inclusion plus importante dans le Groupe 2. PSI (Percent Spliced In) est estimé " +
        "à partir des comptages de jonctions d'inclusion (IJC) et d'exclusion (SJC) en utilisant " +
        "le modèle probabiliste de rMATS (Shen et al., 2014). " +
        "Le FDR est la p-value corrigée par Benjamini-Hochberg. " +
        "Le transcrit MANE Select (Morales et al., 2022) est utilisé pour la cartographie " +
        "des exons et la classification du cadre de lecture.",
    },
  },
  spliceView: {
    nonSeEventTitle: "Événement {{type}}",
    nonSeEventDesc: "L'analyse de sites canoniques (5'SS GT, 3'SS AG, PPT, branchpoint) est restreinte aux événements SE (exon skipping). Les données statistiques (FDR, ΔΨ) restent disponibles dans les autres onglets.",
    notComputed: "Features non calculées pour cet événement.",
    computing: "Calcul…",
    computeBtn: "Calculer les features",
    computingDesc: "Récupération des séquences et calcul des features d'épissage pour tous les événements SE",
    computeError: "Le calcul des features d'épissage a échoué",
    computeErrorHint: "Consultez le journal du backend ; le calcul peut être relancé depuis une carte d'événement (« Compute features »).",
  },
  mutatedGenePanel: {
    noContext: "Contexte d'analyse non disponible.",
    noGoTerms: "Aucun terme GO disponible.",
    noPanelApp: "Aucun panel PanelApp trouvé.",
    goCategories: {
      BP: "Processus biol.",
      MF: "Fonction mol.",
      CC: "Composant cell.",
    },
    tabs: {
      gene: "Gène",
      go: "GO",
      panelapp: "PanelApp",
      scores: "Scores rMATS",
    },
    noGeneSelected: "Aucun gène candidat sélectionné lors de l'analyse",
    noGeneSubtext: "Ajoutez un gène candidat lors de la création ou modification de l'analyse pour activer les annotations et l'onglet Interactions STRING-DB.",
    candidateGene: "Gène candidat",
    candidateGenes: "Gènes candidats",
    clickTabToExplore: "— cliquez sur un onglet pour explorer les annotations",
    viewOnEnsembl: "Voir sur Ensembl",
    sigEvents: "Évén. significatifs",
    totalEvents: "Total événements",
    allCategories: "toutes catégories",
    detailedScores: "Scores détaillés disponibles dans le tableau des événements.",
    sectionLabel: "Gène(s) candidat(s)",
  },
  consensusExon: {
    analyzed: "Analysés",
    meanExon: "Exon moy.",
    upstreamMean: "Intron ↑ moy.",
    downstreamMean: "Intron ↓ moy.",
    seEvents: "Évén. SE",
    meanDeltaPsi: "ΔΨ moyen",
    meanPpt: "PPT moyen",
    consensusExonLabel: "Exon fictif consensus",
    noSeq: "(séquences non disponibles — FASTA requis)",
    frameLabelNonCoding: "Non-codant",
    sizeRange: "Tailles : {{min}}–{{max}} nt",
    description: "L'exon fictif consensus représente la taille moyenne des {{n}} événements SE · introns = moyenne · ΔΨ = moyenne · séquences = consensus IUPAC de la PWM cohorte.",
  },
  exonDiagram: {
    upstreamFlankingExon: "Exon flanquant amont",
    downstreamFlankingExon: "Exon flanquant aval",
    hoverForSeq: "Survolez pour voir la séquence complète",
    hoverForNuc: "Survolez pour voir la composition nucléotidique",
    ariaLabel: "Diagramme exon sauté",
    size: "Taille : {{n}} nt",
    coords: "Coordonnées : {{start}}–{{end}}",
    exonRank: "Rang exon : {{n}}",
    psiGroup1Label: "groupe 1",
    psiGroup2Label: "groupe 2",
    donor5ssCanonical: "Site donneur 5'SS — GT canonique",
    donor5ssNonGt: "Site donneur 5'SS ⚠ non-GT",
    donor5ss: "Site donneur 5'SS",
    donor5ssNoData: "Site donneur 5'SS — aucune donnée de séquence",
    seq9nt: "Séquence 9 nt : {{seq}}",
    acceptor3ssCanonical: "Site accepteur 3'SS — AG canonique",
    acceptor3ssNonAg: "Site accepteur 3'SS ⚠ non-AG",
    acceptor3ss: "Site accepteur 3'SS",
    acceptor3ssNoData: "Site accepteur 3'SS — aucune donnée de séquence",
    seq23nt: "Séquence 23 nt : {{seq}}",
    pptZone: "Zone polypyrimidine (PPT — 47 nt avant 3'SS)",
    pptScore: "Score Y : {{pct}}% — {{interp}}",
    pptSeq: "Séquence : {{seq}}",
    pptStrong: "PPT fort",
    pptModerate: "PPT modéré",
    pptWeak: "PPT faible",
    bp: "Point de branchement (YNYURAY)",
    bpFound: "Trouvé — BP −{{dist}} nt du début de l'exon (3′SS)",
    bpMotif: "Motif : {{motif}}",
    bpHoverDetail: "Survolez pour voir le détail",
    bpNotFound: "Non détecté dans la région PPT",
    maneTranscript: "Transcrit MANE : {{id}}",
    maneNotFound: "MANE : non trouvé",
  },
  manhattan: {
    title: "Manhattan Plot — Significativité des événements à l'échelle du génome",
    toggle: "Manhattan Plot",
    loading: "Chargement des données Manhattan…",
    noData: "Aucun événement avec des coordonnées chromosomiques disponible.",
    xAxis: "Chromosome",
    yAxis: "−log₁₀(FDR)",
    description: "{{n}} événements affichés · chaque point est un événement d'épissage positionné par coordonnée génomique · axe y = −log₁₀(FDR) · ligne rouge pointillée = seuil FDR 0.05",
    viewInTable: "Voir dans le tableau",
    clickHint: "Cliquez sur un point pour inspecter les détails",
  },
  deepAnalysis: {
    breadcrumb: "Analyse approfondie",
    title: "Analyses approfondies",
    backToEvents: "Retour aux événements",
    backToList: "Retour à la liste des analyses",
    loading: "Chargement…",
    noEvents: "Aucun événement significatif trouvé avec ces seuils.",
    permutationTitle: "Significativité par permutation",
    newAnalysis: "Nouvelle analyse approfondie",
    newAnalysisForm: "Créer une nouvelle analyse approfondie",
    formName: "Nom",
    formNamePlaceholder: "auto : Gène-FDR-PSI-Date",
    optional: "optionnel",
    significant: "significatif(s)",
    notSignificant: "non-significatif(s)",
    modules: "Modules",
    create: "Créer l'analyse",
    creating: "Création…",
    cancel: "Annuler",
    savedAnalyses: "Analyses sauvegardées",
    noSavedAnalyses: "Aucune analyse approfondie pour l'instant.",
    noSavedAnalysesHint: "Cliquez sur « Nouvelle analyse approfondie » pour en créer une avec vos seuils.",
    confirmDelete: "Supprimer cette analyse approfondie ? Cette action est irréversible.",
    delete: "Supprimer",
    methodology: "Méthodologie :",
    eventTypes: "Types d'événements :",
    seOnlyNotice: "Analyse séquences (motifs, logos, PPT) — SE uniquement",
    optionalModulesActive: "{{n}} module optionnel activé",
    optionalModulesActivePlural: "{{n}} modules optionnels activés",
  },
  hnrnpPanel: {
    error: "Erreur lors du chargement des données d'enrichissement de motifs hnRNP.",
    sigEvents: "Événements significatifs",
    bgEvents: "Événements de référence",
    significantMotifs: "Motifs significatifs",
    filters: "Filtres",
    showAll: "Tout afficher",
    significantOnly: "Significatifs uniquement",
    allProteins: "Toutes les protéines",
    allRegions: "Toutes les régions",
    noResults: "Aucun résultat de motif trouvé.",
    noSignificant: "Aucun motif significativement enrichi. Cliquez sur « Tout afficher » pour voir tous les résultats.",
    colProtein: "Protéine",
    colMotif: "Motif",
    colRegion: "Région",
    colSig: "Sig.",
    colBg: "Référence",
    showing: "Affichage de {{n}} sur {{total}} résultats",
    bonferroni: "q-values ajustées BH FDR — présence : test z de deux proportions · densité : Mann-Whitney U · * q < 0,05 · une paire est significative si l'un des deux tests passe",
    colPresenceQ: "q présence",
    colDensityQ: "q densité",
    presenceTooltip: "Test z de deux proportions sur la présence du motif par événement (ajusté BH)",
    densityTooltip: "Test de Mann-Whitney U sur la densité de motifs par événement (ajusté BH)",
    heatmapTitle: "Carte de chaleur — meilleur motif par protéine × région",
    heatmapNote: "La couleur de la cellule utilise la plus petite des deux q-values (présence, densité) ; * = q < 0,05 pour au moins un test.",
    enriched: "Enrichi chez sig.",
    depleted: "Appauvri chez sig.",
    silencer: "Silenceur (ESS/ISS)",
    enhancer: "Activateur (ESE/ISE)",
    regions: {
      upstream_exon: "Exon amont",
      upstream_intron: "Intron amont",
      upstream_intron_5ss: "Intron amont (côté 5′ss)",
      upstream_intron_3ss: "Intron amont (côté 3′ss)",
      skipped_exon: "Exon sauté",
      downstream_intron: "Intron aval",
      downstream_intron_5ss: "Intron aval (côté 5′ss)",
      downstream_intron_3ss: "Intron aval (côté 3′ss)",
      downstream_exon: "Exon aval",
    },
  },
  enrichrPanel: {
    error: "Erreur lors du chargement des résultats Enrichr.",
    genesSubmitted: "Gènes soumis",
    termsFound: "Termes trouvés",
    libraries: "Bibliothèques interrogées",
    allLibraries: "Toutes",
    noTerms: "Aucun terme enrichi trouvé.",
  },
};
