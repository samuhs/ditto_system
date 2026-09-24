# Inferência de LLMs pequenos (0,5B–4B) para os experimentos do Ditto

Pesquisa feita em 2026-09-23. Versões consultadas nesta data: Ollama v0.34.3, llama.cpp b11149 / v0.5.0, vLLM v0.30.0, SGLang v0.5.20, mlx-lm 0.31.3, LMDeploy v0.17.0, ExLlamaV3 v1.5.1, TensorRT-LLM v1.2.1, llamafile 0.10.6, TGI v3.3.7. Essas ferramentas mudam de um mês para o outro, então vale conferir as versões de novo antes de fixar qualquer decisão.

---

## 1. Resumo e recomendação

**O gargalo hoje está no Ditto, não no servidor.** O `run_experiment` percorre as perguntas uma a uma (`for question in questions:` em `backend/app/experiments/orchestrator.py`), então só existe uma requisição ao LLM em andamento por vez. Com um único fluxo, todos os servidores ficam limitados pela velocidade de decode de uma sequência, e a diferença entre eles é pequena. Continuous batching, paged attention e RadixAttention só aumentam o throughput quando **várias requisições chegam ao mesmo tempo**. Portanto, a mudança que mais reduz o tempo total do grid é **processar N perguntas em paralelo dentro de cada combinação** (seção 5). A escolha do servidor vem depois.

Depois dessa mudança, a recomendação por hardware fica assim:

