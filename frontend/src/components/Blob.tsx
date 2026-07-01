import type { ReactNode } from "react";

interface BlobProps {
  size?: number;
  children?: ReactNode;
  /** decorative only — hidden from assistive tech */
  className?: string;
}

/**
 * The Ditto blob: a gelatinous, morphing mass that floats and
 * shifts shape. Pure CSS animation (see global.css), GPU-friendly.
 */
export function Blob({ size = 240, children, className }: BlobProps) {
  return (
    <div
      className={className}
      style={{ position: "relative", width: size, height: size }}
      aria-hidden
    >
      <div className="ditto-blob-halo" />
      <div
        className="ditto-blob"
        style={{
          width: "100%",
          height: "100%",
          display: "grid",
          placeItems: "center",
        }}
      >
        {children}
      </div>
    </div>
  );
}
