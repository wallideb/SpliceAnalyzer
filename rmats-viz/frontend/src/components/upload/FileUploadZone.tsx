"use client";
import { useCallback, useState } from "react";

const VALID_TYPES = ["SE", "RI", "A3SS", "A5SS", "MXE"];

function detectEventType(filename: string): string | null {
  const upper = filename.toUpperCase();
  for (const t of ["MXE", "A3SS", "A5SS", "RI", "SE"]) {
    if (upper.includes(t)) return t;
  }
  return null;
}

interface FileUploadZoneProps {
  files: File[];
  onChange: (files: File[]) => void;
}

export function FileUploadZone({ files, onChange }: FileUploadZoneProps) {
  const [dragging, setDragging] = useState(false);

  const addFiles = useCallback(
    (newFiles: File[]) => {
      const merged = [...files];
      for (const f of newFiles) {
        if (!merged.find((x) => x.name === f.name)) merged.push(f);
      }
      onChange(merged);
    },
    [files, onChange]
  );

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragging(false);
      addFiles(Array.from(e.dataTransfer.files));
    },
    [addFiles]
  );

  const onInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) addFiles(Array.from(e.target.files));
  };

  const remove = (name: string) => onChange(files.filter((f) => f.name !== name));

  return (
    <div className="space-y-3">
      <div
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={`border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors ${
          dragging ? "border-blue-500 bg-blue-50" : "border-gray-300 hover:border-blue-400"
        }`}
        onClick={() => document.getElementById("file-input")?.click()}
      >
        <p className="text-gray-500 text-sm">
          Glissez vos fichiers rMATS ici ou <span className="text-blue-600 underline">parcourez</span>
        </p>
        <p className="text-xs text-gray-400 mt-1">SE, RI, A3SS, A5SS, MXE (.txt / .tsv)</p>
        <input
          id="file-input"
          type="file"
          multiple
          accept=".txt,.tsv"
          className="hidden"
          onChange={onInput}
        />
      </div>

      {files.length > 0 && (
        <ul className="space-y-1">
          {files.map((f) => {
            const et = detectEventType(f.name);
            const valid = et !== null;
            return (
              <li
                key={f.name}
                className={`flex items-center justify-between text-sm px-3 py-2 rounded-md ${
                  valid ? "bg-green-50 border border-green-200" : "bg-red-50 border border-red-200"
                }`}
              >
                <span className="truncate max-w-xs">{f.name}</span>
                <div className="flex items-center gap-2 ml-2 shrink-0">
                  {et && (
                    <span className="text-xs font-medium px-1.5 py-0.5 rounded bg-blue-100 text-blue-700">
                      {et}
                    </span>
                  )}
                  {!valid && <span className="text-xs text-red-500">type inconnu</span>}
                  <button
                    type="button"
                    onClick={() => remove(f.name)}
                    className="text-gray-400 hover:text-red-500 text-xs"
                  >
                    ✕
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
