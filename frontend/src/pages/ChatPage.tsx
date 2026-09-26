import { Button, Loader, Select, Textarea } from "@mantine/core";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { listChatConfigs, saveDialogue, sendChat } from "../api/client";
import type { ChatConfig, ChatMessage, TurnDifficulty } from "../api/types";
import { SIGNAL_LABELS, formatSignal } from "../components/DifficultyPanel";
import { Errata, Saved, errorText } from "../components/Notice";
import { PageHeader } from "../components/PageHeader";
import { ArrowIcon } from "../components/icons";

export function ChatPage() {
  const [configs, setConfigs] = useState<ChatConfig[] | null>(null);
  const [configId, setConfigId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  // Per assistant reply, by message index (not sent back to the API): what was
  // searched and the difficulty signals.
  const [turns, setTurns] = useState<Record<number, { query?: string | null; difficulty?: TurnDifficulty }>>({});
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<{ title: string; text: string } | null>(null);
  const endRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    listChatConfigs()
      .then((cs) => {
        setConfigs(cs);
        if (cs.length > 0) setConfigId(String(cs[0].id));
      })
      .catch((e) => setError({ title: "Não foi possível carregar as configurações", text: `${errorText(e)}. Recarregue a página.` }));
  }, []);

  useEffect(() => {
    if (endRef.current && typeof endRef.current.scrollIntoView === "function") {
      endRef.current.scrollIntoView({ block: "end" });
    }
  }, [messages, sending]);

  function newConversation() {
    setMessages([]);
    setTurns({});
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
      setTurns((t) => ({ ...t, [next.length]: { query: turn.query, difficulty: turn.difficulty } }));
    } catch (e) {
      setError({ title: "A mensagem não foi respondida", text: `${errorText(e)}. Tente enviar de novo.` });
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
      setError({ title: "O diálogo não foi salvo", text: `${errorText(e)}. Tente salvar de novo.` });
    }
  }

  const current = configs?.find((c) => String(c.id) === configId);

  return (
    <div>
      <PageHeader
        title="Conversa"
        lede="Converse com os seus documentos usando uma configuração salva. Ao final, salve o diálogo para dar uma nota a ele."
      />

      {configs !== null && configs.length === 0 && (
        <div className="ditto-empty">
          <h2 className="ditto-h2">Nenhuma configuração de chat</h2>
          <p>
            Para conversar, escolha antes qual base, técnica e modelo o agente vai usar. Isso fica
            salvo numa configuração.
          </p>
          <Button component={Link} to="/chat-configs" rightSection={<ArrowIcon />}>
            Criar configuração
          </Button>
        </div>
      )}

      {configs !== null && configs.length > 0 && (
        <>
          <div className="ditto-toolbar">
            <Select
              label="Configuração"
              data={configs.map((c) => ({ value: String(c.id), label: c.name }))}
              value={configId}
              onChange={(v) => {
                setConfigId(v);
                newConversation();
              }}
              allowDeselect={false}
              w={300}
              description={current ? `${current.base} · ${current.rag} · ${current.llm}` : undefined}
            />
            <Button variant="default" onClick={newConversation} disabled={messages.length === 0}>
              Nova conversa
            </Button>
            <Button variant="default" disabled={messages.length === 0 || sending} onClick={save}>
              Salvar diálogo
            </Button>
            {saved && (
              <Saved>
                Diálogo salvo. <Link to="/dialogues">Dar nota</Link>
              </Saved>
            )}
          </div>

          <div className="ditto-chat" aria-live="polite">
            {messages.length === 0 && (
              <p className="ditto-chat-empty">
                Faça uma pergunta sobre os documentos da base “{current?.base ?? ""}”.
              </p>
            )}
            {messages.map((m, i) => (
              <div key={i} className="ditto-msg" data-role={m.role}>
                <span className="ditto-msg-who">{m.role === "user" ? "Você" : "Ditto"}</span>
                <span className="ditto-msg-text">{m.content}</span>
                {turns[i]?.query && (
                  <span className="ditto-msg-query">
                    Buscou nos documentos: <q>{turns[i].query}</q>
                  </span>
                )}
                {turns[i]?.difficulty && <TurnSignals difficulty={turns[i].difficulty!} />}
              </div>
            ))}
            {sending && (
              <div className="ditto-msg" data-role="assistant">
                <span className="ditto-msg-who">Ditto</span>
                <span className="ditto-msg-text">
                  <Loader size="sm" aria-label="Escrevendo resposta" />
                </span>
              </div>
            )}
            <div ref={endRef} />
          </div>

          <form
            className="ditto-composer"
            onSubmit={(e) => {
              e.preventDefault();
              send();
            }}
          >
            <Textarea
              label="Mensagem"
              placeholder="Sua mensagem… (Enter envia, Shift+Enter quebra a linha)"
              value={input}
              onChange={(e) => setInput(e.currentTarget.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  send();
                }
              }}
              autosize
              minRows={1}
              maxRows={6}
              disabled={!configId}
              styles={{ input: { fontFamily: "var(--font-ui)", fontSize: 15 } }}
            />
            <Button type="submit" loading={sending} disabled={!configId || input.trim() === ""} rightSection={<ArrowIcon />}>
              Enviar
            </Button>
          </form>
        </>
      )}

      {error && (
        <div style={{ marginTop: 16 }}>
          <Errata title={error.title}>{error.text}</Errata>
        </div>
      )}
    </div>
  );
}

/** Collapsed list of the difficulty signals measured for one reply. */
function TurnSignals({ difficulty }: { difficulty: TurnDifficulty }) {
  const entries = [...Object.entries(difficulty.question), ...Object.entries(difficulty.retrieval)];
  if (entries.length === 0) return null;
  return (
    <details className="ditto-msg-signals">
      <summary>Sinais de dificuldade</summary>
      <dl className="ditto-kv">
        {entries.map(([name, value]) => (
          <div key={name} style={{ display: "contents" }}>
            <dt>{SIGNAL_LABELS[name] ?? name}</dt>
            <dd>{formatSignal(name, value)}</dd>
          </div>
        ))}
      </dl>
    </details>
  );
}
