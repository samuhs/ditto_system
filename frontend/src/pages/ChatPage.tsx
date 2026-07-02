import { Alert, Button, Group, Loader, Select, Text, TextInput } from "@mantine/core";
import { useEffect, useRef, useState } from "react";

import { listChatConfigs, saveDialogue, sendChat } from "../api/client";
import type { ChatConfig, ChatMessage } from "../api/types";
import { PageHeader } from "../components/PageHeader";

export function ChatPage() {
  const [configs, setConfigs] = useState<ChatConfig[]>([]);
  const [configId, setConfigId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    listChatConfigs()
      .then((cs) => {
        setConfigs(cs);
        if (cs.length > 0) setConfigId(String(cs[0].id));
      })
      .catch((e) => setError(String(e)));
  }, []);

  useEffect(() => {
    if (endRef.current && typeof endRef.current.scrollIntoView === "function") {
      endRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages]);

  function newConversation() {
    setMessages([]);
    setSaved(false);
    setError(null);
  }

  async function send() {
    if (!configId || input.trim() === "" || sending) return;
    setError(null);
    setSaved(false);
    const next = [...messages, { role: "user" as const, content: input.trim() }];
    setMessages(next);
    setInput("");
    setSending(true);
    try {
      const turn = await sendChat(Number(configId), next);
      setMessages([...next, { role: "assistant", content: turn.reply }]);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSending(false);
    }
  }

  async function save() {
    if (!configId || messages.length === 0) return;
    try {
      await saveDialogue(Number(configId), messages);
      setSaved(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div>
      <PageHeader
        eyebrow="Passo 04 · Conversar"
        title="Conversa"
        subtitle="Escolha uma configuração e converse com o agente. Ao final, você pode salvar o diálogo para avaliação."
      />

      <Group mb="md" align="flex-end" gap="sm">
        <Select
          label="Configuração"
          data={configs.map((c) => ({ value: String(c.id), label: c.name }))}
          value={configId}
          onChange={setConfigId}
          w={280}
        />
        <Button variant="subtle" color="gray" size="sm" onClick={newConversation}>
          Nova conversa
        </Button>
        <Button
          variant="light"
          color="violet"
          size="sm"
          disabled={messages.length === 0}
          onClick={save}
        >
          Salvar diálogo
        </Button>
        {saved && <Text size="sm" c="#07f285">Diálogo salvo</Text>}
      </Group>

      <div className="ditto-glass ditto-chat-window">
        {messages.length === 0 && (
          <p className="ditto-empty">Sem mensagens ainda. Diga um "oi" para começar.</p>
        )}
        {messages.map((m, i) => (
          <div key={i} className="ditto-chat-msg" data-role={m.role}>
            <span className="ditto-chat-bubble">{m.content}</span>
          </div>
        ))}
        {sending && (
          <div className="ditto-chat-msg" data-role="assistant">
            <span className="ditto-chat-bubble"><Loader size="xs" color="#05dbf2" /></span>
          </div>
        )}
        <div ref={endRef} />
      </div>

      <Group mt="md" gap="sm">
        <TextInput
          placeholder="Sua mensagem…"
          value={input}
          onChange={(e) => setInput(e.currentTarget.value)}
          onKeyDown={(e) => { if (e.key === "Enter") send(); }}
          style={{ flex: 1 }}
          disabled={!configId}
        />
        <Button onClick={send} loading={sending} disabled={!configId}>
          Enviar
        </Button>
      </Group>

      {error && (
        <Alert color="red" variant="light" title="Erro" mt="md" radius="lg">
          {error}
        </Alert>
      )}
    </div>
  );
}
