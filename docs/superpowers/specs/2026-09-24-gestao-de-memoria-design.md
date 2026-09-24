# Gestão de memória com modelos locais (Macs de 8 GB)

**Status:** Fases 0, 1, 2 e 3.1–3.3 implementadas (plano `docs/superpowers/plans/2026-09-24-gestao-de-memoria-parte-1.md`); 3.4 e 4 ficam para a parte 2
**Contexto:** no M4 Pro de 8 GB a RAM acaba quando o sistema usa LLM e embeddings locais. Este documento mapeia onde a memória vai e propõe mudanças em fases, das mais baratas às estruturais.

## 1. Orçamento de memória num Mac de 8 GB

Números aproximados. A Fase 0 existe para medir os reais.

| Consumidor | Estimativa | Observação |
|---|---|---|
| macOS + navegador + IDE | 2,5–3,5 GB | fora do nosso controle |
| VM do Docker Desktop | o que estiver em *Settings → Resources* | a memória fica reservada para a VM, mesmo sem uso |
| ↳ container `api` (torch CPU + 1 modelo ST) | 0,8–1,2 GB | o import do torch sozinho custa ~300–500 MB |
| ↳ qdrant + postgres + nginx | 0,2–0,4 GB | |
| MLX Qwen2.5-3B-4bit | ~1,8 GB + KV cache | o padrão do `llm-setup-mlx.sh` |
| MLX Qwen2.5-7B-4bit | ~4,3 GB + KV cache | **não cabe** junto com o Docker em 8 GB |
| e5-small / MiniLM-L12 multilíngue (fp32) | ~470 MB cada | 118M parâmetros |

Com 3B, Docker e um embedder local, o total fica perto do limite. Com 7B, ou com qualquer duplicação de modelo (seção 2), o macOS começa a comprimir e a usar swap.

## 2. Diagnóstico: onde a RAM vaza ou se duplica

Ordenado por impacto estimado.

### P1. Embedder recarregado a cada combinação, com duas cópias no pico
`backend/app/experiments/orchestrator.py:178`: `embedder = deps.embedder_factory(embedding)` roda dentro do `itertools.product`. Cada combinação `rag × retriever × llm` lê o SentenceTransformer do disco de novo, mesmo quando o embedding é o mesmo. Como o lado direito executa antes do rebind, a instância antiga continua viva enquanto a nova carrega, então o pico é de **2 cópias do embedder de retrieval + o `eval_embedder` (linha 155)**. Quando `eval_embedding == embedding` (o caso comum), são **3 cópias do mesmo modelo**. No host (MPS), o allocator de cache do torch também não devolve essa memória ao sistema.

### P2. O LLM troca a cada combinação
O `llm` é o eixo mais interno do `itertools.product` (linha 158). Com 2 LLMs selecionados, o MLX descarrega e recarrega os pesos em **toda** combinação. O `mlx_lm.server` guarda um modelo por vez (`ModelProvider._load` zera o anterior), mas não chama `mx.clear_cache()`, então a memória liberada fica no pool do MLX e o pico se aproxima da soma dos dois modelos. Além de gastar RAM, isso deixa o experimento muito mais lento.

### P3. O prompt cache do MLX não tem limite de bytes e a memória fica *wired*
`scripts/llm.sh:28` sobe o servidor sem `--prompt-cache-size` nem `--prompt-cache-bytes`. O padrão é **10 KV caches sem limite de bytes**. Cada pergunta de RAG gera um prompt único (o contexto recuperado muda), então o cache enche de entradas que quase nunca são reaproveitadas. Para o Qwen2.5-3B (~36 KB/token), 10 prompts de 4k tokens somam ~1,4 GB. O servidor também chama `mx.set_wired_limit(max_recommended_working_set_size)`: essa memória não pode ir para swap, o que torna a pressão pior do que parece no Monitor de Atividade.

### P4. O chat carrega um embedder novo a cada mensagem
`backend/app/core/chat/graph.py:97` chama `deps.embedder_factory(cfg.embedding)` em todo turno: lê do disco, aloca, joga fora. Isso gera latência e fragmentação.

### P5. Nada limita experimentos simultâneos
`backend/app/api/experiments.py:152` agenda cada experimento como `BackgroundTask`, sem fila. Dois experimentos em paralelo têm cada um seus próprios embedders e disputam o LLM. `concurrency` aceita até 32 (`schemas.py:39`), enquanto o MLX decodifica só `MLX_PARALLEL` (4) ao mesmo tempo. O excedente fica esperando com os prompts já montados na memória.

