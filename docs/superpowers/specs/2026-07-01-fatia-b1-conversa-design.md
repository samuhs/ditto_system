# Fatia B1 — Conversa (agente conversacional) — Design

**Data:** 2026-07-01
**Autor:** Samuel (samuhs) + Claude

## Contexto

O sistema (Ditto) foi fatiado em: **Fatia A** (núcleo de descoberta: ingest → experimento → resultados, **completa**), **Fatia B** (conversacional) e **Fatia C** (fine-tuning). Este spec cobre a **primeira sub-fatia da Fatia B (B1 — Conversa)**. A segunda (B2 — avaliação de diálogo) terá spec/plano próprios depois, pois depende dos diálogos que o B1 gera.

Referências: `Doutorado Base architecture.md` (raiz) e `HANDOFF.md`.

## Objetivo

Um agente conversacional que responde o usuário em diálogo (baseline: **guia de viagem**), consultando a RAG da Fatia A quando necessário, com **persona trocável** e **memória curta** (por diálogo). O usuário conversa numa tela, e ao final decide **salvar ou não** o diálogo (os salvos serão avaliados no B2).

## Escopo (B1)

Dentro: configuração de chat persistida, personas trocáveis, agente ReAct (LangGraph) com tool de busca, endpoint de conversa (stateless, request-response), persistência de diálogo ao salvar, e duas telas (configuração de chat + conversa).

Fora (B2/futuro): listar/ler/avaliar diálogos; streaming de tokens; edição de persona pela UI; fine-tuning.

## Arquitetura

### 1. Agente conversacional (LangGraph ReAct)

Módulo novo `backend/app/core/chat/`:

- **`agent.py`** — constrói e roda o agente:
  - `build_chat_model(llm: str)` → um chat model LangChain com tool-calling. Para `"gemini"`: `ChatGoogleGenerativeAI(model=<settings/model>, google_api_key=...)`. Outros nomes levantam `KeyError` (tratado como 400 na API). (Custom LLM fica para depois.)
  - `build_retrieve_tool(retriever)` → uma tool LangChain `retrieve(query: str) -> str` que chama `retriever.retrieve(query)` e devolve `format_context(...)` (reusa `app.core.rag.base.format_context`). Docstring da tool orienta o agente a usá-la para buscar informação sobre o domínio.
  - `run_agent(persona: str, retriever, chat_model, messages: list[ChatMessage]) -> ChatTurnResult`:
    - monta `create_react_agent(chat_model, tools=[retrieve_tool], prompt=persona)` (LangGraph prebuilt);
    - converte `messages` (nossos `{role, content}`) para `HumanMessage`/`AIMessage`;
    - `result = agent.invoke({"messages": lc_messages})`;
    - `reply` = conteúdo da última `AIMessage`; `contexts` = textos das `ToolMessage` produzidas neste turno (best-effort, para transparência).
  - `ChatTurnResult` = dataclass `{answer: str, contexts: list[str]}`.

- **Injeção de dependências** (para testes hermenêuticos, no estilo `ExperimentDeps`): `ChatDeps` dataclass em `backend/app/core/chat/deps.py`:
  ```python
  @dataclass
  class ChatDeps:
      store: QdrantStore
      session_factory: Callable[[], Session]
      chat_model_factory: Callable[[str], object] = build_chat_model
      retriever_factory: Callable = build_retriever
      agent_runner: Callable[..., ChatTurnResult] = run_agent
  ```
  Testes injetam um `agent_runner`/`chat_model_factory` fake (sem rede). Produção usa os defaults reais.

Nova dependência: **`langgraph`** em `backend/pyproject.toml` e instalada na imagem Docker (grupo padrão).

### 2. Personas trocáveis

Reaproveita o padrão file-backed de prompts. Módulo `backend/app/core/personas/loader.py`:

