"use client";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import Link from "next/link";
import { getAnalysis, getTop10 } from "@/lib/api";
import { Top10View } from "@/components/events/Top10View";
import { MutatedGenePanel } from "@/components/top10/MutatedGenePanel";
import { useT } from "@/contexts/LanguageContext";
import type { GeneEntry } from "@/types/gene";

const EVENT_TYPES = ["SE", "RI", "A3SS", "A5SS", "MXE"] as const;

export default function Top10Page() {
  const { id } = useParams<{ id: string }>();
  const t = useT();
  const [eventType, setEventType] = useState<string>("");

  const { data: analysis } = useQuery({
    queryKey: ["analysis", id],
    queryFn: () => getAnalysis(id),
  });

  const { data: top10, isLoading } = useQuery({
    queryKey: ["top10", id, eventType],
    queryFn: () => getTop10(id, eventType || undefined),
    enabled: !!id,
  });

  const group1 = analysis?.sample_groups.find((g) => g.group_index === 1);
  const group2 = analysis?.sample_groups.find((g) => g.group_index === 2);

  // Resolve mutated gene entries – guard against legacy plain-string format
  const mutatedGenes: GeneEntry[] = (analysis?.mutated_genes ?? []).filter(
    (g): g is GeneEntry => typeof g === "object" && "ensembl_id" in g,
  );

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <nav className="flex items-center gap-1 text-sm text-muted-foreground mb-2">
          <Link href="/analyses" className="hover:text-foreground transition-colors">
            Analyses
          </Link>
          <svg xmlns="http://www.w3.org/2000/svg" className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
          </svg>
          <Link href={`/analyses/${id}`} className="hover:text-foreground transition-colors truncate max-w-[200px]">
            {analysis?.name ?? "…"}
          </Link>
          <svg xmlns="http://www.w3.org/2000/svg" className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
          </svg>
          <span className="text-foreground font-medium">Top 10</span>
        </nav>

        <div className="flex items-center gap-4 flex-wrap">
          <h1 className="text-2xl font-extrabold tracking-tight text-foreground">
            Top 10 événements
          </h1>
          <select
            value={eventType}
            onChange={(e) => setEventType(e.target.value)}
            className="border border-border rounded-lg px-3 py-1.5 text-sm bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-blue-500 transition-shadow"
          >
            <option value="">{t("analysisDetail.filters.allTypes")}</option>
            {EVENT_TYPES.map((et) => (
              <option key={et} value={et}>{et}</option>
            ))}
          </select>
        </div>
        {group1 && group2 && (
          <p className="text-sm text-muted-foreground mt-1">
            <span className="text-red-500 dark:text-red-400 font-semibold">{group1.group_label}</span>
            {" vs "}
            <span className="text-blue-500 dark:text-blue-400 font-semibold">{group2.group_label}</span>
            {" — classés par FDR puis |ΔPSI|"}
          </p>
        )}
      </div>

      <Link
        href={`/analyses/${id}`}
        className="inline-flex items-center gap-1.5 text-sm text-blue-600 dark:text-blue-400 hover:underline"
      >
        <svg xmlns="http://www.w3.org/2000/svg" className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
        </svg>
        Voir tous les événements
      </Link>

      {isLoading && (
        <div className="flex items-center gap-2 text-muted-foreground text-sm py-6">
          <div className="w-4 h-4 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
          Chargement des événements…
        </div>
      )}

      {/* Mutated gene annotation panel */}
      <MutatedGenePanel mutatedGenes={mutatedGenes} analysisId={id} />

      {top10 && (
        <Top10View
          events={top10}
          mutatedGenes={mutatedGenes}
          group1Label={group1?.group_label ?? "Groupe 1"}
          group2Label={group2?.group_label ?? "Groupe 2"}
        />
      )}
    </div>
  );
}
