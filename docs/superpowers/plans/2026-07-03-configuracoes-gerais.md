# Configurações gerais + feedback de pausa — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Um store de configurações editáveis em runtime (arquivo), uma tela de Configurações (chave do Gemini + modelos Ollama nomeados, extensível) acessível por engrenagem no menu, e um indicador de "pausa pendente" nos resultados.

**Architecture:** Loader file-backed `runtime.py` (JSON em `backend/config/`, bind-mounted). Os providers Gemini leem a chave via `get_gemini_key()`; um `resolve_llm(name)` resolve ids de modelos Ollama nomeados antes do registry e vira o `llm_factory` default. Uma API `settings` e uma `SettingsPage` gerem tudo. O `GET /experiments/{id}` expõe `pause_requested` e a tela de detalhe mostra o estado de pausa pendente.

**Tech Stack:** Python 3.13 (venv `backend/.venv`), FastAPI, pytest; React + Vite + TS + Mantine, vitest.

## Global Constraints

- Identificadores/classes/docstrings/erros em **inglês**; UI em **PT-BR**.
- Store em **arquivo** `backend/config/app_settings.json` (gitignored; bind-mount `./backend/config:/app/config`); loader lê a cada chamada (sem cache).
- `get_gemini_key()` = valor do arquivo, senão `get_settings().gemini_api_key` (env fallback).
- Modelo Ollama nomeado = `{id, model}`; `id` casa `^[\w-]+$`, sem colidir com nomes do registry (`gemini/custom/ollama`) nem duplicar. Mantém o `ollama` genérico.
- A chave do Gemini **nunca** é devolvida crua pela API (só `gemini_api_key_set: bool`).
- Testes herméticos (sem rede): `APP_CONFIG_DIR` em tmp; `get_settings.cache_clear()` quando mexer no env; fakes injetados; TestClient sem context-manager (não dispara `create_all`/DB).
- **Post-merge deployment (manual, NÃO é task de código):** adicionar o bind-mount `./backend/config:/app/config` ao serviço `api` no `docker-compose.yml` já é feito na Task 5; criar o dir `backend/config/` (o loader cria on-demand).
- Rodar: backend `cd backend && ./.venv/bin/python -m pytest <arquivo> -v`; frontend `cd frontend && npx vitest run <arquivo>`.

---

### Task 1: Store de configurações em arquivo (`runtime.py`)

**Files:**
- Create: `backend/app/core/config/runtime.py`
- Create: `backend/tests/test_runtime_config.py`
- Modify: `.gitignore` (ignorar o arquivo de settings)

**Interfaces:**
- Consumes: `get_settings` (`app.core.config.settings`).
- Produces: `config_dir()`, `load_config()`, `save_config(dict)`, `get_gemini_key() -> str | None`, `set_gemini_key(str | None)`, `get_ollama_models() -> list[dict]`, `set_ollama_models(list[dict], reserved: set[str] | None)`, `validate_ollama_models(list[dict], reserved: set[str])`.

- [ ] **Step 1: Write the failing test**

Criar `backend/tests/test_runtime_config.py`:

```python
"""Tests for the runtime settings store."""
import pytest

from app.core.config import runtime


@pytest.fixture
def cfg_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_CONFIG_DIR", str(tmp_path))
    return tmp_path


def test_gemini_key_file_overrides_env(cfg_dir, monkeypatch):
    from app.core.config.settings import get_settings

    monkeypatch.setenv("GEMINI_API_KEY", "env-key")
    get_settings.cache_clear()
    try:
        assert runtime.get_gemini_key() == "env-key"  # no file yet -> env
        runtime.set_gemini_key("file-key")
        assert runtime.get_gemini_key() == "file-key"  # file overrides
        runtime.set_gemini_key("")
        assert runtime.get_gemini_key() == "env-key"  # cleared -> env
    finally:
        get_settings.cache_clear()


def test_ollama_models_roundtrip(cfg_dir):
    assert runtime.get_ollama_models() == []
    runtime.set_ollama_models(
        [{"id": "qwen", "model": "qwen2.5:3b-instruct"}], reserved={"gemini"}
    )
    assert runtime.get_ollama_models() == [{"id": "qwen", "model": "qwen2.5:3b-instruct"}]


def test_validate_ollama_models_rejects_bad_entries(cfg_dir):
    with pytest.raises(ValueError):
        runtime.validate_ollama_models([{"id": "bad id", "model": "m"}], reserved=set())
    with pytest.raises(ValueError):
        runtime.validate_ollama_models([{"id": "qwen", "model": ""}], reserved=set())
    with pytest.raises(ValueError):
        runtime.validate_ollama_models([{"id": "gemini", "model": "m"}], reserved={"gemini"})
    with pytest.raises(ValueError):
        runtime.validate_ollama_models(
            [{"id": "x", "model": "m"}, {"id": "x", "model": "n"}], reserved=set()
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_runtime_config.py -v`
Expected: FAIL — `ModuleNotFoundError: app.core.config.runtime`.

