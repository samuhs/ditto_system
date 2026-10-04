import { Button, Loader, Modal } from "@mantine/core";
import { useEffect, useId, useState } from "react";
import { Link } from "react-router-dom";

import { deleteBase, listBases } from "../api/client";
import type { BaseSummary } from "../api/types";
import { Errata, Note, Saved, errorText } from "../components/Notice";
import { PageHeader } from "../components/PageHeader";
import { ArrowIcon } from "../components/icons";
import { term } from "../glossary";

const count = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

const formatPct = (value: number) => `${value.toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%`;

const formatDate = (iso: string | null) => (iso ? new Date(iso).toLocaleDateString("pt-BR") : "—");

function graphCount(base: BaseSummary): number {
  return base.indexes.reduce((n, index) => n + index.graphs.length, 0);
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

function BaseSection({ base, onDelete }: { base: BaseSummary; onDelete: () => void }) {
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
        <Button size="sm" variant="default" onClick={onDelete}>
          Apagar base
        </Button>
      </div>
      <div className="ditto-sec-body">
        {base.in_use && <Note title="Em uso agora">{base.in_use}</Note>}
        <div className="ditto-table-wrap">
          <table className="ditto-table">
            <caption className="visually-hidden">Índices da base {base.name}</caption>
            <thead>
              <tr>
                <th>Corte</th>
                <th>Embedding</th>
                <th className="ditto-num">Trechos</th>
              </tr>
            </thead>
            <tbody>
              {base.indexes.map((index) => (
                <tr key={`${index.chunking}__${index.embedding}`}>
                  <td><Named dimension="chunking" value={index.chunking} /></td>
                  <td><Named dimension="embedding" value={index.embedding} /></td>
                  <td className="ditto-num">{index.chunks}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {graphs.length === 0 ? (
          <p className="ditto-read">
            Nenhum Grafo de conhecimento ainda. Ele é montado na primeira vez que um experimento usa
            a técnica Grafo num índice desta base.
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

  function refresh() {
    listBases()
      .then((list) => {
        setBases(list);
        setError(null);
      })
      .catch((e) => setError(errorText(e)));
  }

  useEffect(refresh, []);

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
            <BaseSection key={base.name} base={base} onDelete={() => askDelete(base)} />
          ))}
        </div>
      )}

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