| Hardware | Recomendação para throughput | Alternativa / "fácil" |
|---|---|---|
| **Linux + NVIDIA Turing ou mais nova (RTX 20xx/30xx/40xx/50xx), ≥ 6–8 GB** | **vLLM** (`vllm serve`, BF16 para ≤1,5B; AWQ/GPTQ via Marlin ou FP8 em Ada+ para 3–4B), com 16–64 requisições concorrentes. Prefix caching vem ligado por padrão ([source](https://raw.githubusercontent.com/vllm-project/vllm/v0.30.0/vllm/config/cache.py)). O SGLang (RadixAttention) é o concorrente direto, mas agora exige CUDA 13 ([docs](https://docs.sglang.io/docs/get-started/install)). | `llama-server -np 8` (GGUF), ou Ollama com `OLLAMA_NUM_PARALLEL` |
| **NVIDIA 4 GB ou pré-Turing (GTX 10xx, compute capability < 7.5)** | **llama.cpp `llama-server`** com GGUF Q4_K_M/Q5_K_M e `-np 4..8`. O vLLM exige CC ≥ 7.5 ([docs](https://docs.vllm.ai/en/latest/getting_started/installation/gpu.html)). | Ollama |
| **Apple Silicon (máquina de dev)** | **`llama-server`** (Metal, GGUF, `-np 4..8`) **ou `mlx_lm.server`** (MLX 4-bit, batching nativo com `--decode-concurrency` 32 por padrão; [source](https://github.com/ml-explore/mlx-lm/blob/main/mlx_lm/server.py)). Qual dos dois ganha depende do modelo e do chip: meça com o protocolo da seção 6. | Ollama com `OLLAMA_NUM_PARALLEL=4..8` |
| **Só CPU** | **`llama-server`** (GGUF Q4/Q8, `-np` baixo, 2–4). Em CPU o ganho de batching é bem menor. | Ollama |

**Vale manter o Ollama como padrão "fácil"? Sim, com um ajuste.** Desde o PR #16031 (commit de 2026-05-29, "Remove CGO engines, use llama-server exclusively for GGML models") o Ollama roda o **`llama-server` upstream como subprocesso**, passando `-np <numParallel>` e `-c <num_ctx × numParallel>` ([`llm/llama_server.go`](https://github.com/ollama/ollama/blob/main/llm/llama_server.go), [commits](https://github.com/ollama/ollama/commits/main/llm/llama_server.go)). Na prática, para modelos GGUF ele usa o mesmo continuous batching do llama.cpp. O porém é o padrão: **`OLLAMA_NUM_PARALLEL` = 1** ([FAQ](https://docs.ollama.com/faq), [`envconfig/config.go`](https://github.com/ollama/ollama/blob/main/envconfig/config.go)). Sem mudar isso, o Ollama serializa as requisições mesmo que o Ditto passe a enviá-las em paralelo. O `make llm-setup` deve passar a configurar essa variável (seção 5.3).

Estratégia sugerida:
1. Paralelizar as perguntas no orquestrador (maior ganho, vale para qualquer backend, inclusive Gemini).
2. Manter o Ollama como padrão do `make llm-setup`, agora com `OLLAMA_NUM_PARALLEL` > 1.
3. Para rodadas grandes em Linux+NVIDIA, usar o vLLM via `CustomLLM(base_url="http://host.docker.internal:8001/v1")`, sem mudar código.
4. Validar no hardware real com o protocolo da seção 6 antes de fixar a escolha na tese.

---

## 2. Contexto e critérios

**Carga de trabalho do Ditto.** Grid chunking × embedding × técnica RAG × retriever × LLM sobre um CSV de perguntas. Cada pergunta gera de 1 a 5+ chamadas ao LLM (naive = 1; hyde, rerank, crag, compression e agentic fazem chamadas extras), e métricas LLM-based podem acrescentar outras. Os prompts de uma mesma técnica compartilham o template (system prompt e instruções), o que favorece **prefix caching**. O contexto recuperado varia de pergunta para pergunta, então o reaproveitamento cobre só o prefixo do template.

**Integração.** O backend chama os LLMs por `langchain_openai.ChatOpenAI` (`backend/app/core/llm/custom.py`), e `OllamaLLM` é só uma subclasse apontando para `/v1` do Ollama. Qualquer servidor com `/v1/chat/completions` compatível com OpenAI entra sem código novo. O servidor roda no **host** (fora do Docker) para ter acesso à GPU.

**Critérios avaliados.**
1. Throughput com requisições concorrentes (continuous batching, paged attention, prefix caching) e velocidade de um único fluxo.
2. Pouca VRAM e quantização (GGUF, AWQ, GPTQ, FP8, EXL2/EXL3, MLX 4-bit); fallback para CPU.
3. API compatível com OpenAI.
4. Plataformas (macOS Metal, Linux NVIDIA, CPU) e facilidade de instalação.
5. Disponibilidade de modelos pequenos.

**Single-stream × concorrência.** No decode, um modelo pequeno é limitado pela banda de memória: a cada token, todos os pesos são lidos. Com uma sequência só, a GPU fica ociosa na maior parte do tempo. Com batching, a mesma leitura de pesos serve B sequências, e o throughput agregado sobe quase linearmente até a computação ou o KV cache virarem o limite. Em compensação, a latência de cada requisição aumenta um pouco. É esse o mecanismo que o artigo do SGLang e a documentação do vLLM exploram ([arXiv 2312.07104](https://arxiv.org/abs/2312.07104)). Uma medição de terceiros com Ollama, que não é fonte primária e serve só como ilustração, relata throughput agregado de ~18 para ~33 tok/s (≈1,8×) com 4 requisições paralelas, enquanto a velocidade por requisição caiu de ~22 para ~10 tok/s ([jangwook.net, terceiro](https://jangwook.net/en/blog/en/local-llm-concurrent-requests-num-parallel-experiment/)). Para o Ditto, que só se importa com o tempo total do lote, esse é o trade-off certo.

---

## 3. Tabela comparativa

| Framework | Batching concorrente | Prefix caching | Quantização (relevante p/ 0,5–4B) | Plataformas | API OpenAI | Instalação | Observação |
|---|---|---|---|---|---|---|---|
| **Ollama** v0.34 | Sim, via llama-server interno (`-np`); **padrão 1** | Herdado do llama-server (cache por slot) | GGUF (Q4_K_M etc.); MLX em preview no Mac | macOS, Linux (NVIDIA/AMD), Windows, CPU | Sim (`/v1`) | brew / script / app | Algumas arquiteturas são forçadas a paralelo = 1 |
| **llama.cpp `llama-server`** | Sim, `--cont-batching` ligado por padrão; `-np` auto = 4 | `--cache-prompt` ligado; `--cache-reuse` | GGUF 1,5–8 bit | macOS Metal, CUDA, HIP, Vulkan, CPU | Sim | brew, binários, Docker, fonte | A opção mais versátil em hardware |
| **vLLM** v0.30 | Sim (continuous batching, PagedAttention) | **Ligado por padrão** (APC) | AWQ, GPTQ (Marlin), FP8 (Ada+), bitsandbytes, GGUF | Linux + NVIDIA CC ≥ 7.5; CPU x86/ARM; macOS só CPU experimental ou vllm-metal | Sim | pip/uv, Docker | Reserva 92% da VRAM por padrão |
| **SGLang** v0.5.20 | Sim | **RadixAttention** (ligado por padrão) | AWQ, GPTQ, FP8, GGUF, bnb… | Linux NVIDIA (CUDA 13), AMD, Xeon, TPU; Apple Metal a partir do código-fonte | Sim | uv/pip, Docker | O mais forte em reuso de prefixo; exige mais setup |
| **mlx-lm server** 0.31.3 | Sim (`BatchGenerator`, decode 32 / prefill 8) | LRU prompt cache | MLX 4/8-bit (mlx-community) | Só Apple Silicon | Sim (básico) | pip / brew | "Não recomendado para produção"; `--kv-bits` desliga o batching |
| **LM Studio** 0.4.x | Sim (llama.cpp ≥ 2.0.0; MLX a partir do 0.4.2), padrão 4 | Não verificado | GGUF, MLX | macOS, Windows, Linux | Sim | App / `llmster` headless | Fechado; bom para uso interativo |
| **TGI** v3.3.7 | Sim | Sim | Vários | Linux NVIDIA/AMD… | Sim | Docker | **Em modo de manutenção**, não usar em projeto novo |
| **ExLlamaV3 + TabbyAPI** | Sim (paged attention em Ampere+) | Não verificado | EXL3 (2–8 bit), EXL2 via ExLlamaV2 | Linux/Windows + NVIDIA; sem Mac/CPU | Sim | pip wheels | "Hobby project", não voltado para produção |
| **TensorRT-LLM** v1.2.1 | Sim (in-flight batching) | Sim | FP8 (Ada/Hopper), INT8, INT4 | Linux x86_64/aarch64, Ampere+ | Sim (`trtllm-serve`) | pip/NGC, CUDA 13.1 | Pesado; não compensa para modelos de 0,5–4B |
| **LMDeploy** v0.17 | Sim ("persistent batch") | Sim | AWQ 4-bit, KV int8/int4 | NVIDIA Volta–Hopper, Ascend, ROCm, Mac (Metal) | Sim | pip | Alternativa ao vLLM; cobertura de modelos menor |
| **llamafile** 0.10.6 | Herdado do llama.cpp | Herdado | GGUF | Binário único multi-OS | Não verificado na versão 0.10 | 1 arquivo | Não traz vantagem sobre o llama-server |
| **MLC-LLM** | Sim (batching no servidor) | Não verificado | Formatos próprios (q4f16 etc.) | CUDA, ROCm, Metal, Vulkan, WebGPU, mobile | Sim | pip nightly | Exige compilar/converter os modelos; último commit em 2026-08-17 |

---

## 4. Frameworks

### 4.1 Ollama
- **Arquitetura atual.** Para GGUF, o Ollama lança o binário `llama-server` do llama.cpp como subprocesso, com flags como `-c <NumCtx × numParallel>` e `-np <numParallel>`, e deixa o llama-server detectar sozinho `-ngl`, threads e flash attention ([`llm/llama_server.go`](https://github.com/ollama/ollama/blob/main/llm/llama_server.go)). Essa mudança entrou pelo PR #16031 (2026-05-29) ([commits](https://github.com/ollama/ollama/commits/main/llm/llama_server.go)). Já está na v0.34.3 (confirmado via `compare` no GitHub). A primeira release exata que trouxe a mudança **não foi verificada**.
- **Faz batching de verdade?** Sim. Com `OLLAMA_NUM_PARALLEL=N`, o llama-server interno recebe N slots e aplica continuous batching. A conclusão vem da leitura do código e não foi medida neste estudo.
- **Variáveis** ([FAQ](https://docs.ollama.com/faq)):
  - `OLLAMA_NUM_PARALLEL`: "maximum number of parallel requests each model will process at the same time, **default 1**". A memória necessária escala com `OLLAMA_NUM_PARALLEL × OLLAMA_CONTEXT_LENGTH`.
  - `OLLAMA_MAX_LOADED_MODELS`: segundo a FAQ, o padrão é 3 × nº de GPUs (ou 3 em CPU). No código, `MaxRunners` tem default 0, que significa automático ([config.go](https://github.com/ollama/ollama/blob/main/envconfig/config.go)).
  - `OLLAMA_MAX_QUEUE`: 512. `OLLAMA_KV_CACHE_TYPE`: `f16` (padrão), `q8_0` ou `q4_0`, útil para caber mais slots em 4–8 GB. `OLLAMA_FLASH_ATTENTION`.
- **Pegadinha.** O scheduler força `numParallel = 1` para algumas famílias: `mllama`, `qwen3vl`, `qwen3vlmoe`, `qwen35`, `qwen35moe`, `qwen3next`, `lfm2`, `lfm2moe`, `nemotron_h*` ([`server/sched.go`](https://github.com/ollama/ollama/blob/main/server/sched.go)). Qwen2.5, Qwen3 (densos), Llama 3.2, Gemma 3, Phi-4-mini e SmolLM2 não estão na lista. **Qwen3.5 pequeno no Ollama fica sem paralelismo.**
- **Apple Silicon / MLX.** Existe um motor MLX, ainda em *preview* (post de 2026-03-30), que o blog associa a Macs com mais de 32 GB e a modelos específicos ([blog](https://ollama.com/blog/mlx), [blog de desempenho](https://ollama.com/blog/mlx-performance)). Não verifiquei se ele faz batching concorrente.
- **Modelos pequenos.** O catálogo oficial tem [qwen2.5](https://ollama.com/library/qwen2.5), [qwen3](https://ollama.com/library/qwen3), [llama3.2](https://ollama.com/library/llama3.2), [gemma3](https://ollama.com/library/gemma3), [phi4-mini](https://ollama.com/library/phi4-mini) e [smollm2](https://ollama.com/library/smollm2).

### 4.2 llama.cpp `llama-server`
- Flags ([README do server](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)):
  - `--parallel/-np N`: número de slots, "default: -1, -1 = auto". No código, auto vira **4 slots com KV unificado** ([server-context.cpp](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/server-context.cpp)).
  - `--cont-batching`: "enabled" por padrão.
  - `-kvu/--kv-unified`: um único buffer de KV compartilhado entre as sequências, ligado quando `-np` é auto. Assim o contexto não fica dividido rigidamente por slot.
  - `--cache-prompt` (ligado) e `--cache-reuse N` (reuso por KV shifting): o prefixo comum do template é reaproveitado **dentro do mesmo slot**. Isso é menos geral que o RadixAttention.
  - `-ngl auto|all|N`: offload parcial para a GPU. É o que permite rodar em GPU de 4 GB ou fazer fallback para CPU.
  - `GET /slots` expõe métricas por slot.
- Quantização de 1,5 a 8 bits em GGUF. Apple Silicon é "first-class citizen" (Metal); também há CUDA, HIP, Vulkan e CPU ([README](https://github.com/ggml-org/llama.cpp/blob/master/README.md)).
- Instalação: `brew install llama.cpp` (formula em 0.4.1, [formulae.brew.sh](https://formulae.brew.sh/formula/llama.cpp)), binários nas [releases](https://github.com/ggml-org/llama.cpp/releases) e imagens `ghcr.io/ggml-org/llama.cpp:server-cuda` e `server-cuda13` ([docker.md](https://github.com/ggml-org/llama.cpp/blob/master/docs/docker.md)). Baixa modelos direto do HF com `-hf` (ex.: [Qwen/Qwen3-4B-GGUF](https://huggingface.co/Qwen/Qwen3-4B-GGUF), [bartowski/Llama-3.2-3B-Instruct-GGUF](https://huggingface.co/bartowski/Llama-3.2-3B-Instruct-GGUF)).

### 4.3 vLLM
- Requisitos: **Linux**, Python 3.10–3.13, NVIDIA com **compute capability ≥ 7.5** (T4, RTX 20xx em diante), wheels com CUDA 12.9 (também há 12.8 e 13.0). Não roda nativamente no Windows (só via WSL) ([docs GPU](https://docs.vllm.ai/en/latest/getting_started/installation/gpu.html)).
- **macOS**: só CPU, experimental, compilado do fonte, FP32/FP16 ([docs CPU](https://docs.vllm.ai/en/latest/getting_started/installation/cpu.html)). Para usar a GPU do Mac existe o plugin comunitário **vllm-metal** (MLX por baixo, macOS 15+, `brew install vllm-project/vllm-metal/vllm-metal`) ([repo](https://github.com/vllm-project/vllm-metal)). Não avaliei a maturidade dele para este caso de uso.
- **Memória.** `--gpu-memory-utilization` tem **padrão 0,92** e reserva essa fração da VRAM para pesos + KV cache ([engine args](https://docs.vllm.ai/en/latest/configuration/engine_args.html), [cache.py](https://raw.githubusercontent.com/vllm-project/vllm/v0.30.0/vllm/config/cache.py)). Em GPU de 6–8 GB que também roda o desktop, reduza para ~0,8 e limite `--max-model-len` (ex.: 8k) para não estourar. `--cpu-offload-gb` existe (padrão 0).
- **Prefix caching**: `enable_prefix_caching: bool = True` na v0.30.0 ([cache.py](https://raw.githubusercontent.com/vllm-project/vllm/v0.30.0/vllm/config/cache.py)). A página de APC ainda diz que é preciso ligá-lo ([docs APC](https://docs.vllm.ai/en/latest/features/automatic_prefix_caching.html)); vale o código-fonte. O mecanismo faz hash de blocos de KV ([design](https://docs.vllm.ai/en/latest/design/prefix_caching.html)).
- **Quantização** ([docs](https://docs.vllm.ai/en/latest/features/quantization/)): AWQ exige Turing+, Marlin (GPTQ/AWQ/FP8) Turing+, FP8 W8A8 Ada/Hopper; GGUF tem a maior cobertura de hardware. Para 0,5–1,5B, BF16 já cabe com folga em 8 GB. Para 3–4B em 6–8 GB, use AWQ/GPTQ 4-bit (ex.: [Qwen2.5-3B-Instruct-AWQ](https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-AWQ)).
- Suporta "continuous batching" e PagedAttention; `--max-num-seqs` limita as sequências simultâneas.

### 4.4 SGLang
- "Low-latency, high-throughput inference with **RadixAttention**, prefix caching…", API compatível com OpenAI ([docs](https://docs.sglang.io/)). O RadixAttention mantém os prefixos numa árvore radix e os reaproveita entre requisições diferentes. O artigo relata até 6,4× de throughput em cargas que incluem RAG ([arXiv 2312.07104](https://arxiv.org/abs/2312.07104)). O número é dos próprios autores e não foi medido neste estudo.
- `--disable-radix-cache` tem padrão `False`, ou seja, o cache vem ligado. `--mem-fraction-static` fica em ~0,88 ([server args](https://docs.sglang.io/docs/advanced_features/server_arguments)).
- **Requisitos**: Python ≥ 3.10 e **CUDA 13**. A 0.5.19 foi a última release com CUDA 12. FlashInfer exige sm75+ ([install](https://docs.sglang.io/docs/get-started/install)). Suporte a Apple Metal via MLX, só compilando do fonte, macOS 14+ ([Apple Metal](https://docs.sglang.io/docs/hardware-platforms/apple_metal)).
- Para o Ditto é o candidato mais bem alinhado em teoria (muitas chamadas com o mesmo template). Na prática, a vantagem sobre o vLLM, que também faz prefix caching, precisa ser medida.

### 4.5 MLX / `mlx_lm.server` (Apple Silicon)
- Servidor HTTP que "mirrors OpenAI's chat completion", com `/v1/chat/completions` e `/v1/models`. Aviso explícito: "**not recommended for production** as it only implements basic security checks" ([SERVER.md](https://github.com/ml-explore/mlx-lm/blob/main/mlx_lm/SERVER.md)).
- **Batching**: o `server.py` atual usa `BatchGenerator` quando o modelo é "batchable" (sem draft model e com cache mesclável), com `--decode-concurrency` (padrão **32**) e `--prompt-concurrency` (padrão **8**). Também tem um LRU prompt cache (`--prompt-cache-size` 10) ([server.py](https://github.com/ml-explore/mlx-lm/blob/main/mlx_lm/server.py)). Com `--kv-bits` (KV quantizado), "does not support batching" ([SERVER.md](https://github.com/ml-explore/mlx-lm/blob/main/mlx_lm/SERVER.md)).
- Instalação: `pip install mlx-lm` (0.31.3, 2026-04-22) ou `brew install mlx-lm` ([formula](https://formulae.brew.sh/formula/mlx-lm)). Os modelos 4-bit prontos ficam em [mlx-community](https://huggingface.co/mlx-community) (ex.: [Qwen3-4B-4bit](https://huggingface.co/mlx-community/Qwen3-4B-4bit)).

### 4.6 LM Studio
- "Parallel requests via continuous batching", com "Max Concurrent Predictions" padrão **4**. No motor llama.cpp exige a versão ≥ 2.0.0 ([docs](https://lmstudio.ai/docs/app/advanced/parallel-requests)). O MLX ganhou continuous batching no LM Studio 0.4.2 (mlx-engine 1.0.0) ([changelog](https://lmstudio.ai/changelog/lmstudio-v0.4.2)).
- Tem modo headless (`llmster`, `lms daemon up`) com endpoints OpenAI ([docs headless](https://lmstudio.ai/docs/app/api/headless)). Os motores são os mesmos do llama.cpp e do MLX, então não oferece vantagem de desempenho sobre eles. É software fechado e mais difícil de automatizar num `make`.

### 4.7 Hugging Face TGI
- **Em modo de manutenção**: "we will accept pull requests for minor bug fixes, documentation improvements and lightweight maintenance tasks". O próprio README recomenda vLLM, SGLang, llama.cpp e MLX ([repo](https://github.com/huggingface/text-generation-inference)). Última release: v3.3.7 (2025-12-19). **Descartado.**

### 4.8 ExLlamaV3 / ExLlamaV2 + TabbyAPI
- ExLlamaV3: formato EXL3, "continuous, dynamic batching", CUDA 12.4+, Linux/Windows, Ampere+, **sem macOS** ([repo](https://github.com/turboderp-org/exllamav3)).
- TabbyAPI: API compatível com OpenAI sobre ExLlamaV3 (e V2), com batching via paged attention em Ampere+. O próprio README diz "hobby project… not meant to run on production servers" ([repo](https://github.com/theroyallab/tabbyAPI)).
- Para modelos de 0,5–4B, o forte do EXL3 (qualidade em 2–3 bits para caber modelos grandes) importa pouco. **Não recomendado** para o Ditto.

### 4.9 TensorRT-LLM
- Linux x86_64/aarch64. Ampere, Ada, Hopper e Blackwell; RTX 30xx/40xx estão nessas arquiteturas, mas GeForce não aparece listada nominalmente ([support matrix](https://nvidia.github.io/TensorRT-LLM/reference/support-matrix.html)). Exige CUDA 13.1 e PyTorch 2.10 ([install](https://nvidia.github.io/TensorRT-LLM/installation/linux.html)).
- É o mais rápido em datacenter, mas o custo de setup não se paga para 0,5–4B numa GPU de consumo. **Não recomendado.**

### 4.10 LMDeploy
- Motores TurboMind e PyTorch, "persistent batch", AWQ 4-bit, KV int8/int4, prefix caching, `api_server` OpenAI. Hardware: NVIDIA (Volta–Hopper), Ascend, ROCm e Mac (Metal). Afirma "up to 1.8x higher request throughput than vLLM" ([repo](https://github.com/InternLM/lmdeploy)), mas isso é alegação do próprio projeto. É uma alternativa razoável ao vLLM em NVIDIA. Não verifiquei se cobre Gemma 3, Phi-4-mini e SmolLM no TurboMind.

### 4.11 llamafile
- Empacota o llama.cpp num executável único (Cosmopolitan). A versão 0.10 foi reescrita para acompanhar o llama.cpp atual ([repo](https://github.com/mozilla-ai/llamafile)). Como tem o mesmo motor, o `llama-server` direto é mais simples de configurar. Não verifiquei a API OpenAI na 0.10.

### 4.12 MLC-LLM
- Compilação de ML para CUDA, ROCm, Metal, Vulkan, WebGPU e mobile, com servidor REST OpenAI e batching ([repo](https://github.com/mlc-ai/mlc-llm)). Exige converter e compilar cada modelo. Sem releases no GitHub; último commit em 2026-08-17. Não compensa o esforço para o Ditto.

---

## 5. Implicações para o Ditto

### 5.1 Mudança necessária no orquestrador (a de maior impacto)
Hoje (`orchestrator.py`, linhas ~134–196): para cada combinação, `for question in questions:` chama `_process_question_with_retry` de forma síncrona. `CustomLLM.generate` usa `ChatOpenAI.invoke` (síncrono).

Proposta mínima, sem async:
- Dentro de cada combinação, submeter as perguntas a um `concurrent.futures.ThreadPoolExecutor(max_workers=N)`. Cada worker executa `_process_question_with_retry(rag, question, ...)`, que é I/O-bound (HTTP), então threads bastam.
- **Toda escrita no banco continua na thread principal.** Monte os `RunResult` à medida que os futures terminam (`as_completed`) ou em ordem (`executor.map`, que preserva a ordem das perguntas). A `session` do SQLAlchemy não é thread-safe.
- A pausa passa a ser verificada antes de submeter cada pergunta (ou com um `threading.Event`). As perguntas já em andamento terminam normalmente.
- **N configurável por LLM** (ex.: campo `concurrency` no `ExperimentConfig` ou em `app_settings.json` por modelo). Um bom ponto de partida é N = número de slots do servidor (`OLLAMA_NUM_PARALLEL`, `-np`, ou 16–32 no vLLM). Para Gemini/API remota, N é limitado pelo rate limit.
- `latency_ms` por pergunta passa a incluir a espera na fila do servidor. Documentar isso na tese, ou medir a latência também com N = 1 como referência de single-stream.
- É preciso garantir que as técnicas RAG, os retrievers e as métricas sejam seguros para uso concorrente (instâncias compartilhadas: `rag`, `retriever`, embedder, cliente Qdrant). O cliente HTTP do Qdrant e os clientes httpx costumam aguentar threads, mas **isso não foi verificado no código do Ditto**. Revisar estado mutável nas classes (caches, contadores de tokens).
- Uma alternativa de maior escopo é paralelizar **entre combinações** que usam o mesmo LLM. Isso complica pausa e progresso; a paralelização dentro da combinação é suficiente.

Ganho esperado: com N concorrentes, o tempo de parede de uma combinação cai quase por um fator igual ao ganho de throughput agregado do servidor (tipicamente vários ×, nunca N×). Técnicas com várias chamadas por pergunta (hyde, crag, agentic) continuam sequenciais dentro da pergunta, mas se sobrepõem entre perguntas.

### 5.2 Como cada servidor se conecta (sem código novo)
Todos entram via `CustomLLM(base_url=..., model=...)`. De dentro do Docker, o host é `host.docker.internal` no Mac. No Linux, o compose precisa de `extra_hosts: host-gateway` ou do IP da bridge (o setup atual já trata do Ollama com `OLLAMA_HOST=0.0.0.0`).

| Servidor | Comando no host (exemplo) | `base_url` | `model` |
|---|---|---|---|
| Ollama | `OLLAMA_NUM_PARALLEL=8 ollama serve` | `http://host.docker.internal:11434/v1` | `qwen2.5:3b-instruct` |
| llama-server | `llama-server -hf Qwen/Qwen3-4B-GGUF:Q4_K_M -np 8 -c 32768 --host 0.0.0.0 --port 8080` | `http://host.docker.internal:8080/v1` | qualquer string (modelo único) |
| vLLM | `vllm serve Qwen/Qwen2.5-3B-Instruct-AWQ --gpu-memory-utilization 0.8 --max-model-len 8192 --host 0.0.0.0 --port 8001` | `http://host.docker.internal:8001/v1` | nome HF |
| SGLang | `python -m sglang.launch_server --model-path Qwen/Qwen2.5-3B-Instruct --host 0.0.0.0 --port 30000` | `http://host.docker.internal:30000/v1` | nome HF |
| mlx-lm | `mlx_lm.server --model mlx-community/Qwen3-4B-4bit --host 0.0.0.0 --port 8082` | `http://host.docker.internal:8082/v1` | nome HF |

(No llama-server, `-c` é o KV total compartilhado pelos slots quando o KV é unificado. Os comandos são exemplos baseados na documentação citada e não foram executados neste estudo.)

Cuidado ao comparar LLMs entre servidores: o mesmo nome de modelo com quantizações diferentes (GGUF Q4_K_M × AWQ × MLX 4-bit) **dá respostas diferentes**. Para a tese, o identificador do LLM no Ditto deve incluir servidor + quantização.

### 5.3 O que mudar no `make llm-setup` (`scripts/llm-setup.sh`)
- **Ollama (padrão)**: exportar `OLLAMA_NUM_PARALLEL` (sugestão: 4 em CPU/4 GB, 8 em GPU de 8–12 GB ou Mac com 16 GB+) e, opcionalmente, `OLLAMA_KV_CACHE_TYPE=q8_0` para caber mais slots. Hoje o script só define `OLLAMA_HOST`. Isso precisa ir para o `nohup ollama serve` e para o override do systemd (`Environment="OLLAMA_NUM_PARALLEL=8"`). No Mac com o app/brew service, a variável tem que estar no ambiente do serviço (`launchctl setenv`) ou o servidor precisa ser iniciado pelo script. Avisar se o modelo escolhido estiver na lista de arquiteturas sem paralelismo (seção 4.1).
- **Backend opcional** (`LLM_BACKEND=vllm|llamacpp|mlx`):
  - `vllm`: só em Linux com `nvidia-smi` e CC ≥ 7.5 (`nvidia-smi --query-gpu=compute_cap`); instalar num venv (`uv pip install vllm`) ou Docker `vllm/vllm-openai`; subir `vllm serve` com `--gpu-memory-utilization` calculado a partir da VRAM livre.
  - `llamacpp`: `brew install llama.cpp` (Mac/Linux) ou imagem `ghcr.io/ggml-org/llama.cpp:server-cuda`; `llama-server -hf ... -np N`.
  - `mlx`: só em Darwin arm64; `pip install mlx-lm` ou `brew install mlx-lm`.
  - Em todos os casos, registrar em `backend/config/app_settings.json` uma entrada `custom` com `base_url` e `model`, como já é feito para o Ollama.

---

## 6. Como medir (protocolo de benchmark no hardware do usuário)

Objetivo: decidir com dados, e não só com esta leitura, qual servidor termina K perguntas mais rápido.

1. **Fixe o modelo e a quantização.** Ex.: Qwen2.5-3B-Instruct em ~4 bits em cada ecossistema (GGUF Q4_K_M para Ollama/llama-server, AWQ para vLLM/SGLang, MLX 4-bit para mlx-lm). Registre as versões dos servidores e o hash do modelo.
2. **Fixe a carga.** Use `database/perguntas.csv` com K = 50–100 perguntas e uma combinação fixa (ex.: chunking X, embedding gemini, `naive`, retriever denso). Grave os prompts finais que o Ditto envia (contexto já recuperado) num JSONL, para que o benchmark isole o LLM do retrieval. Use `temperature=0` e `max_tokens` fixo (ex.: 256).
3. **Aqueça o servidor.** Descarte as 3 primeiras requisições (carga do modelo, compilação de kernels/CUDA graphs).
4. **Varie a concorrência**, C ∈ {1, 2, 4, 8, 16, 32}, sem ultrapassar os slots configurados no servidor. Para cada C, meça:
   - **tempo de parede para terminar as K requisições** (a métrica que importa para o Ditto);
   - throughput de saída agregado (tokens gerados ÷ tempo de parede), usando `usage.completion_tokens` da resposta OpenAI;
   - latência p50/p95 por requisição e TTFT (com `stream=true`);
   - pico de VRAM/RAM (`nvidia-smi --query-gpu=memory.used --format=csv -l 1`; no Mac, Activity Monitor ou `sudo powermetrics`).
5. **Ferramenta.** Um script Python com `openai.AsyncOpenAI(base_url=...)` + `asyncio.Semaphore(C)` já basta e funciona igual para todos os servidores. Como alternativa, `vllm bench serve` (vLLM) e `python -m sglang.bench_serving` (SGLang) aceitam backends OpenAI-compatíveis. Não verifiquei as flags exatas na versão atual.
6. **Qualidade.** Rode as métricas do Ditto sobre as respostas de cada servidor/quantização. Se o servidor mais rápido usar uma quantização que piora as métricas, isso é um confundidor que precisa aparecer na tese.
7. **Teste ponta a ponta.** Depois de implementar a seção 5.1, rode um experimento real do Ditto com N ∈ {1, 4, 8, 16} e compare `finished_at − started_at`.
8. **Repetições.** 3 execuções por ponto; reportar média e desvio.

Critério de decisão: escolher o servidor com o menor tempo de parede no C que cabe na memória, desde que a qualidade fique equivalente.

---

### 6.1 Medição feita nesta máquina (2026-09-23)

Hardware: MacBook com Apple M2 e 8 GB de memória unificada, com o stack Docker do Ditto rodando. Servidor: Ollama 0.31.1 (app). Modelo: `qwen2.5:3b-instruct` (Q4). Comando: `make bench-llm`, com `max_tokens` 128.

| Rodada | Configuração | paralelo=1 | paralelo=2 | paralelo=4 | paralelo=8 |
|---|---|---|---|---|---|
| A (N=8) | `OLLAMA_NUM_PARALLEL` não definido | 22,8 s · 17 tok/s | — | 11,3 s · 35 tok/s (2,0x) | — |
| B (N=8) | `OLLAMA_NUM_PARALLEL=4` | 13,4 s · 29 tok/s | — | 12,1 s · 33 tok/s (1,1x) | 21,8 s · 18 tok/s (0,6x) |
| C (N=16) | `OLLAMA_NUM_PARALLEL=4` | 103,6 s · 8 tok/s | 69,8 s · 12 tok/s (1,5x) | 70,7 s · 12 tok/s (1,5x) | — |

Leitura:
- **Esta máquina não serve para comparar frameworks.** Com o Docker ativo sobravam cerca de 16% de memória livre, e a mesma medição (paralelo=1) variou de 8 a 29 tok/s entre rodadas. Diferenças entre servidores ficariam escondidas nesse ruído. Ela serve como smoke test. O benchmark comparativo (Ollama × llama-server × mlx-lm, ou vLLM no Linux) deve rodar na máquina-alvo, com o stack Docker parado durante a medição.
- Mesmo com o ruído, paralelo 2–4 foi **1,1–2,0x mais rápido** que paralelo 1, e paralelo 8 **piorou** (pressão de memória). Com 8 GB, use 2–4.
- Observação que diverge da seção 1: sem `OLLAMA_NUM_PARALLEL` definido, 4 requisições simultâneas já foram 2x mais rápidas. Isso indica que o Ollama 0.31.1 escolheu sozinho um paralelismo maior que 1 nesta máquina. O padrão "1" citado acima deve ser tratado como **não verificado para todas as versões**. Definir a variável explicitamente (como o `make llm-setup` agora faz) elimina a dúvida.

## 7. Fontes

Oficiais / primárias:
- Ollama FAQ: https://docs.ollama.com/faq (fonte: https://github.com/ollama/ollama/blob/main/docs/faq.mdx)
- Ollama `envconfig/config.go`: https://github.com/ollama/ollama/blob/main/envconfig/config.go
- Ollama `llm/llama_server.go`: https://github.com/ollama/ollama/blob/main/llm/llama_server.go
- Ollama commits de `llama_server.go` (PR #16031): https://github.com/ollama/ollama/commits/main/llm/llama_server.go
- Ollama `server/sched.go`: https://github.com/ollama/ollama/blob/main/server/sched.go
- Ollama releases: https://github.com/ollama/ollama/releases
- Ollama blog MLX: https://ollama.com/blog/mlx · https://ollama.com/blog/mlx-performance
- Ollama library: https://ollama.com/library/qwen2.5 · /qwen3 · /llama3.2 · /gemma3 · /phi4-mini · /smollm2
- llama.cpp README: https://github.com/ggml-org/llama.cpp/blob/master/README.md
- llama.cpp server README: https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md
- llama.cpp `server-context.cpp`: https://github.com/ggml-org/llama.cpp/blob/master/tools/server/server-context.cpp
- llama.cpp Docker: https://github.com/ggml-org/llama.cpp/blob/master/docs/docker.md
- Homebrew formulas: https://formulae.brew.sh/formula/llama.cpp · https://formulae.brew.sh/formula/ollama · https://formulae.brew.sh/formula/mlx-lm
- vLLM instalação GPU: https://docs.vllm.ai/en/latest/getting_started/installation/gpu.html
- vLLM instalação CPU: https://docs.vllm.ai/en/latest/getting_started/installation/cpu.html
- vLLM engine args: https://docs.vllm.ai/en/latest/configuration/engine_args.html
- vLLM `config/cache.py` (v0.30.0): https://raw.githubusercontent.com/vllm-project/vllm/v0.30.0/vllm/config/cache.py
- vLLM APC: https://docs.vllm.ai/en/latest/features/automatic_prefix_caching.html · design: https://docs.vllm.ai/en/latest/design/prefix_caching.html
- vLLM quantização: https://docs.vllm.ai/en/latest/features/quantization/
- vllm-metal: https://github.com/vllm-project/vllm-metal
- SGLang docs: https://docs.sglang.io/ · install: https://docs.sglang.io/docs/get-started/install · Apple Metal: https://docs.sglang.io/docs/hardware-platforms/apple_metal · server args: https://docs.sglang.io/docs/advanced_features/server_arguments
- Artigo SGLang / RadixAttention: https://arxiv.org/abs/2312.07104
- mlx-lm SERVER.md: https://github.com/ml-explore/mlx-lm/blob/main/mlx_lm/SERVER.md · server.py: https://github.com/ml-explore/mlx-lm/blob/main/mlx_lm/server.py
- LM Studio parallel requests: https://lmstudio.ai/docs/app/advanced/parallel-requests · changelog 0.4.2: https://lmstudio.ai/changelog/lmstudio-v0.4.2 · headless: https://lmstudio.ai/docs/app/api/headless
- TGI: https://github.com/huggingface/text-generation-inference
- ExLlamaV3: https://github.com/turboderp-org/exllamav3 · TabbyAPI: https://github.com/theroyallab/tabbyAPI
- TensorRT-LLM: https://nvidia.github.io/TensorRT-LLM/installation/linux.html · https://nvidia.github.io/TensorRT-LLM/reference/support-matrix.html
- LMDeploy: https://github.com/InternLM/lmdeploy
- llamafile: https://github.com/mozilla-ai/llamafile
- MLC-LLM: https://github.com/mlc-ai/mlc-llm
- Modelos HF: https://huggingface.co/Qwen/Qwen3-4B-GGUF · https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-AWQ · https://huggingface.co/bartowski/Llama-3.2-3B-Instruct-GGUF · https://huggingface.co/mlx-community/Qwen3-4B-4bit

Terceiros (só ilustrativos, não usados para conclusões):
- jangwook.net, medição Ollama `num_parallel`: https://jangwook.net/en/blog/en/local-llm-concurrent-requests-num-parallel-experiment/

Não verificado:
- Primeira release do Ollama que trouxe o llama-server como motor único (sabe-se só que a v0.34.3 já o inclui).
- Batching concorrente no motor MLX do Ollama.
- Prefix caching no LM Studio, TabbyAPI e MLC-LLM; API OpenAI no llamafile 0.10.
- Segurança para uso concorrente das classes RAG/retriever/métricas do Ditto.
- Todos os números de throughput: nenhum benchmark foi executado neste estudo (ver seção 6).
