import { Checkbox, NativeSelect } from "@mantine/core";
import { useEffect, useState } from "react";

import { getExperiment, listBases, listExperiments } from "../api/client";
import type { ExperimentRunRef, ExperimentSummary } from "../api/types";
import { term } from "../glossary";

import { Errata, errorText } from "./Notice";

export function runLabel(run: ExperimentRunRef): string {
  const index = run.rag === "closed_book" || run.rag === "oracle"
    ? "" : ` · ${term("chunking", run.chunking).name} × ${term("embedding", run.embedding).name}`;
  return `${term("rag", run.rag).name} · ${term("retriever", run.retriever).name} · ${run.llm}${index}`;
}

/** Base → Experimento → Combinações: ticking a Combinação adds it to the Comparação. */
export function CombinationPicker({ items, onToggle }: { items: string[]; onToggle: (id: string) => void }) {
  const [bases, setBases] = useState<string[]>([]);
  const [base, setBase] = useState("");
  const [experiments, setExperiments] = useState<ExperimentSummary[]>([]);
  const [experimentId, setExperimentId] = useState("");
  const [runs, setRuns] = useState<ExperimentRunRef[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listBases().then((b) => setBases(b.map((x) => x.name))).catch((e) => setError(errorText(e)));
  }, []);
  useEffect(() => {
    setExperiments([]);
    setExperimentId("");
    if (!base) return;
    listExperiments(1, 100, base).then((l) => setExperiments(l.items)).catch((e) => setError(errorText(e)));
  }, [base]);
  useEffect(() => {
    setRuns([]);
    if (!experimentId) return;
    getExperiment(Number(experimentId)).then((d) => setRuns(d.runs ?? [])).catch((e) => setError(errorText(e)));
  }, [experimentId]);

  return (
    <section className="ditto-compare-picker" aria-label="Adicionar combinações">
      <div className="ditto-toolbar">
        <NativeSelect
          label="Base"
          value={base}
          onChange={(e) => setBase(e.currentTarget.value)}
          data={[{ value: "", label: "Escolha a Base" }, ...bases.map((b) => ({ value: b, label: b }))]}
        />
        {base && (
          <NativeSelect
            label="Experimento"
            value={experimentId}
            onChange={(e) => setExperimentId(e.currentTarget.value)}
            data={[
              { value: "", label: experiments.length ? "Escolha o experimento" : "Nenhum experimento nesta Base" },
              ...experiments.map((x) => ({ value: String(x.id), label: `${x.name} (#${x.id})` })),
            ]}
          />
        )}
      </div>
      {runs.length > 0 && (
        <div className="ditto-compare-runs">
          {runs.map((run) => {
            const id = `${experimentId}:${run.id}`;
            return (
              <Checkbox
                key={id}
                label={runLabel(run)}
                checked={items.includes(id)}
                onChange={() => onToggle(id)}
              />
            );
          })}
        </div>
      )}
      {error && <Errata title="Não foi possível carregar as opções">{error}</Errata>}
    </section>
  );
}

