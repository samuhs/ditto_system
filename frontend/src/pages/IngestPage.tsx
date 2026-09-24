import { Button, FileInput, TextInput } from "@mantine/core";
import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { getOptions, ingest } from "../api/client";
import type { Options } from "../api/types";
import { ChoiceGroup } from "../components/ChoiceGroup";
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
  const [started, setStarted] = useState<string | null>(null);

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
  ].filter(Boolean) as string[];

  function submit() {
    const form = new FormData();
    form.append("base", baseName);
    form.append("chunkings", chunkings.join(","));
    form.append("embeddings", embeddings.join(","));
    files.forEach((file) => form.append("files", file));
    addIngestTask(baseName || "sem nome", ingest(form));
    setStarted(baseName);
    setFiles([]);
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

