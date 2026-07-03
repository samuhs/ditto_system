# Ollama como provider de LLM — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adicionar um provider de LLM `ollama` (modelo configurável por env, default `qwen2.5:3b-instruct`) usável inclusive de dentro do Docker, com alvos `make ollama-up`/`ollama-down`.

**Architecture:** `OllamaLLM` é uma subclasse de `CustomLLM` (que já usa `langchain_openai.ChatOpenAI` contra o endpoint OpenAI-compatível do Ollama), trocando os defaults por `ollama_model`/`ollama_base_url` de settings; registrado em `llm_registry` (surge sozinho em `/options.llms`). O compose passa `OLLAMA_BASE_URL=host.docker.internal` para a API alcançar o Ollama do host; o Makefile gerencia o servidor no host.

**Tech Stack:** Python 3.13 (venv `backend/.venv`), pytest; `langchain-openai` (já dependência); Docker Compose; Makefile.

## Global Constraints

- Provider plugável = classe implementando `LLM.generate(prompt) -> str`, registrada via `llm_registry.register("ollama", OllamaLLM)`, importada em `llm/__init__.py` (o import é o que registra).
- Identificadores/classes/docstrings/erros em **inglês**; textos de UI/Makefile em **PT-BR**.
- Provider genérico `ollama` (modelo por env), NÃO um registro por nome de modelo. Modelo default `qwen2.5:3b-instruct`.
- Settings: `ollama_base_url: str = "http://localhost:11434/v1"`, `ollama_model: str = "qwen2.5:3b-instruct"`; overrides por env `OLLAMA_BASE_URL`/`OLLAMA_MODEL`.
- Docker: default de settings em `localhost` (dev fora do Docker); o compose sobrescreve para `http://host.docker.internal:11434/v1` + `extra_hosts: ["host.docker.internal:host-gateway"]`.
- Testes herméticos (sem rede): client fake injetado; para o teste de defaults, monkeypatch de `langchain_openai.ChatOpenAI` + `get_settings.cache_clear()`.
- Provider `custom` existente permanece intacto.
- Rodar testes backend: `cd backend && ./.venv/bin/python -m pytest tests/test_llm.py -v`.

---

### Task 1: Settings + provider `ollama` + registro + testes

**Files:**
- Modify: `backend/app/core/config/settings.py` (dois campos em `Settings`)
- Create: `backend/app/core/llm/ollama.py`
- Modify: `backend/app/core/llm/__init__.py` (import + `__all__`)
- Test: `backend/tests/test_llm.py` (append)

**Interfaces:**
- Consumes: `LLM`, `llm_registry` (`app.core.llm.base`); `CustomLLM` (`app.core.llm.custom`); `get_settings` (`app.core.config.settings`).
- Produces: `OllamaLLM(model=None, base_url=None, api_key="ollama", client=None)` registrada como `"ollama"`; campos `Settings.ollama_base_url`, `Settings.ollama_model`.

- [ ] **Step 1: Write the failing test**

Adicionar ao fim de `backend/tests/test_llm.py` (e ao import do topo incluir `from app.core.llm.ollama import OllamaLLM`):

```python
def test_ollama_registered():
    assert "ollama" in llm_registry.names()


def test_ollama_generate_uses_injected_client():
    client = _FakeClient()
    llm = OllamaLLM(client=client)
    assert llm.generate("hi") == "generated answer"
    assert client.last_prompt == "hi"


def test_ollama_uses_settings_defaults(monkeypatch):
    import langchain_openai

    from app.core.config.settings import get_settings

    captured = {}

    class _FakeChatOpenAI:
        def __init__(self, model, base_url, api_key):
            captured["model"] = model
            captured["base_url"] = base_url
            captured["api_key"] = api_key

        def invoke(self, prompt):
            return _FakeResponse("ok")

    monkeypatch.setattr(langchain_openai, "ChatOpenAI", _FakeChatOpenAI)
    monkeypatch.setenv("OLLAMA_MODEL", "qwen2.5:3b-instruct")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434/v1")
    get_settings.cache_clear()
    try:
        llm = OllamaLLM()
        assert captured["model"] == "qwen2.5:3b-instruct"
        assert captured["base_url"] == "http://host.docker.internal:11434/v1"
        assert captured["api_key"] == "ollama"
        assert llm.generate("x") == "ok"
    finally:
        get_settings.cache_clear()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_llm.py -v`
Expected: FAIL — `ModuleNotFoundError: app.core.llm.ollama` (import no topo do arquivo de teste).

- [ ] **Step 3: Add the settings fields**

Em `backend/app/core/config/settings.py`, dentro da classe `Settings`, após a linha `gemini_api_key: str | None = None`, adicionar:

```python
    ollama_base_url: str = "http://localhost:11434/v1"
    ollama_model: str = "qwen2.5:3b-instruct"
```

- [ ] **Step 4: Create the provider**

Criar `backend/app/core/llm/ollama.py`:

```python
"""Ollama LLM provider (OpenAI-compatible endpoint, model/url from settings)."""
from app.core.config.settings import get_settings
from app.core.llm.base import llm_registry
from app.core.llm.custom import CustomLLM


class OllamaLLM(CustomLLM):
    """Generates answers via a local Ollama server's OpenAI-compatible endpoint."""

    def __init__(self, model=None, base_url=None, api_key="ollama", client=None) -> None:
        settings = get_settings()
        super().__init__(
            model=model or settings.ollama_model,
            base_url=base_url or settings.ollama_base_url,
            api_key=api_key,
            client=client,
        )


llm_registry.register("ollama", OllamaLLM)
```

