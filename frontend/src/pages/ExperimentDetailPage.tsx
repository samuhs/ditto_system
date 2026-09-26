import { Button, Drawer, Loader, MultiSelect, Pagination, Select, Tabs } from "@mantine/core";
import { useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "react-router-dom";

import { exportExperimentUrl, getExperiment, pauseExperiment } from "../api/client";
import type { ExperimentDetail, ExperimentResultRow } from "../api/types";
import { Errata, Note, errorText } from "../components/Notice";
import { PageHeader } from "../components/PageHeader";
import { type Combination, ScoreCell, Traits } from "../components/Score";
import { DifficultyPanel } from "../components/DifficultyPanel";
import { StatusTag } from "../components/StatusTag";
import { DownloadIcon, PauseIcon, SortIcon } from "../components/icons";
import { techniqueName, term } from "../glossary";
import { formatDateTime, formatDuration } from "../utils/duration";

const MEDIA_KEY = "__media__";
const PAGE_SIZES = ["10", "25", "50", "100"];

type Dim = keyof Combination;
const DIMS: Dim[] = ["chunking", "embedding", "rag", "retriever", "llm"];

function experimentDurationMs(createdAt?: string, finishedAt?: string): number | null {
  if (!createdAt) return null;
  const start = new Date(createdAt).getTime();
  const end = finishedAt ? new Date(finishedAt).getTime() : Date.now();
  return end - start;
}

function mean(values: number[]): number | null {
  if (values.length === 0) return null;
  return values.reduce((a, b) => a + b, 0) / values.length;
}

function rowMedia(row: ExperimentResultRow): number | null {
  return mean(Object.values(row.scores));
}

function comboKey(c: Combination): string {
  return DIMS.map((d) => c[d]).join("|");
}

function dimName(dim: Dim, key: string): string {
  return dim === "llm" ? key : term(dim, key).name;
}

interface RankRow {
  key: string;
  combo: Combination;
  count: number;
  scores: Record<string, number | null>;
  media: number | null;
}

function rankCombinations(results: ExperimentResultRow[], metricKeys: string[]): RankRow[] {
  const groups = new Map<string, ExperimentResultRow[]>();
  for (const r of results) {
    const k = comboKey(r);
    groups.set(k, [...(groups.get(k) ?? []), r]);
  }
  return [...groups.entries()].map(([key, rows]) => {
    const scores: Record<string, number | null> = {};
    for (const m of metricKeys) {
      scores[m] = mean(rows.filter((r) => m in r.scores).map((r) => r.scores[m]));
    }
    return {
      key,
      combo: rows[0],
      count: rows.length,
      scores,
      media: mean(rows.map(rowMedia).filter((v): v is number => v !== null)),
    };
  });
}

export function ExperimentDetailPage() {
  const { id } = useParams<{ id: string }>();

  const [detail, setDetail] = useState<ExperimentDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pausing, setPausing] = useState(false);
  const timer = useRef<number | null>(null);

  const [tab, setTab] = useState<string>("ranking");
  const [filters, setFilters] = useState<Record<Dim, string[]>>({
    chunking: [], embedding: [], rag: [], retriever: [], llm: [],
  });
  const [sortKey, setSortKey] = useState<string>(MEDIA_KEY);
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [pageSize, setPageSize] = useState<string>("10");
  const [page, setPage] = useState(1);
  const [openRow, setOpenRow] = useState<ExperimentResultRow | null>(null);
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
          setError(errorText(e));
          setLoading(false);
        });
    };
    poll();

    return () => {
      active = false;
      if (timer.current) window.clearTimeout(timer.current);
    };
  }, [id]);

  const isRunning = detail?.status === "running" || detail?.status === "pending";

  async function handlePause() {
    if (!id) return;
    setPausing(true);
    try {
      await pauseExperiment(Number(id));
    } catch (e) {
      setError(errorText(e));
      setPausing(false);
    }
  }

  const results = useMemo(() => detail?.results ?? [], [detail]);
  const promptTechniques = detail?.prompts ? Object.keys(detail.prompts) : [];

  const metricKeys = useMemo(() => {
    const keys = new Set<string>();
    results.forEach((r) => Object.keys(r.scores).forEach((k) => keys.add(k)));
    return Array.from(keys).sort();
  }, [results]);

  const distinct = (dim: Dim) =>
    Array.from(new Set(results.map((r) => r[dim])))
      .sort()
      .map((v) => ({ value: v, label: dimName(dim, v) }));

  // ---- ranking (one row per combination)
  const ranking = useMemo(() => rankCombinations(results, metricKeys), [results, metricKeys]);
  const rankingByMedia = useMemo(
    () => [...ranking].sort((a, b) => (b.media ?? -1) - (a.media ?? -1)),
    [ranking],
  );
  const winner = rankingByMedia[0];

  const sortedRanking = useMemo(() => {
    const val = (r: RankRow) => (sortKey === MEDIA_KEY ? r.media : r.scores[sortKey]) ?? -1;
    return [...ranking].sort((a, b) => (sortDir === "desc" ? val(b) - val(a) : val(a) - val(b)));
  }, [ranking, sortKey, sortDir]);

  const bestOf = useMemo(() => {
    const best: Record<string, number> = {};
    for (const k of [...metricKeys, MEDIA_KEY]) {
      const values = ranking
        .map((r) => (k === MEDIA_KEY ? r.media : r.scores[k]))
        .filter((v): v is number => v !== null);
      if (values.length > 0) best[k] = Math.max(...values);
    }
    return best;
  }, [ranking, metricKeys]);

  // ---- answers (one row per question × combination)
  const filtered = useMemo(
    () => results.filter((r) => DIMS.every((d) => filters[d].length === 0 || filters[d].includes(r[d]))),
    [results, filters],
  );

  const sorted = useMemo(() => {
    const val = (r: ExperimentResultRow): number =>
      sortKey === MEDIA_KEY ? rowMedia(r) ?? -1 : r.scores[sortKey] ?? -1;
    return [...filtered].sort((a, b) => (sortDir === "desc" ? val(b) - val(a) : val(a) - val(b)));
  }, [filtered, sortKey, sortDir]);

  useEffect(() => {
    setPage(1);
  }, [filters, sortKey, sortDir, pageSize]);

  const size = Number(pageSize);
  const pageCount = Math.max(1, Math.ceil(sorted.length / size));
  const start = (page - 1) * size;
  const pageRows = sorted.slice(start, start + size);
  const hasFilters = DIMS.some((d) => filters[d].length > 0);

  function toggleSort(key: string) {
    if (sortKey === key) setSortDir((d) => (d === "desc" ? "asc" : "desc"));
    else {
      setSortKey(key);
      setSortDir("desc");
    }
  }

  function showAnswersOf(combo: Combination) {
    setFilters({
      chunking: [combo.chunking],
      embedding: [combo.embedding],
      rag: [combo.rag],
      retriever: [combo.retriever],
      llm: [combo.llm],
    });
    setTab("answers");
  }

  function SortHeader({ k, label, code }: { k: string; label: string; code?: string }) {
    const active = sortKey === k;
    return (
      <th
        className="ditto-num"
        aria-sort={active ? (sortDir === "desc" ? "descending" : "ascending") : "none"}
      >
        <button
          type="button"
          className="ditto-sort"
          data-active={active}
          onClick={() => toggleSort(k)}
          title={`Ordenar por ${label}`}
        >
          <span>
            {label}
            {code && <span className="ditto-mono">{code}</span>}
          </span>
          <SortIcon dir={active ? sortDir : null} />
        </button>
      </th>
    );
  }

  const metricHeaders = (
    <>
      {metricKeys.map((k) => (
        <SortHeader key={k} k={k} label={term("metric", k).name} code={k} />
      ))}
      <SortHeader k={MEDIA_KEY} label="Média" />
    </>
  );

  const legend = (
    <dl className="ditto-legend">
      {metricKeys.map((k) => {
        const t = term("metric", k);
        return (
          <div key={k}>
            <dt>{t.name}</dt>
            <dd>{t.description ?? k}</dd>
          </div>
        );
      })}
      <div>
        <dt>Média</dt>
        <dd>Média simples das métricas. De 0 a 1; maior é melhor.</dd>
      </div>
    </dl>
  );

  const duration = detail?.created_at
    ? formatDuration(experimentDurationMs(detail.created_at, detail.finished_at) ?? 0)
    : null;

  return (
    <div>
      <PageHeader
        back={{ to: "/results", label: "Voltar aos experimentos" }}
        title={detail?.name ?? "Carregando…"}
        lede="Qual combinação respondeu melhor às suas perguntas, e o que ela respondeu em cada uma."
      />

      {detail && (
        <div className="ditto-meta">
          <StatusTag status={detail.status} />
          {isRunning && detail.progress?.phase === "evaluating" && <span>Avaliando as respostas</span>}
          {isRunning && detail.progress && detail.progress.total > 0 && detail.progress.phase !== "evaluating" && (
            <span>
              {detail.progress.completed} de {detail.progress.total} combinações
            </span>
          )}
          {detail.created_at && (
            <span>
              Iniciado em {formatDateTime(detail.created_at)} · Duração {duration}
            </span>
          )}
          <span>
            {results.length} {results.length === 1 ? "resposta" : "respostas"} · {metricKeys.length}{" "}
            {metricKeys.length === 1 ? "métrica" : "métricas"}
          </span>
          {detail.eval_embedding && <span>Avaliado com {term("embedding", detail.eval_embedding).name}</span>}
          <span className="ditto-meta-actions">
            {isRunning && (
              <>
                {detail.pause_requested && <span>aguardando a combinação atual terminar…</span>}
                <Button
                  size="sm"
                  variant="default"
                  leftSection={<PauseIcon />}
                  loading={pausing && !detail.pause_requested}
                  disabled={pausing || (detail.pause_requested ?? false)}
                  onClick={handlePause}
                >
                  {pausing || detail.pause_requested ? "Pausando…" : "Pausar"}
                </Button>
              </>
            )}
            <Button
              component="a"
              href={exportExperimentUrl(detail.id)}
              download
              size="sm"
              variant="default"
              leftSection={<DownloadIcon />}
            >
              Exportar CSV
            </Button>
          </span>
        </div>
      )}

      {loading && <Loader aria-label="Carregando experimento" />}

      {error && (
        <Errata title="Não foi possível carregar este experimento">
          {error}. Volte à lista e tente abrir de novo.
        </Errata>
      )}

      {detail && !loading && results.length === 0 &&
        (detail.status === "failed" ? (
          <Errata title="O experimento falhou">
            {detail.error ?? "Ele parou sem registrar resultados."} Corrija a causa e crie um novo
            experimento.
          </Errata>
        ) : (
          <Note
            title={
              detail.status === "paused"
                ? "Experimento pausado"
                : detail.status === "done"
                  ? "Sem resultados"
                  : "Experimento em andamento"
            }
          >
            {detail.status === "paused"
              ? "Ele foi pausado antes de gerar resultados."
              : detail.status === "done"
                ? "Nenhum resultado foi registrado para este experimento."
                : "As primeiras respostas aparecem aqui assim que ficarem prontas. A página se atualiza sozinha."}
          </Note>
        ))}

      {detail && !loading && results.length > 0 && (
        <>
          {winner && (
            <section className="ditto-winner" aria-label="Melhor combinação">
              <span className="ditto-winner-badge" aria-hidden>
                1
              </span>
              <div>
                <h2 className="ditto-winner-title">
                  Melhor combinação{isRunning ? " até agora" : ""}
                </h2>
                <Traits combo={winner.combo} />
                <div className="ditto-winner-metrics">
                  <span>
                    Média <b>{winner.media?.toFixed(2) ?? "—"}</b>
                  </span>
                  {metricKeys.map((k) => (
                    <span key={k}>
                      {term("metric", k).name} <b>{winner.scores[k]?.toFixed(2) ?? "—"}</b>
                    </span>
                  ))}
                  <span className="ditto-muted">
                    sobre {winner.count} {winner.count === 1 ? "pergunta" : "perguntas"}, entre{" "}
                    {ranking.length} {ranking.length === 1 ? "combinação" : "combinações"}
                  </span>
                </div>
              </div>
            </section>
          )}

          <Tabs value={tab} onChange={(v) => setTab(v ?? "ranking")} keepMounted={false}>
            <Tabs.List mb="md">
              <Tabs.Tab value="ranking">Ranking das combinações</Tabs.Tab>
              <Tabs.Tab value="answers">Respostas por pergunta</Tabs.Tab>
              <Tabs.Tab value="difficulty">Dificuldade por pergunta</Tabs.Tab>
              <Tabs.Tab value="prompts">Prompts usados</Tabs.Tab>
            </Tabs.List>

            <Tabs.Panel value="ranking">
              <p className="ditto-caption">
                <strong>Tabela 1.</strong> Média de cada métrica por combinação, sobre todas as
                perguntas. Clique numa linha para ver as respostas dela.
              </p>
              <div className="ditto-table-wrap">
                <table className="ditto-table" data-stack="true">
                  <thead>
                    <tr>
                      <th className="ditto-num">#</th>
                      <th>Combinação</th>
                      <th className="ditto-num">Perguntas</th>
                      {metricHeaders}
                    </tr>
                  </thead>
                  <tbody>
                    {sortedRanking.map((r) => {
                      const place = rankingByMedia.indexOf(r) + 1;
                      return (
                        <tr
                          key={r.key}
                          data-clickable="true"
                          data-best={place === 1 || undefined}
                          onClick={() => showAnswersOf(r.combo)}
                        >
                          <td className="ditto-num ditto-cell-rank">
                            <span className="ditto-rank">{place}</span>
                          </td>
                          <td className="ditto-cell-combo">
                            <button
                              type="button"
                              className="ditto-sort"
                              style={{ textAlign: "left" }}
                              onClick={(e) => {
                                e.stopPropagation();
                                showAnswersOf(r.combo);
                              }}
                              aria-label={`Ver respostas da combinação ${place}`}
                            >
                              <Traits combo={r.combo} />
                            </button>
                          </td>
                          <td className="ditto-num ditto-cell-count" data-label="Perguntas">{r.count}</td>
                          {metricKeys.map((k) => (
                            <td key={k} className="ditto-num" data-label={term("metric", k).name}>
                              <ScoreCell value={r.scores[k]} best={r.scores[k] === bestOf[k]} />
                            </td>
                          ))}
                          <td className="ditto-num ditto-cell-media" data-label="Média">
                            <ScoreCell value={r.media} best={r.media === bestOf[MEDIA_KEY]} />
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              {legend}
            </Tabs.Panel>

            <Tabs.Panel value="answers">
              <div className="ditto-filters">
                <MultiSelect label="Corte" placeholder="Todos" data={distinct("chunking")} value={filters.chunking} onChange={(v) => setFilters((f) => ({ ...f, chunking: v }))} clearable size="sm" />
                <MultiSelect label="Embedding" placeholder="Todos" data={distinct("embedding")} value={filters.embedding} onChange={(v) => setFilters((f) => ({ ...f, embedding: v }))} clearable size="sm" />
                <MultiSelect label="Técnica de RAG" placeholder="Todas" data={distinct("rag")} value={filters.rag} onChange={(v) => setFilters((f) => ({ ...f, rag: v }))} clearable size="sm" />
                <MultiSelect label="Busca (retrievers)" placeholder="Todas" data={distinct("retriever")} value={filters.retriever} onChange={(v) => setFilters((f) => ({ ...f, retriever: v }))} clearable size="sm" />
                <MultiSelect label="Modelo (LLMs)" placeholder="Todos" data={distinct("llm")} value={filters.llm} onChange={(v) => setFilters((f) => ({ ...f, llm: v }))} clearable size="sm" />
                {hasFilters && (
                  <Button
                    variant="subtle"
                    size="sm"
                    onClick={() => setFilters({ chunking: [], embedding: [], rag: [], retriever: [], llm: [] })}
                  >
                    Limpar filtros
                  </Button>
                )}
              </div>

              <p className="ditto-caption">
                Mostrando {sorted.length === 0 ? 0 : start + 1}–{Math.min(start + size, sorted.length)} de{" "}
                {sorted.length}. Clique numa linha para ler a pergunta e a resposta completas.
              </p>

              <div className="ditto-table-wrap">
                <table className="ditto-table" data-stack="true">
                  <thead>
                    <tr>
                      <th>Combinação</th>
                      <th>Pergunta</th>
                      <th>Resposta</th>
                      {metricHeaders}
                    </tr>
                  </thead>
                  <tbody>
                    {pageRows.length === 0 && (
                      <tr>
                        <td colSpan={4 + metricKeys.length} className="ditto-muted">
                          Nenhuma resposta com esses filtros.
                        </td>
                      </tr>
                    )}
                    {pageRows.map((row, index) => (
                      <tr key={start + index} data-clickable="true" onClick={() => setOpenRow(row)}>
                        <td className="ditto-cell-combo">
                          <Traits combo={row} />
                        </td>
                        <td className="ditto-cell-text" data-label="Pergunta">
                          <button
                            type="button"
                            className="ditto-sort ditto-clip"
                            style={{ textAlign: "left" }}
                            onClick={(e) => {
                              e.stopPropagation();
                              setOpenRow(row);
                            }}
                          >
                            {row.question}
                          </button>
                        </td>
                        <td className="ditto-cell-text" data-label="Resposta">
                          <span className="ditto-clip ditto-muted">{row.answer}</span>
                        </td>
                        {metricKeys.map((k) => (
                          <td key={k} className="ditto-num" data-label={term("metric", k).name}>
                            <ScoreCell value={k in row.scores ? row.scores[k] : null} />
                          </td>
                        ))}
                        <td className="ditto-num ditto-cell-media" data-label="Média">
                          <ScoreCell value={rowMedia(row)} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="ditto-table-foot">
                <Select
                  label="Por página"
                  data={PAGE_SIZES}
                  value={pageSize}
                  onChange={(v) => setPageSize(v ?? "10")}
                  size="sm"
                  w={110}
                  allowDeselect={false}
                />
                <Pagination total={pageCount} value={page} onChange={setPage} size="sm" />
              </div>
              {legend}
            </Tabs.Panel>

            <Tabs.Panel value="difficulty">
              <DifficultyPanel experimentId={detail.id} />
            </Tabs.Panel>

            <Tabs.Panel value="prompts">
              {promptTechniques.length > 0 ? (
                <>
                  <p className="ditto-caption">
                    O texto exato dos prompts no momento em que este experimento rodou. Editar os
                    prompts depois não altera este registro.
                  </p>
                  <div className="ditto-row-actions">
                    {promptTechniques.map((tech) => (
                      <Button key={tech} variant="default" size="sm" onClick={() => setPromptTech(tech)}>
                        Prompts: {tech}
                      </Button>
                    ))}
                  </div>
                </>
              ) : (
                <Note title="Prompts não registrados para este experimento">
                  Experimentos antigos rodaram antes do registro de prompts existir.
                </Note>
              )}
            </Tabs.Panel>
          </Tabs>
        </>
      )}

      <Drawer
        opened={promptTech !== null}
        onClose={() => setPromptTech(null)}
        title={promptTech ? `Prompts de ${techniqueName(promptTech)}` : "Prompts"}
      >
        {promptTech &&
          detail?.prompts?.[promptTech] &&
          Object.entries(detail.prompts[promptTech]).map(([key, text]) => (
            <div key={key} style={{ marginBottom: 20 }}>
              <h3 className="ditto-h3" style={{ marginBottom: 6 }}>
                <span className="ditto-mono">{key}</span>
              </h3>
              <pre className="ditto-prompt-pre">{text}</pre>
            </div>
          ))}
      </Drawer>

      <Drawer opened={openRow !== null} onClose={() => setOpenRow(null)} title="Detalhe do resultado">
        {openRow && (
          <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>
            <Traits combo={openRow} />
            <div>
              <h3 className="ditto-h3">Pergunta</h3>
              <p className="ditto-read" style={{ color: "var(--ink)", margin: "6px 0 0" }}>
                {openRow.question}
              </p>
            </div>
            <div>
              <h3 className="ditto-h3">Resposta</h3>
              <p className="ditto-read" style={{ color: "var(--ink)", margin: "6px 0 0", whiteSpace: "pre-wrap" }}>
                {openRow.answer}
              </p>
            </div>
            <div>
              <h3 className="ditto-h3" style={{ marginBottom: 8 }}>
                Métricas
              </h3>
              <table className="ditto-table">
                <tbody>
                  {metricKeys
                    .filter((k) => k in openRow.scores)
                    .map((k) => (
                      <tr key={k}>
                        <td>
                          {term("metric", k).name}
                          <div className="ditto-muted" style={{ fontSize: 13 }}>
                            {term("metric", k).description}
                          </div>
                        </td>
                        <td className="ditto-num">
                          <ScoreCell value={openRow.scores[k]} />
                        </td>
                      </tr>
                    ))}
                  <tr>
                    <td>
                      <b>Média</b>
                    </td>
                    <td className="ditto-num">
                      <ScoreCell value={rowMedia(openRow)} best />
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
            <dl className="ditto-kv">
              <dt>Tempo de resposta</dt>
              <dd>{openRow.latency_ms} ms</dd>
              <dt>Tokens</dt>
              <dd>{openRow.tokens}</dd>
            </dl>
          </div>
        )}
      </Drawer>
    </div>
  );
}
