# Ollama como provider de LLM — Design

**Data:** 2026-07-03
**Autor:** Samuel (samuhs) + Claude

## Contexto

O Ditto expõe modelos de LLM plugáveis via interface + registry (`app.core.llm`): cada provider implementa `LLM.generate(prompt) -> str` e se registra em `llm_registry`; `/options.llms` deriva de `llm_registry.names()`, então um provider novo aparece automaticamente na matriz de experimentos e na config de chat, sem mudança de API/frontend.

Hoje há três providers registrados: `gemini` (Google, via `langchain-google-genai`), `custom` (endpoint OpenAI-compatível genérico, via `langchain-openai`, com defaults `model="qwen2"`, `base_url="http://localhost:11434/v1"`) e `custom` já cobre Ollama tecnicamente, mas: (a) seu default aponta para `localhost`, que a API dentro do Docker não alcança no host; (b) não expõe um nome claro nem o modelo desejado. `langchain-openai>=0.1` já é dependência.

O usuário instalou o Ollama na máquina host e baixou `qwen2.5:3b-instruct`. Quer o modelo disponível para a aplicação, selecionável como opção, e alvos no Makefile para iniciar/parar o servidor do Ollama.

## Objetivo

Adicionar um provider de LLM `ollama` (genérico, modelo configurável por env, default `qwen2.5:3b-instruct`) que a aplicação — inclusive rodando em Docker — consiga usar contra o Ollama do host, mais alvos `make ollama-up`/`make ollama-down` para gerenciar o servidor.

## Arquitetura

### 1. Provider `ollama`

Novo arquivo `backend/app/core/llm/ollama.py`:

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

- Subclasse de `CustomLLM` (reusa a construção do `ChatOpenAI` e o `generate`), apenas trocando os defaults por valores vindos de settings. DRY: nenhuma duplicação da lógica de geração.
- `build_llm("ollama")` (chamada sem kwargs pelo orquestrador e pelo chat) instancia com os defaults das settings.
- Registrado; importado em `backend/app/core/llm/__init__.py` (o import é o que registra), adicionado ao `__all__`.
- O provider `custom` existente permanece intacto (fora de escopo).

### 2. Settings + rede Docker→host

Em `backend/app/core/config/settings.py`, adicionar dois campos a `Settings`:

```python
    ollama_base_url: str = "http://localhost:11434/v1"
    ollama_model: str = "qwen2.5:3b-instruct"
```

Overrides por env: `OLLAMA_BASE_URL`, `OLLAMA_MODEL` (pydantic-settings já mapeia nome do campo → env maiúsculo).

No `docker-compose.yml`, serviço `api`:
- `environment`: `OLLAMA_BASE_URL: http://host.docker.internal:11434/v1`.
- `extra_hosts: ["host.docker.internal:host-gateway"]` — garante a resolução do host a partir do container (nativo no Docker Desktop/Mac; explícito para portabilidade).

Rationale: a API roda no container e precisa alcançar o Ollama do **host**; `localhost` dentro do container é o próprio container. Rodando o backend fora do Docker (dev/testes), o default `localhost:11434` já serve — por isso o default de settings fica em `localhost` e o compose sobrescreve para `host.docker.internal`.

### 3. Makefile

Dois alvos novos (adicionar a `.PHONY`):

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

- `ollama-up` é idempotente: se o servidor já responde (ex.: app do Ollama já rodando), só avisa; senão sobe `ollama serve` em background e espera o endpoint responder antes de retornar; ao final lista os modelos.
- `ollama-down` encerra o processo `ollama serve` iniciado; se não houver, avisa sem erro.
- Ficam separados de `make up`/`make down` — o usuário controla quando ligar/desligar o modelo.

### 4. Testes

Herméticos (sem rede), no padrão de `backend/tests/test_llm.py` (que injeta um client fake):

- **Registro:** `"ollama" in llm_registry.names()`.
- **Delegação:** `OllamaLLM(client=fake)` onde `fake.invoke(prompt).content` devolve um texto fixo; `generate(prompt)` retorna esse texto.
- **Defaults das settings:** com `OLLAMA_MODEL`/`OLLAMA_BASE_URL` definidos no ambiente do teste e o cache de settings limpo (`get_settings.cache_clear()`), monkeypatch de `langchain_openai.ChatOpenAI` por um fake que registra os kwargs; assert de que `OllamaLLM()` (sem client) construiu o client com `model`/`base_url` vindos das settings. Restaurar o cache/env ao final.

## Tratamento de erros

- Ollama fora do ar / modelo ausente: o `ChatOpenAI.invoke` levanta em tempo de geração; no fluxo de experimentos o retry progressivo existente (3× com espera) já cobre, e a rota de chat propaga como hoje. Nenhum tratamento novo.
- `make ollama-up` quando a porta já está ocupada por outro `ollama serve`/app: o ramo "já está rodando" evita o erro de porta.

## Decisões e trade-offs

- **Provider genérico `ollama` (modelo por env)**, não um registro por nome de modelo: trocar de modelo local não exige mexer no código, só `.env`. Escolha do usuário.
- **Subclasse de `CustomLLM`**: reusa a integração OpenAI-compatível já existente; sem duplicar a lógica de `generate`. Mantém `custom` intacto.
- **Ollama no host, não no compose**: o modelo já foi instalado no host; containerizar o Ollama (com pesos, GPU/CPU) é bem mais pesado e fora do pedido. A API alcança o host via `host.docker.internal`.
- **Default de settings em `localhost`, compose sobrescreve**: um único código funciona tanto em dev (fora do Docker) quanto no container.
- **Realidade de qualidade:** um modelo local 3B tende a pontuar bem abaixo do gemini nas métricas; o valor aqui é custo/privacidade e a comparação da tese, não ganho de qualidade.

## Fora de escopo

- Ollama como **embedder** (isto cobre só LLM de geração).
- Rodar o servidor do Ollama dentro do docker-compose.
- Múltiplos modelos Ollama simultâneos como opções distintas (troca via env).
- Mudanças de UI (o provider surge sozinho pelo registry).
- Alterar/remover o provider `custom` existente.
