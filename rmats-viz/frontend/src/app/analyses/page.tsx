"use client";
import { useQuery } from "@tanstack/react-query";
import { listAnalyses, deleteAnalysis } from "@/lib/api";
import Link from "next/link";
import { useRouter } from "next/navigation";

export default function AnalysesPage() {
  const router = useRouter();
  const { data: analyses, isLoading, error, refetch } = useQuery({
    queryKey: ["analyses"],
    queryFn: listAnalyses,
  });

  const handleDelete = async (id: string, e: React.MouseEvent) => {
    e.preventDefault();
    if (!confirm("Supprimer cette analyse ?")) return;
    await deleteAnalysis(id);
    refetch();
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">Analyses</h1>
        <Link
          href="/analyses/new"
          className="bg-blue-600 text-white px-4 py-2 rounded-md text-sm font-medium hover:bg-blue-700"
        >
          Nouvelle analyse
        </Link>
      </div>

      {isLoading && <p className="text-gray-500">Chargement...</p>}
      {error && <p className="text-red-600">Erreur : {(error as Error).message}</p>}

      {analyses && analyses.length === 0 && (
        <div className="text-center py-16 text-gray-400">
          <p className="text-lg mb-2">Aucune analyse</p>
          <p className="text-sm">Importez vos fichiers rMATS pour commencer.</p>
        </div>
      )}

      <div className="grid gap-3">
        {analyses?.map((a) => (
          <Link
            key={a.id}
            href={`/analyses/${a.id}`}
            className="block border rounded-lg p-4 bg-white hover:shadow-sm transition-shadow"
          >
            <div className="flex items-center justify-between">
              <div>
                <p className="font-medium">{a.name}</p>
                <p className="text-sm text-gray-400">
                  {new Date(a.created_at).toLocaleString("fr-FR")}
                </p>
              </div>
              <div className="flex items-center gap-3">
                <StatusBadge status={a.status} />
                <button
                  onClick={(e) => handleDelete(a.id, e)}
                  className="text-xs text-red-400 hover:text-red-600 px-2 py-1 rounded hover:bg-red-50"
                >
                  Supprimer
                </button>
              </div>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    ready: "bg-green-100 text-green-700",
    processing: "bg-yellow-100 text-yellow-700",
    error: "bg-red-100 text-red-700",
  };
  return (
    <span className={`text-xs font-medium px-2 py-1 rounded-full ${colors[status] ?? "bg-gray-100 text-gray-600"}`}>
      {status}
    </span>
  );
}
