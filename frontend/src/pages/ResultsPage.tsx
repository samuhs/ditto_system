import { Alert, Group, Pagination, Text } from "@mantine/core";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { listExperiments } from "../api/client";
import type { ExperimentList } from "../api/types";
import { PageHeader } from "../components/PageHeader";

const PAGE_SIZE = 20;

function statusColor(status: string): string {
  if (status === "done") return "#07f285";
  if (status === "failed") return "#f26dcf";
  if (status === "paused") return "#f2ec91";
  return "#05dbf2";
}

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("pt-BR");
}

export function ResultsPage() {
  const navigate = useNavigate();
  const [data, setData] = useState<ExperimentList | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);

  useEffect(() => {
    setError(null);
    listExperiments(page, PAGE_SIZE)
      .then(setData)
      .catch((e) => setError(String(e)));
  }, [page]);

  const items = data?.items ?? [];
  const pageCount = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;

  return (
    <div>
      <PageHeader
        eyebrow="Passo 03 · Ranquear"
        title="Resultados"
        subtitle="Clique num experimento para abrir sua página com a tabela completa, ordenável por métrica, com filtros e paginação."
      />

      {error && (
        <Alert color="red" variant="light" title="Erro" mb="lg" radius="lg" maw={760}>
          {error}
        </Alert>
      )}

      <div className="ditto-exp-list" style={{ maxWidth: 900 }}>
        {items.length === 0 && !error && (
          <p className="ditto-empty">Nenhum experimento encontrado.</p>
        )}
        {items.map((exp) => (
          <button
            key={exp.id}
            className="ditto-exp-row"
            onClick={() => navigate(`/results/${exp.id}`)}
          >
            <Text fw={600} fz="sm">
              {exp.name}
            </Text>
            <Text size="xs" c="dimmed" style={{ marginLeft: "auto", marginRight: 12 }}>
              {formatDate(exp.created_at)}
            </Text>
            <span className="ditto-chip" style={{ color: statusColor(exp.status) }}>
              {exp.status}
            </span>
          </button>
        ))}
      </div>

      {data && data.total > data.page_size && (
        <Group justify="center" mt="lg">
          <Pagination total={pageCount} value={page} onChange={setPage} size="sm" color="violet" />
        </Group>
      )}
    </div>
  );
}
