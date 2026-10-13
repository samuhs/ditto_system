import { Button, Checkbox, NativeSelect, NumberInput, Radio, TextInput } from "@mantine/core";
import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";

import {
  closeAnnotationRound,
  createAnnotationRound,
  getAnnotationAgreement,
  getAnnotationRound,
  getFinalNotes,
  listAnnotationRounds,
  listAnnotators,
  previewAnnotationRound,
  removeAnnotationParticipant,
  setAnnotationAdjudicator,
  setAnnotatorActive,
} from "../api/client";
import type {
  AgreementValue,
  AnnotationAgreement,
  AnnotationNoteValues,
  AnnotationRoundDetail,
  AnnotationRoundInput,
  AnnotationRoundPreview,
  AnnotationRoundSummary,
  AnnotationStratumDim,
  Annotator,
  FinalNotes,
} from "../api/types";
import { CombinationPicker } from "../components/CombinationPicker";
import { Errata, Saved, errorText } from "../components/Notice";
import { PageHeader } from "../components/PageHeader";

const STATUS = { open: "Aberta", closed: "Fechada" } as const;

const DIMS: { value: AnnotationStratumDim; label: string }[] = [
  { value: "question_type", label: "Tipo de pergunta" },
  { value: "rag", label: "Técnica RAG" },
  { value: "llm", label: "LLM de resposta" },
];

