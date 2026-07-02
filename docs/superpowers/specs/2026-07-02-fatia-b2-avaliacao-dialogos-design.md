# Fatia B2 — Avaliação de diálogos — Design

**Data:** 2026-07-02
**Autor:** Samuel (samuhs) + Claude

## Contexto

O sistema (Ditto) foi fatiado em **A** (descoberta: ingest → experimento → resultados, completa), **B** (conversacional) e **C** (fine-tuning). A Fatia B foi dividida em **B1 — Conversa** (agente LangGraph + personas + salvar diálogo, completa e deployada) e **B2 — Avaliação de diálogo** (este spec).

O B1 já persiste diálogos: existem as tabelas `dialogue` (`id`, `config_snapshot` JSON, `created_at`) e `dialogue_message` (`id`, `dialogue_id`, `role`, `content`, `position`), e o endpoint `POST /dialogues` que os grava. Falta o lado de **leitura e avaliação humana** dos diálogos salvos.

Referências: `Doutorado Base architecture.md`, `HANDOFF.md`, `docs/superpowers/specs/2026-07-01-fatia-b1-conversa-design.md`.

## Objetivo

Uma tela onde o usuário lista os diálogos salvos, abre um diálogo para ler a conversa inteira, e atribui uma **nota de 0 a 10** (avaliação humana, reeditável). A lista traz **data de salvamento**, **paginação** (preparada para muitos diálogos) e **filtros** (por dia, por avaliadas/não avaliadas) e **ordenação** (recentes, antigos, nota crescente/decrescente). As notas alimentarão a Fatia C (fine-tuning) no futuro.

## Escopo (B2)

Dentro: coluna de nota no diálogo; endpoints de listagem paginada com filtros/ordenação, detalhe e gravação de nota; duas telas (lista + detalhe).

Fora (futuro): avaliação por múltiplos critérios ou comentário em texto; export dos diálogos avaliados; deletar diálogos; edição/criação de diálogo pela tela de avaliação; fine-tuning (Fatia C).

## Arquitetura

### 1. Dados

Duas colunas novas em `dialogue` (`backend/app/core/db/models.py`):

| coluna | tipo | nota |
|---|---|---|
| rating | int, nullable | nota humana 0–10; `NULL` = não avaliado |
| rated_at | datetime, nullable | quando a nota foi definida/atualizada; `NULL` enquanto não avaliado |

O schema é criado via `Base.metadata.create_all()`, que **não** altera tabelas já existentes. Bancos já deployados precisam de ALTER manual:

```sql
ALTER TABLE dialogue ADD COLUMN IF NOT EXISTS rating INTEGER;
ALTER TABLE dialogue ADD COLUMN IF NOT EXISTS rated_at TIMESTAMP;
```

### 2. Endpoints da API

Adicionados ao router existente `backend/app/api/chat.py` (onde já vive `POST /dialogues`).

**`GET /dialogues`** — lista paginada. Query params (todos opcionais):
- `page: int = 1` (>= 1), `page_size: int = 20` (1–100).
- `date: str | None` — formato `YYYY-MM-DD`; filtra diálogos cujo `created_at` cai naquele dia. Data inválida → 422.
- `rated: str = "all"` — um de `all` | `rated` (rating não nulo) | `unrated` (rating nulo). Valor inválido → 422.
- `sort: str = "recent"` — um de `recent` (`created_at` desc) | `oldest` (`created_at` asc) | `rating_asc` | `rating_desc`. Valor inválido → 422.
  - Em `rating_asc`/`rating_desc`, diálogos não avaliados (`rating IS NULL`) vão sempre **por último**, com desempate por `created_at` desc.

Resposta:
```json
{
  "items": [
    {
      "id": 5,
      "created_at": "2026-07-02T13:40:00",
      "rating": 8,
      "name": "guia-viagem",
      "persona": "travel_guide",
      "message_count": 6,
      "preview": "Quais praias visitar em..."
    }
  ],
  "total": 42,
  "page": 1,
  "page_size": 20
}
```
- `name` e `persona` vêm de `config_snapshot` (`.get("name")`, `.get("persona")`; ausentes → `null`).
- `message_count` = número de `dialogue_message` do diálogo.
- `preview` = `content` da primeira mensagem com `role == "user"` (menor `position`), truncado em 80 caracteres; se não houver, `null`.
- `total` = total de diálogos que casam com os filtros (antes da paginação), para o front calcular o número de páginas.

**`GET /dialogues/{id}`** — detalhe. 404 se inexistente. Resposta:
```json
{
  "id": 5,
  "created_at": "2026-07-02T13:40:00",
  "rating": 8,
  "config_snapshot": { "name": "...", "base": "...", "chunking": "...", "embedding": "...", "retriever": "...", "llm": "...", "persona": "..." },
  "messages": [ { "role": "user", "content": "..." }, { "role": "assistant", "content": "..." } ]
}
```
- `messages` ordenadas por `position` ascendente.

**`PUT /dialogues/{id}/rating`** — grava/atualiza a nota. Body `{ "rating": int }`:
- `rating` fora de 0–10 → 422.
- 404 se o diálogo não existir.
- Ao gravar, seta `rating` e `rated_at = now()`.
- Resposta: `{ "id": 5, "rating": 8 }`.

