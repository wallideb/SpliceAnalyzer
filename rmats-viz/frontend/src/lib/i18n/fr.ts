/**
 * French locale dictionary — mirrors the English structure exactly.
 */
import type { Translations } from "./en";

export const fr: Translations = {
  meta: {
    description: "Exploration d'événements d'épissage différentiel",
  },
  nav: {
    analyses: "Analyses",
  },
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
    mutatedGenes: "Gène(s) muté(s) :",
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
      mutatedGenes: "Gène(s) muté(s) dans la cohorte",
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
      selectedGenes: "Gène(s) muté(s) sélectionné(s)",
    },
    loading: {
      title: "Analyse en cours…",
      subtitle:
        "Veuillez patienter, suppression des duplicats et priorisation des événements d'épissage…",
    },
  },
  analysisDetail: {
    breadcrumb: "Analyses",
    mutatedGenes: "Gène(s) muté(s) :",
    highlightTop10: "Surligner Top 10",
    hideTop10: "Masquer Top 10",
    showTop10: "Afficher les Top 10 dans la liste",
    top10Hidden: "Top 10 masqué",
    excel: "Excel",
    pdf: "PDF",
    top10: "Top 10",
    excelError: "Erreur lors de l'export Excel. Veuillez réessayer.",
    pdfError: "Erreur lors de la génération du PDF. Veuillez réessayer.",
    loading: "Chargement des événements…",
    filters: {
      allTypes: "Tous les types",
      genePlaceholder: "Gène (ex: PCBP1)",
      sortFdrAsc: "FDR ↑ croissant",
      sortFdrDesc: "FDR ↓ décroissant",
      sortPvalAsc: "p-value ↑",
      sortPvalDesc: "p-value ↓",
      sortDpsiDesc: "|ΔPSI| ↓ plus grand",
      sortDpsiAsc: "|ΔPSI| ↑ plus petit",
      sortGeneAz: "Gène A→Z",
      incLevelVisible: "IncLevel visible",
      incLevelHidden: "IncLevel masqué",
      showIncLevel: "Afficher les niveaux d'inclusion",
      hideIncLevel: "Masquer les niveaux d'inclusion",
      noFilter: "aucun filtre",
      reset: "Réinitialiser",
    },
    top10Notice:
      "Les <strong>Top 10 événements ◈</strong> sont sélectionnés selon les seuils rMATS par défaut (FDR &lt; 0.05, |ΔPSI| ≥ 0.1), classés par FDR puis |ΔPSI|. Ils sont filtrés comme tous les autres événements lorsque des seuils statistiques sont actifs. Utilisez le bouton <strong>Masquer Top 10</strong> pour les exclure de la liste.",
    legend: {
      deltaLabel: "ΔPSI :",
      positive: "positif → ↑ {{group}}",
      negative: "négatif → ↑ {{group}}",
    },
    events: "événement",
    eventsPlural: "événements",
    candidateGenes: "Gènes candidats",
    basket: {
      selected: "sélectionné",
      deselect: "Tout désélectionner",
      add: "Ajouter ({{n}})",
      alreadyInBasket: "Déjà dans le panier",
      alreadyInBasketTitle: "Tous ces événements sont déjà dans le panier",
    },
  },
  eventTable: {
    rank: "◈",
    type: "Type",
    gene: "Gène",
    chr: "Chr",
    strand: "Brin",
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
    openBasket: "Ouvrir le panier",
    title: "Panier",
    header: "Panier — {{n}} événement",
    headerPlural: "Panier — {{n}} événements",
    subtitle: "Sélectionnez des événements puis lancez l'analyse approfondie.",
    close: "Fermer",
    top10Notice:
      "Les <strong>Top 10 événements</strong> seront toujours inclus dans la poursuite de l'analyse, quels que soient les événements du panier.",
    empty: {
      title: "Le panier est vide.",
      subtitle:
        "Sélectionnez des événements dans la liste puis cliquez sur <strong>Ajouter au panier</strong>.",
    },
    event: "événement",
    eventPlural: "événements",
    remove: "Retirer du panier",
    continueAnalysis: "Poursuivre l'analyse",
    clearBasket: "Vider le panier",
  },
  analysisOptions: {
    title: "Poursuite de l'analyse",
    alwaysIncluded: "Toujours inclus",
    alwaysIncludedModules: {
      gene: "Gène & localisation",
      go: "Gene Ontology (GO)",
      panelapp: "PanelApp Australia",
      scores: "Scores rMATS",
    },
    optionalModules: "Modules optionnels",
    modules: {
      stringdb: {
        label: "STRING-DB & interactions protéiques",
        description:
          "Réseau d'interactions entre le gène muté et les gènes porteurs d'événements",
      },
      pathways: {
        label: "Voies moléculaires",
        description: "Enrichissement de voies (KEGG / Reactome) — module à venir",
      },
      motifs: {
        label: "Motifs récurrents",
        description:
          "Analyse de motifs d'épissage récurrents dans la sélection — module à venir",
      },
      splice: {
        label: "Sites consensus d'épissage",
        description: "Force des sites 5′/3′ et branchement — module à venir",
      },
    },
    basketEventsPrefix: "{{n}} événement du panier +",
    basketEventsPrefixPlural: "{{n}} événements du panier +",
    top10AlwaysIncluded: "seront toujours inclus dans l'analyse approfondie.",
    cancel: "Annuler",
    launch: "Lancer l'analyse",
  },
  sidebarNav: {
    collapse: "Masquer le volet",
    expand: "Afficher le volet",
    tabs: {
      gene: "Gène",
      go: "GO / Ontologie",
      scores: "Scores rMATS",
      interactions: "Interactions",
      pathways: "Voies moléc.",
      motifs: "Motifs récur.",
      splice: "Sites consensus",
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
        "Le gène porteur de l'événement est identique au gène muté — pas d'interaction à afficher.",
      error: "Erreur lors de la récupération des données STRING-DB.",
      noInteraction:
        "Aucune interaction STRING-DB trouvée entre ces deux gènes.",
      combinedScore: "Score combiné STRING :",
      evidence: "Preuves d'interaction",
      publications: "Publications associées",
      openStringDB: "Ouvrir dans STRING-DB",
    },
    comingSoon: "Module à venir",
    comingSoonModule:
      "Le module <strong>{{label}}</strong> est en cours de développement.",
    basketEvent: "Événement du panier",
  },
  permutation: {
    iterations: "Nombre d'itérations",
    moreIterations: "Plus d'itérations = distribution nulle plus précise.",
    launch: "Lancer le test de permutation",
    running: "Calcul en cours ({{n}} itér.)…",
    error:
      "Erreur lors du calcul. Vérifiez que les données PSI sont disponibles.",
    tabs: {
      delta_psi: {
        label: "ΔΨ",
        description: "Différence d'inclusion PSI par événement (test per-event).",
      },
      ppt_score: {
        label: "Score PPT",
        description:
          "Score polypyrimidique moyen (% C/T dans les 47 nt avant 3'SS).",
      },
      exon_size: {
        label: "Taille exon",
        description: "Taille de l'exon sauté (normalisée sur la plage observée).",
      },
      frame_in_frame: {
        label: "Phase / In-frame",
        description: "Fraction d'événements prédits in-frame (saut de 3n nt).",
      },
      canonical_sites: {
        label: "Sites GT-AG",
        description:
          "Score moyen de canonicité des sites d'épissage (GT donor, AG accepteur).",
      },
    },
    results: {
      eventsTested: "Événements testés",
      iterations: "Itérations",
      sig05: "Sig. p<0.05",
      sig01: "Sig. p<0.01",
      nullDistribution: "Distribution des ΔΨ sous H₀ vs observés",
      topEvents: "Top événements les plus significatifs",
      interpretation:
        "<strong>Interprétation :</strong> La distribution bleue représente la distribution nulle sous H₀ (labels aléatoires). La distribution orange représente les ΔΨ observés. Un déplacement vers des valeurs extrêmes (±1) indique un signal biologique réel.",
      interpretationMetric:
        "<strong>Interprétation :</strong> Le test compare les événements avec ΔΨ &lt; 0 (exon plus sauté en condition 2, groupe G1) vs ΔΨ &gt; 0 (exon plus inclus, groupe G2). La statistique observée est mean(G2) − mean(G1). Si la ligne orange est dans la queue de la distribution bleue, la différence entre les deux groupes est statistiquement significative.",
      method:
        "Test de permutation bilatéral — H₀ : les étiquettes de groupe sont interchangeables — p empirique = (k+1)/(N+1) avec correction de continuité (Phipson & Smyth 2010). Pour les métriques auxiliaires, les groupes G1 (ΔΨ < 0) et G2 (ΔΨ > 0) sont définis par le signe du ΔΨ observé.",
      validEvents: "Événements valides",
      g1: "G1 (ΔΨ<0)",
      g2: "G2 (ΔΨ>0)",
      observedDelta: "Δ observé",
      empiricalP: "p empirique",
      nullDistLabel: "Distribution nulle — {{label}}",
      insufficientData:
        "Données insuffisantes pour ce paramètre (n={{n}} événements avec valeur).",
      requiresPermutation:
        "Calculez le test de permutation pour voir ce paramètre. Les features de splice doivent être disponibles (FASTA requis pour PPT).",
      gene: "Gène",
      observedDeltaPsi: "ΔΨ observé",
      empiricalPValue: "p empirique",
      nGroups: "N groupes",
      significant: "Significatif",
    },
    empty: {
      main: "Lancez le test pour estimer la significativité empirique des ΔΨ et des propriétés de splice signal.",
      params:
        "5 paramètres testés : ΔΨ · score PPT · taille exon · phase · sites GT-AG.",
    },
  },
};
