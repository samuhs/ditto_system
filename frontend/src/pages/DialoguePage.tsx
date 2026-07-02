import { Alert, Button, Group, Loader, NumberInput, Text } from "@mantine/core";
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { getDialogue, saveDialogueRating } from "../api/client";
import type { DialogueDetail } from "../api/types";
import { PageHeader } from "../components/PageHeader";

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("pt-BR");
}

export function DialoguePage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [detail, setDetail] = useState<DialogueDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [rating, setRating] = useState<number | "">("");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    getDialogue(Number(id))
      .then((d) => {
        setDetail(d);
        setRating(d.rating ?? "");
        setLoading(false);
      })
      .catch((e) => {
        setError(String(e));
        setLoading(false);
      });
  }, [id]);

  async function save() {
    if (!id || rating === "") return;
    setSaving(true);
    setSaved(false);
    try {
      await saveDialogueRating(Number(id), Number(rating));
      setSaved(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }

  const snap = detail?.config_snapshot ?? {};

  return (
    <div>
      <Button
        variant="subtle"
        color="gray"
        size="xs"
        mb="md"
        onClick={() => navigate("/dialogues")}
      >
        ← Voltar aos diálogos
      </Button>

      <PageHeader
        eyebrow="Passo 05 · Avaliar"
        title="Diálogo"
        subtitle="Leia a conversa e atribua uma nota de 0 a 10."
      />

      {loading && (
        <div style={{ display: "flex", justifyContent: "center", padding: "48px 0" }}>
          <Loader size="md" color="#05dbf2" />
        </div>
      )}

      {error && (
        <Alert color="red" variant="light" title="Erro" radius="lg" maw={760}>
          {error}
        </Alert>
      )}

      {detail && !loading && (
        <>
          <div style={{ marginBottom: "1.5rem" }}>
            <Group gap="xs" mb="xs" align="center">
              <Text fw={600} fz="lg">
                {snap.name ?? "Configuração sem nome"}
              </Text>
              <Text size="sm" c="dimmed">
                {formatDate(detail.created_at)}
              </Text>
            </Group>
            <Group gap="xs">
              <span className="ditto-chip" style={{ color: "#05dbf2" }}>
                persona: {snap.persona ?? "—"}
              </span>
              <span className="ditto-chip" style={{ color: "#f2ec91" }}>
                base: {snap.base ?? "—"}
              </span>
              <span className="ditto-chip" style={{ color: "#f2ec91" }}>
                corte: {snap.chunking ?? "—"}
              </span>
              <span className="ditto-chip" style={{ color: "#f2ec91" }}>
                embedding: {snap.embedding ?? "—"}
              </span>
              <span className="ditto-chip" style={{ color: "#f2ec91" }}>
                retriever: {snap.retriever ?? "—"}
              </span>
              <span className="ditto-chip" style={{ color: "#07f285" }}>
                rag: {snap.rag ?? "—"}
              </span>
              <span className="ditto-chip" style={{ color: "#07f285" }}>
                llm: {snap.llm ?? "—"}
              </span>
            </Group>
          </div>

          <div className="ditto-glass ditto-chat-window">
            {detail.messages.map((m, i) => (
              <div key={i} className="ditto-chat-msg" data-role={m.role}>
                <span className="ditto-chat-bubble">{m.content}</span>
              </div>
            ))}
          </div>

          <Group mt="lg" align="flex-end" gap="sm">
            <NumberInput
              label="Nota (0–10)"
              min={0}
              max={10}
              value={rating}
              onChange={(v) => setRating(typeof v === "number" ? v : "")}
              w={140}
            />
            <Button color="violet" loading={saving} disabled={rating === ""} onClick={save}>
              Salvar nota
            </Button>
            {saved && (
              <Text size="sm" c="#07f285">
                Nota salva
              </Text>
            )}
          </Group>
        </>
      )}
    </div>
  );
}
