"use client";

/**
 * SpliceSiteTrack
 * ================
 * Displays donor (5'SS) and acceptor (3'SS) splice-site sequences as
 * per-nucleotide coloured blocks with position axes.
 *
 * Convention (Shapiro & Senapathy 1987, Burge & Karlin 1997):
 *  • 5'SS donor   — 9 nt: positions -3,-2,-1 (exon) | +1,+2 (GT) +3..+6 (intron)
 *  • 3'SS acceptor — 23 nt: positions -20..-2,-1 (AG) | +1,+2,+3 (exon)
 *
 * A dashed vertical line marks the exon–intron boundary.
 * Canonical GT / AG dinucleotides are displayed with a filled background.
 * Each nucleotide has a native SVG <title> tooltip showing position + base.
 */

const BASE_COLORS: Record<string, string> = {
  A: "#22c55e",   // green-500
  C: "#3b82f6",   // blue-500
  G: "#f97316",   // orange-500
  T: "#ef4444",   // red-500
};

// Position arrays — no zero in splice-site numbering
const DONOR_POSITIONS    = [-3, -2, -1, 1, 2, 3, 4, 5, 6] as const;      // 9 nt
const ACCEPTOR_POSITIONS = [
  ...Array.from({ length: 20 }, (_, i) => -(20 - i)), // -20 … -1
  1, 2, 3,                                             // +1 … +3
] as const;                                            // 23 nt

// 0-based indices of the canonical dinucleotide within each sequence
const DONOR_CANONICAL_IDX    = new Set([3, 4]);   // +1,+2 = GT
const ACCEPTOR_CANONICAL_IDX = new Set([18, 19]); // -2,-1 = AG

// Where to insert the boundary line (before this index)
const DONOR_BOUNDARY    = 3;   // between position -1 and +1
const ACCEPTOR_BOUNDARY = 20;  // between position -1 and +1

const NT_W  = 17;  // px per nucleotide column
const NT_H  = 22;  // nucleotide block height
const AXIS_H = 16; // height reserved for position labels below blocks

// ---------------------------------------------------------------------------
// NucTrack — internal sub-component
// ---------------------------------------------------------------------------

function NucTrack({
  seq,
  positions,
  canonicalIdx,
  boundaryAt,
  label,
}: {
  seq: string;
  positions: readonly number[];
  canonicalIdx: Set<number>;
  boundaryAt: number;
  label: string;
}) {
  const n = seq.length;
  // Extra horizontal space for the boundary gap
  const totalW = n * NT_W + 10;
  const svgH   = NT_H + AXIS_H;

  /** Pixel x-coordinate for nucleotide index i (offset by gap after boundary). */
  const getX = (i: number) => i * NT_W + (i >= boundaryAt ? 10 : 0);

  return (
    <div>
      <p className="text-[9px] text-muted-foreground uppercase tracking-wide font-semibold mb-1.5">
        {label}
      </p>
      <div style={{ overflowX: "auto" }}>
        <svg
          viewBox={`0 0 ${totalW} ${svgH}`}
          style={{ width: totalW, height: svgH, display: "block", overflow: "visible" }}
          aria-label={label}
        >
          {/* Boundary line */}
          <line
            x1={getX(boundaryAt) - 5}
            y1={-2}
            x2={getX(boundaryAt) - 5}
            y2={NT_H + 2}
            stroke="#475569"
            strokeWidth={1.5}
            strokeDasharray="3 2"
          />

          {seq
            .toUpperCase()
            .split("")
            .map((base, i) => {
              const color    = BASE_COLORS[base] ?? "#94a3b8";
              const isHL     = canonicalIdx.has(i);
              const x        = getX(i);
              const pos      = positions[i] ?? i;
              const posLabel = pos > 0 ? `+${pos}` : `${pos}`;

              return (
                <g key={i}>
                  <title>{`Position ${posLabel}: ${base}`}</title>
                  {/* Nucleotide block */}
                  <rect
                    x={x + 1}
                    y={1}
                    width={NT_W - 2}
                    height={NT_H - 2}
                    rx={2}
                    fill={isHL ? color : "transparent"}
                    stroke={color}
                    strokeWidth={isHL ? 0 : 1}
                    opacity={0.9}
                  />
                  {/* Base letter */}
                  <text
                    x={x + NT_W / 2}
                    y={NT_H - 5}
                    textAnchor="middle"
                    fontSize={9.5}
                    fontFamily="monospace"
                    fontWeight={isHL ? "800" : "500"}
                    fill={isHL ? "white" : color}
                  >
                    {base}
                  </text>
                  {/* Position label */}
                  <text
                    x={x + NT_W / 2}
                    y={NT_H + AXIS_H - 2}
                    textAnchor="middle"
                    fontSize={6.5}
                    fontFamily="monospace"
                    fill={isHL ? "#64748b" : "#94a3b8"}
                  >
                    {posLabel}
                  </text>
                </g>
              );
            })}
        </svg>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Public component
// ---------------------------------------------------------------------------

export function SpliceSiteTrack({
  donorSeq,
  acceptorSeq,
  fastaAvailable = true,
}: {
  donorSeq: string | null;
  acceptorSeq: string | null;
  fastaAvailable?: boolean;
}) {
  return (
    <div className="mt-3 space-y-4 p-3 rounded-lg bg-muted/30 border border-border">
      <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide">
        Sites d&apos;épissage — séquences canoniques proches des exons sautés
      </p>

      {!fastaAvailable && (
        <div className="flex items-start gap-2 px-3 py-2 rounded-md bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800 text-amber-800 dark:text-amber-300">
          <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4 mt-0.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
          </svg>
          <div>
            <p className="text-xs font-semibold">FASTA non disponible — séquences non calculées</p>
            <p className="text-[11px] mt-0.5 text-amber-700 dark:text-amber-400">
              Seules les données de taille (coordonnées) sont affichées. Indexez un génome de référence FASTA pour activer l&apos;analyse des séquences d&apos;épissage (5&apos;SS GT, 3&apos;SS AG, PPT, branchpoint).
            </p>
          </div>
        </div>
      )}

      {donorSeq && donorSeq.length >= 9 && (
        <NucTrack
          seq={donorSeq.slice(0, 9)}
          positions={DONOR_POSITIONS}
          canonicalIdx={DONOR_CANONICAL_IDX}
          boundaryAt={DONOR_BOUNDARY}
          label="5'SS donneur  (exon | intron) — GT canonique en +1/+2"
        />
      )}

      {acceptorSeq && acceptorSeq.length >= 23 && (
        <NucTrack
          seq={acceptorSeq.slice(-23)}
          positions={ACCEPTOR_POSITIONS}
          canonicalIdx={ACCEPTOR_CANONICAL_IDX}
          boundaryAt={ACCEPTOR_BOUNDARY}
          label="3'SS accepteur  (intron | exon) — AG canonique en −2/−1"
        />
      )}

      {fastaAvailable && !donorSeq && !acceptorSeq && (
        <p className="text-xs text-muted-foreground italic">
          Séquences non disponibles pour cet événement.
        </p>
      )}
    </div>
  );
}
