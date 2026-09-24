import { Button, Select, Tabs, Textarea } from "@mantine/core";
import { Background, Controls, ReactFlow, type Edge, type Node } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useEffect, useMemo, useState } from "react";

import { getFlow, getPersona, getPersonas, saveFlowPrompt, savePersona } from "../api/client";
import type { FlowNode, FlowSpec } from "../api/types";
import { Errata, Note, Saved, errorText } from "../components/Notice";
import { PageHeader } from "../components/PageHeader";

function toReactFlow(spec: FlowSpec, selectedId: string | null): { nodes: Node[]; edges: Edge[] } {
  const nodes: Node[] = spec.nodes.map((n, i) => ({
    id: n.id,
    position: { x: (i % 2) * 240, y: i * 110 },
    data: { label: n.label },
    selected: n.id === selectedId,
  }));
  const edges: Edge[] = spec.edges.map((e, i) => ({
    id: `e${i}`,
    source: e.source,
    target: e.target,
    label: e.label || undefined,
  }));
  return { nodes, edges };
}

function Placeholders({ names }: { names: string[] }) {
  if (names.length === 0) return null;
  return (
    <div className="ditto-placeholders">
      Precisa conter:
      {names.map((p) => (
        <code key={p}>{`{${p}}`}</code>
      ))}
    </div>
  );
}

export function AgentePage() {
  const [spec, setSpec] = useState<FlowSpec | null>(null);
  const [selected, setSelected] = useState<FlowNode | null>(null);
  const [promptDraft, setPromptDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const [personas, setPersonas] = useState<string[]>([]);
  const [personaName, setPersonaName] = useState<string | null>(null);
  const [personaText, setPersonaText] = useState("");
  const [personaSaved, setPersonaSaved] = useState(false);

  useEffect(() => {
    getFlow().then(setSpec).catch((e) => setError(errorText(e)));
    getPersonas()
      .then((p) => {
        setPersonas(p.personas);
        if (p.personas.length > 0) setPersonaName(p.personas[0]);
      })
      .catch((e) => setError(errorText(e)));
  }, []);

  useEffect(() => {
    if (!personaName) return;
    getPersona(personaName)
      .then((p) => setPersonaText(p.text))
      .catch((e) => setError(errorText(e)));
  }, [personaName]);

  const graph = useMemo(
    () => (spec ? toReactFlow(spec, selected?.id ?? null) : { nodes: [], edges: [] }),
    [spec, selected],
  );

  function pickNode(id: string) {
    const node = spec?.nodes.find((n) => n.id === id) ?? null;
    setSelected(node);
    setSaved(false);
    setPromptDraft(node?.prompt ?? "");
  }

  async function savePrompt() {
    if (!selected || selected.type !== "prompt") return;
    setError(null);
    try {
      await saveFlowPrompt(selected.id, promptDraft);
      setSaved(true);
      setSpec((s) => s && { ...s, nodes: s.nodes.map((n) => (n.id === selected.id ? { ...n, prompt: promptDraft } : n)) });
    } catch (e) {
      setError(errorText(e));
    }
  }

  async function doSavePersona() {
    if (!personaName) return;
    setError(null);
    try {
      await savePersona(personaName, personaText);
      setPersonaSaved(true);
    } catch (e) {
      setError(errorText(e));
    }
  }

  return (
    <div>
      <PageHeader
        title="Agente e personas"
        lede="O caminho que cada mensagem percorre no agente de conversa. Clique numa etapa para ler e editar o prompt dela."
      />

      {error && (
        <div style={{ marginBottom: 20 }}>
          <Errata title="Algo não funcionou">{error}. Tente de novo.</Errata>
        </div>
      )}

      <Tabs defaultValue="flow" keepMounted={false}>
        <Tabs.List mb="lg">
          <Tabs.Tab value="flow">Fluxo do agente</Tabs.Tab>
          <Tabs.Tab value="personas">Personas</Tabs.Tab>
        </Tabs.List>

        <Tabs.Panel value="flow">
          <div className="ditto-flow">
            <div className="ditto-flow-canvas">
              <ReactFlow
                nodes={graph.nodes}
                edges={graph.edges}
                onNodeClick={(_e, node) => pickNode(node.id)}
                nodesDraggable={false}
                fitView
                proOptions={{ hideAttribution: true }}
              >
                <Background gap={24} color="var(--line)" />
                <Controls showInteractive={false} />
              </ReactFlow>
            </div>
            <div>
              {!selected && (
                <Note title="Nenhuma etapa escolhida">
                  Clique numa etapa do fluxo para ver o que ela faz e o prompt que ela usa.
                </Note>
              )}
              {selected && selected.type === "rag" && (
                <Note title={selected.label}>
                  {selected.description} O prompt desta etapa depende da técnica de RAG da
                  configuração de chat; edite em Prompts.
                </Note>
              )}
              {selected && selected.type === "prompt" && (
                <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                  <h2 className="ditto-h2">{selected.label}</h2>
                  <p className="ditto-read" style={{ margin: 0 }}>
                    {selected.description}
                  </p>
                  <Textarea
                    label="Prompt"
                    autosize
                    minRows={8}
                    value={promptDraft}
                    onChange={(e) => {
                      setPromptDraft(e.currentTarget.value);
                      setSaved(false);
                    }}
                  />
                  <Placeholders names={selected.required_placeholders ?? []} />
                  <div className="ditto-row-actions">
                    <Button onClick={savePrompt}>Salvar prompt</Button>
                    {saved && <Saved>Prompt salvo</Saved>}
                  </div>
                </div>
              )}
            </div>
          </div>
        </Tabs.Panel>

        <Tabs.Panel value="personas">
          <div style={{ display: "flex", flexDirection: "column", gap: 14, maxWidth: 780 }}>
            <p className="ditto-read" style={{ margin: 0 }}>
              A persona define o tom e o papel do agente, como “guia de viagem”. Ela entra no
              prompt de todas as respostas.
            </p>
            <Select
              label="Persona"
              data={personas}
              value={personaName}
              onChange={(v) => {
                setPersonaName(v);
                setPersonaSaved(false);
              }}
              placeholder="Escolha uma persona"
              maw={320}
              allowDeselect={false}
            />
            {personaName && (
              <>
                <Textarea
                  label="Texto da persona"
                  autosize
                  minRows={10}
                  value={personaText}
                  onChange={(e) => {
                    setPersonaText(e.currentTarget.value);
                    setPersonaSaved(false);
                  }}
                />
                <div className="ditto-row-actions">
                  <Button onClick={doSavePersona}>Salvar persona</Button>
                  {personaSaved && <Saved>Persona salva</Saved>}
                </div>
              </>
            )}
          </div>
        </Tabs.Panel>
      </Tabs>
    </div>
  );
}