- [ ] **Step 3: Create the loader**

Criar `backend/app/core/config/runtime.py`:

```python
"""Runtime-editable app settings, backed by a JSON file (env fallback for secrets)."""
import json
import os
import re
from pathlib import Path

from app.core.config.settings import get_settings

_ID_RE = re.compile(r"^[\w-]+$")


def config_dir() -> Path:
    """Directory holding the runtime settings file (env APP_CONFIG_DIR overrides)."""
    env = os.environ.get("APP_CONFIG_DIR")
    if env:
        return Path(env)
    # runtime.py is at <root>/app/core/config/runtime.py -> backend root is parents[3]
    return Path(__file__).resolve().parents[3] / "config"


def _config_path() -> Path:
    return config_dir() / "app_settings.json"


def load_config() -> dict:
    """Read the settings file; return {} if absent or unreadable."""
    path = _config_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_config(data: dict) -> None:
    """Persist the whole settings dict as pretty JSON."""
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def get_gemini_key() -> str | None:
    """The runtime Gemini key if set, else the env default."""
    return load_config().get("gemini_api_key") or get_settings().gemini_api_key


def set_gemini_key(key: str | None) -> None:
    """Set (or clear, when falsy) the runtime Gemini key."""
    data = load_config()
    if key:
        data["gemini_api_key"] = key
    else:
        data.pop("gemini_api_key", None)
    save_config(data)


def get_ollama_models() -> list[dict]:
    """The list of named Ollama models ([{id, model}, ...])."""
    return load_config().get("ollama_models", [])


def validate_ollama_models(models: list[dict], reserved: set[str]) -> None:
    """Raise ValueError if any entry is malformed, duplicated, or reserved."""
    seen: set[str] = set()
    for entry in models:
        mid = entry.get("id", "")
        model = entry.get("model", "")
        if not _ID_RE.match(mid):
            raise ValueError(f"invalid model id: {mid!r}")
        if not model:
            raise ValueError(f"empty model for id: {mid!r}")
        if mid in reserved:
            raise ValueError(f"id conflicts with a built-in provider: {mid!r}")
        if mid in seen:
            raise ValueError(f"duplicate model id: {mid!r}")
        seen.add(mid)


def set_ollama_models(models: list[dict], reserved: set[str] | None = None) -> None:
    """Validate and persist the named Ollama models."""
    validate_ollama_models(models, reserved or set())
    data = load_config()
    data["ollama_models"] = [{"id": m["id"], "model": m["model"]} for m in models]
    save_config(data)
```

- [ ] **Step 4: Ignore the settings file**

Adicionar ao `.gitignore` (na raiz do repo) a linha:

```
backend/config/app_settings.json
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_runtime_config.py -v`
Expected: PASS (3 passed).

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/config/runtime.py backend/tests/test_runtime_config.py .gitignore
git commit -m "feat(config): runtime settings store (file-backed)"
```

---

### Task 2: Integração no core (chave do Gemini, resolve_llm, options)

**Files:**
- Modify: `backend/app/core/llm/gemini.py`, `backend/app/core/embedding/gemini.py` (usar `get_gemini_key`)
- Create: `backend/app/core/llm/factory.py` (`resolve_llm`)
- Modify: `backend/app/core/llm/__init__.py` (exportar `resolve_llm`)
- Modify: `backend/app/experiments/orchestrator.py`, `backend/app/core/chat/deps.py` (default `llm_factory = resolve_llm`)
- Modify: `backend/app/api/options.py` (incluir ids)
- Test: `backend/tests/test_llm_factory.py`

**Interfaces:**
- Consumes: `get_gemini_key`, `get_ollama_models`, `set_ollama_models` (Task 1); `build_llm`, `OllamaLLM`, `GeminiLLM`, `llm_registry`.
- Produces: `resolve_llm(name: str, **kwargs) -> LLM`.

- [ ] **Step 1: Write the failing test**

Criar `backend/tests/test_llm_factory.py`:

```python
"""Tests for resolve_llm and the dynamic /options llms."""
import pytest
from fastapi.testclient import TestClient

