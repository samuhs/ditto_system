import { Drawer, Loader, Select } from "@mantine/core";
import { useEffect, useMemo, useState } from "react";

import { getExperimentDifficulty } from "../api/client";
import type { ExperimentDifficulty, QuestionDifficulty } from "../api/types";
import { term } from "../glossary";
import { Errata, Note, errorText } from "./Notice";
import { ScoreCell } from "./Score";

/** Answer-quality metrics tried, in order, as the default for the table. */
const PREFERRED_METRICS = ["chrf", "token_f1", "answer_correctness", "rouge_l"];

export const SIGNAL_LABELS: Record<string, string> = {
  question_length: "Palavras na pergunta",
  sub_questions: "Perguntas numa só",
  temporal: "Sobre horário ou data",
  numeric: "Pede número ou preço",
  negation: "Tem negação",
  aggregation: "Pede lista ou vários itens",
  yes_no: "Sim ou não",
  mean_idf: "Raridade média dos termos (IDF)",
  max_idf: "Termo mais raro (IDF)",
  out_of_corpus: "Termos fora dos documentos",
  top_score: "Nota do melhor trecho",
  score_gap: "Distância do 1º para o 2º trecho",
  score_spread: "Dispersão das notas dos trechos",
};

const FLAG_SIGNALS = new Set(["temporal", "numeric", "negation", "aggregation", "yes_no"]);

export function formatSignal(name: string, value: number): string {
  if (FLAG_SIGNALS.has(name)) return value >= 1 ? "sim" : "não";
  if (name === "out_of_corpus") return `${Math.round(value * 100)}%`;
  if (name === "question_length" || name === "sub_questions") return String(value);
  return value.toFixed(2);
}

function SignalList({ signals }: { signals: Record<string, number> }) {
  const entries = Object.entries(signals);
  if (entries.length === 0) return <p className="ditto-muted">Nenhum sinal registrado.</p>;
  return (
    <dl className="ditto-kv">
      {entries.map(([name, value]) => (
        <div key={name} style={{ display: "contents" }}>
          <dt>{SIGNAL_LABELS[name] ?? name}</dt>
          <dd>{formatSignal(name, value)}</dd>
        </div>
      ))}
    </dl>
  );
}

function meanOver(q: QuestionDifficulty, metric: string): number | null {
  const values = Object.values(q.by_llm)
    .map((cell) => cell.retrieval[metric]?.mean)
    .filter((v): v is number => v !== undefined);
  return values.length ? values.reduce((a, b) => a + b, 0) / values.length : null;
}

