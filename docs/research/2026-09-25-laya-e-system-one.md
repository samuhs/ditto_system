# Laya e a arquitetura "System One": ganho possível para o Ditto?

Pesquisa feita em 2026-09-25. Versões consultadas nesta data: Laya 0.3.20 (PyPI, publicada em 2026-09-24; clone de `main` em `4066d5d`), TypeSafe Jev 1.13 (`jev-1.13.0`, docs revisadas em 2026-09-17). As afirmações sobre o Laya vêm do código e dos documentos do repositório clonado. As afirmações sobre o System One vêm da documentação oficial da TypeSafe (docs.typesafe.ai). O resto vem de artigos no arXiv. Cada afirmação tem link para a sua fonte. Nenhum modelo foi executado nesta máquina.

---

## 1. Resumo e recomendação

**Os dois nomes apontam para a mesma coisa.** "System One" é o nome que a TypeSafe dá à sua classe de modelos de decisão. O Jev é o primeiro deles: recebe um texto ("state") e perguntas tipadas e devolve probabilidades, sem gerar texto ([System One](https://docs.typesafe.ai/concepts/system-one.md)). O Laya é um **clone aberto** dessa ideia. O próprio README se apresenta como "non-autoregressive System 1 decision engine", compara-se ao Jev em quase todas as tabelas e expõe um servidor no mesmo protocolo `POST /v1/systemone` ([README, "Self-Hosting: HTTP Server (Jev-compatible)"](https://github.com/NandhaKishorM/laya#self-hosting-http-server-jev-compatible)). Por isso, a leitura mais provável da pergunta é "Laya ou o Jev da TypeSafe". A leitura kahnemaniana genérica (System 1 × System 2 em RAG) também existe na literatura e está coberta na seção 4, mas o Ditto já tem os dois lados dela.

**O que um modelo System One faria no Ditto:** trocar chamadas de LLM que servem **só para decidir** (reordenar passagens, dizer se o contexto basta, dizer se a resposta está apoiada no contexto) por uma passada de um encoder que devolve uma probabilidade. O Ditto tem três pontos assim (seção 5).

| Item | Veredito | Por quê, em uma linha |
|---|---|---|
| **Laya como métrica de avaliação** (`faithfulness`/relevância via `noul`) | **Não adotar** | É zero-shot fraco (abaixo do baseline de classe majoritária no benchmark do próprio autor), falha em negação e é inglês-cêntrico. Para PT-BR, o NLI mDeBERTa já recomendado em [2026-09-24-avaliacao-rag-sem-llm.md](2026-09-24-avaliacao-rag-sem-llm.md) tem mais fundamento. |
| **Laya como técnica RAG nova** (rerank/filtro de passagens sem LLM) | **Experimento opcional, baixa prioridade** | Encaixa no registry sem mudar interfaces e cabe no perfil `low`. Porém não há medição de reranking publicada para o Laya, e um cross-encoder dedicado (`bge-reranker-v2-m3`) é a linha de base mais defensável na tese. Se entrar, deve ser como uma variante a mais na grade, ao lado do cross-encoder. |
| **TypeSafe Jev (API)** | **Pular** | API fechada, paga, com rede e dados enviados a terceiros. O alias muda de versão, os limites mudam "sem aviso" e o suporte fora do inglês é declarado inferior. Isso contradiz a reprodutibilidade de um experimento de doutorado. |
| **Enquadramento System 1 / System 2** (Kahneman, survey de RAG) | **Usar só como vocabulário na tese** | O Ditto já compara pipelines predefinidos (naive, rerank, hyde, crag) com o `agentic`, que é exatamente o eixo da taxonomia. Não há código a ganhar. |

**Ganho esperado: marginal.** O único cenário com ganho concreto é reduzir chamadas de LLM nas técnicas `rerank` e `crag` (seção 5.2). Mesmo assim, o ganho depende de uma validação em PT-BR que ninguém publicou.

---

## 2. O que o Laya realmente é (lido no código)

**Arquitetura.** É um encoder bidirecional (ModernBERT ou mmBERT) com uma "cabeça de decisão": 2 camadas `TransformerEncoder`, um embedding de tipo de pergunta e um `scorer` que dá um logit por opção (`laya/common.py:149-172`, classe `DecisionModel`). A entrada é uma sequência única, `[CLS] <tipo> instruções [SEP] [MASK] opção0 [MASK] opção1 ... [SEP] state [SEP]` (`laya/common.py:94-108`). Cada opção é truncada em 48 tokens (`common.py:116-124`). Na prática, é um **cross-encoder de múltipla escolha**. Não é um LLM e não gera texto.

**Três primitivos** ([README, "Decision Primitives"](https://github.com/NandhaKishorM/laya#decision-primitives)):
- `choice`: uma opção de um conjunto, com distribuição;
- `score`: posição esperada numa escala ordinal;
- `noul`: P(verdadeiro).

**Treino ("RLCD").** Recompensa por regras de pontuação estritamente próprias (log score + spherical + RPS), em `proper_reward` (`laya/common.py:278-297`), com gradiente de política "GRPO-style" ([README, "Fine-Tuning"](https://github.com/NandhaKishorM/laya#fine-tuning)). **Não há artigo.** Nem o Laya nem a TypeSafe citam paper para o RLCD. A única descrição da TypeSafe é conceitual ([AI primer](https://docs.typesafe.ai/introduction/machine-learning-primer.md)). O Laya diz que chegou ao mesmo método de forma independente (post no [dev.to](https://dev.to/nandakishor_m_6cc0adfde9f/i-built-non-autoregressive-decision-models-a-year-ago-then-a-frontier-lab-called-it-a-18me), não lido a fundo, porque não é fonte primária de resultado).

**Checkpoints** ([README, tabela de checkpoints](https://github.com/NandhaKishorM/laya/blob/main/README.md), linhas 111-119):

| checkpoint | encoder | params | contexto |
|---|---|---|---|
| `laya` | ModernBERT-large | 421M | 512 (~320 tokens para o state) |
| `laya-multilingual` | mmBERT-base | 322M | 1024 (até 8.192) |
| `laya-typed-decisions` | ModernBERT-large | 421M | 1024 |

O `Router` detecta script e idioma e manda texto não inglês para o `laya-multilingual`. Texto latino curto (o README usa "Quero cancelar" e "Esqueci minha senha" como exemplo) cai no inglês, a menos que se configure `Router(default="multilingual")` ([README](https://github.com/NandhaKishorM/laya#quickstart-route-mode-recommended)). Para o Ditto, com dados em PT-BR, o certo seria fixar `model="multilingual"`.

**Maturidade.**
- Repositório criado em 2026-09-18 (`gh repo view`), ou seja, **7 dias** antes desta pesquisa.
- 413 commits, 28 releases no PyPI entre 0.1.0 (2026-09-18) e 0.3.20 (2026-09-24), cerca de 24 mil estrelas.
- Classificador PyPI "Development Status :: 4 - Beta" (`pyproject.toml`).

É um projeto em fluxo intenso, com muitos PRs de terceiros mesclados no mesmo dia. Para a tese, isso pede **fixar a revisão** dos pesos (o próprio Laya suporta, `laya/revisions.py`).

**Licença.** Apache-2.0 no código (`LICENSE`, `pyproject.toml`) e nos pesos (`license: apache-2.0` na [model card](https://huggingface.co/convaiinnovations/laya)).

**Dependências.** `torch>=2.0`, `transformers>=4.48`, `safetensors`, `huggingface_hub`, `numpy` (`pyproject.toml`). O README exige Python ≥ 3.10 e diz que o piso vem de `transformers` 5.x e `torch` 2.14 ([README, "Installation details"](https://github.com/NandhaKishorM/laya#installation-details)). Isso é o mesmo que o grupo opcional `local` do Ditto já puxa via `sentence-transformers` (`backend/pyproject.toml:33-35`). **Não verifiquei** se as versões fixadas no Ditto são compatíveis com a exigência de `transformers` 5.x.

**Apple Silicon.** Roda em MPS pelo PyTorch comum: a seleção automática de device escolhe `mps` quando disponível (`laya/agent.py:346-358`), e o autocast em MPS só liga a partir de N linhas (`agent.py:198`, `agent.py:680-690`). O caminho rápido TileLang é só CUDA e cai para o forward normal em CPU/MPS ([README, "GPU Fast Path"](https://github.com/NandhaKishorM/laya#gpu-fast-path-tilelang)). O README cita um tempo de ~1,7 s para 4.000 tokens "on an Apple GPU", sem dizer qual chip ([README, Quickstart](https://github.com/NandhaKishorM/laya#quickstart)). Há um runtime MLX/ANE de terceiros ([tc3oliver/laya-apple](https://github.com/tc3oliver/laya-apple), 10 estrelas, não avaliado).

**Custo em CPU** (medido pelo autor, EPYC de 4 núcleos, fp32; [BENCHMARKS.md, "Server CPU"](https://github.com/NandhaKishorM/laya/blob/main/BENCHMARKS.md)): `multilingual` leva **193 ms por pergunta** (1.842 ms para 10), e `english` leva 580 ms. "Batching questions saves little on CPU." O pico de RSS foi de 9,3 GiB, mas com até **cinco** checkpoints carregados. Um checkpoint `multilingual` de 322M params em fp32 deve ocupar ~1,3 GB (estimativa minha, não medida), comparável ao mDeBERTa-base do NLI.

### 2.1 O que os próprios números do Laya dizem sobre qualidade

O README é honesto nas limitações. Os pontos que pesam para o Ditto:

1. **Zero-shot é fraco.** No benchmark typed-decisions, os checkpoints base marcam 0,362 (`laya`) e 0,352 (`laya-multilingual`). Isso fica **abaixo do baseline de classe majoritária (0,461)** e pouco acima do aleatório (0,318). O 0,766 que o projeto divulga vem do checkpoint **fine-tunado no split de treino do próprio benchmark**. Nas palavras do autor: "Laya is a fast base to specialise, not a zero-shot decision engine" ([README, "Honest limits"](https://github.com/NandhaKishorM/laya#honest-limits)).
2. **Negação.** Em cinco exemplos de cancelamento, o `laya` escolheu `cancel_account` nos quatro pedidos **negados**, e o multilingual errou em dois, um deles com probabilidade 0,9998 ([issue #377](https://github.com/NandhaKishorM/laya/issues/377), citada em "Honest limits"). Para avaliar fidelidade de respostas, onde "não abre às segundas" × "abre às segundas" é o erro típico, isso é grave.
3. **O `noul` segue os rótulos, não o texto.** No checkpoint inglês, o par `false:`/`true:` pode dominar a resposta ([issue #156](https://github.com/NandhaKishorM/laya/issues/156)). A contorna proposta é trocar os rótulos, sem garantia.
4. **Português.** No MASSIVE (intenção, 20 opções, aleatório = 0,05), `pt` marca **0,470** (`laya`) e **0,450** (`laya-multilingual`), contra 0,783 e 0,657 em inglês ([BENCHMARKS.md, tabela de 51 línguas](https://github.com/NandhaKishorM/laya/blob/main/BENCHMARKS.md#all-51-massive-languages--intent-20-options-random--0050)). O XNLI multilíngue (0,731 em 14 línguas) **não inclui português**, porque o XNLI não tem PT. Não existe medição de NLI/fidelidade em PT.
5. **Calibração.** Os dois checkpoints saem **super-confiantes**, e o `laya-multilingual` "has no fitted temperatures at all" ([README, "Calibration"](https://github.com/NandhaKishorM/laya#calibration)). A vantagem de "probabilidades calibradas" só aparece depois de ajustar temperatura em dados rotulados do domínio.
6. **Documentos longos.** O `predict_long` janela o texto, mas a probabilidade devolvida é da janela decisiva, "not a calibrated number for the whole document", e o `noul` sobe com o número de janelas mesmo sem sinal ([README, "Long documents: predict_long"](https://github.com/NandhaKishorM/laya#long-documents-predict_long)).

---

## 3. O "System One" da TypeSafe (Jev)

**Definição oficial.** "System One models are a class of AI models built to make fast, structured decisions that software can use directly. A System One model evaluates a state and returns typed answers and probabilities." O nome vem de Kahneman: "System 1 thinking is fast and intuitive. System 2 is slower and more deliberate" ([System One](https://docs.typesafe.ai/concepts/system-one.md)). Os primitivos são os mesmos do Laya (`choice`, `score`, `noul`).

**Condições de uso** ([Models](https://docs.typesafe.ai/models.md)):
- **Só API** (`POST https://api.typesafe.ai/v1/systemone`, [API](https://docs.typesafe.ai/api.md)). Pesos fechados, e "Jev is not fine-tuned or LoRA-adapted with customer data".
- **Preço**: US$ 0,042 por milhão de tokens de entrada; tokens de saída são grátis.
- **Limites** de 250k tokens/s e 1.200 req/min, com o aviso de que "limits above can change without notice".
- **Contexto**: 64k tokens por requisição.
- **Idioma**: "English is the primary training language and where accuracy is currently best. Other languages [...] are handled but not equally well."
- **Versões**: o alias `jev-latest` muda quando sai versão nova. A doc recomenda fixar `jev-1.13.0` para quem calibrou limiares.

**Limitações publicadas pela própria TypeSafe** ([Jev 1.13 jaggedness](https://docs.typesafe.ai/model-jaggedness/jev-1.13.md)): leitura literal (negações e escopo "read at face value"), aritmética, datas, indireção e "Large state full of irrelevant detail": "Accuracy falls as the state grows with content unrelated to the decision". Para esse último caso, a doc remete ao cookbook de RAG.

**Receitas diretamente sobre RAG.** São as mais próximas do Ditto:
- **Rerank** ([cookbook](https://docs.typesafe.ai/cookbooks/rerank_typesafe.md)): shortlist BM25 de 30 passagens em 40 consultas jurídicas (CLERC). Uma pergunta Jev por par consulta–candidato leva o top-1 de **5% → 18%** e o top-10 de **38% → 62%**. A comparação é **só contra BM25**, sem cross-encoder nem reranker por LLM.
- **Classificar passagens de RAG** ([cookbook](https://docs.typesafe.ai/cookbooks/classifying_rag_passages.md)): quatro `Noul` por passagem (relevante? contém evidência usável? contradiz a premissa da pergunta? tenta instruir o modelo?), com limiares no código que decidem entre evidência, conflito e descarte. O cookbook mostra o pipeline em exemplos, **sem métrica agregada** contra uma linha de base.
- **Checagem de citação** ([cookbook](https://docs.typesafe.ai/cookbooks/citation_check.md)): classifica citações (apoiada/fabricada etc.) com confiança para revisão humana.

**Comparação Laya × Jev.** Todos os números do Jev no README do Laya são "third-party published, never measured here (no TypeSafe API access)" ([README, "Laya (with routing) vs Jev"](https://github.com/NandhaKishorM/laya#laya-with-routing-vs-jev)). Nesses números, o Laya ganha em AG News e DAIR Emotion, perde feio em Banking77 (0,425 × 0,870, com mais de 20 opções) e empata aproximadamente no typed-decisions só **depois de fine-tuning**. **Não verifiquei** nenhum número do Jev de forma independente.

---

## 4. A leitura kahnemaniana: System 1 × System 2 em RAG

A survey de Liang et al., *Reasoning RAG via System 1 or System 2* ([arXiv 2506.10408](https://arxiv.org/abs/2506.10408), jun/2025), alinha explicitamente na Tabela 1 **"System 1 – Predefined Reasoning: structured, modular, rule-based execution"** e **"System 2 – Agentic Reasoning: autonomous, adaptive, model-driven decision-making"** ([HTML v1](https://arxiv.org/html/2506.10408v1)).

Pela taxonomia, o Ditto já tem os dois sistemas no mesmo registry:
- **System 1:** `naive`, `hyde`, `rerank`, `compression`, `crag` (pipelines fixos, `backend/app/core/rag/*.py`).
- **System 2:** `agentic` ("a bounded loop where the LLM decides to search or answer", `backend/app/core/rag/agentic.py:1`).

O ganho aqui é **de redação da tese**: usar a taxonomia para agrupar as técnicas nos resultados. Não há componente a implementar. Note que o "System 1" da survey (pipeline fixo com LLM) **não é** o "System One" da TypeSafe/Laya (modelo de decisão sem geração). É bom não misturar os dois termos no texto.

---

## 5. Encaixe no Ditto

### 5.1 Onde uma decisão tipada substituiria uma chamada de LLM

Todas as técnicas e métricas vivem atrás de interface + registry (`backend/app/core/registry.py:7-32`). O orquestrador instancia a técnica RAG com `retriever` e `llm` (mais `prompts` quando a técnica tem specs) em `backend/app/experiments/orchestrator.py:333-341`.

| Ponto do Ditto | Hoje | Com um modelo System One | Interface / arquivo |
|---|---|---|---|
| Reordenar passagens | `RerankRAG` pede ao LLM uma permutação em texto livre e faz parse com regex (`backend/app/core/rag/rerank.py:10-24`, `44-55`) | Um `noul` "Esta passagem responde à pergunta?" por passagem; ordenar por P(sim) | `RAG` + `rag_registry` (`backend/app/core/rag/base.py:21-29`) |
| Avaliar se o contexto basta (CRAG) | O LLM gera um veredito; o código testa `startswith("INSUFICIENTE")` (`backend/app/core/rag/crag.py:31-38`) | Um `noul` "O contexto contém a informação para responder?" com limiar | idem |
| Filtrar passagens antes da resposta | Não existe | A receita "classifying RAG passages": manter só P(relevante) ≥ limiar | idem (técnica nova) ou um `Retriever` decorador (`backend/app/core/retrieval/base.py:8-16`) |
| Fidelidade da resposta | `Faithfulness` = cosseno(resposta, contextos) (`backend/app/core/evaluation/embedding_metrics.py:29-38`) | Um `noul` "A resposta é sustentada pelo contexto?" | `Evaluator` + `evaluation_registry` (`backend/app/core/evaluation/base.py:18-28`) |
| Relevância do contexto | `ContextPrecision` = média de cossenos (`embedding_metrics.py:41-53`) | Média de P(relevante) por chunk | idem |

### 5.2 Ganho real, item por item

**(a) Rerank/filtro sem LLM: é onde há ganho plausível.**
- *Custo de execução:* troca uma geração do LLM local (permutação em texto, sujeita a parse) por N passadas de encoder. Em CPU, com o `multilingual`, isso daria ~0,2 s por passagem pelo número do autor. Com `k` passagens, o custo é de ~0,2·k s, contra uma geração de centenas de tokens num LLM de 1,7–7B. A saída é determinística e não depende do parse `_parse_ranking`.
- *Validade na tese:* um reranker precisa ser comparado com um reranker dedicado. O `BAAI/bge-reranker-v2-m3` (multilíngue, Apache-2.0, ~568M) já foi levantado na nota de avaliação ([model card](https://huggingface.co/BAAI/bge-reranker-v2-m3)) e foi **treinado para relevância consulta↔passagem**. O Laya não foi treinado para isso, e **não há número de reranking do Laya** publicado. O único número de reranking de um System One é o do Jev contra BM25, em inglês jurídico.
- *Conclusão:* se o objetivo é "rerank sem LLM", o cross-encoder é a primeira escolha. O Laya só vale como **segunda variante**, para testar a hipótese "decisão tipada genérica ≈ reranker dedicado?". Isso é uma pergunta de pesquisa legítima, mas periférica ao foco do Ditto.

**(b) CRAG com juiz tipado.** O ganho é pequeno: o CRAG faz uma chamada de julgamento por pergunta (`max_corrections=1` por padrão, `crag.py:18`), e trocá-la por um encoder economiza pouco. O que se ganha é um limiar ajustável e uma probabilidade em vez de uma string. O risco é o viés de negação (item 2 da seção 2.1). Só vale se (a) for implementado, reaproveitando o mesmo modelo.

**(c) Métrica de fidelidade: não recomendado.** A nota [2026-09-24-avaliacao-rag-sem-llm.md](2026-09-24-avaliacao-rag-sem-llm.md) (seção 3.3) já escolheu NLI com `mDeBERTa-v3-base-xnli-multilingual-nli-2mil7`, que tem **PT no treino** e agregação estilo SummaC com base em artigo. O Laya perde em todos os critérios que importam para uma métrica de tese:
- não há medição em NLI/fidelidade em PT;
- a qualidade zero-shot fica abaixo da classe majoritária no benchmark do autor;
- a falha em negação está documentada;
- a calibração do multilingual não existe de fábrica;
- a janela de state é de ~768 tokens por padrão, e o `predict_long` não é calibrado.

Uma métrica cuja validade depende de fine-tuning no domínio precisaria de dados rotulados que o Ditto não tem (15 perguntas em `database/perguntas.csv`).

**(d) Jev via API: pular.** Mesmo que funcionasse em PT, quebra quatro premissas do Ditto:
1. os testes e experimentos não dependem de rede de terceiros para decisões de pipeline (a regra de testes do `CLAUDE.md` já exige fakes);
2. o alias muda de versão e os limites mudam sem aviso, o que atrapalha a reprodutibilidade;
3. o documento de teste e as perguntas saem da máquina;
4. o próprio fornecedor declara o inglês como idioma principal.

O custo em dinheiro seria desprezível (US$ 0,042/Mtok). O problema não é preço.

### 5.3 Custo de adotar o Laya, se for o caso

- **Dependência:** `laya` no grupo opcional `local` do `backend/pyproject.toml`, junto do `sentence-transformers`. Checar a compatibilidade de `transformers` 5.x.
- **Memória:** um checkpoint (`multilingual`, 322M) de cada vez. Hoje o `ModelManager` só gerencia `Embedder` (`backend/app/core/memory/manager.py:58`). É o mesmo obstáculo do BERTScore/NLI da nota anterior (seção 5.1, item 3, opção (a)): generalizar o manager para "modelos locais" com factory + `is_local`. Se o Laya rodar **dentro de uma técnica RAG** (etapa de geração), ele disputa memória com o LLM local. A política atual manda embedders para CPU quando há LLM local (`backend/app/core/memory/device.py:8-19`), e o Laya teria de seguir a mesma regra. No perfil `low` (≤ 8 GB) isso cabe só em CPU, a ~0,2 s por decisão.
- **Rede:** só o download dos pesos na primeira vez (Hugging Face). É preciso fixar a revisão com `laya/revisions.py` e embutir os pesos na imagem Docker, como já é feito com `e5`/`paraphrase`.
- **Testes:** injetar um fake do agente (a interface `predict(state, questions) -> {"answers": ...}` é simples), sem baixar pesos, como exige o `CLAUDE.md`.
- **Licença:** Apache-2.0 no código e nos pesos. Sem impedimento.

---

## 6. Recomendação final

1. **TypeSafe Jev (System One via API): pular.** Pelos motivos da seção 5.2(d).
2. **Laya como métrica de avaliação: pular.** Seguir com o plano de NLI mDeBERTa + métricas léxicas da nota de 2026-09-24.
3. **Laya como técnica RAG (`rerank` sem LLM): experimento opcional, depois do cross-encoder.** A ordem sugerida é:
   - (i) implementar `rerank_ce` com `bge-reranker-v2-m3` como nova técnica em `backend/app/core/rag/` (ou como `Retriever` decorador);
   - (ii) só então, se houver interesse em comparar, `rerank_laya` com o mesmo contrato;
   - (iii) medir com as métricas de recuperação com gold propostas na nota anterior (hit@k/MRR por texto).

   Sem o gold de evidência, qualquer comparação de rerankers no Ditto é por proxy de cosseno e não sustenta conclusão.
4. **System 1 / System 2 (Kahneman): usar como taxonomia na escrita**, citando [arXiv 2506.10408](https://arxiv.org/abs/2506.10408), e separar o termo do "System One" comercial.

---

## 7. Questões em aberto / não verificado

1. **Qualidade do Laya em PT-BR para relevância/fidelidade**: não há nenhum número publicado. Só dá para saber medindo nas 15 perguntas com anotação manual.
2. **Compatibilidade de versões**: `transformers` 5.x / `torch` 2.14 (exigidos pelo Laya segundo o README) × as versões fixadas no venv/imagem do Ditto. Não conferido.
3. **Latência em Apple Silicon (MPS) no hardware do usuário**: o autor só dá "~1,7 s para 4.000 tokens on an Apple GPU", sem chip. Não medido aqui.
4. **Números do Jev**: todos vêm de terceiros ou da própria TypeSafe. Não reproduzidos.
5. **RLCD**: sem artigo revisado por pares. A descrição é só a da doc e a do código (`proper_reward`).
6. **laya-apple (MLX/ANE)**: é de terceiros, tem 10 estrelas e não foi avaliado.

---

## 8. Fontes

- Laya, repositório (código, README, BENCHMARKS.md, pyproject.toml): https://github.com/NandhaKishorM/laya (clonado em `4066d5d`, 2026-09-25)
- Laya, PyPI: https://pypi.org/project/laya/
- Laya, pesos: https://huggingface.co/convaiinnovations/laya · https://huggingface.co/convaiinnovations/laya-multilingual
- Laya, issues citadas: https://github.com/NandhaKishorM/laya/issues/377 · https://github.com/NandhaKishorM/laya/issues/156
- TypeSafe, System One: https://docs.typesafe.ai/concepts/system-one.md
- TypeSafe, Models (preço, limites, idiomas, versões): https://docs.typesafe.ai/models.md
- TypeSafe, API: https://docs.typesafe.ai/api.md
- TypeSafe, AI primer (RLCD): https://docs.typesafe.ai/introduction/machine-learning-primer.md
- TypeSafe, Jev 1.13 jaggedness: https://docs.typesafe.ai/model-jaggedness/jev-1.13.md
- TypeSafe, cookbook rerank: https://docs.typesafe.ai/cookbooks/rerank_typesafe.md
- TypeSafe, cookbook classifying RAG passages: https://docs.typesafe.ai/cookbooks/classifying_rag_passages.md
- TypeSafe, cookbook citation check: https://docs.typesafe.ai/cookbooks/citation_check.md
- Liang et al., *Reasoning RAG via System 1 or System 2* (2025): https://arxiv.org/abs/2506.10408
- BAAI bge-reranker-v2-m3: https://huggingface.co/BAAI/bge-reranker-v2-m3
- Nota anterior do Ditto: [2026-09-24-avaliacao-rag-sem-llm.md](2026-09-24-avaliacao-rag-sem-llm.md)