from app.api.options import get_store
from app.core.config import runtime
from app.core.llm.factory import resolve_llm
from app.core.llm.gemini import GeminiLLM
from app.core.llm.ollama import OllamaLLM
from app.main import create_app


@pytest.fixture
def cfg_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_CONFIG_DIR", str(tmp_path))
    return tmp_path


class _FakeStore:
    def list_collections(self):
        return []


def test_resolve_llm_named_ollama_model(cfg_dir):
    runtime.set_ollama_models([{"id": "qwen", "model": "qwen2.5:3b-instruct"}], reserved=set())
    llm = resolve_llm("qwen", client=object())
    assert isinstance(llm, OllamaLLM)


def test_resolve_llm_registry_name(cfg_dir):
    assert isinstance(resolve_llm("gemini", client=object()), GeminiLLM)


def test_resolve_llm_unknown_raises(cfg_dir):
    with pytest.raises(KeyError):
        resolve_llm("nope", client=object())


def test_options_llms_includes_named_models(cfg_dir):
    runtime.set_ollama_models([{"id": "qwen", "model": "qwen2.5:3b-instruct"}], reserved=set())
    app = create_app()
    app.dependency_overrides[get_store] = lambda: _FakeStore()
    client = TestClient(app)
    llms = client.get("/options").json()["llms"]
    assert "qwen" in llms
    assert "gemini" in llms
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_llm_factory.py -v`
Expected: FAIL — `ModuleNotFoundError: app.core.llm.factory`.

- [ ] **Step 3: Create the factory**

Criar `backend/app/core/llm/factory.py`:

```python
"""LLM factory that resolves named Ollama models before the static registry."""
from app.core.config.runtime import get_ollama_models
from app.core.llm.base import LLM, build_llm
from app.core.llm.ollama import OllamaLLM


def resolve_llm(name: str, **kwargs) -> LLM:
    """Build an LLM by name; a named Ollama-model id resolves to OllamaLLM."""
    for entry in get_ollama_models():
        if entry.get("id") == name:
            return OllamaLLM(model=entry["model"], **kwargs)
    return build_llm(name, **kwargs)
```

- [ ] **Step 4: Export resolve_llm**

Em `backend/app/core/llm/__init__.py`, adicionar `from app.core.llm.factory import resolve_llm` e incluir `"resolve_llm"` no `__all__`.

- [ ] **Step 5: Gemini providers read the runtime key**

Em `backend/app/core/llm/gemini.py`: trocar o import `from app.core.config.settings import get_settings` por `from app.core.config.runtime import get_gemini_key`, e a linha `google_api_key=api_key or get_settings().gemini_api_key` por `google_api_key=api_key or get_gemini_key()`.

Em `backend/app/core/embedding/gemini.py`: mesma troca (`get_settings` import → `get_gemini_key`; `api_key or get_settings().gemini_api_key` → `api_key or get_gemini_key()`).

- [ ] **Step 6: Default llm_factory = resolve_llm**

Em `backend/app/experiments/orchestrator.py`: trocar `from app.core.llm.base import build_llm` por `from app.core.llm.factory import resolve_llm`, e `llm_factory: Callable = build_llm` por `llm_factory: Callable = resolve_llm`.

Em `backend/app/core/chat/deps.py`: trocar `from app.core.llm.base import build_llm` por `from app.core.llm.factory import resolve_llm`, e `llm_factory: Callable = build_llm` por `llm_factory: Callable = resolve_llm`.

- [ ] **Step 7: Options includes named model ids**

Em `backend/app/api/options.py`: adicionar `from app.core.config.runtime import get_ollama_models` e trocar `"llms": llm_registry.names(),` por:

```python
        "llms": llm_registry.names() + [m["id"] for m in get_ollama_models()],
