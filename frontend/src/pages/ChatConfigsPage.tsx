import { Alert, Button, Group, Select, Stack, Text, TextInput } from "@mantine/core";
import { useEffect, useState } from "react";

import {
  createChatConfig,
  deleteChatConfig,
  getOptions,
  getPersonas,
  listChatConfigs,
} from "../api/client";
import type { ChatConfig, Options } from "../api/types";
import { PageHeader } from "../components/PageHeader";
import { llmOptionRenderer, llmSelectData } from "../components/llmOptions";

export function ChatConfigsPage() {
  const [options, setOptions] = useState<Options | null>(null);
  const [personas, setPersonas] = useState<string[]>([]);
  const [configs, setConfigs] = useState<ChatConfig[]>([]);
  const [name, setName] = useState("");
  const [base, setBase] = useState("");
  const [chunking, setChunking] = useState("");
  const [embedding, setEmbedding] = useState("");
  const [retriever, setRetriever] = useState("");
  const [rag, setRag] = useState("");
  const [llm, setLlm] = useState("gemini");
  const [persona, setPersona] = useState("travel_guide");
  const [error, setError] = useState<string | null>(null);

  function refresh() {
    listChatConfigs().then(setConfigs).catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }

  useEffect(() => {
    getOptions().then((opts) => {
      setOptions(opts);
      if (opts.bases.length > 0) setBase(opts.bases[0]);
      if (opts.chunkings.length > 0) setChunking(opts.chunkings[0]);
      if (opts.embeddings.length > 0) setEmbedding(opts.embeddings[0]);
      if (opts.retrievers.length > 0) setRetriever(opts.retrievers[0]);
      if (opts.rags.length > 0) setRag(opts.rags[0]);
      if (opts.llms.length > 0) setLlm(opts.llms[0]);
    }).catch((e) => setError(e instanceof Error ? e.message : String(e)));
    getPersonas().then((p) => {
      setPersonas(p.personas);
      if (p.personas.length > 0) setPersona(p.personas[0]);
    }).catch((e) => setError(e instanceof Error ? e.message : String(e)));
    refresh();
  }, []);

  async function submit() {
    setError(null);
    try {
      await createChatConfig({ name, base, chunking, embedding, retriever, rag, llm, persona });
      setName("");
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  const canSubmit = name.trim() !== "" && base && chunking && embedding && retriever && rag && persona;

  return (
    <div>
      <PageHeader
        eyebrow="Passo 04 · Conversar"
        title="Configurações de chat"
        subtitle="Crie uma configuração para o agente conversacional: qual base/coleção consultar, retriever, modelo e persona."
      />

      <div className="ditto-glass" style={{ padding: 30, maxWidth: 760 }}>
        <Stack gap="lg">
          <TextInput label="Nome" value={name} onChange={(e) => setName(e.currentTarget.value)} />
          <Group grow align="flex-start">
            <Select label="Base" data={options?.bases ?? []} value={base || null} onChange={(v) => setBase(v ?? "")} searchable />
            <Select label="Corte" data={options?.chunkings ?? []} value={chunking || null} onChange={(v) => setChunking(v ?? "")} searchable />
          </Group>
          <Group grow align="flex-start">
            <Select label="Embedding" data={options?.embeddings ?? []} value={embedding || null} onChange={(v) => setEmbedding(v ?? "")} searchable />
            <Select label="Retriever" data={options?.retrievers ?? []} value={retriever || null} onChange={(v) => setRetriever(v ?? "")} searchable />
            <Select label="RAG" data={options?.rags ?? []} value={rag || null} onChange={(v) => setRag(v ?? "")} searchable />
          </Group>
          <Group grow align="flex-start">
            <Select label="Modelo (LLM)" data={llmSelectData(options)} renderOption={llmOptionRenderer(options)} value={llm || null} onChange={(v) => setLlm(v ?? "gemini")} searchable />
            <Select label="Persona" data={personas} value={persona || null} onChange={(v) => setPersona(v ?? "")} searchable />
          </Group>
          <Button
            onClick={submit}
            disabled={!canSubmit}
            size="md"
            variant="gradient"
            gradient={{ from: "#ab63f2", to: "#f26dcf", deg: 115 }}
            style={{ alignSelf: "flex-start" }}
          >
            Criar
          </Button>
        </Stack>
      </div>

      {error && (
        <Alert color="red" variant="light" title="Erro" mt="xl" radius="lg" maw={760}>
          {error}
        </Alert>
      )}

      <div className="ditto-exp-list" style={{ maxWidth: 760, marginTop: 24 }}>
        {configs.map((c) => (
          <div key={c.id} className="ditto-exp-row" style={{ cursor: "default" }}>
            <div>
              <Text fw={600} fz="sm">{c.name}</Text>
              <Text size="xs" c="dimmed">
                {c.base} · {c.chunking} · {c.embedding} · {c.retriever} · {c.persona}
              </Text>
            </div>
            <Button
              size="xs"
              variant="subtle"
              color="red"
              onClick={() => deleteChatConfig(c.id).then(refresh).catch((e) => setError(e instanceof Error ? e.message : String(e)))}
            >
              Remover
            </Button>
          </div>
        ))}
      </div>
    </div>
  );
}
