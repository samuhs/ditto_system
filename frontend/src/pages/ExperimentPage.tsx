import {
  Alert,
  Button,
  FileInput,
  Group,
  MultiSelect,
  Select,
  Stack,
  TextInput,
} from "@mantine/core";
import { useEffect, useState } from "react";

import { createExperiment, getOptions } from "../api/client";
import type { Options } from "../api/types";
import { PageHeader } from "../components/PageHeader";
import { ArrowIcon } from "../components/icons";
import { useTasks } from "../context/TasksContext";

export function ExperimentPage() {
  const { addExperimentTask } = useTasks();
  const [options, setOptions] = useState<Options | null>(null);
  const [name, setName] = useState("");
  const [base, setBase] = useState("");
  const [chunkings, setChunkings] = useState<string[]>([]);
  const [embeddings, setEmbeddings] = useState<string[]>([]);
  const [rags, setRags] = useState<string[]>([]);
  const [retrievers, setRetrievers] = useState<string[]>([]);
  const [llms, setLlms] = useState<string[]>([]);
  const [metrics, setMetrics] = useState<string[]>([]);
  const [csv, setCsv] = useState<File | null>(null);
  const [optionsError, setOptionsError] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const allFilled =
    options !== null &&
    options.chunkings.length > 0 &&
    chunkings.length === options.chunkings.length &&
    embeddings.length === options.embeddings.length &&
    rags.length === options.rags.length &&
    retrievers.length === options.retrievers.length &&
    llms.length === options.llms.length &&
    metrics.length === options.metrics.length;

  function toggleAll() {
    if (allFilled) {
      setChunkings([]);
      setEmbeddings([]);
      setRags([]);
      setRetrievers([]);
      setLlms([]);
      setMetrics([]);
    } else {
      setChunkings(options?.chunkings ?? []);
      setEmbeddings(options?.embeddings ?? []);
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
      const config = {
        name: name || undefined,
        base,
        chunkings,
        embeddings,
        rags,
        retrievers,
        llms,
        metrics,
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
              onChange={(v) => setBase(v ?? "")}
              searchable
            />
          </Group>
          <Group grow align="flex-start">
            <MultiSelect
              label="Cortes"
              placeholder="Selecione"
              data={options?.chunkings ?? []}
              value={chunkings}
              onChange={setChunkings}
              searchable
            />
            <MultiSelect
              label="Embeddings"
              placeholder="Selecione"
              data={options?.embeddings ?? []}
              value={embeddings}
              onChange={setEmbeddings}
              searchable
            />
          </Group>
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
              data={options?.llms ?? []}
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
