import {
  Alert,
  Button,
  Group,
  Loader,
  Modal,
  MultiSelect,
  Pagination,
  Select,
  Text,
} from "@mantine/core";
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { getExperiment, pauseExperiment } from "../api/client";
import type { ExperimentDetail, ExperimentResultRow } from "../api/types";
import { PageHeader } from "../components/PageHeader";
import { formatDuration } from "../utils/duration";

const MEDIA_KEY = "__media__";
const PAGE_SIZES = ["10", "25", "50", "100"];

function statusColor(status: string): string {
  if (status === "done") return "#07f285";
  if (status === "failed") return "#f26dcf";
  if (status === "paused") return "#f2ec91";
  return "#05dbf2";
}

function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("pt-BR");
}

function experimentDurationMs(createdAt?: string, finishedAt?: string): number | null {
  if (!createdAt) return null;
  const start = new Date(createdAt).getTime();
  const end = finishedAt ? new Date(finishedAt).getTime() : Date.now();
  return end - start;
}

function scoreColor(value: number): string {
  if (value >= 0.7) return "#07f285";
  if (value >= 0.45) return "#05dbf2";
  if (value >= 0.25) return "#f2ec91";
  return "#f26dcf";
}

function rowMedia(row: ExperimentResultRow): number | null {
  const values = Object.values(row.scores);
  if (values.length === 0) return null;
  return values.reduce((a, b) => a + b, 0) / values.length;
}

function ScoreCell({ value }: { value: number | null }) {
  if (value === null) return <span className="ditto-metric-na">—</span>;
  return (
    <span className="ditto-score-pill">
      <span className="ditto-score-dot" style={{ background: scoreColor(value) }} />
      {value.toFixed(2)}
    </span>
  );
}

