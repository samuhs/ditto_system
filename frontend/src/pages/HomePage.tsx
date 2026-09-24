import { Button } from "@mantine/core";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { getOptions, listExperiments } from "../api/client";
import type { ExperimentSummary } from "../api/types";
import { StatusTag } from "../components/StatusTag";
import { ArrowIcon } from "../components/icons";
import { SECTIONS, type SectionId } from "../sections";

interface Overview {
  bases: number;
  indexes: number;
  experiments: number;
  latest: ExperimentSummary | null;
}

function useOverview(): Overview | null {
  const [overview, setOverview] = useState<Overview | null>(null);
  useEffect(() => {
    let active = true;
    Promise.all([
      Promise.resolve().then(getOptions),
      Promise.resolve().then(() => listExperiments(1, 1)),
    ])
      .then(([options, list]) => {
        if (!active || !options || !list) return;
        const indexes = Object.values(options.base_indexes ?? {}).reduce((n, l) => n + l.length, 0);
        setOverview({
          bases: options.bases.length,
          indexes,
          experiments: list.total,
          latest: list.items[0] ?? null,
        });
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, []);
  return overview;
}

function nextStep(o: Overview | null): { title: string; text: string; to: string; action: string } {
  if (o && o.bases === 0)
    return {
      title: "Comece pelos documentos",
      text: "Envie os textos que o Ditto vai estudar e escolha como cortá-los.",
      to: "/ingest",
      action: "Preparar documentos",
    };
  if (o && o.experiments === 0)
    return {
      title: "Seus documentos estão prontos",
      text: "Agora crie um experimento: escolha as técnicas e envie as perguntas.",
      to: "/experiment",
      action: "Criar experimento",
    };
  if (o?.latest)
    return {
      title: `Último experimento: ${o.latest.name}`,
      text: "Veja qual combinação respondeu melhor e leia as respostas.",
      to: `/results/${o.latest.id}`,
      action: "Ver resultado",
    };
  return {
    title: "Três passos até a melhor combinação",
    text: "Prepare os documentos, rode um experimento e compare os resultados.",
    to: "/ingest",
    action: "Preparar documentos",
  };
}

function sectionState(id: SectionId, o: Overview | null) {
  if (!o) return null;
  switch (id) {
    case "preparar":
      return o.bases === 0 ? (
        "Nenhuma base ainda"
      ) : (
        <>
          <b>{o.bases}</b> {o.bases === 1 ? "base" : "bases"} · <b>{o.indexes}</b> {o.indexes === 1 ? "índice" : "índices"}
        </>
      );
    case "experimentar":
    case "comparar":
      if (o.experiments === 0) return "Nenhum experimento ainda";
      return id === "experimentar" ? (
        <>
          <b>{o.experiments}</b> {o.experiments === 1 ? "experimento" : "experimentos"}
        </>
      ) : (
        o.latest && <StatusTag status={o.latest.status} label={`Último: ${o.latest.name}`} />
      );
    default:
      return null;
  }
}

export function HomePage() {
  const overview = useOverview();
  const next = nextStep(overview);

  return (
    <div>
      <header className="ditto-home-head" style={{ gridTemplateColumns: "minmax(0, 1fr)" }}>
        <div className="ditto-page-head" style={{ marginBottom: 0 }}>
          <h1 className="ditto-page-title" style={{ fontSize: "clamp(40px, 5vw, 60px)" }}>
            Vire especialista nos seus documentos.
          </h1>
          <p className="ditto-page-lede">
            Como o Pokémon que copia a forma de quem está à sua frente, o Ditto assume a forma dos
            seus documentos: testa cada combinação de técnicas de RAG sobre as suas perguntas e
            mostra qual responde melhor.
          </p>
          <p className="ditto-formula" aria-label="Uma combinação é corte, embedding, técnica de RAG, busca e modelo">
            <span>corte</span>
            <span className="ditto-formula-x" aria-hidden>×</span>
            <span>embedding</span>
            <span className="ditto-formula-x" aria-hidden>×</span>
            <span>técnica de RAG</span>
            <span className="ditto-formula-x" aria-hidden>×</span>
            <span>busca</span>
            <span className="ditto-formula-x" aria-hidden>×</span>
            <span>modelo</span>
          </p>
        </div>
      </header>

      <section className="ditto-next" aria-label="Próximo passo">
        <div className="ditto-next-text">
          <h2 className="ditto-h2">{next.title}</h2>
          <p>{next.text}</p>
        </div>
        <Button component={Link} to={next.to} size="md" rightSection={<ArrowIcon />}>
          {next.action}
        </Button>
      </section>

      <h2 className="ditto-h2" style={{ marginBottom: 12 }}>
        Sumário
      </h2>
      <ol className="ditto-toc">
        {SECTIONS.filter((s) => s.id !== "inicio").map((s) => (
          <li key={s.id} className="ditto-toc-item" data-section={s.id}>
            <span className="ditto-toc-tab" aria-hidden>
              {s.step ?? ""}
            </span>
            <div>
              <Link to={s.pages[0].to} className="ditto-toc-link">
                {s.label}
              </Link>
              <p className="ditto-toc-purpose">{s.purpose}</p>
            </div>
            <span className="ditto-toc-state">{sectionState(s.id, overview)}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}
