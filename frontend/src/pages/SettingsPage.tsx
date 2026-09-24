import { Button, PasswordInput, TextInput } from "@mantine/core";
import { useEffect, useState } from "react";

import { getMemory, getSettings, saveGeminiKey, saveOllamaModels } from "../api/client";
import type { MemoryStatus, OllamaModel } from "../api/types";
import { Errata, Saved, errorText } from "../components/Notice";
import { PageHeader } from "../components/PageHeader";
import { StatusTag } from "../components/StatusTag";

const PROFILE_TEXT: Record<string, string> = {
  low: "Para máquinas com até 8 GB. Um modelo local na memória por vez, embeddings na CPU e menos perguntas em paralelo. Os experimentos ficam mais lentos, mas a RAM não estoura.",
  standard:
    "Para máquinas com folga de RAM. Até 3 modelos locais na memória, embeddings na GPU quando o LLM não a está usando e mais perguntas em paralelo. Mais rápido, mas pode usar swap se a RAM não comportar.",
};
const OTHER_PROFILE: Record<string, string> = { low: "standard", standard: "low" };
const gb = (bytes: number) => `${(bytes / 1024 ** 3).toFixed(1)} GB`;

export function SettingsPage() {
  const [keySet, setKeySet] = useState(false);
  const [newKey, setNewKey] = useState("");
  const [models, setModels] = useState<OllamaModel[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [keySaved, setKeySaved] = useState(false);
  const [modelsSaved, setModelsSaved] = useState(false);
  const [memory, setMemory] = useState<MemoryStatus | null>(null);
  const [memoryError, setMemoryError] = useState(false);

  // Separate from the settings load: a memory-status failure must not hide the rest.
  useEffect(() => {
    getMemory()
      .then(setMemory)
      .catch(() => setMemoryError(true));
  }, []);

  useEffect(() => {
    getSettings()
      .then((s) => {
        setKeySet(s.gemini_api_key_set);
        setModels(s.ollama_models);
      })
      .catch((e) => setError(errorText(e)));
  }, []);

  async function saveKey() {
    setError(null);
    setKeySaved(false);
    try {
      const r = await saveGeminiKey(newKey);
      setKeySet(r.gemini_api_key_set);
      setNewKey("");
      setKeySaved(true);
    } catch (e) {
      setError(errorText(e));
    }
  }

  function addModel() {
    setModels((m) => [...m, { id: "", model: "" }]);
    setModelsSaved(false);
  }
  function updateModel(i: number, field: "id" | "model", value: string) {
    setModels((m) => m.map((row, idx) => (idx === i ? { ...row, [field]: value } : row)));
    setModelsSaved(false);
  }
  function removeModel(i: number) {
    setModels((m) => m.filter((_, idx) => idx !== i));
    setModelsSaved(false);
  }

  async function saveModels() {
    setError(null);
    setModelsSaved(false);
    try {
      const r = await saveOllamaModels(models);
      setModels(r.ollama_models);
      setModelsSaved(true);
    } catch (e) {
      setError(errorText(e));
    }
  }

  return (
    <div>
      <PageHeader
        title="Sistema"
        lede="Chaves e modelos usados pelo Ditto. As mudanças valem para as próximas execuções."
      />

      {error && (
        <div style={{ marginBottom: 20 }}>
          <Errata title="A configuração não foi salva">{error}. Revise os valores e tente de novo.</Errata>
        </div>
      )}

      <div className="ditto-form">
        <section className="ditto-sec">
          <div className="ditto-sec-head">
            <h2 className="ditto-h2">Memória</h2>
            <p className="ditto-read">Quanto o Ditto pode ocupar com modelos locais nesta máquina.</p>
          </div>
          <div className="ditto-sec-body">
            {memoryError && (
              <p className="ditto-read" style={{ margin: 0 }}>
                Não foi possível ler o estado da memória.
              </p>
            )}
            {memory && (
              <>
                <StatusTag status="done" label={`Perfil ${memory.profile.name}`} />
                <p className="ditto-read">{PROFILE_TEXT[memory.profile.name]}</p>
                <p className="ditto-read">
                  Em vigor: até {memory.profile.max_local_models} modelo(s) local(is) carregado(s) · embeddings{" "}
                  {memory.profile.embedding_device === "cpu" ? "na CPU" : "na GPU quando livre"} · até{" "}
                  {memory.profile.max_concurrency} pergunta(s) em paralelo.
                </p>
                <p className="ditto-read">
                  Memória: {gb(memory.available_bytes)} livres de {gb(memory.total_bytes)} · API usando{" "}
                  {gb(memory.process_memory_bytes)} · modelos carregados:{" "}
                  {memory.loaded_models.length === 0
                    ? "nenhum"
                    : memory.loaded_models.map((m) => `${m.name} (${m.device})`).join(", ")}
                </p>
                <p className="ditto-read">
                  Para trocar de perfil, rode no terminal, na pasta do projeto:{" "}
                  <code>make memory-profile PROFILE={OTHER_PROFILE[memory.profile.name] ?? "low"}</code>. Depois
                  reinicie a API com <code>make up</code> ou <code>make up-local</code>.
                </p>
              </>
            )}
          </div>
        </section>

        <section className="ditto-sec">
          <div className="ditto-sec-head">
            <h2 className="ditto-h2">Chave do Gemini</h2>
            <p className="ditto-read">
              Usada pelo embedding e pelo modelo Gemini. Crie uma em aistudio.google.com/apikey.
            </p>
          </div>
          <div className="ditto-sec-body">
            <StatusTag
              status={keySet ? "done" : "idle"}
              label={keySet ? "Uma chave está configurada." : "Nenhuma chave configurada."}
            />
            <div className="ditto-row-actions" style={{ alignItems: "flex-end" }}>
              <PasswordInput
                label={keySet ? "Nova chave (substitui a atual)" : "Nova chave"}
                placeholder="cole a chave aqui"
                value={newKey}
                onChange={(e) => setNewKey(e.currentTarget.value)}
                w={380}
              />
              <Button onClick={saveKey} disabled={newKey.trim() === ""}>
                Salvar
              </Button>
              {keySaved && <Saved>Chave salva</Saved>}
            </div>
          </div>
        </section>

        <section className="ditto-sec">
          <div className="ditto-sec-head">
            <h2 className="ditto-h2">Modelos Ollama</h2>
            <p className="ditto-read">
              Cada linha vira uma opção de modelo nos experimentos e no chat. O identificador é o
              nome curto; o modelo é o nome no servidor Ollama.
            </p>
          </div>
          <div className="ditto-sec-body">
            {models.length === 0 && (
              <p className="ditto-read" style={{ margin: 0 }}>
                Nenhum modelo cadastrado.
              </p>
            )}
            {models.map((row, i) => (
              <div key={i} className="ditto-row-actions" style={{ alignItems: "flex-end" }}>
                <TextInput
                  label="Identificador"
                  placeholder="ex.: qwen"
                  value={row.id}
                  onChange={(e) => updateModel(i, "id", e.currentTarget.value)}
                  w={180}
                />
                <TextInput
                  label="Modelo"
                  placeholder="ex.: qwen2.5:3b-instruct"
                  value={row.model}
                  onChange={(e) => updateModel(i, "model", e.currentTarget.value)}
                  style={{ flex: "1 1 240px" }}
                />
                <Button variant="subtle" onClick={() => removeModel(i)} aria-label={`Remover modelo ${row.id || i + 1}`}>
                  Remover
                </Button>
              </div>
            ))}
            <div className="ditto-row-actions">
              <Button variant="default" onClick={addModel}>
                Adicionar modelo
              </Button>
              <Button onClick={saveModels}>Salvar modelos</Button>
              {modelsSaved && <Saved>Modelos salvos</Saved>}
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
