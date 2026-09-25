import { Button, FileInput, NumberInput, Select, TextInput } from "@mantine/core";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { createExperiment, getExperiment, getOptions, listExperiments } from "../api/client";
import type { ExperimentRef, IndexPair, Options } from "../api/types";
import { ChoiceGroup } from "../components/ChoiceGroup";
import { Errata, Note, Saved, errorText } from "../components/Notice";
import { PageHeader } from "../components/PageHeader";
import { ArrowIcon, UploadIcon } from "../components/icons";
import { llmChoices } from "../components/llmOptions";
import { useTasks } from "../context/TasksContext";
import { term } from "../glossary";
import { formatDuration } from "../utils/duration";
import { joinPt } from "../utils/text";

export function ExperimentPage() {
  const { addExperimentTask } = useTasks();
  const [options, setOptions] = useState<Options | null>(null);
  const [name, setName] = useState("");
  const [base, setBase] = useState("");
  const [indexKeys, setIndexKeys] = useState<string[]>([]);
  const [rags, setRags] = useState<string[]>([]);
  const [retrievers, setRetrievers] = useState<string[]>([]);
  const [llms, setLlms] = useState<string[]>([]);
  const [metrics, setMetrics] = useState<string[]>([]);
  const [concurrency, setConcurrency] = useState<number>(1);
  const [csv, setCsv] = useState<File | null>(null);
  const [questionCount, setQuestionCount] = useState<number | null>(null);
  const [optionsError, setOptionsError] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [created, setCreated] = useState<ExperimentRef | null>(null);

  useEffect(() => {
    getOptions().then(setOptions).catch((e) => setOptionsError(errorText(e)));
  }, []);

  const msPerAnswer = useMsPerAnswer();

  useEffect(() => {
    setQuestionCount(null);
    if (!csv) return;
    let active = true;
    const reader = new FileReader();
    reader.onload = () => {
      if (active && typeof reader.result === "string") setQuestionCount(countCsvRecords(reader.result));
    };
    reader.readAsText(csv);
    return () => {
      active = false;
    };
  }, [csv]);

  const baseIndexes: IndexPair[] = (base && options?.base_indexes?.[base]) || [];
  const allIndexKeys = baseIndexes.map(indexKey);

  function chooseBase(value: string) {
    setBase(value);
    setIndexKeys(((value && options?.base_indexes?.[value]) || []).map(indexKey));
  }

  const allFilled =
    options !== null &&
    options.rags.length > 0 &&
    indexKeys.length === allIndexKeys.length &&
    rags.length === options.rags.length &&
    retrievers.length === options.retrievers.length &&
    llms.length === options.llms.length &&
    metrics.length === options.metrics.length;

  function toggleAll() {
    if (allFilled) {
      setIndexKeys([]);
      setRags([]);
      setRetrievers([]);
      setLlms([]);
      setMetrics([]);
    } else {
      setIndexKeys(allIndexKeys);
      setRags(options?.rags ?? []);
      setRetrievers(options?.retrievers ?? []);
      setLlms(options?.llms ?? []);
      setMetrics(options?.metrics ?? []);
    }
  }

  const forms = indexKeys.length * rags.length * retrievers.length * llms.length;
  const missing = [
    base === "" && "a base",
    base !== "" && indexKeys.length === 0 && "um índice",
    rags.length === 0 && "uma técnica de RAG",
    retrievers.length === 0 && "uma busca",
    llms.length === 0 && "um modelo",
    metrics.length === 0 && "uma métrica",
    csv === null && "o arquivo de perguntas",
  ].filter(Boolean) as string[];

  async function submit() {
    setSubmitError(null);
    setCreated(null);
    try {
      const indexes = baseIndexes.filter((i) => indexKeys.includes(indexKey(i)));
      const config = {
        name: name || undefined,
        base,
        chunkings: unique(indexes.map((i) => i.chunking)),
        embeddings: unique(indexes.map((i) => i.embedding)),
        indexes,
        rags,
        retrievers,
        llms,
        metrics,
        concurrency,
      };
      const form = new FormData();
      form.append("config", JSON.stringify(config));
      if (csv) form.append("questions", csv);
      const ref = await createExperiment(form);
      addExperimentTask(ref.id, ref.name);
      setCreated(ref);
      setName("");
      setCsv(null);
    } catch (e) {
      setSubmitError(errorText(e));
    }
  }

  const noBases = options !== null && options.bases.length === 0;

  return (
    <div>
      <PageHeader
        title="Novo experimento"
        lede="Escolha o que comparar. O Ditto roda cada combinação sobre as suas perguntas e mede a qualidade de cada resposta."
      />

      {optionsError && (
        <Errata title="Não foi possível carregar as técnicas disponíveis">
          {optionsError}. Confira se a API está no ar (make up) e recarregue a página.
        </Errata>
      )}

      {noBases && (
        <Note title="Nenhuma base preparada ainda">
          <p>
            Um experimento roda sobre documentos já indexados.{" "}
            <Link to="/ingest">Prepare seus documentos</Link> primeiro.
          </p>
        </Note>
      )}

      <div className="ditto-form">
        <div className="ditto-row-actions" style={{ justifyContent: "flex-end", marginBottom: 12 }}>
          <Button variant="default" size="sm" disabled={options === null} onClick={toggleAll}>
            {allFilled ? "Limpar tudo" : "Preencher tudo"}
          </Button>
        </div>

        <section className="ditto-sec">
          <div className="ditto-sec-head">
            <h2 className="ditto-h2">Documentos</h2>
            <p className="ditto-read">
              A base e os índices (corte × embedding) que ela já tem. Cada índice marcado entra na
              comparação.
            </p>
          </div>
          <div className="ditto-sec-body">
            <Select
              label="Base"
              placeholder="Escolha uma base"
              data={options?.bases ?? []}
              value={base || null}
              onChange={(v) => chooseBase(v ?? "")}
              searchable
              allowDeselect={false}
              maw={420}
            />
            <ChoiceGroup
              legend="Índices da base"
              choices={baseIndexes.map((i) => ({
                value: indexKey(i),
                name: `${i.chunking} · ${i.embedding}`,
                description: `${term("chunking", i.chunking).name} + ${term("embedding", i.embedding).name}`,
              }))}
              value={indexKeys}
              onChange={setIndexKeys}
              empty={base ? "Esta base ainda não tem índices." : "Escolha uma base para ver os índices dela."}
            />
            <Link
              to={base ? `/ingest?base=${encodeURIComponent(base)}` : "/ingest"}
              style={{ fontSize: 14, fontWeight: 600, alignSelf: "flex-start" }}
            >
              {base ? "Indexar mais variações desta base" : "Preparar documentos"}
            </Link>
          </div>
        </section>

        <section className="ditto-sec">
          <div className="ditto-sec-head">
            <h2 className="ditto-h2">Como responder</h2>
            <p className="ditto-read">
              A técnica de RAG decide como os trechos viram resposta; a busca decide quais trechos
              chegam até ela.
            </p>
          </div>
          <div className="ditto-sec-body">
            <ChoiceGroup
              legend="Técnica de RAG"
              choices={(options?.rags ?? []).map((k) => ({ value: k, code: k, ...term("rag", k) }))}
              value={rags}
              onChange={setRags}
              empty="Carregando…"
            />
            <ChoiceGroup
              legend="Busca (retriever)"
              choices={(options?.retrievers ?? []).map((k) => ({ value: k, code: k, ...term("retriever", k) }))}
              value={retrievers}
              onChange={setRetrievers}
              empty="Carregando…"
            />
          </div>
        </section>

        <section className="ditto-sec">
          <div className="ditto-sec-head">
            <h2 className="ditto-h2">Modelo</h2>
            <p className="ditto-read">
              O LLM que escreve as respostas. Os modelos locais vêm do servidor de LLM da sua máquina (MLX ou Ollama).
            </p>
          </div>
          <div className="ditto-sec-body">
            <ChoiceGroup
              legend="Modelos (LLM)"
              choices={llmChoices(options)}
              value={llms}
              onChange={setLlms}
              empty="Carregando…"
            />
          </div>
        </section>

        <section className="ditto-sec">
          <div className="ditto-sec-head">
            <h2 className="ditto-h2">Perguntas e métricas</h2>
            <p className="ditto-read">
              Um CSV com as colunas <span className="ditto-mono">pergunta</span> e{" "}
              <span className="ditto-mono">resposta_referencia</span>. A coluna opcional{" "}
              <span className="ditto-mono">evidencia_referencia</span> traz trechos do documento
              que respondem à pergunta, separados por <span className="ditto-mono">|</span>; as
              métricas da busca só são calculadas com ela. Cada métrica vai de 0 a 1; quanto maior,
              melhor.
            </p>
          </div>
          <div className="ditto-sec-body">
            <FileInput
              label="Perguntas (CSV)"
              placeholder="Escolher arquivo .csv"
              accept=".csv,text/csv"
              value={csv}
              onChange={setCsv}
              leftSection={<UploadIcon />}
              maw={520}
              description={
                questionCount !== null
                  ? `${questionCount} ${questionCount === 1 ? "pergunta encontrada" : "perguntas encontradas"} no arquivo.`
                  : undefined
              }
            />
            <ChoiceGroup
              legend="Métricas"
              choices={(options?.metrics ?? []).map((k) => ({ value: k, code: k, ...term("metric", k) }))}
              value={metrics}
              onChange={setMetrics}
              empty="Carregando…"
            />
          </div>
        </section>

        <section className="ditto-sec">
          <div className="ditto-sec-head">
            <h2 className="ditto-h2">Execução</h2>
            <p className="ditto-read">Opcional. Os valores padrão servem para a maioria dos casos.</p>
          </div>
          <div className="ditto-sec-body" style={{ flexDirection: "row", flexWrap: "wrap", gap: 20 }}>
            <TextInput
              label="Nome do experimento"
              description="Se ficar vazio, o Ditto gera um nome."
              placeholder="ex.: teste-cortes-maio"
              value={name}
              onChange={(e) => setName(e.currentTarget.value)}
              w={300}
            />
            <NumberInput
              label="Perguntas em paralelo"
              description="Acima de 1 só acelera se o servidor da LLM atende em paralelo (OLLAMA_NUM_PARALLEL)."
              min={1}
              max={32}
              value={concurrency}
              onChange={(v) => setConcurrency(typeof v === "number" && v >= 1 ? v : 1)}
              w={300}
            />
          </div>
        </section>

        {submitError && (
          <div style={{ marginBottom: 16 }}>
            <Errata title="O experimento não foi criado">
              {submitError}. Revise as escolhas e o CSV e tente de novo.
            </Errata>
          </div>
        )}

        <div className="ditto-strip">
          <div className="ditto-strip-figures" aria-live="polite">
            <span className="ditto-strip-fig">
              <span className="ditto-strip-num">{forms}</span>
              <span className="ditto-strip-label">{forms === 1 ? "combinação" : "combinações"}</span>
            </span>
            {questionCount !== null && (
              <>
                <span className="ditto-strip-op" aria-hidden>×</span>
                <span className="ditto-strip-fig">
                  <span className="ditto-strip-num">{questionCount}</span>
                  <span className="ditto-strip-label">perguntas</span>
                </span>
                <span className="ditto-strip-op" aria-hidden>=</span>
                <span className="ditto-strip-fig">
                  <span className="ditto-strip-num">{forms * questionCount}</span>
                  <span className="ditto-strip-label">respostas a gerar e avaliar</span>
                </span>
                {msPerAnswer !== null && forms * questionCount > 0 && (
                  <span className="ditto-strip-fig" title="Estimativa pelo ritmo do último experimento concluído">
                    <span className="ditto-strip-label">· cerca de</span>
                    <span className="ditto-strip-num">
                      {formatDuration((forms * questionCount * msPerAnswer) / concurrency)}
                    </span>
                    <span className="ditto-strip-label">(estimativa)</span>
                  </span>
                )}
              </>
            )}
          </div>
          <Button
            className="ditto-strip-action"
            size="md"
            onClick={submit}
            disabled={missing.length > 0}
            rightSection={<ArrowIcon />}
          >
            Gerar experimento
          </Button>
          {missing.length > 0 && <p className="ditto-strip-missing">Ainda falta: {joinPt(missing)}.</p>}
          {created && (
            <p className="ditto-strip-missing">
              <Saved>Experimento “{created.name}” criado.</Saved> Ele roda em segundo plano.{" "}
              <Link to={`/results/${created.id}`}>Acompanhar</Link>
            </p>
          )}
          {created?.warnings?.map((w) => (
            <Note key={w} title="Atenção à memória">
              {w}
            </Note>
          ))}
        </div>
      </div>
    </div>
  );
}