### P6. Embedder local no MPS disputa memória com o MLX
No `make up-local`, o SentenceTransformer escolhe `mps` sozinho. O pool de cache do MPS e a memória *wired* do MLX competem pela mesma memória unificada. Modelos de ~118M rodam rápido em CPU, então a GPU não compensa nesse tamanho.

### P7. Ineficiências menores (polimento)
- `huggingface.py:17,21`: `list(map(float, vector))` converte cada dimensão num objeto `float` Python (~32 B por valor, contra 4 B no numpy). Um vetor de 384 dims passa de ~1,5 KB para ~12 KB. `encode` também roda sem `batch_size` explícito.
- `ingestion/pipeline.py:36`: embeda todos os chunks de um documento de uma vez e só depois faz o upsert, então documentos grandes viram picos grandes. `qdrant.py:60` faz um `count()` a cada `add` para gerar ids.
- `evaluation/embedding_metrics.py`: cada métrica embeda de novo os mesmos textos. Por amostra, a resposta é embedada 3×, a pergunta 2× e os contextos concatenados 2×. Na `ContextPrecision`, cada contexto vira uma chamada separada.
- `retrieval/parent_document.py:38`: para cada hit, faz `scroll` de **todos** os chunks do documento (até 1000) para usar só ±`window` vizinhos.
- `CLAUDE.md` diz que a imagem Docker não traz os embedders locais, mas o `Dockerfile` instala `.[local]` (torch CPU). A doc está desatualizada, e a imagem da API é maior do que ela sugere.

## 3. Proposta

### Fase 0: medir antes de mudar (pequena)
- `GET /system/memory`: memória do processo da API (no macOS o *physical footprint*, porque o RSS ignora páginas comprimidas, em swap e do Metal; RSS nos outros sistemas), memória MPS (`torch.mps.current_allocated_memory()`, se o torch estiver carregado), modelos carregados pelo `ModelManager` (Fase 2) e os modelos do servidor de LLM (Ollama `/api/ps`).
- Log da memória da API no fim de cada combinação do orquestrador.
- `make mem-watch`: monitor que imprime a cada 2 s a memória livre, o swap, a memória da API e do `mlx_lm.server` (footprint no macOS) e os modelos carregados, enquanto você roda algo no app. Serve de linha de base antes e depois de cada fase.

### Fase 1: ganhos rápidos de configuração (sem mexer no domínio)
Um perfil `MEMORY_PROFILE=low|standard` no `.env`. O `make setup` detecta via `sysctl hw.memsize` e escolhe `low` quando a RAM é ≤ 8 GB. No perfil `low`:

| Item | Hoje | `low` |
|---|---|---|
| MLX `--prompt-cache-size` / `--prompt-cache-bytes` | 10 / ilimitado | 2 / 512M |
| MLX `--decode-concurrency` | 4 | 2 |
| Modelo padrão do `llm-setup` | 3B-4bit | 3B-4bit, com aviso em `model-add` para modelos > 3 GB |
| Ollama | `NUM_PARALLEL=4` | `NUM_PARALLEL=2`, `MAX_LOADED_MODELS=1`, `KEEP_ALIVE=5m`, `FLASH_ATTENTION=1`, `KV_CACHE_TYPE=q8_0` |
| Docker | sem limites | `mem_limit` por serviço (api 1,5g, qdrant 512m, postgres 256m) |
| Recomendação do `make doctor` | `up` ou `up-local` | `up-local` (sem a VM do Docker nem uma segunda cópia do torch) |
| `concurrency` máximo aceito pela API | 32 | igual ao `decode-concurrency` do servidor |

Custo baixo, risco baixo. Resolve P3 e alivia P5.

### Fase 2: `ModelManager` para modelos locais (núcleo da proposta)
Um gerenciador por processo em `backend/app/core/models/manager.py`, que vira a única porta de entrada para instanciar embedders.

```python
class ModelManager:
    def acquire(self, name: str) -> ContextManager[Embedder]: ...
    def loaded(self) -> list[LoadedModel]: ...   # para /system/memory
    def release_all(self) -> None: ...
```

