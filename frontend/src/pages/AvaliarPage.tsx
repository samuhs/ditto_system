import { Button, Checkbox, Radio, TextInput, Textarea } from "@mantine/core";
import { useCallback, useEffect, useState } from "react";

import {
  createAnnotator,
  getAnnotationQueue,
  getRubric,
  joinAnnotationRound,
  listAnnotationRounds,
  listAnnotators,
  saveAnnotationNote,
} from "../api/client";
import type {
  AnnotationNoteValues,
  AnnotationQueue,
  AnnotationQueueItem,
  AnnotationRoundSummary,
  Annotator,
  Rubric,
  RubricDimension,
} from "../api/types";
import { Errata, errorText } from "../components/Notice";

type Draft = AnnotationNoteValues;

const EMPTY: Draft = { correctness: null, grounding: null, cannot_evaluate: false, reason: null, comment: null };

function isComplete(d: Draft, item: AnnotationQueueItem): boolean {
  if (d.cannot_evaluate) return Boolean(d.reason?.trim());
  return d.correctness !== null && (!item.grounding_applicable || d.grounding !== null);
}

/** What goes to the API: no scores when the Avaliador cannot evaluate, no Fundamentação when
 * it does not apply, blank texts as null. */
function toNote(d: Draft, item: AnnotationQueueItem): AnnotationNoteValues {
  if (d.cannot_evaluate) {
    return { correctness: null, grounding: null, cannot_evaluate: true, reason: d.reason?.trim() || null,
      comment: d.comment?.trim() || null };
  }
  return {
    correctness: d.correctness, grounding: item.grounding_applicable ? d.grounding : null,
    cannot_evaluate: false, reason: null, comment: d.comment?.trim() || null,
  };
}

/** Whether saving `draft` would change the stored note (compares what would be sent). */
function changes(draft: Draft, item: AnnotationQueueItem): boolean {
  const saved = item.note ?? EMPTY;
  return JSON.stringify(toNote(draft, item)) !== JSON.stringify(toNote(saved, item));
}

/**
 * The Avaliador's screen, in focus mode (no menu, no link to results): who is evaluating,
 * which open Rodada, then one answer at a time on the Rubrica. Everyone evaluates on the
 * researcher's machine, so there is no login: picking a name is enough.
 */
