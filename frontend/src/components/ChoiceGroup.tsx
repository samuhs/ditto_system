import { Button } from "@mantine/core";
import type { ReactNode } from "react";

export interface Choice {
  value: string;
  name: string;
  /** Registry key, shown in mono when it differs from the name. */
  code?: string;
  description?: string;
  tag?: string;
}

interface ChoiceGroupProps {
  legend: string;
  choices: Choice[];
  value: string[];
  onChange: (value: string[]) => void;
  /** Single choice renders radios; the value array then holds at most one item. */
  single?: boolean;
  empty?: ReactNode;
}

/** Options as leaves the user can read before choosing: name, key and what it does. */
export function ChoiceGroup({ legend, choices, value, onChange, single, empty }: ChoiceGroupProps) {
  const all = choices.length > 0 && value.length === choices.length;

  function toggle(v: string) {
    if (single) onChange([v]);
    else onChange(value.includes(v) ? value.filter((x) => x !== v) : [...value, v]);
  }

  return (
    <fieldset className="ditto-choice-set">
      <legend className="visually-hidden">{legend}</legend>
      <div className="ditto-choice-group-head">
        <span className="ditto-h3" aria-hidden>
          {legend}
        </span>
        {!single && choices.length > 1 && (
          <span className="ditto-row-actions">
            <span className="ditto-choice-count">
              {value.length} de {choices.length}
            </span>
            <Button
              variant="subtle"
              size="compact-sm"
              onClick={() => onChange(all ? [] : choices.map((c) => c.value))}
            >
              {all ? "Desmarcar todos" : "Marcar todos"}
            </Button>
          </span>
        )}
      </div>
      {choices.length === 0 ? (
        <div className="ditto-read" style={{ marginTop: 8 }}>{empty}</div>
      ) : (
        <div className="ditto-choices">
          {choices.map((c) => (
            <label key={c.value} className="ditto-choice">
              <input
                type={single ? "radio" : "checkbox"}
                name={single ? legend : undefined}
                value={c.value}
                checked={value.includes(c.value)}
                onChange={() => toggle(c.value)}
              />
              <span className="ditto-hole" aria-hidden />
              <span className="ditto-choice-name">
                {c.name}
                {c.code && c.code !== c.name && <span className="ditto-choice-key">{c.code}</span>}
                {c.tag && <span className="ditto-choice-tag">{c.tag}</span>}
              </span>
              {c.description && <span className="ditto-choice-desc">{c.description}</span>}
            </label>
          ))}
        </div>
      )}
    </fieldset>
  );
}
