"use client";

/**
 * PPTTrack
 * =========
 * Visual display of the polypyrimidine tract (PPT) sequence upstream of 3'SS.
 *
 * • Each nucleotide is coloured: C/T (pyrimidines) in blue, A/G (purines) in
 *   red/orange.
 * • A horizontal pyrimidine-fraction bar shows ppt_score globally.
 * • The longest consecutive pyrimidine run is annotated.
 * • Branch-point detection result is shown inline.
 * • Position numbers count backwards from the 3'SS (e.g. −47 … −1).
 */

import { ScienceNote } from "@/components/ScienceNote";
import { useT } from "@/contexts/LanguageContext";

const PYRIMIDINE_COLOR = "#3b82f6";  // blue-500
const PURINE_COLOR     = "#f97316";  // orange-500

function isPyrimidine(base: string): boolean {
  return base === "C" || base === "T";
}

// ---------------------------------------------------------------------------
// Longest consecutive pyrimidine run (with start index) — used to annotate
// the graphical underline for ppt_longest_run.
// ---------------------------------------------------------------------------

function longestPyrRun(seq: string): { start: number; length: number } {
  let best = { start: 0, length: 0 };
  let cur  = { start: 0, length: 0 };
  for (let i = 0; i < seq.length; i++) {
    if (isPyrimidine(seq[i].toUpperCase())) {
      if (cur.length === 0) cur.start = i;
      cur.length++;
      if (cur.length > best.length) best = { ...cur };
    } else {
      cur = { start: 0, length: 0 };
    }
  }
  return best;
}

// ---------------------------------------------------------------------------
// Public component
// ---------------------------------------------------------------------------