export function AvaliarPage() {
  const [annotator, setAnnotator] = useState<Annotator | null>(null);
  const [roundId, setRoundId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [joining, setJoining] = useState(false);

  async function choose(id: number) {
    if (!annotator || joining) return;
    setError(null);
    setJoining(true);
    try {
      await joinAnnotationRound(id, annotator.id);
      setRoundId(id);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setJoining(false);
    }
  }

  function leave() {
    setRoundId(null);
    setAnnotator(null);
    setError(null);
  }

  return (
    <div className="ditto-focus">
      <header className="ditto-focus-head">
        <span className="ditto-focus-title">Anotação humana</span>
        {annotator && (
          <span className="ditto-focus-who">
            Avaliando como <strong>{annotator.name}</strong>
            <Button variant="subtle" size="xs" onClick={leave}>Sair</Button>
          </span>
        )}
      </header>
      {error && <Errata title="Algo não funcionou">{error}</Errata>}
      {!annotator && <Identify onDone={setAnnotator} onError={setError} />}
      {annotator && roundId === null && (
        <ChooseRound onChoose={choose} onError={setError} busy={joining} />
      )}
      {annotator && roundId !== null && (
        <Evaluate roundId={roundId} annotator={annotator} onError={setError} />
      )}
    </div>
  );
}

function Identify({ onDone, onError }: { onDone: (a: Annotator) => void; onError: (e: string | null) => void }) {
  const [annotators, setAnnotators] = useState<Annotator[]>([]);
  const [isNew, setIsNew] = useState(false);
  const [name, setName] = useState("");

  useEffect(() => {
    listAnnotators(true).then(setAnnotators).catch((e) => onError(errorText(e)));
  }, [onError]);

  async function register() {
    onError(null);
    try {
      onDone(await createAnnotator(name.trim()));
    } catch (e) {
      onError(errorText(e));
    }
  }

  return (
    <section className="ditto-sec">
      <h1 className="ditto-h2">Quem está avaliando?</h1>
      {annotators.length > 0 && (
        <div className="ditto-choices">
          {annotators.map((a) => (
            <Button key={a.id} variant="default" onClick={() => onDone(a)}>{a.name}</Button>
          ))}
        </div>
      )}
      {isNew ? (
        <form
          className="ditto-inline-form"
          onSubmit={(e) => {
            e.preventDefault();
            if (name.trim()) void register();
          }}
        >
          <TextInput label="Seu nome" value={name} onChange={(e) => setName(e.currentTarget.value)} autoFocus maw={320} />
          <Button type="submit" disabled={!name.trim()}>Começar</Button>
        </form>
      ) : (
        <Button variant="light" onClick={() => setIsNew(true)}>Sou um avaliador novo</Button>
      )}
    </section>
  );
}

function ChooseRound({ onChoose, onError, busy }: {
  onChoose: (id: number) => void; onError: (e: string) => void; busy: boolean;
}) {
  const [rounds, setRounds] = useState<AnnotationRoundSummary[] | null>(null);

  useEffect(() => {
    listAnnotationRounds()
      .then((all) => setRounds(all.filter((r) => r.status === "open")))
      .catch((e) => onError(errorText(e)));
  }, [onError]);

  return (
    <section className="ditto-sec">
      <h1 className="ditto-h2">Escolha a rodada</h1>
      {rounds?.length === 0 && <p className="ditto-empty">Nenhuma rodada aberta. Peça ao pesquisador para criar uma.</p>}
      <div className="ditto-choices">
        {rounds?.map((r) => (
          <Button key={r.id} variant="default" disabled={busy} onClick={() => onChoose(r.id)}>
            {r.name} · {r.size} respostas{r.pilot ? " · rodada piloto" : ""}
          </Button>
        ))}
      </div>
    </section>
  );
}

function Evaluate({ roundId, annotator, onError }: {
  roundId: number; annotator: Annotator; onError: (e: string | null) => void;
}) {
  const [queue, setQueue] = useState<AnnotationQueue | null>(null);
  const [rubric, setRubric] = useState<Rubric | null>(null);
  const [index, setIndex] = useState(0);
  // Unsaved choices per Item, kept while the Avaliador moves between answers.
  const [drafts, setDrafts] = useState<Record<number, Draft>>({});
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    Promise.all([getAnnotationQueue(roundId, annotator.id), getRubric()])
      .then(([q, r]) => {
        setQueue(q);
        setRubric(r);
        setDrafts({});
        const firstOpen = q.items.findIndex((i) => i.note === null);
        setIndex(firstOpen === -1 ? 0 : firstOpen);
      })
      .catch((e) => onError(errorText(e)));
  }, [roundId, annotator.id, onError]);

  const item = queue?.items[index];
  const draft: Draft = item ? (drafts[item.id] ?? item.note ?? EMPTY) : EMPTY;
  const edit = useCallback((change: Partial<Draft>) => {
    if (!item) return;
    setDrafts((all) => ({ ...all, [item.id]: { ...(all[item.id] ?? item.note ?? EMPTY), ...change } }));
  }, [item]);
  const complete = item ? isComplete(draft, item) : false;
  const last = queue ? queue.items.length - 1 : 0;

  const save = useCallback(async () => {
    if (!queue || !item || !isComplete(draft, item) || saving) return;
    setSaving(true);
    onError(null);
    try {
      const sent = draft;
      const note = toNote(draft, item);
      await saveAnnotationNote(item.id, annotator.id, note);
      const items = queue.items.map((i) => (i.id === item.id ? { ...i, note } : i));
      setQueue({ ...queue, items, done: items.filter((i) => i.note !== null).length });
      // Drop the draft only if nothing was edited while the request was in flight.
      setDrafts((all) => {
        if (all[item.id] !== undefined && all[item.id] !== sent) return all;
        const { [item.id]: _sent, ...rest } = all;
        return rest;
      });
      // Next answer still without a note, wrapping around to ones skipped earlier; unless the
      // Avaliador already moved elsewhere during the request.
      const pending = [...items.keys()].map((k) => (index + 1 + k) % items.length)
        .find((k) => items[k].note === null);
      setIndex((current) => (current === index ? (pending ?? Math.min(index + 1, items.length - 1)) : current));
    } catch (e) {
      onError(errorText(e));
    } finally {
      setSaving(false);
    }
  }, [queue, item, draft, saving, annotator.id, index, onError]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const target = e.target as HTMLElement | null;
      const tag = target?.tagName ?? "";
      const onRadio = tag === "INPUT" && target?.getAttribute("type") === "radio";
      // Typing, buttons and links keep their own keys; on a radio only the digits and Enter are
      // shortcuts (the arrows move between its levels).
      if (!onRadio && ["INPUT", "TEXTAREA", "SELECT", "BUTTON", "A"].includes(tag)) return;
      if (onRadio && e.key.startsWith("Arrow")) return;
      if (!item || saving || e.metaKey || e.ctrlKey || e.altKey) return;
      if (["0", "1", "2"].includes(e.key) && !draft.cannot_evaluate) {
        const value = Number(e.key);
        // 0/1/2 score Correção first, then Fundamentação (when it applies).
        if (draft.correctness === null || !item.grounding_applicable) edit({ correctness: value });
        else edit({ grounding: value });
      } else if (e.key === "Enter") {
        void save();
      } else if (e.key === "ArrowLeft") {
        setIndex((i) => Math.max(0, i - 1));
      } else if (e.key === "ArrowRight") {
        setIndex((i) => Math.min(last, i + 1));
      } else {
        return;
      }
      e.preventDefault();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [item, draft, edit, save, last, saving]);

  if (!queue || !rubric) return null;
  const unsaved = item ? item.id in drafts && changes(drafts[item.id], item) : false;

  return (
    <section className="ditto-sec">
      <div className="ditto-sec-head">
        <h1 className="ditto-h2">{queue.round.name}</h1>
        <p className="ditto-read">
          Resposta {index + 1} de {queue.total} · {queue.done} de {queue.total} avaliadas
          {unsaved && <strong> · escolha não salva</strong>}
        </p>
      </div>
      {item && (
        <div className="ditto-annotate">
          <div className="ditto-annotate-text">
            <h2 className="ditto-h3">Pergunta</h2>
            <p>{item.question}</p>
            <h2 className="ditto-h3">Resposta de referência</h2>
            <p>{item.reference_answer}</p>
            <h2 className="ditto-h3">Evidência</h2>
            <ul>{item.evidence.map((e, k) => <li key={k}>{e}</li>)}</ul>
            <h2 className="ditto-h3">Resposta a avaliar</h2>
            <p className="ditto-annotate-answer">{item.generated_answer}</p>
            <details>
              <summary>Trechos que o sistema recuperou ({item.retrieved_context.length})</summary>
              {item.retrieved_context.length === 0
                ? <p className="ditto-muted">Nenhum trecho recuperado.</p>
                : <ol>{item.retrieved_context.map((c, k) => <li key={k}>{c}</li>)}</ol>}
            </details>
          </div>
          <div className="ditto-annotate-rubric">
            {rubric.dimensions.map((dim) => (
              dim.key === "grounding" && !item.grounding_applicable ? (
                <fieldset key={dim.key} className="ditto-rubric-dim">
                  <legend>{dim.label}</legend>
                  <p className="ditto-muted">Não se aplica: o sistema não recuperou trechos para esta resposta.</p>
                </fieldset>
              ) : (
                <DimensionField
                  key={dim.key}
                  dim={dim}
                  value={draft[dim.key]}
                  disabled={draft.cannot_evaluate}
                  onChange={(v) => edit({ [dim.key]: v })}
                />
              )
            ))}
            <Checkbox
              label="Não consigo avaliar esta resposta"
              checked={draft.cannot_evaluate}
              onChange={(e) => edit({ cannot_evaluate: e.currentTarget.checked })}
            />
            {draft.cannot_evaluate && (
              <TextInput label="Por quê?" value={draft.reason ?? ""} onChange={(e) => edit({ reason: e.currentTarget.value })} />
            )}
            <Textarea
              label="Comentário (opcional)"
              value={draft.comment ?? ""}
              onChange={(e) => edit({ comment: e.currentTarget.value })}
              autosize
              minRows={2}
            />
            <div className="ditto-annotate-nav">
              <Button variant="default" disabled={index === 0} onClick={() => setIndex(index - 1)}>Anterior</Button>
              <Button variant="default" disabled={index === last} onClick={() => setIndex(index + 1)}>Próxima</Button>
              <Button onClick={save} disabled={!complete} loading={saving}>Salvar e seguir</Button>
            </div>
            <p className="ditto-muted">
              Atalhos: 0, 1 e 2 dão a nota (Correção, depois Fundamentação) · Enter salva e segue · ← e → navegam.
            </p>
          </div>
        </div>
      )}
    </section>
  );
}

function DimensionField({ dim, value, disabled, onChange }: {
  dim: RubricDimension; value: number | null; disabled: boolean; onChange: (v: number) => void;
}) {
  return (
    <fieldset className="ditto-rubric-dim">
      <legend>{dim.label}</legend>
      <p className="ditto-muted">{dim.question}</p>
      {dim.levels.map((lvl) => (
        <Radio
          key={lvl.value}
          name={dim.key}
          checked={value === lvl.value}
          disabled={disabled}
          onChange={() => onChange(lvl.value)}
          aria-label={`${dim.label}: ${lvl.value} · ${lvl.label}`}
          label={<span><strong>{lvl.value} · {lvl.label}</strong> — {lvl.description}</span>}
        />
      ))}
    </fieldset>
  );
}