```

- [ ] **Step 8: Run test to verify it passes**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_llm_factory.py tests/test_llm.py -v`
Expected: PASS (novos + os de LLM existentes inalterados).

- [ ] **Step 9: Commit**

```bash
git add backend/app/core/llm/factory.py backend/app/core/llm/__init__.py backend/app/core/llm/gemini.py backend/app/core/embedding/gemini.py backend/app/experiments/orchestrator.py backend/app/core/chat/deps.py backend/app/api/options.py backend/tests/test_llm_factory.py
git commit -m "feat(config): runtime gemini key + named ollama models in options"
```

---

### Task 3: API de Configurações

**Files:**
- Create: `backend/app/api/settings.py`
- Modify: `backend/app/main.py` (registrar o router)
- Test: `backend/tests/test_settings_api.py`

**Interfaces:**
- Consumes: `get_gemini_key`, `set_gemini_key`, `get_ollama_models`, `set_ollama_models` (Task 1); `llm_registry`.
- Produces: `GET /settings`, `PUT /settings/gemini-key`, `PUT /settings/ollama-models`.

- [ ] **Step 1: Write the failing test**

Criar `backend/tests/test_settings_api.py`:

```python
"""Tests for the settings endpoints (hermetic, file-backed)."""
import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_CONFIG_DIR", str(tmp_path))
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    from app.core.config.settings import get_settings

    get_settings.cache_clear()
    yield TestClient(create_app())
    get_settings.cache_clear()


def test_get_settings_masks_key(client):
    body = client.get("/settings").json()
    assert body["gemini_api_key_set"] is False
    assert body["ollama_models"] == []
    assert "gemini_api_key" not in body


def test_put_gemini_key_persists_and_never_exposes_raw(client):
    resp = client.put("/settings/gemini-key", json={"key": "secret"})
    assert resp.status_code == 200 and resp.json()["gemini_api_key_set"] is True
    assert client.get("/settings").json()["gemini_api_key_set"] is True
    assert "secret" not in client.get("/settings").text


def test_put_ollama_models_persists(client):
    resp = client.put(
        "/settings/ollama-models",
        json={"models": [{"id": "qwen", "model": "qwen2.5:3b-instruct"}]},
    )
    assert resp.status_code == 200
    assert resp.json()["ollama_models"] == [{"id": "qwen", "model": "qwen2.5:3b-instruct"}]


def test_put_ollama_models_rejects_collision(client):
    resp = client.put("/settings/ollama-models", json={"models": [{"id": "gemini", "model": "x"}]})
    assert resp.status_code == 422
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_settings_api.py -v`
Expected: FAIL — 404 (rotas inexistentes).

- [ ] **Step 3: Create the router**

Criar `backend/app/api/settings.py`:

```python
"""Endpoints for runtime-editable app settings (Gemini key, named Ollama models)."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.config.runtime import (
    get_gemini_key,
    get_ollama_models,
    set_gemini_key,
    set_ollama_models,
)
from app.core.llm.base import llm_registry

router = APIRouter()


class GeminiKeyBody(BaseModel):
    key: str


class OllamaModelBody(BaseModel):
    id: str
    model: str


class OllamaModelsBody(BaseModel):
    models: list[OllamaModelBody]


@router.get("/settings")
def get_settings_view() -> dict:
    """Return non-secret settings state for the UI."""
    return {
        "gemini_api_key_set": get_gemini_key() is not None,
        "ollama_models": get_ollama_models(),
    }


@router.put("/settings/gemini-key")
def update_gemini_key(body: GeminiKeyBody) -> dict:
    """Set or clear (empty string) the Gemini API key."""
    set_gemini_key(body.key)
    return {"gemini_api_key_set": get_gemini_key() is not None}


@router.put("/settings/ollama-models")
def update_ollama_models(body: OllamaModelsBody) -> dict:
    """Validate and persist the named Ollama models."""
    models = [m.model_dump() for m in body.models]
    try:
        set_ollama_models(models, reserved=set(llm_registry.names()))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"ollama_models": get_ollama_models()}
```

- [ ] **Step 4: Register the router**

