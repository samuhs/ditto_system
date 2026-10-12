import { Button, Checkbox, Loader, NativeSelect } from "@mantine/core";
import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { getComparison, getExperiment, listBases, listExperiments } from "../api/client";
import type {
  Comparison, ComparisonDiff, ComparisonFriedman, ExperimentRunRef, ExperimentSummary,
} from "../api/types";
import { Errata, Note, errorText } from "../components/Notice";
import { PageHeader } from "../components/PageHeader";
import { ScoreCell, Traits } from "../components/Score";
import { questionType, term } from "../glossary";

/** Items of the Comparação in the URL: `?items=25:3,37:12&baseline=25:3&metric=...`. */
function itemsOf(params: URLSearchParams): string[] {
  return (params.get("items") ?? "").split(",").filter(Boolean);
}

function signed(value: number): string {
  return `${value >= 0 ? "+" : "−"}${Math.abs(value).toFixed(3)}`;
}

function DiffCell({ diff }: { diff: ComparisonDiff | null }) {
  if (!diff) return <span className="ditto-choice-tag">Linha de base</span>;
  return (
    <span className="ditto-diff" data-significant={diff.significant || undefined}>
      <b>{signed(diff.mean)}</b>
      {diff.significant && <span aria-label="significativa" title="IC 95% não cruza zero">*</span>}{" "}
      <span className="ditto-muted">[{diff.low.toFixed(3)}, {diff.high.toFixed(3)}]</span>
    </span>
  );
}

function pValue(p: number): string {
  return p < 0.001 ? "p < 0.001" : `p = ${p.toFixed(3)}`;
}

/** The global test: is there any difference among the paired Combinações? */
function FriedmanLine({ friedman }: { friedman: ComparisonFriedman }) {
  if (friedman.reason !== undefined) {
    return <p className="ditto-muted">Friedman não calculado: {friedman.reason}.</p>;
  }
  return (
    <p>
      Friedman: χ² = {friedman.chi2.toFixed(2)}, {friedman.df}{" "}
      {friedman.df === 1 ? "grau" : "graus"} de liberdade, {pValue(friedman.p)}, sobre{" "}
      {friedman.n} {friedman.n === 1 ? "pergunta" : "perguntas"}
    </p>
  );
}

function runLabel(run: ExperimentRunRef): string {
  const index = run.rag === "closed_book" || run.rag === "oracle"
    ? "" : ` · ${term("chunking", run.chunking).name} × ${term("embedding", run.embedding).name}`;
  return `${term("rag", run.rag).name} · ${term("retriever", run.retriever).name} · ${run.llm}${index}`;
}

