/** Tipo de pergunta of result rows: which types an experiment has and the rows of one. */
import type { ExperimentResultRow } from "../api/types";
import { DEFAULT_QUESTION_TYPE, QUESTION_TYPES } from "../glossary";

/** Filter value meaning every Tipo de pergunta. */
export const ALL_TYPES = "__all__";

const ORDER = Object.keys(QUESTION_TYPES);

/** A row's Tipo de pergunta; rows stored before annotations existed are "simples". */
export function typeOf(row: { question_type?: string }): string {
  return row.question_type || DEFAULT_QUESTION_TYPE;
}

/** Types present in the rows, in glossary order (unknown ones last, by name). */
export function typesIn(rows: ExperimentResultRow[]): string[] {
  const rank = (t: string) => (ORDER.includes(t) ? ORDER.indexOf(t) : ORDER.length);
  return [...new Set(rows.map(typeOf))].sort((a, b) => rank(a) - rank(b) || a.localeCompare(b));
}

/** The rows of one type, or all of them for ALL_TYPES. */
export function ofType(rows: ExperimentResultRow[], type: string): ExperimentResultRow[] {
  return type === ALL_TYPES ? rows : rows.filter((r) => typeOf(r) === type);
}
