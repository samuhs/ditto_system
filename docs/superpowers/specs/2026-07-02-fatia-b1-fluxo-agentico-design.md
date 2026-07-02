# Fatia B1.1 — Fluxo agêntico multi-nó + visualização — Design

**Data:** 2026-07-02
**Autor:** Samuel (samuhs) + Claude

## Contexto

A Fatia B1 entregou um agente conversacional ReAct (um único `create_react_agent` com uma tool de busca). Ao testar, o usuário pediu uma evolução: transformar o agente num **grafo LangGraph explícito e multi-nó**, onde um dos nós é o **fluxo de RAG** (naive/agentic da Fatia A, selecionável na config), e os demais nós são etapas de um agente conversacional (triagem, guardrail, memória, persona). Além disso: **visualizar** o fluxo e os prompts de cada nó de forma bonita no front, com **edição**, e uma aba para editar personas.

Isto substitui o agente ReAct do B1 (que ainda não foi mergeado na `main`).

## Objetivo

Um agente conversacional orquestrado por um `StateGraph` do LangGraph, com nós especializados (guardrail, triagem, RAG, memória, persona), técnica de RAG selecionável por configuração, e uma tela que desenha o grafo (react-flow) permitindo ver e editar o prompt de cada nó, mais uma aba para editar personas.

## Escopo

Dentro: grafo multi-nó (backend), campo `rag` na config de chat, prompts de nó file-backed + edição, endpoints de descrição/edição do fluxo, edição de persona, tela de fluxo (react-flow) + aba de personas, e o select de RAG na config.

Fora: editor visual de grafo (add/remover/reordenar nós — estrutura é fixa no código); streaming; fine-tuning (Fatia C); B2 (avaliação de diálogo).

## Arquitetura

### 1. Grafo LangGraph (`StateGraph`)

Módulo novo `backend/app/core/chat/graph.py`. Os nós são funções customizadas (não ReAct) — **não precisam de tool-calling**; cada nó chama o **LLM da Fatia A** (`build_llm`, interface `.generate(prompt) -> str`). O nó RAG usa `build_rag`. Isso unifica o LLM em todo o grafo e torna tudo testável com um LLM fake.

**Estado** (`TypedDict` `FlowState`): `question: str`, `history: list[ChatMessage]`, `route: str` (`"rag" | "direct" | "blocked"`), `summary: str`, `draft: str`, `contexts: list[str]`, `answer: str`.

**Nós:**
- **guardrail** — `llm.generate(guardrail_prompt.format(question=...))`; se a saída indicar bloqueio (começa com `BLOCK`), define `route="blocked"`.
- **triage** — `llm.generate(triage_prompt.format(question=..., summary=...))`; define `route="rag"` ou `route="direct"` (a partir de `RAG`/`DIRECT` na saída). Não roda se já `blocked`.
- **rag** — `rag.answer(question)` → `draft` + `contexts` (contextos como `list[str]` via `format_context`/textos). Só no caminho `rag`.
- **memory** — `llm.generate(memory_prompt.format(history=...))` → `summary` curto do histórico anterior.
- **persona** — compõe a resposta final: `llm.generate(persona_compose_prompt.format(persona=<texto da persona>, summary=..., context=..., question=...))` → `answer`. O `context` carrega o rascunho do RAG, ou "(responda diretamente)" no caminho direto, ou "(fora do escopo — recuse educadamente)" quando `blocked`.

**Arestas (condicionais):**
```
START → guardrail
guardrail → (route=="blocked") ? persona : triage
triage → (route=="rag") ? rag : memory
rag → memory
memory → persona
persona → END
```

**Runner** `run_flow(cfg: ChatConfigView, messages: list[ChatMessage], deps: ChatDeps) -> ChatTurnResult`:
monta llm/embedder/retriever/rag a partir da config (via `deps.*_factory`), carrega persona (`load_persona`) e os prompts de nó (`load_flow_prompts`), constrói o grafo (`build_graph(llm, rag, persona_text, prompts)`), invoca com `{question, history}` e retorna `ChatTurnResult(answer, contexts)`.

`ChatConfigView` (dataclass em `schemas.py`): `base, chunking, embedding, retriever, rag, llm, persona` — extraída do ORM dentro da sessão e passada ao `run_flow` (evita objeto SQLAlchemy destacado).

