import {
  Alert,
  Anchor,
  Button,
  FileInput,
  Group,
  MultiSelect,
  NumberInput,
  Select,
  Stack,
  TextInput,
} from "@mantine/core";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { createExperiment, getOptions } from "../api/client";
import type { IndexPair, Options } from "../api/types";
import { PageHeader } from "../components/PageHeader";
import { ArrowIcon } from "../components/icons";
import { llmOptionRenderer, llmSelectData } from "../components/llmOptions";
import { useTasks } from "../context/TasksContext";

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
  const [optionsError, setOptionsError] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);

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

  useEffect(() => {
    getOptions().then(setOptions).catch((e) => setOptionsError(String(e)));
  }, []);

  async function submit() {
    setSubmitError(null);
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
      setName("");
      setCsv(null);
    } catch (e) {
      setSubmitError(String(e));
      setName("");
    }
  }

  return (
    <div>
      <PageHeader
        eyebrow="Passo 02 · Experimentar"
        title="Gerar teste de qualidade"
        subtitle="Escolha as estratégias a combinar e o conjunto de perguntas. O Ditto executa cada forma possível e mede a qualidade das respostas — acompanhe no canto inferior direito."
      />

      <div className="ditto-glass" style={{ padding: "30px", maxWidth: 760 }}>
        <Stack gap="lg">
          <Group justify="flex-end">
            <Button
              variant="subtle"
              size="xs"
              disabled={options === null}
              color={allFilled ? "gray" : "violet"}
              onClick={toggleAll}
            >
              {allFilled ? "Limpar tudo" : "Preencher tudo"}
            </Button>
          </Group>
          <Group grow align="flex-start">
            <TextInput
              label="Nome do experimento (opcional)"
              placeholder="gerado automaticamente"
              value={name}
              onChange={(e) => setName(e.currentTarget.value)}
            />
            <Select
              label="Base"
              placeholder="Selecione a base ingerida"
              data={options?.bases ?? []}
              value={base || null}
              onChange={(v) => chooseBase(v ?? "")}
              searchable
            />
          </Group>
          <Stack gap={4}>
            <MultiSelect
              label="Índices da base"
              description="Variações de corte × embedding já indexadas para esta base."
              placeholder={base ? "Selecione" : "Escolha a base primeiro"}
              data={baseIndexes.map((i) => ({ value: indexKey(i), label: `${i.chunking} · ${i.embedding}` }))}
              value={indexKeys}
              onChange={setIndexKeys}
              disabled={!base}
              searchable
            />
            <Anchor
              component={Link}
              to={base ? `/ingest?base=${encodeURIComponent(base)}` : "/ingest"}
              size="xs"
              c="dimmed"
            >
              {base ? "Indexar mais variações desta base →" : "Indexar documentos →"}
            </Anchor>
          </Stack>
          <Group grow align="flex-start">
            <MultiSelect
              label="RAGs"
              placeholder="Selecione"
              data={options?.rags ?? []}
              value={rags}
              onChange={setRags}
              searchable
            />
            <MultiSelect
              label="Retrievers"
              placeholder="Selecione"
              data={options?.retrievers ?? []}
              value={retrievers}
              onChange={setRetrievers}
              searchable
            />
          </Group>
          <Group grow align="flex-start">
            <MultiSelect
              label="LLMs"
              placeholder="Selecione"
              data={llmSelectData(options)}
              renderOption={llmOptionRenderer(options)}
              value={llms}
              onChange={setLlms}
              searchable
            />
            <MultiSelect
              label="Métricas"
              placeholder="Selecione"
              data={options?.metrics ?? []}
              value={metrics}
              onChange={setMetrics}
              searchable
            />
          </Group>
          <NumberInput
            label="Perguntas em paralelo"
            description="Acima de 1 só acelera se o servidor da LLM atende em paralelo (ex.: OLLAMA_NUM_PARALLEL)."
            min={1}
            max={32}
            value={concurrency}
            onChange={(v) => setConcurrency(typeof v === "number" && v >= 1 ? v : 1)}
            style={{ maxWidth: 240 }}
          />
          <FileInput
            label="Perguntas (CSV)"
            placeholder="Escolher arquivo .csv"
            value={csv}
            onChange={setCsv}
          />
          <Button
            onClick={submit}
            size="md"
            variant="gradient"
            gradient={{ from: "#ab63f2", to: "#f26dcf", deg: 115 }}
            rightSection={<ArrowIcon />}
            style={{ alignSelf: "flex-start" }}
          >
            Gerar
          </Button>
        </Stack>
      </div>

      {optionsError && (
        <Alert color="red" variant="light" title="Erro ao carregar opções" mt="xl" radius="lg" maw={760}>
          {optionsError}
        </Alert>
      )}
      {submitError && (
        <Alert color="red" variant="light" title="Erro ao criar experimento" mt="xl" radius="lg" maw={760}>
          {submitError}
        </Alert>
      )}
    </div>
  );
}

function indexKey(i: IndexPair): string {
  return `${i.chunking}|${i.embedding}`;
}

function unique(values: string[]): string[] {
  return [...new Set(values)];
}
