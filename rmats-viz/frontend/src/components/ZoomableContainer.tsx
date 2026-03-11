"use client";

/**
 * ZoomableContainer
 * ==================
 * Wraps any content with pinch-to-zoom and mouse-drag pan support.
 * Particularly useful for SVG diagrams on small screens.
 *
 * Controls:
 *  - Mouse wheel / trackpad pinch → zoom (1x – 4x)
 *  - Mouse drag (left button) → pan
 *  - Touch pinch → zoom
 *  - Double-click / double-tap → reset to 1x
 *  - Zoom indicator badge with reset button
 */

import { useRef, useState, useCallback, type ReactNode } from "react";

interface Props {
  children: ReactNode;
  /** Minimum zoom level (default 1). */
  minZoom?: number;
  /** Maximum zoom level (default 4). */
  maxZoom?: number;
  className?: string;
}

export function ZoomableContainer({
  children,
  minZoom = 1,
  maxZoom = 4,
  className = "",
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const dragRef = useRef<{ startX: number; startY: number; panX: number; panY: number } | null>(null);
  const touchRef = useRef<{ dist: number; zoom: number } | null>(null);

  const reset = useCallback(() => {
    setZoom(1);
    setPan({ x: 0, y: 0 });
  }, []);

  const handleWheel = useCallback(
    (e: React.WheelEvent) => {
      if (e.ctrlKey || e.metaKey) {
        e.preventDefault();
        setZoom((z) => {
          const delta = -e.deltaY * 0.005;
          return Math.min(maxZoom, Math.max(minZoom, z + delta));
        });
      }
    },
    [minZoom, maxZoom],
  );

  const handleMouseDown = useCallback(
    (e: React.MouseEvent) => {
      if (zoom <= 1) return;
      if (e.button !== 0) return;
      e.preventDefault();
      dragRef.current = { startX: e.clientX, startY: e.clientY, panX: pan.x, panY: pan.y };
    },
    [zoom, pan],
  );

  const handleMouseMove = useCallback(
    (e: React.MouseEvent) => {
      if (!dragRef.current) return;
      const dx = e.clientX - dragRef.current.startX;
      const dy = e.clientY - dragRef.current.startY;
      setPan({ x: dragRef.current.panX + dx, y: dragRef.current.panY + dy });
    },
    [],
  );

  const handleMouseUp = useCallback(() => {
    dragRef.current = null;
  }, []);

  const handleTouchStart = useCallback(
    (e: React.TouchEvent) => {
      if (e.touches.length === 2) {
        const dx = e.touches[0].clientX - e.touches[1].clientX;
        const dy = e.touches[0].clientY - e.touches[1].clientY;
        touchRef.current = { dist: Math.hypot(dx, dy), zoom };
      }
    },
    [zoom],
  );

  const handleTouchMove = useCallback(
    (e: React.TouchEvent) => {
      if (e.touches.length === 2 && touchRef.current) {
        const dx = e.touches[0].clientX - e.touches[1].clientX;
        const dy = e.touches[0].clientY - e.touches[1].clientY;
        const newDist = Math.hypot(dx, dy);
        const scale = newDist / touchRef.current.dist;
        setZoom(Math.min(maxZoom, Math.max(minZoom, touchRef.current.zoom * scale)));
      }
    },
    [minZoom, maxZoom],
  );

  const handleTouchEnd = useCallback(() => {
    touchRef.current = null;
  }, []);

  const isZoomed = zoom > 1.05;

  return (
    <div
      ref={containerRef}
      className={`relative ${className}`}
      onWheel={handleWheel}
      onMouseDown={handleMouseDown}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onMouseLeave={handleMouseUp}
      onTouchStart={handleTouchStart}
      onTouchMove={handleTouchMove}
      onTouchEnd={handleTouchEnd}
      onDoubleClick={reset}
      style={{
        cursor: isZoomed ? "grab" : undefined,
        touchAction: "pan-x pan-y",
        overflow: isZoomed ? "hidden" : "visible",
      }}
    >
      <div
        style={{
          transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`,
          transformOrigin: "center center",
          transition: dragRef.current ? undefined : "transform 0.15s ease-out",
          /* Extra padding prevents edge clipping for SVG overflow:visible content */
          padding: "4px 8px",
        }}
      >
        {children}
      </div>

      {/* Zoom indicator badge — larger hit targets */}
      {isZoomed && (
        <div className="absolute top-2 right-2 flex items-center gap-1.5 z-10">
          <span className="text-[10px] font-bold text-muted-foreground bg-card/90 backdrop-blur-sm border border-border rounded px-2 py-1 tabular-nums">
            {zoom.toFixed(1)}x
          </span>
          <button
            onClick={(e) => {
              e.stopPropagation();
              reset();
            }}
            className="text-[10px] text-muted-foreground hover:text-foreground bg-card/90 backdrop-blur-sm border border-border rounded px-2 py-1 transition-colors min-w-[28px] text-center"
            title="Reset zoom"
          >
            1:1
          </button>
        </div>
      )}

      {/* Zoom hint (shown only at 1x) */}
      {!isZoomed && (
        <div className="absolute bottom-1 right-1 text-[8px] text-muted-foreground/50 pointer-events-none select-none">
          Ctrl+scroll to zoom
        </div>
      )}
    </div>
  );
}
