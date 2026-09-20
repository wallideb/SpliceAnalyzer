"use client";
import { useCallback, useState } from "react";

/**
 * Detected rMATS file identity: event type + counting mode (A2).
 *
 *   SE.MATS.JC.txt            → { eventType: "SE",   countingMode: "JC" }
 *   cohort_A3SS.MATS.JCEC.txt → { eventType: "A3SS", countingMode: "JCEC" }
 *   SE.MATS.JC (1).txt        → { eventType: "SE",   countingMode: "JC" }   (browser copy)
 *   results_A5SS.txt          → { eventType: "A5SS", countingMode: null }   (loose token)
 *   fromGTF.SE.txt            → { eventType: "SE",   countingMode: null }
 *
 * The type token must be delimited (start of name or a non-alphanumeric
 * character), so `PRIMARY_SE.MATS.JC.txt` / `MYSERIES_SE.MATS.JC.txt` are no
 * longer mis-classified as RI / SE by substring matching.  The backend applies
 * the same rules and additionally reads the file header, so a chip shown as
 * "unknown" here may still be imported when the header is unambiguous.
 */
export interface DetectedRmatsFile {
  eventType: string;
  countingMode: string | null;
}

const MATS_RE = /(?:^|[^A-Za-z0-9])(SE|MXE|A3SS|A5SS|RI)[._-]MATS[._-](JC|JCEC)(?![A-Za-z0-9])/i;
const FROM_GTF_RE = /(?:^|[^A-Za-z0-9])fromGTF[._](?:(?:novelJunction|novelSpliceSite|novelEvents)[._])?(SE|MXE|A3SS|A5SS|RI)(?![A-Za-z0-9])/i;
const TYPE_TOKEN_RE = /(?:^|[^A-Za-z0-9])(SE|MXE|A3SS|A5SS|RI)(?![A-Za-z0-9])/gi;
const MODE_TOKEN_RE = /(?:^|[^A-Za-z0-9])(JC|JCEC)(?![A-Za-z0-9])/gi;

export function detectRmatsFile(filename: string): DetectedRmatsFile | null {
  const m = MATS_RE.exec(filename);
  if (m) return { eventType: m[1].toUpperCase(), countingMode: m[2].toUpperCase() };
  const g = FROM_GTF_RE.exec(filename);
  if (g) return { eventType: g[1].toUpperCase(), countingMode: null };
  const types = Array.from(filename.matchAll(TYPE_TOKEN_RE), (x) => x[1].toUpperCase());
  if (types.length === 0) return null;
  const modes = Array.from(filename.matchAll(MODE_TOKEN_RE), (x) => x[1].toUpperCase());
  return { eventType: types[types.length - 1], countingMode: modes.length ? modes[modes.length - 1] : null };
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
      {/* Drop zone */}
      <div
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-colors ${
          dragging
            ? "border-blue-500 bg-blue-50 dark:bg-blue-950/30"
            : "border-border hover:border-blue-400 dark:hover:border-blue-600 hover:bg-muted/40"
        }`}
        onClick={() => document.getElementById("file-input")?.click()}
      >
        <div className="flex justify-center mb-3">
          <svg xmlns="http://www.w3.org/2000/svg" className="w-8 h-8 text-muted-foreground/60" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
          </svg>
        </div>
        <p className="text-muted-foreground text-sm">
          Glissez vos fichiers rMATS ici ou{" "}
          <span className="text-blue-600 dark:text-blue-400 underline">parcourez</span>
        </p>
        <p className="text-xs text-muted-foreground/70 mt-1">
          SE, RI, A3SS, A5SS, MXE (.txt / .tsv)
        </p>
        <input
          id="file-input"
          type="file"
          multiple
          accept=".txt,.tsv"
          className="hidden"
          onChange={onInput}
        />
      </div>

      {/* File list */}
      {files.length > 0 && (
        <ul className="space-y-1.5">
          {files.map((f) => {
            const det = detectRmatsFile(f.name);
            const valid = det !== null;
            return (
              <li
                key={f.name}
                className={`flex items-center justify-between text-sm px-3 py-2 rounded-lg border ${
                  valid
                    ? "bg-green-50 dark:bg-green-950/30 border-green-200 dark:border-green-800 text-foreground"
                    : "bg-red-50 dark:bg-red-950/30 border-red-200 dark:border-red-800 text-foreground"
                }`}
              >
                <span className="truncate max-w-xs text-foreground">{f.name}</span>
                <div className="flex items-center gap-2 ml-2 shrink-0">
                  {det && (
                    <span className="text-xs font-semibold px-1.5 py-0.5 rounded-md bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300">
                      {det.eventType}
                    </span>
                  )}
                  {det?.countingMode && (
                    <span
                      className="text-[10px] font-semibold px-1.5 py-0.5 rounded-md bg-violet-100 dark:bg-violet-900/40 text-violet-700 dark:text-violet-300"
                      title={det.countingMode === "JCEC"
                        ? "Junction counts + exon body reads (JCEC)"
                        : "Junction counts only (JC)"}
                    >
                      {det.countingMode}
                    </span>
                  )}
                  {!valid && (
                    <span className="text-xs text-red-600 dark:text-red-400 font-medium">
                      type inconnu
                    </span>
                  )}
                  <button
                    type="button"
                    onClick={() => remove(f.name)}
                    title="Retirer ce fichier"
                    className="text-muted-foreground hover:text-destructive transition-colors"
                  >
                    <svg xmlns="http://www.w3.org/2000/svg" className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                    </svg>
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