/** The researcher's side of the Anotação humana: Avaliadores and Rodadas. */
export function RodadasPage() {
  const [annotators, setAnnotators] = useState<Annotator[]>([]);
  const [rounds, setRounds] = useState<AnnotationRoundSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [items, setItems] = useState<string[]>([]);
  const [size, setSize] = useState<number | string>(60);
  const [seed, setSeed] = useState<number | string>("");
  const [strata, setStrata] = useState<AnnotationStratumDim[]>([]);
  const [allocation, setAllocation] = useState<"proportional" | "equal">("proportional");
  const [pilot, setPilot] = useState(false);
  const [preview, setPreview] = useState<AnnotationRoundPreview | null>(null);
  // Bumped on every design change, so a preview that answers late for an old design is dropped.
  const designVersion = useRef(0);

  function refresh() {
    listAnnotators().then(setAnnotators).catch((e) => setError(errorText(e)));
    listAnnotationRounds().then(setRounds).catch((e) => setError(errorText(e)));
  }

  useEffect(() => {
    refresh();
  }, []);

  async function toggle(a: Annotator) {
    setError(null);
    try {
      const updated = await setAnnotatorActive(a.id, !a.active);
      setAnnotators((all) => all.map((x) => (x.id === a.id ? updated : x)));
    } catch (e) {
      setError(errorText(e));
    }
  }

  function design(): AnnotationRoundInput {
    return {
      name: name.trim() || "prévia",
      items,
      sample_size: Number(size),
      ...(seed === "" ? {} : { seed: Number(seed) }),
      strata,
      allocation,
      pilot,
    };
  }

  function touch<T>(set: (v: T) => void) {
    return (v: T) => {
      set(v);
      designVersion.current += 1;
      setPreview(null);
    };
  }

  async function showPreview() {
    setError(null);
    const asked = designVersion.current;
    try {
      const result = await previewAnnotationRound(design());
      if (asked === designVersion.current) setPreview(result);
    } catch (e) {
      setError(errorText(e));
    }
  }

  async function create() {
    setError(null);
    setCreated(null);
    try {
      const rnd = await createAnnotationRound(design());
      setCreated(rnd.name);
      setName("");
      setPreview(null);
      refresh();
    } catch (e) {
      setError(errorText(e));
    }
  }

  const toggleItem = touch((id: string) =>
    setItems((all) => (all.includes(id) ? all.filter((x) => x !== id) : [...all, id])));
  const ready = items.length > 0 && Number(size) > 0;
  const canCreate = name.trim() !== "" && ready;

  return (
    <div>
      <PageHeader
        title="Anotação humana"
        lede="Avaliadores dão notas, às cegas, a respostas sorteadas de um experimento. As notas validam as métricas automáticas."
      />
      {error && (
        <div style={{ marginBottom: 20 }}>
          <Errata title="Algo não funcionou">{error}</Errata>
        </div>
      )}
      <p>
        Os avaliadores usam esta máquina: <Link to="/anotar">abrir a tela de avaliação</Link>. Lá, cada pessoa se
        cadastra como avaliador novo ou escolhe o próprio nome.
      </p>

      <section className="ditto-sec">
        <div className="ditto-sec-head">
          <h2 className="ditto-h2">Nova rodada</h2>
          <p className="ditto-read">
            Sorteia respostas válidas das Combinações escolhidas, de uma Base só. A mesma semente sorteia as mesmas
            respostas. Estratificar garante que cada tipo de pergunta, técnica ou LLM apareça na amostra.
          </p>
        </div>
        <div className="ditto-sec-body">
          <TextInput label="Nome da rodada" value={name} onChange={(e) => setName(e.currentTarget.value)} maw={420} />
          <CombinationPicker items={items} onToggle={toggleItem} />
          {items.length > 0 && <p className="ditto-muted">{items.length} Combinação(ões) escolhida(s): {items.join(", ")}</p>}
          <div className="ditto-filters" style={{ margin: 0 }}>
            <NumberInput label="Respostas a sortear" value={size} onChange={touch(setSize)} min={1} maw={200} />
            <NumberInput label="Semente (opcional)" value={seed} onChange={touch(setSeed)} min={0} maw={200} />
          </div>
          <fieldset className="ditto-rubric-dim">
            <legend>Estratificar por</legend>
            {DIMS.map((d) => (
              <Checkbox
                key={d.value}
                label={d.label}
                checked={strata.includes(d.value)}
                onChange={() => touch(setStrata)(strata.includes(d.value)
                  ? strata.filter((x) => x !== d.value) : [...strata, d.value])}
              />
            ))}
            <Radio.Group value={allocation} onChange={(v) => touch(setAllocation)(v as "proportional" | "equal")}>
              <Radio value="proportional" label="Proporcional ao tamanho de cada estrato" />
              <Radio value="equal" label="Igual por estrato" mt={6} />
            </Radio.Group>
          </fieldset>
          <Checkbox
            label="Rodada piloto (calibra a rubrica; fica fora da análise)"
            checked={pilot}
            onChange={(e) => setPilot(e.currentTarget.checked)}
          />
          <div className="ditto-annotate-nav">
            <Button variant="default" onClick={showPreview} disabled={!ready}>Ver prévia</Button>
            <Button onClick={create} disabled={!canCreate}>Criar rodada</Button>
          </div>
          {preview && <PreviewTable preview={preview} />}
          {created && <Saved>Rodada {created} criada.</Saved>}
        </div>
      </section>

      <section className="ditto-sec">
        <h2 className="ditto-h2">Rodadas</h2>
        {rounds.length === 0 ? (
          <p className="ditto-empty">Nenhuma rodada ainda.</p>
        ) : (
          <div className="ditto-table-wrap">
            <table className="ditto-table">
              <thead><tr><th>Rodada</th><th>Respostas</th><th>Situação</th><th>Experimento</th></tr></thead>
              <tbody>
                {rounds.map((r) => (
                  <tr key={r.id}>
                    <td><Link to={`/anotacao/${r.id}`}>{r.name}</Link></td>
                    <td className="ditto-num">{r.size} respostas</td>
                    <td>{STATUS[r.status]}{r.pilot && <span className="ditto-muted"> · piloto, fora da análise</span>}</td>
                    <td>{r.experiment_ids.map((id) => `#${id}`).join(", ")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="ditto-sec">
        <h2 className="ditto-h2">Avaliadores</h2>
        {annotators.length === 0 ? (
          <p className="ditto-empty">Ninguém se cadastrou ainda. O cadastro é feito na tela de avaliação.</p>
        ) : (
          <div className="ditto-table-wrap">
            <table className="ditto-table">
              <thead><tr><th>Nome</th><th>Situação</th><th /></tr></thead>
              <tbody>
                {annotators.map((a) => (
                  <tr key={a.id}>
                    <td>{a.name}</td>
                    <td>{a.active ? "Ativo" : "Desativado"}</td>
                    <td>
                      <Button variant="subtle" size="xs" onClick={() => toggle(a)}>
                        {a.active ? "Desativar" : "Reativar"}
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}

function PreviewTable({ preview }: { preview: AnnotationRoundPreview }) {
  const label = (key: AnnotationRoundPreview["strata"][number]["key"]) =>
    Object.values(key).join(" · ") || "Todas as respostas";
  return (
    <div className="ditto-table-wrap">
      <table className="ditto-table">
        <caption>{preview.size} de {preview.available} respostas válidas</caption>
        <thead><tr><th>Estrato</th><th>Sorteadas</th><th /></tr></thead>
        <tbody>
          {preview.strata.map((s) => (
            <tr key={label(s.key)}>
              <td>{label(s.key)}</td>
              <td className="ditto-num">{s.allocated} de {s.available}</td>
              <td>{s.short && <span className="ditto-muted">Faltam respostas: os outros estratos completam</span>}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function RodadaDetailPage() {
  const { id } = useParams();
  const [round, setRound] = useState<AnnotationRoundDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState<number | null>(null);
  const [agreement, setAgreement] = useState<AnnotationAgreement | null>(null);
  const [closing, setClosing] = useState(false);

  const [computing, setComputing] = useState(false);
  const [annotators, setAnnotators] = useState<Annotator[]>([]);
  const [final, setFinal] = useState<FinalNotes | null>(null);

  async function designate(value: string) {
    setError(null);
    try {
      // Only the round and the final notes depend on it: no need to redo the Concordância.
      setRound((r) => (r ? { ...r, adjudicator_id: value ? Number(value) : null } : r));
      await setAnnotationAdjudicator(Number(id), value ? Number(value) : null);
      getAnnotationRound(Number(id)).then(setRound).catch((e) => setError(errorText(e)));
      getFinalNotes(Number(id)).then(setFinal).catch((e) => setError(errorText(e)));
    } catch (e) {
      setError(errorText(e));
    }
  }

  function computeAgreement() {
    setComputing(true);
    getAnnotationAgreement(Number(id))
      .then(setAgreement)
      .catch((e) => setError(errorText(e)))
      .finally(() => setComputing(false));
  }

  // A closed Rodada shows its Concordância right away (cached on the server); an open one
  // computes it on demand, since the bootstrap takes a few seconds and the notes still change.
  function load() {
    setAgreement(null);
    getAnnotationRound(Number(id))
      .then((r) => {
        setRound(r);
        if (r.status === "closed") {
          computeAgreement();
          listAnnotators().then(setAnnotators).catch((e) => setError(errorText(e)));
          getFinalNotes(Number(id)).then(setFinal).catch((e) => setError(errorText(e)));
        }
      })
      .catch((e) => setError(errorText(e)));
  }

  async function close() {
    setError(null);
    try {
      await closeAnnotationRound(Number(id));
      setClosing(false);
      load();
    } catch (e) {
      setError(errorText(e));
    }
  }

  useEffect(load, [id]);

  async function remove(annotatorId: number) {
    setError(null);
    try {
      await removeAnnotationParticipant(Number(id), annotatorId);
      setConfirming(null);
      load();
    } catch (e) {
      setError(errorText(e));
    }
  }

  return (
    <div>
      <PageHeader
        title={round ? `Rodada ${round.name}` : "Rodada"}
        lede={round && `${round.size} respostas · semente ${round.seed} · rubrica v${round.rubric_version} · ${STATUS[round.status]}${round.pilot ? " · piloto, fora da análise" : ""}`}
        back={{ to: "/anotacao", label: "Voltar às rodadas" }}
      />
      {error && <Errata title="Algo não funcionou">{error}</Errata>}
      {round?.status === "open" && (
        <div className="ditto-annotate-nav" style={{ marginBottom: 16 }}>
          {closing ? (
            <>
              <Button color="red" onClick={close}>Confirmar: fechar e congelar as notas</Button>
              <Button variant="subtle" onClick={() => setClosing(false)}>Cancelar</Button>
            </>
          ) : (
            <Button variant="default" onClick={() => setClosing(true)}>Fechar rodada</Button>
          )}
        </div>
      )}
      {round && (
        <section className="ditto-sec">
          <h2 className="ditto-h2">Progresso</h2>
          {round.progress.length === 0 ? (
            <p className="ditto-empty">Ninguém avaliou esta rodada ainda.</p>
          ) : (
            <div className="ditto-table-wrap">
              <table className="ditto-table">
                <thead><tr><th>Avaliador</th><th>Avaliadas</th><th /></tr></thead>
                <tbody>
                  {round.progress.map((p) => (
                    <tr key={p.annotator_id}>
                      <td>{p.name}</td>
                      <td className="ditto-num">{p.done} de {p.total}</td>
                      <td>
                        {confirming === p.annotator_id ? (
                          <>
                            <Button size="xs" color="red" onClick={() => remove(p.annotator_id)}>
                              Confirmar: apagar {p.done} notas
                            </Button>
                            <Button size="xs" variant="subtle" onClick={() => setConfirming(null)}>Cancelar</Button>
                          </>
                        ) : (
                          <Button size="xs" variant="subtle" onClick={() => setConfirming(p.annotator_id)}>Remover</Button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}
      {round?.status === "open" && !agreement && (
        <section className="ditto-sec">
          <h2 className="ditto-h2">Concordância</h2>
          <p className="ditto-read">A rodada ainda está aberta: as notas podem mudar.</p>
          <Button variant="default" onClick={computeAgreement} loading={computing}>Calcular concordância agora</Button>
        </section>
      )}
      {agreement && <AgreementSection agreement={agreement} />}
      {round?.status === "closed" && (
        <section className="ditto-sec">
          <div className="ditto-sec-head">
            <h2 className="ditto-h2">Adjudicação e Nota final</h2>
            <p className="ditto-read">
              Onde os avaliadores discordam, o adjudicador decide a nota na tela de avaliação. Ele não pode ter dado
              notas nesta rodada.
            </p>
          </div>
          <NativeSelect
            label="Adjudicador"
            value={round.adjudicator_id ? String(round.adjudicator_id) : ""}
            onChange={(e) => designate(e.currentTarget.value)}
            data={[{ value: "", label: "Ninguém designado" },
              ...annotators
                .filter((a) => a.active || a.id === round.adjudicator_id)
                .map((a) => ({ value: String(a.id), label: a.active ? a.name : `${a.name} (desativado)` }))]}
            maw={320}
          />
          {final && <p>{finalSummary(final)}</p>}
        </section>
      )}
    </div>
  );
}

function finalSummary(final: FinalNotes): string {
  const count = (status: string) => final.items.filter((i) => i.status === status).length;
  const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;
  return `${count("concordância")} em concordância · ${plural(count("adjudicada"), "adjudicada")} · `
    + `${plural(final.pending, "pendente")}`;
}

const DIM_LABEL = { correctness: "Correção", grounding: "Fundamentação" } as const;

const dec = (v: number) => v.toFixed(2).replace(".", ",");

function withCi(v: AgreementValue | null): string {
  if (!v || v.value === null) return "—";
  return v.low === null || v.high === null ? dec(v.value) : `${dec(v.value)} [${dec(v.low)}; ${dec(v.high)}]`;
}

function noteText(n: AnnotationNoteValues): string {
  if (n.cannot_evaluate) return "não conseguiu avaliar";
  return `${n.correctness ?? "—"} / ${n.grounding ?? "—"}`;
}

function AgreementSection({ agreement }: { agreement: AnnotationAgreement }) {
  const dims = (["correctness", "grounding"] as const).map((k) => [k, agreement.dimensions[k]] as const);
  return (
    <section className="ditto-sec">
      <div className="ditto-sec-head">
        <h2 className="ditto-h2">Concordância</h2>
        <p className="ditto-read">
          α de Krippendorff ordinal e, com dois avaliadores, kappa ponderado (pesos quadráticos), com IC 95% por
          bootstrap. Respostas sem nota numa dimensão ficam fora dela.
        </p>
      </div>
      {agreement.note && <p className="ditto-empty">{agreement.note}</p>}
      <div className="ditto-table-wrap">
        <table className="ditto-table">
          <thead><tr><th>Dimensão</th><th className="ditto-num">Respostas</th><th>α ordinal</th><th>κ ponderado</th></tr></thead>
          <tbody>
            {dims.map(([key, d]) => (
              <tr key={key}>
                <td>{DIM_LABEL[key]}</td>
                <td className="ditto-num">{d.n}</td>
                <td>{withCi(d.alpha)}</td>
                <td>{withCi(d.kappa)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {dims.filter(([, d]) => d.confusion).map(([key, d]) => (
        <div className="ditto-table-wrap" key={key}>
          <table className="ditto-table" aria-label={`Matriz de confusão · ${DIM_LABEL[key]}`}>
            <caption>Matriz de confusão · {DIM_LABEL[key]} (linhas: {d.confusion!.avaliadores[0]}; colunas: {d.confusion!.avaliadores[1]})</caption>
            <thead><tr><th />{d.confusion!.levels.map((l) => <th key={l} className="ditto-num">{l}</th>)}</tr></thead>
            <tbody>
              {d.confusion!.matrix.map((row, i) => (
                <tr key={i}>
                  <th>{d.confusion!.levels[i]}</th>
                  {row.map((c, j) => <td key={j} className="ditto-num">{c}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
      <h3 className="ditto-h3">Discordâncias ({agreement.disagreements.length})</h3>
      {agreement.disagreements.length === 0 ? (
        <p className="ditto-muted">Nenhuma discordância.</p>
      ) : (
        <div className="ditto-table-wrap">
          <table className="ditto-table">
            <thead><tr><th>Pergunta</th><th>Resposta avaliada</th><th>Notas (Correção / Fundamentação)</th></tr></thead>
            <tbody>
              {agreement.disagreements.map((d) => (
                <tr key={d.item_id}>
                  <td>{d.question}</td>
                  <td>{d.generated_answer}</td>
                  <td>
                    {Object.entries(d.notes).map(([name, n]) => (
                      <div key={name}>{name}: {noteText(n)}{n.comment ? ` (“${n.comment}”)` : ""}</div>
                    ))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
