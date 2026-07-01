# Gestão de Prompts — Design

**Data:** 2026-07-01
**Autor:** Samuel (samuhs) + Claude

## Objetivo

Permitir visualizar e editar os prompts usados por cada técnica de RAG (e pelo retriever `multi_query`), e registrar em snapshot no banco os prompts efetivamente usados por cada experimento no momento do disparo — para reprodutibilidade e para permitir alterar prompts em testes futuros.

## Motivação

Hoje os prompts são constantes hardcoded espalhadas no código:

- `app/core/rag/naive.py` → `_PROMPT` (1 prompt)
- `app/core/rag/agentic.py` → `_DECIDE_PROMPT`, `_ANSWER_PROMPT` (2 prompts)
- `app/core/retrieval/multi_query.py` → `_PROMPT` (1 prompt)

Não é possível ver, comparar ou alterar esses prompts sem editar código e rebuildar, nem saber qual prompt um experimento passado usou.

## Escopo

Técnicas cobertas: **naive**, **agentic**, **multi_query**. Métricas de avaliação (ragas) ficam **fora** deste escopo.

## Arquitetura

### 1. Armazenamento dos prompts em arquivos

Nova pasta versionada em git:

```
backend/prompts/
  naive/
    answer.md
  agentic/
    decide.md
    answer.md
  multi_query/
    generate.md
```

Cada `.md` contém o template com placeholders no estilo `str.format` (ex.: `{context}`, `{question}`, `{n}`). O conteúdo inicial de cada arquivo é exatamente o texto hoje hardcoded (migrado 1:1).

### 2. Manifesto e loader de prompts

Novo módulo `app/core/prompts/` com:

**Manifesto** (`PROMPT_SPECS`): declara, por técnica, os prompts existentes e os placeholders **obrigatórios** de cada um:

```python
PROMPT_SPECS: dict[str, dict[str, set[str]]] = {
    "naive":       {"answer":   {"context", "question"}},
    "agentic":     {"decide":   {"question", "context"},
                    "answer":    {"context", "question"}},
    "multi_query": {"generate": {"n", "question"}},
}
```

**Defaults embutidos** (`DEFAULT_PROMPTS`): dict com o texto de cada prompt, usado como fallback quando o arquivo `.md` não existe (evita quebra).

**Funções:**

- `prompts_dir() -> Path` — raiz configurável (default `backend/prompts`), sobreponível por env `PROMPTS_DIR` para testes.
- `load_prompt(technique, key) -> str` — lê o `.md`; se ausente, retorna o default embutido.
- `load_technique(technique) -> dict[str, str]` — todos os prompts da técnica.
- `load_all() -> dict[str, dict[str, str]]` — todas as técnicas do manifesto.
- `save_prompt(technique, key, text) -> None` — valida placeholders e grava o `.md` (cria a pasta se preciso).
- `validate_placeholders(technique, key, text) -> None` — levanta `ValueError` se faltar algum placeholder obrigatório; placeholders extras são permitidos.

Técnica/chave fora do manifesto levantam `KeyError` (tratado como 404 na API).

### 3. Injeção dos prompts nas técnicas

Os construtores passam a aceitar os prompts por parâmetro, mantendo compatibilidade (default = carregar dos arquivos):

- `NaiveRAG(retriever, llm, prompts: dict[str, str] | None = None)` — usa `prompts["answer"]`; se `None`, `load_technique("naive")`.
- `AgenticRAG(retriever, llm, prompts: dict[str, str] | None = None, max_steps=3)` — usa `prompts["decide"]` e `prompts["answer"]`.
- `MultiQueryRetriever(..., prompts: dict[str, str] | None = None)` — usa `prompts["generate"]`.

As constantes `_PROMPT`/`_DECIDE_PROMPT`/`_ANSWER_PROMPT` são removidas dos arquivos das técnicas e passam a viver como defaults no módulo de prompts.

`build_rag(name, **kwargs)` e `build_retriever(...)` já repassam `**kwargs`, então aceitam `prompts=...` sem mudança de assinatura.

### 4. Snapshot no disparo do experimento

Em `POST /experiments` (`create_experiment`), após validar o config:

1. Para cada RAG em `config.rags` e, se `multi_query` estiver em `config.retrievers`, para `multi_query`, carrega os prompts atuais via `load_technique`.
2. Monta `snapshot = {technique: {key: text}}`.
3. Grava dentro do JSON já existente: `experiment.config["prompts"] = snapshot` (sem migração de schema — a coluna `config` já é JSON).

No orchestrator (`run_experiment`), lê `experiment.config["prompts"]` e injeta:

- `deps.rag_factory(rag_name, retriever=..., llm=..., prompts=snapshot.get(rag_name))`
- `_build_retriever(...)` passa `prompts=snapshot.get("multi_query")` quando `name == "multi_query"`.

Se o snapshot estiver ausente (experimentos criados antes desta feature, ou config sem prompts), as técnicas caem no default (carregam dos arquivos), preservando o comportamento atual.

### 5. Endpoints da API

