"use client";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { listAnalyses, deleteAnalysis } from "@/lib/api";
import Link from "next/link";

export default function AnalysesPage() {
  const { data: analyses, isLoading, error, refetch } = useQuery({
    queryKey: ["analyses"],
    queryFn: listAnalyses,
  });

  const handleDelete = async (id: string, name: string, e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (!confirm(`Supprimer l'analyse « ${name} » ?`)) return;
    await deleteAnalysis(id);
    refetch();
  };

  const handleShare = (id: string, e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    const url = `${window.location.origin}/analyses/${id}`;
    navigator.clipboard.writeText(url).then(() => {
      // small visual feedback via title change is handled in ShareButton
    });
  };

  return (
    <div className="space-y-6">
      {/* Hero heading */}
      <div className="flex items-start justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-3xl font-extrabold tracking-tight text-foreground">
            Mes analyses
          </h1>
          <p className="text-muted-foreground text-sm mt-1">
            Explorez et gérez vos analyses d&apos;épissage différentiel rMATS
          </p>
        </div>
        <Link
          href="/analyses/new"
          className="inline-flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg text-sm font-semibold shadow-sm transition-colors"
        >
          <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
          </svg>
          Nouvelle analyse
        </Link>
      </div>

      {isLoading && (
        <div className="flex items-center gap-2 text-muted-foreground text-sm py-8">
          <LoadingDots />
          <span>Chargement...</span>
        </div>
      )}
      {error && (
        <div className="bg-destructive/10 text-destructive border border-destructive/20 rounded-lg px-4 py-3 text-sm">
          Erreur : {(error as Error).message}
        </div>
      )}

      {analyses && analyses.length === 0 && (
        <div className="text-center py-20 border-2 border-dashed border-border rounded-xl">
          <div className="w-14 h-14 mx-auto mb-4 rounded-full bg-muted flex items-center justify-center">
            <svg xmlns="http://www.w3.org/2000/svg" className="w-7 h-7 text-muted-foreground" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9.75 3.75H6A2.25 2.25 0 003.75 6v12A2.25 2.25 0 006 20.25h12A2.25 2.25 0 0020.25 18v-3.75M16.5 3.75h4.5m0 0v4.5m0-4.5L12 12" />
            </svg>
          </div>
          <p className="text-lg font-semibold text-foreground mb-1">Aucune analyse</p>
          <p className="text-sm text-muted-foreground">Importez vos fichiers rMATS pour commencer.</p>
          <Link
            href="/analyses/new"
            className="inline-flex items-center gap-2 mt-4 bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
          >
            Créer ma première analyse
          </Link>
        </div>
      )}

      <div className="grid gap-3">
        {analyses?.map((a) => (
          <Link
            key={a.id}
            href={`/analyses/${a.id}`}
            className="group block border border-border rounded-xl p-4 bg-card hover:shadow-md hover:border-blue-300 dark:hover:border-blue-700 transition-all duration-150"
          >
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 flex-wrap mb-1">
                  <p className="font-semibold text-base text-card-foreground group-hover:text-blue-600 dark:group-hover:text-blue-400 transition-colors truncate">
                    {a.name}
                  </p>
                  <StatusBadge status={a.status} />
                </div>

                {/* Mutated genes */}
                {a.mutated_genes && a.mutated_genes.length > 0 && (
                  <div className="flex items-center gap-1.5 flex-wrap mt-1.5">
                    <span className="text-xs text-muted-foreground font-medium">Gène(s) muté(s) :</span>
                    {a.mutated_genes.map((gene) => (
                      <span
                        key={gene}
                        className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300 border border-amber-200 dark:border-amber-800"
                      >
                        {gene}
                      </span>
                    ))}
                  </div>
                )}

                <p className="text-xs text-muted-foreground mt-1.5">
                  <span className="inline-flex items-center gap-1">
                    <svg xmlns="http://www.w3.org/2000/svg" className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
                    </svg>
                    {new Date(a.created_at).toLocaleString("fr-FR")}
                  </span>
                </p>
              </div>

              {/* Action buttons */}
              <div className="flex items-center gap-1 shrink-0" onClick={(e) => e.preventDefault()}>
                <ShareButton analysisId={a.id} />
                <button
                  onClick={(e) => handleDelete(a.id, a.name, e)}
                  title="Supprimer l'analyse"
                  className="w-8 h-8 flex items-center justify-center rounded-lg text-muted-foreground hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-950/40 transition-colors"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                  </svg>
                </button>
              </div>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}

function ShareButton({ analysisId }: { analysisId: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    const url = `${window.location.origin}/analyses/${analysisId}`;
    navigator.clipboard.writeText(url).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    });
  };

  return (
    <button
      onClick={handleCopy}
      title={copied ? "Lien copié !" : "Partager l'analyse (copier le lien)"}
      className={`w-8 h-8 flex items-center justify-center rounded-lg transition-colors ${
        copied
          ? "text-green-600 bg-green-50 dark:bg-green-950/40"
          : "text-muted-foreground hover:text-blue-600 hover:bg-blue-50 dark:hover:bg-blue-950/40"
      }`}
    >
      {copied ? (
        <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
        </svg>
      ) : (
        <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M8.684 13.342C8.886 12.938 9 12.482 9 12c0-.482-.114-.938-.316-1.342m0 2.684a3 3 0 110-2.684m0 2.684l6.632 3.316m-6.632-6l6.632-3.316m0 0a3 3 0 105.367-2.684 3 3 0 00-5.367 2.684zm0 9.316a3 3 0 105.368 2.684 3 3 0 00-5.368-2.684z" />
        </svg>
      )}
    </button>
  );
}

function StatusBadge({ status }: { status: string }) {
  const config: Record<string, { cls: string; label: string; dot: string }> = {
    ready: {
      cls: "bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-400 border border-green-200 dark:border-green-800",
      dot: "bg-green-500",
      label: "Prête",
    },
    processing: {
      cls: "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/40 dark:text-yellow-400 border border-yellow-200 dark:border-yellow-800",
      dot: "bg-yellow-500",
      label: "En cours",
    },
    error: {
      cls: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-400 border border-red-200 dark:border-red-800",
      dot: "bg-red-500",
      label: "Erreur",
    },
  };
  const c = config[status] ?? {
    cls: "bg-gray-100 text-gray-600 border border-gray-200",
    dot: "bg-gray-400",
    label: status,
  };
  return (
    <span className={`inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-0.5 rounded-full ${c.cls}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${c.dot}`} />
      {c.label}
    </span>
  );
}

function LoadingDots() {
  return (
    <span className="flex gap-1">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="w-1.5 h-1.5 rounded-full bg-blue-400 pulse-dot"
          style={{ animationDelay: `${i * 0.2}s` }}
        />
      ))}
    </span>
  );
}
