import {
  Alert,
  Button,
  FileInput,
  Group,
  Loader,
  MultiSelect,
  Stack,
  Text,
  TextInput,
} from "@mantine/core";
import { useEffect, useRef, useState } from "react";

import { createExperiment, getExperiment, getOptions } from "../api/client";
import type { ExperimentDetail, Options } from "../api/types";
import { PageHeader } from "../components/PageHeader";
import { ArrowIcon } from "../components/icons";

const POLL_INTERVAL_MS = 2000;

function statusColor(status: string): string {
  if (status === "done") return "#07f285";
  if (status === "failed") return "#f26d6d";
  return "#05dbf2";
}

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

  const running =
    experiment != null &&
    experiment.status !== "done" &&
    experiment.status !== "failed";

  return (
    <div>
      <PageHeader
        eyebrow="Passo 02 · Experimentar"
        title="Gerar teste de qualidade"
        subtitle="Escolha as estratégias a combinar e o conjunto de perguntas. O Ditto executa cada forma possível e mede a qualidade das respostas — você acompanha em tempo real."
      />

      <div className="ditto-glass" style={{ padding: "30px", maxWidth: 760 }}>
        <Stack gap="lg">
          <Group grow align="flex-start">
            <TextInput
              label="Nome do experimento (opcional)"
              placeholder="gerado automaticamente"
              value={name}
              onChange={(e) => setName(e.currentTarget.value)}
            />
            <TextInput
              label="Base"
              placeholder="nome da base ingerida"
              value={base}
              onChange={(e) => setBase(e.currentTarget.value)}
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
          <MultiSelect
            label="Métricas"
            placeholder="Selecione"
            data={options?.metrics ?? []}
            value={metrics}
            onChange={setMetrics}
            searchable
          />
          <FileInput
            label="Perguntas (CSV)"
            placeholder="Escolher arquivo .csv"
            value={csv}
            onChange={setCsv}
          />
          <Button
            onClick={submit}
            loading={loading}
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

      {experiment && (
        <div
          className="ditto-glass"
          style={{
            padding: "22px 26px",
            maxWidth: 760,
            marginTop: 28,
            borderColor: statusColor(experiment.status),
          }}
        >
          <Group justify="space-between" align="center">
            <div>
              <Text className="ditto-mono" size="xs" c="dimmed">
                EXPERIMENTO
              </Text>
              <Text fw={700} fz="lg" mt={4}>
                {experiment.name}
              </Text>
            </div>
            <Group gap="xs" align="center">
              {running && <Loader size="xs" color="#05dbf2" />}
              <span
                className="ditto-chip"
                style={{ color: statusColor(experiment.status) }}
              >
                {experiment.status}
              </span>
            </Group>
          </Group>
        </div>
      )}
      {error && (
        <Alert color="red" variant="light" title="Erro" mt="xl" radius="lg" maw={760}>
          {error}
        </Alert>
      )}
    </div>
  );
}
