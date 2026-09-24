import { Button, Tabs, Textarea } from "@mantine/core";
import { useEffect, useState } from "react";

import { getPrompts, savePrompt } from "../api/client";
import type { PromptsResponse } from "../api/types";
import { Errata, Saved, errorText } from "../components/Notice";
import { PageHeader } from "../components/PageHeader";
import { techniqueName, term } from "../glossary";

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
      .catch((e) => setError(errorText(e)));
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
      setSaveError((s) => ({ ...s, [id]: errorText(e) }));
    } finally {
      setSavingKey(null);
    }
  }

  const techniques = prompts ? Object.keys(prompts) : [];

  return (
    <div>
      <PageHeader
        title="Prompts"
        lede="Os textos que cada técnica de RAG envia ao modelo. Mudanças valem para os próximos experimentos; os já rodados guardam o prompt que usaram."
      />

      {error && (
        <Errata title="Não foi possível carregar os prompts">{error}. Recarregue a página.</Errata>
      )}

      {prompts && techniques.length > 0 && (
        <Tabs defaultValue={techniques[0]} keepMounted={false}>
          <Tabs.List mb="lg">
            {techniques.map((tech) => (
              <Tabs.Tab key={tech} value={tech}>
                {techniqueName(tech)}
              </Tabs.Tab>
            ))}
          </Tabs.List>

          {techniques.map((tech) => (
            <Tabs.Panel key={tech} value={tech}>
              {term("rag", tech).description && (
                <p className="ditto-read" style={{ margin: "0 0 8px", maxWidth: "62ch" }}>
                  {term("rag", tech).description}
                </p>
              )}
              {Object.entries(prompts[tech]).map(([key, info]) => {
                const id = `${tech}/${key}`;
                const changed = drafts[id] !== info.text && savedKey !== id;
                return (
                  <section key={id} className="ditto-sec ditto-sec-narrow">
                    <div className="ditto-sec-head">
                      <h2 className="ditto-h2">
                        <span className="ditto-mono">{key}</span>
                      </h2>
                      {info.required_placeholders.length > 0 && (
                        <p className="ditto-read">
                          Precisa conter{" "}
                          {info.required_placeholders.map((p, i) => (
                            <span key={p}>
                              {i > 0 && ", "}
                              <code className="ditto-mono">{`{${p}}`}</code>
                            </span>
                          ))}
                          . O Ditto troca cada um pelo valor real.
                        </p>
                      )}
                    </div>
                    <div className="ditto-sec-body">
                      <Textarea
                        aria-label={`Prompt ${key} de ${techniqueName(tech)}`}
                        autosize
                        minRows={5}
                        value={drafts[id] ?? ""}
                        error={saveError[id] ? `${saveError[id]}. Corrija o texto e salve de novo.` : undefined}
                        onChange={(e) => {
                          const value = e.currentTarget.value;
                          setDrafts((d) => ({ ...d, [id]: value }));
                          if (savedKey === id) setSavedKey(null);
                        }}
                      />
                      <div className="ditto-row-actions">
                        <Button
                          variant={changed ? "filled" : "default"}
                          loading={savingKey === id}
                          onClick={() => handleSave(tech, key)}
                        >
                          Salvar
                        </Button>
                        {changed && <span className="ditto-muted" style={{ fontSize: 14 }}>Alterações não salvas</span>}
                        {savedKey === id && <Saved>Prompt salvo</Saved>}
                      </div>
                    </div>
                  </section>
                );
              })}
            </Tabs.Panel>
          ))}
        </Tabs>
      )}
    </div>
  );
}
