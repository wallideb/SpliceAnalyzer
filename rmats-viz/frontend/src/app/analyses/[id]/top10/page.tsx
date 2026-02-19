"use client";
import { useQuery } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import Link from "next/link";
import { getAnalysis, getTop10 } from "@/lib/api";
import { Top10View } from "@/components/events/Top10View";

export default function Top10Page() {
  const { id } = useParams<{ id: string }>();

  const { data: analysis } = useQuery({
    queryKey: ["analysis", id],
    queryFn: () => getAnalysis(id),
  });

  const { data: top10, isLoading } = useQuery({
    queryKey: ["top10", id],
    queryFn: () => getTop10(id),
    enabled: !!id,
  });

  const group1 = analysis?.sample_groups.find((g) => g.group_index === 1);
  const group2 = analysis?.sample_groups.find((g) => g.group_index === 2);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <div className="flex items-center gap-2 text-sm text-gray-400 mb-1">
          <Link href="/analyses" className="hover:text-gray-600">Analyses</Link>
          <span>/</span>
          <Link href={`/analyses/${id}`} className="hover:text-gray-600">{analysis?.name ?? "..."}</Link>
          <span>/</span>
          <span>Top 10</span>
        </div>
        <h1 className="text-2xl font-bold">Top 10 événements</h1>
        {group1 && group2 && (
          <p className="text-sm text-gray-500 mt-1">
            {group1.group_label} vs {group2.group_label} — classés par FDR puis |ΔPSI|
          </p>
        )}
      </div>

      <Link
        href={`/analyses/${id}`}
        className="inline-block text-sm text-blue-600 hover:text-blue-800"
      >
        ← Voir tous les événements
      </Link>

      {isLoading && <p className="text-gray-400">Chargement...</p>}
      {top10 && <Top10View events={top10} />}
    </div>
  );
}
