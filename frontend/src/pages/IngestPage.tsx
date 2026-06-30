import {
  Alert,
  Button,
  FileInput,
  MultiSelect,
  Stack,
  TextInput,
  Title,
} from "@mantine/core";
import { useEffect, useState } from "react";

import { getOptions, ingest } from "../api/client";
import type { IngestResult, Options } from "../api/types";

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
    <Stack maw={640}>
      <Title order={2}>Inserir documentos</Title>
      <TextInput
        label="Nome da base"
        value={base}
        onChange={(e) => setBase(e.currentTarget.value)}
      />
      <MultiSelect
        label="Técnicas de corte"
        data={options?.chunkings ?? []}
        value={chunkings}
        onChange={setChunkings}
      />
      <MultiSelect
        label="Modelos de embedding"
        data={options?.embeddings ?? []}
        value={embeddings}
        onChange={setEmbeddings}
      />
      <FileInput
        label="Documentos (.txt / .md)"
        multiple
        value={files}
        onChange={setFiles}
      />
      <Button onClick={submit} loading={loading}>
        Inserir
      </Button>
      {result && (
        <Alert color="green" title="Inserção concluída">
          {result.total_chunks} trechos em {result.collections.length} coleção(ões).
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