Regras:
1. **Cache por nome.** O mesmo embedder carrega uma vez e é compartilhado entre orquestrador, ingestão, chat e avaliação. Resolve P1 e P4.
2. **Contagem de referências.** `acquire` é um context manager, e um modelo em uso nunca é despejado no meio de uma run.
3. **Limite de modelos locais residentes.** `MAX_LOCAL_MODELS=1` no perfil `low`. Pedir um modelo diferente despeja o anterior (LRU) se ninguém o estiver usando; se estiver, espera numa `Condition`. É isso que garante "um modelo local por vez".
4. **Despejo de verdade.** Remove as referências, roda `gc.collect()` e depois `torch.mps.empty_cache()` ou `torch.cuda.empty_cache()`, conforme o device.
5. **Remotos ficam fora.** O `Embedder` ganha `is_local: bool` e `estimated_bytes: int`. Gemini não conta no limite.
6. **A GPU é do LLM; o embedder usa a que sobrar.** Em qualquer perfil, o embedder só roda na GPU (MPS/CUDA) quando nenhum LLM local ocupa a GPU. Se houver chance de concorrência, ele vai para a CPU. Embedders são pequenos e menos críticos que o LLM, então perdem a disputa. Regras concretas (resolve P6):
   - perfil `low`: sempre CPU;
   - perfil `standard`: GPU só se o LLM do experimento for remoto (Gemini) ou se o servidor local confirmar que não há modelo carregado (Ollama `/api/ps` vazio depois de um `unload`). Com o MLX, que não descarrega o modelo, o embedder fica em CPU;
   - trocar de device descarrega o embedder e o recarrega no device novo, passando pelo mesmo caminho de despejo da regra 4;
   - `EMBEDDING_DEVICE=cpu|auto` no `.env` permite forçar CPU sempre. Não há opção para forçar GPU junto com o LLM.

Coordenação com o servidor de LLM, via uma interface `LLMServer` no mesmo estilo interface + registry:
- `OllamaServer.unload(model)` → `POST /api/generate {"model": m, "keep_alive": 0}`.
- `MLXServer.unload(model)` → não existe endpoint. O servidor já mantém um modelo só, então a medida possível é agrupar as runs por LLM (Fase 3). Reiniciar o processo fica como último recurso, fora do escopo.
- No perfil `low`, antes de carregar um embedder local quando o orçamento não comporta os dois, o manager pede ao servidor que descarregue o LLM (só no Ollama).

Testes: um embedder fake que conta instanciações, verificando que duas runs com o mesmo embedding carregam uma vez, que o limite 1 despeja o anterior e que um modelo em uso bloqueia o despejo. Nada de rede, como já é a convenção do projeto.

### Fase 3: orquestrador ciente de memória
1. **Reordenar o produto cartesiano** para `llm → (chunking, embedding) → rag → retriever`. Cada LLM carrega uma vez por experimento e cada embedder uma vez por LLM. A ordem das runs muda, mas os resultados não (resolve P2).
2. **Fila global de experimentos.** Um semáforo no processo deixa um experimento rodando por vez e os demais com status `queued`. O front já lida com status, então basta mostrar "na fila".
3. **Pré-checagem de memória.** Antes de rodar, estima o pico: maior LLM (tamanho do `/api/tags` do Ollama ou da pasta do modelo no cache HF do MLX) + embedders locais + overhead, comparado com a RAM livre. Acima do limite, a UI avisa antes de começar.
4. **Execução em estágios** (padrão nos dois perfis, com a flag `staged=false` como saída de emergência). Garante um modelo por vez mesmo com embedders locais:
   - **A. Embeddings das perguntas:** para cada embedding, calcula os vetores de todas as perguntas de uma vez (as perguntas já são conhecidas) e descarrega o embedder.
   - **B. Geração:** para cada LLM, roda as combinações com os vetores pré-calculados. Só o LLM fica residente. Exceções: `hyde` e `multi_query` embedam texto gerado pelo LLM, então precisam dos dois modelos juntos. Nesses casos o embedder roda em CPU enquanto o LLM está na GPU (regra 6 da Fase 2), então nunca disputam a mesma memória de GPU.
   - **C. Avaliação:** descarrega o LLM, carrega o `eval_embedder` uma vez e pontua todos os `RunResult` persistidos em lote. De quebra, dá para reavaliar com outras métricas sem gerar as respostas de novo.

   Isso exige que os retrievers aceitem um vetor pré-calculado (`retrieve(query, query_vector=None)`) e que as métricas passem a rodar depois da geração. É a mudança mais invasiva, por isso fica por último.

### Fase 4: polimento do código (P7)
- `HuggingFaceEmbedder`: `encode(texts, batch_size=32, convert_to_numpy=True).tolist()`.
- Ingestão em streaming: embed + upsert em lotes de 256 chunks, com ids por contador local ou UUID em vez de `count()`.
- Avaliação: por amostra, junta os textos únicos (pergunta, resposta, referência, contextos, contexto concatenado), embeda tudo numa chamada `embed_documents` e passa os vetores para as métricas.
- `ParentDocumentRetriever`: `scroll` com filtro `Range` em `chunk_index` (`index ± window`) em vez de trazer o documento inteiro.
- Qdrant: `on_disk=True` nos vetores de coleções grandes, se a Fase 0 mostrar que isso importa.
- Atualizar o `CLAUDE.md` sobre os embedders locais na imagem Docker.