- Personas vivem em `backend/prompts/personas/<nome>.md` (o bind mount `./backend/prompts:/app/prompts` já criado na feature de prompts torna-as duráveis/versionáveis).
- `personas_dir()` → `prompts_dir() / "personas"` (reusa `app.core.prompts.prompts_dir`, com override por env em testes).
- `DEFAULT_PERSONAS: dict[str, str]` — fallback embutido; baseline `travel_guide` (system prompt de guia de viagem em PT-BR) e um `assistant` genérico.
- `list_personas() -> list[str]` — nomes de `DEFAULT_PERSONAS` unidos aos `.md` presentes no diretório, ordenados.
- `load_persona(name) -> str` — lê o `.md`; se ausente, usa o default; se o nome não existir em lugar nenhum, `KeyError`.
- Arquivos iniciais: `backend/prompts/personas/travel_guide.md`, `backend/prompts/personas/assistant.md` (conteúdo = os defaults).

Personas não têm placeholders obrigatórios (são system prompts livres) — sem validação de placeholder.

### 3. Configuração de chat (persistida)

Nova tabela `chat_config` (`backend/app/core/db/models.py`):

| coluna | tipo | nota |
|---|---|---|
| id | int PK | |
| name | str(120) unique | nome da config |
| base | str(120) | base ingerida |
| chunking | str(60) | técnica de corte (define a coleção) |
| embedding | str(60) | modelo de embedding (define a coleção) |
| retriever | str(60) | retriever usado como tool |
| llm | str(60) | modelo do agente (default "gemini") |
| persona | str(120) | nome da persona |
| created_at | datetime server_default now | |

A coleção usada é `collection_name(base, chunking, embedding)` (reusa `app.core.vectorstore.qdrant.collection_name`).

### 4. Conversa stateless + persistência de diálogo

- O **frontend guarda as mensagens** da conversa e envia o histórico a cada turno. "Nova conversa" = estado novo no front (memória curta, limpa por diálogo). O backend é **stateless** por request: reconstrói o agente e responde.
- **Salvar diálogo**: só ao final, quando o usuário escolhe. Tabelas:
  - `dialogue` — id PK, `config_snapshot` (JSON com a config usada), created_at.
  - `dialogue_message` — id PK, dialogue_id FK, `role` ("user"/"assistant"), `content` (str), `position` (int, ordem). Relação `dialogue.messages` (cascade delete).
  - (A avaliação humana — rating — é coluna do B2; não entra aqui.)

### 5. Endpoints da API

Router novo `backend/app/api/chat.py`:

- `GET /personas` → `{"personas": [str, ...]}` (de `list_personas`).
- `POST /chat-configs` (body: name, base, chunking, embedding, retriever, llm?, persona) → cria; 409 se nome duplicado. `GET /chat-configs` → lista. `DELETE /chat-configs/{id}` → remove (404 se inexistente).
- `POST /chat` → body `{config_id: int, messages: [{role, content}, ...]}`:
  - carrega a `chat_config` (404 se inexistente);
  - monta embedder (`build_embedder(embedding)`), retriever (`_build_retriever`-equivalente; injeta llm em `multi_query`), chat model (`chat_model_factory(llm)`), persona (`load_persona(persona)`);
  - `result = deps.agent_runner(persona_text, retriever, chat_model, messages)`;
  - retorna `{"reply": result.answer, "contexts": result.contexts}`.
  - Erros de modelo/persona desconhecidos → 400 com mensagem.
- `POST /dialogues` → body `{config_id: int, messages: [{role, content}, ...]}` → persiste `dialogue` (com `config_snapshot` da config) + `dialogue_message`s; retorna `{"id": int}`. (Listagem/leitura fica no B2.)

Dependência FastAPI `get_chat_deps()` → `ChatDeps(store=QdrantStore(), session_factory=SessionLocal)` (defaults reais), sobreponível em teste via `app.dependency_overrides`.

### 6. Frontend

Novas telas + navegação (itens no `Sidebar`):

