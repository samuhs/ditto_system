import { Button, Select, TextInput } from "@mantine/core";
import { useEffect, useState } from "react";

import {
  createChatConfig,
  deleteChatConfig,
  getOptions,
  getPersonas,
  listChatConfigs,
} from "../api/client";
import type { ChatConfig, Options } from "../api/types";
import { Errata, Saved, errorText } from "../components/Notice";
import { PageHeader } from "../components/PageHeader";
import { llmSelectData } from "../components/llmOptions";
import { term } from "../glossary";

const named = (dim: "chunking" | "embedding" | "rag" | "retriever", keys: string[] = []) =>
  keys.map((k) => ({ value: k, label: term(dim, k).name }));

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
  const [created, setCreated] = useState<string | null>(null);
  const [confirmId, setConfirmId] = useState<number | null>(null);

  function refresh() {
    listChatConfigs().then(setConfigs).catch((e) => setError(errorText(e)));
  }

  useEffect(() => {
    getOptions()
      .then((opts) => {
        setOptions(opts);
        if (opts.bases.length > 0) chooseBase(opts.bases[0], opts);
        if (opts.chunkings.length > 0) setChunking((c) => c || opts.chunkings[0]);
        if (opts.embeddings.length > 0) setEmbedding((e) => e || opts.embeddings[0]);
        if (opts.retrievers.length > 0) setRetriever(opts.retrievers[0]);
        const chatRags = opts.rags.filter((r) => r !== "oracle");
        if (chatRags.length > 0) setRag(chatRags[0]);
        if (opts.llms.length > 0) setLlm(opts.llms[0]);
      })
      .catch((e) => setError(errorText(e)));
    getPersonas()
      .then((p) => {
        setPersonas(p.personas);
        if (p.personas.length > 0) setPersona(p.personas[0]);
      })
      .catch((e) => setError(errorText(e)));
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function chooseBase(value: string, opts: Options | null = options) {
    setBase(value);
    const first = opts?.base_indexes?.[value]?.[0];
    if (first) {
      setChunking(first.chunking);
      setEmbedding(first.embedding);
    }
  }

  const indexes = (base && options?.base_indexes?.[base]) || null;

  async function submit() {
    setError(null);
    setCreated(null);
    try {
      await createChatConfig({ name, base, chunking, embedding, retriever, rag, llm, persona });
      setCreated(name);
      setName("");
      refresh();
    } catch (e) {
      setError(errorText(e));
    }
  }

  async function remove(id: number) {
    try {
      await deleteChatConfig(id);
      setConfirmId(null);
      refresh();
    } catch (e) {
      setError(errorText(e));
    }
  }

  const canSubmit = name.trim() !== "" && base && chunking && embedding && retriever && rag && persona;

  return (
    <div>
      <PageHeader
        title="Configurações de chat"
        lede="Uma configuração diz ao agente qual base consultar, com qual técnica, qual modelo e com que persona responder. Crie uma para cada setup que quiser conversar."
      />

      {error && (
        <div style={{ marginBottom: 20 }}>
          <Errata title="Algo não funcionou">{error}. Tente de novo.</Errata>
        </div>
      )}

      <div className="ditto-form">
        <section className="ditto-sec">
          <div className="ditto-sec-head">
            <h2 className="ditto-h2">Nova configuração</h2>
            <p className="ditto-read">
              Dica: use a melhor combinação do seu último experimento, em Resultados.
            </p>
          </div>
          <div className="ditto-sec-body">
            <TextInput
              label="Nome da configuração"
              placeholder="ex.: guia-recursivo-gemini"
              value={name}
              onChange={(e) => setName(e.currentTarget.value)}
              maw={420}
            />
            <div className="ditto-filters" style={{ margin: 0 }}>
              <Select label="Base" data={options?.bases ?? []} value={base || null} onChange={(v) => chooseBase(v ?? "")} searchable allowDeselect={false} />
              {indexes ? (
                <Select
                  label="Índice (corte · embedding)"
                  data={indexes.map((i) => ({
                    value: `${i.chunking}|${i.embedding}`,
                    label: `${term("chunking", i.chunking).name} · ${term("embedding", i.embedding).name}`,
                  }))}
                  value={`${chunking}|${embedding}`}
                  onChange={(v) => {
                    const [c, e] = (v ?? "|").split("|");
                    setChunking(c);
                    setEmbedding(e);
                  }}
                  allowDeselect={false}
                />
              ) : (
                <>
                  <Select label="Corte" data={named("chunking", options?.chunkings)} value={chunking || null} onChange={(v) => setChunking(v ?? "")} allowDeselect={false} />
                  <Select label="Embedding" data={named("embedding", options?.embeddings)} value={embedding || null} onChange={(v) => setEmbedding(v ?? "")} allowDeselect={false} />
                </>
              )}
              <Select label="Técnica de RAG" data={named("rag", options?.rags.filter((r) => r !== "oracle"))} value={rag || null} onChange={(v) => setRag(v ?? "")} allowDeselect={false} />
              <Select label="Busca" data={named("retriever", options?.retrievers)} value={retriever || null} onChange={(v) => setRetriever(v ?? "")} allowDeselect={false} />
              <Select label="Modelo (LLM)" data={llmSelectData(options)} value={llm || null} onChange={(v) => setLlm(v ?? "gemini")} searchable allowDeselect={false} />
              <Select label="Persona" data={personas} value={persona || null} onChange={(v) => setPersona(v ?? "")} allowDeselect={false} />
            </div>
            <div className="ditto-row-actions">
              <Button onClick={submit} disabled={!canSubmit}>
                Criar configuração
              </Button>
              {created && <Saved>“{created}” criada. Já aparece na Conversa.</Saved>}
            </div>
          </div>
        </section>

        <section className="ditto-sec">
          <div className="ditto-sec-head">
            <h2 className="ditto-h2">Salvas</h2>
            <p className="ditto-read">
              {configs.length === 0
                ? "Nenhuma configuração ainda."
                : `${configs.length} ${configs.length === 1 ? "configuração" : "configurações"}.`}
            </p>
          </div>
          <div className="ditto-sec-body">
            {configs.length > 0 && (
              <ul className="ditto-records">
                {configs.map((c) => (
                  <li key={c.id} className="ditto-record" style={{ gridTemplateColumns: "minmax(0,1fr) auto" }}>
                    <div>
                      <div style={{ fontWeight: 650 }}>{c.name}</div>
                      <div className="ditto-record-sub">
                        {c.base} · {term("chunking", c.chunking).name} · {term("embedding", c.embedding).name} ·{" "}
                        {term("rag", c.rag).name} · {term("retriever", c.retriever).name} · {c.llm} · persona {c.persona}
                      </div>
                    </div>
                    {confirmId === c.id ? (
                      <span className="ditto-row-actions">
                        <span style={{ fontSize: 14 }}>Remover de vez?</span>
                        <Button size="sm" className="ditto-danger" onClick={() => remove(c.id)}>
                          Remover
                        </Button>
                        <Button size="sm" variant="subtle" onClick={() => setConfirmId(null)}>
                          Cancelar
                        </Button>
                      </span>
                    ) : (
                      <Button size="sm" variant="default" onClick={() => setConfirmId(c.id)}>
                        Remover
                      </Button>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
