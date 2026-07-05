# Tempo nos experimentos (início + duração) — Design

**Data:** 2026-07-05
**Autor:** Samuel (samuhs) + Claude

## Contexto

A tela de **Resultados** lista os experimentos (`GET /experiments`, hoje só `{id, name, status}`), e a tela de **detalhe** (`GET /experiments/{id}`) mostra status, progresso e a tabela de resultados. Não há indicação de **quando** um experimento começou nem de **quanto tempo levou** — informação útil para estimar experimentos maiores. O modelo `Experiment` já tem `created_at` (server default now) e `finished_at` (nullable, setado ao concluir/pausar/falhar), então não é preciso coluna nova nem migração. A lista atual também não tem paginação (retorna todos, ordenados por id desc).

## Objetivo

Mostrar a **data de início** de cada experimento na listagem (com paginação), e o **tempo de início + duração** na tela do experimento. A duração aparece ao vivo enquanto o experimento roda.

## Arquitetura

### Backend (`backend/app/api/experiments.py`)

- **`GET /experiments`** — passa a ser paginado e a incluir `created_at`:
  - Query params: `page: int = 1` (>=1), `page_size: int = 20` (1–100).
  - Resposta: `{"items": [{"id", "name", "status", "created_at"}], "total": int, "page": int, "page_size": int}` (envelope idêntico ao de `GET /dialogues`).
  - `created_at` em ISO (`e.created_at.isoformat()`); ordena por `Experiment.id.desc()`; `total` é a contagem antes da paginação.
- **`GET /experiments/{id}`** — inclui dois campos novos na resposta:
  - `"created_at": experiment.created_at.isoformat() if experiment.created_at else None`
  - `"finished_at": experiment.finished_at.isoformat() if experiment.finished_at else None`

"Início" = `created_at` (a background task começa logo após a criação; sem `started_at` separado).

### Frontend

- **Tipos (`api/types.ts`)**:
  - `ExperimentSummary` ganha `created_at: string`.
  - Novo `ExperimentList { items: ExperimentSummary[]; total: number; page: number; page_size: number }`.
  - `ExperimentDetail` ganha `created_at?: string` e `finished_at?: string`.
- **Cliente (`api/client.ts`)**: `listExperiments(page?, page_size?)` retorna `ExperimentList` (envelope). Constrói a query string com os params quando presentes.
- **Tela de Resultados (`pages/ResultsPage.tsx`)**: mostra a **data de início** formatada (pt-BR) em cada linha de experimento, e um controle de **paginação** (`Pagination` do Mantine) dirigido por `total`/`page_size`; mudar de página refaz a busca. (Ajustar o consumo de `listExperiments` para o novo envelope.)
- **Tela do experimento (`pages/ExperimentDetailPage.tsx`)**: no cabeçalho, além do status/progresso, mostra:
  - **"Iniciado em"** — `created_at` formatado.
  - **"Duração"** — para experimentos com `finished_at`: `finished_at − created_at`; para os que estão `running`/`pending`: tempo decorrido **ao vivo** (`Date.now() − created_at`), recalculado no polling que já roda a cada 3s. Formatado por um helper `formatDuration(ms) -> "1h 23m 45s"` (omite unidades zeradas à esquerda; ex.: `2m 10s`, `45s`).

### Formatação de duração

Helper puro `formatDuration(ms: number): string` (frontend), testável: horas/minutos/segundos, sem casas de ms; `< 1s` → `"0s"`.

## Tratamento de erros

- `created_at`/`finished_at` ausentes (dados antigos improváveis, mas defensivo) → o front mostra "—" na data e omite a duração.
- Página fora do intervalo na lista → o backend devolve `items: []` (offset além do total); o front trata lista vazia.
- Duração com `finished_at` anterior a `created_at` (não deve ocorrer) → `formatDuration` clampa para `0s`.

## Testes

**Backend (herméticos):**
- `GET /experiments`: envelope paginado (`items`/`total`/`page`/`page_size`), cada item traz `created_at`; respeita `page`/`page_size`.
- `GET /experiments/{id}`: resposta inclui `created_at` e `finished_at` (este último preenchido para experimento concluído).

**Frontend (vitest):**
- `formatDuration`: casos (`45s`, `2m 10s`, `1h 23m 45s`, `0s`).
- `ResultsPage`: renderiza a data de início e o controle de paginação; trocar de página chama `listExperiments` com a página nova.
- `ExperimentDetailPage`: experimento concluído mostra a duração calculada; experimento rodando mostra a duração ao vivo (decorrido).

## Decisões e trade-offs

- **`created_at` como "início":** evita coluna/migração; a diferença para o momento real de start é desprezível (a task roda logo após criar).
- **Paginação server-side no mesmo padrão dos diálogos:** consistência e escalabilidade da lista conforme os experimentos crescem. Muda o formato de resposta de `GET /experiments` (lista → envelope); todos os consumidores no front são atualizados.
- **Duração ao vivo via o polling existente:** sem timer novo; a tela já refaz `getExperiment` a cada 3s enquanto roda, então o decorrido atualiza junto.
- **Duração só do experimento inteiro** (não por combinação/run): é o sinal que importa para estimar tempo total; granularidade por run fica para depois se necessário.

## Fora de escopo

- Coluna `started_at` separada.
- Duração por combinação (`ExperimentRun`) ou por questão.
- Estimativa preditiva de tempo restante (ETA); mostramos o decorrido, não a projeção.
