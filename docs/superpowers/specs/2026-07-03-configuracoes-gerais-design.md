# Configurações gerais + feedback de pausa — Design

**Data:** 2026-07-03
**Autor:** Samuel (samuhs) + Claude

## Contexto

Duas necessidades: (1) uma tela de **Configurações** (acessível por um ícone de engrenagem no rodapé do menu) para gerir variáveis gerais do sistema — a chave do Gemini (alterar/adicionar) e **modelos Ollama nomeados** (hoje só existe a opção genérica `ollama`; o usuário quer identificadores próprios para vários modelos) — extensível para configs futuras; e (2) **feedback na UI** quando uma pausa de experimento foi solicitada mas ainda não aplicou (a pausa é cooperativa e pode demorar a alcançar um checkpoint, ex.: combinação `agentic × ollama`).

Estado atual: a chave do Gemini vive em `Settings` (`app/core/config/settings.py`, `gemini_api_key`), lida via `get_settings()` (cacheado do env) em `llm/gemini.py` e `embedding/gemini.py`. Os LLMs vêm do `llm_registry` via `build_llm(name)`; `/options.llms = llm_registry.names()`. O `ExperimentDeps`/`ChatDeps` usam `llm_factory = build_llm` como default (testes injetam fakes). A pausa de experimento usa um registro em memória no orquestrador (`_pause_requested(id)`), aplicado em checkpoints entre perguntas/combinações; o `GET /experiments/{id}` não expõe se uma pausa foi solicitada.

## Objetivo

Adicionar um store de configurações editáveis em runtime (arquivo), uma tela de Configurações para geri-lo (chave do Gemini + modelos Ollama nomeados, extensível), e um indicador de "pausa pendente" nos resultados do experimento.

## Decisões

- **Store em arquivo** bind-mounted (`backend/config/app_settings.json`), consistente com o padrão file-backed de prompts/personas; sem migração; a chave secreta não entra em dumps do Postgres.
- **Modelos Ollama nomeados + mantém o `ollama` genérico**: cada `{id, model}` cadastrado vira uma opção, junto de `gemini/custom/ollama`.

## Arquitetura

### Parte A — Store de configurações (arquivo)

Arquivo `backend/config/app_settings.json` (gitignored; bind-mount `./backend/config:/app/config` no serviço `api`):

```json
{
  "gemini_api_key": "AI...",
  "ollama_models": [
    {"id": "qwen", "model": "qwen2.5:3b-instruct"}
  ]
}
```

Módulo novo `backend/app/core/config/runtime.py`:

- `config_dir() -> Path` — `Path(os.environ["APP_CONFIG_DIR"])` se setado (para testes), senão `Path(__file__).resolve().parents[3] / "config"` (raiz do backend `/config`). Espelha `prompts_dir()`.
- `_config_path() -> Path` — `config_dir() / "app_settings.json"`.
- `load_config() -> dict` — lê o JSON se existir, senão `{}`.
- `save_config(data: dict) -> None` — cria o diretório se preciso e grava o JSON (indent=2).
- `get_gemini_key() -> str | None` — `load_config().get("gemini_api_key") or get_settings().gemini_api_key` (arquivo sobrepõe env; env é fallback).
- `set_gemini_key(key: str | None) -> None` — atualiza a chave `gemini_api_key` no arquivo (string vazia → remove a chave, voltando ao env).
- `get_ollama_models() -> list[dict]` — `load_config().get("ollama_models", [])`.
- `set_ollama_models(models: list[dict]) -> None` — valida e grava.
- `validate_ollama_models(models, reserved: set[str]) -> None` — cada item tem `id` casando `^[\w-]+$`, `model` não vazio; `id` não pode colidir com `reserved` (nomes do registry) nem repetir; senão `ValueError`.

Lê o arquivo a cada chamada (sem `lru_cache`), então edições valem para novas construções de LLM sem restart.

### Parte B — Integração no core

- **Chave do Gemini editável:** em `llm/gemini.py` e `embedding/gemini.py`, trocar `get_settings().gemini_api_key` por `get_gemini_key()` (de `runtime`). Como os providers são construídos por combinação/turno, uma edição na tela passa a valer sem restart.
- **Resolver de LLM (modelos nomeados):** função nova `resolve_llm(name: str, **kwargs) -> LLM` (em `app/core/llm/__init__.py` ou `factory.py`): se `name` é o `id` de um modelo Ollama cadastrado → `OllamaLLM(model=<model>, **kwargs)`; senão `build_llm(name, **kwargs)`. Vira o default de `llm_factory` em `ExperimentDeps` e `ChatDeps` (substitui `build_llm`). Testes seguem injetando fakes, então não tocam o arquivo.
- **`/options.llms`** (`api/options.py`): `llm_registry.names()` + `[m["id"] for m in get_ollama_models()]` (registry primeiro, depois os ids cadastrados).

### Parte C — API + tela de Configurações

**API nova `backend/app/api/settings.py`** (registrada em `main.py`):