## 4. Ordem sugerida e ganho esperado

| Fase | Esforço | Risco | Ganho esperado em 8 GB |
|---|---|---|---|
| 0: medição | ~0,5 dia | nenhum | linha de base para validar o resto |
| 1: perfil `low` | ~0,5–1 dia | baixo | −1 a −2 GB de pico (prompt cache, sem Docker VM, concorrência) |
| 2: `ModelManager` | ~1–2 dias | médio | −0,5 a −1,5 GB (fim das cópias duplicadas de embedder); chat mais rápido |
| 3.1–3.3: ordem, fila, pré-checagem | ~1 dia | baixo | fim do vaivém de LLM; sem experimentos concorrentes |
| 3.4: estágios | ~2–3 dias | médio/alto | garante 1 modelo por vez com embedders locais |
| 4: polimento | ~1 dia | baixo | picos menores em ingestão e avaliação grandes |

Ordem: 0 → 1 → 2 → 3.1–3.3 → 3.4. Os estágios deixaram de ser opcionais (decisão de 2026-09-24), mas vêm por último porque dependem do `ModelManager` e da reordenação.

## 5. Decisões

### Tomadas (2026-09-24)
- **O limite é por contagem de modelos** (`MAX_LOCAL_MODELS`), não por orçamento em bytes. É simples e previsível. Um orçamento em bytes pode vir depois, se a medição pedir.
- **Máquinas com ≤ 8 GB começam no perfil `low`.** O `make up` **recomenda** o `up-local`, mas não troca sozinho.
- **O perfil é sempre visível e reversível.** O sistema informa qual perfil está ativo, o que ele muda e como trocar (seção 6).

- **Um modelo por vez é o padrão:** a execução em estágios (3.4) vale para os dois perfis.
- **O embedder nunca disputa a GPU com o LLM**, nem no perfil `standard`. Havendo risco de concorrência, o embedder vai para a CPU (regra 6 da Fase 2).

## 6. Perfil de memória: como aparece para quem usa

### O que cada perfil significa

| | `low` (padrão com ≤ 8 GB) | `standard` (padrão com > 8 GB) |
|---|---|---|
| Para quem | Macs de 8 GB, ou máquinas com outros apps pesados abertos | Máquinas com folga de RAM |
| Modelos locais residentes na API (`MAX_LOCAL_MODELS`) | 1 (trocar de embedder descarrega o anterior) | 3 |
| Execução em estágios (1 modelo por vez) | sim | sim |
| Device dos embedders locais | CPU | GPU só sem LLM local na GPU; senão CPU |
| MLX: paralelismo / cache de prompts | 2 / 2 entradas, 512 MB | 4 / 10 entradas, sem teto |
| Ollama | `NUM_PARALLEL=2`, `MAX_LOADED_MODELS=1`, KV em q8_0 | `NUM_PARALLEL=4`, padrões do Ollama |
| Concorrência máxima de um experimento | 2 | 32 |
| Limites de memória nos containers | sim | não |
| Custo | experimentos mais lentos (menos paralelismo, recarga ao trocar de modelo) | risco de swap se a RAM não comportar |

Valores explícitos no `.env` (por exemplo `MLX_PARALLEL=3`) têm precedência sobre o perfil. O perfil só preenche o que não foi definido.

### Como trocar
Um comando, que grava no `.env` e reinicia o que precisa:

```bash
make memory-profile                    # mostra o perfil ativo e o que ele configura
make memory-profile PROFILE=standard   # troca para standard
make memory-profile PROFILE=low        # volta para low
```

Equivalente manual: editar `MEMORY_PROFILE=low|standard` no `.env` e rodar `make llm-down && make llm-up` e depois `make up` (ou `make up-local`).

### Onde o sistema avisa
- **`make setup`**, na detecção: "Memória: 8 GB → perfil `low` (1 modelo local por vez, menos paralelismo). Para trocar: `make memory-profile PROFILE=standard`."
- **`make up`, no perfil `low`**: uma linha de aviso, sem bloquear: "Perfil `low` ativo. Recomendado: `make up-local` (economiza a memória da VM do Docker). Para trocar o perfil: `make memory-profile PROFILE=standard`."
- **`make doctor`**: mostra a RAM total, o perfil ativo e a recomendação.
- **UI, página de Configurações**: um bloco só de leitura com o perfil ativo, o resumo da tabela acima e o comando para trocar. A troca fica no terminal porque envolve reiniciar o servidor de LLM.
- **`GET /system/memory`** (Fase 0) inclui o campo `profile`.
- **`CLAUDE.md` e o README**: uma seção curta com a tabela e os comandos.
