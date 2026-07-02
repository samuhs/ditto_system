import { Alert, Button, Group, Select, Stack, Tabs, Text, Textarea } from "@mantine/core";
import {
  Background,
  Controls,
  ReactFlow,
  type Edge,
  type Node,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useEffect, useMemo, useState } from "react";

import {
  getFlow,
  getPersona,
  getPersonas,
  saveFlowPrompt,
  savePersona,
} from "../api/client";
import type { FlowNode, FlowSpec } from "../api/types";
import { PageHeader } from "../components/PageHeader";

function toReactFlow(spec: FlowSpec): { nodes: Node[]; edges: Edge[] } {
  const nodes: Node[] = spec.nodes.map((n, i) => ({
    id: n.id,
    position: { x: (i % 2) * 240, y: i * 110 },
    data: { label: `${n.label}` },
    style: {
      border: "1px solid var(--stroke-strong)",
      background: "var(--surface-strong)",
      color: "var(--text-hi)",
      borderRadius: 12,
      padding: 8,
      fontSize: 12,
    },
  }));
  const edges: Edge[] = spec.edges.map((e, i) => ({
    id: `e${i}`,
    source: e.source,
    target: e.target,
    label: e.label || undefined,
  }));
  return { nodes, edges };
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
    getFlow().then(setSpec).catch((e) => setError(e instanceof Error ? e.message : String(e)));
    getPersonas()
      .then((p) => {
        setPersonas(p.personas);
        if (p.personas.length > 0) setPersonaName(p.personas[0]);
      })
      .catch((e) => setError(String(e)));
  }, []);

  useEffect(() => {
    if (!personaName) return;
    getPersona(personaName).then((p) => setPersonaText(p.text)).catch((e) => setError(String(e)));
  }, [personaName]);

  const graph = useMemo(() => (spec ? toReactFlow(spec) : { nodes: [], edges: [] }), [spec]);

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
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  async function doSavePersona() {
    if (!personaName) return;
    setError(null);
    try {
      await savePersona(personaName, personaText);
      setPersonaSaved(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div>
      <PageHeader
        eyebrow="Passo 04 · Conversar"
        title="Agente"
        subtitle="Visualize o fluxo do agente conversacional e edite o prompt de cada etapa, ou ajuste as personas."
      />

      {error && (
        <Alert color="red" variant="light" title="Erro" mb="md" radius="lg" maw={860}>
          {error}
        </Alert>
      )}

      <Tabs defaultValue="flow">
        <Tabs.List>
          <Tabs.Tab value="flow">Fluxo do agente</Tabs.Tab>
          <Tabs.Tab value="personas">Personas</Tabs.Tab>
        </Tabs.List>

        <Tabs.Panel value="flow" pt="md">
          <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
            <div style={{ flex: "1 1 480px", height: 460 }} className="ditto-glass">
              <ReactFlow
                nodes={graph.nodes}
                edges={graph.edges}
                onNodeClick={(_e, node) => pickNode(node.id)}
                fitView
              >
                <Background />
                <Controls />
              </ReactFlow>
            </div>
            <div style={{ flex: "1 1 320px" }}>
              {!selected && <Text c="dimmed" size="sm">Clique num nó para ver/editar o prompt.</Text>}
              {selected && selected.type === "rag" && (
                <Alert color="violet" variant="light" radius="lg" title={selected.label}>
                  {selected.description} O prompt depende da técnica escolhida na config — edite em Prompts.
                </Alert>
              )}
              {selected && selected.type === "prompt" && (
                <Stack gap="sm">
                  <Text fw={700}>{selected.label}</Text>
                  <Text size="xs" c="dimmed">{selected.description}</Text>
                  <Textarea
                    autosize
                    minRows={6}
                    value={promptDraft}
                    onChange={(e) => setPromptDraft(e.currentTarget.value)}
                    styles={{ input: { fontFamily: "var(--font-mono)", fontSize: "0.82rem" } }}
                  />
                  <Text size="xs" c="dimmed">
                    Placeholders obrigatórios: {(selected.required_placeholders ?? []).map((p) => `{${p}}`).join(", ")}
                  </Text>
                  <Group>
                    <Button size="xs" variant="light" color="violet" onClick={savePrompt}>Salvar prompt</Button>
                    {saved && <Text size="xs" c="#07f285">Prompt salvo</Text>}
                  </Group>
                </Stack>
              )}
            </div>
          </div>
        </Tabs.Panel>

        <Tabs.Panel value="personas" pt="md">
          <Stack gap="sm" maw={760}>
            <Select
              label="Persona"
              data={personas}
              value={personaName}
              onChange={(v) => { setPersonaName(v); setPersonaSaved(false); }}
              placeholder="Selecione uma persona"
            />
            {personaName && (
              <>
                <Textarea
                  autosize
                  minRows={8}
                  value={personaText}
                  onChange={(e) => { setPersonaText(e.currentTarget.value); setPersonaSaved(false); }}
                  styles={{ input: { fontFamily: "var(--font-mono)", fontSize: "0.82rem" } }}
                />
                <Group>
                  <Button size="xs" variant="light" color="violet" onClick={doSavePersona}>Salvar persona</Button>
                  {personaSaved && <Text size="xs" c="#07f285">Persona salva</Text>}
                </Group>
              </>
            )}
          </Stack>
        </Tabs.Panel>
      </Tabs>
    </div>
  );
}
