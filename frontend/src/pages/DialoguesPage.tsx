import { Button, Loader, Pagination, Select, TextInput } from "@mantine/core";
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { listDialogues } from "../api/client";
import type { DialogueList, DialogueListParams } from "../api/types";
import { Errata, errorText } from "../components/Notice";
import { PageHeader } from "../components/PageHeader";
import { ArrowIcon } from "../components/icons";
import { formatDateTime } from "../utils/duration";

const PAGE_SIZE = 20;

const RATED_OPTIONS = [
  { value: "all", label: "Todas" },
  { value: "rated", label: "Avaliadas" },
  { value: "unrated", label: "Não avaliadas" },
];
const SORT_OPTIONS = [
  { value: "recent", label: "Mais recentes" },
  { value: "oldest", label: "Mais antigos" },
  { value: "rating_desc", label: "Maior nota" },
  { value: "rating_asc", label: "Menor nota" },
];

export function DialoguesPage() {
  const navigate = useNavigate();
  const [data, setData] = useState<DialogueList | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const [date, setDate] = useState<string>("");
  const [rated, setRated] = useState<string>("all");
  const [sort, setSort] = useState<string>("recent");
  const [page, setPage] = useState(1);

  useEffect(() => {
    setLoading(true);
    setError(null);
    const params: DialogueListParams = {
      page,
      page_size: PAGE_SIZE,
      rated: rated as DialogueListParams["rated"],
      sort: sort as DialogueListParams["sort"],
    };
    if (date) params.date = date;
    listDialogues(params)
      .then((d) => {
        setData(d);
        setLoading(false);
      })
      .catch((e) => {
        setError(errorText(e));
        setLoading(false);
      });
  }, [date, rated, sort, page]);

  const items = data?.items ?? [];
  const pageCount = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;
  const filtering = date !== "" || rated !== "all";

  return (
    <div>
      <PageHeader
        title="Diálogos salvos"
        lede="Leia cada conversa salva e dê uma nota de 0 a 10. As notas ajudam a comparar configurações na prática."
      />

      <div className="ditto-filters" style={{ maxWidth: 640 }}>
        <TextInput
          label="Data"
          type="date"
          value={date}
          onChange={(e) => {
            setDate(e.currentTarget.value);
            setPage(1);
          }}
        />
        <Select
          label="Avaliação"
          data={RATED_OPTIONS}
          value={rated}
          onChange={(v) => {
            setRated(v ?? "all");
            setPage(1);
          }}
          allowDeselect={false}
        />
        <Select
          label="Ordenar por"
          data={SORT_OPTIONS}
          value={sort}
          onChange={(v) => {
            setSort(v ?? "recent");
            setPage(1);
          }}
          allowDeselect={false}
        />
      </div>

      {error && (
        <Errata title="Não foi possível carregar os diálogos">
          {error}. Recarregue a página.
        </Errata>
      )}

      {loading && <Loader aria-label="Carregando diálogos" />}

      {!loading && items.length === 0 && !error && (
        <div className="ditto-empty">
          <h2 className="ditto-h2">{filtering ? "Nenhum diálogo com esses filtros" : "Nenhum diálogo salvo ainda"}</h2>
          <p>
            {filtering
              ? "Mude a data ou a avaliação para ver outros diálogos."
              : "Na Conversa, use “Salvar diálogo” ao final de uma conversa. Ela aparece aqui para você avaliar."}
          </p>
          {!filtering && (
            <Button component={Link} to="/chat" rightSection={<ArrowIcon />}>
              Ir para a conversa
            </Button>
          )}
        </div>
      )}

      {!loading && items.length > 0 && (
        <>
          <div className="ditto-table-wrap">
            <table className="ditto-table">
              <thead>
                <tr>
                  <th>Data</th>
                  <th>Configuração</th>
                  <th>Persona</th>
                  <th>Início da conversa</th>
                  <th className="ditto-num">Mensagens</th>
                  <th className="ditto-num">Nota</th>
                </tr>
              </thead>
              <tbody>
                {items.map((it) => (
                  <tr key={it.id} data-clickable="true" onClick={() => navigate(`/dialogues/${it.id}`)}>
                    <td style={{ whiteSpace: "nowrap" }}>
                      <Link to={`/dialogues/${it.id}`} onClick={(e) => e.stopPropagation()}>
                        {formatDateTime(it.created_at)}
                      </Link>
                    </td>
                    <td>{it.name ?? "—"}</td>
                    <td>{it.persona ?? "—"}</td>
                    <td>
                      <span className="ditto-clip ditto-muted">{it.preview ?? "—"}</span>
                    </td>
                    <td className="ditto-num">{it.message_count}</td>
                    <td className="ditto-num">
                      {it.rating === null ? (
                        <span className="ditto-muted">não avaliado</span>
                      ) : (
                        <b>{it.rating}</b>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="ditto-table-foot">
            <span className="ditto-muted" style={{ fontSize: 14 }}>
              {data?.total ?? 0} {data?.total === 1 ? "diálogo" : "diálogos"}
            </span>
            <Pagination total={pageCount} value={page} onChange={setPage} size="sm" />
          </div>
        </>
      )}
    </div>
  );
}
