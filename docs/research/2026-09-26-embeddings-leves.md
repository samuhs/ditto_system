# Embeddings leves e modernos para o Ditto: qual usar em busca semântica em português, rodando em CPU e GPU locais

Pesquisa feita em 2026-09-26. As afirmações sobre modelos vêm das model cards no Hugging Face, dos relatórios técnicos no arXiv (EmbeddingGemma, MMTEB, Arctic Embed 2.0, Nomic Embed v2, Granite R2) e de dois benchmarks independentes de português publicados em julho de 2026: **MTEB-BR** ([Stekel, arXiv 2607.04581](https://arxiv.org/abs/2607.04581), 22 tarefas nativas em PT-BR, 93 modelos, [leaderboard](https://huggingface.co/spaces/mteb-br/leaderboard)) e **MTEB-PT** ([Okamura, Alcoforado & Costa (USP), arXiv 2607.04071](https://arxiv.org/abs/2607.04071), 14 conjuntos, 20 modelos). Os dois são preprints, sem revisão por pares até esta data. Os números por tarefa do MTEB-BR para modelos fora do top 30 do artigo foram extraídos dos dados embutidos no próprio leaderboard (o artigo diz que "the complete 93-model matrix is on the interactive leaderboard"); a média de recuperação de 6 tarefas que aparece aqui foi calculada por mim a partir desses números. Também rodei um micro-benchmark local (M2, 8 GB) na FAQ do projeto; ele é pequeno e está descrito como tal na seção 5.

Cada afirmação traz um **nível de evidência**:

- **independente**: benchmark de terceiros, com protocolo publicado, que avaliou o modelo sem participação do fornecedor;
- **fornecedor**: número publicado por quem treinou o modelo (model card, relatório técnico, blog);
- **medição local**: rodei aqui, em hardware e dados do Ditto, com amostra pequena;
- **conjectura**: raciocínio meu, sem fonte direta.

---

## 1. Resumo e recomendação

**Resposta curta.** Para recuperação em português com até ~600M de parâmetros, o modelo com a melhor evidência independente hoje é o **`google/embeddinggemma-300m`** (308M, 768 dims com Matryoshka, 2048 tokens, carrega no `sentence-transformers` sem `trust_remote_code`). No MTEB-BR ele é o melhor modelo aberto abaixo de 1B parâmetros: 13º de 93 na média geral (0,649) e média de recuperação de 0,654, acima de `bge-m3`, `snowflake-arctic-embed-l-v2.0`, `Qwen3-Embedding-0.6B` e `multilingual-e5-large-instruct`, todos com o dobro do tamanho. O custo prático é que o repositório oficial é **gated** (exige token do Hugging Face e aceite dos Gemma Terms of Use), o que afeta `make setup` e o build Docker.

Na medição local (M2, 8 GB, FAQ do projeto), o EmbeddingGemma também foi o melhor (R@1 0,90 contra 0,82 do `e5`) e roda bem em CPU: 33 ms por consulta e ~2,2 s para indexar 50 trechos, cerca de 4× o custo do `e5`. É aceitável para o perfil `low`.

A opção mais leve com ganho de qualidade sobre o `e5` é o **`ibm-granite/granite-embedding-97m-multilingual-r2`** (97M, 384 dims, Apache 2.0, sem prompts). No MTEB-BR ele supera o `multilingual-e5-small` em recuperação (0,557 contra 0,507). O problema é que, com PyTorch em CPU, ele foi 7× mais lento que o `e5` na medição local; em MPS foi rápido. Ele só vale para o perfil `low` se a variante ONNX/OpenVINO que a IBM publica resolver isso, e eu não medi essa variante.

**Tabela comparativa** (candidatos com PT explícito ou avaliados em PT; "Recup." = média de recuperação):

| Modelo | Params | Dim (MRL) | Contexto | Licença | Prompts | `trust_remote_code` | MMTEB v2 Recup. (18 tarefas) | MTEB-BR Recup. (6 tarefas, calc.) | MTEB-BR geral (22) | MTEB-PT Recup. (3) |
|---|---|---|---|---|---|---|---|---|---|---|
| **embeddinggemma-300m** | 308M | 768 (512/256/128) | 2048 | Gemma ToU (gated) | sim, obrigatórios | não | 62,5 [G6] | **0,654** | **0,649** (13º/93) | não avaliado |
| **granite-embedding-97m-multilingual-r2** | 97M | 384 (MRL) | 32k | Apache 2.0 | não | não | 60,3 (fornecedor) | 0,557 | 0,560 | não avaliado |
| granite-embedding-311m-multilingual-r2 | 311M | 768 (512…128) | 32k | Apache 2.0 | não | não | 65,2 (fornecedor) | 0,607 | 0,590 | não avaliado |
| Qwen3-Embedding-0.6B | 596M | 1024 (32–1024) | 32k | Apache 2.0 | sim, só na consulta | não | 64,6 [G5, Q] | 0,603 | 0,623 | **78,9** |
| bge-m3 | 568M | 1024 | 8192 | MIT | não | não | 54,6 [G5] | 0,635 | 0,616 | não avaliado |
| snowflake-arctic-embed-l-v2.0 | 568M | 1024 (256) | 8192 | Apache 2.0 | `query: ` na consulta | não | n/d | 0,636 | 0,620 | não avaliado |
| multilingual-e5-large-instruct | 560M | 1024 | 512 | MIT | `Instruct:` na consulta | não | 57,1 [G5] | 0,599 | 0,641 | 70,1 |
| gte-multilingual-base | 305M | 768 (128–768) | 8192 | Apache 2.0 | não | **sim** | 56,5 [G6] | não avaliado | não avaliado | 76,9 |
| snowflake-arctic-embed-m-v2.0 | 305M | 768 (256) | 8192 | Apache 2.0 | `query: ` na consulta | **sim** | 54,8 [G6] | não avaliado | não avaliado | não avaliado |
| harrier-oss-v1-270m | 268M | 640 | 32k | MIT | sim, só na consulta | não | n/d (MTEB v2 médio 66,5, fornecedor) | 0,571 | 0,604 | não avaliado |
| **multilingual-e5-small** (atual `e5`) | 118M | 384 | 512 | MIT | `query: `/`passage: ` | não | 49,3 [G6] | 0,507 | 0,561 | 70,2 |
| paraphrase-multilingual-MiniLM-L12-v2 (atual `paraphrase`) | 118M | 384 | 128 | Apache 2.0 | não | não | n/d | 0,023 (suspeito, ver 3.3) | 0,248 (suspeito) | não avaliado |

[G5]/[G6]: tabelas 5 e 6 do [relatório do EmbeddingGemma](https://arxiv.org/abs/2509.20354), que reproduzem números do leaderboard MMTEB (a tabela 6 ordena por Borda contra todos os modelos). [Q]: a [model card do Qwen3-Embedding-0.6B](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B) dá 64,64. "n/d": não encontrei número em fonte primária. As colunas MMTEB e MTEB-BR/PT não são comparáveis entre si (métricas, tarefas e truncamento diferentes).

**Recomendação para o registry do Ditto** (detalhes e código na seção 6):

| # | Nome no registry (sugestão) | Modelo | Perfil | Por quê | Evidência |
|---|---|---|---|---|---|
| 1 | `gemma` | `google/embeddinggemma-300m` | `standard` e `low` | Melhor recuperação em PT entre os abertos ≤ 1B no único benchmark nativo grande; melhor também na FAQ do projeto; 33 ms/consulta em CPU | **independente** (MTEB-BR) + fornecedor (MMTEB) + medição local |
| 2 | `granite-small` | `ibm-granite/granite-embedding-97m-multilingual-r2` | `standard` (GPU livre); `low` só com backend ONNX/OpenVINO, depois de medir | Mesmo porte do `e5` atual, melhor em recuperação em PT, sem prompts, Apache 2.0; lento em CPU com PyTorch | **independente** (MTEB-BR) + fornecedor + medição local |
| 3 | `qwen3` (opcional) | `Qwen/Qwen3-Embedding-0.6B` | só `standard` | Arquitetura diferente (decoder com instrução), 1º em recuperação no MTEB-PT entre os abertos avaliados; serve como "teto" do eixo de embedding | **independente** (MTEB-PT, MTEB-BR), com resultados que não concordam entre si |

Manter o `e5` como linha de base (é o modelo mais citado e já está no projeto). O `paraphrase` não foi treinado para recuperação e trunca em 128 tokens; faz sentido mantê-lo só como embedder de avaliação (`DEFAULT_EVAL_EMBEDDING`, em `backend/app/core/config/runtime.py:12`), não como eixo de retrieval. **conjectura**.

---

## 2. O que o Ditto já tem e o que a escolha precisa respeitar

- **Interface.** `Embedder` (`backend/app/core/embedding/base.py`) exige `embed_documents`, `embed_query`, `dimension` e aceita `embed_queries`. `HuggingFaceEmbedder` (`backend/app/core/embedding/huggingface.py`) já separa `document_prefix` e `query_prefix`; o `E5Embedder` usa `"passage: "`/`"query: "`. Qualquer modelo com prompts fixos entra só com uma subclasse de 5 linhas.
- **Qdrant.** Cada combinação base × chunking × embedding tem uma coleção própria (`collection_name` em `backend/app/core/vectorstore/qdrant.py:30`), criada com `embedder.dimension` (`backend/app/ingestion/pipeline.py:42`). Dimensões diferentes (384, 768, 1024) não conflitam. Se usarmos truncamento Matryoshka, cada dimensão precisa de um nome de registry próprio (por exemplo `gemma-256`), senão duas dimensões iriam para a mesma coleção.
- **Memória e device.** O perfil `low` fixa `max_local_models=1` e `embedding_device="cpu"`; o `standard` permite GPU, mas `resolve_embedding_device` devolve CPU sempre que um LLM local pode estar residente (`backend/app/core/memory/profile.py`, `device.py`). Na prática, com MLX ou Ollama rodando, **o embedder roda em CPU**. A latência em CPU é o critério que manda; MPS/CUDA é bônus.
- **Dependências.** O extra `local` pede `sentence-transformers>=2.7` (`backend/pyproject.toml`). O venv de dev tem `sentence-transformers 6.1.0`, `transformers 5.17.0` e `torch 2.14.0`, o que basta para todos os modelos recomendados. O limite inferior do `pyproject.toml` não basta: EmbeddingGemma pede `sentence-transformers>=5.0` e `transformers>=4.56` ([blog do HF](https://huggingface.co/blog/embeddinggemma)); Qwen3 pede `transformers>=4.51` ([model card](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B)).
- **Dados.** PT-BR, trechos curtos a médios (a FAQ tem seções de 274 a 990 caracteres; na medição local os 50 trechos somam cerca de 4.800 tokens, média de ~95 tokens). Nenhum dos candidatos tem problema de contexto para esse tamanho; a vantagem de 8k/32k tokens dos modelos novos não pesa aqui. **medição local**.

---

## 3. Evidência de qualidade em português

### 3.1 MTEB-BR (independente, nativo em PT-BR)

O [MTEB-BR](https://arxiv.org/abs/2607.04581) usa só dados criados em português (exclui tradução). Tem 6 tarefas de recuperação (MedPTRetrieval, FaQuAD-IR, Quati, FaqBacenRetrieval, JurisTCU, BR-TaxQA-R) e 2 de reranking, com nDCG@10. Protocolo: A100, `max_seq_length` fixo em 512, precisão nativa, pooling e padding da model card, e prompt padrão do `mteb` 2.12 para modelos com instrução ("we add no custom instructions") (Apêndice A).

Números por tarefa relevantes para o Ditto, tirados do leaderboard. FaqBacen é o caso mais parecido com a FAQ do projeto (FAQ institucional em PT):

| Modelo | FaQuAD-IR | FaqBacen | Quati | MedPT | JurisTCU | BR-TaxQA | Média 6 | Assin2 STS |
|---|---|---|---|---|---|---|---|---|
| embeddinggemma-300m | 0,846 | 0,695 | 0,607 | 0,777 | 0,621 | 0,375 | **0,654** | 0,799 |
| snowflake-arctic-embed-l-v2.0 | 0,826 | 0,699 | 0,585 | 0,767 | 0,662 | 0,278 | 0,636 | 0,728 |
| bge-m3 | 0,829 | 0,672 | 0,594 | 0,747 | 0,591 | 0,377 | 0,635 | 0,774 |
| granite-embedding-311m-multilingual-r2 | 0,770 | 0,681 | 0,572 | 0,718 | 0,557 | 0,347 | 0,607 | 0,686 |
| Qwen3-Embedding-0.6B | 0,794 | 0,632 | 0,562 | 0,691 | 0,574 | 0,370 | 0,603 | 0,778 |
| multilingual-e5-large-instruct | 0,812 | 0,692 | 0,561 | 0,769 | 0,579 | 0,182 | 0,599 | 0,806 |
| harrier-oss-v1-270m | 0,783 | 0,610 | 0,547 | 0,702 | 0,488 | 0,298 | 0,571 | 0,761 |
| granite-embedding-97m-multilingual-r2 | 0,758 | 0,649 | 0,495 | 0,652 | 0,462 | 0,325 | 0,557 | 0,666 |
| multilingual-e5-base | 0,822 | 0,639 | 0,553 | 0,619 | 0,491 | 0,177 | 0,550 | 0,745 |
| multilingual-e5-small | 0,828 | 0,587 | 0,493 | 0,494 | 0,494 | 0,145 | 0,507 | 0,743 |

O que o artigo conclui e interessa aqui:

- A curva qualidade × tamanho dos modelos abertos "rises steeply with scale at the small end and then flattens", com o joelho no `embeddinggemma-300m`; acima disso, "two further orders of magnitude in parameters add little" (seção VII). **independente**.
- O ranking no leaderboard multilíngue prevê o ranking em PT "only moderately": um modelo que é 3º de 55 no MMTEB cai para 49º no MTEB-BR (`llama-embed-nemotron-8b`), e a queda se concentra em recuperação (seção VII). É o argumento central para não escolher embedder só pela média MMTEB. **independente**.
- Encoders específicos de português (BERTimbau, Serafim, Albertina) ficam atrás dos multilíngues em recuperação, e o artigo atribui a diferença ao objetivo de treino, não à língua. Os `serafim-*-ir`, treinados para IR, chegam a ~0,52–0,53, abaixo do `embeddinggemma` (0,654). **independente**. Não há hoje modelo brasileiro que justifique entrar no registry por qualidade de recuperação.

Limites do MTEB-BR: preprint de um único autor; o top 6 é "statistically too close to order"; os intervalos de confiança do ranking são largos (o `embeddinggemma` tem IC de posição [6, 26]); o corte em 512 tokens esconde vantagens de contexto longo (irrelevante para o Ditto).

### 3.2 MTEB-PT (independente, subconjunto português do MMTEB)

O [MTEB-PT](https://arxiv.org/abs/2607.04071) (USP) usa 3 tarefas de recuperação: WebFAQRetrieval (10.000 consultas, 209.353 documentos), WikipediaRetrievalMultilingual e MultiLongDocRetrieval. Resultados de recuperação (nDCG@10, tabela 3 do artigo): `qwen3-embedding-0.6b` 78,9; `gte-multilingual-base` 76,9; `multilingual-e5-large` 73,4; `multilingual-e5-base` 71,7; `multilingual-e5-small` 70,2; `multilingual-e5-large-instruct` 70,1; `multilingual-mpnet-base` 58,0; `serafim-900m` 54,9. **independente**.

O MTEB-PT **não avaliou** EmbeddingGemma, bge-m3, Arctic nem Granite. Os dois benchmarks discordam sobre o Qwen3-0.6B (1º no MTEB-PT; no MTEB-BR, 0,603 em recuperação, atrás de bge-m3, Arctic-l e EmbeddingGemma e praticamente empatado com o `e5-large-instruct`, que tem 0,599). O MTEB-PT inclui MultiLongDoc, que favorece contexto longo (o próprio artigo diz que "models with longer context windows excel on retrieval/reranking"), e o MTEB-BR corta tudo em 512 tokens. Isso explica parte da divergência. **conjectura**.

### 3.3 Uma anomalia: `paraphrase-multilingual-MiniLM-L12-v2` no MTEB-BR

No leaderboard, o `paraphrase` tem 0,249 em AssinSTS e 0,058 em FaQuAD-IR, quase o piso aleatório (0,023 em FaQuAD-IR). Isso não bate com a medição local (seção 5: R@1 de 0,74 na FAQ) nem com o uso normal do modelo em STS. O mais provável é erro de avaliação dessa linha, não desempenho real. **conjectura**. Não uso esse número em nenhuma conclusão.

### 3.4 MMTEB (fornecedores e leaderboard)

O [MMTEB](https://arxiv.org/abs/2502.13595) é o benchmark multilíngue oficial. A tabela 6 do [relatório do EmbeddingGemma](https://arxiv.org/abs/2509.20354), que reproduz o leaderboard de modelos < 500M, dá em recuperação: EmbeddingGemma 62,5 (768d), 61,5 (512d), 58,8 (256d), 55,3 (128d); gte-multilingual-base 56,5; snowflake-arctic-embed-m-v2.0 54,8; multilingual-e5-base 52,7; granite-embedding-278m-multilingual 52,2; multilingual-e5-small 49,3. A tabela 5 dá Qwen3-Embedding-0.6B 64,65, e5-large-instruct 57,12 e bge-m3 54,60. Esses números estão no leaderboard, mas quem os seleciona e apresenta é o fornecedor do EmbeddingGemma. **fornecedor**.

Números declarados por fornecedores, sem confirmação independente em PT:
- Granite R2: 311M "scores 65.2 on Multilingual MTEB Retrieval (18 tasks)" e 97M "scores 60.3", "outperforming ... multilingual-e5-small at 50.9" ([card 311M](https://huggingface.co/ibm-granite/granite-embedding-311m-multilingual-r2), [card 97M](https://huggingface.co/ibm-granite/granite-embedding-97m-multilingual-r2)). No MTEB-BR, o 311M fica atrás do EmbeddingGemma (0,607 contra 0,654), embora o fornecedor declare mais no MMTEB (65,2 contra 62,5).
- harrier-oss-v1-270m: "MTEB v2 Score 66.5" ([card](https://huggingface.co/microsoft/harrier-oss-v1-270m)), treinado com destilação. No MTEB-BR fica em 40º (0,604 geral; 0,571 em recuperação). É um exemplo concreto de média multilíngue alta que não se repete em PT.
- jina-embeddings-v5-text-nano (239M): "65.5 on MMTEB" ([card](https://huggingface.co/jinaai/jina-embeddings-v5-text-nano)). A versão `small` (596M) faz 0,643 geral no MTEB-BR. Licença **CC-BY-NC-4.0** e `custom_code`; a nano não aparece no MTEB-BR.
- nomic-embed-text-v2-moe: MIRACL 65,80 e BEIR 52,86 ([card](https://huggingface.co/nomic-ai/nomic-embed-text-v2-moe)). Sem avaliação em PT que eu tenha achado.
- Arctic Embed 2.0: m-v2.0 com MIRACL(4) 55,2 e CLEF 51,7/53,9; l-v2.0 com 55,8 e 52,9/54,3 ([card m](https://huggingface.co/Snowflake/snowflake-arctic-embed-m-v2.0), [card l](https://huggingface.co/Snowflake/snowflake-arctic-embed-l-v2.0)). A tabela da card rotula "me5 base" com 560M, que é o tamanho do e5-large. Trato esses números com cautela.

---

## 4. Ficha de cada candidato

**`google/embeddinggemma-300m`**. 308M parâmetros, "roughly 100M model parameters and 200M embedding parameters" ([Google Developers Blog](https://developers.googleblog.com/en/introducing-embeddinggemma/)). É um backbone Gemma 3 com atenção bidirecional, mean pooling e duas camadas densas, com saída de 768 dims e MRL em 512/256/128 ([blog HF](https://huggingface.co/blog/embeddinggemma)). Contexto de 2048 tokens, 100+ línguas. Prompts obrigatórios: consulta `task: search result | query: `, documento `title: none | text: ` (ou `title: {título} | text: `). No `sentence-transformers` esses prompts ficam em `config_sentence_transformers.json` com os nomes `query`/`document` e são aplicados por `encode_query`/`encode_document`. A card avisa que "EmbeddingGemma activations do not support `float16`": em GPU, usar fp32 ou bf16. Quantização: bf16 61,15 → int8 60,93 → int4 60,62 no MMTEB médio (tabela 1 do relatório). O Google diz que roda "on less than 200MB of RAM with quantization" e declara "<15ms ... (256 input tokens) on EdgeTPU". **fornecedor**. Há ONNX (fp32, fp16, q4, int8) em [`onnx-community/embeddinggemma-300m-ONNX`](https://huggingface.co/onnx-community/embeddinggemma-300m-ONNX), além de integração com llama.cpp, MLX e Ollama segundo o Google. Licença: [Gemma Terms of Use](https://ai.google.dev/gemma/terms). Uso comercial permitido, sujeito à Prohibited Use Policy; quem redistribui precisa repassar os termos; "Google claims no rights in Outputs". Não é licença OSI. Uso acadêmico sem problema. **Repositório gated**: sem token, `config.json` devolve HTTP 401 (testado aqui). Existem espelhos não gated sob a mesma licença (por exemplo [`unsloth/embeddinggemma-300m`](https://huggingface.co/unsloth/embeddinggemma-300m), com os mesmos prompts no `config_sentence_transformers.json`), mas são de terceiros.

**`ibm-granite/granite-embedding-97m-multilingual-r2`**. 97M, 384 dims, arquitetura ModernBERT, contexto de 32.768 tokens, vocabulário de 262K, MRL, "enhanced support for 52 languages" com Portuguese na lista, Apache 2.0, lançado em 2026-04-29 ([card](https://huggingface.co/ibm-granite/granite-embedding-97m-multilingual-r2), [card 311M](https://huggingface.co/ibm-granite/granite-embedding-311m-multilingual-r2)). Prompts vazios (`"query": ""`, `"document": ""` no config do ST). "Released with ONNX and OpenVINO models; compatible with vLLM and llama.cpp (GGUF)". Não precisa de `trust_remote_code`. Dados de treino "permissive, enterprise-friendly" (declaração do fornecedor).

**`Qwen/Qwen3-Embedding-0.6B`**. 0,6B, 28 camadas, até 1024 dims com MRL (32–1024), contexto de 32k, 100+ línguas, Apache 2.0 ([card](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B)). Instrução só na consulta. O prompt padrão do ST é `Instruct: Given a web search query, retrieve relevant passages that answer the query\nQuery:`; a card recomenda escrever a instrução em inglês e adaptá-la à tarefa. Pooling pelo último token, com `padding_side="left"` recomendado. Memória de 2272 MB em fp32, segundo a tabela 5 do relatório do EmbeddingGemma, contra 578 MB do EmbeddingGemma. **fornecedor (terceiro)**.

**`BAAI/bge-m3`**. Base XLM-R large, 568M, 1024 dims, 8192 tokens, MIT, sem instrução. Gera vetores densos, esparsos e multi-vetor (ColBERT) ([card](https://huggingface.co/BAAI/bge-m3)). Pelo `sentence-transformers` sai só o denso. Independente: 0,635 em recuperação no MTEB-BR. Custa o dobro do EmbeddingGemma em memória e fica um pouco abaixo dele em qualidade.

**`Snowflake/snowflake-arctic-embed-l-v2.0` / `m-v2.0`**. O l tem 568M (base bge-m3-retromae) e o m tem 305M (base gte-multilingual-base); Apache 2.0, prefixo `query: ` só na consulta, MRL em 256 dims. O **m exige `trust_remote_code=True`** ([card m](https://huggingface.co/Snowflake/snowflake-arctic-embed-m-v2.0)). O l carrega sem código remoto e tem 0,636 no MTEB-BR (melhor que o EmbeddingGemma em JurisTCU e FaqBacen).

**`Alibaba-NLP/gte-multilingual-base`**. 305M, 768 dims (elástico 128–768), 8192 tokens, 70+ línguas, Apache 2.0; **`trust_remote_code=True` obrigatório**, e o xformers é recomendado para unpadding ([card](https://huggingface.co/Alibaba-NLP/gte-multilingual-base)). 76,9 em recuperação no MTEB-PT (independente). Não está no MTEB-BR.

**`intfloat/multilingual-e5-large-instruct`**. 560M, 1024 dims, 512 tokens, MIT; na consulta, `Instruct: {task}\nQuery: {q}` ([card](https://huggingface.co/intfloat/multilingual-e5-large-instruct)). O melhor em STS no MTEB-PT, mas mediano em recuperação nos dois benchmarks de PT.

**`nomic-ai/nomic-embed-text-v2-moe`**. MoE com 475M no total e 305M ativos, 768 dims (MRL até 256), **512 tokens**, Apache 2.0; prefixos `search_query: `/`search_document: `; `trust_remote_code=True` obrigatório, e para GPU a card pede `megablocks` instalado do GitHub ([card](https://huggingface.co/nomic-ai/nomic-embed-text-v2-moe)). Sem avaliação em PT. Dependência pesada para o ganho que se pode esperar.

**`jinaai/jina-embeddings-v3`** (570M) e **v5-text-small/nano**. CC-BY-NC-4.0 e `custom_code` ([v3](https://huggingface.co/jinaai/jina-embeddings-v3), [v5 nano](https://huggingface.co/jinaai/jina-embeddings-v5-text-nano)). A v5 nano pede `peft`. A licença serve para a tese, mas não para um produto; o v3 já está no cache local da máquina.

**`sentence-transformers/static-similarity-mrl-multilingual-v1`**. Sem atenção (média de embeddings de tokens), 1024 dims, Apache 2.0. A card diz "~125x faster on CPU" que o e5-small e também diz: "this model is not intended for retrieval use cases" ([card](https://huggingface.co/sentence-transformers/static-similarity-mrl-multilingual-v1)). Descartado para retrieval. Pode servir como piso barato num experimento de ablação. **conjectura**.

**IBM granite R1 (`granite-embedding-278m-multilingual`, `107m`)**. Substituídos pela R2. O 107m R1 tem 0,510 de recuperação no MTEB-BR, igual ao e5-small.

---

## 5. Medição local no hardware do projeto

**Setup.** MacBook Air M2, 8 GB, venv do backend (`torch 2.14.0`, `sentence-transformers 6.1.0`, `transformers 5.17.0`), um processo por modelo e por device, `max_seq_length` ≤ 512, fp32, `normalize_embeddings=True`, com os prefixos da seção 6. O EmbeddingGemma foi carregado do espelho `unsloth/embeddinggemma-300m`, porque o oficial é gated. **Tarefa de sanidade:** o corpus são os 50 corpos de resposta de `database/faq_manus_normalizado.md` (sem o título `###`). As consultas são (a) os 50 títulos-pergunta e (b) as 7 perguntas de `database/perguntas.csv` cuja evidência aponta para uma única seção de `faq_manus_completa.md`. Métricas: Recall@1 e MRR@10. As latências são de uma segunda passada, com o modelo aquecido. O script está no scratchpad da sessão e não foi versionado. **medição local**.

| Modelo | Dim | Device | 50 trechos (s) | 1 consulta (ms, mediana) | RSS pico do processo (MB) | Títulos R@1 / MRR@10 (n=50) | Paráfrases R@1 (n=7) |
|---|---|---|---|---|---|---|---|
| multilingual-e5-small (`e5`) | 384 | CPU | 0,61 | 8,3 | 1154 | 0,82 / 0,854 | 6/7 |
| | | MPS | 0,22 | 8,9 | 952 | 0,82 / 0,854 | 6/7 |
| paraphrase-multilingual-MiniLM-L12-v2 | 384 | CPU | 0,41 | 8,1 | 1285 | 0,74 / 0,813 | 3/7 |
| | | MPS | 0,17 | 9,4 | 1156 | 0,74 / 0,813 | 3/7 |
| granite-embedding-97m-multilingual-r2 | 384 | CPU | **4,66** | 13,8 | 933 | 0,86 / 0,907 | 5/7 |
| | | MPS | 0,50 | 9,8 | 811 | 0,82 / 0,887 | 5/7 |
| embeddinggemma-300m | 768 | CPU | 2,23 | 33,5 | 1777 | **0,90 / 0,933** | **7/7** |
| | | MPS | 2,00 | 39,0 | 1028 | 0,90 / 0,933 | 7/7 |

O RSS inclui o próprio `torch` (~400 MB antes de carregar o modelo); serve para comparar os modelos entre si, não como consumo absoluto. O Qwen3-Embedding-0.6B ficou fora da medição: o download de 1,2 GB não terminou num tempo razoável na rede desta máquina.

O que dá para tirar disso (com n tão pequeno, só direção):

- **A qualidade segue a ordem do MTEB-BR**: EmbeddingGemma > granite-97m > e5-small > paraphrase. O EmbeddingGemma acertou as 7 paráfrases e 45 dos 50 títulos. O `paraphrase` é o pior em recuperação, coerente com o fato de truncar em 128 tokens e não ter sido treinado para isso.
- **CPU.** O EmbeddingGemma custa ~3,7× o e5-small para indexar e ~4× por consulta, mas 33 ms por consulta e ~22 trechos/s continuam aceitáveis. Uma base de 1.000 chunks indexa em ~45 s em CPU. **conjectura** por extrapolação linear.
- **Surpresa: o granite-97m é lento em CPU com PyTorch** (4,7 s contra 0,6 s do e5-small, o mesmo porte em parâmetros), mas rápido em MPS (0,5 s). O tamanho do lote não muda o quadro (3,2–3,8 s com lotes de 1, 8 e 32 em textos sintéticos). A causa provável é o caminho ModernBERT em `transformers` sem flash-attention na CPU. **conjectura**. A IBM publica variantes ONNX (`onnx/model_quint8_avx2.onnx`) e OpenVINO int8 no repositório, que o `sentence-transformers` carrega com `backend="onnx"`/`"openvino"`, mas o `onnxruntime` não está no venv e não medi. Como o Ditto roda o embedder em CPU sempre que há LLM local, isso pesa contra o granite no perfil `low`.
- **MPS não ajudou o EmbeddingGemma** (2,0 s contra 2,2 s em CPU) e ajudou os modelos pequenos. Com o device policy atual, o ganho de GPU só aparece quando não há LLM local.

---

## 6. Como encaixar no Ditto

Os três cabem no `HuggingFaceEmbedder` sem mudar a interface, só com subclasses que fixam o nome do modelo e os prefixos (esboço; não alterei código):

```python
class GemmaEmbedder(HuggingFaceEmbedder):
    """EmbeddingGemma-300m; prompts from its model card (retrieval query/document)."""

    document_prefix = "title: none | text: "
    query_prefix = "task: search result | query: "

    def __init__(self, model=None, device: str | None = None) -> None:
        super().__init__("google/embeddinggemma-300m", model=model, device=device)


class GraniteSmallEmbedder(HuggingFaceEmbedder):
    """granite-embedding-97m-multilingual-r2; no prompts."""

    def __init__(self, model=None, device: str | None = None) -> None:
        super().__init__("ibm-granite/granite-embedding-97m-multilingual-r2", model=model, device=device)


class Qwen3Embedder(HuggingFaceEmbedder):
    """Qwen3-Embedding-0.6B; instruction on queries only (model card)."""

    query_prefix = "Instruct: Given a web search query, retrieve relevant passages that answer the query\nQuery:"

    def __init__(self, model=None, device: str | None = None) -> None:
        super().__init__("Qwen/Qwen3-Embedding-0.6B", model=model, device=device)
```

Detalhes que importam:

1. **Prefixos manuais ou `encode_query`/`encode_document`.** O `HuggingFaceEmbedder` concatena o prefixo à mão, e isso dá o mesmo texto que o `sentence-transformers` montaria a partir de `config_sentence_transformers.json`. Manter os prefixos explícitos na classe deixa o experimento reprodutível e visível no código, que é o padrão já usado no `E5Embedder`. **conjectura**. O `title: none` do EmbeddingGemma pode ser trocado pelo título da seção Markdown quando o chunker o guardar no payload (ver [2026-09-26-formatacao-de-dados-para-rag.md](2026-09-26-formatacao-de-dados-para-rag.md)); isso é uma variável de experimento, não um padrão.
2. **Precisão.** Não passar `torch_dtype=float16` ao EmbeddingGemma (a card proíbe). Em CPU, fp32 é o padrão do `SentenceTransformer`.
3. **Qwen3 e padding.** Com lotes de tamanhos variados, o pooling pelo último token depende de `padding_side="left"` (`tokenizer_kwargs={"padding_side": "left"}`). O `HuggingFaceEmbedder` não passa `tokenizer_kwargs`; seria preciso um parâmetro a mais no construtor. O MTEB-BR alerta que "the wrong padding side silently degrades scores" em embedders do tipo decoder.
4. **Gated.** Para `google/embeddinggemma-300m`, `make setup`/`setup-dev` precisariam pedir `HF_TOKEN` (como já pedem a chave Gemini) e o usuário teria de aceitar os termos na página do modelo. A alternativa é apontar para um espelho não gated. É uma decisão de reprodutibilidade para a tese: o espelho é de terceiro e pode mudar. Nesse caso, fixar `revision=`.
5. **Matryoshka.** `SentenceTransformer(..., truncate_dim=256)` reduz a dimensão. Qualquer variante truncada deve virar outro nome no registry (`gemma-256`), porque a coleção do Qdrant é por nome de embedding. Isso transforma a dimensão num eixo do experimento de graça.
6. **Dependências.** Subir o extra `local` para `sentence-transformers>=5.0` (e, implicitamente, `transformers>=4.56`). O Dockerfile já instala o torch CPU; nenhum dos três precisa de `trust_remote_code`, xformers, flash-attn ou megablocks.
7. **Testes.** Os testes injetam `model=` falso, então nada toca a rede. Um teste por classe nova pode checar só os prefixos, como os do `E5Embedder`.
8. **Perfis de memória.** No `low` (1 modelo local, CPU), o EmbeddingGemma cabe (RSS de pico de ~1,8 GB com o torch incluído, na seção 5). O granite-97m cabe em memória, mas é lento em CPU com PyTorch. O Qwen3-0.6B em fp32 ocupa ~2,3 GB (tabela 5 do relatório do EmbeddingGemma) e disputa RAM com o LLM MLX numa máquina de 8 GB. Eu o deixaria só para o `standard`. **conjectura** baseada nos números da seção 5.

---

## 7. O que não consegui verificar ou onde a evidência é fraca

- **Os dois benchmarks de PT são preprints de julho de 2026** e ainda não passaram por revisão. O MTEB-BR tem um só autor. Os números abaixo do top 30 vêm do JavaScript do leaderboard, não de uma tabela do artigo. Conferi que os valores do top 30 no leaderboard batem com a tabela V do artigo (por exemplo, embeddinggemma-300m com média 0,649 e FaqBacen 0,695).
- **O EmbeddingGemma não está no MTEB-PT**, e o gte-multilingual-base não está no MTEB-BR. Não há um benchmark de PT que tenha avaliado todos os candidatos com o mesmo protocolo.
- **Não achei o leaderboard MMTEB em forma legível por máquina.** Os números MMTEB citados vêm de tabelas de fornecedores (EmbeddingGemma, Qwen3, IBM, Microsoft), que selecionam os concorrentes.
- **Prompts no MTEB-BR.** O artigo diz que usa "their default task-type prompt as shipped in the pinned mteb version". Não verifiquei, modelo a modelo, se o `mteb` 2.12 aplica `query: `/`passage: ` ao e5 ou os prompts do EmbeddingGemma. Se não aplicar, os números desses modelos estão subestimados.
- **Latência em CPU com ONNX/int8** não foi medida aqui. O [guia de eficiência do sentence-transformers](https://sbert.net/docs/sentence_transformer/usage/efficiency.html) documenta `backend="onnx"`/`"openvino"` e quantização dinâmica, mas a página não traz números que eu possa citar para estes modelos.
- **A medição local** usa 50 títulos e 7 paráfrases de uma base só. Ela serve para detectar problemas grosseiros (prefixo errado, truncamento, lentidão), não para ordenar modelos.

---

## 8. Referências

Benchmarks e artigos:
- Stekel. *MTEB-BR: A Text Embedding Benchmark for Brazilian Portuguese.* arXiv 2607.04581, jul/2026. https://arxiv.org/abs/2607.04581 · leaderboard: https://huggingface.co/spaces/mteb-br/leaderboard
- Okamura, Alcoforado & Costa. *Beyond Multilingual Averages: MTEB-PT, a Benchmark for Portuguese Sentence Encoders.* arXiv 2607.04071, jul/2026. https://arxiv.org/abs/2607.04071
- Enevoldsen et al. *MMTEB: Massive Multilingual Text Embedding Benchmark.* ICLR 2025. https://arxiv.org/abs/2502.13595
- Vera et al. (Google DeepMind). *EmbeddingGemma: Powerful and Lightweight Text Representations.* arXiv 2509.20354. https://arxiv.org/abs/2509.20354
- Wang et al. *Multilingual E5 Text Embeddings: A Technical Report.* https://arxiv.org/abs/2402.05672
- Yu et al. *Arctic-Embed 2.0: Multilingual Retrieval Without Compromise.* https://arxiv.org/abs/2412.04506
- Nussbaum & Duderstadt. *Training Sparse Mixture Of Experts Text Embedding Models* (Nomic Embed v2). https://arxiv.org/abs/2502.07972
- IBM. *Granite Embedding Multilingual R2 Models.* https://huggingface.co/papers/2605.13521

Model cards e documentação:
- google/embeddinggemma-300m: https://huggingface.co/google/embeddinggemma-300m · blog HF: https://huggingface.co/blog/embeddinggemma · Google: https://developers.googleblog.com/en/introducing-embeddinggemma/ · termos: https://ai.google.dev/gemma/terms
- ibm-granite/granite-embedding-97m-multilingual-r2: https://huggingface.co/ibm-granite/granite-embedding-97m-multilingual-r2 · 311m: https://huggingface.co/ibm-granite/granite-embedding-311m-multilingual-r2
- Qwen/Qwen3-Embedding-0.6B: https://huggingface.co/Qwen/Qwen3-Embedding-0.6B
- BAAI/bge-m3: https://huggingface.co/BAAI/bge-m3
- Alibaba-NLP/gte-multilingual-base: https://huggingface.co/Alibaba-NLP/gte-multilingual-base
- Snowflake/snowflake-arctic-embed-m-v2.0: https://huggingface.co/Snowflake/snowflake-arctic-embed-m-v2.0 · l-v2.0: https://huggingface.co/Snowflake/snowflake-arctic-embed-l-v2.0
- intfloat/multilingual-e5-small: https://huggingface.co/intfloat/multilingual-e5-small · large-instruct: https://huggingface.co/intfloat/multilingual-e5-large-instruct
- nomic-ai/nomic-embed-text-v2-moe: https://huggingface.co/nomic-ai/nomic-embed-text-v2-moe
- microsoft/harrier-oss-v1-270m: https://huggingface.co/microsoft/harrier-oss-v1-270m
- jinaai/jina-embeddings-v3: https://huggingface.co/jinaai/jina-embeddings-v3 · v5-text-nano: https://huggingface.co/jinaai/jina-embeddings-v5-text-nano
- sentence-transformers/static-similarity-mrl-multilingual-v1: https://huggingface.co/sentence-transformers/static-similarity-mrl-multilingual-v1
- Sentence Transformers, *Speeding up Inference*: https://sbert.net/docs/sentence_transformer/usage/efficiency.html