Em `backend/app/main.py`: adicionar `settings` ao import `from app.api import chat, experiments, health, ingest, options, prompts` (→ `... prompts, settings`) e `app.include_router(settings.router)` junto dos demais.

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_settings_api.py -v`
Expected: PASS (4 passed).

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/settings.py backend/app/main.py backend/tests/test_settings_api.py
git commit -m "feat(config): settings API (gemini key + ollama models)"
```

---

### Task 4: Tela de Configurações + engrenagem no menu

**Files:**
- Modify: `frontend/src/api/types.ts`, `frontend/src/api/client.ts`
- Create: `frontend/src/pages/SettingsPage.tsx`, `frontend/src/pages/SettingsPage.test.tsx`
- Modify: `frontend/src/components/icons.tsx` (`GearIcon`), `frontend/src/components/Sidebar.tsx`, `frontend/src/App.tsx`

**Interfaces:**
- Consumes: `GET/PUT /settings*` (Task 3).
- Produces: `getSettings`, `saveGeminiKey`, `saveOllamaModels`; tipos `AppSettings`, `OllamaModel`; rota `/configuracoes`.

- [ ] **Step 1: Write the failing test**

Criar `frontend/src/pages/SettingsPage.test.tsx`:

```tsx
import { MantineProvider } from "@mantine/core";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as client from "../api/client";
import { SettingsPage } from "./SettingsPage";

vi.mock("../api/client");

function renderPage() {
  return render(
    <MantineProvider>
      <SettingsPage />
    </MantineProvider>,
  );
}

beforeEach(() => {
  vi.mocked(client.getSettings).mockResolvedValue({
    gemini_api_key_set: false,
    ollama_models: [{ id: "qwen", model: "qwen2.5:3b-instruct" }],
  });
  vi.mocked(client.saveGeminiKey).mockResolvedValue({ gemini_api_key_set: true });
  vi.mocked(client.saveOllamaModels).mockResolvedValue({
    ollama_models: [{ id: "qwen", model: "qwen2.5:3b-instruct" }],
  });
});

describe("SettingsPage", () => {
  it("loads settings and shows key state + models", async () => {
    renderPage();
    expect(await screen.findByText(/Nenhuma chave configurada/)).toBeInTheDocument();
    expect(screen.getByDisplayValue("qwen")).toBeInTheDocument();
  });

  it("saves the gemini key", async () => {
    renderPage();
    const user = userEvent.setup();
    await screen.findByText(/Nenhuma chave configurada/);
    await user.type(screen.getByLabelText(/Nova chave/), "abc");
    await user.click(screen.getByRole("button", { name: /^salvar$/i }));
    await waitFor(() => expect(client.saveGeminiKey).toHaveBeenCalledWith("abc"));
  });

  it("saves the ollama models", async () => {
    renderPage();
    const user = userEvent.setup();
    await screen.findByDisplayValue("qwen");
    await user.click(screen.getByRole("button", { name: /salvar modelos/i }));
    await waitFor(() =>
      expect(client.saveOllamaModels).toHaveBeenCalledWith([
        { id: "qwen", model: "qwen2.5:3b-instruct" },
      ]),
    );
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/pages/SettingsPage.test.tsx`
Expected: FAIL — `SettingsPage`/client fns não existem.

- [ ] **Step 3: Add types**

Ao fim de `frontend/src/api/types.ts`:

```typescript
export interface OllamaModel {
  id: string;
  model: string;
}

export interface AppSettings {
  gemini_api_key_set: boolean;
  ollama_models: OllamaModel[];
}
```

- [ ] **Step 4: Add client functions**

Em `frontend/src/api/client.ts`, adicionar `AppSettings, OllamaModel` ao bloco `import type { ... } from "./types";` e, ao fim do arquivo:

```typescript
export async function getSettings(): Promise<AppSettings> {
  return asJson<AppSettings>(await fetch(`${BASE}/settings`));
}

export async function saveGeminiKey(key: string): Promise<{ gemini_api_key_set: boolean }> {
  return asJson(await fetch(`${BASE}/settings/gemini-key`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ key }),
  }));
}

export async function saveOllamaModels(
  models: OllamaModel[],
): Promise<{ ollama_models: OllamaModel[] }> {
  return asJson(await fetch(`${BASE}/settings/ollama-models`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ models }),
  }));
}
```