export function PPTTrack({
  pptSeq,
  pptScore,
  pptLongestRun,
  bpFound,
  bpDistance,
}: {
  pptSeq: string;
  pptScore: number | null;
  pptLongestRun: number | null;
  bpFound: boolean | null;
  bpDistance: number | null;
}) {
  const t = useT();
  if (!pptSeq) return null;

  const seq      = pptSeq.toUpperCase();
  const seqLen   = seq.length;
  const run      = longestPyrRun(seq);

  const scoreLabel =
    pptScore === null ? null :
    pptScore >= 0.7   ? "Strong PPT"   :
    pptScore >= 0.5   ? "Moderate PPT" : "Weak PPT";

  const scoreBadgeClass =
    pptScore === null     ? "" :
    pptScore >= 0.7       ? "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300 border-blue-200 dark:border-blue-700" :
    pptScore >= 0.5       ? "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300 border-amber-200 dark:border-amber-700" :
                            "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300 border-red-200 dark:border-red-700";

  return (
    <div className="mt-3 p-3 rounded-lg bg-muted/30 border border-border space-y-2">

      {/* Header */}
      <div className="flex items-center justify-between">
        <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide">
          Zone polypyrimidique  (PPT — ~{seqLen} nt avant 3&apos;SS)
        </p>
        {pptScore !== null && (
          <span className={`text-[10px] font-bold px-2 py-0.5 rounded border ${scoreBadgeClass}`}>
            {Math.round(pptScore * 100)}% Y — {scoreLabel}
          </span>
        )}
      </div>

      {/* Nucleotide sequence with position numbers and branch point marker */}
      <div className="overflow-x-auto -mx-1 px-1" style={{ WebkitOverflowScrolling: "touch" }}>
        {/* Position number row (every 5 nt) */}
        <div className="flex gap-[2px] mb-0.5">
          {seq.split("").map((_, i) => {
            const posFromSS = -(seqLen - i);
            const showLabel = posFromSS % 5 === 0 || i === 0 || i === seqLen - 1;
            return (
              <span
                key={i}
                className="inline-flex items-center justify-center w-4 text-[7px] font-mono text-muted-foreground/60 select-none"
              >
                {showLabel ? posFromSS : ""}
              </span>
            );
          })}
        </div>

        {/* Nucleotide cells */}
        <div className="flex gap-[2px]">
          {seq.split("").map((base, i) => {
            const isPyr = isPyrimidine(base);
            const posFromSS = -(seqLen - i);
            const isBpSite = bpFound === true && bpDistance != null && posFromSS === -bpDistance;
            return (
              <span
                key={i}
                title={`Position ${posFromSS}: ${base} (${isPyr ? "pyrimidine Y" : "purine R"})${isBpSite ? " — Branch point" : ""}`}
                style={{
                  color:       isPyr ? PYRIMIDINE_COLOR : PURINE_COLOR,
                  borderColor: isBpSite
                    ? "#22c55e"
                    : isPyr ? `${PYRIMIDINE_COLOR}44` : `${PURINE_COLOR}44`,
                  backgroundColor: isBpSite
                    ? "#22c55e1a"
                    : isPyr ? `${PYRIMIDINE_COLOR}1a` : `${PURINE_COLOR}1a`,
                }}
                className={`inline-flex items-center justify-center w-4 h-5 text-[9px] font-mono font-bold rounded-sm border cursor-default select-none ${isBpSite ? "border-2 ring-1 ring-green-400/40" : ""}`}
              >
                {base}
              </span>
            );
          })}
        </div>

        {/* Branch point annotation arrow */}
        {bpFound === true && bpDistance != null && (
          <div className="flex gap-[2px] mt-0.5">
            {seq.split("").map((_, i) => {
              const posFromSS = -(seqLen - i);
              const isBpSite = posFromSS === -bpDistance;
              return (
                <span
                  key={i}
                  className="inline-flex items-center justify-center w-4 text-[8px] select-none"
                >
                  {isBpSite ? (
                    <span className="text-green-600 dark:text-green-400 font-bold" title="Branch point adenosine">
                      BP
                    </span>
                  ) : ""}
                </span>
              );
            })}
          </div>
        )}

        {/* Legend */}
        <div className="flex items-center gap-3 mt-1.5 text-[8px] text-muted-foreground select-none">
          <span className="flex items-center gap-1">
            <span className="inline-block w-2.5 h-2.5 rounded-sm" style={{ backgroundColor: `${PYRIMIDINE_COLOR}33`, border: `1px solid ${PYRIMIDINE_COLOR}44` }} />
            C/T (pyrimidine)
          </span>
          <span className="flex items-center gap-1">
            <span className="inline-block w-2.5 h-2.5 rounded-sm" style={{ backgroundColor: `${PURINE_COLOR}33`, border: `1px solid ${PURINE_COLOR}44` }} />
            A/G (purine)
          </span>
          {bpFound === true && (
            <span className="flex items-center gap-1">
              <span className="inline-block w-2.5 h-2.5 rounded-sm border-2 border-green-500 bg-green-500/10" />
              Branch point
            </span>
          )}
          <span className="ml-auto italic">positions relative to 3&apos;SS →</span>
        </div>
      </div>

      {/* Score bar + longest run underline */}
      {pptScore !== null && (
        <div className="space-y-1">
          {/* Fraction bar */}
          <div className="flex items-center gap-2">
            <div className="flex-1 h-2 rounded-full bg-muted overflow-hidden">
              <div
                className="h-full rounded-full bg-blue-500/70 transition-all"
                style={{ width: `${Math.round(pptScore * 100)}%` }}
              />
            </div>
            <span className="text-[9px] tabular-nums text-muted-foreground w-7 text-right">
              {Math.round(pptScore * 100)}%
            </span>
          </div>

          {/* Longest run annotation */}
          {pptLongestRun !== null && pptLongestRun > 0 && (
            <p className="text-[9px] text-muted-foreground">
              Run Y max :{" "}
              <strong className="text-foreground tabular-nums">{pptLongestRun} nt</strong>
              {" "}(positions{" "}
              <code className="font-mono">
                {-(seqLen - run.start)}…{-(seqLen - run.start - run.length + 1)}
              </code>
              )
            </p>
          )}
        </div>
      )}

      {/* Branch-point */}
      {bpFound !== null && (
        <p className={`text-[9px] font-medium ${bpFound ? "text-green-600 dark:text-green-400" : "text-muted-foreground"}`}>
          {bpFound
            ? `✓ Branch point (YNYURAY) detected — ~${bpDistance} nt upstream of 3′SS`
            : "— Branch point (YNYURAY) not detected in the PPT region"}
        </p>
      )}
      <ScienceNote
        title={t("scienceNotes.pptTrack.title")}
        body={t("scienceNotes.pptTrack.body")}
        refs={["ppt", "branch_point"]}
      />
    </div>
  );
}
