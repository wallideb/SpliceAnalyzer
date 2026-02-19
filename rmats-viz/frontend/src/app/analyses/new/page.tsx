"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { FileUploadZone } from "@/components/upload/FileUploadZone";
import { GroupMappingDialog } from "@/components/upload/GroupMappingDialog";
import { uploadAnalysis } from "@/lib/api";

export default function NewAnalysisPage() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [group1Label, setGroup1Label] = useState("Patients PCBP1");
  const [group2Label, setGroup2Label] = useState("Contrôles");
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
        files,
      });
      router.push(`/analyses/${res.analysis_id}`);
    } catch (e) {
      setError((e as Error).message);
      setLoading(false);
    }
  };

  return (
    <div className="max-w-2xl mx-auto">
      <h1 className="text-2xl font-bold mb-6">Nouvelle analyse</h1>

      {/* Step indicators */}
      <div className="flex items-center gap-2 mb-8">
        <StepDot n={1} active={step === 1} done={step > 1} label="Fichiers" />
        <div className="flex-1 h-px bg-gray-200" />
        <StepDot n={2} active={step === 2} done={false} label="Groupes" />
      </div>

      <div className="bg-white border rounded-lg p-6 space-y-5">
        {step === 1 && (
          <>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Nom de l'analyse
              </label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Ex: PCBP1 cohort 2024"
                className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Fichiers rMATS
              </label>
              <FileUploadZone files={files} onChange={setFiles} />
            </div>
            <div className="flex justify-end">
              <button
                disabled={!canNext}
                onClick={() => setStep(2)}
                className="bg-blue-600 text-white px-5 py-2 rounded-md text-sm font-medium hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed"
              >
                Suivant
              </button>
            </div>
          </>
        )}

        {step === 2 && (
          <>
            <div>
              <h2 className="text-base font-semibold mb-1">Labels des groupes</h2>
              <p className="text-sm text-gray-500 mb-4">
                Ces labels apparaîtront dans les colonnes IncLevel1 / IncLevel2.
              </p>
              <GroupMappingDialog
                group1Label={group1Label}
                group2Label={group2Label}
                onGroup1Change={setGroup1Label}
                onGroup2Change={setGroup2Label}
              />
            </div>

            {error && (
              <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded text-sm">
                {error}
              </div>
            )}

            <div className="flex justify-between">
              <button
                onClick={() => setStep(1)}
                className="text-sm text-gray-500 hover:text-gray-700 px-3 py-2 rounded border hover:bg-gray-50"
              >
                Retour
              </button>
              <button
                onClick={handleSubmit}
                disabled={loading}
                className="bg-blue-600 text-white px-5 py-2 rounded-md text-sm font-medium hover:bg-blue-700 disabled:opacity-60"
              >
                {loading ? "Analyse en cours..." : "Lancer l'analyse"}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function StepDot({ n, active, done, label }: { n: number; active: boolean; done: boolean; label: string }) {
  return (
    <div className="flex items-center gap-1.5">
      <div
        className={`w-7 h-7 rounded-full flex items-center justify-center text-sm font-bold ${
          active ? "bg-blue-600 text-white" : done ? "bg-green-500 text-white" : "bg-gray-200 text-gray-500"
        }`}
      >
        {done ? "✓" : n}
      </div>
      <span className={`text-sm ${active ? "font-medium text-gray-800" : "text-gray-400"}`}>{label}</span>
    </div>
  );
}