- [ ] **Step 5: Register in the package `__init__`**

Em `backend/app/core/llm/__init__.py`: adicionar `from app.core.llm.ollama import OllamaLLM` junto aos outros imports e `"OllamaLLM"` ao `__all__`. Não remover os imports existentes (`GeminiLLM`, `CustomLLM`) — cada import é o que registra o provider.

- [ ] **Step 6: Run test to verify it passes**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_llm.py -v`
Expected: PASS (todos, incluindo os 3 novos: `test_ollama_registered`, `test_ollama_generate_uses_injected_client`, `test_ollama_uses_settings_defaults`).

- [ ] **Step 7: Commit**

```bash
git add backend/app/core/config/settings.py backend/app/core/llm/ollama.py backend/app/core/llm/__init__.py backend/tests/test_llm.py
git commit -m "feat(llm): add ollama provider (model/url from settings)"
```

---

### Task 2: docker-compose (rede host) + alvos do Makefile

**Files:**
- Modify: `docker-compose.yml` (serviço `api`: `environment` + `extra_hosts`)
- Modify: `Makefile` (`.PHONY` + alvos `ollama-up`/`ollama-down`)

**Interfaces:**
- Consumes: o campo `Settings.ollama_base_url` da Task 1 (lido de `OLLAMA_BASE_URL`).
- Produces: variável de ambiente `OLLAMA_BASE_URL` no container `api`; alvos `make ollama-up`, `make ollama-down`.

- [ ] **Step 1: Add the api service env + extra_hosts**

Em `docker-compose.yml`, no serviço `api`: acrescentar a linha de ambiente e o bloco `extra_hosts`. O bloco `environment` do `api` hoje é:

```yaml
    environment:
      DATABASE_URL: postgresql://ditto:ditto@postgres:5432/ditto
      QDRANT_URL: http://qdrant:6333
```

Deixá-lo assim (adicionar a linha `OLLAMA_BASE_URL`) e acrescentar `extra_hosts` logo após o bloco `environment`:

```yaml
    environment:
      DATABASE_URL: postgresql://ditto:ditto@postgres:5432/ditto
      QDRANT_URL: http://qdrant:6333
      OLLAMA_BASE_URL: http://host.docker.internal:11434/v1
    extra_hosts:
      - "host.docker.internal:host-gateway"
```

- [ ] **Step 2: Verify the compose file is valid**

Run: `cd /Users/samuelhenriquesilva/Desktop/doutorado/ditto_system && docker compose config >/dev/null && echo OK`
Expected: `OK` (sem erro de parsing). Confirma também, no output de `docker compose config`, que o serviço `api` tem `OLLAMA_BASE_URL: http://host.docker.internal:11434/v1` e `extra_hosts` com `host.docker.internal:host-gateway`.

- [ ] **Step 3: Add the Makefile targets**

Em `Makefile`, adicionar `ollama-up ollama-down` à linha `.PHONY:` e acrescentar os alvos ao fim do arquivo. Usar **TAB** de indentação (Makefile exige tab, não espaços):

```makefile
ollama-up:
	@if curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; then \
		echo "ollama ja esta rodando"; \
	else \
		echo "iniciando ollama serve..."; \
		nohup ollama serve >/tmp/ollama.log 2>&1 & \
		until curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; do sleep 1; done; \
		echo "ollama pronto"; \
	fi; \
	ollama list

ollama-down:
	@pkill -f "ollama serve" && echo "ollama parado" || echo "nenhum processo 'ollama serve' rodando"
```

- [ ] **Step 4: Verify the Makefile targets parse**

Run: `cd /Users/samuelhenriquesilva/Desktop/doutorado/ditto_system && make -n ollama-up && make -n ollama-down`
Expected: imprime os comandos de cada alvo sem erro `missing separator` (confirma que a indentação é TAB e a sintaxe está correta). NÃO executa de verdade (`-n` = dry-run).

- [ ] **Step 5: Commit**

```bash
git add docker-compose.yml Makefile
git commit -m "feat(ollama): reach host ollama from docker + make ollama-up/down"
```

---

## Self-Review

**Spec coverage:**
- Provider `ollama` subclasse de `CustomLLM`, defaults de settings, registrado + import em `__init__` → Task 1. ✓
- Settings `ollama_base_url`/`ollama_model` + overrides por env → Task 1. ✓
- docker-compose `OLLAMA_BASE_URL=host.docker.internal` + `extra_hosts` → Task 2. ✓
- Makefile `ollama-up` (idempotente, espera ficar pronto, `ollama list`) / `ollama-down` → Task 2. ✓
- Testes herméticos (registro, delegação via client injetado, defaults via monkeypatch de `ChatOpenAI` + `cache_clear`) → Task 1. ✓
- Surge sozinho em `/options.llms` (via registry) — coberto pelo teste de registro + wiring existente. ✓

**Placeholder scan:** nenhum TBD/TODO; todo passo com conteúdo real e comando + saída esperada. Passos de ops (compose/Makefile) têm comandos de verificação (`docker compose config`, `make -n`) em vez de pytest, pois não são unit-testáveis.

**Type consistency:** `OllamaLLM(model=None, base_url=None, api_key="ollama", client=None)` idêntico entre Task 1 (definição) e os testes; `super().__init__` casa com a assinatura de `CustomLLM(model, base_url, api_key, client)`; `Settings.ollama_base_url`/`ollama_model` idênticos entre settings, provider e teste; `OLLAMA_BASE_URL` idêntico entre compose (Task 2) e o mapeamento env→campo do pydantic-settings (Task 1).
