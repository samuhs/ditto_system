import {
  Alert,
  Button,
  FileInput,
  Group,
  MultiSelect,
  Stack,
  Text,
  TextInput,
} from "@mantine/core";
import { useEffect, useState } from "react";

import { getOptions, ingest } from "../api/client";
import type { IngestResult, Options } from "../api/types";
import { PageHeader } from "../components/PageHeader";
import { ArrowIcon, UploadIcon } from "../components/icons";

export function IngestPage() {
  const [options, setOptions] = useState<Options | null>(null);
  const [base, setBase] = useState("");
  const [chunkings, setChunkings] = useState<string[]>([]);
  const [embeddings, setEmbeddings] = useState<string[]>([]);
  const [files, setFiles] = useState<File[]>([]);
  const [result, setResult] = useState<IngestResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    getOptions().then(setOptions).catch((e) => setError(String(e)));
  }, []);

  async function submit() {
    setError(null);
    setResult(null);
    setLoading(true);
    try {
      const form = new FormData();
      form.append("base", base);
      form.append("chunkings", chunkings.join(","));
      form.append("embeddings", embeddings.join(","));
      files.forEach((file) => form.append("files", file));
      setResult(await ingest(form));
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <PageHeader
        eyebrow="Passo 01 · Absorver"
        title="Inserir documentos"
        subtitle="Envie seus textos e escolha como o Ditto vai cortá-los e representá-los. Cada combinação de corte e embedding vira uma coleção pronta para os experimentos."
      />

      <div className="ditto-glass" style={{ padding: "30px", maxWidth: 680 }}>
        <Stack gap="lg">
          <TextInput
            label="Nome da base"
            placeholder="ex.: manuais-de-viagem"
            value={base}
            onChange={(e) => setBase(e.currentTarget.value)}
          />
          <Group grow align="flex-start">
            <MultiSelect
              label="Técnicas de corte"
              placeholder="Selecione"
              data={options?.chunkings ?? []}
              value={chunkings}
              onChange={setChunkings}
              searchable
            />
            <MultiSelect
              label="Modelos de embedding"
              placeholder="Selecione"
              data={options?.embeddings ?? []}
              value={embeddings}
              onChange={setEmbeddings}
              searchable
            />
          </Group>
          <FileInput
            label="Documentos (.txt / .md)"
            placeholder="Escolher arquivos"
            multiple
            value={files}
            onChange={setFiles}
            leftSection={<UploadIcon />}
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
            Inserir
          </Button>
        </Stack>
      </div>

      {result && (
        <Alert
          color="teal"
          variant="light"
          title="Inserção concluída"
          mt="xl"
          radius="lg"
          maw={680}
        >
          <Group gap="xs" align="baseline">
            <Text className="ditto-mono" fz={28} fw={700} c="#07f285">
              {result.total_chunks}
            </Text>
            <Text c="dimmed">
              trechos absorvidos em {result.collections.length} coleção(ões).
            </Text>
          </Group>
        </Alert>
      )}
      {error && (
        <Alert color="red" variant="light" title="Erro" mt="xl" radius="lg" maw={680}>
          {error}
        </Alert>
      )}
    </div>
  );
}
