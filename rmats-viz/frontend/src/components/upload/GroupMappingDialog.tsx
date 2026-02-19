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
        <label className="block text-sm font-medium text-gray-700 mb-1">
          Groupe 1 (IncLevel1)
        </label>
        <input
          type="text"
          value={group1Label}
          onChange={(e) => onGroup1Change(e.target.value)}
          className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          placeholder="Patients PCBP1"
        />
        <p className="text-xs text-gray-400 mt-1">Porteurs de variants PCBP1</p>
      </div>
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">
          Groupe 2 (IncLevel2)
        </label>
        <input
          type="text"
          value={group2Label}
          onChange={(e) => onGroup2Change(e.target.value)}
          className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          placeholder="Contrôles"
        />
        <p className="text-xs text-gray-400 mt-1">Contrôles sains</p>
      </div>
    </div>
  );
}
