import { Alert, Button, Group, PasswordInput, Stack, Text, TextInput } from "@mantine/core";
import { useEffect, useState } from "react";

import { getSettings, saveGeminiKey, saveOllamaModels } from "../api/client";
import type { OllamaModel } from "../api/types";
import { PageHeader } from "../components/PageHeader";

export function SettingsPage() {
  const [keySet, setKeySet] = useState(false);
  const [newKey, setNewKey] = useState("");
  const [models, setModels] = useState<OllamaModel[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [keySaved, setKeySaved] = useState(false);
  const [modelsSaved, setModelsSaved] = useState(false);

  useEffect(() => {
    getSettings()
      .then((s) => {
        setKeySet(s.gemini_api_key_set);
        setModels(s.ollama_models);
      })
      .catch((e) => setError(String(e)));
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
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  function addModel() {
    setModels((m) => [...m, { id: "", model: "" }]);
  }
  function updateModel(i: number, field: "id" | "model", value: string) {
    setModels((m) => m.map((row, idx) => (idx === i ? { ...row, [field]: value } : row)));
  }
  function removeModel(i: number) {
    setModels((m) => m.filter((_, idx) => idx !== i));
  }

  async function saveModels() {
    setError(null);
    setModelsSaved(false);
    try {
      const r = await saveOllamaModels(models);
      setModels(r.ollama_models);
      setModelsSaved(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div>
      <PageHeader
        eyebrow="Sistema"
        title="Configurações"
        subtitle="Variáveis gerais do sistema. Alterações valem para novas execuções."
      />

      {error && (
        <Alert color="red" variant="light" title="Erro" mb="lg" radius="lg" maw={640}>
          {error}
        </Alert>
      )}

      <div className="ditto-glass" style={{ padding: 24, maxWidth: 640, marginBottom: 24 }}>
        <Text fw={700} mb={4}>
          Chave do Gemini
        </Text>
        <Text size="sm" c="dimmed" mb="md">
          {keySet ? "Uma chave está configurada." : "Nenhuma chave configurada."}
        </Text>
        <Group align="flex-end" gap="sm">
          <PasswordInput
            label="Nova chave"
            placeholder="cole a chave aqui"
            value={newKey}
            onChange={(e) => setNewKey(e.currentTarget.value)}
            style={{ flex: 1 }}
          />
          <Button color="violet" onClick={saveKey} disabled={newKey.trim() === ""}>
            Salvar
          </Button>
          {keySaved && (
            <Text size="sm" c="#07f285">
              Salva
            </Text>
          )}
        </Group>
      </div>

      <div className="ditto-glass" style={{ padding: 24, maxWidth: 640 }}>
        <Text fw={700} mb={4}>
          Modelos Ollama
        </Text>
        <Text size="sm" c="dimmed" mb="md">
          Cada identificador vira uma opção de LLM (ex.: qwen → qwen2.5:3b-instruct).
        </Text>
        <Stack gap="xs">
          {models.map((row, i) => (
            <Group key={i} gap="sm" align="flex-end">
              <TextInput
                label={i === 0 ? "Identificador" : undefined}
                placeholder="qwen"
                value={row.id}
                onChange={(e) => updateModel(i, "id", e.currentTarget.value)}
              />
              <TextInput
                label={i === 0 ? "Modelo" : undefined}
                placeholder="qwen2.5:3b-instruct"
                value={row.model}
                onChange={(e) => updateModel(i, "model", e.currentTarget.value)}
                style={{ flex: 1 }}
              />
              <Button variant="subtle" color="gray" onClick={() => removeModel(i)}>
                Remover
              </Button>
            </Group>
          ))}
        </Stack>
        <Group mt="md" gap="sm">
          <Button variant="light" color="gray" onClick={addModel}>
            Adicionar modelo
          </Button>
          <Button color="violet" onClick={saveModels}>
            Salvar modelos
          </Button>
          {modelsSaved && (
            <Text size="sm" c="#07f285">
              Salvos
            </Text>
          )}
        </Group>
      </div>
    </div>
  );
}
