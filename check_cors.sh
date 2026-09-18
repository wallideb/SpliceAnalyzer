#!/usr/bin/env bash
# CORS / reachability check for the APIs that SpliceAnalyzer-web will call from the browser.
# Run from a normal machine (not from the Claude Code cloud sandbox, whose egress policy blocks these hosts):
#   bash check_cors.sh > docs/api-cors.txt
# It sends an Origin header (as a GitHub Pages site would) and prints the status line and every access-control-* header.
ORIGIN="${ORIGIN:-https://wallideb.github.io}"
urls=(
  "https://api.genome.ucsc.edu/getData/sequence?genome=hg38;chrom=chr1;start=1000000;end=1000010"
  "https://api.genome.ucsc.edu/getData/track?genome=hg38;track=mane;chrom=chr17;start=43044295;end=43125364"
  "https://api.genome.ucsc.edu/list/schema?genome=hg38;track=mane"
  "https://rest.ensembl.org/info/ping?content-type=application/json"
  "https://rest.ensembl.org/lookup/id/ENSG00000012048?expand=1;mane=1;content-type=application/json"
  "https://mygene.info/v3/query?q=symbol:BRCA1&species=human&fields=go,summary&size=1"
  "https://rest.uniprot.org/uniprotkb/search?query=gene_exact:BRCA1%20AND%20organism_id:9606%20AND%20reviewed:true&fields=accession,cc_function&format=json&size=1"
  "https://string-db.org/api/json/network?identifiers=BRCA1%0dBRCA2&species=9606&caller_identity=spliceanalyzer-web"
  "https://panelapp.genomicsengland.co.uk/api/v1/genes/?entity_name=BRCA1&format=json"
  "https://panelapp-aus.org/api/v1/genes/?entity_name=BRCA1&format=json"
  "https://panelapp.agha.umccr.org/api/v1/genes/?entity_name=BRCA1&format=json"
  "https://maayanlab.cloud/Enrichr/datasetStatistics"
  "https://maayanlab.cloud/Enrichr/geneSetLibrary?mode=text&libraryName=KEGG_2021_Human"
  "https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=BRCA1&format=json&pageSize=1"
  "https://www.ebi.ac.uk/QuickGO/services/ontology/go/terms/GO:0000398"
  "https://reactome.org/ContentService/data/query/R-HSA-72172"
  "https://rest.genenames.org/fetch/symbol/BRCA1"
  "https://gnomad.broadinstitute.org/api"
  "https://gtexportal.org/api/v2/dataset/tissueSiteDetail?datasetId=gtex_v10"
  "https://hgdownload.soe.ucsc.edu/goldenPath/hg38/bigZips/hg38.2bit"
  "https://benjamin-cogne.github.io/Sashimi-viewer/"
)
for u in "${urls[@]}"; do
  echo "== $u"
  if [[ "$u" == *gnomad* ]]; then
    curl -sS -m 25 -o /dev/null -D - -H "Origin: $ORIGIN" -H "Content-Type: application/json" \
      --data '{"query":"{ gene(gene_symbol:\"BRCA1\", reference_genome: GRCh38){ gnomad_constraint { pli oe_lof_upper } } }"}' "$u" \
      | grep -iE '^(HTTP|access-control|retry-after|x-ratelimit)' || echo "(no response)"
  elif [[ "$u" == *2bit* ]]; then
    curl -sS -m 25 -o /dev/null -D - -H "Origin: $ORIGIN" -H "Range: bytes=0-15" "$u" | grep -iE '^(HTTP|access-control|accept-ranges|content-range)' || echo "(no response)"
  else
    curl -sS -m 25 -o /dev/null -D - -H "Origin: $ORIGIN" -H "Accept: application/json" "$u" | grep -iE '^(HTTP|access-control|retry-after|x-ratelimit)' || echo "(no response)"
  fi
  # preflight (OPTIONS) as a browser would send for a POST with JSON
  curl -sS -m 25 -o /dev/null -D - -X OPTIONS -H "Origin: $ORIGIN" -H "Access-Control-Request-Method: GET" "$u" | grep -iE '^(HTTP|access-control)' | sed 's/^/  preflight: /'
  echo
done
