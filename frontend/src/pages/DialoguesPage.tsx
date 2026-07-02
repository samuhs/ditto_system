import { Alert, Loader, Pagination, Select, Text, TextInput } from "@mantine/core";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { listDialogues } from "../api/client";
import type { DialogueList, DialogueListParams } from "../api/types";
import { PageHeader } from "../components/PageHeader";

const PAGE_SIZE = 20;

const RATED_OPTIONS = [
  { value: "all", label: "Todas" },
  { value: "rated", label: "Avaliadas" },
  { value: "unrated", label: "Não avaliadas" },
];
const SORT_OPTIONS = [
  { value: "recent", label: "Mais recentes" },
  { value: "oldest", label: "Mais antigos" },
  { value: "rating_desc", label: "Nota ↓" },
  { value: "rating_asc", label: "Nota ↑" },
];

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("pt-BR");
}

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
        setError(String(e));
        setLoading(false);
      });
  }, [date, rated, sort, page]);

  const items = data?.items ?? [];
  const pageCount = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;

  return (
    <div>
      <PageHeader
        eyebrow="Passo 05 · Avaliar"
        title="Avaliação de diálogos"
        subtitle="Leia os diálogos salvos e dê uma nota de 0 a 10. Filtre por data, por avaliadas/não avaliadas e ordene pela nota."
      />

      <div className="ditto-filter-bar">
        <TextInput
          label="Data"
          type="date"
          value={date}
          onChange={(e) => {
            setDate(e.currentTarget.value);
            setPage(1);
          }}
          size="xs"
        />
        <Select
          label="Avaliação"
          data={RATED_OPTIONS}
          value={rated}
          onChange={(v) => {
            setRated(v ?? "all");
            setPage(1);
          }}
          size="xs"
          allowDeselect={false}
        />
        <Select
          label="Ordenar"
          data={SORT_OPTIONS}
          value={sort}
          onChange={(v) => {
            setSort(v ?? "recent");
            setPage(1);
          }}
          size="xs"
          allowDeselect={false}
        />
      </div>

      {error && (
        <Alert color="red" variant="light" title="Erro" mb="lg" radius="lg" maw={760}>
          {error}
        </Alert>
      )}

      {loading && (
        <div style={{ display: "flex", justifyContent: "center", padding: "48px 0" }}>
          <Loader size="md" color="#05dbf2" />
        </div>
      )}

      {!loading && items.length === 0 && !error && (
        <p className="ditto-empty">Nenhum diálogo encontrado.</p>
      )}

      {!loading && items.length > 0 && (
        <>
          <div className="ditto-table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Data</th>
                  <th>Config</th>
                  <th>Persona</th>
                  <th>Nº msgs</th>
                  <th>Nota</th>
                </tr>
              </thead>
              <tbody>
                {items.map((it) => (
                  <tr
                    key={it.id}
                    className="ditto-row"
                    onClick={() => navigate(`/dialogues/${it.id}`)}
                  >
                    <td>{formatDate(it.created_at)}</td>
                    <td>{it.name ?? "—"}</td>
                    <td>{it.persona ?? "—"}</td>
                    <td>{it.message_count}</td>
                    <td>
                      {it.rating === null ? (
                        <span className="ditto-chip" style={{ color: "#8892b0" }}>
                          não avaliado
                        </span>
                      ) : (
                        <span className="ditto-chip" style={{ color: "#07f285" }}>
                          {it.rating}
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="ditto-table-foot">
            <Text size="xs" c="dimmed">
              {data?.total ?? 0} diálogo(s)
            </Text>
            <Pagination
              total={pageCount}
              value={page}
              onChange={setPage}
              size="sm"
              color="violet"
            />
          </div>
        </>
      )}
    </div>
  );
}
