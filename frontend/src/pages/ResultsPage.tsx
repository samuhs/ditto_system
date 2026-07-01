import { Alert, Text } from "@mantine/core";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { listExperiments } from "../api/client";
import type { ExperimentSummary } from "../api/types";
import { PageHeader } from "../components/PageHeader";

function statusColor(status: string): string {
  if (status === "done") return "#07f285";
  if (status === "failed") return "#f26dcf";
  return "#05dbf2";
}

export function ResultsPage() {
  const navigate = useNavigate();
  const [experiments, setExperiments] = useState<ExperimentSummary[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listExperiments()
      .then(setExperiments)
      .catch((e) => setError(String(e)));
  }, []);

  return (
    <div>
      <PageHeader
        eyebrow="Passo 03 · Ranquear"
        title="Resultados"
        subtitle="Clique num experimento para abrir sua página com a tabela completa — ordenável por métrica, com filtros e paginação."
      />

      {error && (
        <Alert color="red" variant="light" title="Erro" mb="lg" radius="lg" maw={760}>
          {error}
        </Alert>
      )}

      <div className="ditto-exp-list" style={{ maxWidth: 900 }}>
        {experiments.length === 0 && !error && (
          <p className="ditto-empty">Nenhum experimento encontrado.</p>
        )}
        {experiments.map((exp) => (
          <button
            key={exp.id}
            className="ditto-exp-row"
            onClick={() => navigate(`/results/${exp.id}`)}
          >
            <Text fw={600} fz="sm">
              {exp.name}
            </Text>
            <span className="ditto-chip" style={{ color: statusColor(exp.status) }}>
              {exp.status}
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}
