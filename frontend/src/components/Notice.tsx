import type { ReactNode } from "react";

import { AlertIcon, CheckIcon, InfoIcon } from "./icons";

/** Vermilion errata slip: the only place the error colour appears. */
export function Errata({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="ditto-errata" role="alert">
      <AlertIcon />
      <div className="ditto-errata-title">{title}</div>
      {children && <div className="ditto-errata-body">{children}</div>}
    </div>
  );
}

export function Note({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="ditto-note" role="status">
      <InfoIcon />
      <div className="ditto-note-title">{title}</div>
      {children && <div className="ditto-note-body">{children}</div>}
    </div>
  );
}

/** Inline confirmation next to the button that saved something. */
export function Saved({ children }: { children: ReactNode }) {
  return (
    <span className="ditto-saved" role="status">
      <CheckIcon />
      {children}
    </span>
  );
}

/** Turns thrown values into readable text without the "Error: " prefix. */
export function errorText(e: unknown): string {
  if (e instanceof Error) return e.message;
  return String(e).replace(/^Error:\s*/, "");
}
