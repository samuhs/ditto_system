import { Alert, Collapse, Select, Text } from "@mantine/core";
import { Fragment, useEffect, useState } from "react";

import { getExperiment, listExperiments } from "../api/client";
import type { ExperimentDetail, ExperimentSummary } from "../api/types";
import { PageHeader } from "../components/PageHeader";

/** Map a 0–1 score to an accent color: high = green, low = pink. */
function scoreColor(value: number): string {
  if (value >= 0.7) return "#07f285";
  if (value >= 0.45) return "#05dbf2";
  if (value >= 0.25) return "#f2ec91";
  return "#f26dcf";
}

function truncateAnswer(answer: string, max = 60): string {
  return answer.length > max ? `${answer.slice(0, max)}…` : answer;
}

export function ResultsPage() {
  const [experiments, setExperiments] = useState<ExperimentSummary[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<ExperimentDetail | null>(null);
  const [openRow, setOpenRow] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listExperiments()
      .then((rows) => {
        setExperiments(rows);
        if (rows.length > 0) setSelected(String(rows[0].id));
      })
      .catch((e) => setError(String(e)));
  }, []);

  useEffect(() => {
    if (selected)
      getExperiment(Number(selected))
        .then(setDetail)
        .catch((e) => setError(String(e)));
  }, [selected]);

  return (
    <div>
      <PageHeader
        eyebrow="Passo 03 · Ranquear"
        title="Resultados"
        subtitle="Cada linha é uma forma que o Ditto assumiu. As barras coloridas mostram a qualidade de cada métrica — verde é bom, rosa pede atenção. Clique para abrir a resposta completa."
      />

      {error && (
        <Alert color="red" variant="light" title="Erro" mb="lg" radius="lg" maw={520}>
          {error}
        </Alert>
      )}

      <Select
        label="Experimento"
        placeholder="Selecione um experimento"
        data={experiments.map((e) => ({
          value: String(e.id),
          label: `${e.name} (${e.status})`,
        }))}
        value={selected}
        onChange={setSelected}
        maw={380}
        mb="xl"
        searchable
      />

      {detail && (
        <div className="ditto-table-wrap">
          <table>
            <thead>
              <tr>
                <th style={{ width: "26%" }}>Combinação</th>
                <th style={{ width: "26%" }}>Pergunta</th>
                <th style={{ width: "26%" }}>Resposta</th>
                <th style={{ width: "22%" }}>Scores</th>
              </tr>
            </thead>
            <tbody>
              {detail.results.length === 0 && (
                <tr>
                  <td colSpan={4} className="ditto-empty">
                    Nenhum resultado para este experimento ainda.
                  </td>
                </tr>
              )}
              {detail.results.map((row, index) => {
                const open = openRow === index;
                return (
                  <Fragment key={index}>
                    <tr
                      className="ditto-row"
                      data-open={open}
                      onClick={() => setOpenRow(open ? null : index)}
                    >
                      <td>
                        <div className="ditto-combo">
                          <span>{row.chunking}</span>
                          <span>{row.embedding}</span>
                          <span>{row.rag}</span>
                          <span>{row.retriever}</span>
                        </div>
                      </td>
                      <td>{row.question}</td>
                      {/* Hide answer preview when expanded to avoid duplicate matches */}
                      <td>{open ? null : truncateAnswer(row.answer)}</td>
                      <td>
                        <div className="ditto-scores-mini">
                          {Object.entries(row.scores).map(([key, value]) => (
                            <span key={key} className="ditto-score-pill">
                              <span
                                className="ditto-score-dot"
                                style={{ background: scoreColor(value) }}
                              />
                              {value.toFixed(2)}
                            </span>
                          ))}
                        </div>
                      </td>
                    </tr>
                    <tr>
                      <td colSpan={4} style={{ padding: 0, borderBottom: 0 }}>
                        <Collapse in={open}>
                          {open && (
                            <div className="ditto-expand">
                              <Text className="ditto-eyebrow" mb={6}>
                                Resposta completa
                              </Text>
                              <Text mb="md" style={{ lineHeight: 1.6 }}>
                                {row.answer}
                              </Text>

                              {Object.entries(row.scores).map(([key, value]) => (
                                <div key={key} className="ditto-score-bar-row">
                                  <span className="ditto-score-bar-label">{key}</span>
                                  <span className="ditto-score-bar-track">
                                    <span
                                      className="ditto-score-bar-fill"
                                      style={{
                                        width: `${Math.max(0, Math.min(1, value)) * 100}%`,
                                        background: scoreColor(value),
                                        boxShadow: `0 0 12px ${scoreColor(value)}`,
                                      }}
                                    />
                                  </span>
                                  <span className="ditto-score-bar-val">
                                    {value.toFixed(2)}
                                  </span>
                                </div>
                              ))}

                              <div className="ditto-meta-chips">
                                <span
                                  className="ditto-chip"
                                  style={{ color: "#05dbf2" }}
                                >
                                  {row.latency_ms} ms
                                </span>
                                <span
                                  className="ditto-chip"
                                  style={{ color: "#f2ec91" }}
                                >
                                  {row.tokens} tokens
                                </span>
                              </div>
                            </div>
                          )}
                        </Collapse>
                      </td>
                    </tr>
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
