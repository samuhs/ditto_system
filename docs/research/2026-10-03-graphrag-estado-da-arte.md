# GraphRAG: estado da arte 2024–2026 e o que construir no Ditto

Pesquisa feita em 2026-10-03. As afirmações sobre métodos vêm dos artigos originais (arXiv, ACL Anthology, NeurIPS/ICML/COLM), do código-fonte no GitHub (microsoft/graphrag, HKUDS/LightRAG, OSU-NLP-Group/HippoRAG, langchain-ai, ml-explore/mlx-lm), da documentação oficial (LangGraph, Ollama, NetworkX, spaCy, Qwen) e dos próprios datasets no Hugging Face, inspecionados direto. O código do Ditto foi lido em `backend/app/`. Cada afirmação tem link para a fonte. Cada recomendação traz um **nível de evidência**:

- **forte**: resultado empírico publicado, com comparação controlada, em mais de um conjunto de dados;
- **misto**: há resultado empírico, mas em um domínio, com resultados contraditórios ou longe do nosso cenário (outra língua, modelo grande, base grande);
- **só fornecedor**: post, README ou documentação de quem fez a ferramenta, sem experimento publicado que o sustente;
- **conjectura**: raciocínio meu, sem fonte direta.

---

## 1. Resumo e recomendação

**O que a literatura de 2024–2026 diz, em uma frase:** GraphRAG ganha de RAG vetorial em perguntas que exigem juntar fatos de trechos diferentes (multi-hop, comparação, temporal) e em perguntas globais de "sensemaking", e perde ou empata em perguntas de um salto sobre um fato só. Essa conclusão aparece em quatro avaliações independentes:

| Fonte | Um salto / fato | Multi-hop / raciocínio | Global / resumo |
|---|---|---|---|
| [Han et al. 2025, *RAG vs. GraphRAG*](https://arxiv.org/abs/2502.11371) | RAG vence (NQ: 64,78 F1 contra 63,01 do melhor GraphRAG, Llama 3.1-8B) | GraphRAG vence (HotpotQA: HippoRAG2 63,01 contra 60,04) | métricas com referência favorecem RAG; juiz LLM tem viés de posição |
| [Xiang et al. 2025, *GraphRAG-Bench*](https://arxiv.org/abs/2506.05690) | RAG com rerank 60,92 contra HippoRAG2 60,14 e MS-GraphRAG 49,29 | HippoRAG2 53,38 contra RAG 42,93 | MS-GraphRAG 64,40 contra RAG 51,30 |
| [Gutiérrez et al. 2025, HippoRAG 2](https://arxiv.org/abs/2502.14802) | NQ: RAG 61,9 F1; GraphRAG 46,9; LightRAG 16,6 | 2Wiki: HippoRAG 2 71,0 contra RAG 61,5 | — |
| [Edge et al. 2024, GraphRAG](https://arxiv.org/abs/2404.16130) | não avalia | não avalia | 72–83% de vitória em abrangência contra RAG vetorial |

Nível: **forte** para a divisão "um salto → RAG; multi-hop/global → grafo". Nenhuma dessas avaliações usa português, base pequena ou LLM de 7B na extração.

**O que isso significa para o Ditto.** A base-alvo (`database/guia_santo_antonio_da_alegria.md`, 491 linhas, 103 seções `###`, ~51 mil caracteres) é FAQ: cada seção responde uma pergunta e repete o nome da cidade. As perguntas atuais (`database/perguntas.csv`) são todas de um salto. Nesse cenário a literatura prevê que um GraphRAG **empate ou perca** para o RAG vetorial. Isso é um resultado válido para a tese, mas só se o conjunto de perguntas também tiver perguntas em que o grafo deveria ajudar. Por isso a ordem recomendada é:

1. **Primeiro as perguntas** (seção 6): estender o CSV com `tipo`, `n_saltos`, `entidades_ponte` e evidência por salto, mantendo `pergunta,resposta_referencia,evidencia_referencia` como estão (o loader atual ignora colunas extras). Escrever 20–40 perguntas de ponte, comparação e agregação sobre a base da cidade. Custo baixo, e sem isso o GraphRAG não tem como mostrar ganho.
2. **Depois um GraphRAG mínimo** (seção 7), no estilo LightRAG-local + HippoRAG: extração por chunk com LLM local em formato de delimitadores, resolução de entidades por nome normalizado + embedding, entidades e relações em collections do Qdrant com os ids dos chunks de origem, vizinhança de 1 salto (PPR como variante) e **contexto final = chunks de origem**, para que `context_hit`/`context_recall_gold` continuem valendo.
3. **Ficam fora do mínimo**: comunidades Leiden e busca global map-reduce (caras demais para LLM local e base pequena), resumos de entidade por LLM, gleaning múltiplo e filtro de triplas por LLM. Cada um pode entrar depois como variante no registry.

**Risco principal** (conjectura, apoiada em [MiniRAG](https://arxiv.org/abs/2501.06713) e na nota da [HippoRAG](https://arxiv.org/abs/2405.14831) com Llama-3.1-8B): a qualidade da extração com Qwen2.5-7B-4bit ou qwen3:1.7b em português. O MiniRAG mediu o LightRAG caindo de 56,90% para 35,42% de acurácia ao trocar o LLM por um modelo pequeno, e o GraphRAG da Microsoft falhando por completo. O mínimo viável deve, por isso, depender o menos possível do LLM na consulta e tratar o LLM de extração como **eixo fixo e separado** do LLM de resposta.

---

## 2. Estado da arte

### 2.1 Microsoft GraphRAG (Edge et al. 2024) e LazyGraphRAG

**Construção.** Chunks de 600 tokens com 100 de overlap. Um LLM extrai entidades, relações e (opcional) *claims* de cada chunk com prompt few-shot, e faz uma etapa de *self-reflection* ("gleaning") para recuperar o que faltou. Os autores relatam que o GPT-4 "extracted almost twice as many entity references when the chunk size was 600 tokens than when it was 2400". Descrições repetidas da mesma entidade são resumidas por LLM, o grafo é particionado em comunidades hierárquicas por Leiden e cada comunidade ganha um "relatório" escrito pelo LLM ([arXiv 2404.16130](https://arxiv.org/abs/2404.16130)). A documentação descreve as etapas e estima a extração do grafo em "roughly 75% of indexing cost" ([docs/index/methods.md](https://github.com/microsoft/graphrag/blob/main/docs/index/methods.md)).

**Formato de saída.** O prompt pede registros `("entity"<|><entity_name><|><entity_type><|><entity_description>)` e `("relationship"<|><source_entity><|><target_entity><|><relationship_description><|><relationship_strength>)`, separados por `##`, e manda "Return output in English". O gleaning usa dois prompts fixos: `CONTINUE_PROMPT` ("MANY entities and relationships were missed in the last extraction...") e `LOOP_PROMPT`, que pede uma resposta Y/N sobre se ainda falta algo ([extract_graph.py](https://github.com/microsoft/graphrag/blob/main/packages/graphrag/graphrag/prompts/index/extract_graph.py)).

**Recuperação.** Quatro modos: *global* (map-reduce sobre relatórios de comunidade), *local* (entidade + vizinhos), *DRIFT* (local com contexto de comunidade) e *basic* (RAG vetorial) ([docs](https://microsoft.github.io/graphrag/)). Na busca global, cada relatório de comunidade gera uma resposta parcial com nota 0–100, e as melhores são combinadas numa resposta final ([arXiv 2404.16130](https://arxiv.org/abs/2404.16130)).

**Resultado.** Em dois corpora de ~1M e ~1,7M tokens, com 125 perguntas globais geradas por LLM a partir de personas e tarefas, o GraphRAG venceu o RAG vetorial em abrangência (72–83%) e diversidade (62–82%), avaliado por LLM em comparação pareada. O nível mais alto de comunidade (C0) usou "9x-43x" menos tokens do que resumir o texto-fonte inteiro ([arXiv 2404.16130](https://arxiv.org/abs/2404.16130)). Nível: **misto**. É uma avaliação de perguntas globais com juiz LLM, em inglês, e não mede fatos pontuais.

**Custo.** No MuSiQue, o GraphRAG gastou 115,5M tokens de entrada e 277 min para indexar, contra 9,2M e 99,5 min do HippoRAG 2 ([arXiv 2502.14802](https://arxiv.org/abs/2502.14802), Tabela 12).

**LazyGraphRAG e FastGraphRAG.** O LazyGraphRAG troca o LLM da indexação por extração de sintagmas nominais por NLP e um grafo de coocorrência. Todo uso de LLM fica adiado para a consulta, com um "relevance test budget" que controla o custo. A Microsoft relata indexação com custo "identical to vector RAG and 0.1% of the costs of full GraphRAG" ([blog MSR, nov/2024](https://www.microsoft.com/en-us/research/blog/lazygraphrag-setting-a-new-standard-for-quality-and-cost/)). Nível: **só fornecedor**. No repositório, a variante que já existe é o `--method fast`: entidades são sintagmas nominais (NLTK ou spaCy), relações são coocorrência no mesmo chunk e não há descrições. A doc avisa que o extrator padrão é "primarily suitable for English" e que o grafo "tends to be quite a bit noisier" ([methods.md](https://github.com/microsoft/graphrag/blob/main/docs/index/methods.md)).

### 2.2 LightRAG (Guo et al. 2024)

**Construção.** Três funções: R(·) extrai entidades e relações por chunk, P(·) gera pares chave-valor (a chave é uma palavra ou frase curta; o valor é um parágrafo-resumo) e D(·) junta entidades e relações idênticas vindas de chunks diferentes. Não há comunidades. Os experimentos usaram GPT-4o-mini e chunks de 1200 tokens ([arXiv 2410.05779](https://arxiv.org/abs/2410.05779)).

**Recuperação dual.** Um LLM extrai da pergunta dois conjuntos de palavras-chave em JSON (`high_level_keywords`, `low_level_keywords`) ([prompt.py](https://github.com/HKUDS/LightRAG/blob/main/lightrag/prompt.py)). No modo *local*, as de baixo nível são buscadas na base vetorial de **entidades**. No modo *global*, as de alto nível são buscadas na base vetorial de **relações**. Os vizinhos de 1 salto entram no contexto, e os chunks de origem são achados pelo campo `source_id` de cada entidade ([operate.py](https://github.com/HKUDS/LightRAG/blob/main/lightrag/operate.py)). Há também os modos `hybrid`, `naive` e `mix`, que é o padrão e combina grafo com chunks vetoriais ([README](https://github.com/HKUDS/LightRAG/blob/main/README.md)).

**Limites de contexto (padrões no código).** `DEFAULT_TOP_K = 40`, `DEFAULT_CHUNK_TOP_K = 20`, `DEFAULT_MAX_ENTITY_TOKENS = 6000`, `DEFAULT_MAX_RELATION_TOKENS = 8000`, `DEFAULT_MAX_TOTAL_TOKENS = 30000`, `DEFAULT_MAX_GLEANING = 1`, `DEFAULT_SUMMARY_LANGUAGE = "English"` ([constants.py](https://github.com/HKUDS/LightRAG/blob/main/lightrag/constants.py)). Um orçamento de 30 mil tokens não cabe no perfil ≤ 8 GB do Ditto. Para um 7B local o orçamento tem de ser bem menor (seção 3.6).

**Resultado.** Nos quatro conjuntos UltraDomain (0,6M a 5M tokens, 125 perguntas cada, geradas como no GraphRAG), o LightRAG venceu o NaiveRAG em 83,6% e o GraphRAG em 52,8% (critério *overall*, no Legal), por juiz LLM pareado. Na consulta, os autores relatam "fewer than 100 tokens" e uma chamada de API, contra 610 mil tokens do GraphRAG global ([arXiv 2410.05779](https://arxiv.org/abs/2410.05779)). Nível: **misto**. É o mesmo protocolo de perguntas globais com juiz LLM. Em avaliações de terceiros com perguntas factuais o LightRAG vai mal: 16,6 F1 no NQ contra 61,9 do RAG vetorial ([HippoRAG 2, Tabela 2](https://arxiv.org/abs/2502.14802)), e LightRAG 58,62 contra RAG 60,92 em *fact retrieval* ([GraphRAG-Bench](https://arxiv.org/abs/2506.05690)). O 16,6 é tão baixo que pode refletir configuração e não o método (**conjectura**).

**Requisitos de LLM (fornecedor).** O README de 2026 diz que, para rodar local, "Qwen3-30B-A3B-Instruct is a reasonable minimum" para a extração, recomenda um modelo "non-thinking" e um reranker (`BAAI/bge-reranker-v2-m3`) ([README](https://github.com/HKUDS/LightRAG/blob/main/README.md)). Nível: **só fornecedor**, mas é um sinal de que 7B está abaixo do que os autores consideram seguro.

### 2.3 HippoRAG (NeurIPS 2024) e HippoRAG 2 (ICML 2025)

**Construção (HippoRAG).** O LLM faz NER no trecho e depois OpenIE condicionado às entidades, com saída em JSON (`{"named_entities": [...]}`, depois `{"triples": [...]}`) ([templates](https://github.com/OSU-NLP-Group/HippoRAG/tree/main/src/hipporag/prompts/templates)). O KG não tem esquema. Arestas de sinonímia ligam nós cujo cosseno no encoder passa de τ = 0,8. Uma matriz passagem × nó guarda de onde veio cada nó ([arXiv 2405.14831](https://arxiv.org/abs/2405.14831)).

**Recuperação.** NER na pergunta → nós do KG mais próximos pelo encoder → **Personalized PageRank** a partir desses nós (fator de amortecimento 0,5) → nota de cada passagem = soma das probabilidades dos seus nós, ponderada pela especificidade do nó (|P_i|⁻¹, o inverso do número de passagens que contêm o nó). Resultado: até 20% a mais de Recall@5 no 2WikiMultiHopQA, desempenho comparável no HotpotQA ("a much weaker test for multi-hop reasoning") e 10–30× mais barato que recuperação iterativa (IRCoT) ([arXiv 2405.14831](https://arxiv.org/abs/2405.14831)). A especificidade de nó é a peça que importa para a base do Ditto: "Santo Antônio da Alegria" aparece em quase todas as seções e, sem esse peso, vira um hub que espalha a probabilidade por todo o grafo (**conjectura** sobre o efeito; o mecanismo é do artigo).

**HippoRAG 2.** Adiciona nós de passagem ao grafo, com arestas "contains" entre passagem e frase. Liga a pergunta a **triplas** e não só a entidades, usa o LLM como "recognition memory" para filtrar triplas irrelevantes e dá peso 0,05 às passagens no vetor de reinício do PPR ([arXiv 2502.14802](https://arxiv.org/abs/2502.14802)). É o único método da tabela que não perde do RAG vetorial em QA simples: NQ 63,3 contra 61,9, e média 59,8 contra 57,0. Os autores motivam o trabalho dizendo que métodos com estrutura têm desempenho em memória factual que "drops considerably below standard RAG" ([abstract](https://arxiv.org/abs/2502.14802)). Nível: **forte** (7 datasets), mas com Llama-3.3-70B na extração.

### 2.4 Outros

- **KAG** (Ant Group): representação "LLM-friendly", indexação mútua entre grafo e chunks e raciocínio guiado por forma lógica. Relata +19,6% e +33,5% de F1 relativo no 2Wiki e no HotpotQA ([arXiv 2409.13731](https://arxiv.org/abs/2409.13731)). Depende de esquema de domínio e de um motor próprio (OpenSPG). É pesado demais para o Ditto (**conjectura**).
- **G-Retriever**: recuperação de subgrafo por *Prize-Collecting Steiner Tree* sobre grafos textuais, com GNN e *soft prompting* treinados ([arXiv 2402.07630](https://arxiv.org/abs/2402.07630)). Exige treino e acesso a embeddings internos do LLM. Não cabe num LLM servido por API OpenAI-compatível.
- **MiniRAG**: feito para modelos pequenos. Monta um grafo heterogêneo com nós de chunk e nós de entidade (arestas entidade–entidade e entidade–chunk). Na consulta usa só extração de entidades e predição do tipo da resposta, sem resumos gerados por LLM, e combina similaridade de embedding com caminhos no grafo. Com Phi-3.5-mini, GLM-Edge-1.5B, Qwen2.5-3B e MiniCPM3-4B, ficou 5–12 pontos acima do NaiveRAG no LiHuaWorld e no MultiHop-RAG. Com esses modelos o LightRAG ficou entre 35 e 40% e o GraphRAG falhou ("/") ([arXiv 2501.06713](https://arxiv.org/abs/2501.06713)). O artigo não deixa claro qual modelo construiu o índice. Nível: **misto**.
- **Surveys.** [Peng et al. 2024](https://arxiv.org/abs/2408.08921) organizam a área em G-Indexing → G-Retrieval → G-Generation. [Han et al. 2025](https://arxiv.org/abs/2501.00309) propõem os componentes *query processor, retriever, organizer, generator, data source* e defendem que grafos de domínios diferentes "require dedicated designs". Os dois servem para a revisão de literatura da tese. Não trazem números próprios.

### 2.5 Benchmarks comparativos: quando o grafo ganha

- **Han et al., *RAG vs. GraphRAG*** ([arXiv 2502.11371](https://arxiv.org/abs/2502.11371)). No MultiHop-RAG com Llama 3.1-70B, o RAG ganha em *inference* (94,85 contra 92,03) e *null* (91,36 contra 88,70). O GraphRAG local ganha em *comparison* (60,16 contra 56,31) e *temporal* (49,06 contra 25,73). Dois achados contam muito para o Ditto. (a) Só ~65,8% das entidades-resposta do HotpotQA aparecem no KG extraído, e o KG-GraphRAG só com triplas teve 39,20% de acurácia de recuperação contra 88,60% do RAG. Em F1 com Llama 3.1-8B, no HotpotQA, "só triplas" fez 25,02, "triplas + texto" 42,60 e RAG 60,04. **Triplas sem o texto perdem informação.** (b) No juiz LLM pareado, trocar a ordem das respostas muda e às vezes inverte o veredito ("position bias is clearly present"). Integrar RAG e GraphRAG deu +6,4% no MultiHop-RAG, e escolher um dos dois por pergunta deu +1,1%. Nível: **forte**.
- **GraphRAG-Bench (Xiang et al. 2025)** ([arXiv 2506.05690](https://arxiv.org/abs/2506.05690), [repo](https://github.com/GraphRAG-Bench/GraphRAG-Benchmark)). Dois corpora (romances do Gutenberg e diretrizes médicas NCCN) e 4 níveis: Fact Retrieval, Complex Reasoning, Contextual Summarize e Creative Generation. Gerador GPT-4o-mini. Resultados no Novel na tabela da seção 1. O prompt do MS-GraphRAG global chega a ~4×10⁴ tokens, contra ~10³ do HippoRAG2. Nível: **forte**.
- **GraphRAG-Bench (Xiao et al. 2025)**, outro benchmark com o mesmo nome: questões de nível universitário em 16 disciplinas, avalia construção, recuperação e geração ([arXiv 2506.02404](https://arxiv.org/abs/2506.02404)). Não li os números. Fica fora do escopo do Ditto.

---

## 3. Componentes de uma arquitetura própria

Cada componente traz o que é **mínimo** (MVP) e o que é **opcional** (vira variante no registry).

### 3.1 Extração de entidades e relações — **mínimo**

- **Unidade**: o chunk do Índice. Isso segue a definição do `CONTEXT.md` ("derivado de um Índice"). O texto extraído só depende do **chunking**, não do embedding. Guardar a extração em cache pelo hash do texto do chunk + LLM de extração + versão do prompt evita repetir a extração quando só o embedder muda (**conjectura**, ganho de engenharia).
- **Prompt**: o do LightRAG/GraphRAG (entidade com nome, tipo, descrição; relação com origem, destino, palavras-chave, descrição) ([LightRAG prompt.py](https://github.com/HKUDS/LightRAG/blob/main/lightrag/prompt.py); [GraphRAG extract_graph.py](https://github.com/microsoft/graphrag/blob/main/packages/graphrag/graphrag/prompts/index/extract_graph.py)), traduzido e com 1–2 exemplos tirados de uma **outra** base PT-BR, nunca da base de teste. Tipos de entidade para guia de cidade: `lugar, estabelecimento, evento, pessoa, organização, produto, serviço` (**conjectura**). O LightRAG deixa o idioma configurável ("must be written in `{language}`") com padrão inglês. Os dois prompts originais pedem saída em inglês.
- **Formato de saída**: seção 5.2.
- **Gleaning** — **opcional**. O LightRAG usa 1 rodada por padrão ([constants.py](https://github.com/HKUDS/LightRAG/blob/main/lightrag/constants.py)). O ganho do GraphRAG foi medido com GPT-4 e chunks grandes ([Edge et al.](https://arxiv.org/abs/2404.16130)). Com seções de ~500 caracteres, a chance de omissão é menor e o custo dobra (**conjectura**).

### 3.2 Resolução de entidades — **mínimo** (versão barata)

- **Normalização de nome** antes de juntar: casefold, espaços, remover sufixos que a base repete ("em Santo Antônio da Alegria"), aliases entre parênteses ("Cachoeira do Deosdédi (Cachoeira do Dédi)"). O LightRAG junta por nome exato e escolhe o tipo por maioria ([operate.py](https://github.com/HKUDS/LightRAG/blob/main/lightrag/operate.py)). O GraphRAG reconcilia por "string matching" ([Edge et al.](https://arxiv.org/abs/2404.16130)).
- **Sinonímia por embedding**: o HippoRAG **não funde** os nós. Liga os pares com cosseno ≥ 0,8 por arestas de sinonímia ([arXiv 2405.14831](https://arxiv.org/abs/2405.14831)). Isso é mais seguro que fundir ("Serra da Lajinha" e "Serra da Laginha" devem ficar juntas, mas "Cachoeira do Adilson" e "Cachoeira do Deosdédi" não). Fundir com clustering e LLM (KGGen ([arXiv 2502.09956](https://arxiv.org/abs/2502.09956)); RAGU com DBSCAN ([arXiv 2607.11683](https://arxiv.org/abs/2607.11683))) fica como **opcional**.
- **Hub da cidade**: a entidade "Santo Antônio da Alegria" vai aparecer em quase todos os chunks. Ou ela sai da expansão, ou entra com o peso de especificidade do HippoRAG (seção 2.3).

### 3.3 Descrição de entidades — mínimo = concatenar; resumo por LLM = **opcional**

O LightRAG concatena os fragmentos de descrição e só chama o LLM para resumir quando eles passam de um limite ([operate.py](https://github.com/HKUDS/LightRAG/blob/main/lightrag/operate.py); `DEFAULT_SUMMARY_MAX_TOKENS = 1200` em [constants.py](https://github.com/HKUDS/LightRAG/blob/main/lightrag/constants.py)). O MiniRAG mostra que descrições geradas por modelos pequenos são "notably lower-quality" ([arXiv 2501.06713](https://arxiv.org/abs/2501.06713)). Numa base de 103 seções poucas entidades devem passar de 3–4 fragmentos (**conjectura**).

### 3.4 Indexação vetorial e armazenamento — **mínimo**

Duas collections no Qdrant por Índice × LLM de extração, por exemplo `kg_ent__{indice}__{llm}` e `kg_rel__{indice}__{llm}`:
- entidade: vetor de `nome + descrição`, payload `{nome, nome_normalizado, tipo, descricao, chunk_ids[]}`;
- relação: vetor de `palavras-chave + origem + destino + descrição`, payload `{origem, destino, palavras_chave, descricao, peso, chunk_ids[]}`.

É o mesmo desenho do LightRAG (`entities_vdb`, `relationships_vdb`, `source_id` com os chunks) ([operate.py](https://github.com/HKUDS/LightRAG/blob/main/lightrag/operate.py)). O grafo `networkx` é reconstruído a partir dos payloads na carga. Com centenas de nós isso custa milissegundos (**conjectura**). `networkx` já está no venv do backend (3.7).

### 3.5 Recuperação — mínimo = vincular entidades + 1 salto; PPR e palavras-chave dual = **opcional**

1. **Vincular a pergunta a entidades.** Duas opções:
   - (a) sem LLM: embedding da pergunta → top-k na collection de entidades (e de relações). É o mais robusto com modelo pequeno, na linha do MiniRAG (**misto**);
   - (b) com LLM: palavras-chave baixo/alto nível do LightRAG em JSON → busca em entidades/relações ([prompt.py](https://github.com/HKUDS/LightRAG/blob/main/lightrag/prompt.py)). Mais uma chamada de LLM por pergunta, e mais um ponto de falha com 1,7B.
2. **Expandir.** Vizinhos de 1 salto, ordenados por grau e peso como no LightRAG. Variante: PPR a partir das entidades vinculadas, `networkx.pagerank(G, alpha=..., personalization={...})` ([doc NetworkX](https://networkx.org/documentation/stable/reference/algorithms/generated/networkx.algorithms.link_analysis.pagerank_alg.pagerank.html)), como no HippoRAG.
3. **Voltar aos chunks.** Nota de cada chunk = soma das notas das entidades/relações que apontam para ele (HippoRAG) → top-k chunks.
4. **Integrar com o vetorial** — **opcional, mas barato**. Unir os chunks do grafo com os do retriever vetorial (o modo `mix` do LightRAG). Han et al. medem +6,4% com integração ([arXiv 2502.11371](https://arxiv.org/abs/2502.11371)).

### 3.6 Montagem do contexto e limites de tokens — **mínimo**

- O contexto que vai para o LLM leva os **chunks de origem** e, opcionalmente, uma lista curta de "fatos" (descrições de relação). Só triplas não basta: o KG captura ~65% das entidades-resposta ([Han et al.](https://arxiv.org/abs/2502.11371)).
- `RAGResult.contexts` deve trazer **só os chunks** (com o mesmo formato dos outros RAGs), para que `context_hit`, `context_mrr` e `context_recall_gold` comparem GraphRAG e RAG vetorial na mesma régua (`backend/app/core/evaluation/gold_metrics.py`). As descrições de entidades podem ir num campo separado do dict.
- Orçamento: a mesma ordem de grandeza do RAG naive de hoje (k chunks de ~1000 caracteres) mais ≤ ~500 tokens de fatos. O padrão de 30 mil tokens do LightRAG não serve para um 7B 4-bit num perfil ≤ 8 GB (**conjectura**). O GraphRAG-Bench mostra que o custo de contexto do GraphRAG global (~4×10⁴ tokens) é o que o torna caro ([arXiv 2506.05690](https://arxiv.org/abs/2506.05690)).

### 3.7 Comunidades e busca global — **opcional, não recomendado agora**

Leiden + relatórios de comunidade + map-reduce é o que dá ao GraphRAG a vantagem em perguntas globais ([Edge et al.](https://arxiv.org/abs/2404.16130)). Mas a busca global chama o LLM uma vez por relatório, e com 103 seções a base inteira cabe em poucos contextos de 8–16k tokens: dá para responder pergunta global com "texto-fonte inteiro" (a condição TS do próprio artigo) sem grafo (**conjectura**). Um baseline `stuff`/map-reduce sobre chunks mede isso mais barato.

---

## 4. LangChain e LangGraph

**LangGraph não é um grafo de conhecimento.** A doc oficial o define como "a low-level orchestration framework and runtime for building, managing, and deploying long-running, stateful agents". O "grafo" é o fluxo de controle (`StateGraph`, nós, arestas, `START`/`END`) e a doc não menciona knowledge graphs ([overview](https://docs.langchain.com/oss/python/langgraph/overview)). Ele serve para **orquestrar** a indexação e a consulta. Não guarda o grafo.

**Peças de KG no ecossistema:**

| Peça | Onde | O que faz | Limitações para o Ditto |
|---|---|---|---|
| `LLMGraphTransformer` | `langchain_experimental.graph_transformers` e também exportado por `langchain_neo4j` ([fonte](https://github.com/langchain-ai/langchain-experimental/blob/main/libs/experimental/langchain_experimental/graph_transformers/llm.py); [`__init__` do langchain-neo4j](https://github.com/langchain-ai/langchain-neo4j/blob/main/libs/neo4j/langchain_neo4j/__init__.py)) | Documento → `GraphDocument(nodes, relationships, source)` via `with_structured_output` ou, se o modelo não suportar, JSON por prompt + `json_repair` | Prompt fixo em inglês ("# Knowledge Graph Instructions for GPT-4"). Nós sem descrição. Ids passam por `.title()`. **Se o JSON não parsear, devolve `([], [])` sem erro.** Sem dedup entre documentos |
| `NetworkxEntityGraph` + `GraphQAChain` | `langchain_community` ([graph](https://github.com/langchain-ai/langchain-community/blob/main/libs/community/langchain_community/graphs/networkx_graph.py), [chain](https://github.com/langchain-ai/langchain-community/blob/main/libs/community/langchain_community/chains/graph_qa/base.py)) | Triplas `(subject, predicate, object_)`. A chain extrai entidades da pergunta como lista separada por vírgulas e pega `get_entity_knowledge` (DFS com `depth=1`) | Só triplas, sem chunks de origem, sem vetores. `add_triple` sobrescreve arestas. Prompt em inglês ([prompts.py](https://github.com/langchain-ai/langchain-community/blob/main/libs/community/langchain_community/chains/graph_qa/prompts.py)) |
| `GraphCypherQAChain`, `Neo4jGraph` | `langchain_neo4j` | Text-to-Cypher sobre Neo4j | Exige Neo4j e um LLM bom em Cypher; fora das decisões do usuário |

Conclusão: nenhuma das peças cobre o desenho decidido (Qdrant + networkx + ids de chunk). O que vale reaproveitar é a **orquestração** (LangGraph) e, no máximo, o padrão de saída do `LLMGraphTransformer`. Nível: **só fornecedor** (lido no código).

**Structured output com os servidores locais do Ditto.** O adaptador do Ditto usa `ChatOpenAI` (`backend/app/core/llm/ollama.py`). No `langchain-openai` 1.3.3 instalado, `with_structured_output` usa `method="json_schema"` por padrão (verificado no venv). O Ollama aceita JSON Schema no campo `format` e `response_format` na API OpenAI-compatível, e recomenda também colocar o schema no prompt e usar temperatura 0 ([doc Ollama](https://docs.ollama.com/capabilities/structured-outputs)). O `mlx_lm.server` **não tem** `response_format` nem decodificação restrita. Tem *tool calling* quando o chat template do modelo suporta ([server.py](https://github.com/ml-explore/mlx-lm/blob/main/mlx_lm/server.py), busca por `response_format` sem resultado). Com MLX, portanto, o JSON não tem garantia de formato, e o `LLMGraphTransformer` pode devolver grafos vazios em silêncio. A extração do Ditto precisa de parser próprio tolerante e de uma contagem de falhas de parse por chunk.

**Como montar como StateGraphs** (desenho, **conjectura** apoiada na doc):

```
Indexação (por Índice × LLM de extração)
  START → carregar_chunks (Qdrant) → [Send("extrair", chunk) para cada chunk]
        → extrair (LLM + parser; falha registrada, não silenciosa)
        → gleaning? (aresta condicional, opcional)
        → consolidar (normalizar nomes, juntar, sinonímia por embedding, especificidade)
        → embutir_e_gravar (collections kg_ent/kg_rel) → END

Consulta (GraphRAG.answer(query) → RAGResult)
  START → vincular_entidades (vetorial; ou palavras-chave por LLM)
        → expandir (1 salto | PPR) → pontuar_chunks → [unir_com_vetorial?]
        → montar_contexto (orçamento de tokens) → gerar (LLM.generate) → END
```

O fan-out por chunk usa a API `Send` ("first is the name of the node, and second is the state to pass to that node"), e a lista de extrações acumula com um reducer `Annotated[list, operator.add]` ([Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api)). O paralelismo real fica limitado pelo servidor local: o mlx-lm faz batching ([nota de 2026-09-23](2026-09-23-inferencia-small-llms.md)). A consulta é linear e pode ser uma função comum dentro de `RAG.answer`. Usar StateGraph nela só se paga se houver ramificação (por exemplo, roteamento entre vetorial e grafo).

---

## 5. LLMs locais pequenos para extração

### 5.1 Evidência sobre qualidade

- **HippoRAG**: trocando o GPT-3.5 por Llama-3.1-8B na OpenIE, o resultado é "competitive with GPT-3.5 in all datasets except 2Wiki, where performance drops substantially". O REBEL (extrator sem LLM) teve "large performance drops" ([arXiv 2405.14831](https://arxiv.org/html/2405.14831)). Nível: **forte** para 8B ser viável em inglês, com uma queda num dataset.
- **MiniRAG**: com SLMs de 1,5–4B, o LightRAG cai para 35–40% e o GraphRAG falha. A causa apontada é a qualidade das descrições e das palavras-chave geradas ([arXiv 2501.06713](https://arxiv.org/abs/2501.06713)). Nível: **misto**. Para o qwen3:1.7b do Ditto, isso sugere não depender do LLM na consulta.
- **RAGU** (2026): extração em duas etapas (entidades primeiro, depois relações restritas às entidades validadas) com um 7B ajustado. No benchmark de IE deles, o Qwen2.5-7B teve média harmônica 0,356 contra 0,468 do modelo ajustado, que superou o Qwen2.5-32B ([arXiv 2607.11683](https://arxiv.org/abs/2607.11683)). Os autores criticam a extração de passada única por produzir "noisy, duplicated entities". Nível: **misto** (russo/inglês, um grupo).
- **CoDe-KG** (EMNLP 2025): Llama-3-8B e similares, com resolução de correferência e decomposição de frases antes da extração. A ablação mostra que tirar essas etapas "hurts performance sharply" ([arXiv 2509.17289](https://arxiv.org/abs/2509.17289)). Combina com a recomendação de unidades autocontidas da [nota de 2026-09-26](2026-09-26-formatacao-de-dados-para-rag.md). A base da cidade já repete a entidade em cada seção, o que ajuda.
- **Triplex** (Phi-3 3.8B ajustado para triplas): o card afirma "98% cost reduction" e desempenho acima do GPT-4 ([HF](https://huggingface.co/SciPhi/Triplex)). Nível: **só fornecedor**. Licença cc-by-nc-sa-4.0 e exemplos em inglês.

### 5.2 Formato de saída: JSON ou delimitadores

- **Delimitadores** (GraphRAG `("entity"<|>...)`, LightRAG `entity<|#|>...`). Um registro malformado se perde sozinho e o resto se aproveita. O prompt atual do LightRAG gasta várias linhas corrigindo erros típicos ("must start with `relation`, never `entity`", "The `{tuple_delimiter}` is a complete, atomic marker and **must not be filled with content**") ([prompt.py](https://github.com/HKUDS/LightRAG/blob/main/lightrag/prompt.py)), sinal de que modelos abertos erram o formato. Esse prompt foi revisto em set/2025 para "Open-Sourced LLMs such as Qwen3-30B-A3B" ([README](https://github.com/HKUDS/LightRAG/blob/main/README.md)). Nível: **só fornecedor**.
- **JSON** (HippoRAG, LLMGraphTransformer). Funciona com decodificação restrita (Ollama `format`), mas um erro no meio invalida a resposta inteira, a não ser que se use `json_repair`. O Qwen2.5 é anunciado como melhor em "generating structured outputs especially JSON" ([blog Qwen2.5](https://qwenlm.github.io/blog/qwen2.5/)) (**só fornecedor**). Tam et al. mostram que "stricter format constraints generally lead to greater performance degradation in reasoning tasks" ([arXiv 2408.02442](https://arxiv.org/abs/2408.02442)) (**misto**: raciocínio, não extração).
- **Recomendação** (**conjectura**): delimitadores, um registro por linha, parser tolerante (ignora linhas inválidas e conta as falhas), temperatura 0. Com Ollama, JSON com schema é uma variante barata de comparar. Como o MLX não restringe a saída, o formato por linhas é o que funciona igual nos dois servidores.

### 5.3 Português

- O Qwen2.5 lista português entre "over 29 languages" e aceita até 128K tokens de contexto ([blog Qwen2.5](https://qwenlm.github.io/blog/qwen2.5/)).
- Única evidência direta em PT que achei: OpenIE em português com LLMs (PROPOR 2024). No PUD100, o LLaMA-2-7B com 5-shot teve F1 léxico 0,1106, o GPT-4 0,2366, o LLaMA-2-70B 0,1770, e um 7B ajustado com LoRA chegou a 0,2372. O melhor foi um sistema neural dedicado (PortNOIE, 0,2905). Os autores concluem que "the LLM size was a considerable factor" ([Cabral, Souza & Claro](https://aclanthology.org/2024.propor-1.13/)). Nível: **misto**. São modelos de 2023 e OpenIE de frase, não extração de KG por chunk. Mostra que extração em PT com 7B genérico é fraca e que exemplos/ajuste pesam muito.
- Baseline sem LLM: o spaCy tem pipelines `pt_core_news_sm/md/lg` com entidades e sintaxe ([spaCy](https://spacy.io/models/pt)), o que permite uma variante "FastGraphRAG em PT" (sintagmas nominais/NER + coocorrência no chunk), na linha do `--method fast` da Microsoft ([methods.md](https://github.com/microsoft/graphrag/blob/main/docs/index/methods.md)). Serve de controle barato para medir quanto o LLM de extração acrescenta (**conjectura**).

---

## 6. Dados para avaliar GraphRAG e esquema de CSV

### 6.1 Tipos de pergunta e datasets

| Dataset | Tipos | Colunas relevantes (verificadas) |
|---|---|---|
| HotpotQA ([HF](https://huggingface.co/datasets/hotpotqa/hotpot_qa)) | `bridge`, `comparison`; `level` easy/medium/hard | `question, answer, type, level, supporting_facts{title, sent_id}, context` |
| 2WikiMultiHopQA ([repo](https://github.com/Alab-NII/2wikimultihop)) | `comparison, inference, compositional, bridge_comparison` | `supporting_facts`, `evidences` = triplas `[sujeito, relação, objeto]`, `entity_ids` |
| MuSiQue ([repo](https://github.com/StonyBrookNLP/musique)) | 2–4 saltos; com e sem resposta | `question_decomposition[{question, answer, paragraph_support_idx}]`, `paragraphs[is_supporting]`, `answer_aliases`, `answerable` |
| MultiHop-RAG, COLM 2024 ([repo](https://github.com/yixuantt/MultiHop-RAG)) | 2.556 perguntas: `comparison_query` 856, `inference_query` 816, `temporal_query` 583, `null_query` 301 (contei no JSON) | `query, answer, question_type, evidence_list[{fact, title, source, published_at, url}]` |
| GraphRAG-Bench ([HF](https://huggingface.co/datasets/GraphRAG-Bench/GraphRAG-Bench)) | Novel: `Fact Retrieval` 971, `Complex Reasoning` 610, `Contextual Summarize` 362, `Creative Generation` 67 (contei) | `id, source, question, answer, question_type, evidence[], evidence_triple[]` |
| UltraDomain / GraphRAG (perguntas globais) | sensemaking, geradas por LLM: 5 personas × 5 tarefas × 5 perguntas = 125 ([Edge et al.](https://arxiv.org/abs/2404.16130); [LightRAG](https://arxiv.org/abs/2410.05779)) | só a pergunta: **não há resposta de referência** |

**Perguntas globais** são avaliadas por juiz LLM em comparação pareada: *comprehensiveness, diversity, empowerment* (+ *directness* como controle no GraphRAG; *overall* no LightRAG) ([Edge et al.](https://arxiv.org/abs/2404.16130); [LightRAG](https://arxiv.org/abs/2410.05779)). A versão revista do GraphRAG adiciona uma checagem por *claims* (extraídas com Claimify e agrupadas por 1−ROUGE-L), que concorda com o juiz em 78% das comparações de abrangência ([arXiv 2404.16130v2](https://arxiv.org/html/2404.16130v2)). Han et al. mostram viés de posição nesse protocolo: é preciso avaliar nas duas ordens ([arXiv 2502.11371](https://arxiv.org/abs/2502.11371)).

### 6.2 Esquema de CSV proposto (compatível)

O loader atual (`backend/app/experiments/csv_loader.py`) usa `csv.DictReader`, exige só `pergunta` e já aceita **várias evidências** em `evidencia_referencia` separadas por `|`. Colunas extras são ignoradas. A proposta só **acrescenta** colunas opcionais:

| Coluna | Obrigatória | Conteúdo | Inspiração |
|---|---|---|---|
| `pergunta` | sim | como hoje | — |
| `resposta_referencia` | não | como hoje; **vazia** em `global` | — |
| `evidencia_referencia` | não | trechos literais separados por `\|`, **na ordem dos saltos** | `supporting_facts` |
| `tipo` | não (padrão `simples`) | `simples \| ponte \| comparacao \| agregacao \| global \| sem_resposta` | HotpotQA `type`, MultiHop-RAG `question_type`, GraphRAG-Bench |
| `n_saltos` | não (padrão 1) | inteiro = número de trechos distintos necessários | MuSiQue |
| `evidencia_salto` | não | índice do salto de cada trecho de `evidencia_referencia`, separado por `\|` (ex.: `1\|2`; trechos alternativos do mesmo salto repetem o número) | MuSiQue `paragraph_support_idx` |
| `entidades_ponte` | não | entidades que ligam os saltos, separadas por `\|` | 2Wiki `evidences`, GraphRAG-Bench `evidence_triple` |
| `subperguntas` | não | decomposição separada por `\|` | MuSiQue `question_decomposition` |

Exemplos sobre `guia_santo_antonio_da_alegria.md` (trechos copiados da base):

```csv
pergunta,resposta_referencia,evidencia_referencia,tipo,n_saltos,evidencia_salto,entidades_ponte
Em que mês acontece o evento de carros antigos do parque que fica na Rua Vicentino B. dos Santos?,Em outubro.,"Fica na principal entrada da cidade, na Rua Vicentino B. dos Santos, s/n|O Encontro de Carros Antigos de Santo Antônio da Alegria acontece em outubro",ponte,2,1|2,Parque Ecológico Municipal José Jorge Felício
Qual é mais alto: o cume do Morro da Santa Cruz ou a Ilha do Ar?,"A Ilha do Ar, a 1.100 m; o cume do Morro da Santa Cruz está a 970 m.",o cume está a 970 metros de altitude|A Ilha do Ar fica a 1.100 metros de altitude,comparacao,2,1|2,Morro da Santa Cruz|Ilha do Ar
Que perfil de turista Santo Antônio da Alegria atende melhor?,,,global,,,
```

**Cuidado específico desta base** (fato, verificado no arquivo): por ser FAQ redundante, muitas perguntas "multi-hop" têm **atalho de um chunk**. A linha 37 lista as altitudes de vários morros juntas, e a seção do Parque já cita o Encontro de Carros Antigos (só o mês fica na outra seção). Ao escrever as perguntas, é preciso checar se um único trecho responde e, se responder, marcar como `simples`. Senão o GraphRAG é avaliado em perguntas que o vetorial resolve de graça.

### 6.3 Que métricas do Ditto servem

| Métrica | `simples` | `ponte`/`comparacao`/`agregacao` | `global` |
|---|---|---|---|
| chrF, token F1, ROUGE-L | sim | sim (resposta curta) | **não**: sem referência única; premia parecer com um texto arbitrário |
| `answer_correctness` (cosseno com a referência) | sim | sim, mas pouco sensível a uma metade errada | **não** |
| `context_hit` (algum trecho achado) | sim | **enganosa**: acerta com um salto só | não se aplica |
| `context_recall_gold` (fração dos trechos achados) | sim | **sim, é a principal** | não se aplica |
| nova `context_all_hops` (1 se todos os saltos têm ≥ 1 trecho achado) | = hit | **recomendada**, no espírito do *supporting facts* do HotpotQA | — |
| juiz LLM pareado (abrangência, diversidade, empoderamento) com troca de ordem | — | — | **única opção da literatura**; entra em conflito com a linha "sem LLM" da [nota de 2026-09-24](2026-09-24-avaliacao-rag-sem-llm.md) |

Para `global`, a alternativa sem juiz é uma lista de **claims de referência** por pergunta (anotada à mão) com recall de claims por alinhamento difuso, como o `evidence_found_in` atual. É uma adaptação, não um protocolo publicado (**conjectura**). A dificuldade IRT continua valendo, mas deve ser estimada **por tipo**, ou ter `tipo` como covariável, porque misturar tipos muda a escala (**conjectura**).

---

## 7. Recomendação para o Ditto

### 7.1 Arquitetura mínima viável (`rag = "graph"`)

1. **Extração por chunk** do Índice, com LLM local fixo (Qwen2.5-7B-Instruct-4bit no MLX), prompt em PT-BR no formato de delimitadores do LightRAG, 1–2 exemplos de outra base, temperatura 0, **sem gleaning**. Cache por hash do chunk + LLM + versão do prompt. Contagem de falhas de parse no resultado do experimento.
2. **Consolidação** sem LLM: nome normalizado + aliases; arestas de sinonímia por cosseno ≥ 0,8 (sem fundir nós); descrições concatenadas; peso de especificidade 1/|chunks| por entidade (derruba o hub "Santo Antônio da Alegria").
3. **Armazenamento**: `kg_ent__*` e `kg_rel__*` no Qdrant, com `chunk_ids` no payload; `networkx.Graph` montado na carga.
4. **Consulta sem LLM até a geração**: embedding da pergunta → top-k entidades e relações → vizinhos de 1 salto → nota por chunk → top-k chunks → mesmo prompt de resposta do `naive` + bloco curto de fatos. `contexts` = chunks.
5. **Variantes no registry** (cada uma é uma linha na matriz): `graph_ppr` (PPR no lugar de 1 salto), `graph_mix` (união com o retriever vetorial), `graph_kw` (palavras-chave dual do LightRAG), `graph_nlp` (extração por spaCy + coocorrência, sem LLM).

O que fica de fora e por quê: comunidades/busca global (custo de LLM por relatório; base pequena cabe no contexto), resumos por LLM (pior com modelos pequenos), filtro de triplas por LLM do HippoRAG 2 (mais uma chamada por pergunta).

### 7.2 Esforço e risco (estimativas, **conjectura**)

- **Perguntas novas** (20–40 entre ponte, comparação, agregação e global, com checagem de atalho): 1–2 dias de anotação. Esse é o pré-requisito.
- **Métrica `context_all_hops` + colunas no loader/DB**: ~1 dia.
- **Extração + parser + consolidação + testes com LLM falso**: 3–4 dias.
- **Collections no Qdrant + carga em networkx + RAG no registry**: 2–3 dias.
- **Variantes PPR/mix**: ~1 dia cada.
- **Custo de indexação**: o recursive (1000 caracteres) gera ~55–65 chunks nesta base. Com ~1,5–2k tokens de prompt e ~300–500 de saída por chamada, e a vazão medida nesta máquina (8–35 tok/s, [nota de 2026-09-23](2026-09-23-inferencia-small-llms.md)), a extração deve levar de 15 a 60 min por chunking × LLM de extração. É viável, mas o cache por chunk é obrigatório.

**Riscos.** (1) Extração ruim em PT com 7B 4-bit: medir primeiro numa amostra de 10 seções anotadas à mão (precisão/recall de entidades) antes de rodar a matriz. (2) Resultado esperado em perguntas `simples`: empate ou derrota do grafo, o que a literatura já prevê e não deve ser lido como bug. (3) Confusão de variáveis: o grafo depende do LLM de extração. Ele precisa ser fixo, ou virar eixo explícito, e não pode ser o mesmo eixo do LLM de resposta. (4) qwen3:1.7b como extrator: a evidência do MiniRAG sugere evitar. Use-o só na geração.

---

## 8. O que não consegui verificar

- **Qual modelo construiu o índice no MiniRAG**: o artigo não diz com clareza. Os números de SLM podem valer só para a consulta.
- **Venue do LightRAG, do KAG e do G-Retriever**: citei como arXiv. Não confirmei os anais.
- **O LightRAG com 16,6 F1 no NQ** (tabela do HippoRAG 2): não sei se é configuração ou o método.
- **Extração de KG por LLMs de 7B em português, no nível de chunk**: não achei estudo. O único dado é OpenIE de frase com modelos de 2023 (PROPOR 2024).
- **LazyGraphRAG**: só há o post da Microsoft, sem artigo revisado.
- **Throughput do mlx-lm com o prompt de extração**: as estimativas de tempo da seção 7.2 são extrapoladas, não medidas.
- **GraphRAG-Bench de Xiao et al.**: li só o resumo.
- Não li os PDFs completos de KAG, G-Retriever, KGGen e Triplex. As afirmações sobre eles vêm do resumo ou do card.

---

## 9. Referências

Artigos:
- Edge et al. *From Local to Global: A Graph RAG Approach to Query-Focused Summarization.* 2024. https://arxiv.org/abs/2404.16130
- Guo et al. *LightRAG: Simple and Fast Retrieval-Augmented Generation.* 2024. https://arxiv.org/abs/2410.05779
- Gutiérrez et al. *HippoRAG: Neurobiologically Inspired Long-Term Memory for Large Language Models.* NeurIPS 2024. https://arxiv.org/abs/2405.14831
- Gutiérrez et al. *From RAG to Memory: Non-Parametric Continual Learning for Large Language Models* (HippoRAG 2). ICML 2025. https://arxiv.org/abs/2502.14802
- Liang et al. *KAG: Boosting LLMs in Professional Domains via Knowledge Augmented Generation.* https://arxiv.org/abs/2409.13731
- He et al. *G-Retriever: Retrieval-Augmented Generation for Textual Graph Understanding and Question Answering.* https://arxiv.org/abs/2402.07630
- Fan et al. *MiniRAG: Towards Extremely Simple Retrieval-Augmented Generation.* https://arxiv.org/abs/2501.06713
- Peng et al. *Graph Retrieval-Augmented Generation: A Survey.* 2024. https://arxiv.org/abs/2408.08921
- Han et al. *Retrieval-Augmented Generation with Graphs (GraphRAG).* 2025. https://arxiv.org/abs/2501.00309
- Han et al. *RAG vs. GraphRAG: A Systematic Evaluation and Key Insights.* 2025. https://arxiv.org/abs/2502.11371
- Xiang et al. *When to use Graphs in RAG: A Comprehensive Analysis for Graph Retrieval-Augmented Generation* (GraphRAG-Bench). 2025. https://arxiv.org/abs/2506.05690
- Xiao et al. *GraphRAG-Bench: Challenging Domain-Specific Reasoning for Evaluating Graph Retrieval-Augmented Generation.* 2025. https://arxiv.org/abs/2506.02404
- Tang & Yang. *MultiHop-RAG: Benchmarking Retrieval-Augmented Generation for Multi-Hop Queries.* COLM 2024. https://github.com/yixuantt/MultiHop-RAG
- Mo et al. *KGGen: Extracting Knowledge Graphs from Plain Text with Language Models.* https://arxiv.org/abs/2502.09956
- Komarov et al. *RAGU: A Multi-Step GraphRAG Engine with a Compact Domain-Adapted LLM.* 2026. https://arxiv.org/abs/2607.11683
- Anuyah et al. *Automated Knowledge Graph Construction using Large Language Models and Sentence Complexity Modelling* (CoDe-KG). EMNLP 2025. https://arxiv.org/abs/2509.17289
- Tam et al. *Let Me Speak Freely? A Study on the Impact of Format Restrictions on Performance of Large Language Models.* https://arxiv.org/abs/2408.02442
- Cabral, Souza & Claro. *Exploring Open Information Extraction for Portuguese Using Large Language Models.* PROPOR 2024. https://aclanthology.org/2024.propor-1.13/

Código, documentação e datasets:
- microsoft/graphrag: prompt de extração (https://github.com/microsoft/graphrag/blob/main/packages/graphrag/graphrag/prompts/index/extract_graph.py), métodos de indexação (https://github.com/microsoft/graphrag/blob/main/docs/index/methods.md), docs (https://microsoft.github.io/graphrag/)
- Microsoft Research. *LazyGraphRAG: Setting a new standard for quality and cost.* nov/2024. https://www.microsoft.com/en-us/research/blog/lazygraphrag-setting-a-new-standard-for-quality-and-cost/
- HKUDS/LightRAG: `prompt.py`, `operate.py`, `constants.py`, README. https://github.com/HKUDS/LightRAG
- OSU-NLP-Group/HippoRAG: templates de NER/OpenIE. https://github.com/OSU-NLP-Group/HippoRAG
- LangGraph overview e Graph API. https://docs.langchain.com/oss/python/langgraph/overview · https://docs.langchain.com/oss/python/langgraph/graph-api
- `LLMGraphTransformer` (langchain-experimental). https://github.com/langchain-ai/langchain-experimental/blob/main/libs/experimental/langchain_experimental/graph_transformers/llm.py
- langchain-neo4j. https://github.com/langchain-ai/langchain-neo4j
- `NetworkxEntityGraph`, `GraphQAChain` (langchain-community). https://github.com/langchain-ai/langchain-community
- mlx-lm server. https://github.com/ml-explore/mlx-lm/blob/main/mlx_lm/server.py
- Ollama, *Structured outputs.* https://docs.ollama.com/capabilities/structured-outputs
- NetworkX, `pagerank`. https://networkx.org/documentation/stable/reference/algorithms/generated/networkx.algorithms.link_analysis.pagerank_alg.pagerank.html
- spaCy, pipelines em português. https://spacy.io/models/pt
- Qwen Team, *Qwen2.5: A Party of Foundation Models.* https://qwenlm.github.io/blog/qwen2.5/
- SciPhi, *Triplex* (model card). https://huggingface.co/SciPhi/Triplex
- Datasets: HotpotQA (https://huggingface.co/datasets/hotpotqa/hotpot_qa), 2WikiMultihopQA (https://github.com/Alab-NII/2wikimultihop), MuSiQue (https://github.com/StonyBrookNLP/musique), GraphRAG-Bench (https://huggingface.co/datasets/GraphRAG-Bench/GraphRAG-Bench)
