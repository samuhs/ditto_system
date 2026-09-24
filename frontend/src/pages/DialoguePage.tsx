import { Button, Loader, NumberInput } from "@mantine/core";
import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import { getDialogue, saveDialogueRating } from "../api/client";
import type { DialogueDetail } from "../api/types";
import { Errata, Saved, errorText } from "../components/Notice";
import { PageHeader } from "../components/PageHeader";
import { formatDateTime } from "../utils/duration";

const SNAPSHOT_FIELDS: [string, string][] = [
  ["persona", "Persona"],
  ["base", "Base"],
  ["chunking", "Corte"],
  ["embedding", "Embedding"],
  ["retriever", "Busca"],
  ["rag", "RAG"],
  ["llm", "Modelo"],
];

export function DialoguePage() {
  const { id } = useParams<{ id: string }>();
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
        setError(errorText(e));
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
      setError(errorText(e));
    } finally {
      setSaving(false);
    }
  }

  const snap = detail?.config_snapshot ?? {};

  return (
    <div>
      <PageHeader
        back={{ to: "/dialogues", label: "Voltar aos diálogos" }}
        title={snap.name ?? "Diálogo"}
        lede={detail ? `Salvo em ${formatDateTime(detail.created_at)}. Leia a conversa e dê uma nota de 0 a 10.` : undefined}
      />

      {loading && <Loader aria-label="Carregando diálogo" />}

      {error && (
        <div style={{ marginBottom: 20 }}>
          <Errata title="Algo não funcionou">{error}. Tente de novo.</Errata>
        </div>
      )}

      {detail && !loading && (
        <div className="ditto-flow" style={{ gridTemplateColumns: "minmax(0, 1fr) 280px" }}>
          <div className="ditto-chat" data-static="true">
            {detail.messages.map((m, i) => (
              <div key={i} className="ditto-msg" data-role={m.role}>
                <span className="ditto-msg-who">{m.role === "user" ? "Pessoa" : "Ditto"}</span>
                <span className="ditto-msg-text">{m.content}</span>
              </div>
            ))}
          </div>

          <aside style={{ display: "flex", flexDirection: "column", gap: 24 }}>
            <div>
              <h2 className="ditto-h2" style={{ marginBottom: 10 }}>
                Nota
              </h2>
              <NumberInput
                label="Nota (0–10)"
                min={0}
                max={10}
                clampBehavior="strict"
                value={rating}
                onChange={(v) => {
                  setRating(typeof v === "number" ? v : "");
                  setSaved(false);
                }}
                w={140}
              />
              <div className="ditto-row-actions" style={{ marginTop: 12 }}>
                <Button loading={saving} disabled={rating === ""} onClick={save}>
                  Salvar nota
                </Button>
                {saved && <Saved>Nota salva</Saved>}
              </div>
            </div>
            <div>
              <h2 className="ditto-h2" style={{ marginBottom: 10 }}>
                Configuração usada
              </h2>
              <dl className="ditto-kv">
                {SNAPSHOT_FIELDS.map(([key, label]) => (
                  <div key={key} style={{ display: "contents" }}>
                    <dt>{label}</dt>
                    <dd>{snap[key] ?? "—"}</dd>
                  </div>
                ))}
              </dl>
            </div>
          </aside>
        </div>
      )}
    </div>
  );
}
