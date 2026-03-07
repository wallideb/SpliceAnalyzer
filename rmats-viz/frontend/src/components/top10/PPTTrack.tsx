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
  pptSeq: string | null;
  pptScore: number | null;
  pptLongestRun: number | null;
  bpFound: boolean | null;
  bpDistance: number | null;
}) {
  if (!pptSeq) return null;

  const seq      = pptSeq.toUpperCase();
  const seqLen   = seq.length;
  const run      = longestPyrRun(seq);

  const scoreLabel =
    pptScore === null ? null :
    pptScore >= 0.7   ? "PPT fort"   :
    pptScore >= 0.5   ? "PPT modéré" : "PPT faible";

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

      {/* Nucleotide sequence — wrapping flex */}
      <div className="flex flex-wrap gap-[2px]">
        {seq.split("").map((base, i) => {
          const isPyr = isPyrimidine(base);
          const posFromSS = -(seqLen - i); // e.g. −47, −46, … −1
          return (
            <span
              key={i}
              title={`Position ${posFromSS}: ${base} (${isPyr ? "pyrimidine Y" : "purine R"})`}
              style={{
                color:       isPyr ? PYRIMIDINE_COLOR : PURINE_COLOR,
                borderColor: isPyr ? `${PYRIMIDINE_COLOR}44` : `${PURINE_COLOR}44`,
                backgroundColor: isPyr ? `${PYRIMIDINE_COLOR}1a` : `${PURINE_COLOR}1a`,
              }}
              className="inline-flex items-center justify-center w-4 h-5 text-[9px] font-mono font-bold rounded-sm border cursor-default select-none"
            >
              {base}
            </span>
          );
        })}
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
            ? `✓ Point de branchement (YNYURAY) détecté — ~${bpDistance} nt avant 3'SS`
            : "— Point de branchement (YNYURAY) non détecté dans la région PPT"}
        </p>
      )}
    </div>
  );
}
