/** Stroke icons (currentColor, 1.6 stroke on a 24 grid) used across the app. */
const base = {
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.6,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  viewBox: "0 0 24 24",
  "aria-hidden": true,
  focusable: false,
};

export function ArrowIcon() {
  return (
    <svg {...base}>
      <path d="M5 12h14" />
      <path d="m13 6 6 6-6 6" />
    </svg>
  );
}

export function UploadIcon() {
  return (
    <svg {...base}>
      <path d="M12 16V5" />
      <path d="m8 9 4-4 4 4" />
      <path d="M5 15v3a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-3" />
    </svg>
  );
}

export function DownloadIcon() {
  return (
    <svg {...base}>
      <path d="M12 5v11" />
      <path d="m8 12 4 4 4-4" />
      <path d="M5 19h14" />
    </svg>
  );
}

export function CheckIcon() {
  return (
    <svg {...base}>
      <path d="m5 12.5 4.5 4.5L19 7.5" />
    </svg>
  );
}

export function CloseIcon() {
  return (
    <svg {...base}>
      <path d="M6 6l12 12" />
      <path d="M18 6 6 18" />
    </svg>
  );
}

export function AlertIcon() {
  return (
    <svg {...base}>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7.5v5.5" />
      <path d="M12 16.5v.01" />
    </svg>
  );
}

export function InfoIcon() {
  return (
    <svg {...base}>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 11v5.5" />
      <path d="M12 7.5v.01" />
    </svg>
  );
}

export function PauseIcon() {
  return (
    <svg {...base}>
      <path d="M9 6v12" />
      <path d="M15 6v12" />
    </svg>
  );
}

export function SortIcon({ dir }: { dir: "asc" | "desc" | null }) {
  return (
    <svg {...base} strokeWidth={1.8}>
      {dir !== "asc" && <path d="m7 14 5 5 5-5" opacity={dir === "desc" ? 1 : 0.4} />}
      {dir !== "desc" && <path d="m7 10 5-5 5 5" opacity={dir === "asc" ? 1 : 0.4} />}
    </svg>
  );
}

/**
 * The Ditto mark: a flat, shape-shifting mass mid-transformation — half blob,
 * half the corner of a page it is copying.
 */
export function DittoMark() {
  return (
    <svg viewBox="0 0 64 64" aria-hidden focusable={false}>
      <path
        d="M9 38c-3-12 4-25 17-28 7-1.6 11 2 16 1.5 6-.6 11 3 12 10 .9 6-2 9-1.2 14 1 6 5 9 3 14.5C53 56 45 57 38 55.5c-6-1.3-9 1.5-16 1C14 56 11 49 9 38Z"
        fill="var(--hue-violet)"
      />
      <path d="M40 11.3 54 11v14" fill="none" stroke="var(--leaf)" strokeWidth="2.4" strokeLinejoin="round" />
      <circle cx="26" cy="31" r="2.3" fill="var(--ink)" />
      <circle cx="37" cy="30" r="2.3" fill="var(--ink)" />
      <path d="M27 39.5c3 1.6 6.5 1.6 9.5-.3" fill="none" stroke="var(--ink)" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}