export function DifficultyPanel({ experimentId }: { experimentId: number }) {
  const [data, setData] = useState<ExperimentDifficulty | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [metric, setMetric] = useState<string | null>(null);
  const [open, setOpen] = useState<QuestionDifficulty | null>(null);

  useEffect(() => {
    let active = true;
    getExperimentDifficulty(experimentId)
      .then((d) => {
        if (!active) return;
        setData(d);
        setMetric(PREFERRED_METRICS.find((m) => d.metrics.includes(m)) ?? d.metrics[0] ?? null);
      })
      .catch((e) => active && setError(errorText(e)));
    return () => {
      active = false;
    };
  }, [experimentId]);

  const questions = useMemo(() => {
    if (!data || !metric) return [];
    // Hardest first: lowest mean of the chosen metric over the models.
    return [...data.questions].sort((a, b) => (meanOver(a, metric) ?? 2) - (meanOver(b, metric) ?? 2));
  }, [data, metric]);

  if (error) return <Errata title="Não foi possível carregar a dificuldade">{error}.</Errata>;
  if (!data) return <Loader aria-label="Carregando dificuldade" />;
  if (!metric || data.llms.length === 0) {
    return <Note title="Sem respostas avaliadas">A dificuldade aparece quando houver respostas com nota.</Note>;
  }

  const hasClosedBook = data.questions.some((q) =>
    Object.values(q.by_llm).some((c) => metric in c.closed_book),
  );
  const hasEvidence = data.questions.some((q) =>
    Object.values(q.by_llm).some((c) => c.hit_rate !== null),
  );
  const perLlm = 1 + (hasClosedBook ? 1 : 0) + (hasEvidence ? 1 : 0);

  return (
    <>
      <div className="ditto-filters">
        <Select
          label="Métrica"
          data={data.metrics.map((m) => ({ value: m, label: term("metric", m).name }))}
          value={metric}
          onChange={(v) => v && setMetric(v)}
          allowDeselect={false}
          size="sm"
          w={240}
        />
      </div>
      <p className="ditto-caption">
        <strong>Tabela 2.</strong> Nota média de cada pergunta por modelo, sobre as combinações com
        busca (± desvio entre elas). As mais difíceis vêm primeiro.
        {hasClosedBook && " “Sem busca” é o mesmo modelo respondendo sem os documentos."}
        {hasEvidence && " “Evidência” é a parte das buscas que trouxe o trecho anotado."} Clique numa
        pergunta para ver os sinais dela.
      </p>
      <div className="ditto-table-wrap">
        <table className="ditto-table" data-stack="true">
          <thead>
            <tr>
              <th rowSpan={2}>Pergunta</th>
              {data.llms.map((llm) => (
                <th key={llm} colSpan={perLlm} className="ditto-num">
                  {llm}
                </th>
              ))}
            </tr>
            <tr>
              {data.llms.map((llm) => [
                <th key={`${llm}-r`} className="ditto-num">Com busca</th>,
                hasClosedBook && <th key={`${llm}-c`} className="ditto-num">Sem busca</th>,
                hasEvidence && <th key={`${llm}-e`} className="ditto-num">Evidência</th>,
              ])}
            </tr>
          </thead>
          <tbody>
            {questions.map((q) => (
              <tr key={q.question} data-clickable="true" onClick={() => setOpen(q)}>
                <td className="ditto-cell-text" data-label="Pergunta">
                  <button
                    type="button"
                    className="ditto-sort ditto-clip"
                    style={{ textAlign: "left" }}
                    onClick={(e) => {
                      e.stopPropagation();
                      setOpen(q);
                    }}
                  >
                    {q.question}
                  </button>
                </td>
                {data.llms.map((llm) => {
                  const cell = q.by_llm[llm];
                  const summary = cell?.retrieval[metric];
                  return [
                    <td key={`${llm}-r`} className="ditto-num" data-label={`${llm} · com busca`}>
                      <ScoreCell value={summary?.mean ?? null} />
                      {summary && summary.n > 1 && (
                        <span className="ditto-muted" style={{ fontSize: 12 }}>
                          ±{summary.std.toFixed(2)}
                        </span>
                      )}
                    </td>,
                    hasClosedBook && (
                      <td key={`${llm}-c`} className="ditto-num" data-label={`${llm} · sem busca`}>
                        <ScoreCell value={cell?.closed_book[metric] ?? null} />
                      </td>
                    ),
                    hasEvidence && (
                      <td key={`${llm}-e`} className="ditto-num" data-label={`${llm} · evidência`}>
                        {cell?.hit_rate == null ? (
                          <span className="ditto-score-na">—</span>
                        ) : (
                          `${Math.round(cell.hit_rate * 100)}%`
                        )}
                      </td>
                    ),
                  ];
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <Drawer opened={open !== null} onClose={() => setOpen(null)} title="Dificuldade da pergunta">
        {open && (
          <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>
            <p className="ditto-read" style={{ color: "var(--ink)", margin: 0 }}>
              {open.question}
            </p>
            <div>
              <h3 className="ditto-h3" style={{ marginBottom: 8 }}>
                Sinais antes da busca
              </h3>
              <SignalList signals={open.signals} />
            </div>
            <div>
              <h3 className="ditto-h3" style={{ marginBottom: 8 }}>
                Sinais da busca (média das combinações)
              </h3>
              <SignalList signals={open.retrieval_signals} />
            </div>
            {hasEvidence && (
              <div>
                <h3 className="ditto-h3" style={{ marginBottom: 8 }}>
                  {term("metric", metric).name} com e sem a evidência no contexto
                </h3>
                <p className="ditto-muted" style={{ marginTop: 0, fontSize: 13 }}>
                  Nota baixa mesmo com a evidência no contexto indica que o modelo não a usou: a
                  dificuldade está na geração, não na busca.
                </p>
                <table className="ditto-table">
                  <thead>
                    <tr>
                      <th>Modelo</th>
                      <th className="ditto-num">Com evidência</th>
                      <th className="ditto-num">Sem evidência</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(open.by_llm).map(([llm, cell]) => (
                      <tr key={llm}>
                        <td>{llm}</td>
                        <td className="ditto-num">
                          <ScoreCell value={cell.with_evidence[metric] ?? null} />
                        </td>
                        <td className="ditto-num">
                          <ScoreCell value={cell.without_evidence[metric] ?? null} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </Drawer>
    </>
  );
}
