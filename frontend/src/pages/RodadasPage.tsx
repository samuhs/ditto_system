import { Button, NumberInput, Select, TextInput } from "@mantine/core";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import {
  createAnnotationRound,
  getAnnotationRound,
  listAnnotationRounds,
  listAnnotators,
  listExperiments,
  setAnnotatorActive,
} from "../api/client";
import type {
  AnnotationRoundDetail,
  AnnotationRoundSummary,
  Annotator,
  ExperimentSummary,
} from "../api/types";
import { Errata, Saved, errorText } from "../components/Notice";
import { PageHeader } from "../components/PageHeader";

const STATUS = { open: "Aberta", closed: "Fechada" } as const;

/** The researcher's side of the Anotação humana: Avaliadores and Rodadas. */
export function RodadasPage() {
  const [annotators, setAnnotators] = useState<Annotator[]>([]);
  const [rounds, setRounds] = useState<AnnotationRoundSummary[]>([]);
  const [experiments, setExperiments] = useState<ExperimentSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [experimentId, setExperimentId] = useState<string | null>(null);
  const [size, setSize] = useState<number | string>(60);
  const [seed, setSeed] = useState<number | string>("");

  function refresh() {
    listAnnotators().then(setAnnotators).catch((e) => setError(errorText(e)));
    listAnnotationRounds().then(setRounds).catch((e) => setError(errorText(e)));
  }

  useEffect(() => {
    refresh();
    listExperiments(1, 100)
      .then((list) => setExperiments(list.items.filter((x) => x.status === "done")))
      .catch((e) => setError(errorText(e)));
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

  async function create() {
    setError(null);
    setCreated(null);
    try {
      const rnd = await createAnnotationRound({
        name: name.trim(),
        experiment_id: Number(experimentId),
        sample_size: Number(size),
        ...(seed === "" ? {} : { seed: Number(seed) }),
      });
      setCreated(rnd.name);
      setName("");
      refresh();
    } catch (e) {
      setError(errorText(e));
    }
  }

  const canCreate = name.trim() !== "" && experimentId !== null && Number(size) > 0;

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
          <p className="ditto-read">Sorteia respostas válidas de um experimento concluído. A mesma semente sorteia as mesmas respostas.</p>
        </div>
        <div className="ditto-sec-body">
          <TextInput label="Nome da rodada" value={name} onChange={(e) => setName(e.currentTarget.value)} maw={420} />
          <div className="ditto-filters" style={{ margin: 0 }}>
            <Select
              label="Experimento"
              data={experiments.map((x) => ({ value: String(x.id), label: `#${x.id} · ${x.name}` }))}
              value={experimentId}
              onChange={setExperimentId}
              searchable
            />
            <NumberInput label="Respostas a sortear" value={size} onChange={setSize} min={1} maw={200} />
            <NumberInput label="Semente (opcional)" value={seed} onChange={setSeed} min={0} maw={200} />
          </div>
          <Button onClick={create} disabled={!canCreate}>Criar rodada</Button>
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
                    <td>{STATUS[r.status]}</td>
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

export function RodadaDetailPage() {
  const { id } = useParams();
  const [round, setRound] = useState<AnnotationRoundDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getAnnotationRound(Number(id)).then(setRound).catch((e) => setError(errorText(e)));
  }, [id]);

  return (
    <div>
      <PageHeader
        title={round ? `Rodada ${round.name}` : "Rodada"}
        lede={round && `${round.size} respostas · semente ${round.seed} · rubrica v${round.rubric_version} · ${STATUS[round.status]}`}
        back={{ to: "/anotacao", label: "Voltar às rodadas" }}
      />
      {error && <Errata title="Algo não funcionou">{error}</Errata>}
      {round && (
        <section className="ditto-sec">
          <h2 className="ditto-h2">Progresso</h2>
          {round.progress.length === 0 ? (
            <p className="ditto-empty">Ninguém avaliou esta rodada ainda.</p>
          ) : (
            <div className="ditto-table-wrap">
              <table className="ditto-table">
                <thead><tr><th>Avaliador</th><th>Avaliadas</th></tr></thead>
                <tbody>
                  {round.progress.map((p) => (
                    <tr key={p.annotator_id}>
                      <td>{p.name}</td>
                      <td className="ditto-num">{p.done} de {p.total}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}
    </div>
  );
}
