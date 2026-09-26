import { DIMENSION_LABEL, term } from "../glossary";

/** A 0..1 metric as a number plus a short ink bar; the best value in a column is bold. */
export function ScoreCell({ value, best }: { value: number | null; best?: boolean }) {
  if (value === null) return <span className="ditto-score-na">—</span>;
  const pct = Math.max(0, Math.min(1, value)) * 100;
  return (
    <span className="ditto-score" data-best={best || undefined}>
      <span>{value.toFixed(2)}</span>
      <span className="ditto-score-track" aria-hidden>
        <span className="ditto-score-fill" style={{ width: `${pct}%` }} />
      </span>
    </span>
  );
}

export interface Combination {
  chunking: string;
  embedding: string;
  rag: string;
  retriever: string;
  llm: string;
}

/** The five traits of a combination, each labelled with its dimension. */
export function Traits({ combo }: { combo: Combination }) {
  // "Sem busca" runs attached to an index and retriever it never uses.
  const unused = combo.rag === "closed_book" ? "—" : null;
  const items: [string, string][] = [
    [DIMENSION_LABEL.chunking, unused ?? term("chunking", combo.chunking).name],
    [DIMENSION_LABEL.embedding, unused ?? term("embedding", combo.embedding).name],
    [DIMENSION_LABEL.rag, term("rag", combo.rag).name],
    [DIMENSION_LABEL.retriever, unused ?? term("retriever", combo.retriever).name],
    ["LLM", combo.llm],
  ];
  return (
    <span className="ditto-traits">
      {items.map(([dim, name]) => (
        <span key={dim} className="ditto-trait" title={`${dim}: ${name}`}>
          <span className="ditto-trait-dim">{dim}</span>
          {name}
        </span>
      ))}
    </span>
  );
}