O agente ReAct do B1 (`build_chat_model`, `build_retrieve_tool`, `to_lc_messages`, `extract_turn`, `run_agent`) é **removido**; `run_flow` passa a ser o `agent_runner` default.

### 2. Prompts dos nós (file-backed + editáveis)

Módulo `backend/app/core/chat/flow_prompts.py` (espelha o loader de personas), lendo de `backend/prompts/conversation/<nó>.md` (durável via bind mount existente):

- `FLOW_PROMPT_SPECS: dict[str, set[str]]` — placeholders obrigatórios por nó:
  - `guardrail`: `{"question"}`
  - `triage`: `{"question"}`
  - `memory`: `{"history"}`
  - `persona_compose`: `{"persona", "question"}` (disponíveis também: `{summary}`, `{context}`)
- `DEFAULT_FLOW_PROMPTS: dict[str, str]` — fallbacks embutidos (PT-BR no conteúdo).
- `list_flow_prompts() -> dict[str,str]`, `load_flow_prompt(node)`, `save_flow_prompt(node, text)` (valida placeholders), `validate_flow_placeholders(node, text)`. Nó desconhecido → `KeyError`.
- Arquivos iniciais: `backend/prompts/conversation/{guardrail,triage,memory,persona_compose}.md`.

O nó **RAG não tem prompt próprio aqui** — usa o prompt da técnica (naive/agentic) já gerenciado pela feature de prompts.

### 3. Personas editáveis

Estende `backend/app/core/personas/loader.py`: `save_persona(name, text)` (grava `personas/<name>.md`, sem validação de placeholder). O nome deve existir (default ou arquivo) ou ser novo válido (`[\w-]+`).

### 4. Config de chat

`ChatConfig` ganha coluna `rag: Mapped[str]` (default `"naive"`). O body de criação passa a exigir `rag`.

**Migração (importante):** o B1 já foi testado localmente, então a tabela `chat_config` pode existir sem a coluna `rag`, e `create_all` **não altera** tabelas existentes. O passo de deploy deve rodar um ALTER idempotente antes/depois do rebuild:
```sql
ALTER TABLE chat_config ADD COLUMN IF NOT EXISTS rag VARCHAR(60) DEFAULT 'naive';
```
Instalações novas recebem a coluna via `create_all`. Configs criadas no B1 (sem `rag`) ganham o default `'naive'`.

### 5. API

Router `chat.py`:
- `GET /chat/flow` → descrição estática do grafo para desenhar:
  ```json
  {
    "nodes": [
      {"id":"guardrail","label":"Guardrail","type":"prompt","description":"...",
       "prompt":"...","required_placeholders":["question"]},
      {"id":"triage", ...},
      {"id":"rag","label":"RAG","type":"rag","description":"Usa a técnica de RAG da config"},
      {"id":"memory", ...},
      {"id":"persona_compose","label":"Persona", ...}
    ],
    "edges": [
      {"source":"guardrail","target":"triage","label":"ok"},
      {"source":"guardrail","target":"persona_compose","label":"bloqueado"},
      {"source":"triage","target":"rag","label":"precisa de conhecimento"},
      {"source":"triage","target":"memory","label":"direto"},
      {"source":"rag","target":"memory"},
      {"source":"memory","target":"persona_compose"}
    ]
  }
  ```
  A estrutura (nós/arestas/labels/descrições) vem de uma constante `FLOW_SPEC` no backend; `prompt`/`required_placeholders` dos nós `type=="prompt"` vêm de `flow_prompts`.
- `PUT /chat/flow/{node}` body `{text}` → `save_flow_prompt`; 404 nó desconhecido (ou `type!="prompt"`), 422 placeholder faltando.
- `GET /personas/{name}` → `{name, text}` (404 desconhecido). `PUT /personas/{name}` body `{text}` → `save_persona`; retorna `{name, text}`.
- `GET /personas` (já existe) continua listando nomes.

### 6. Frontend

Nova dependência **`@xyflow/react`** (react-flow) no `frontend/package.json`.