Todos usam a dependência `get_chat_deps()` / `deps.session_factory()` já existente, para manter os testes herméticos (SQLite, sem rede).

### 3. Frontend

Duas telas novas + item no `Sidebar` ("Avaliação de diálogos"), roteadas em `frontend/src/App.tsx`. Espelha o padrão da tela de resultados (lista → página de detalhe).

**Lista (`/dialogues`)** — `frontend/src/pages/DialoguesPage.tsx`:
- Barra de filtros no topo: seletor de **data** (input `type="date"` do Mantine, limpável), `Select` de **avaliação** (Todas / Avaliadas / Não avaliadas), `Select` de **ordenação** (Mais recentes / Mais antigos / Nota ↑ / Nota ↓).
- Tabela com colunas: **Data** (formatada), **Config** (`name`), **Persona**, **Nº msgs**, **Nota** (badge com o número, ou badge cinza "não avaliado"). Preview da 1ª pergunta como texto secundário na linha (opcional, ajuda a identificar).
- Clique na linha → navega para `/dialogues/:id`.
- **Paginação** embaixo (`Pagination` do Mantine), dirigida por `total`/`page_size`. Mudar filtro/ordenação volta para a página 1.
- Estado dos filtros/página é local (React state); cada mudança refaz o `GET /dialogues` com os params.

**Detalhe (`/dialogues/:id`)** — `frontend/src/pages/DialoguePage.tsx`:
- Cabeçalho com resumo da config (persona, base, rag/llm) a partir de `config_snapshot`, e a data.
- Bolhas user/assistant renderizando `messages` (reusa o estilo visual da tela de conversa).
- Bloco de avaliação: `NumberInput` 0–10 (pré-preenchido com o `rating` atual, se houver) + botão **Salvar nota**; chama `PUT /dialogues/:id/rating` e mostra feedback. Reeditável.
- Botão "voltar" para a lista.

Cliente e tipos novos em `frontend/src/api/`:
- `client.ts`: `listDialogues(params)`, `getDialogue(id)`, `saveDialogueRating(id, rating)`.
- `types.ts`: `DialogueListItem`, `DialogueList` (`items`, `total`, `page`, `page_size`), `DialogueDetail`, `DialogueFilters`.

## Tratamento de erros

- `date` fora do formato `YYYY-MM-DD`, `rated`/`sort` inválidos, `rating` fora de 0–10 → 422 com mensagem clara; o front trata os selects/inputs para só enviar valores válidos.
- `GET /dialogues/{id}` e `PUT .../rating` com id inexistente → 404; o front mostra estado "não encontrado".
- Lista vazia (nenhum diálogo ou nenhum casa com o filtro) → `items: []`, `total: 0`; o front mostra um estado vazio.

## Testes

**Backend (hermético — SQLite, sem rede):**
- `GET /dialogues`: paginação (respeita `page`/`page_size`, `total` correto); filtro `date` (só o dia certo); filtro `rated` (`rated`/`unrated`); cada `sort` (incl. não avaliados por último em `rating_asc`/`rating_desc`); item traz `message_count`, `preview` (1ª msg de user, truncado) e `name`/`persona` do snapshot; params inválidos → 422.
- `GET /dialogues/{id}`: mensagens em ordem de `position`; snapshot presente; 404 inexistente.
- `PUT /dialogues/{id}/rating`: grava `rating` + `rated_at`; reeditar sobrescreve; 0–10 válidos, fora disso 422; 404 inexistente.

**Frontend (vitest, mocks do client):**
- Lista: carrega e renderiza itens; trocar filtro `rated`/`sort`/`date` refaz a chamada com os params certos e volta para página 1; paginação chama com a página nova.
- Detalhe: carrega mensagens + resumo da config; `NumberInput` pré-preenchido com o rating; salvar chama `saveDialogueRating(id, nota)` e reflete o feedback.

## Decisões e trade-offs

- **Paginação server-side (page/page_size + total):** preparada para muitos diálogos desde já, sem carregar tudo no cliente. `total` deixa o front montar o controle de páginas.
- **Nota só numérica (0–10), sem comentário:** decisão do usuário; mantém a avaliação simples. Comentário/critérios múltiplos podem entrar depois sem quebrar o schema.
- **`rated_at` separado de `created_at`:** permite auditar quando a avaliação aconteceu, independente de quando o diálogo foi salvo. Barato de adicionar.
- **Não avaliados por último na ordenação por nota:** ordenar por nota é para comparar avaliações; jogar os `NULL` para o fim evita que apareçam no topo do `rating_asc`.
- **Reutiliza `chat.py` e `get_chat_deps`:** diálogos são domínio de chat; não vale um router novo. Mantém a suíte sem rede (SQLite, sem Qdrant/Postgres).
- **Lista → página de detalhe (não modal):** espelha a tela de resultados de experimentos, consistência de navegação.

## Fora de escopo

- Comentário em texto / avaliação multi-critério.
- Export dos diálogos avaliados (dataset para fine-tuning) — Fatia C.
- Deletar ou editar diálogos pela tela de avaliação.
- Streaming, memória de longo prazo (herdados do B1).
