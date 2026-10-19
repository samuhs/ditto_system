import { Button, Checkbox, Group, NumberInput, PasswordInput, Select, Textarea, TextInput } from "@mantine/core";
import { useEffect, useState } from "react";

import { deleteLlmProvider, listLlmProviders, saveLlmProvider, testLlmProvider } from "../api/client";
import type { LlmProvider, LlmProviderTest } from "../api/types";
import { Errata, Saved, errorText } from "./Notice";
import { StatusTag } from "./StatusTag";

const KIND_OPTIONS = [
  { value: "custom", label: "Custom (URL compatível com OpenAI: OpenRouter, vLLM, DeepSeek, GLM...)" },
  { value: "openai", label: "openai" },
  { value: "google_genai", label: "google_genai" },
  { value: "anthropic", label: "anthropic" },
  { value: "mistralai", label: "mistralai" },
  { value: "groq", label: "groq" },
];

interface Form {
  id: string;
  kind: string;
  base_url: string;
  api_key: string;
  api_key_env: string;
  models: string;
  params: string;
  local: boolean;
  rpm: number | null;
}

const EMPTY: Form = {
  id: "", kind: "custom", base_url: "", api_key: "", api_key_env: "", models: "", params: "{}", local: false, rpm: null,
};

function toForm(p: LlmProvider): Form {
  return {
    id: p.id, kind: p.kind, base_url: p.base_url ?? "", api_key: "", api_key_env: p.api_key_env ?? "",
    models: p.models.join("\n"), params: JSON.stringify(p.params, null, 2), local: p.local,
    rpm: p.requests_per_minute,
  };
}