- [ ] **Step 5: Create the page**

Criar `frontend/src/pages/SettingsPage.tsx`:

```tsx
import { Alert, Button, Group, PasswordInput, Stack, Text, TextInput } from "@mantine/core";
import { useEffect, useState } from "react";

import { getSettings, saveGeminiKey, saveOllamaModels } from "../api/client";
import type { OllamaModel } from "../api/types";
import { PageHeader } from "../components/PageHeader";

export function SettingsPage() {
  const [keySet, setKeySet] = useState(false);
  const [newKey, setNewKey] = useState("");
  const [models, setModels] = useState<OllamaModel[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [keySaved, setKeySaved] = useState(false);
  const [modelsSaved, setModelsSaved] = useState(false);

  useEffect(() => {
    getSettings()
      .then((s) => {
        setKeySet(s.gemini_api_key_set);
        setModels(s.ollama_models);
      })
      .catch((e) => setError(String(e)));
  }, []);

  async function saveKey() {
    setError(null);
    setKeySaved(false);
    try {
      const r = await saveGeminiKey(newKey);
      setKeySet(r.gemini_api_key_set);
      setNewKey("");
      setKeySaved(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  function addModel() {
    setModels((m) => [...m, { id: "", model: "" }]);
  }
  function updateModel(i: number, field: "id" | "model", value: string) {
    setModels((m) => m.map((row, idx) => (idx === i ? { ...row, [field]: value } : row)));
  }
  function removeModel(i: number) {
    setModels((m) => m.filter((_, idx) => idx !== i));
  }

  async function saveModels() {
    setError(null);
    setModelsSaved(false);
    try {
      const r = await saveOllamaModels(models);
      setModels(r.ollama_models);
      setModelsSaved(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div>
      <PageHeader
        eyebrow="Sistema"
        title="Configurações"
        subtitle="Variáveis gerais do sistema. Alterações valem para novas execuções."
      />

      {error && (
        <Alert color="red" variant="light" title="Erro" mb="lg" radius="lg" maw={640}>
          {error}
        </Alert>
      )}

      <div className="ditto-glass" style={{ padding: 24, maxWidth: 640, marginBottom: 24 }}>
        <Text fw={700} mb={4}>
          Chave do Gemini
        </Text>
        <Text size="sm" c="dimmed" mb="md">
          {keySet ? "Uma chave está configurada." : "Nenhuma chave configurada."}
        </Text>
        <Group align="flex-end" gap="sm">
          <PasswordInput
            label="Nova chave"
            placeholder="cole a chave aqui"
            value={newKey}
            onChange={(e) => setNewKey(e.currentTarget.value)}
            style={{ flex: 1 }}
          />
          <Button color="violet" onClick={saveKey} disabled={newKey.trim() === ""}>
            Salvar
          </Button>
          {keySaved && (
            <Text size="sm" c="#07f285">
              Salva
            </Text>
          )}
        </Group>
      </div>

      <div className="ditto-glass" style={{ padding: 24, maxWidth: 640 }}>
        <Text fw={700} mb={4}>
          Modelos Ollama
        </Text>
        <Text size="sm" c="dimmed" mb="md">
          Cada identificador vira uma opção de LLM (ex.: qwen → qwen2.5:3b-instruct).
        </Text>
        <Stack gap="xs">
          {models.map((row, i) => (
            <Group key={i} gap="sm" align="flex-end">
              <TextInput
                label={i === 0 ? "Identificador" : undefined}
                placeholder="qwen"
                value={row.id}
                onChange={(e) => updateModel(i, "id", e.currentTarget.value)}
              />
              <TextInput
                label={i === 0 ? "Modelo" : undefined}
                placeholder="qwen2.5:3b-instruct"
                value={row.model}
                onChange={(e) => updateModel(i, "model", e.currentTarget.value)}
                style={{ flex: 1 }}
              />
              <Button variant="subtle" color="gray" onClick={() => removeModel(i)}>
                Remover
              </Button>
            </Group>
          ))}
        </Stack>
        <Group mt="md" gap="sm">
          <Button variant="light" color="gray" onClick={addModel}>
            Adicionar modelo
          </Button>
          <Button color="violet" onClick={saveModels}>
            Salvar modelos
          </Button>
          {modelsSaved && (
            <Text size="sm" c="#07f285">
              Salvos
            </Text>
          )}
        </Group>
      </div>
    </div>
  );
}
```