- **Configurações de chat** (`/chat-configs`):
  - Form: nome, `Select` de base (de `/options`), chunking, embedding, retriever (de `/options`), llm (de `/options.llms`), persona (de `/personas`). Botão "Criar".
  - Lista as configs existentes (`GET /chat-configs`) com botão remover.
- **Conversa** (`/chat`):
  - `Select` para escolher a config; área de mensagens (bolhas user/assistant); input + enviar; botão "Nova conversa" (limpa o estado); ao ter ao menos 1 troca, botão "Salvar diálogo" (chama `POST /dialogues`) com feedback.
  - Estado das mensagens é local (React state); cada envio faz `POST /chat` com o histórico atual + a nova mensagem e adiciona a resposta.

Cliente e tipos novos em `frontend/src/api/`: `getPersonas`, `listChatConfigs`, `createChatConfig`, `deleteChatConfig`, `sendChat`, `saveDialogue`; tipos `ChatConfig`, `ChatMessage`, `ChatTurn`.

## Tratamento de erros

- LLM/persona desconhecidos → 400/`KeyError` mapeado.
- Coleção inexistente (base/chunking/embedding sem ingestão) → o retrieve tool pode falhar; o agente ainda responde com o que tem, ou a rota retorna erro claro. O front mostra a mensagem.
- Nome de config duplicado → 409.
- `POST /chat` / `POST /dialogues` com config_id inexistente → 404.

## Testes

**Backend (hermético — sem rede, via injeção):**
- `personas`: `list_personas` inclui defaults + arquivos; `load_persona` lê arquivo e cai no default; nome inexistente → `KeyError` (usar `PERSONAS_DIR`/`PROMPTS_DIR` tmp).
- `chat-configs`: criar/listar/deletar; 409 duplicado; 404 delete inexistente.
- `/chat`: com `ChatDeps` cujo `agent_runner` é um fake que ecoa a última mensagem + registra que recebeu persona/retriever; assert `reply` retornado e que a persona/retriever chegaram. Retriever real não é chamado (fake), Qdrant `:memory:`.
- `/dialogues`: persiste dialogue + messages na ordem certa; 404 config inexistente.
- `run_agent` (unit): com um `chat_model` fake e retriever stub, um turno que usa a tool retorna `answer` + `contexts` (sem rede). (Se `create_react_agent` exigir um modelo com tool-calling real, este teste usa um fake mínimo compatível; caso inviável de forjar, cobrir `run_agent` via o fake `agent_runner` na rota e testar `build_retrieve_tool` isoladamente.)

**Frontend:**
- Config page: carrega options+personas, cria config (chama `createChatConfig` com os campos), lista.
- Chat page: seleciona config, envia mensagem (mock `sendChat` → resposta aparece), "Salvar diálogo" chama `saveDialogue`.

## Decisões e trade-offs

- **Stateless + salvar-no-fim**: sem estado de sessão no servidor; "memória curta limpa por diálogo" sai de graça; diálogos só persistem quando o usuário quer. Custo: histórico trafega a cada turno (ok para diálogos curtos).
- **Retriever como tool; agente ReAct = o "RAG" do chat**: naive/agentic eram para o pipeline de descoberta; no chat o LangGraph raciocina e decide buscar. A config seleciona retriever + coleção, não técnica de rag.
- **Persona = arquivo** (reusa infra de prompts + bind mount): editável e versionável; sem nova mecânica de storage.
- **DI (`ChatDeps`)**: mantém a suíte sem rede (padrão já usado em `ExperimentDeps`).
- **Sem streaming no B1**: request-response é mais simples; streaming é melhoria isolável.

## Fora de escopo

- B2: listar/ler/avaliar diálogos (rating humano) — spec próprio.
- Streaming de tokens (SSE/WebSocket).
- Edição de persona pela UI (por ora, arquivos `.md`).
- Fine-tuning (Fatia C).
- Memória de longo prazo / múltiplas sessões persistentes server-side.
