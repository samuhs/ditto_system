import { Button, Checkbox, FileInput, Select, TextInput } from "@mantine/core";
import { useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { getOptions, ingest, listGraphBuilds, pauseGraphBuild, resumeGraphBuild } from "../api/client";
import type { GraphBuildJob, Options } from "../api/types";
import { ChoiceGroup } from "../components/ChoiceGroup";
import { GraphBuildList } from "../components/GraphBuildList";
import { llmSelectData } from "../components/llmOptions";
import { Errata, Saved, errorText } from "../components/Notice";
import { PageHeader } from "../components/PageHeader";
import { ArrowIcon, UploadIcon } from "../components/icons";
import { useTasks } from "../context/TasksContext";
import { term } from "../glossary";
import { joinPt } from "../utils/text";

export function IngestPage() {
  const { addIngestTask } = useTasks();
  const [options, setOptions] = useState<Options | null>(null);
  const [searchParams] = useSearchParams();
  const [base, setBase] = useState(searchParams.get("base") ?? "");
  const [chunkings, setChunkings] = useState<string[]>([]);
  const [embeddings, setEmbeddings] = useState<string[]>([]);
  const [files, setFiles] = useState<File[]>([]);
  const [optionsError, setOptionsError] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [started, setStarted] = useState<string | null>(null);
  const [withGraph, setWithGraph] = useState(false);
  const [extractor, setExtractor] = useState<string | null>(null);
  const builds = useGraphBuilds();

  useEffect(() => {
    getOptions().then(setOptions).catch((e) => setOptionsError(errorText(e)));
  }, []);

  const allFilled =
    options !== null &&
    options.chunkings.length > 0 &&
    options.embeddings.length > 0 &&
    chunkings.length === options.chunkings.length &&
    embeddings.length === options.embeddings.length;

  function toggleAll() {
    if (allFilled) {
      setChunkings([]);
      setEmbeddings([]);
    } else {
      setChunkings(options?.chunkings ?? []);
      setEmbeddings(options?.embeddings ?? []);
    }
  }

  const baseName = base.trim();
  const existing = baseName !== "" && (options?.bases ?? []).includes(baseName);
  const indexCount = chunkings.length * embeddings.length;

  const missing = [
    baseName === "" && "o nome da base",
    files.length === 0 && "os arquivos",
    chunkings.length === 0 && "um tipo de corte",
    embeddings.length === 0 && "um embedding",
    withGraph && !extractor && "o LLM extrator",
  ].filter(Boolean) as string[];

  async function submit() {
    setSubmitError(null);
    const form = new FormData();
    form.append("base", baseName);
    form.append("chunkings", chunkings.join(","));
    form.append("embeddings", embeddings.join(","));
    files.forEach((file) => form.append("files", file));
    if (withGraph && extractor) form.append("graph_extractor", extractor);
    try {
      const result = ingest(form);
      addIngestTask(baseName || "sem nome", result);
      const r = await result;
      if (r.graph_build) builds.follow(r.graph_build);
      setStarted(baseName);
      setFiles([]);
    } catch (e) {
      setSubmitError(errorText(e));
    }
  }

  return (
    <div>
      <PageHeader
        title="Documentos"
        lede="Envie os textos que o Ditto vai estudar. Cada combinação de corte e embedding vira um índice de busca, e cada índice pode ser testado nos experimentos."
      />

      {optionsError && (
        <Errata title="Não foi possível carregar as técnicas disponíveis">
          {optionsError}. Confira se a API está no ar (make up) e recarregue a página.
        </Errata>
      )}

      <div className="ditto-form">
        <div className="ditto-row-actions" style={{ justifyContent: "flex-end", marginBottom: 12 }}>
          <Button variant="default" size="sm" disabled={options === null} onClick={toggleAll}>
            {allFilled ? "Limpar tudo" : "Preencher tudo"}
          </Button>
        </div>

        <section className="ditto-sec">
          <div className="ditto-sec-head">
            <h2 className="ditto-h2">Base</h2>
            <p className="ditto-read">
              Um nome para este conjunto de documentos. É por ele que você escolhe a base nos
              experimentos e no chat.
            </p>
          </div>
          <div className="ditto-sec-body">
            <TextInput
              label="Nome da base"
              placeholder="ex.: guia-de-viagem"
              value={base}
              onChange={(e) => setBase(e.currentTarget.value)}
              maw={420}
              description={
                existing
                  ? "Essa base já existe. Os novos índices serão adicionados a ela."
                  : undefined
              }
            />
          </div>
        </section>

        <section className="ditto-sec">
          <div className="ditto-sec-head">
            <h2 className="ditto-h2">Arquivos</h2>
            <p className="ditto-read">
              Texto simples (.txt) ou Markdown (.md). Pode enviar vários de uma vez.
            </p>
          </div>
          <div className="ditto-sec-body">
            <FileInput
              label="Documentos"
              placeholder="Escolher arquivos"
              multiple
              accept=".txt,.md"
              value={files}
              onChange={setFiles}
              leftSection={<UploadIcon />}
              maw={520}
              description={
                existing ? "Para criar novos índices numa base existente, envie os arquivos de novo." : undefined
              }
            />
          </div>
        </section>

        <section className="ditto-sec">
          <div className="ditto-sec-head">
            <h2 className="ditto-h2">Corte do texto</h2>
            <p className="ditto-read">
              Como dividir os documentos em trechos. Marque mais de um para comparar qual funciona
              melhor.
            </p>
          </div>
          <div className="ditto-sec-body">
            <ChoiceGroup
              legend="Técnicas de corte"
              choices={(options?.chunkings ?? []).map((k) => ({ value: k, code: k, ...term("chunking", k) }))}
              value={chunkings}
              onChange={setChunkings}
              empty="Carregando técnicas…"
            />
          </div>
        </section>

        <section className="ditto-sec">
          <div className="ditto-sec-head">
            <h2 className="ditto-h2">Embedding</h2>
            <p className="ditto-read">
              O modelo que transforma cada trecho em números para a busca. Os locais não precisam
              de chave de API.
            </p>
          </div>
          <div className="ditto-sec-body">
            <ChoiceGroup
              legend="Modelos de embedding"
              choices={(options?.embeddings ?? []).map((k) => ({ value: k, code: k, ...term("embedding", k) }))}
              value={embeddings}
              onChange={setEmbeddings}
              empty="Carregando modelos…"
            />
          </div>
        </section>

        <section className="ditto-sec">
          <div className="ditto-sec-head">
            <h2 className="ditto-h2">Grafo de conhecimento</h2>
            <p className="ditto-read">
              Opcional. Um LLM lê cada trecho uma vez e anota entidades e relações. As técnicas
              graph e graph_mix dos experimentos consultam esse Grafo. A construção roda em segundo
              plano depois dos índices e pode ser pausada.
            </p>
          </div>
          <div className="ditto-sec-body">
            <Checkbox
              label="Gerar Grafo de conhecimento"
              checked={withGraph}
              onChange={(e) => setWithGraph(e.currentTarget.checked)}
            />
            {withGraph && (
              <Select
                label="LLM extrator"
                description="O modelo que lê os trechos. Os locais (MLX ou Ollama) não têm custo de API."
                placeholder="Escolha um modelo"
                data={llmSelectData(options)}
                value={extractor}
                onChange={setExtractor}
                allowDeselect={false}
                maw={420}
              />
            )}
          </div>
        </section>

        {builds.shown.length > 0 && (
          <section className="ditto-sec">
            <div className="ditto-sec-head">
              <h2 className="ditto-h2">Construção do Grafo</h2>
              <p className="ditto-read">
                Ao retomar, só os trechos ainda não lidos vão para o LLM.
              </p>
            </div>
            <div className="ditto-sec-body">
              <GraphBuildList jobs={builds.shown} onPause={builds.pause} onResume={builds.resume} />
            </div>
          </section>
        )}

        {submitError && (
          <div style={{ marginBottom: 16 }}>
            <Errata title="Os documentos não foram enviados">
              {submitError}. Revise os campos e tente de novo.
            </Errata>
          </div>
        )}

        <div className="ditto-strip">
          <div className="ditto-strip-figures" aria-live="polite">
            <span className="ditto-strip-fig">
              <span className="ditto-strip-num">{chunkings.length}</span>
              <span className="ditto-strip-label">{chunkings.length === 1 ? "corte" : "cortes"}</span>
            </span>
            <span className="ditto-strip-op" aria-hidden>×</span>
            <span className="ditto-strip-fig">
              <span className="ditto-strip-num">{embeddings.length}</span>
              <span className="ditto-strip-label">{embeddings.length === 1 ? "embedding" : "embeddings"}</span>
            </span>
            <span className="ditto-strip-op" aria-hidden>=</span>
            <span className="ditto-strip-fig">
              <span className="ditto-strip-num">{indexCount}</span>
              <span className="ditto-strip-label">{indexCount === 1 ? "índice" : "índices"}</span>
            </span>
          </div>
          <Button
            className="ditto-strip-action"
            size="md"
            onClick={submit}
            disabled={missing.length > 0}
            rightSection={<ArrowIcon />}
          >
            Inserir documentos
          </Button>
          {missing.length > 0 && (
            <p className="ditto-strip-missing">Ainda falta: {joinPt(missing)}.</p>
          )}
          {started !== null && missing.length === 0 && (
            <p className="ditto-strip-missing">
              <Saved>Preparação de “{started}” iniciada.</Saved> Ela continua em segundo plano;
              quando terminar, <Link to="/experiment">crie um experimento</Link>.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}


const POLL_MS = 2000;

const isActive = (job: GraphBuildJob) => job.status === "pending" || job.status === "running";

/**
 * The Grafo builds to show: those running, queued or paused, and any this page
 * started; polled while one is active.
 */
function useGraphBuilds() {
  const [jobs, setJobs] = useState<GraphBuildJob[]>([]);
  const [mine, setMine] = useState<number[]>([]);

  const refresh = useCallback(() => {
    Promise.resolve()
      .then(() => listGraphBuilds())
      .then((list) => list && setJobs(list))
      .catch(() => {});
  }, []);

  useEffect(refresh, [refresh]);

  useEffect(() => {
    if (!jobs.some(isActive)) return;
    const timer = window.setTimeout(refresh, POLL_MS);
    return () => window.clearTimeout(timer);
  }, [jobs, refresh]);

  return {
    shown: jobs.filter((j) => isActive(j) || j.status === "paused" || mine.includes(j.id)),
    follow(job: GraphBuildJob) {
      setMine((ids) => [...ids, job.id]);
      setJobs((list) => [job, ...list.filter((j) => j.id !== job.id)]);
      refresh();
    },
    pause(job: GraphBuildJob) {
      pauseGraphBuild(job.id).then(refresh).catch(() => {});
    },
    resume(job: GraphBuildJob) {
      resumeGraphBuild(job.id).then(refresh).catch(() => {});
    },
  };
}
