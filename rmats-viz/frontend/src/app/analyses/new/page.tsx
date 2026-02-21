"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { FileUploadZone } from "@/components/upload/FileUploadZone";
import { GroupMappingDialog } from "@/components/upload/GroupMappingDialog";
import { GeneAutocomplete } from "@/components/genes/GeneAutocomplete";
import { uploadAnalysis } from "@/lib/api/analyses";
import type { GeneEntry } from "@/types/gene";

export default function NewAnalysisPage() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [group1Label, setGroup1Label] = useState("Patients");
  const [group2Label, setGroup2Label] = useState("Contrôles");
  const [mutatedGenes, setMutatedGenes] = useState<GeneEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [step, setStep] = useState<1 | 2>(1);

  const canNext = name.trim() && files.length > 0;

  const handleSubmit = async () => {
    if (!canNext) return;
    setLoading(true);
    setError(null);
    try {
      const res = await uploadAnalysis({
        name: name.trim(),
        group1_label: group1Label,
        group2_label: group2Label,
        group1_samples: [],
        group2_samples: [],
        mutated_genes: mutatedGenes,
        files,
      });
      router.push(`/analyses/${res.analysis_id}`);
    } catch (e) {
      setError((e as Error).message);
      setLoading(false);
    }
  };

  if (loading) {
    return <DnaLoadingScreen />;
  }

  return (
    <div className="max-w-2xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-extrabold tracking-tight text-foreground">Nouvelle analyse</h1>
        <p className="text-sm text-muted-foreground mt-1">Importez vos fichiers rMATS et configurez votre analyse</p>
      </div>

      {/* Step indicators */}
      <div className="flex items-center gap-2 mb-8">
        <StepDot n={1} active={step === 1} done={step > 1} label="Fichiers & gènes" />
        <div className="flex-1 h-0.5 bg-border rounded" />
        <StepDot n={2} active={step === 2} done={false} label="Groupes" />
      </div>

      <div className="bg-card border border-border rounded-xl p-6 space-y-5 shadow-sm">
        {step === 1 && (
          <>
            {/* Analysis name */}
            <div>
              <label className="block text-sm font-semibold text-foreground mb-1.5">
                Nom de l&apos;analyse
              </label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Ex: PCBP1 cohort 2024"
                className="w-full border border-border rounded-lg px-3 py-2 text-sm bg-background text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 transition-shadow"
              />
            </div>

            {/* Mutated genes – Ensembl autocomplete */}
            <div>
              <label className="block text-sm font-semibold text-foreground mb-1">
                Gène(s) muté(s) dans la cohorte{" "}
                <span className="text-muted-foreground font-normal">(nomenclature HUGO)</span>
              </label>
              <p className="text-xs text-muted-foreground mb-2">
                Ces gènes seront affichés dans l&apos;analyse même s&apos;ils n&apos;apparaissent pas
                dans les anomalies d&apos;épissage détectées. L&apos;identifiant Ensembl (ENSG) est
                récupéré automatiquement.
              </p>
              <GeneAutocomplete value={mutatedGenes} onChange={setMutatedGenes} />
            </div>

            {/* File upload */}
            <div>
              <label className="block text-sm font-semibold text-foreground mb-2">
                Fichiers rMATS
              </label>
              <FileUploadZone files={files} onChange={setFiles} />
            </div>

            <div className="flex justify-end">
              <button
                disabled={!canNext}
                onClick={() => setStep(2)}
                className="inline-flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white px-5 py-2 rounded-lg text-sm font-semibold disabled:opacity-40 disabled:cursor-not-allowed transition-colors shadow-sm"
              >
                Suivant
                <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
                </svg>
              </button>
            </div>
          </>
        )}

        {step === 2 && (
          <>
            <div>
              <h2 className="text-base font-semibold text-foreground mb-1">Labels des groupes</h2>
              <p className="text-sm text-muted-foreground mb-4">
                Ces labels apparaîtront dans les colonnes IncLevel1 / IncLevel2.
              </p>
              <GroupMappingDialog
                group1Label={group1Label}
                group2Label={group2Label}
                onGroup1Change={setGroup1Label}
                onGroup2Change={setGroup2Label}
              />
            </div>

            {/* Summary of selected genes */}
            {mutatedGenes.length > 0 && (
              <div className="bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-800 rounded-lg px-4 py-3">
                <p className="text-xs font-semibold text-amber-800 dark:text-amber-300 mb-1.5">
                  Gène(s) muté(s) sélectionné(s)
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {mutatedGenes.map((g) => (
                    <span
                      key={g.ensembl_id}
                      className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300 border border-amber-200 dark:border-amber-700"
                    >
                      {g.display}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {error && (
              <div className="bg-destructive/10 border border-destructive/20 text-destructive px-4 py-3 rounded-lg text-sm">
                {error}
              </div>
            )}

            <div className="flex justify-between">
              <button
                onClick={() => setStep(1)}
                className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground px-3 py-2 rounded-lg border border-border hover:bg-muted transition-colors"
              >
                <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
                </svg>
                Retour
              </button>
              <button
                onClick={handleSubmit}
                className="inline-flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white px-5 py-2 rounded-lg text-sm font-semibold transition-colors shadow-sm"
              >
                <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                Lancer l&apos;analyse
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function DnaLoadingScreen() {
  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] gap-8">
      <div className="relative w-24 h-24 flex items-center justify-center">
        <img
          src="/logo.svg"
          alt="SpliceAnalyzer"
          className="w-20 h-20 dna-strand"
          draggable={false}
        />
      </div>

      <div className="text-center space-y-2">
        <p className="text-lg font-semibold text-foreground">Analyse en cours…</p>
        <p className="text-sm text-muted-foreground max-w-xs leading-relaxed">
          Veuillez patienter, suppression des duplicats et priorisation des événements d&apos;épissage…
        </p>
      </div>

      <div className="flex gap-2">
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            className="w-2.5 h-2.5 rounded-full bg-blue-500 pulse-dot"
            style={{ animationDelay: `${i * 0.2}s` }}
          />
        ))}
      </div>
    </div>
  );
}

function StepDot({ n, active, done, label }: { n: number; active: boolean; done: boolean; label: string }) {
  return (
    <div className="flex items-center gap-2">
      <div
        className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold transition-colors ${
          active
            ? "bg-blue-600 text-white ring-4 ring-blue-100 dark:ring-blue-900"
            : done
            ? "bg-green-500 text-white"
            : "bg-muted text-muted-foreground"
        }`}
      >
        {done ? (
          <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
          </svg>
        ) : n}
      </div>
      <span className={`text-sm font-medium ${active ? "text-foreground" : "text-muted-foreground"}`}>{label}</span>
    </div>
  );
}
