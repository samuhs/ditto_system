import { Drawer, Loader, Select } from "@mantine/core";
import { useEffect, useMemo, useState } from "react";

import { getExperimentDifficulty } from "../api/client";
import type { ExperimentDifficulty, QuestionDifficulty } from "../api/types";
import { term } from "../glossary";
import { DifficultyGuide } from "./DifficultyGuide";
import { Errata, Note, errorText } from "./Notice";
import { ScoreCell } from "./Score";

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
  evidence_count: "Trechos de evidência",
  evidence_overlap: "Palavras da pergunta na evidência",
  evidence_distance: "Distância pergunta–evidência (GRADE)",
  top_score: "Nota do melhor trecho",
  score_gap: "Distância do 1º para o 2º trecho",
  score_spread: "Dispersão das notas dos trechos",
};

const FLAG_SIGNALS = new Set(["temporal", "numeric", "negation", "aggregation", "yes_no"]);

export function formatSignal(name: string, value: number): string {
  if (FLAG_SIGNALS.has(name)) return value >= 1 ? "sim" : "não";
  if (name === "out_of_corpus" || name === "evidence_overlap") return `${Math.round(value * 100)}%`;
  if (name === "question_length" || name === "sub_questions" || name === "evidence_count") {
    return String(value);
  }
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

function signed(value: number | undefined): string {
  if (value === undefined) return "—";
  return `${value > 0 ? "+" : ""}${value.toFixed(2)}`;
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

  // The IRT fit is per metric, so choosing another metric refetches.
  useEffect(() => {
    let active = true;
    getExperimentDifficulty(experimentId, metric ?? undefined)
      .then((d) => {
        if (!active) return;
        setData(d);
        if (d.metric && d.metric !== metric) setMetric(d.metric);
      })
      .catch((e) => active && setError(errorText(e)));
    return () => {
      active = false;
    };
  }, [experimentId, metric]);

  const irt = data?.irt ?? null;
  const questions = useMemo(() => {
    if (!data || !metric) return [];
    // Hardest first: highest IRT difficulty, else lowest mean of the metric.
    const hardness = (q: QuestionDifficulty) =>
      irt?.difficulty[q.question] ?? -(meanOver(q, metric) ?? 2);
    return [...data.questions].sort((a, b) => hardness(b) - hardness(a));
  }, [data, metric, irt]);

  if (error) return <Errata title="Não foi possível carregar a dificuldade">{error}.</Errata>;
  if (!data) return <Loader aria-label="Carregando dificuldade" />;
  if (!metric || data.llms.length === 0) {
    return <Note title="Sem respostas avaliadas">A dificuldade aparece quando houver respostas com nota.</Note>;
  }

  const hasClosedBook = data.questions.some((q) =>
    Object.values(q.by_llm).some((c) => metric in c.closed_book),
  );
  const hasOracle = data.questions.some((q) =>
    Object.values(q.by_llm).some((c) => metric in (c.oracle ?? {})),
  );
  const hasEvidence = data.questions.some((q) =>
    Object.values(q.by_llm).some((c) => c.hit_rate !== null),
  );
  const perLlm = 1 + (hasClosedBook ? 1 : 0) + (hasOracle ? 1 : 0) + (hasEvidence ? 1 : 0);

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
        <div>
          <DifficultyGuide />
        </div>
      </div>
      {irt && !irt.reliable && (
        <Note title="TRI só indicativa">
          Com {irt.n_questions} {irt.n_questions === 1 ? "pergunta" : "perguntas"} a dificuldade
          estimada pela TRI serve para testar o fluxo, não para tirar conclusões. Use pelo menos{" "}
          {irt.min_questions} perguntas no experimento final.
        </Note>
      )}
      <p className="ditto-caption">
        <strong>Tabela 2.</strong> Nota média de cada pergunta por modelo, sobre as combinações com
        busca (± desvio entre elas). As mais difíceis vêm primeiro.
        {irt && " “TRI” é a dificuldade estimada sobre todas as combinações: acima de 0, mais difícil que a média."}
        {hasClosedBook && " “Sem busca” é o mesmo modelo respondendo sem os documentos."}
        {hasOracle && " “Oráculo” é o modelo com o trecho correto no contexto: o melhor que ele consegue."}
        {hasEvidence && " “Evidência” é a parte das buscas que trouxe o trecho anotado."} Clique numa
        pergunta para ver os sinais dela.
      </p>
      <div className="ditto-table-wrap">
        <table className="ditto-table" data-stack="true">
          <thead>
            <tr>
              <th rowSpan={2}>Pergunta</th>
              {irt && (
                <th rowSpan={2} className="ditto-num">
                  TRI
                </th>
              )}
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
                hasOracle && <th key={`${llm}-o`} className="ditto-num">Oráculo</th>,
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
                {irt && (
                  <td className="ditto-num" data-label="TRI">
                    {signed(irt.difficulty[q.question])}
                  </td>
                )}
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
                    hasOracle && (
                      <td key={`${llm}-o`} className="ditto-num" data-label={`${llm} · oráculo`}>
                        <ScoreCell value={cell?.oracle?.[metric] ?? null} />
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
            {irt && (
              <div>
                <h3 className="ditto-h3" style={{ marginBottom: 8 }}>
                  Dificuldade estimada (TRI, {term("metric", irt.metric).name})
                </h3>
                <dl className="ditto-kv">
                  <dt>Todas as combinações</dt>
                  <dd>{signed(irt.difficulty[open.question])}</dd>
                  {data.llms.map((llm) => (
                    <div key={llm} style={{ display: "contents" }}>
                      <dt>{llm}</dt>
                      <dd>{signed(irt.difficulty_by_llm[llm]?.[open.question])}</dd>
                    </div>
                  ))}
                </dl>
              </div>
            )}
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
