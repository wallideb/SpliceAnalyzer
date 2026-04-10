"use client";

interface GroupMappingProps {
  group1Label: string;
  group2Label: string;
  onGroup1Change: (v: string) => void;
  onGroup2Change: (v: string) => void;
}

export function GroupMappingDialog({
  group1Label,
  group2Label,
  onGroup1Change,
  onGroup2Change,
}: GroupMappingProps) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
      <div>
        <label className="block text-sm font-semibold text-foreground mb-1.5">
          <span className="inline-block w-2.5 h-2.5 rounded-full bg-red-500 mr-1.5 align-middle" />
          Groupe 1 — IncLevel1
        </label>
        <input
          type="text"
          value={group1Label}
          onChange={(e) => onGroup1Change(e.target.value)}
          className="w-full border border-border rounded-lg px-3 py-2 text-sm bg-background text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 transition-shadow"
          placeholder="Ex : Subjects PCBP1"
        />
        <p className="text-xs text-muted-foreground mt-1">Porteurs de variants / cohorte cas</p>
      </div>
      <div>
        <label className="block text-sm font-semibold text-foreground mb-1.5">
          <span className="inline-block w-2.5 h-2.5 rounded-full bg-blue-500 mr-1.5 align-middle" />
          Groupe 2 — IncLevel2
        </label>
        <input
          type="text"
          value={group2Label}
          onChange={(e) => onGroup2Change(e.target.value)}
          className="w-full border border-border rounded-lg px-3 py-2 text-sm bg-background text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 transition-shadow"
          placeholder="Ex : Contrôles"
        />
        <p className="text-xs text-muted-foreground mt-1">Contrôles sains / cohorte référence</p>
      </div>
    </div>
  );
}
