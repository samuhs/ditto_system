import { Button } from "@mantine/core";

import type { GraphBuildJob, IndexBuild } from "../api/types";
import { term } from "../glossary";
import { StatusTag } from "./StatusTag";

function indexState(index: IndexBuild): string {
  switch (index.status) {
    case "building":
      return index.total > 0
        ? `Construindo Grafo: ${index.extracted} / ${index.total} trechos`
        : "Construindo Grafo: lendo os trechos";
    case "done":
      return index.stats
        ? `Pronto: ${index.stats.entities} entidades, ${index.stats.relations} relações`
        : "Pronto";
    case "failed":
      return `Falhou: ${index.error ?? "erro desconhecido"}`;
    default:
      return index.extracted > 0
        ? `Aguardando: ${index.extracted} / ${index.total} trechos já extraídos`
        : "Aguardando";
  }
}

interface GraphBuildListProps {
  jobs: GraphBuildJob[];
  /** Omitted: the list is read-only. */
  onPause?: (job: GraphBuildJob) => void;
  onResume?: (job: GraphBuildJob) => void;
}

/** Grafo de conhecimento builds: per Índice, chunks extracted / total; pause and resume. */
export function GraphBuildList({ jobs, onPause, onResume }: GraphBuildListProps) {
  return (
    <ul className="ditto-graph-builds" aria-label="Construções de Grafo de conhecimento">
      {jobs.map((job) => {
        const active = job.status === "pending" || job.status === "running";
        return (
          <li key={job.id} className="ditto-graph-build">
            <div className="ditto-graph-build-head">
              <StatusTag status={job.status} />
              <span>
                Grafo de conhecimento da base <strong>{job.base}</strong> · LLM extrator{" "}
                <span className="ditto-mono">{job.extractor}</span>
              </span>
              {onPause && active && (
                <Button size="xs" variant="default" disabled={job.pause_requested} onClick={() => onPause(job)}>
                  {job.pause_requested ? "Pausando…" : "Pausar"}
                </Button>
              )}
              {onResume && (job.status === "paused" || job.status === "failed") && (
                <Button size="xs" variant="default" onClick={() => onResume(job)}>
                  Retomar
                </Button>
              )}
            </div>
            <ul className="ditto-graph-build-indexes">
              {job.indexes.map((index) => (
                <li key={`${index.chunking}__${index.embedding}`}>
                  {term("chunking", index.chunking).name} · {term("embedding", index.embedding).name}:{" "}
                  <span>{indexState(index)}</span>
                </li>
              ))}
            </ul>
          </li>
        );
      })}
    </ul>
  );
}