- [ ] **Step 6: Add the GearIcon**

Em `frontend/src/components/icons.tsx`, adicionar (mesmo estilo dos existentes — stroke currentColor, 20x20):

```tsx
export function GearIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
    </svg>
  );
}
```

- [ ] **Step 7: Add the sidebar link + route**

Em `frontend/src/components/Sidebar.tsx`: importar `GearIcon` (junto dos outros ícones) e adicionar um link de Configurações imediatamente **antes** do `<div className="ditto-sidebar-foot">`, com o mesmo padrão de `ditto-navlink` e empurrado para baixo:

```tsx
      <Link
        to="/configuracoes"
        className="ditto-navlink"
        data-active={pathname.startsWith("/configuracoes")}
        aria-current={pathname.startsWith("/configuracoes") ? "page" : undefined}
        style={{ marginTop: "auto" }}
      >
        <GearIcon />
        <span>Configurações</span>
      </Link>
```

Em `frontend/src/App.tsx`: importar `import { SettingsPage } from "./pages/SettingsPage";` e adicionar a rota após a `/dialogues/:id` (ou junto das demais):

```tsx
                <Route
                  path="/configuracoes"
                  element={
                    <PageTransition>
                      <SettingsPage />
                    </PageTransition>
                  }
                />
```

- [ ] **Step 8: Run test + full suite + build**

Run: `cd frontend && npx vitest run src/pages/SettingsPage.test.tsx`
Expected: PASS (3 passed).
Run: `cd frontend && npx vitest run`
Expected: PASS (todas).
Run: `cd frontend && npm run build`
Expected: build sem erros.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/api/types.ts frontend/src/api/client.ts frontend/src/pages/SettingsPage.tsx frontend/src/pages/SettingsPage.test.tsx frontend/src/components/icons.tsx frontend/src/components/Sidebar.tsx frontend/src/App.tsx
git commit -m "feat(config): settings screen + gear nav item"
```

---

### Task 5: Feedback de pausa + bind-mount do config

**Files:**
- Modify: `backend/app/api/experiments.py` (`pause_requested` no GET)
- Modify: `frontend/src/api/types.ts` (`ExperimentDetail.pause_requested`), `frontend/src/pages/ExperimentDetailPage.tsx`
- Modify: `docker-compose.yml` (bind-mount `./backend/config`)
- Test: `backend/tests/test_experiments_api.py`, `frontend/src/pages/ExperimentDetailPage.test.tsx`

**Interfaces:**
- Consumes: `_pause_requested`, `request_pause`, `_pause_requests` (`app.experiments.orchestrator`).
- Produces: campo `pause_requested: bool` no `GET /experiments/{id}`; indicador de UI.

- [ ] **Step 1: Write the failing tests**

Em `backend/tests/test_experiments_api.py`, adicionar:

```python
def test_get_experiment_reports_pause_requested(client):
    from app.experiments.orchestrator import _pause_requests, request_pause

    files = {"questions": ("q.csv", io.BytesIO(b"pergunta,resposta_referencia\nWhere?,\n"), "text/csv")}
    exp_id = client.post("/experiments", data={"config": _config_payload()}, files=files).json()["id"]
    request_pause(exp_id)
    try:
        assert client.get(f"/experiments/{exp_id}").json()["pause_requested"] is True
    finally:
        _pause_requests.discard(exp_id)
```

Em `frontend/src/pages/ExperimentDetailPage.test.tsx`, adicionar:

```typescript
  it("shows the pausing state when pause is requested", async () => {
    vi.mocked(client.getExperiment).mockResolvedValue({
      id: 7,
      name: "running-exp",
      status: "running",
      pause_requested: true,
      progress: { completed: 1, total: 4 },
      results: [],
    });
    renderPage();
    expect(await screen.findByText(/aguardando a combinação atual terminar/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /pausando/i })).toBeDisabled();
  });
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_experiments_api.py::test_get_experiment_reports_pause_requested -v`
Expected: FAIL — resposta sem `pause_requested`.
Run: `cd frontend && npx vitest run src/pages/ExperimentDetailPage.test.tsx -t "pausing state"`
Expected: FAIL — indicador inexistente.

- [ ] **Step 3: Add pause_requested to the GET**

Em `backend/app/api/experiments.py`: adicionar `_pause_requested` ao import de `app.experiments.orchestrator` (junto do que já é importado de lá), e incluir no dict de resposta de `get_experiment` (junto de `status`/`progress`):

```python
        "pause_requested": _pause_requested(experiment_id),
