import { Button, Loader, Modal, Select } from "@mantine/core";
import { useCallback, useEffect, useId, useState } from "react";
import { Link } from "react-router-dom";

import {
  deleteBase,
  getOptions,
  listBases,
  pauseGraphBuild,
  resumeGraphBuild,
  startGraphBuild,
} from "../api/client";
import type { BaseSummary, GraphBuildJob, IndexPair, IndexSummary, Options } from "../api/types";
import { ChoiceGroup } from "../components/ChoiceGroup";
import { GraphBuildList, isActiveBuild } from "../components/GraphBuildList";
import { llmSelectData } from "../components/llmOptions";
import { Errata, Note, Saved, errorText } from "../components/Notice";
import { PageHeader } from "../components/PageHeader";
import { ArrowIcon } from "../components/icons";
import { term } from "../glossary";
import { joinPt } from "../utils/text";

const POLL_MS = 2000;

function indexKey(i: IndexPair): string {
  return `${i.chunking}|${i.embedding}`;
}

function hasActiveBuild(base: BaseSummary): boolean {
  return (base.graph_builds ?? []).some(isActiveBuild);
}

const count = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

const formatPct = (value: number) => `${value.toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%`;

const formatDate = (iso: string | null) => (iso ? new Date(iso).toLocaleDateString("pt-BR") : "—");

function graphCount(base: BaseSummary): number {
  return base.indexes.reduce((n, index) => n + index.graphs.length, 0);
}

/** "Regerar" once the Base has any Grafo, so it is clear one already exists. */
const graphAction = (base: BaseSummary) => (graphCount(base) > 0 ? "Regerar Grafo" : "Gerar Grafo");

/** "qwen3:1.7b (01/10/2026), gemini (—)": the Grafos an Índice already has. */
function graphList(index: IndexSummary): string {
  return index.graphs.map((g) => `${g.extractor} (${formatDate(g.built_at)})`).join(", ");
}

/** A technique's plain name with its registry key in mono beside it. */
function Named({ dimension, value }: { dimension: "chunking" | "embedding"; value: string }) {
  const name = term(dimension, value).name;
  return (
    <>
      {name}
      {name !== value && <span className="ditto-mono ditto-muted"> {value}</span>}
    </>
  );
}

