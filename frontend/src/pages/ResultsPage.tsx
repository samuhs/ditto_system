import { ActionIcon, Alert, Collapse, Group, Loader, Text } from "@mantine/core";
import { Fragment, useEffect, useState } from "react";

import { getExperiment, listExperiments } from "../api/client";
import type { ExperimentDetail, ExperimentSummary } from "../api/types";
import { PageHeader } from "../components/PageHeader";

function statusColor(status: string): string {
  if (status === "done") return "#07f285";
  if (status === "failed") return "#f26dcf";
  return "#05dbf2";
}

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
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<ExperimentDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [openRow, setOpenRow] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listExperiments()
      .then(setExperiments)
      .catch((e) => setError(String(e)));
  }, []);

  useEffect(() => {
    if (selectedId === null) return;
    setDetailLoading(true);
    setDetail(null);
    setDetailError(null);
    setOpenRow(null);
    getExperiment(selectedId)
      .then(setDetail)
      .catch((e) => setDetailError(String(e)))
      .finally(() => setDetailLoading(false));
  }, [selectedId]);

  function closeDetail() {
    setSelectedId(null);
    setDetail(null);
    setDetailError(null);
    setOpenRow(null);
  }

  return (
    <div>
      <PageHeader
        eyebrow="Passo 03 · Ranquear"
        title="Resultados"
        subtitle="Clique num experimento para ver seus resultados. As barras coloridas mostram a qualidade de cada métrica — verde é bom, rosa pede atenção."
      />

      {error && (
        <Alert color="red" variant="light" title="Erro" mb="lg" radius="lg" maw={760}>
          {error}
        </Alert>
      )}

      {/* Detail panel — appears above list when an experiment is selected */}
      {selectedId !== null && (
        <div
          className="ditto-glass"
          style={{
            padding: "22px 26px",
            maxWidth: 900,
            marginBottom: 24,
            borderColor: detail ? statusColor(detail.status) : "var(--stroke)",
          }}
        >
          <Group justify="space-between" align="center" mb={16}>
            <div>
              <Text className="ditto-mono" size="xs" c="dimmed">
                EXPERIMENTO
              </Text>
              {detail && (
                <Group gap="xs" align="center" mt={4}>
                  <Text fw={700} fz="lg">
                    {detail.name}
                  </Text>
                  <span
                    className="ditto-chip"
                    style={{ color: statusColor(detail.status) }}
                  >
                    {detail.status}
                  </span>
                </Group>
              )}
            </div>
            <ActionIcon
              variant="subtle"
              color="gray"
              size="lg"
              onClick={closeDetail}
              aria-label="Fechar painel"
            >
              ✕
            </ActionIcon>
          </Group>

          {detailLoading && (
            <div style={{ display: "flex", justifyContent: "center", padding: "32px 0" }}>
              <Loader size="md" color="#05dbf2" />
            </div>
          )}

          {detailError && (
            <Alert color="red" variant="light" title="Erro ao carregar" radius="lg">
              {detailError}
            </Alert>
          )}

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
                        {detail.status === "done"
                          ? "Nenhum resultado para este experimento."
                          : "Experimento em andamento..."}
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
                                    <span className="ditto-chip" style={{ color: "#05dbf2" }}>
                                      {row.latency_ms} ms
                                    </span>
                                    <span className="ditto-chip" style={{ color: "#f2ec91" }}>
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
      )}

      {/* Experiment list */}
      <div className="ditto-exp-list" style={{ maxWidth: 900 }}>
        {experiments.length === 0 && !error && (
          <p className="ditto-empty">Nenhum experimento encontrado.</p>
        )}
        {experiments.map((exp) => (
          <button
            key={exp.id}
            className="ditto-exp-row"
            data-selected={selectedId === exp.id}
            onClick={() => setSelectedId(exp.id)}
          >
            <Text fw={600} fz="sm">
              {exp.name}
            </Text>
            <span className="ditto-chip" style={{ color: statusColor(exp.status) }}>
              {exp.status}
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}