/**
 * Wall-clock time per answer in the most recent finished experiment, used to
 * estimate how long a new run will take. Null when there is no such run.
 */
function useMsPerAnswer(): number | null {
  const [ms, setMs] = useState<number | null>(null);
  useEffect(() => {
    let active = true;
    Promise.resolve()
      .then(() => listExperiments(1, 10))
      .then((list) => {
        const last = list?.items.find((e) => e.status === "done");
        return last ? getExperiment(last.id) : null;
      })
      .then((d) => {
        if (!active || !d?.created_at || !d.finished_at || d.results.length === 0) return;
        const elapsed = new Date(d.finished_at).getTime() - new Date(d.created_at).getTime();
        if (elapsed > 0) setMs(elapsed / d.results.length);
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, []);
  return ms;
}

function indexKey(i: IndexPair): string {
  return `${i.chunking}|${i.embedding}`;
}

function unique(values: string[]): string[] {
  return [...new Set(values)];
}

/** Data records in a CSV (header excluded), honouring quoted line breaks. */
export function countCsvRecords(text: string): number {
  let records = 0;
  let inQuotes = false;
  let rowHasContent = false;
  for (const ch of text) {
    if (ch === '"') inQuotes = !inQuotes;
    if (ch === "\n" && !inQuotes) {
      if (rowHasContent) records += 1;
      rowHasContent = false;
    } else if (ch !== "\r" && ch.trim() !== "") {
      rowHasContent = true;
    }
  }
  if (rowHasContent) records += 1;
  return Math.max(0, records - 1);
}