/** Configured LLM providers: any model behind an OpenAI-compatible URL or a LangChain provider. */
export function LlmProvidersSection() {
  const [providers, setProviders] = useState<LlmProvider[]>([]);
  const [form, setForm] = useState<Form>(EMPTY);
  const [editing, setEditing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [testModel, setTestModel] = useState<string | null>(null);
  const [test, setTest] = useState<LlmProviderTest | null>(null);
  const [testing, setTesting] = useState(false);

  function reload() {
    Promise.resolve(listLlmProviders())
      .then((list) => setProviders(list ?? []))
      .catch((e) => setError(errorText(e)));
  }

  useEffect(reload, []);

  const set = (patch: Partial<Form>) => setForm((f) => ({ ...f, ...patch }));

  function edit(p: LlmProvider) {
    setForm(toForm(p));
    setEditing(true);
    setSaved(false);
    setTest(null);
    setTestModel(p.models[0] ?? null);
  }

  async function save() {
    setError(null);
    setSaved(false);
    let params: Record<string, unknown>;
    try {
      params = form.params.trim() ? JSON.parse(form.params) : {};
    } catch {
      setError("Parâmetros extras precisam ser um JSON válido");
      return;
    }
    try {
      const p = await saveLlmProvider(form.id.trim(), {
        kind: form.kind,
        base_url: form.base_url.trim() || null,
        // Blank keeps the stored key when editing.
        api_key: form.api_key ? form.api_key : editing ? null : "",
        api_key_env: form.api_key_env.trim() || null,
        models: form.models.split("\n").map((m) => m.trim()).filter(Boolean),
        params,
        local: form.local,
        requests_per_minute: form.rpm,
      });
      setSaved(true);
      setEditing(true);
      setForm(toForm(p));
      setTestModel(p.models[0] ?? null);
      reload();
    } catch (e) {
      setError(errorText(e));
    }
  }

  async function remove(id: string) {
    setError(null);
    try {
      await deleteLlmProvider(id);
      if (form.id === id) {
        setForm(EMPTY);
        setEditing(false);
      }
      reload();
    } catch (e) {
      setError(errorText(e));
    }
  }

  async function runTest() {
    if (!testModel) return;
    setTesting(true);
    setTest(null);
    try {
      setTest(await testLlmProvider(form.id, testModel));
    } catch (e) {
      setTest({ ok: false, error: errorText(e) });
    } finally {
      setTesting(false);
    }
  }

  const models = form.models.split("\n").map((m) => m.trim()).filter(Boolean);

  return (
    <section className="ditto-sec">
      <div className="ditto-sec-head">
        <h2 className="ditto-h2">Provedores de LLM</h2>
        <p className="ditto-read">
          Qualquer modelo, em qualquer provedor, sem código específico: informe a URL (provedor custom compatível com
          OpenAI) ou o nome do provedor no LangChain, a chave e os modelos. Nos experimentos, o modelo aparece como{" "}
          <code>provedor::modelo</code>.
        </p>
      </div>
      <div className="ditto-sec-body">
        {error && <Errata title="O provedor não foi salvo">{error}</Errata>}

        <ul className="ditto-read" style={{ margin: 0, paddingLeft: 18 }}>
          {providers.map((p) => (
            <li key={p.id} style={{ marginBottom: 6 }}>
              <strong>{p.id}</strong> · {p.kind}
              {p.base_url ? ` · ${p.base_url}` : ""} · {p.local ? "local" : "remoto"} ·{" "}
              {p.api_key_set ? "chave configurada" : "sem chave"}
              {p.models.length > 0 ? ` · ${p.models.length} modelo(s)` : ""}
              {p.builtin ? (
                " · embutido"
              ) : (
                <>
                  {" "}
                  <Button variant="subtle" size="compact-xs" onClick={() => edit(p)}>
                    Editar
                  </Button>
                  <Button variant="subtle" color="red" size="compact-xs" onClick={() => remove(p.id)}>
                    Remover
                  </Button>
                </>
              )}
            </li>
          ))}
        </ul>

        <Group align="flex-end" gap="sm">
          <TextInput
            label="Id do provedor"
            description="Letras minúsculas, números e hífen"
            placeholder="openrouter"
            value={form.id}
            onChange={(e) => set({ id: e.currentTarget.value })}
            disabled={editing}
            w={200}
          />
          <Select
            label="Tipo"
            data={KIND_OPTIONS}
            value={form.kind}
            onChange={(v) => set({ kind: v ?? "custom" })}
            searchable
            w={420}
          />
        </Group>
        <TextInput
          label="Base URL"
          description="Obrigatória no tipo custom; opcional nos outros"
          placeholder="https://openrouter.ai/api/v1"
          value={form.base_url}
          onChange={(e) => set({ base_url: e.currentTarget.value })}
          w={620}
        />
        <Group align="flex-end" gap="sm">
          <PasswordInput
            label={editing ? "Nova chave de API (vazio mantém a atual)" : "Chave de API"}
            value={form.api_key}
            onChange={(e) => set({ api_key: e.currentTarget.value })}
            w={300}
          />
          <TextInput
            label="Ou variável de ambiente com a chave"
            placeholder="OPENROUTER_API_KEY"
            value={form.api_key_env}
            onChange={(e) => set({ api_key_env: e.currentTarget.value })}
            w={300}
          />
        </Group>
        <Textarea
          label="Modelos (um por linha)"
          placeholder={"qwen/qwen3.5-9b\nz-ai/glm-5.3-flash"}
          autosize
          minRows={3}
          value={form.models}
          onChange={(e) => set({ models: e.currentTarget.value })}
          w={620}
        />
        <Textarea
          label="Parâmetros extras (JSON, repassados ao LangChain)"
          description='Ex.: {"extra_body": {"reasoning": {"enabled": false}}} para desligar o raciocínio'
          autosize
          minRows={2}
          value={form.params}
          onChange={(e) => set({ params: e.currentTarget.value })}
          w={620}
          styles={{ input: { fontFamily: "monospace" } }}
        />
        <NumberInput
          label="Limite de requisições por minuto"
          description="Vazio: sem limite. Ex.: 18 para uma conta nova do OpenRouter limitada a 20/min"
          min={1}
          value={form.rpm ?? ""}
          onChange={(v) => set({ rpm: typeof v === "number" && v > 0 ? v : null })}
          w={300}
        />
        <Checkbox
          label="Roda nesta máquina (entra na política de memória e GPU)"
          checked={form.local}
          onChange={(e) => set({ local: e.currentTarget.checked })}
        />
        <div className="ditto-row-actions">
          <Button onClick={save} disabled={form.id.trim() === "" || form.kind.trim() === ""}>
            Salvar provedor
          </Button>
          {editing && (
            <Button
              variant="default"
              onClick={() => {
                setForm(EMPTY);
                setEditing(false);
                setTest(null);
              }}
            >
              Novo provedor
            </Button>
          )}
          {saved && <Saved>Provedor salvo</Saved>}
        </div>

        {editing && models.length > 0 && (
          <div className="ditto-row-actions" style={{ alignItems: "flex-end" }}>
            <Select label="Testar o modelo" data={models} value={testModel} onChange={setTestModel} w={300} />
            <Button variant="default" onClick={runTest} loading={testing} disabled={!testModel}>
              Testar
            </Button>
            {test &&
              (test.ok ? (
                <StatusTag
                  status="done"
                  label={`Respondeu "${test.answer}" em ${test.latency_ms} ms · ${test.usage?.input_tokens ?? 0} tokens de entrada, ${test.usage?.output_tokens ?? 0} de saída, ${test.usage?.reasoning_tokens ?? 0} de raciocínio`}
                />
              ) : (
                <StatusTag status="failed" label={`Falhou: ${test.error}`} />
              ))}
          </div>
        )}
      </div>
    </section>
  );
}
