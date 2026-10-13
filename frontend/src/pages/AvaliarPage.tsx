import { Button, Radio, TextInput } from "@mantine/core";
import { useEffect, useState } from "react";

import {
  createAnnotator,
  getAnnotationQueue,
  getRubric,
  listAnnotationRounds,
  listAnnotators,
  saveAnnotationNote,
} from "../api/client";
import type {
  AnnotationQueue,
  AnnotationRoundSummary,
  Annotator,
  Rubric,
  RubricDimension,
} from "../api/types";
import { Errata, errorText } from "../components/Notice";

type Draft = { correctness: number | null; grounding: number | null };

const EMPTY: Draft = { correctness: null, grounding: null };

/**
 * The Avaliador's screen, in focus mode (no menu, no link to results): who is evaluating,
 * which open Rodada, then one answer at a time on the Rubrica. Everyone evaluates on the
 * researcher's machine, so there is no login: picking a name is enough.
 */
export function AvaliarPage() {
  const [annotator, setAnnotator] = useState<Annotator | null>(null);
  const [roundId, setRoundId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

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
        <ChooseRound onChoose={setRoundId} onError={setError} />
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

function ChooseRound({ onChoose, onError }: { onChoose: (id: number) => void; onError: (e: string) => void }) {
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
          <Button key={r.id} variant="default" onClick={() => onChoose(r.id)}>
            {r.name} · {r.size} respostas
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
  const [draft, setDraft] = useState<Draft>(EMPTY);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    Promise.all([getAnnotationQueue(roundId, annotator.id), getRubric()])
      .then(([q, r]) => {
        setQueue(q);
        setRubric(r);
        const firstOpen = q.items.findIndex((i) => i.note === null);
        go(q, firstOpen === -1 ? 0 : firstOpen);
      })
      .catch((e) => onError(errorText(e)));
  }, [roundId, annotator.id, onError]);

  function go(q: AnnotationQueue, to: number) {
    setIndex(to);
    setDraft(q.items[to]?.note ?? EMPTY);
  }

  if (!queue || !rubric) return null;
  const item = queue.items[index];
  const complete = draft.correctness !== null && draft.grounding !== null;

  async function save() {
    if (!queue || !item || draft.correctness === null || draft.grounding === null) return;
    setSaving(true);
    onError(null);
    try {
      const note = { correctness: draft.correctness, grounding: draft.grounding };
      await saveAnnotationNote(item.id, annotator.id, note);
      const items = queue.items.map((i) => (i.id === item.id ? { ...i, note } : i));
      const next: AnnotationQueue = { ...queue, items, done: items.filter((i) => i.note !== null).length };
      setQueue(next);
      // Next answer still without a note, wrapping around to ones skipped earlier.
      const pending = [...items.keys()].map((k) => (index + 1 + k) % items.length)
        .find((k) => items[k].note === null);
      go(next, pending ?? Math.min(index + 1, items.length - 1));
    } catch (e) {
      onError(errorText(e));
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="ditto-sec">
      <div className="ditto-sec-head">
        <h1 className="ditto-h2">{queue.round.name}</h1>
        <p className="ditto-read">
          Resposta {index + 1} de {queue.total} · {queue.done} de {queue.total} avaliadas
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
              <DimensionField
                key={dim.key}
                dim={dim}
                value={draft[dim.key]}
                onChange={(v) => setDraft((d) => ({ ...d, [dim.key]: v }))}
              />
            ))}
            <div className="ditto-annotate-nav">
              <Button variant="default" disabled={index === 0} onClick={() => go(queue, index - 1)}>Anterior</Button>
              <Button variant="default" disabled={index === queue.items.length - 1} onClick={() => go(queue, index + 1)}>
                Próxima
              </Button>
              <Button onClick={save} disabled={!complete} loading={saving}>Salvar e seguir</Button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

function DimensionField({ dim, value, onChange }: {
  dim: RubricDimension; value: number | null; onChange: (v: number) => void;
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
          onChange={() => onChange(lvl.value)}
          aria-label={`${dim.label}: ${lvl.value} · ${lvl.label}`}
          label={<span><strong>{lvl.value} · {lvl.label}</strong> — {lvl.description}</span>}
        />
      ))}
    </fieldset>
  );
}