```

- [ ] **Step 4: Add the type field**

Em `frontend/src/api/types.ts`, na interface `ExperimentDetail`, adicionar após `status: string;`:

```typescript
  pause_requested?: boolean;
```

- [ ] **Step 5: Show the pausing indicator**

Em `frontend/src/pages/ExperimentDetailPage.tsx`, no bloco `{isRunning && (...)}` do cabeçalho, substituir o `<Button>` de pausa por (usando `detail?.pause_requested`):

```tsx
          {isRunning && (
            <>
              <Button
                size="xs"
                variant="light"
                color="yellow"
                loading={pausing}
                disabled={pausing || (detail?.pause_requested ?? false)}
                onClick={handlePause}
                ml="auto"
              >
                {pausing || detail?.pause_requested ? "Pausando…" : "Pausar"}
              </Button>
              {detail?.pause_requested && (
                <Text size="xs" c="dimmed">
                  aguardando a combinação atual terminar…
                </Text>
              )}
            </>
          )}
```

- [ ] **Step 6: Add the config bind-mount**

Em `docker-compose.yml`, no serviço `api`, no bloco `volumes` (que já tem `./backend/prompts:/app/prompts`), adicionar a linha:

```yaml
      - ./backend/config:/app/config
```

- [ ] **Step 7: Run tests + build**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_experiments_api.py -v`
Expected: PASS (incluindo o novo).
Run: `cd frontend && npx vitest run src/pages/ExperimentDetailPage.test.tsx`
Expected: PASS.
Run: `cd frontend && npm run build` e `cd /Users/samuelhenriquesilva/Desktop/doutorado/ditto_system && docker compose config >/dev/null && echo OK`
Expected: build sem erros; `OK`.

- [ ] **Step 8: Commit**

```bash
git add backend/app/api/experiments.py frontend/src/api/types.ts frontend/src/pages/ExperimentDetailPage.tsx frontend/src/pages/ExperimentDetailPage.test.tsx docker-compose.yml backend/tests/test_experiments_api.py
git commit -m "feat(experiments): surface pause-requested state in UI"
```

---

## Self-Review

**Spec coverage:**
- Store em arquivo (loader, get/set chave, get/set/validate modelos) → Task 1. ✓
- Chave do Gemini editável nos providers → Task 2 Step 5. ✓
- `resolve_llm` + default factory + `/options.llms` com ids → Task 2. ✓
- API settings (GET mascarado, PUT chave, PUT modelos com 422) → Task 3. ✓
- Tela + engrenagem + rota + cliente/tipos → Task 4. ✓
- `pause_requested` no GET + indicador na UI → Task 5. ✓
- Bind-mount do `config` → Task 5 Step 6. ✓
- Testes backend (runtime, factory, options, settings API, pause) e frontend (SettingsPage, pausing) → todas as tasks. ✓

**Placeholder scan:** nenhum TBD/TODO; código completo em cada passo; passos de ops (docker-compose) com verificação (`docker compose config`).

**Type consistency:** `get_gemini_key`/`set_gemini_key`/`get_ollama_models`/`set_ollama_models`/`validate_ollama_models` idênticos entre Task 1 (def) e Tasks 2–3 (uso). `resolve_llm(name, **kwargs)` def Task 2 ↔ uso em orchestrator/deps. `AppSettings`/`OllamaModel` (Task 4 types) ↔ `getSettings`/`saveOllamaModels` (client) ↔ resposta da API (Task 3: `gemini_api_key_set`, `ollama_models[{id,model}]`). `pause_requested` idêntico entre GET (Task 5 backend), tipo `ExperimentDetail` e componente. `_ID_RE` reservado contra `llm_registry.names()` consistente entre validação (Task 1) e chamada (Task 3).
