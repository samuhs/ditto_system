import {
  Alert,
  Button,
  FileInput,
  Group,
  MultiSelect,
  Stack,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import { useEffect, useRef, useState } from "react";

import { createExperiment, getExperiment, getOptions } from "../api/client";
import type { ExperimentDetail, Options } from "../api/types";

const POLL_INTERVAL_MS = 2000;

export function ExperimentPage() {
  const [options, setOptions] = useState<Options | null>(null);
  const [name, setName] = useState("");
  const [base, setBase] = useState("");
  const [chunkings, setChunkings] = useState<string[]>([]);
  const [embeddings, setEmbeddings] = useState<string[]>([]);
  const [rags, setRags] = useState<string[]>([]);
  const [retrievers, setRetrievers] = useState<string[]>([]);
  const [metrics, setMetrics] = useState<string[]>([]);
  const [csv, setCsv] = useState<File | null>(null);
  const [experiment, setExperiment] = useState<ExperimentDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const timer = useRef<number | null>(null);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    getOptions().then(setOptions).catch((e) => setError(String(e)));
    return () => {
      mounted.current = false;
      if (timer.current) window.clearTimeout(timer.current);
    };
  }, []);

  function poll(id: number) {
    getExperiment(id)
      .then((detail) => {
        if (!mounted.current) return;
        setExperiment(detail);
        if (detail.status === "done" || detail.status === "failed") {
          setLoading(false);
        } else {
          timer.current = window.setTimeout(() => poll(id), POLL_INTERVAL_MS);
        }
      })
      .catch((e) => {
        if (!mounted.current) return;
        setError(String(e));
        setLoading(false);
      });
  }

  async function submit() {
    if (loading) return;
    setError(null);
    setLoading(true);
    try {
      const config = {
        name: name || undefined,
        base,
        chunkings,
        embeddings,
        rags,
        retrievers,
        metrics,
      };
      const form = new FormData();
      form.append("config", JSON.stringify(config));
      if (csv) form.append("questions", csv);
      const ref = await createExperiment(form);
      setExperiment({ id: ref.id, name: ref.name, status: ref.status, results: [] });
      poll(ref.id);
    } catch (e) {
      setError(String(e));
      setLoading(false);
    }
  }

  return (
    <Stack maw={720}>
      <Title order={2}>Gerar teste de qualidade</Title>
      <TextInput label="Nome do experimento (opcional)" value={name} onChange={(e) => setName(e.currentTarget.value)} />
      <TextInput label="Base" value={base} onChange={(e) => setBase(e.currentTarget.value)} />
      <Group grow>
        <MultiSelect label="Cortes" data={options?.chunkings ?? []} value={chunkings} onChange={setChunkings} />
        <MultiSelect label="Embeddings" data={options?.embeddings ?? []} value={embeddings} onChange={setEmbeddings} />
      </Group>
      <Group grow>
        <MultiSelect label="RAGs" data={options?.rags ?? []} value={rags} onChange={setRags} />
        <MultiSelect label="Retrievers" data={options?.retrievers ?? []} value={retrievers} onChange={setRetrievers} />
      </Group>
      <MultiSelect label="Métricas" data={options?.metrics ?? []} value={metrics} onChange={setMetrics} />
      <FileInput label="Perguntas (CSV)" value={csv} onChange={setCsv} />
      <Button onClick={submit} loading={loading}>
        Gerar
      </Button>
      {experiment && (
        <Alert
          color={
            experiment.status === "done"
              ? "green"
              : experiment.status === "failed"
                ? "red"
                : "blue"
          }
          title={experiment.name}
        >
          <Text>Status: {experiment.status}</Text>
        </Alert>
      )}
      {error && (
        <Alert color="red" title="Erro">
          {error}
        </Alert>
      )}
    </Stack>
  );
}
