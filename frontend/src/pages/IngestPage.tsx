import {
  Alert,
  Button,
  FileInput,
  Group,
  MultiSelect,
  Stack,
  TextInput,
} from "@mantine/core";
import { useEffect, useState } from "react";

import { getOptions, ingest } from "../api/client";
import type { Options } from "../api/types";
import { PageHeader } from "../components/PageHeader";
import { ArrowIcon, UploadIcon } from "../components/icons";
import { useTasks } from "../context/TasksContext";

export function IngestPage() {
  const { addIngestTask } = useTasks();
  const [options, setOptions] = useState<Options | null>(null);
  const [base, setBase] = useState("");
  const [chunkings, setChunkings] = useState<string[]>([]);
  const [embeddings, setEmbeddings] = useState<string[]>([]);
  const [files, setFiles] = useState<File[]>([]);
  const [optionsError, setOptionsError] = useState<string | null>(null);

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

  useEffect(() => {
    getOptions().then(setOptions).catch((e) => setOptionsError(String(e)));
  }, []);

  function submit() {
    const form = new FormData();
    form.append("base", base);
    form.append("chunkings", chunkings.join(","));
    form.append("embeddings", embeddings.join(","));
    files.forEach((file) => form.append("files", file));
    addIngestTask(`Inserção · ${base || "sem nome"}`, ingest(form));
    setFiles([]);
  }

  const canSubmit = base.trim() !== "" && chunkings.length > 0 && embeddings.length > 0;

  return (
    <div>
      <PageHeader
        eyebrow="Passo 01 · Absorver"
        title="Inserir documentos"
        subtitle="Envie seus textos e escolha como o Ditto vai cortá-los e representá-los. Cada combinação de corte e embedding vira uma coleção pronta para os experimentos."
      />

      <div className="ditto-glass" style={{ padding: "30px", maxWidth: 680 }}>
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
            disabled={!canSubmit}
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

      {optionsError && (
        <Alert color="red" variant="light" title="Erro ao carregar opções" mt="xl" radius="lg" maw={680}>
          {optionsError}
        </Alert>
      )}
    </div>
  );
}
