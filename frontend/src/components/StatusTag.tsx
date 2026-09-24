import { statusInfo } from "../glossary";

/** Status as glyph + word; the colour is a third, redundant signal. */
export function StatusTag({ status, label }: { status: string; label?: string }) {
  const info = statusInfo(status);
  return (
    <span className="ditto-status" data-tone={info.tone}>
      <span className="ditto-status-glyph" aria-hidden />
      {label ?? info.label}
    </span>
  );
}