- `GET /settings` → `{"gemini_api_key_set": bool, "ollama_models": [{"id","model"}, ...]}`. Nunca devolve a chave crua — só se está setada (`get_gemini_key() is not None`).
- `PUT /settings/gemini-key` — body `{"key": str}` → `set_gemini_key(key)` (string vazia limpa). Retorna `{"gemini_api_key_set": bool}`.
- `PUT /settings/ollama-models` — body `{"models": [{"id","model"}, ...]}` → valida (contra `llm_registry.names()` como reservados) e persiste; `ValueError` → 422. Retorna `{"ollama_models": [...]}`.

**Frontend:**

- **Sidebar** (`components/Sidebar.tsx`): item de engrenagem "Configurações" no rodapé do menu (antes/junto do `ditto-sidebar-foot`) → rota `/configuracoes`. Ícone novo `GearIcon` em `components/icons`.
- **`SettingsPage`** (`pages/SettingsPage.tsx`, rota `/configuracoes` em `App.tsx`):
  - Seção **"Chave do Gemini"**: indica se há chave setada; `PasswordInput` para nova chave + botão salvar (chama `PUT /settings/gemini-key`); feedback.
  - Seção **"Modelos Ollama"**: lista editável de linhas `{identificador, modelo}` (add/remover linha) + botão salvar (chama `PUT /settings/ollama-models`); erro 422 mostrado.
  - Layout em seções para acomodar **configs futuras** como novas seções.
- Cliente/tipos (`api/client.ts`, `api/types.ts`): `getSettings`, `saveGeminiKey`, `saveOllamaModels`; tipos `AppSettings`, `OllamaModel`.

### Parte D — Feedback de pausa

- `GET /experiments/{id}` (`api/experiments.py`) inclui `"pause_requested": _pause_requested(experiment_id)` (importa de `orchestrator`).
- `ExperimentDetailPage`: quando `status === "running" && detail.pause_requested`, mostra um texto "Pausando… aguardando a combinação atual terminar" e o botão de pausa vira "Pausando…" desabilitado. Nenhuma mudança no fluxo de execução (a pausa continua cooperativa, aplicada no próximo checkpoint).
- Tipo `ExperimentDetail` ganha `pause_requested?: boolean`.

## Tratamento de erros

- `id` de modelo Ollama inválido (regex), duplicado, ou colidindo com nome do registry (`gemini`/`custom`/`ollama`) → `ValueError` → 422 na API; o front mostra a mensagem.
- `config` inexistente/corrompido → `load_config()` devolve `{}` (tela mostra vazio).
- LLM selecionado com id de modelo removido depois → `resolve_llm` cai em `build_llm(name)` → `KeyError` → 400/registro de falha (comportamento existente).
- Chave do Gemini ausente (nem arquivo nem env) → comportamento atual (provider falha na chamada); a tela deixa claro que não há chave setada.

## Testes

**Backend (herméticos, sem rede; `APP_CONFIG_DIR` em tmp):**
- `runtime`: `get_gemini_key` (arquivo sobrepõe env; sem arquivo cai no env); `set_gemini_key` grava e limpa; `get/set_ollama_models` roundtrip; `validate_ollama_models` rejeita id inválido, duplicado, e colisão com reservados.
- `settings` API: `GET` reflete `gemini_api_key_set` e lista de modelos, nunca a chave crua; `PUT gemini-key` persiste; `PUT ollama-models` valida (422 em colisão/regex) e persiste.
- `resolve_llm`: id cadastrado → instância de `OllamaLLM`; nome do registry → instância do provider correspondente; desconhecido → propaga `KeyError`.
- `/options.llms` inclui os ids cadastrados além dos nomes do registry.
- `pause_requested` no `GET /experiments/{id}`: após `request_pause(id)`, o GET traz `pause_requested: true` (limpar o registro ao fim).

**Frontend (vitest, mocks do client):**
- `SettingsPage`: carrega `getSettings` (mostra estado da chave + modelos); salvar chave chama `saveGeminiKey`; adicionar/editar linha de modelo e salvar chama `saveOllamaModels` com a lista.
- `ExperimentDetailPage`: com `status: "running"` e `pause_requested: true`, mostra o indicador de "Pausando…" e o botão desabilitado.

## Decisões e trade-offs

- **Arquivo, não DB:** consistente com prompts/personas; sem migração; secret fora do banco. Custo: não é transacional (ok para um único usuário).
- **Leitura não-cacheada do arquivo:** edições valem sem restart; custo desprezível (arquivo pequeno, lido na construção do provider).
- **`resolve_llm` como camada fina sobre `build_llm`:** não mexe no registry (que continua estático); ids dinâmicos resolvidos só na fábrica. Mantém a testabilidade (fakes injetados).
- **Chave nunca devolvida crua:** a tela opera por "setada/não setada" + substituição, reduzindo exposição do secret.
- **Pausa: só feedback de UI:** o fluxo de execução não muda (decisão do usuário — sem checkpoint no meio da combinação).

## Fora de escopo

- Múltiplas chaves de Gemini (apenas uma).
- `base_url` por modelo Ollama (todos usam o `ollama_base_url` do host).
- Criptografia do arquivo de configurações.
- Checkpoint de pausa dentro do loop agêntico (o usuário não quis parar no meio do fluxo).
- Gestão via UI de chunking/embedding/rag/retriever (essas continuam plugáveis por código).