export function ExperimentDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const [detail, setDetail] = useState<ExperimentDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pausing, setPausing] = useState(false);
  const timer = useRef<number | null>(null);

  // filters (per config dimension)
  const [fChunkings, setFChunkings] = useState<string[]>([]);
  const [fEmbeddings, setFEmbeddings] = useState<string[]>([]);
  const [fRags, setFRags] = useState<string[]>([]);
  const [fRetrievers, setFRetrievers] = useState<string[]>([]);
  const [fLlms, setFLlms] = useState<string[]>([]);

  // sorting & pagination
  const [sortKey, setSortKey] = useState<string>(MEDIA_KEY);
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [pageSize, setPageSize] = useState<string>("10");
  const [page, setPage] = useState(1);

  // modal for full pergunta/resposta
  const [modalRow, setModalRow] = useState<ExperimentResultRow | null>(null);

  // prompt snapshot modal
  const [promptTech, setPromptTech] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    let active = true;
    setLoading(true);

    const poll = () => {
      getExperiment(Number(id))
        .then((d) => {
          if (!active) return;
          setDetail(d);
          setLoading(false);
          if (d.status === "running" || d.status === "pending") {
            timer.current = window.setTimeout(poll, 3000);
          }
        })
        .catch((e) => {
          if (!active) return;
          setError(String(e));
          setLoading(false);
        });
    };
    poll();

    return () => {
      active = false;
      if (timer.current) window.clearTimeout(timer.current);
    };
  }, [id]);

  const isRunning =
    detail?.status === "running" || detail?.status === "pending";

  async function handlePause() {
    if (!id) return;
    setPausing(true);
    try {
      await pauseExperiment(Number(id));
    } catch (e) {
      setError(String(e));
      setPausing(false);
    }
  }

  const results = detail?.results ?? [];

  const promptTechniques = detail?.prompts ? Object.keys(detail.prompts) : [];

  const metricKeys = useMemo(() => {
    const keys = new Set<string>();
    results.forEach((r) => Object.keys(r.scores).forEach((k) => keys.add(k)));
    return Array.from(keys).sort();
  }, [results]);

  const distinct = (pick: (r: ExperimentResultRow) => string): string[] =>
    Array.from(new Set(results.map(pick))).sort();

  const filtered = useMemo(() => {
    return results.filter(
      (r) =>
        (fChunkings.length === 0 || fChunkings.includes(r.chunking)) &&
        (fEmbeddings.length === 0 || fEmbeddings.includes(r.embedding)) &&
        (fRags.length === 0 || fRags.includes(r.rag)) &&
        (fRetrievers.length === 0 || fRetrievers.includes(r.retriever)) &&
        (fLlms.length === 0 || fLlms.includes(r.llm)),
    );
  }, [results, fChunkings, fEmbeddings, fRags, fRetrievers, fLlms]);

  const sorted = useMemo(() => {
    const val = (r: ExperimentResultRow): number =>
      sortKey === MEDIA_KEY ? rowMedia(r) ?? -1 : r.scores[sortKey] ?? -1;
    return [...filtered].sort((a, b) =>
      sortDir === "desc" ? val(b) - val(a) : val(a) - val(b),
    );
  }, [filtered, sortKey, sortDir]);

  // reset to first page whenever the visible set changes
  useEffect(() => {
    setPage(1);
  }, [fChunkings, fEmbeddings, fRags, fRetrievers, fLlms, sortKey, sortDir, pageSize]);

  const size = Number(pageSize);
  const pageCount = Math.max(1, Math.ceil(sorted.length / size));
  const start = (page - 1) * size;
  const pageRows = sorted.slice(start, start + size);

  function toggleSort(key: string) {
    if (sortKey === key) {
      setSortDir((d) => (d === "desc" ? "asc" : "desc"));
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
  }

  function sortArrow(key: string): string {
    if (sortKey !== key) return "";
    return sortDir === "desc" ? " ▼" : " ▲";
  }

  const hasFilters =
    fChunkings.length > 0 ||
    fEmbeddings.length > 0 ||
    fRags.length > 0 ||
    fRetrievers.length > 0 ||
    fLlms.length > 0;

  return (
    <div>
      <Button
        variant="subtle"
        color="gray"
        size="xs"
        mb="md"
        onClick={() => navigate("/results")}
      >
        ← Voltar aos experimentos
      </Button>

      <PageHeader
        eyebrow="Passo 03 · Ranquear"
        title={detail?.name ?? "Carregando…"}
        subtitle="Cada linha é uma pergunta rodada numa combinação. Ordene por qualquer métrica (clique no cabeçalho), filtre pelas configurações e clique numa linha para ler pergunta e resposta."
      />

      {detail && (
        <Group gap="xs" mb="lg" align="center">
          <span className="ditto-chip" style={{ color: statusColor(detail.status) }}>
            {detail.status}
          </span>
          {isRunning && detail.progress && detail.progress.total > 0 && (
            <Text size="sm" c="dimmed">
              {detail.progress.completed}/{detail.progress.total} combinações
            </Text>
          )}
          <Text size="sm" c="dimmed">
            {results.length} resultado(s) · {metricKeys.length} métrica(s)
          </Text>
          {detail.created_at && (
            <Text size="sm" c="dimmed">
              Iniciado em {formatDate(detail.created_at)} · Duração{" "}
              {formatDuration(experimentDurationMs(detail.created_at, detail.finished_at) ?? 0)}
            </Text>
          )}
          {isRunning && (
            <>
              <Button
                size="xs"
                variant="light"
                color="yellow"
                loading={pausing}
                disabled={pausing || (detail?.pause_requested ?? false)}
                onClick={handlePause}
                ml="auto"
              >
                {pausing || detail?.pause_requested ? "Pausando…" : "Pausar"}
              </Button>
              {detail?.pause_requested && (
                <Text size="xs" c="dimmed">
                  aguardando a combinação atual terminar…
                </Text>
              )}
            </>
          )}
        </Group>
      )}

      {loading && (
        <div style={{ display: "flex", justifyContent: "center", padding: "48px 0" }}>
          <Loader size="md" color="#05dbf2" />
        </div>
      )}

      {error && (
        <Alert color="red" variant="light" title="Erro ao carregar" radius="lg" maw={760}>
          {error}
        </Alert>
      )}

      {detail && !loading && results.length === 0 && (
        <Alert
          color={detail.status === "failed" ? "red" : "gray"}
          variant="light"
          title={
            detail.status === "failed"
              ? "Experimento falhou"
              : detail.status === "paused"
              ? "Experimento pausado"
              : "Sem resultados"
          }
          radius="lg"
          maw={760}
        >
          {detail.status === "failed"
            ? detail.error ?? "Falhou sem registrar resultados."
            : detail.status === "done"
            ? "Nenhum resultado para este experimento."
            : detail.status === "paused"
            ? "Pausado antes de gerar resultados."
            : "Experimento em andamento…"}
        </Alert>
      )}

      {detail && !loading && results.length > 0 && (
        <>
          {/* Prompt snapshot buttons */}
          {detail.prompts && promptTechniques.length > 0 ? (
            <div className="ditto-prompt-bar">
              <span className="ditto-eyebrow">Prompts</span>
              {promptTechniques.map((tech) => (
                <Button
                  key={tech}
                  size="xs"
                  variant="light"
                  color="violet"
                  onClick={() => setPromptTech(tech)}
                >
                  Prompts: {tech}
                </Button>
              ))}
            </div>
          ) : (
            <Text size="xs" c="dimmed" mb="sm">
              Prompts não registrados para este experimento.
            </Text>
          )}

          {/* Filters */}
          <div className="ditto-filter-bar">
            <MultiSelect
              label="Cortes"
              placeholder="Todos"
              data={distinct((r) => r.chunking)}
              value={fChunkings}
              onChange={setFChunkings}
              clearable
              size="xs"
            />
            <MultiSelect
              label="Embeddings"
              placeholder="Todos"
              data={distinct((r) => r.embedding)}
              value={fEmbeddings}
              onChange={setFEmbeddings}
              clearable
              size="xs"
            />
            <MultiSelect
              label="RAGs"
              placeholder="Todos"
              data={distinct((r) => r.rag)}
              value={fRags}
              onChange={setFRags}
              clearable
              size="xs"
            />
            <MultiSelect
              label="Retrievers"
              placeholder="Todos"
              data={distinct((r) => r.retriever)}
              value={fRetrievers}
              onChange={setFRetrievers}
              clearable
              size="xs"
            />
            <MultiSelect
              label="LLMs"
              placeholder="Todos"
              data={distinct((r) => r.llm)}
              value={fLlms}
              onChange={setFLlms}
              clearable
              size="xs"
            />
            {hasFilters && (
              <Button
                variant="subtle"
                color="gray"
                size="xs"
                className="ditto-filter-clear"
                onClick={() => {
                  setFChunkings([]);
                  setFEmbeddings([]);
                  setFRags([]);
                  setFRetrievers([]);
                  setFLlms([]);
                }}
              >
                Limpar filtros
              </Button>
            )}
          </div>

          <Text size="xs" c="dimmed" mb={8}>
            Mostrando {sorted.length === 0 ? 0 : start + 1}–
            {Math.min(start + size, sorted.length)} de {sorted.length}
          </Text>

          <div className="ditto-table-wrap">
            <table>
              <thead>
                <tr>
                  <th className="ditto-th-combo">Combinação</th>
                  <th className="ditto-th-text">Pergunta</th>
                  <th className="ditto-th-text">Resposta</th>
                  {metricKeys.map((key) => (
                    <th
                      key={key}
                      className="ditto-th-sortable ditto-th-metric"
                      data-active={sortKey === key}
                      onClick={() => toggleSort(key)}
                      title={`Ordenar por ${key}`}
                    >
                      {key}
                      {sortArrow(key)}
                    </th>
                  ))}
                  <th
                    className="ditto-th-sortable ditto-th-metric"
                    data-active={sortKey === MEDIA_KEY}
                    onClick={() => toggleSort(MEDIA_KEY)}
                    title="Ordenar pela média"
                  >
                    Média{sortArrow(MEDIA_KEY)}
                  </th>
                </tr>
              </thead>
              <tbody>
                {pageRows.length === 0 && (
                  <tr>
                    <td colSpan={4 + metricKeys.length} className="ditto-empty">
                      Nenhum resultado com os filtros atuais.
                    </td>
                  </tr>
                )}
                {pageRows.map((row, index) => {
                  const media = rowMedia(row);
                  return (
                    <tr
                      key={start + index}
                      className="ditto-row"
                      onClick={() => setModalRow(row)}
                    >
                      <td>
                        <div className="ditto-combo">
                          <span>{row.chunking}</span>
                          <span>{row.embedding}</span>
                          <span>{row.rag}</span>
                          <span>{row.retriever}</span>
                          <span>{row.llm}</span>
                        </div>
                      </td>
                      <td className="ditto-cell-clip">
                        <div className="ditto-clip-box" title={row.question}>
                          {row.question}
                        </div>
                      </td>
                      <td className="ditto-cell-clip">
                        <div className="ditto-clip-box" title={row.answer}>
                          {row.answer}
                        </div>
                      </td>
                      {metricKeys.map((mk) => (
                        <td key={mk} className="ditto-td-metric">
                          <ScoreCell value={mk in row.scores ? row.scores[mk] : null} />
                        </td>
                      ))}
                      <td className="ditto-td-metric ditto-media-cell">
                        <ScoreCell value={media} />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <div className="ditto-table-foot">
            <Group gap="xs" align="center">
              <Text size="xs" c="dimmed">
                Por página
              </Text>
              <Select
                data={PAGE_SIZES}
                value={pageSize}
                onChange={(v) => setPageSize(v ?? "10")}
                size="xs"
                w={80}
                allowDeselect={false}
              />
            </Group>
            <Pagination
              total={pageCount}
              value={page}
              onChange={setPage}
              size="sm"
              color="violet"
            />
          </div>
        </>
      )}

      <Modal
        opened={promptTech !== null}
        onClose={() => setPromptTech(null)}
        title="Prompts usados neste experimento"
        size="lg"
        centered
        overlayProps={{ backgroundOpacity: 0.6, blur: 3 }}
      >
        {promptTech && detail?.prompts?.[promptTech] && (
          <div>
            <Text className="ditto-eyebrow" mb={10}>
              {promptTech}
            </Text>
            {Object.entries(detail.prompts[promptTech]).map(([key, text]) => (
              <div key={key} style={{ marginBottom: 18 }}>
                <Text fw={700} size="sm" mb={4}>
                  {key}
                </Text>
                <pre className="ditto-prompt-pre">{text}</pre>
              </div>
            ))}
          </div>
        )}
      </Modal>

      <Modal
        opened={modalRow !== null}
        onClose={() => setModalRow(null)}
        title="Detalhe do resultado"
        size="lg"
        centered
        overlayProps={{ backgroundOpacity: 0.6, blur: 3 }}
      >
        {modalRow && (
          <div>
            <div className="ditto-combo" style={{ marginBottom: 18 }}>
              <span>{modalRow.chunking}</span>
              <span>{modalRow.embedding}</span>
              <span>{modalRow.rag}</span>
              <span>{modalRow.retriever}</span>
              <span>{modalRow.llm}</span>
            </div>

            <Text className="ditto-eyebrow" mb={6}>
              Pergunta
            </Text>
            <Text mb="lg" style={{ lineHeight: 1.6 }}>
              {modalRow.question}
            </Text>

            <Text className="ditto-eyebrow" mb={6}>
              Resposta
            </Text>
            <Text mb="lg" style={{ lineHeight: 1.6 }}>
              {modalRow.answer}
            </Text>

            <Text className="ditto-eyebrow" mb={8}>
              Métricas
            </Text>
            {metricKeys.map((mk) =>
              mk in modalRow.scores ? (
                <div key={mk} className="ditto-score-bar-row">
                  <span className="ditto-score-bar-label">{mk}</span>
                  <span className="ditto-score-bar-track">
                    <span
                      className="ditto-score-bar-fill"
                      style={{
                        width: `${Math.max(0, Math.min(1, modalRow.scores[mk])) * 100}%`,
                        background: scoreColor(modalRow.scores[mk]),
                        boxShadow: `0 0 12px ${scoreColor(modalRow.scores[mk])}`,
                      }}
                    />
                  </span>
                  <span className="ditto-score-bar-val">
                    {modalRow.scores[mk].toFixed(2)}
                  </span>
                </div>
              ) : null,
            )}
            {rowMedia(modalRow) !== null && (
              <div className="ditto-score-bar-row" style={{ marginTop: 10 }}>
                <span className="ditto-score-bar-label" style={{ fontWeight: 700 }}>
                  Média
                </span>
                <span className="ditto-score-bar-track">
                  <span
                    className="ditto-score-bar-fill"
                    style={{
                      width: `${Math.max(0, Math.min(1, rowMedia(modalRow) ?? 0)) * 100}%`,
                      background: scoreColor(rowMedia(modalRow) ?? 0),
                      boxShadow: `0 0 12px ${scoreColor(rowMedia(modalRow) ?? 0)}`,
                    }}
                  />
                </span>
                <span className="ditto-score-bar-val" style={{ fontWeight: 700 }}>
                  {(rowMedia(modalRow) ?? 0).toFixed(2)}
                </span>
              </div>
            )}

            <div className="ditto-meta-chips">
              <span className="ditto-chip" style={{ color: "#05dbf2" }}>
                {modalRow.latency_ms} ms
              </span>
              <span className="ditto-chip" style={{ color: "#f2ec91" }}>
                {modalRow.tokens} tokens
              </span>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}
