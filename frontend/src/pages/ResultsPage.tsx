import { Button, Group, Loader, Pagination } from "@mantine/core";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { listExperiments } from "../api/client";
import type { ExperimentList } from "../api/types";
import { Errata, errorText } from "../components/Notice";
import { PageHeader } from "../components/PageHeader";
import { StatusTag } from "../components/StatusTag";
import { ArrowIcon } from "../components/icons";
import { formatDateTime } from "../utils/duration";

const PAGE_SIZE = 20;

export function ResultsPage() {
  const [data, setData] = useState<ExperimentList | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);

  useEffect(() => {
    setError(null);
    listExperiments(page, PAGE_SIZE)
      .then(setData)
      .catch((e) => setError(errorText(e)));
  }, [page]);

  const items = data?.items ?? [];
  const pageCount = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;

  return (
    <div>
      <PageHeader
        title="Resultados"
        lede="Todos os experimentos, do mais recente ao mais antigo. Abra um para ver o ranking das combinações e cada resposta."
      />

      {error && (
        <Errata title="Não foi possível carregar os experimentos">
          {error}. Confira se a API está no ar e recarregue a página.
        </Errata>
      )}

      {!data && !error && <Loader aria-label="Carregando experimentos" />}

      {data && items.length === 0 && (
        <div className="ditto-empty">
          <h2 className="ditto-h2">Nenhum experimento ainda</h2>
          <p>
            Um experimento roda as suas perguntas em cada combinação de técnicas e mede a
            qualidade das respostas. Os resultados aparecem aqui.
          </p>
          <Button component={Link} to="/experiment" rightSection={<ArrowIcon />}>
            Criar experimento
          </Button>
        </div>
      )}

      {items.length > 0 && (
        <ul className="ditto-records" style={{ maxWidth: 900 }}>
          {items.map((exp) => (
            <li key={exp.id} className="ditto-record" data-link="true">
              <Link to={`/results/${exp.id}`} className="ditto-record-link">
                {exp.name}
              </Link>
              <span className="ditto-record-date">{formatDateTime(exp.created_at)}</span>
              <StatusTag status={exp.status} />
            </li>
          ))}
        </ul>
      )}

      {data && data.total > data.page_size && (
        <Group justify="center" mt="lg">
          <Pagination total={pageCount} value={page} onChange={setPage} size="sm" />
        </Group>
      )}
    </div>
  );
}