Novo router `app/api/prompts.py`:

- `GET /prompts` → `{ technique: { key: {"text": str, "required_placeholders": [str]} } }` para todas as técnicas do manifesto (texto atual dos arquivos).
- `PUT /prompts/{technique}/{key}` com body `{"text": str}` → valida placeholders e grava; retorna `{"technique", "key", "text"}`. Erros: 404 (técnica/chave inexistente), 422 (placeholder obrigatório ausente, com mensagem informativa).

Alteração em `GET /experiments/{id}` (`get_experiment`): incluir `"prompts": cfg.get("prompts")` na resposta (pode ser `null` para experimentos antigos).

### 6. Persistência em Docker (bind mount)

O `Dockerfile` faz `COPY . .` a partir de `backend/`, então `backend/prompts/` é embutido na imagem em `/app/prompts` no build. Porém edições feitas pela UI gravam no filesystem do container — efêmeras (perdidas em `docker compose up --build`) e invisíveis para o git do host.

Para que a edição pela UI seja **durável e versionável no git**, o serviço `api` no `docker-compose.yml` recebe um bind mount:

```yaml
  api:
    build: ./backend
    volumes:
      - ./backend/prompts:/app/prompts
    ...
```

Assim, `PUT /prompts/...` grava em `./backend/prompts/...` no host (versionável via git, sobrevive a rebuilds). O loader resolve `prompts_dir()` como `/app/prompts` no container (raiz do backend + `prompts`), com override por env `PROMPTS_DIR` para testes.

### 7. Frontend

**Tela do experimento (`/results/:id`)** — acima da barra de filtros, uma linha de botões:

- Um botão por RAG presente no experimento; + botão `multi_query` se o experimento usou esse retriever. As técnicas presentes são derivadas do snapshot `detail.prompts` (chaves do objeto).
- Clicar abre um **modal read-only** com os prompts daquela técnica (cada chave: título + bloco monoespaçado com o texto). Cabeçalho do modal: "Prompts usados neste experimento".
- Se `detail.prompts` for `null`/vazio (experimento antigo), a linha de botões é substituída por um aviso discreto: "Prompts não registrados para este experimento."

**Nova página "Prompts" (`/prompts`, item no menu lateral)**:

- Lista as técnicas do `GET /prompts`. Para cada prompt: um `Textarea` editável com o texto atual, a lista de placeholders obrigatórios exibida abaixo, e um botão "Salvar" que chama `PUT /prompts/{technique}/{key}`.
- Sucesso: feedback verde ("Prompt salvo"). Erro de validação (422): mostra a mensagem do backend (ex.: "faltando placeholder obrigatório: {context}").
- Estas edições afetam apenas experimentos **futuros** (a tela do experimento é histórica).

**Tipos/cliente novos:** `getPrompts()`, `savePrompt(technique, key, text)`; tipo `ExperimentDetail.prompts?: Record<string, Record<string, string>>`.

## Tratamento de erros

- Arquivo `.md` ausente → default embutido (sem erro).
- `save_prompt` com placeholder faltando → `ValueError` → 422 com mensagem.
- Técnica/chave inválida → `KeyError` → 404.
- Snapshot ausente no experimento → técnicas usam default; frontend mostra aviso.

## Testes

**Backend:**
- Loader: `load_prompt` lê arquivo existente e cai no default quando ausente; `save_prompt` grava e relê; `validate_placeholders` aceita extras e rejeita faltantes (usar `PROMPTS_DIR` temporário via tmp_path).
- Injeção: `NaiveRAG`/`AgenticRAG` usam o prompt fornecido em `prompts=` (verificar via LLM fake que captura o prompt recebido); `MultiQueryRetriever` idem.
- Snapshot: `POST /experiments` grava `config["prompts"]` com as técnicas do config; `GET /experiments/{id}` retorna `prompts`.
- API: `GET /prompts` retorna manifesto + textos; `PUT` grava; `PUT` com placeholder faltando retorna 422.

**Frontend:**
- Tela do experimento: com `prompts` no mock, renderiza um botão por técnica e o modal mostra o texto; sem `prompts`, mostra o aviso.
- Página Prompts: carrega os prompts, edita um textarea e ao salvar chama `savePrompt` com os args certos.

## Decisões e trade-offs

- **Snapshot em `config["prompts"]`** (JSON existente) em vez de nova coluna/tabela: evita migração; `create_all` não altera tabelas existentes. Custo: fica aninhado no config.
- **Edição em página global** separada da tela do experimento (histórica/read-only): mantém a semântica de que o experimento reflete o que rodou, e centraliza a edição.
- **Placeholders validados na escrita**: impede salvar um prompt que quebraria a técnica em runtime.
- **Defaults embutidos** garantem funcionamento mesmo sem os arquivos (ou em ambientes onde a pasta não foi copiada).

## Fora de escopo

- Versionamento/histórico de edições de prompt dentro da app (o git dos `.md` cobre isso).
- Prompts de métricas de avaliação (ragas).
- Autenticação/permissão para editar prompts (app é de uso local/pesquisa).