function BaseSection({
  base,
  onDelete,
  onGenerate,
  onPauseBuild,
  onResumeBuild,
}: {
  base: BaseSummary;
  onDelete: () => void;
  onGenerate: () => void;
  onPauseBuild: (job: GraphBuildJob) => void;
  onResumeBuild: (job: GraphBuildJob) => void;
}) {
  // Base names are free text: never fit for an id.
  const headingId = useId();
  const graphs = base.indexes.flatMap((index) => index.graphs.map((graph) => ({ index, graph })));
  return (
    <section className="ditto-sec" aria-labelledby={headingId}>
      <div className="ditto-sec-head">
        <h2 className="ditto-h2" id={headingId}>{base.name}</h2>
        <p className="ditto-read">
          {count(base.indexes.length, "índice", "índices")} ·{" "}
          {count(graphCount(base), "Grafo de conhecimento", "Grafos de conhecimento")}
        </p>
        <div className="ditto-row-actions">
          <Button
            size="sm"
            variant="default"
            onClick={onGenerate}
            disabled={base.in_use !== null}
            title={base.in_use ?? undefined}
          >
            {graphAction(base)}
          </Button>
          <Button size="sm" variant="default" onClick={onDelete}>
            Apagar base
          </Button>
        </div>
      </div>
      <div className="ditto-sec-body">
        {base.in_use && <Note title="Em uso agora">{base.in_use}</Note>}
        {(base.graph_builds ?? []).length > 0 && (
          <GraphBuildList jobs={base.graph_builds ?? []} onPause={onPauseBuild} onResume={onResumeBuild} />
        )}
        <div className="ditto-table-wrap">
          <table className="ditto-table">
            <caption className="visually-hidden">Índices da base {base.name}</caption>
            <thead>
              <tr>
                <th>Corte</th>
                <th>Embedding</th>
                <th className="ditto-num">Trechos</th>
                <th>Grafo</th>
              </tr>
            </thead>
            <tbody>
              {base.indexes.map((index) => (
                <tr key={`${index.chunking}__${index.embedding}`}>
                  <td><Named dimension="chunking" value={index.chunking} /></td>
                  <td><Named dimension="embedding" value={index.embedding} /></td>
                  <td className="ditto-num">{index.chunks}</td>
                  <td className={index.graphs.length ? undefined : "ditto-muted"}>
                    {index.graphs.length
                      ? `Com Grafo · ${index.graphs.map((g) => g.extractor).join(", ")}`
                      : "Sem Grafo"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {graphs.length === 0 ? (
          <p className="ditto-read">
            Nenhum Grafo de conhecimento ainda. Clique em “Gerar Grafo”, acima, para criar o
            primeiro a partir dos índices desta base.
          </p>
        ) : (
          <div className="ditto-table-wrap">
            <table className="ditto-table">
              <caption className="visually-hidden">Grafos de conhecimento da base {base.name}</caption>
              <thead>
                <tr>
                  <th>Índice</th>
                  <th>LLM extrator</th>
                  <th className="ditto-num">Entidades</th>
                  <th className="ditto-num">Relações</th>
                  <th className="ditto-num">Falhas de extração</th>
                  <th className="ditto-num">Gerado em</th>
                </tr>
              </thead>
              <tbody>
                {graphs.map(({ index, graph }) => (
                  <tr key={`${index.chunking}__${index.embedding}__${graph.extractor}`}>
                    <td>
                      <Named dimension="chunking" value={index.chunking} /> ·{" "}
                      <Named dimension="embedding" value={index.embedding} />
                    </td>
                    <td className="ditto-mono">{graph.extractor}</td>
                    <td className="ditto-num">{graph.entities}</td>
                    <td className="ditto-num">{graph.relations}</td>
                    <td className="ditto-num">{formatPct(graph.failed_pct)}</td>
                    <td className="ditto-num">{formatDate(graph.built_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  );
}

export function BasesPage() {
  const [bases, setBases] = useState<BaseSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState<BaseSummary | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [deleted, setDeleted] = useState<string | null>(null);

  const [options, setOptions] = useState<Options | null>(null);
  const [optionsError, setOptionsError] = useState<string | null>(null);
  const [generating, setGenerating] = useState<BaseSummary | null>(null);
  const [extractor, setExtractor] = useState<string | null>(null);
  const [genIndexKeys, setGenIndexKeys] = useState<string[]>([]);
  const [building, setBuilding] = useState(false);
  const [buildError, setBuildError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    listBases()
      .then((list) => {
        setBases(list);
        setError(null);
      })
      .catch((e) => setError(errorText(e)));
  }, []);

  useEffect(refresh, [refresh]);

  useEffect(() => {
    getOptions().then(setOptions).catch((e) => setOptionsError(errorText(e)));
  }, []);

  // Poll while a Grafo build of any Base is still running, queued or just started.
  useEffect(() => {
    if (!bases?.some(hasActiveBuild)) return;
    const timer = window.setTimeout(refresh, POLL_MS);
    return () => window.clearTimeout(timer);
  }, [bases, refresh]);

  function askDelete(base: BaseSummary) {
    setDeleteError(null);
    setDeleted(null);
    setConfirming(base);
  }

  async function confirmDelete() {
    if (!confirming) return;
    setDeleting(true);
    setDeleteError(null);
    try {
      await deleteBase(confirming.name);
      setDeleted(confirming.name);
      setConfirming(null);
      refresh();
    } catch (e) {
      setDeleteError(errorText(e));
      // A refusal means the Base is in use: show it in the list too.
      refresh();
    } finally {
      setDeleting(false);
    }
  }

  // Picked Índices that already have a Grafo of the chosen extrator: a build keeps it
  // unless it is stale (jobs.py skips a current Grafo).
  const sameExtractor = (generating?.indexes ?? [])
    .filter((i) => genIndexKeys.includes(indexKey(i)) && i.graphs.some((g) => g.extractor === extractor))
    .map((i) => `${i.chunking} · ${i.embedding}`);

  function askGenerate(base: BaseSummary) {
    setBuildError(null);
    setExtractor(null);
    setGenIndexKeys(base.indexes.map(indexKey));
    setGenerating(base);
  }

  async function submitGenerate() {
    if (!generating || !extractor) return;
    setBuilding(true);
    setBuildError(null);
    try {
      const indexes: IndexPair[] = generating.indexes
        .filter((i) => genIndexKeys.includes(indexKey(i)))
        .map((i) => ({ chunking: i.chunking, embedding: i.embedding }));
      // Omitted when every Índice is picked, matching GraphBuildRequest's contract.
      const allPicked = indexes.length === generating.indexes.length;
      await startGraphBuild({
        base: generating.name,
        extractor,
        ...(allPicked ? {} : { indexes }),
      });
      setGenerating(null);
      refresh();
    } catch (e) {
      setBuildError(errorText(e));
    } finally {
      setBuilding(false);
    }
  }

  function pauseBuild(job: GraphBuildJob) {
    pauseGraphBuild(job.id).then(refresh).catch(() => {});
  }

  function resumeBuild(job: GraphBuildJob) {
    resumeGraphBuild(job.id).then(refresh).catch(() => {});
  }

  return (
    <div>
      <PageHeader
        title="Bases"
        lede="Cada base guarda os índices de busca (corte × embedding) gerados dos seus documentos e os Grafos de conhecimento montados a partir deles."
      />

      {error && (
        <div style={{ marginBottom: 20 }}>
          <Errata title="Não foi possível carregar as bases">{error}. Recarregue a página.</Errata>
        </div>
      )}

      {deleted && (
        <div style={{ marginBottom: 20 }}>
          <Saved>Base “{deleted}” apagada.</Saved>
        </div>
      )}

      {bases === null && !error && <Loader aria-label="Carregando bases" />}

      {bases !== null && bases.length === 0 && (
        <div className="ditto-empty">
          <h2 className="ditto-h2">Nenhuma base ainda</h2>
          <p>Envie documentos em Documentos: cada envio cria uma base com os índices que você escolher.</p>
          <Button component={Link} to="/ingest" rightSection={<ArrowIcon />}>
            Enviar documentos
          </Button>
        </div>
      )}

      {bases !== null && bases.length > 0 && (
        <div className="ditto-form">
          {bases.map((base) => (
            <BaseSection
              key={base.name}
              base={base}
              onDelete={() => askDelete(base)}
              onGenerate={() => askGenerate(base)}
              onPauseBuild={pauseBuild}
              onResumeBuild={resumeBuild}
            />
          ))}
        </div>
      )}

      <Modal
        opened={generating !== null}
        onClose={() => {
          if (!building) setGenerating(null);
        }}
        title={generating ? `${graphAction(generating)} de conhecimento em “${generating.name}”` : ""}
      >
        {generating && (
          <div style={{ display: "grid", gap: 16 }}>
            {graphCount(generating) > 0 && (
              <Note title="Esta base já tem Grafo de conhecimento">
                Gerar com outro LLM extrator cria mais um Grafo ao lado do atual. Com o mesmo
                extrator, o Grafo existente é mantido, a não ser que esteja desatualizado.
              </Note>
            )}
            {optionsError && (
              <Errata title="Não foi possível carregar os LLMs">{optionsError}</Errata>
            )}
            <Select
              label="LLM extrator"
              description="O modelo que lê os trechos e anota entidades e relações."
              placeholder="Escolha um modelo"
              data={llmSelectData(options)}
              value={extractor}
              onChange={setExtractor}
              allowDeselect={false}
              maw={420}
            />
            <ChoiceGroup
              legend="Índices"
              choices={generating.indexes.map((i) => ({
                value: indexKey(i),
                name: `${i.chunking} · ${i.embedding}`,
                description:
                  `${term("chunking", i.chunking).name} + ${term("embedding", i.embedding).name}` +
                  (i.graphs.length ? ` · já tem Grafo de ${graphList(i)}` : ""),
              }))}
              value={genIndexKeys}
              onChange={setGenIndexKeys}
              empty="Esta base não tem índices."
            />
            {sameExtractor.length > 0 && (
              <Note title={`Já existe Grafo de ${extractor} em ${joinPt(sameExtractor)}`}>
                Ele só é refeito se estiver desatualizado (mudou a versão do Grafo, o prompt de
                extração ou os trechos do índice); senão a construção o mantém como está.
              </Note>
            )}
            {buildError && <Errata title="A construção não foi iniciada">{buildError}</Errata>}
            <div className="ditto-row-actions" style={{ justifyContent: "flex-end" }}>
              <Button variant="subtle" onClick={() => setGenerating(null)} disabled={building}>
                Cancelar
              </Button>
              <Button
                onClick={submitGenerate}
                loading={building}
                disabled={!extractor || genIndexKeys.length === 0}
              >
                Construir Grafo
              </Button>
            </div>
          </div>
        )}
      </Modal>

      <Modal
        opened={confirming !== null}
        onClose={() => {
          if (!deleting) setConfirming(null);
        }}
        title={confirming ? `Apagar a base “${confirming.name}”?` : ""}
      >
        {confirming && (
          <div style={{ display: "grid", gap: 16 }}>
            <p className="ditto-read" style={{ margin: 0 }}>
              Apaga {count(confirming.indexes.length, "índice", "índices")} e{" "}
              {count(graphCount(confirming), "Grafo de conhecimento", "Grafos de conhecimento")}. Não
              dá para desfazer: para usar a base de novo, envie os documentos outra vez.
            </p>
            {deleteError && <Errata title="A base não foi apagada">{deleteError}</Errata>}
            <div className="ditto-row-actions" style={{ justifyContent: "flex-end" }}>
              <Button variant="subtle" onClick={() => setConfirming(null)} disabled={deleting}>
                Cancelar
              </Button>
              <Button className="ditto-danger" onClick={confirmDelete} loading={deleting}>
                Apagar base
              </Button>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}