/** Base → Experimento → Combinações: ticking a Combinação adds it to the Comparação. */
function Picker({ items, onToggle }: { items: string[]; onToggle: (id: string) => void }) {
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

export function ComparePage() {
  const [params, setParams] = useSearchParams();
  const items = useMemo(() => itemsOf(params), [params]);
  const baseline = params.get("baseline");
  const metric = params.get("metric");
  const [data, setData] = useState<Comparison | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setData(null);
    setError(null);
    if (items.length === 0) return;
    getComparison(items, baseline, metric)
      .then(setData)
      .catch((e) => setError(errorText(e)));
  }, [items, baseline, metric]);

  const others = data ? data.metrics.filter((m) => m !== data.metric) : [];

  /** Writes the Comparação back to the URL: the link always reopens what is shown. */
  function update(next: { items?: string[]; baseline?: string | null; metric?: string | null }) {
    const nextItems = next.items ?? items;
    let nextBaseline = next.baseline !== undefined ? next.baseline : baseline;
    if (nextBaseline && !nextItems.includes(nextBaseline)) nextBaseline = null;
    const nextMetric = next.metric !== undefined ? next.metric : metric;
    const query = new URLSearchParams();
    if (nextItems.length) query.set("items", nextItems.join(","));
    if (nextBaseline) query.set("baseline", nextBaseline);
    if (nextMetric) query.set("metric", nextMetric);
    setParams(query);
  }

  function toggle(id: string) {
    update({ items: items.includes(id) ? items.filter((i) => i !== id) : [...items, id] });
  }

  return (
    <div>
      <PageHeader
        title="Comparar"
        lede="Combinações de um ou mais experimentos medidas contra uma Linha de base, pergunta a pergunta, com intervalo de confiança de 95%."
      />

      <Picker items={items} onToggle={toggle} />

      {items.length === 0 && (
        <Note title="Nenhuma combinação escolhida">
          Escolha uma Base e um experimento acima, ou abra um experimento em Resultados e use
          “Comparar”. A primeira combinação marcada é a Linha de base.
        </Note>
      )}

      {error && <Errata title="Não foi possível montar a comparação">{error}</Errata>}
      {items.length > 0 && !data && !error && <Loader size="sm" />}

      {data && (
        <section aria-labelledby="comparison-caption">
          <div className="ditto-toolbar">
            <NativeSelect
              label="Métrica principal"
              value={data.metric}
              onChange={(e) => update({ metric: e.currentTarget.value })}
              data={data.metrics.map((m) => ({ value: m, label: term("metric", m).name }))}
            />
          </div>
          <p id="comparison-caption" className="ditto-muted">
            Base {data.base} · métrica principal {term("metric", data.metric).name}. Diferença = média
            da combinação menos a da Linha de base nas perguntas que as duas responderam; * quando o
            intervalo não cruza zero.
          </p>
          <div className="ditto-table-wrap">
            <table className="ditto-table" data-stack="true" aria-labelledby="comparison-caption">
              <thead>
                <tr>
                  <th>Combinação</th>
                  <th>Experimento</th>
                  <th className="ditto-num">Perguntas</th>
                  <th className="ditto-num">{term("metric", data.metric).name}</th>
                  <th>Diferença [IC 95%]</th>
                  {others.map((m) => (
                    <th key={m} className="ditto-num">{term("metric", m).name}</th>
                  ))}
                  <th><span className="visually-hidden">Ações</span></th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((it) => (
                  <tr key={it.id} data-best={it.diff === null || undefined}>
                    <td className="ditto-cell-combo"><Traits combo={it} /></td>
                    <td>
                      <Link to={`/results/${it.experiment_id}`}>{it.experiment_name}</Link>
                      {it.partial && <> <span className="ditto-choice-tag">parcial</span></>}
                    </td>
                    <td className="ditto-num">{it.n}</td>
                    <td className="ditto-num"><ScoreCell value={it.means[data.metric] ?? null} /></td>
                    <td><DiffCell diff={it.diff} /></td>
                    {others.map((m) => (
                      <td key={m} className="ditto-num"><ScoreCell value={it.means[m] ?? null} /></td>
                    ))}
                    <td className="ditto-row-actions">
                      {it.diff !== null && (
                        <Button size="xs" variant="subtle" onClick={() => update({ baseline: it.id })}>
                          Usar como Linha de base
                        </Button>
                      )}
                      <Button size="xs" variant="subtle" onClick={() => toggle(it.id)}>
                        Remover
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {data.by_type.rows.length > 0 && (
            <>
              <h2 className="ditto-h3" id="by-type-caption">
                Diferença por tipo de pergunta
              </h2>
              <div className="ditto-table-wrap">
                <table className="ditto-table" data-stack="true" aria-labelledby="by-type-caption">
                  <thead>
                    <tr>
                      <th>Combinação</th>
                      {data.by_type.types.map((t) => (
                        <th key={t}>{questionType(t).name}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {data.by_type.rows.map((row) => {
                      const it = data.items.find((i) => i.id === row.id);
                      return (
                        <tr key={row.id}>
                          <td className="ditto-cell-combo">{it ? <Traits combo={it} /> : row.id}</td>
                          {data.by_type.types.map((t) => {
                            const cell = row.cells[t];
                            return (
                              <td key={t}>
                                {cell ? (
                                  <>
                                    <DiffCell diff={cell} />{" "}
                                    <span className="ditto-muted">n = {cell.n}</span>
                                  </>
                                ) : (
                                  <span className="ditto-score-na">—</span>
                                )}
                              </td>
                            );
                          })}
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </>
          )}

          {data.other_bases.length > 0 && (
            <>
              <h2 className="ditto-h3" id="other-bases-caption">
                Outras Bases (sem pareamento)
              </h2>
              <p className="ditto-muted">
                Perguntas diferentes não se comparam uma a uma: aqui só a média de cada combinação,
                com o intervalo de 95% dela.
              </p>
              <div className="ditto-table-wrap">
                <table className="ditto-table" data-stack="true" aria-labelledby="other-bases-caption">
                  <thead>
                    <tr>
                      <th>Combinação</th>
                      <th>Base</th>
                      <th>Experimento</th>
                      <th className="ditto-num">Perguntas</th>
                      <th>{term("metric", data.metric).name} [IC 95%]</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.other_bases.map((it) => (
                      <tr key={it.id}>
                        <td className="ditto-cell-combo"><Traits combo={it} /></td>
                        <td>{it.base}</td>
                        <td>
                          <Link to={`/results/${it.experiment_id}`}>{it.experiment_name}</Link>
                          {it.partial && <> <span className="ditto-choice-tag">parcial</span></>}
                        </td>
                        <td className="ditto-num">{it.n}</td>
                        <td className="ditto-diff">
                          <b>{it.mean.mean.toFixed(3)}</b>{" "}
                          <span className="ditto-muted">
                            [{it.mean.low.toFixed(3)}, {it.mean.high.toFixed(3)}]
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}

          <FriedmanLine friedman={data.friedman} />
          <p className="ditto-muted">
            Sem correção para comparações múltiplas: com muitas combinações, alguma marca * pode
            ser acaso. O Friedman usa só as perguntas que todas as combinações pareadas responderam.
          </p>

          {data.excluded.length > 0 && (
            <Note title="Fora da comparação">
              <ul>
                {data.excluded.map((e) => (
                  <li key={e.id}>{e.id}: {e.reason}</li>
                ))}
              </ul>
            </Note>
          )}
        </section>
      )}
    </div>
  );
}