- **Tela "Agente"** (`/agente`, item no menu), com Mantine `Tabs`:
  - **Aba "Fluxo do agente"**: `GET /chat/flow` → react-flow desenha nós/arestas (layout estático, rótulos de condição nas arestas), no visual escuro do app. Clicar num nó `type=="prompt"` abre um painel lateral com `Textarea` (prompt atual) + placeholders obrigatórios + "Salvar" (`PUT /chat/flow/{node}`, surfando erro 422). Nó `type=="rag"` mostra um aviso: "o prompt depende da técnica escolhida na config — edite em Prompts".
  - **Aba "Personas"**: lista personas (`GET /personas`); selecionar uma carrega o texto (`GET /personas/{name}`) num `Textarea` editável com "Salvar" (`PUT /personas/{name}`).
- **Config de chat**: novo `Select` **RAG** (de `/options.rags`), obrigatório.
- Cliente/tipos novos: `getFlow`, `saveFlowPrompt`, `getPersona`, `savePersona`; tipos `FlowSpec`, `FlowNode`, `FlowEdge`.

## Tratamento de erros

- LLM/persona/rag/retriever/embedding desconhecidos no `run_flow` → o `/chat` mapeia `KeyError` para 400 (já feito no B1; manter ao passar pelo `run_flow`).
- Nó desconhecido no `PUT /chat/flow/{node}` → 404; placeholder faltando → 422.
- Retrieval falho dentro do nó RAG → o `rag.answer` pode falhar; o nó captura e segue com `draft` vazio/contexto vazio (a persona responde com o que tem), evitando derrubar o turno.
- Persona inexistente no `GET/PUT /personas/{name}` → 404 (GET) / cria se nome novo válido (PUT).

## Testes

**Backend (hermético — LLM/rag fakes, sem rede):**
- `flow_prompts`: load/save/validate + KeyError (via `PROMPTS_DIR` tmp).
- `personas`: `save_persona` grava e relê; nome inválido rejeitado.
- **graph** (o ganho principal): construir o grafo com um LLM fake (cujo `.generate` retorna rótulos conforme o prompt recebido — ex.: contém "segur"→`BLOCK`/`OK`; contém "rota"/"triar"→`RAG`/`DIRECT`; senão ecoa) e um rag fake (`.answer` → draft+contexts). Casos:
  - guardrail bloqueia → `answer` é recusa, nó RAG não roda.
  - triagem `direct` → RAG não roda, persona compõe a partir do resumo.
  - triagem `rag` → RAG roda, `draft`/`contexts` chegam na persona e no resultado.
- `/chat` (via `deps.agent_runner` fake) continua verde; e um teste que injeta o `run_flow` real com fakes cobre a integração da rota→grafo.
- `GET /chat/flow` retorna nós/arestas + prompts; `PUT /chat/flow/{node}` grava (422 placeholder faltando; 404 nó inexistente); `GET/PUT /personas/{name}`.
- `chat_config` com `rag`: criação persiste o campo.

**Frontend:**
- Flow page: mocka `getFlow` → react-flow renderiza os nós (por rótulo); clicar num nó de prompt e salvar chama `saveFlowPrompt`; aba Personas carrega e salva (`getPersona`/`savePersona`).
- Config page: o novo select de RAG participa do `createChatConfig`.

## Decisões e trade-offs

- **Grafo roda no LLM da Fatia A (`.generate`)**, não em chat-model/tool-calling: unifica o LLM, remove o ReAct e a dependência de `bind_tools`, e torna o grafo **testável sem rede** (grande ganho vs. B1).
- **Estrutura do grafo fixa no código** (`FLOW_SPEC` + `build_graph`): a UI edita prompts, não topologia. Editor visual de grafo fica fora de escopo.
- **Prompts de nó file-backed** em `prompts/conversation/` (reusa infra + bind mount).
- **react-flow** para o diagrama (escolha do usuário) — dep no front, porém entrega o "bonito e interativo".
- **Config snapshot (`ChatConfigView`)** desacopla o `run_flow` do ORM (sem objeto destacado).
- Persona = a voz (arquivo em `personas/`); `persona_compose` = o template do nó persona (como usar a voz + resumo + contexto). Separação limpa.

## Fora de escopo

- Editor visual de topologia do grafo.
- Streaming de tokens.
- B2 (avaliação de diálogo) e Fatia C (fine-tuning).
- Memória de longo prazo persistida server-side (a "memória" aqui é um resumo derivado do histórico por turno).
