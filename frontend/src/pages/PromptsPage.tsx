import { Alert, Button, Group, Stack, Text, Textarea } from "@mantine/core";
import { useEffect, useState } from "react";

import { getPrompts, savePrompt } from "../api/client";
import type { PromptsResponse } from "../api/types";
import { PageHeader } from "../components/PageHeader";

export function PromptsPage() {
  const [prompts, setPrompts] = useState<PromptsResponse | null>(null);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [savingKey, setSavingKey] = useState<string | null>(null);
  const [savedKey, setSavedKey] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<Record<string, string>>({});

  useEffect(() => {
    getPrompts()
      .then((data) => {
        setPrompts(data);
        const initial: Record<string, string> = {};
        for (const [tech, keys] of Object.entries(data)) {
          for (const [key, info] of Object.entries(keys)) {
            initial[`${tech}/${key}`] = info.text;
          }
        }
        setDrafts(initial);
      })
      .catch((e) => setError(String(e)));
  }, []);

  async function handleSave(tech: string, key: string) {
    const id = `${tech}/${key}`;
    setSavingKey(id);
    setSavedKey(null);
    setSaveError((s) => ({ ...s, [id]: "" }));
    try {
      await savePrompt(tech, key, drafts[id]);
      setSavedKey(id);
    } catch (e) {
      setSaveError((s) => ({ ...s, [id]: String(e) }));
    } finally {
      setSavingKey(null);
    }
  }

  return (
    <div>
      <PageHeader
        eyebrow="Configuração"
        title="Prompts"
        subtitle="Edite os templates usados por cada técnica. Alterações valem para os próximos experimentos — experimentos já rodados mantêm o snapshot que usaram."
      />

      {error && (
        <Alert color="red" variant="light" title="Erro ao carregar" radius="lg" maw={820}>
          {error}
        </Alert>
      )}

      {prompts &&
        Object.entries(prompts).map(([tech, keys]) => (
          <div key={tech} className="ditto-glass" style={{ padding: 24, maxWidth: 820, marginBottom: 20 }}>
            <Text className="ditto-eyebrow" mb={14}>
              {tech}
            </Text>
            <Stack gap="lg">
              {Object.entries(keys).map(([key, info]) => {
                const id = `${tech}/${key}`;
                return (
                  <div key={id}>
                    <Text fw={700} size="sm" mb={6}>
                      {key}
                    </Text>
                    <Textarea
                      autosize
                      minRows={4}
                      value={drafts[id] ?? ""}
                      onChange={(e) => {
                        const value = e.currentTarget.value;
                        setDrafts((d) => ({ ...d, [id]: value }));
                      }}
                      styles={{ input: { fontFamily: "var(--font-mono)", fontSize: "0.82rem" } }}
                    />
                    <Text size="xs" c="dimmed" mt={6}>
                      Placeholders obrigatórios: {info.required_placeholders.map((p) => `{${p}}`).join(", ")}
                    </Text>
                    {saveError[id] && (
                      <Text size="xs" c="red.4" mt={4}>
                        {saveError[id]}
                      </Text>
                    )}
                    <Group mt={8}>
                      <Button
                        size="xs"
                        variant="light"
                        color="violet"
                        loading={savingKey === id}
                        onClick={() => handleSave(tech, key)}
                      >
                        Salvar
                      </Button>
                      {savedKey === id && (
                        <Text size="xs" c="#07f285">
                          Prompt salvo
                        </Text>
                      )}
                    </Group>
                  </div>
                );
              })}
            </Stack>
          </div>
        ))}
    </div>
  );
}
