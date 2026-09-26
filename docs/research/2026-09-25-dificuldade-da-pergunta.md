# Dificuldade da pergunta como explicação da resposta ruim: o que a literatura já tem e o que sobra para o Ditto

Pesquisa feita em 2026-09-25. As afirmações sobre trabalhos vêm das páginas de abstract/HTML no arXiv, ACL Anthology, OpenReview/SBC OpenLib, dos READMEs dos repositórios e dos dataset cards no Hugging Face. Cada afirmação tem link para a sua fonte. O que não consegui abrir está marcado como **não verificado** e listado no fim. Nenhum modelo foi executado e nenhum código foi alterado. **Revisão no mesmo dia:** uma busca dirigida a small models (≈≤8B, quantizados) acrescentou a seção 3.7, revisou as seções 1, 4 e 6 e criou a seção 5.5 (ganho real de cada processo para o Ditto).

Pergunta original: *existe trabalho que tenta entender a complexidade da pergunta feita a um LLM (ou small model) e relacioná-la à saída, isto é, dizer que a resposta foi ruim porque a pergunta era difícil para aquele modelo? Se não existir, é oportunidade para o Ditto e para a comunidade?*

---

## 1. Resumo e veredito

**A lacuna genérica não existe.** "Dificuldade da pergunta" é um tema bem estudado, em cinco frentes independentes, e há trabalhos recentes que aplicam cada uma delas a RAG:

| Frente | O que já faz | Trabalho mais próximo do Ditto |
|---|---|---|
| Teoria de Resposta ao Item (IRT) | estima dificuldade por pergunta e habilidade por "respondente" | **Guinet et al., ICML 2024**: IRT 3PL hierárquico onde os respondentes são **45 configurações RAG** e a habilidade é decomposta em θ_llm + θ_ret + θ_icl ([arXiv 2405.13622](https://arxiv.org/abs/2405.13622)) |
| Features a priori de dificuldade | explica o erro por propriedades da pergunta | **GRADE, Findings EMNLP 2025**: matriz 2D *hops* × distância semântica pergunta↔evidência; "error rates strongly correlate with our difficulty measures" ([arXiv 2508.16994](https://arxiv.org/abs/2508.16994)) |
| IRT com escores contínuos em RAG | dificuldade por pergunta a partir de notas não binárias | **LiveRAG, SIGIR 2025**: IRT 2PL com Bernoulli contínua via `py-irt`; perguntas semanticamente distantes dos documentos e de resposta concisa são mais difíceis ([arXiv 2511.14531](https://arxiv.org/abs/2511.14531)) |
| Predição de desempenho (QPP → RAG) | prevê a qualidade da resposta por pergunta antes/depois de recuperar | Tian, Ganguly & Macdonald, **ECIR 2026** ([arXiv 2601.14546](https://arxiv.org/abs/2601.14546)); DRAG, set/2026 ([arXiv 2609.17709](https://arxiv.org/abs/2609.17709)) |
| Roteamento por complexidade / modelo pequeno × grande | decide por pergunta se basta o modelo pequeno ou sem recuperação | Adaptive-RAG (NAACL 2024), Hybrid LLM (ICLR 2024), RADAR (ICLR 2026, usa IRT) |
| Atribuição do erro (recuperação × geração) | separa "não recuperou" de "recuperou e não usou" | Sufficient Context (ICLR 2025), RAGChecker, Seven Failure Points |
| Modelos pequenos em RAG, por tamanho (seção 3.7, busca dirigida) | mede, numa escada de tamanhos, se o modelo pequeno usa o contexto e onde quebra | **Pandey 2026** (preprint): Qwen2.5 1,5/3/7B em 4 bits, oráculo, split sabida/não sabida por pergunta ([arXiv 2603.11513](https://arxiv.org/abs/2603.11513)); **PRGB 2025**: tipo de tarefa × tamanho, só ≥7B ([arXiv 2507.22927](https://arxiv.org/abs/2507.22927)); **Baturova et al., ECML PKDD 2026**: 17 SLMs quantizados de 1,5 a 8B, incluindo Qwen3 1,7/4/8B, perguntas em russo rotuladas por tipo, mas resultados só agregados ([arXiv 2606.30062](https://arxiv.org/abs/2606.30062)) |

**Busca dirigida a small models (seção 3.7).** Ela encontrou mais precedentes do que a primeira busca. Três pontos mudam o quadro: (i) já existe estudo com **escada de tamanhos na mesma família** (Qwen2.5 1,5B→7B, 4 bits) que separa por pergunta "o modelo já sabia" de "precisava do contexto" e mostra que, com o contexto correto, modelos ≤7B erram 85–100% das perguntas que não sabiam, e que o contexto **destrói** de 42 a 100% das respostas que o modelo sabia (Pandey 2026, preprint, métrica EM); (ii) a interação **tipo de tarefa × tamanho** em RAG já foi medida (PRGB), mas de 7B para cima e com juiz GPT-4o; (iii) features **a priori** de demanda por item × tamanho do modelo já explicam desempenho por instância fora de RAG (ADeLe, [arXiv 2503.06378](https://arxiv.org/abs/2503.06378)), com rótulos feitos por GPT-4o. **A lacuna encolhe**: "interação pergunta × tamanho com small models" deixou de ser inédita como tal. O que continua sem precedente é a combinação com o fatorial de configurações, features a priori sem LLM, resposta aberta sem juiz e PT-BR.

**A lacuna que sobra é estreita, mas real.** Não encontrei nenhum trabalho que junte, no mesmo modelo estatístico:
1. um **desenho fatorial completo** de configurações RAG (chunking × embedding × técnica × retriever × LLM), como o Ditto roda;
2. **covariáveis a priori da pergunta** (evidências, distância pergunta↔evidência, tipo de resposta) no lado do item;
3. a **interação pergunta × tamanho do LLM**, com modelos locais pequenos e quantizados (1,7–7B), **explicada por features da pergunta** (e não só por dataset ou por "sabia/não sabia");
4. respostas **abertas** com métricas contínuas **sem LLM-juiz**;
5. dados em **português**.

Guinet et al. têm (1) parcial e decompõem a habilidade, mas usam múltipla escolha, inglês, e o único atributo de item é a taxonomia de Bloom. O LiveRAG tem dificuldade contínua e categorias de pergunta, mas os respondentes são sistemas opacos de equipes, sem fatorial. O GRADE tem as features, mas não tem IRT nem decomposição por componente. Sobre o item (3), Pandey 2026 tem a escada de tamanhos e o recorte por pergunta, mas só com dois "tipos" (NQ single-hop × HotpotQA multi-hop, que é o dataset e não uma feature), um único pipeline de recuperação por condição e EM como métrica. O PRGB tem tipo de tarefa × tamanho, mas não abaixo de 7B. O Baturova et al. tem a escada do qwen3 que o Ditto usa e perguntas rotuladas por tipo, mas não cruza tipo × tamanho nos resultados. Em português, o que existe de IRT com LLMs é sobre o ENEM (múltipla escolha, sem recuperação). Não achei trabalho de dificuldade de pergunta em RAG em PT-BR (ausência de evidência, não prova; seção 7).

**Recomendação:**
- **Para o Ditto: sim, vale fazer**, como camada de análise, e não como técnica plugável. Custa pouco, porque os dados já existem: o export CSV tem uma linha por (configuração, pergunta) com todas as métricas, e a `evidencia_referencia` já dá as features de recuperação. Com as 15 perguntas atuais, porém, só dá para fazer análise **descritiva**. Modelos com efeito aleatório de pergunta ou IRT pedem de 50 a 100 perguntas desenhadas para variar as features (seção 5.4). A seção 5.5 pesa cada processo pelo ganho real: o de maior retorno é a decomposição do erro por `context_hit` × LLM, junto com duas condições de controle que o Ditto ainda não tem (sem recuperação e com contexto oráculo), porque é isso que separa "o retriever falhou" de "o modelo pequeno não usou a evidência" (o gargalo que Pandey 2026 relata em ≤7B). A escada qwen3 1,7/4/8B vem em segundo. IRT/GLMM só compensa depois de ampliar as perguntas.
- **Para a comunidade:** a contribuição publicável é "IRT explicativo / modelo misto sobre um fatorial de RAG com small models em PT-BR", com as features do GRADE/LiveRAG como covariáveis de item e a decomposição de Guinet no lado do respondente. É incremental, e não um campo novo. Os concorrentes diretos são Guinet 2024, LiveRAG 2025 e GRADE 2025, e, no recorte de small models, Pandey 2026, PRGB 2025 e Baturova et al. 2026. O texto precisa citá-los logo na introdução. O risco principal é a validade das métricas: a dificuldade estimada herda o viés das métricas de cosseno (seção 6).

---

## 2. O que "a pergunta era difícil" pode significar (e por que importa separar)

A frase mistura três coisas que a literatura trata em separado:

1. **Dificuldade intrínseca (a priori):** propriedades da pergunta e do corpus que existem antes de rodar qualquer modelo. Exemplos: número de evidências, número de *hops*, distância léxica/semântica entre pergunta e evidência, pedido de lista ou agregação, ambiguidade. É o que a QPP pré-recuperação e as features do GRADE medem.
2. **Dificuldade empírica (a posteriori, relativa a uma população de sistemas):** quanto os sistemas erram naquela pergunta. É o parâmetro *b* da IRT, ou simplesmente a média de acerto (o "índice de facilidade" da teoria clássica dos testes).
3. **Dificuldade relativa a um modelo:** a pergunta é difícil **para este** modelo. Ethayarajh et al. formalizam isso com a *pointwise V-information* (PVI), uma dificuldade por instância definida em relação a uma família de modelos V ([arXiv 2110.08420](https://arxiv.org/abs/2110.08420), ICML 2022, Outstanding Paper).

"A resposta foi ruim porque a pergunta era difícil **para um small model**" é uma afirmação do tipo 3, e estatisticamente é uma **interação pergunta × modelo**. Ela só se sustenta se: (a) a recuperação trouxe a evidência (senão o culpado é o retriever); (b) modelos maiores acertam a mesma pergunta com o mesmo contexto; (c) a pergunta tem uma propriedade a priori que explica o padrão. A seção 5 mostra como o Ditto consegue medir (a) e (b) com o que já tem.

---

## 3. Mapa da literatura

### 3.1 Predição de desempenho de consulta (QPP), da RI clássica ao RAG

**Clássicos.** O *clarity score* de Cronen-Townsend, Zhou & Croft (SIGIR 2002) mede a divergência KL entre o modelo de linguagem da consulta e o da coleção e correlaciona com a precisão média em coleções TREC ([ACM DOI 10.1145/564376.564429](https://dl.acm.org/doi/10.1145/564376.564429); **a página da ACM devolveu 403**, então a descrição vem do índice de busca e da [cópia no CIIR/UMass](https://ciir-publications.cs.umass.edu/getpdf.php?id=250), que não abri). O NQC (*Normalized Query Commitment*), de Shtok, Kurland, Carmel et al. (TOIS 2012), é um preditor **pós-recuperação** baseado na dispersão dos escores do ranking ([ACM DOI 10.1145/2180868.2180873](https://dl.acm.org/doi/10.1145/2180868.2180873), também só pelo índice de busca). Em comum: tudo mede se a **recuperação** vai dar certo, não se a **resposta** vai.

**QPP para perguntas multi-hop.** O multHP é um preditor pré-recuperação para QA de domínio aberto multi-hop, e os autores dizem que ele supera preditores single-hop ([arXiv 2308.06431](https://arxiv.org/abs/2308.06431), Samadi & Rafiei).

**QPP com LLM.** O QPP-GenRE decompõe a QPP em julgamentos de relevância item a item, gerados por LLM aberto ajustado ([arXiv 2404.01012](https://arxiv.org/abs/2404.01012), Meng et al., TOIS).

**QPP → qualidade da resposta em RAG (o mais próximo desta frente).**
- Tian, Ganguly & Macdonald definem **RPP** (utilidade dos documentos recuperados) e **GPP** (qualidade da resposta final). Usam regressão linear com preditores de QPP, a perplexidade do LLM sobre o contexto dada a pergunta (*reader-centric*) e qualidade/legibilidade do documento. Concluem que "combining predictors from multiple feature categories yields the most accurate estimates of RAG performance". Dados: Natural Questions ([arXiv 2601.14546](https://arxiv.org/abs/2601.14546), ECIR 2026).
- Os mesmos autores mostram relação positiva entre QPP e qualidade da resposta em RAG agêntico (Search-R1, R1-Searcher) ([arXiv 2507.10411](https://arxiv.org/abs/2507.10411)).
- **DRAG** (Anand et al., submetido em 2026-09-15) escolhe retriever **e** gerador por pergunta. A variante sem treino usa Avg-IDF (QPP pré-recuperação) para o retriever e perplexidade sobre o contexto para o gerador. Geradores: GPT-OSS 20B, Qwen-3 8B, Gemma-4 26B; dados: TriviaQA, HotpotQA, MuSiQue, FRAMES ([arXiv 2609.17709](https://arxiv.org/abs/2609.17709), [HTML](https://arxiv.org/html/2609.17709)).

**Leitura para o Ditto:** a QPP responde "esta pergunta vai dar resposta ruim?". Não responde "**por que**, e qual componente da configuração pesa mais". O DRAG é o que chega mais perto de "configuração por pergunta", mas é um roteador, não uma análise explicativa, e trabalha com modelos de 8–26B, em inglês.

### 3.2 IRT: dificuldade por item e habilidade por sistema

**Base em NLP.**
- Lalor, Wu & Yu (EMNLP 2016) constroem escalas de avaliação com IRT ([D16-1062](https://aclanthology.org/D16-1062/)).
- Rodriguez et al. (ACL 2021) propõem leaderboards bayesianos com IRT. Entre os usos listados estão priorizar anotação, **achar erros de rótulo** e destacar os itens que realmente discriminam os modelos ([2021.acl-long.346](https://aclanthology.org/2021.acl-long.346/)).
- Vania et al. (ACL 2021) comparam 29 datasets com 18 Transformers via IRT e mostram quais ainda discriminam modelos fortes ([2021.acl-long.92](https://aclanthology.org/2021.acl-long.92/)).
- tinyBenchmarks (ICML 2024): "100 curated examples" bastam para estimar o desempenho de um LLM no MMLU ([arXiv 2402.14992](https://arxiv.org/abs/2402.14992)).
- Easy2Hard-Bench (NeurIPS 2024 D&B) atribui dificuldade numérica por problema com IRT e Glicko-2 ([arXiv 2409.18433](https://arxiv.org/abs/2409.18433)).
- **Escores contínuos:** o LEGO-IRT aceita métricas binárias e contínuas e decompõe a habilidade em geral + específica por métrica/benchmark ([arXiv 2510.04051](https://arxiv.org/abs/2510.04051)). O IRSL usa Beta-IRT com probabilidades empíricas em 6.612 checkpoints e 37.682 questões, com modelos de 4M a 1B de parâmetros na parte de pré-treino (segundo o abstract, [arXiv 2606.07616](https://arxiv.org/abs/2606.07616)). Esse é o trabalho de IRT que olha para **modelos pequenos por item** com mais escala.
- Software: `py-irt` (MIT; Pyro/PyTorch; 1PL, 2PL e 4PL; 3PL "in the pipeline"; priors vagos ou hierárquicos) ([GitHub](https://github.com/nd-ball/py-irt)).

**IRT aplicada a RAG (os concorrentes diretos).**
- **Guinet, Omidvar-Tehrani, Deoras & Callot, ICML 2024** ([arXiv 2405.13622](https://arxiv.org/abs/2405.13622), [HTML](https://arxiv.org/html/2405.13622)). Geram provas de múltipla escolha a partir do corpus da tarefa e usam IRT 3PL para medir a qualidade da prova. A variante **hierárquica** decompõe a habilidade do sistema em θ_m = θ_llm + θ_ret + θ_icl. São 45 configurações: 7 mecanismos de recuperação (inclui closed-book e oracle), 3 LLMs (Mistral-7B, Llama-2-13B e -70B) e 3 modos de ICL, em 4 tarefas (AWS DevOps, arXiv, StackExchange, SEC), com provas de 148 a 515 questões. As questões são classificadas pela taxonomia de Bloom, e "remembering is the least discriminatory". O código está em [amazon-science/auto-rag-eval](https://github.com/amazon-science/auto-rag-eval) (Apache-2.0), com `ExamAnalysis/item_response_models.py`, `iterative_item_response_models.py` e `bloom_taxonomy_model.py` ([pasta](https://github.com/amazon-science/auto-rag-eval/tree/main/auto-rag-eval/ExamAnalysis)). **É o trabalho mais parecido com o Ditto.** As diferenças: múltipla escolha (resposta binária, com parâmetro de chute), inglês, sem eixos de chunking/técnica RAG, e sem features de item além de Bloom.
- **LiveRAG (Carmel et al., SIGIR 2025 LiveRAG Challenge)** ([arXiv 2511.14531](https://arxiv.org/abs/2511.14531), [HTML](https://arxiv.org/html/2511.14531)). São 895 perguntas sintéticas com dificuldade e discriminação por IRT 2PL, ajustado sobre as notas das equipes do desafio. Eles modificaram o `py-irt` para aceitar observações contínuas com a distribuição Continuous-Bernoulli. Achados por categoria: comparação e multi-aspecto são as mais difíceis; "questions which are semantically similar to their documents are easier than those that are dissimilar"; "concise-answer questions are relatively more difficult for instruction-tuned LLMs". **É o precedente direto para IRT contínua sobre métricas de RAG.** O número de equipes usadas no ajuste não aparece no texto que consegui ler.

**IRT para roteamento.** O RADAR (ICLR 2026) ajusta um modelo de resposta ao item com dificuldade por pergunta e habilidade por par (modelo, orçamento de raciocínio) e usa isso para rotear ([arXiv 2509.25426](https://arxiv.org/abs/2509.25426)).

**Modelos mistos como alternativa à IRT.** O NIST AI 800-3 (fev/2026) defende modelos lineares generalizados mistos (GLMM) na avaliação de IA e afirma que eles quantificam a incerteza com mais precisão que as técnicas atuais e fornecem "variance decomposition and item difficulty estimates". O exemplo usa 22 LLMs em GPQA-Diamond, BBH e Global-MMLU Lite ([página NIST](https://www.nist.gov/publications/expanding-ai-evaluation-toolbox-statistical-models), [DOI 10.6028/NIST.AI.800-3](https://doi.org/10.6028/NIST.AI.800-3); só li o resumo, não o relatório).

### 3.3 Complexidade da pergunta para decidir recuperar ou escalar de modelo

- **Adaptive-RAG** (Jeong et al., NAACL 2024): um classificador **T5-Large** prevê a classe de complexidade A (sem recuperação), B (um passo) ou C (multi-passo). Os rótulos vêm de qual estratégia mais simples acertou e, na falta disso, do viés do dataset (single-hop → B, multi-hop → C). Acurácia por classe: 54,5% (A), 66,3% (B), 65,5% (C) ([arXiv 2403.14403](https://arxiv.org/abs/2403.14403), [HTML](https://arxiv.org/html/2403.14403)). **Observação importante: a "complexidade" aqui é definida pelo resultado dos próprios modelos, não por uma propriedade independente da pergunta.**
- **Self-RAG** (Asai et al.): tokens de reflexão para decidir quando recuperar e criticar a própria saída ([arXiv 2310.11511](https://arxiv.org/abs/2310.11511)).
- **SKR** (Wang et al.): o modelo usa o autoconhecimento para decidir se recupera. Parte da constatação de que o conhecimento recuperado "does not always help and even has a negative impact" ([arXiv 2310.05002](https://arxiv.org/abs/2310.05002)).
- **Mallen et al., ACL 2023** (PopQA): LMs vão mal em fatos pouco populares, "scaling fails to appreciably improve memorization of factual knowledge in the long tail", e LMs com recuperação superam LMs ordens de grandeza maiores ([arXiv 2212.10511](https://arxiv.org/abs/2212.10511)). **Kandpal et al., ICML 2023**: a acurácia depende de quantos documentos relacionados à pergunta o modelo viu no pré-treino ([arXiv 2211.08411](https://arxiv.org/abs/2211.08411)). Esses dois trabalhos fazem da **popularidade da entidade** uma feature a priori de dificuldade no modo closed-book. No Ditto, uma cidade pequena do interior de SP é cauda longa por construção, então o modelo depende quase só do contexto.
- **Modelo pequeno × grande:** o Hybrid LLM (Ding et al., ICLR 2024) roteia "based on the predicted query difficulty" e reduz em até 40% as chamadas ao modelo grande sem perder qualidade ([arXiv 2404.14618](https://arxiv.org/abs/2404.14618)). O RouteLLM (Ong et al.) aprende roteadores com dados de preferência e relata que eles funcionam mesmo trocando os modelos no teste ([arXiv 2406.18665](https://arxiv.org/abs/2406.18665)). O FrugalGPT (Chen, Zaharia & Zou) usa cascata de LLMs ([arXiv 2305.05176](https://arxiv.org/abs/2305.05176)). **Todos esses trabalhos estimam implicitamente "esta pergunta é difícil demais para o modelo pequeno"**, mas como preditor caixa-preta para decidir, não como variável explicativa reportada.

### 3.4 Atribuição do erro em RAG

- **Seven Failure Points** (Barnett et al., 2024): FP1 conteúdo ausente, FP2 não ranqueou no topo, FP3 não entrou no contexto, **FP4 não extraiu** (a resposta estava no contexto e o LLM não a tirou), FP5 formato errado, FP6 especificidade errada, FP7 incompleta ([arXiv 2401.05856](https://arxiv.org/abs/2401.05856), [HTML](https://arxiv.org/html/2401.05856)). É uma taxonomia qualitativa de três estudos de caso.
- **RGB** (Chen et al., AAAI 2024): quatro habilidades (robustez a ruído, rejeição negativa, integração de informação, robustez contrafactual) ([arXiv 2309.01431](https://arxiv.org/abs/2309.01431)). **CRUD-RAG** (Lyu et al.) é um benchmark chinês que varia retriever, tamanho de contexto, base e LLM ([arXiv 2401.17043](https://arxiv.org/abs/2401.17043)).
- **RAGChecker** (Ru et al.): métricas diagnósticas separadas para o módulo de recuperação e o de geração, validadas contra humanos, em 8 sistemas ([arXiv 2408.08067](https://arxiv.org/abs/2408.08067)). Usa LLM para extrair afirmações.
- **Sufficient Context** (Joren et al., ICLR 2025) é o mais próximo da pergunta do usuário ([arXiv 2411.06037](https://arxiv.org/abs/2411.06037), [HTML](https://arxiv.org/html/2411.06037), [código](https://github.com/hljoren/sufficientcontext)). O trabalho classifica cada instância por "contexto suficiente" (existe uma resposta plausível dada a informação do contexto), com um autorater Gemini 1.5 Pro de 93% de acurácia. Achados: modelos grandes acertam quando o contexto basta, mas respondem errado em vez de se abster quando não basta. Os modelos abertos menores (Mistral-3 7B, Gemma-2 27B) "hallucinate or abstain often, even with sufficient context". E 35–62% dos acertos ocorrem com contexto **insuficiente**, ou seja, vindos do conhecimento paramétrico. **Esse é o recorte "o contexto estava lá e o modelo pequeno não usou".** O que ele não tem: feature a priori da pergunta, decomposição por componente da configuração, e PT.
- **Distratores e posição:** LLMs se distraem com contexto irrelevante (Shi et al., ICML 2023, [arXiv 2302.00093](https://arxiv.org/abs/2302.00093)) e usam mal a informação no meio de contextos longos (Liu et al., TACL, [arXiv 2307.03172](https://arxiv.org/abs/2307.03172)). Nos dois casos a dificuldade depende do **contexto montado pela configuração**, e não só da pergunta. Isso reforça que a dificuldade no Ditto é, em parte, efeito da interação pergunta × configuração.

### 3.5 Features de dificuldade da pergunta e datasets rotulados

- **Sugawara et al., EMNLP 2018**: em 12 datasets de compreensão de leitura, dividem as perguntas em fáceis e difíceis por heurísticas (entre elas a sobreposição léxica pergunta↔passagem) e mostram queda grande nas difíceis, que exigem "knowledge inference and multiple-sentence reasoning" ([D18-1453](https://aclanthology.org/D18-1453/)). **É a referência clássica para usar a sobreposição léxica pergunta↔evidência como feature de dificuldade.**
- **GRADE** (Lee, Kwon & Jin, Findings EMNLP 2025): dificuldade no lado do gerador = número de *hops*; no lado do retriever = D_r(q) = 1 − min_i s(q, c_i), ou seja, a menor similaridade de embedding entre a pergunta e seus chunks de apoio (o chunk mais distante é o gargalo). Geradores: GPT-4o, GPT-4o mini, o1-mini, Claude-4-Sonnet e **Llama 3.2 3B**; notícias em inglês. O artigo não isola o efeito do tamanho do modelo ([arXiv 2508.16994](https://arxiv.org/abs/2508.16994), [HTML](https://arxiv.org/html/2508.16994), [ACL](https://aclanthology.org/2025.findings-emnlp.236.pdf), [código](https://github.com/DaeyongKwon98/GRADE)). **Essa feature é implementável no Ditto com a `evidencia_referencia` e o embedder de avaliação.**
- **MHTS** (mesmo grupo): gera QA multi-hop com dificuldade controlável e uma fórmula de dificuldade que correlaciona com o desempenho do RAG ([arXiv 2504.08756](https://arxiv.org/abs/2504.08756)).
- **Datasets:** o HotpotQA tem o campo `level` (easy/medium/hard) ([dataset card](https://huggingface.co/datasets/hotpotqa/hotpot_qa); artigo em [arXiv 1809.09600](https://arxiv.org/abs/1809.09600), cujo abstract não menciona os níveis, então não verifiquei como foram atribuídos). O MuSiQue tem de 2 a 4 *hops*, com queda de 30 pontos de F1 para modelos single-hop ([arXiv 2108.00573](https://arxiv.org/abs/2108.00573), TACL 2022).
- **Composicionalidade e escala:** Press et al. mostram que, com o aumento do GPT-3, o acerto em perguntas de um fato cresce mais rápido que em perguntas compostas. É o "compositionality gap" ([arXiv 2210.03350](https://arxiv.org/abs/2210.03350), Findings EMNLP 2023). Esse é o resultado mais direto sobre **qual tipo de pergunta** não melhora com a escala.
- **Estimativa de dificuldade a partir do texto (educação):** há um survey na ACM Computing Surveys ([Benedetto et al. 2023, DOI 10.1145/3556538](https://dl.acm.org/doi/10.1145/3556538); não abri o PDF, só o registro), com taxonomia por característica da pergunta.

### 3.6 Português

- **IRT com LLMs no ENEM.** Taschetto & Fileto (STIL 2025, UFSC) ajustam um 3PL quadridimensional alinhado às áreas do ENEM, com calibrações do INEP, e mostram que "similar accuracies can mask proficiency gaps exceeding one standard deviation across domains" ([SBC OpenLib](https://sol.sbc.org.br/index.php/stil/article/view/37846)). Brant, Kühn & Pang testam se LLMs **estimam** a dificuldade de 1.031 itens do ENEM contra os parâmetros oficiais de IRT. Os modelos têm correlação moderada, mas subestimam sistematicamente a dificuldade ([arXiv 2602.06631](https://arxiv.org/abs/2602.06631)). **Consequência para o Ditto: não usar LLM para rotular dificuldade a priori.**
- **RAG com modelos pequenos em PT-BR.** Junqueira, Freitas, Corrêa & Moreira (ERAMIA-RS 2025, UFRGS/UFPel) avaliam o Sabiá-7B quantizado em 4 bits com RAG sobre o Pirá, com ROUGE. Relatam "dificuldades na integração eficaz dos contextos recuperados, particularmente em modelos quantizados" ([SBC OpenLib](https://sol.sbc.org.br/index.php/eramiars/article/view/39409)). Não há análise por pergunta.
- **Dataset PT com textos de apoio:** o Pirá (CIKM 2021) tem 2.261 pares PT/EN com textos de apoio, paráfrases humanas e avaliações humanas ([arXiv 2202.02398](https://arxiv.org/abs/2202.02398), [GitHub](https://github.com/C4AI/Pira)). É um candidato a segundo corpus para o Ditto, com mais perguntas.
- **Não encontrei** trabalho que estime ou explique a dificuldade de pergunta **em RAG** em português (buscas na seção 7).

### 3.7 Modelos pequenos (small language models)

Busca dirigida, feita depois das seções anteriores, a trabalhos com modelos de ≈≤8B (inclusive quantizados) em RAG. O objetivo era checar se alguém já mediu **onde** o modelo pequeno falha, e se isso depende do tipo de pergunta.

**Uso do contexto recuperado em função do tamanho (o mais próximo do Ditto).**
- **Pandey et al., "Can Small Language Models Use What They Retrieve?"** (preprint, mar/2026, "planning to submit to ARR March 2026"; [arXiv 2603.11513](https://arxiv.org/abs/2603.11513), [HTML](https://arxiv.org/html/2603.11513)). Modelos: SmolLM2-360M e **Qwen2.5 1,5B, 3B e 7B, todos em 4 bits NF4**, mais Llama-3.1-8B em FP16. São 1.000 perguntas (500 NQ, 500 HotpotQA) em quatro condições: sem recuperação, BM25, denso (E5-large-v2) e **oráculo**. Cada par (modelo, pergunta) é rotulado **Known** se o modelo acerta sem recuperação (EM = 1) e **Unknown** caso contrário. Achados: "even with oracle retrieval, models ≤7B fail to extract the correct answer 85–100% of the time on questions they cannot answer alone" (7B: 14,6% de EM nas Unknown com oráculo); a recuperação "destroys 42 to 100 percent of answers the model previously knew"; o saldo líquido é negativo em todos os modelos (7B com denso: −3,0 p.p.). Recorte por tipo: "The distraction effect is stronger for HotpotQA at 1.5B (70.4% destruction vs. 53.1% for NQ), suggesting multi-hop context is more confusing for smaller models". A falha dominante nas 2.588 falhas com oráculo é "irrelevant generation" (61–100%), seguida de recusa (20–24% no 7B). **Ressalvas:** preprint sem revisão por pares; EM é severa para respostas gerativas (uma resposta certa e longa conta como erro, e os próprios autores reportam 7–8% de erros de formato); o "tipo de pergunta" é o dataset, e não uma feature da pergunta. **Mesmo assim, é o precedente direto para três coisas que a nota propunha como novas:** escada de tamanhos na mesma família, 4 bits, e decomposição por pergunta com condição oráculo.
- **Baturova, Bruches, Chernov, Derunets, Fomin & Kostin, "Little Brains, Big Feats"** (ECML PKDD 2026, trilha Applied Data Science; [arXiv 2606.30062](https://arxiv.org/abs/2606.30062), [HTML](https://arxiv.org/html/2606.30062)). São 17 SLMs de 1,5 a 8B, entre eles **Qwen2.5 1,5/3/7B e Qwen3 1,7/4/8B**, todos em GGUF quantizado (Q4_K_M ou Q5_K_M), com GPT-5-mini de referência. Os dados são 500 amostras em **russo**, rotuladas em seis tipos de pergunta (factoide 278, baseada em evidência 77, raciocínio 45, comparação 40, experiência 57, instrução 3). O contexto é **oráculo** ("we focus exclusively on the generation stage") e a avaliação é por LLM-juiz (GPT-5-mini, Qwen3-8B, GLM-4.7). **Os resultados são só agregados por modelo, sem quebra por tipo de pergunta** (tabela 3, conforme o HTML). É o trabalho com o cenário mais parecido com o do Ditto (língua não inglesa, quantização local, a mesma escada do qwen3), e ele deixa aberta justamente a análise tipo × tamanho.
- **PRGB** (Tan et al., jul/2025; [arXiv 2507.22927](https://arxiv.org/abs/2507.22927), [HTML](https://arxiv.org/html/2507.22927)). Benchmark de geração em RAG que usa *placeholders* para separar conhecimento paramétrico de contexto, com três dimensões (filtragem multinível, combinação, raciocínio sobre referência) e níveis de ruído. Modelos: Qwen2.5 7B, 14B, 32B, 72B e MAX; Qwen3 8B, 30B e 235B; Gemma3 e fechados. EN e ZH; métrica por palavras-chave e juiz GPT-4o. Achados: modelos menores às vezes **superam** os maiores em "needle-in-a-haystack" porque copiam o trecho literal, enquanto os maiores parafraseiam e omitem detalhes; os maiores vencem em combinação e raciocínio; com ruído moderado/difícil, os menores caem mais. **É uma análise de tipo de tarefa × tamanho em RAG, mas começa em 7B.**
- **Sufficient Context** (seção 3.4) já mostrava, de forma qualitativa, que modelos abertos menores "hallucinate or abstain often, even with sufficient context" ([arXiv 2411.06037](https://arxiv.org/abs/2411.06037)).

**Quantização.**
- **Yazan, Verberne & Situmeang** (IR-RAG @ SIGIR 2024; [arXiv 2406.10251](https://arxiv.org/abs/2406.10251)) comparam FP16 × INT4 em vários modelos de 7B e 8B, em duas tarefas de personalização, aumentando o número de documentos recuperados e com três retrievers. Conclusão: "if a 7B LLM performs the task well, quantization does not impair its performance and long-context reasoning capabilities". Não há análise por tipo de pergunta.
- **"Does quantization affect models' performance on long-context tasks?"** (EMNLP 2025 segundo o [repositório oficial](https://github.com/molereddy/long-context-quantization); [arXiv 2505.20276](https://arxiv.org/abs/2505.20276)). São 9,7 mil exemplos, cinco métodos (FP8, GPTQ-int8, AWQ-int4, GPTQ-int4, BNB-nf4) e Llama-3.1 8B/70B e Qwen-2.5 7B/32B/72B. 8 bits quase não perdem (~0,8%); 4 bits perdem até 59% em entradas longas (>64K tokens); a degradação "tends to worsen when the input is in a language other than English"; o efeito depende de método, modelo e tarefa. **Para o Ditto:** o contexto é curto (top-k chunks), então o número de 59% não se transfere, mas o sinal "4 bits + língua não inglesa piora" vale como hipótese a testar com o MLX 4-bit em PT-BR.
- Li et al., "Evaluating Quantized Large Language Models" ([arXiv 2402.18158](https://arxiv.org/abs/2402.18158)): 11 famílias de 125M a 180B e cinco categorias de tarefa, incluindo contexto longo. Só li o abstract, que não traz os números por categoria.

**Contexto × memória paramétrica e distratores, por tamanho.**
- **FaithEval** (Ming et al., ICLR 2025; [arXiv 2410.03727](https://arxiv.org/abs/2410.03727)): "larger models do not necessarily exhibit improved" fidelidade ao contexto.
- **Contextual entrainment** (Kukreja et al., 2026; [arXiv 2604.13275](https://arxiv.org/abs/2604.13275)): escadas Pythia (410M–12B) e Cerebras-GPT (111M–13B). Modelos maiores resistem mais a contexto contrafactual e relacionado, mas **copiam mais** tokens de contexto aleatório/irrelevante: "Larger models are simultaneously better and worse at handling contextual information". É um estudo de logits, não de QA com RAG.
- **Fouilhé, Asher & Muller** (BlackboxNLP 2026 Reproducibility Challenge; [arXiv 2609.24238](https://arxiv.org/abs/2609.24238)): 31 modelos (Pythia, GPT-2, Qwen3, Ministral). Confirmam que "larger models and higher-frequency entities tend to favor memorized answers", mas o efeito de frequência some em alguns Qwen3, e **a formulação da pergunta sozinha mudou a dependência da memória em até 80 p.p.** Para o Ditto, isso sustenta a paráfrase (sobreposição pergunta↔evidência) como feature, e não só o conteúdo.
- **Zhang, Meng & Collier** (ACL 2026; [arXiv 2601.12499](https://arxiv.org/abs/2601.12499)): em multi-hop com contexto longo, o desempenho "collapses to the level of the least visible evidence, governed by absolute position". Não verifiquei os tamanhos dos 5 LLMs.

**Features a priori × tamanho, fora de RAG.**
- **ADeLe** (Zhou et al., 2025; [arXiv 2503.06378](https://arxiv.org/abs/2503.06378), [HTML](https://arxiv.org/html/2503.06378)): 18 rubricas de "nível de demanda" por instância, 16.108 instâncias de 63 tarefas e 15 LLMs, incluindo **LLaMA 3.2/3.1 de 1B a 405B** e R1-Distill-Qwen de 1,5B a 32B. Prevê o desempenho por instância a partir das demandas e acha que "the ability scores at knowledge dimensions are mostly determined by model size". As rubricas são aplicadas pelo **GPT-4o** (Spearman médio de 0,86 com consenso humano). **É o precedente mais forte para "features a priori da pergunta × tamanho explicam o erro por item"**, mas sem recuperação e com rótulos gerados por LLM, que é o que Brant et al. (seção 3.6) desaconselham para dificuldade. Não confirmei o venue.
- **IRT-Router** (Song et al., ACL 2025; [arXiv 2506.01048](https://arxiv.org/abs/2506.01048)): roteamento entre LLMs com dificuldade e discriminação por consulta, interpretáveis. Sem RAG. **RAGRouter** (Zhang et al., 2025; [arXiv 2505.23052](https://arxiv.org/abs/2505.23052)): roteia entre LLMs com RAG, levando em conta como os documentos mudam a capacidade de cada um, mas com embeddings aprendidos, não com features explicativas.

**Técnicas de RAG feitas para small models.** O **MiniRAG** (Fan, Wang, Ren & Huang; [arXiv 2501.06713](https://arxiv.org/abs/2501.06713); ACL 2026 segundo o [repositório](https://github.com/HKUDS/MiniRAG)) parte da constatação de que frameworks existentes sofrem "severe performance degradation" com SLMs e propõe indexação em grafo heterogêneo (chunks + entidades). É candidato a eixo técnico, não a análise de dificuldade. Froma et al. ([arXiv 2605.00964](https://arxiv.org/abs/2605.00964)) testam assistentes RAG de 3B, 8B e 70B com 112 pessoas: o ganho da colaboração humano+modelo sobre o modelo sozinho é significativo "irrespective of model size".

**Português.** Não achei estudo de small models em RAG em PT com análise por pergunta ou por tamanho. O que existe:
- Kuratomi, Pirozelli, Cozman & Peres ([arXiv 2501.13880](https://arxiv.org/abs/2501.13880), assistente da USP): com os chunks corretos, a acurácia sobe de 13,68% para 54,02%, e o retriever acerta 30% no top-5. **É uma decomposição recuperação × geração em PT**, mas agregada e com um só gerador.
- Garcia et al., PROPOR 2026 ([2026.propor-2.18](https://aclanthology.org/2026.propor-2.18/)): RAG em bulas; a recuperação ingênua "sometimes reduced accuracy compared to a parametric-only baseline", com viés de ancoragem em evidência parcialmente relevante. A página não diz os modelos.
- Ferraz et al., PROPOR 2026 ([2026.propor-1.12](https://aclanthology.org/2026.propor-1.12/)): RAG com small models para fake news; não supera métodos clássicos. A página não diz os modelos.
- Junqueira et al. 2025 (Sabiá-7B 4 bits, seção 3.6) continua sendo o único com quantização explícita.
- Famílias PT que permitiriam uma escada "nativa": Tucano (Corrêa et al., [arXiv 2411.07854](https://arxiv.org/abs/2411.07854); o abstract não lista os tamanhos). Assis, Freitas & Paes (JBCS 2025, [SBC](https://journals-sol.sbc.org.br/index.php/jbcs/article/view/5814)) avaliam LLMs brasileiros em QA gerativo, mas sem RAG.

**Tabela: trabalhos × tamanhos × análise por tipo de pergunta**

| Trabalho | Modelos (≤8B em negrito) | Escada na mesma família? | Quantização | Condição oráculo / sem recuperação | Tamanho analisado **por tipo de pergunta**? | Métrica | Língua |
|---|---|---|---|---|---|---|---|
| Pandey 2026 (preprint) | **SmolLM2-360M, Qwen2.5 1,5/3/7B**, **Llama-3.1-8B** | sim (Qwen2.5 1,5→7B) | 4 bits NF4 | ambas | parcial: só dataset (NQ × HotpotQA) + Known/Unknown por pergunta | EM, F1 | EN |
| Baturova et al. 2026 | 17 SLMs **1,5–8B** (Qwen2.5, **Qwen3 1,7/4/8B**, Mistral, Phi, Llama-2) | sim | GGUF Q4/Q5 | oráculo | **não** (tipos rotulados, resultados agregados) | LLM-juiz | RU |
| PRGB 2025 | Qwen2.5 **7B**–72B, Qwen3 **8B**–235B, Gemma3, fechados | sim, mas a partir de 7B | não informado | placeholders | **sim** (filtragem / combinação / raciocínio × tamanho) | palavras-chave + GPT-4o | EN, ZH |
| Sufficient Context 2025 | **Mistral-3 7B**, Gemma-2 27B, fechados | não | não | suficiente × insuficiente | não (qualitativo por tamanho) | autorater | EN |
| Yazan et al. 2024 | vários **7B/8B** | não | FP16 × INT4 | varia nº de docs | não | da tarefa | EN |
| Long-context quantization 2025 | Llama-3.1 **8B**/70B, Qwen-2.5 **7B**/32B/72B | sim (2 famílias) | 5 métodos, 8 e 4 bits | — | por tarefa, não por pergunta | da tarefa | EN + outras |
| ADeLe 2025 (sem RAG) | LLaMA 3.x **1B**–405B, R1-Distill-Qwen **1,5B**–32B, OpenAI | sim | não | — | **sim** (18 demandas a priori × tamanho, por instância) | acerto | EN |
| GRADE 2025 | **Llama 3.2 3B** + fechados | não | não | — | hops × distância, sem isolar tamanho | LLM | EN |
| Junqueira et al. 2025 | **Sabiá-7B** | não | 4 bits | — | não | ROUGE | PT |
| **Ditto (proposta)** | **qwen3 1,7B, Qwen2.5-7B 4-bit**, Gemini como teto | a fazer (qwen3 1,7/4/8B) | 4 bits (MLX/Ollama) | a adicionar | **sim**, por features a priori sem LLM | `context_hit`, chrF, token-F1 | PT-BR |

**Leitura.** A interação "tamanho × tipo de pergunta" em RAG **já tem precedente**: PRGB (≥7B, por dimensão de tarefa), Pandey (≤7B, por dataset e por Known/Unknown) e, fora de RAG, ADeLe (por demanda a priori). Uma frase como "somos os primeiros a olhar onde o modelo pequeno falha em RAG" não se sustenta mais. O que nenhum dos três faz: (a) variar a **configuração** RAG (chunking/embedding/técnica/retriever) e ver se a falha do pequeno depende dela; (b) explicar a falha por **features da pergunta calculadas sem LLM** (distância pergunta↔evidência, nº de evidências, paráfrase); (c) PT-BR com resposta aberta e sem juiz. Dos dois achados de Pandey, o que mais importa para o Ditto é o **gargalo de uso** (com a evidência no contexto, o modelo pequeno não extrai a resposta), e não o "efeito distração". A distração só atinge perguntas que o modelo já sabia sem contexto, e num FAQ de uma cidade pequena quase nenhuma pergunta deve ser "Known" (cauda longa, seção 3.3). Isso é hipótese: o Ditto não tem hoje nem a condição sem recuperação nem a com oráculo para medir (seção 5.5).

---

## 4. Onde está a lacuna, com honestidade

| Dimensão | Guinet 2024 | LiveRAG 2025 | GRADE 2025 | Sufficient Ctx 2025 | Tian 2026 / DRAG 2026 | Pandey 2026 | PRGB 2025 | Baturova 2026 | ADeLe 2025 | **Ditto (proposta)** |
|---|---|---|---|---|---|---|---|---|---|---|
| Dificuldade por pergunta estimada | IRT 3PL | IRT 2PL contínua | fórmula a priori | não (rótulo binário) | predição de qualidade | Known/Unknown por modelo | não | não | preditor por instância | IRT/GLMM contínuo |
| Features a priori da pergunta | Bloom | categorias + similaridade | *hops* + distância | — | QPP, perplexidade | só dataset | dimensão da tarefa, nível de ruído | 6 tipos (sem cruzar) | 18 demandas, rotuladas por GPT-4o | evidências, distância, tipo, sem LLM |
| Configurações como respondentes, decompostas | **sim** (LLM, ret, ICL) | não (equipes) | não | não | escolha, não decomposição | não (4 condições de recuperação) | não | não (só gerador) | não | **sim** (5 eixos) |
| Interação pergunta × tamanho do LLM | não reportada | não | não isolada | qualitativa (grande × pequeno) | não | **sim, por dataset** | **sim, por tarefa (≥7B)** | não | **sim, por demanda** (sem RAG) | **sim, por feature** |
| Escada de tamanhos na mesma família, ≤8B | não | não | não | não | não | **sim** (Qwen2.5 1,5→7B) | não (começa em 7B) | **sim** (Qwen3 1,7/4/8B) | sim (LLaMA 1B→405B) | a fazer (qwen3 1,7/4/8B) |
| Condição oráculo / sem recuperação | oracle e closed-book | não | — | por suficiência | não | **ambas** | placeholders | oráculo | — | a adicionar |
| Resposta aberta, sem LLM-juiz | não (múltipla escolha) | não (juiz LLM) | — | não (autorater) | NQ (EM) | EM/F1 (curta) | não (GPT-4o) | não (juiz) | acerto binário | **sim** |
| Small models locais quantizados | Mistral-7B | ? | Llama 3.2 3B | Mistral 7B | Qwen-3 8B | 4 bits | ? | Q4/Q5 GGUF | não | **1,7–7B, 4 bits** |
| Português | não | não | não | não | não | não | não | não (russo) | não | **sim** |

A combinação da última coluna continua sem precedente, mas **a busca dirigida a small models encolheu a lacuna**. A interação pergunta × tamanho, com escada na mesma família e modelos de 4 bits, já foi medida em RAG por Pandey 2026 (com as ressalvas de preprint e de EM); a interação tipo de tarefa × tamanho, por PRGB (≥7B); e features a priori × tamanho por instância, pelo ADeLe (sem RAG, com rótulos de LLM). O Baturova et al. tem exatamente o cenário (língua não inglesa, qwen3 quantizado, tipos rotulados) e não publica o cruzamento, o que mostra que o recorte é plausível e que outros podem publicá-lo antes.

O que ainda é defensável como contribuição:
1. **O eixo de configuração.** Nenhum dos trabalhos de small models varia chunking/embedding/técnica/retriever. A pergunta "a falha do modelo pequeno depende da configuração, ou só da pergunta?" (termo `pergunta × llm × técnica` no modelo misto) é só do Ditto.
2. **Features calculáveis sem LLM**, em vez de dataset (Pandey), dimensão sintética (PRGB) ou rótulo de GPT-4o (ADeLe).
3. **PT-BR, resposta aberta, sem juiz.**

Então a contribuição é **integrar** (IRT/GLMM explicativo nos dois lados) **num cenário pouco coberto**, e replicar em PT-BR o gargalo de uso do contexto de Pandey. Não é "ninguém estudou dificuldade de pergunta", e também não é "ninguém estudou onde small models falham em RAG".

---

## 5. Oportunidade no Ditto, concretamente

### 5.1 O que o Ditto já tem

- **Dados por pergunta × configuração.** `RunResult` guarda pergunta, referência, `reference_contexts`, resposta, contextos recuperados e `scores` por métrica (`backend/app/core/db/models.py:47-63`). O export `GET /experiments/{id}/export.csv` achata isso em uma linha por (chunking, embedding, rag, retriever, llm, pergunta), com uma coluna por métrica (`backend/app/api/experiments.py:33-80`, rota na linha 255). **É exatamente a matriz respondente × item que IRT e GLMM pedem.**
- **Grade fatorial.** 4 chunkers (fixed, recursive, token, semantic) × 3 embeddings (gemini, e5, paraphrase) × 6 técnicas (naive, rerank, hyde, crag, compression, agentic) × 4 retrievers (similarity, mmr, multi_query, parent_document) × os LLMs escolhidos (`_combinations`, `backend/app/experiments/orchestrator.py:77-79`). Com 3 LLMs, o fatorial completo tem 864 configurações.
- **Métricas de recuperação com gold**, independentes de LLM e de embedder: `context_hit`, `context_mrr` e `context_recall_gold` (`backend/app/core/evaluation/gold_metrics.py:45-85`). **Elas permitem a decomposição do estilo Sufficient Context sem autorater.**
- **Como o ranking agrega hoje:** a tela faz a média simples por configuração sobre as perguntas e uma "média" das médias de **todas** as métricas, que misturam cosseno, chrF e hit (`frontend/src/pages/ExperimentDetailPage.tsx:28-73`). Não há incerteza nem efeito de pergunta. Todas as configurações respondem às mesmas perguntas, então a comparação é pareada, mas a média esconde se duas configurações diferem só em 2 ou 3 perguntas difíceis.

### 5.2 As perguntas atuais, olhadas como itens

`database/perguntas.csv` tem 15 perguntas; as evidências vêm separadas por `|` (`backend/app/experiments/csv_loader.py:9-22`). Olhando o arquivo:
(Numeração pela ordem das linhas de dados do CSV.)
- **Duas evidências:** P3 (a pé × táxi) e P12 (principais atrações). As outras 13 têm uma.
- **Agregação/lista:** P2, P7 e P12 pedem "o melhor", "o mais famoso", "as principais". Várias referências listam itens que **não estão** na evidência anotada. Exemplos: a referência de P2 cita a sorveteria e o Bar do Hélio, e a evidência só cita a Rua da Gastronomia; a de P9 (lembranças) cita o Bar do Hélio; a de P10 (horários) cita o almoço de domingo do AiJapa, ausente da evidência. Uma resposta perfeita à evidência pode tirar nota baixa contra a referência. **Isso é dificuldade de anotação, não da pergunta.** Rodriguez et al. listam justamente "catching labeling mistakes" como uso da IRT ([2021.acl-long.346](https://aclanthology.org/2021.acl-long.346/)).
- **Evidência compartilhada:** P8 (Wi-Fi) e P14 (hospedagem) têm a mesma evidência.
- **Sim/não com matiz:** P6 ("é seguro à noite?"), P13 ("tem cachoeira?").
- **Correspondência com o FAQ:** segundo a nota anterior ([2026-09-24-avaliacao-rag-sem-llm.md](2026-09-24-avaliacao-rag-sem-llm.md), seção 2), as primeiras 11 perguntas são paráfrases das seções 1–11 do FAQ, então a sobreposição léxica pergunta↔evidência tende a ser alta. As 4 últimas vêm de seções mais adiante e são mais distantes.

Ou seja: há variação real de dificuldade, mas **15 itens com features confundidas entre si** (agregação anda junto com duas evidências e com referência que vai além da evidência). Nenhum modelo estatístico separa essas causas com esse conjunto.

### 5.3 O que medir (em ordem de custo)

**Nível 0: análise offline sobre o CSV exportado, sem mudar código.** Com pandas/statsmodels num notebook:
1. **Dificuldade empírica por pergunta:** média e desvio de cada métrica sobre todas as configurações, e o mesmo separado por LLM. Um heatmap pergunta × LLM já responde "esta pergunta é difícil para o qwen3:1.7b e não para o Gemini?".
2. **Decomposição do erro por linha,** usando o gold que já existe:
   - `context_hit = 0` → **falha de recuperação** (FP2/FP3 de Barnett);
   - `context_hit = 1` e correção baixa (`token_f1`/`chrf`/`answer_correctness` abaixo de um limiar) → **falha de geração com contexto disponível** (FP4 "not extracted"; o caso "contexto suficiente e o modelo pequeno não usou" de Joren et al.);
   - `context_hit = 0` e correção alta → acerto por conhecimento paramétrico ou por evidência não anotada. Isso é pouco provável numa cidade pequena, então essas linhas valem para **auditar o gold**.

   Tabulado por pergunta × LLM, isso responde à pergunta do usuário de forma direta e defensável: "na P12, o retriever trouxe a evidência em X% das configurações; com ela no contexto, o modelo de 1,7B acertou Y% e o Gemini Z%".
3. **Discriminação por pergunta:** a correlação entre o escore da pergunta e a média da configuração nas outras perguntas (correlação item-resto, da teoria clássica dos testes). Pergunta com discriminação ≈ 0 ou negativa é candidata a erro de anotação.

**Nível 1: features a priori por pergunta.** Calculadas uma vez por pergunta e sem LLM:

| Feature | Como | Base na literatura |
|---|---|---|
| `n_evidencias` | número de passagens em `evidencia_referencia` | *hops* / número de evidências (GRADE, MuSiQue) |
| Sobreposição léxica pergunta↔evidência | token-F1 ou chrF entre a pergunta e cada evidência, tomando o **mínimo** | heurística de Sugawara 2018 |
| Distância semântica pergunta↔evidência | 1 − min cos(pergunta, evidência_i) com o embedder de avaliação | D_r do GRADE |
| Tipo de resposta | onde / qual / como / sim-não / lista (manual ou por regra sobre a palavra interrogativa) | categorias do LiveRAG |
| Referência além da evidência | cobertura dos tokens de conteúdo da referência pela evidência | diagnóstico de anotação (Rodriguez 2021) |
| Tamanho da referência | número de tokens | "concise-answer" do LiveRAG |

Isso pode entrar como função pura em um módulo novo (ex.: `backend/app/core/evaluation/difficulty.py`), reaproveitando a `_normalize` e a `rapidfuzz` de `gold_metrics.py`. **Não deve ser um `Evaluator`:** o registry de métricas é por amostra (`base.py:23-34`) e a dificuldade é por pergunta. O lugar natural é a análise, não a pontuação.

**Nível 2: modelo estatístico.** Duas formulações equivalentes em espírito:
- **Modelo misto** (GLMM, na linha do NIST AI 800-3): `escore ~ chunking + embedding + rag + retriever + llm + features_da_pergunta + llm:features_da_pergunta + (1 | pergunta) + (1 | pergunta:llm)`. Para escores em [0,1], regressão Beta; para `context_hit`, logística. O termo `llm:features` é a hipótese do usuário ("pergunta com duas evidências é difícil **para o modelo pequeno**"). A variância de `(1 | pergunta)` diz quanto do escore é explicado pela pergunta, e não pela configuração.
- **IRT explicativa:** a habilidade decomposta por componente, como em Guinet et al. (θ = θ_chunk + θ_emb + θ_rag + θ_ret + θ_llm), e a dificuldade decomposta por features. A versão contínua pode seguir o LiveRAG (Continuous-Bernoulli no `py-irt`) ou o LEGO-IRT. A literatura psicométrica chama "item-side covariates" de modelo explicativo (tipo LLTM). **Não abri fonte primária desse conceito nesta pesquisa (não verificado).**

Os dois dão, como subproduto, **ranking de configurações com intervalo de confiança** e **ranking estratificado por dificuldade** (quem ganha nas perguntas fáceis pode não ganhar nas difíceis, que é o argumento de Rodriguez et al.).

**Nível 3: produto (opcional).** Um endpoint `GET /experiments/{id}/difficulty`, com as features e a dificuldade empírica por pergunta, e uma aba na `ExperimentDetailPage` com o heatmap pergunta × LLM e a decomposição hit/geração. Só vale depois que o nível 0 mostrar sinal.

### 5.4 Tamanho: o que é realista

- **15 perguntas bastam para o nível 0** (descritivo, por pergunta), não para inferência. Com 15 níveis de efeito aleatório, e features confundidas entre si (5.2), a variância de pergunta sai muito imprecisa e o coeficiente de `llm:feature` fica sem poder estatístico. O limiar exato de "quantos itens" não foi verificado numa fonte primária. As referências de redução de benchmarks (100 exemplos no tinyBenchmarks, [2402.14992](https://arxiv.org/abs/2402.14992); 50 por benchmark no IRSL, [2606.07616](https://arxiv.org/abs/2606.07616)) estimam a **habilidade** com itens já calibrados em milhares de respostas. Não servem como limite inferior para **calibrar** dificuldade.
- **Lado dos respondentes:** o Ditto tem de sobra (centenas de configurações). Mas as configurações não são independentes, porque compartilham LLM, chunker etc. Por isso a decomposição hierárquica é obrigatória, e não um enfeite.
- **Meta realista:** de **50 a 100 perguntas desenhadas para descasar as features**. O FAQ tem 50 seções (`### N.`), então dá para ter uma pergunta de uma evidência por seção, e mais um bloco de perguntas de **duas seções** (comparação/agregação, o tipo mais difícil no LiveRAG), variando a paráfrase (alta × baixa sobreposição com a evidência). A anotação é manual, mas barata: a evidência é texto literal, o mesmo formato atual.
- **Segundo corpus para generalizar:** o Pirá ([2202.02398](https://arxiv.org/abs/2202.02398)) tem textos de apoio em PT e mais de 2 mil perguntas, e evita que a tese dependa de um único FAQ.
- **LLMs:** para a interação pergunta × tamanho, são necessários pelo menos 3 pontos de tamanho na **mesma família, versão, runtime e quantização** (ex.: qwen3 1,7B / 4B / 8B, a escada que Baturova et al. usam; seção 3.7), com o Gemini como teto fora da escada. O par atual qwen3:1.7b × Qwen2.5-7B-4bit **não** serve: muda família, versão e runtime junto com o tamanho. Senão, tamanho fica confundido com família, que é exatamente a crítica ao GRADE.
- **Custo de execução:** não é preciso rodar o fatorial completo para a análise de dificuldade. Um subconjunto fixo (ex.: 2 chunkers × 2 embeddings × 3 técnicas × 2 retrievers × 3 LLMs = 72 configurações × 100 perguntas = 7.200 respostas) já dá uma matriz densa. Não estimei o tempo por resposta no hardware do usuário.

### 5.5 Adicionar esses processos teria ganho/impacto real para o Ditto?

**Critério.** O objetivo do Ditto é **ranquear configurações de RAG para modelos pequenos**. Hoje o produto entrega uma média por configuração sobre as perguntas (5.1). Um processo só tem ganho real se permitir uma **decisão** ou uma **afirmação de tese** que esse ranking não permite. Separo dois tipos de ganho:
- **ganho para o ranking** (o que a tela/CSV entrega ao usuário muda ou fica mais confiável);
- **ganho para a tese** (validade interna e narrativa: explicar *por que* uma configuração ganha, e se o ranking generaliza).

**(a) Decomposição do erro por `context_hit` × pergunta × LLM** (nível 0 da 5.3), **mais duas condições de controle: sem recuperação e com oráculo.**
- *O que permite que o ranking atual não permite:* dizer se a configuração perdeu porque o retriever não trouxe a evidência ou porque o LLM pequeno não a usou. São intervenções diferentes: trocar chunking/embedding/retriever num caso, trocar técnica/prompt/tamanho do LLM no outro. Com o oráculo (a `evidencia_referencia` como único contexto), cada LLM ganha um **teto de geração**; sem recuperação, um **piso paramétrico**. A distância entre a configuração e o teto do seu LLM é a parte do erro que a configuração ainda pode recuperar. É o desenho de Pandey 2026 e de Guinet 2024 (que incluem oracle e closed-book), e o Ditto não tem nenhuma das duas condições.
- *Ganho para o ranking:* **alto**. Permite normalizar o ranking por LLM ("esta configuração chega a 90% do teto do qwen3:1.7b") e evita comparar o 1,7B com o Gemini em escala absoluta. Também mostra onde **não adianta** otimizar a recuperação: se o qwen3:1.7b com oráculo já erra uma pergunta, nenhuma configuração a salva.
- *Ganho para a tese:* **alto**. É a replicação em PT-BR do gargalo de uso do contexto (Pandey), com gold textual em vez de EM.
- *Custo:* a decomposição em si é pandas sobre o CSV (horas). As duas condições pedem código: `rag.answer(question.text)` só recebe o texto da pergunta (`backend/app/experiments/orchestrator.py`, `_process_question`), então o oráculo precisa receber a evidência da `QuestionItem` (mudança pequena de interface). E, como chunking/embedding/retriever não afetam essas condições, elas devem rodar uma vez por LLM, e não dentro do produto cartesiano de `_combinations` (senão 48 execuções idênticas por LLM). Estimo 1–2 dias com testes.
- *Dados:* os atuais. As 15 perguntas bastam para o descritivo.
- *Risco:* baixo. O principal é o limiar de "acertou" com chrF/token-F1 (definir e reportar a sensibilidade). As linhas `context_hit = 0` com acerto alto servem para auditar o gold (5.3).

**(b) Escada de tamanhos na mesma família (qwen3 1,7B / 4B / 8B, mesma quantização).**
- *O que permite:* isolar **tamanho** de **família e quantização**. Hoje o contraste é qwen3:1.7b (Ollama) × Qwen2.5-7B-4bit (MLX) × Gemini: família, versão, runtime, quantização e tamanho mudam ao mesmo tempo, e nenhuma frase sobre "modelo pequeno" se sustenta com isso. Com a escada, dá para dizer "o ranking das configurações muda entre 1,7B e 8B" (ou não muda). Essa é uma **decisão de produto**: recomendar uma configuração por faixa de tamanho, ou uma só.
- *Ganho para o ranking:* **médio-alto**, se a ordem das configurações mudar com o tamanho; **baixo**, se não mudar. Mas saber que não muda também é resultado ("o ranking é robusto ao tamanho").
- *Ganho para a tese:* **alto**. É a condição mínima para qualquer afirmação sobre "small models", e é o que Pandey (Qwen2.5 1,5/3/7B) e Baturova (Qwen3 1,7/4/8B) já fazem. Um revisor vai cobrar.
- *Custo:* baixo em código (`make model-add` já existe) e alto em **tempo de máquina e memória**. Cada LLM a mais multiplica o fatorial (com 3 LLMs, 864 configurações, 5.1). No perfil de memória `low` (≤8 GB), rodar 8B junto com embedders locais pode não caber; não testei. Mitigação: rodar a escada num subconjunto fixo de configurações (5.4), e não no fatorial completo.
- *Risco:* confundir versões (qwen3 × Qwen2.5). A escada precisa ser toda qwen3, no mesmo runtime e na mesma quantização. O Gemini fica como teto, fora da escada.

**(c) Features a priori da pergunta** (nº de evidências, distância pergunta↔evidência à la GRADE, sobreposição léxica, tipo de resposta, referência além da evidência).
- *O que permite:* passar de "a P12 é difícil" para "perguntas com duas evidências e baixa sobreposição são difíceis para o 1,7B". Só essa forma generaliza para perguntas novas.
- *Ganho para o ranking:* **baixo agora**. Com 15 perguntas e features confundidas (5.2), não dá para estratificar o ranking por feature com confiança. Uma exceção útil já: a feature "referência além da evidência" funciona como **auditoria do gold**, e corrigir as referências de P2, P9 e P10 muda as notas de todas as configurações.
- *Ganho para a tese:* **alto**, e é o que diferencia o trabalho de Pandey (dataset como tipo) e do ADeLe (rótulo por GPT-4o). É a contribuição (2) da seção 4.
- *Custo:* baixo. Funções puras sem LLM (5.3, nível 1), menos de um dia.
- *Risco:* circularidade, se a feature for calculada com o mesmo embedder que a configuração usa para recuperar (use o embedder de avaliação, fixo); e o efeito de paráfrase de até 80 p.p. relatado por Fouilhé et al. ([2609.24238](https://arxiv.org/abs/2609.24238)) sugere que a formulação pesa tanto quanto o conteúdo, o que é um argumento para variar a paráfrase no desenho (e).

**(d) IRT / GLMM com efeito aleatório de pergunta.**
- *O que permite:* ranking com **intervalo de confiança**, a fração da variância que vem da pergunta e não da configuração, e o teste formal da interação `llm × feature` e `llm × técnica × feature`.
- *Ganho para o ranking:* **médio**. O intervalo é o ganho mais concreto: diz ao usuário quais configurações do topo são indistinguíveis. Mas um bootstrap pareado sobre perguntas dá quase o mesmo intervalo com muito menos maquinaria, e é o que Pandey usa (2.000 reamostragens).
- *Ganho para a tese:* **médio-alto**, mas **só com 50–100 perguntas**. Com 15 é enfeite: a variância de pergunta sai imprecisa e a interação não tem poder (5.4).
- *Custo:* médio (statsmodels/R ou `py-irt` com a modificação contínua do LiveRAG). Alguns dias, mais a curva de aprendizado de IRT contínua.
- *Risco:* complexidade que o revisor não pede. O modelo misto é mais fácil de defender que a IRT, e o NIST AI 800-3 dá cobertura para ele.

**(e) Ampliar o conjunto de perguntas (50–100, desenhadas para descasar as features; ou um segundo corpus, o Pirá).**
- *O que permite:* tudo o que (c) e (d) prometem, e uma resposta à pergunta de validade externa mais óbvia: "o ranking vale fora destas 15 perguntas?".
- *Ganho para o ranking:* **alto**. Com 15 perguntas, uma pergunta pesa 6,7% da média, e uma referência mal escrita muda a ordem do topo. É o único item que melhora a confiabilidade do ranking sem nenhuma estatística nova.
- *Ganho para a tese:* **alto**. É pré-requisito de (c) e (d).
- *Custo:* o maior em **trabalho humano** (anotação da pergunta, referência e evidência literal). O formato é o atual, e o FAQ tem 50 seções. Com 100 perguntas, o custo de execução também sobe cerca de 6,7 vezes, então vale combinar com o subconjunto de configurações (5.4).
- *Risco:* perguntas feitas pelo próprio autor tendem a ter alta sobreposição com o texto. É preciso escrever a paráfrase de propósito (alta × baixa sobreposição) e, se possível, com um segundo anotador.

**Recomendação priorizada**

| Prioridade | Processo | Ganho para o ranking | Ganho para a tese | Custo | Quando |
|---|---|---|---|---|---|
| 1 | (a) decomposição por `context_hit` + condições oráculo e sem recuperação | alto | alto | baixo–médio | agora |
| 2 | (e) ampliar as perguntas, começando por corrigir as referências que vão além da evidência | alto | alto (pré-requisito) | alto (humano) | em paralelo com 1 |
| 3 | (b) escada qwen3 1,7/4/8B num subconjunto de configurações | médio–alto | alto | médio (máquina) | depois de 1 |
| 4 | (c) features a priori | baixo agora, médio com (e) | alto | baixo | junto com (e), no desenho das perguntas novas |
| 5 | (d) GLMM/IRT | médio (intervalo; o bootstrap cobre a maior parte) | médio–alto com ≥50 perguntas | médio | por último |

Em uma frase: **o que muda o ranking do Ditto é (a) e (e)**. (b) e (c) mudam principalmente o que a tese pode afirmar sobre modelos pequenos, e (d) é a forma de reportar, que só vale com as perguntas de (e). Hoje, com 15 perguntas e sem teto por LLM, o ranking diz qual configuração teve maior média, mas não diz se ela está perto do máximo possível para aquele LLM nem se a diferença para a segunda sobrevive a trocar duas perguntas.

---

## 6. Oportunidade para a comunidade: novidade, riscos, formato

**O que seria novo:**
1. IRT/GLMM **explicativa nos dois lados** sobre um fatorial de RAG: componentes da configuração como efeitos fixos, e features a priori da pergunta, com interação com o tamanho do LLM. Guinet et al. fazem o lado do respondente; GRADE e LiveRAG fazem o lado do item. Não achei quem faça os dois.
2. **Small models locais quantizados** (1,7–8B, 4 bits) como foco, com a pergunta explícita "que tipo de pergunta o RAG não salva num modelo pequeno". **Revisado após a busca dirigida (seção 3.7):** isso não é mais novo por si. Pandey 2026 já mede o gargalo por pergunta numa escada Qwen2.5 1,5–7B em 4 bits (por dataset, com EM), e o PRGB mede tipo de tarefa × tamanho a partir de 7B. O que sobra de novo é explicar esse gargalo por **features da pergunta** e pela **configuração RAG**, em PT-BR.
3. **PT-BR**, com um dataset pequeno mas anotado com evidência literal e features. Isso pode sair como *resource paper*.
4. **Sem LLM-juiz:** a decomposição recuperação × geração com gold textual (`context_hit`) e métricas léxicas/semânticas, o que torna a análise reprodutível e barata.

**Concorrentes a citar e diferenciar:** Pandey 2026 ([2603.11513](https://arxiv.org/abs/2603.11513)), PRGB 2025 ([2507.22927](https://arxiv.org/abs/2507.22927)), Baturova et al. 2026 ([2606.30062](https://arxiv.org/abs/2606.30062)), ADeLe 2025 ([2503.06378](https://arxiv.org/abs/2503.06378)), Guinet 2024 ([2405.13622](https://arxiv.org/abs/2405.13622)), LiveRAG 2025 ([2511.14531](https://arxiv.org/abs/2511.14531)), GRADE 2025 ([2508.16994](https://arxiv.org/abs/2508.16994)), Sufficient Context 2025 ([2411.06037](https://arxiv.org/abs/2411.06037)), Tian et al. 2026 ([2601.14546](https://arxiv.org/abs/2601.14546)), DRAG 2026 ([2609.17709](https://arxiv.org/abs/2609.17709)), RADAR 2026 ([2509.25426](https://arxiv.org/abs/2509.25426)). O campo está se movendo rápido: DRAG saiu dez dias antes desta nota. Vale refazer a busca antes de submeter.

**Riscos:**
- **Validade das métricas.** A dificuldade estimada é dificuldade **segundo a métrica**. As métricas de cosseno do Ditto são proxies comprimidos (e5 fica entre 0,7 e 1,0; nota de 2026-09-24, seção 2). Uma pergunta "difícil" pode ser só uma pergunta cuja referência é mal escrita. Mitigação: usar `context_hit` (binário, objetivo) e `chrf`/`token_f1` como variáveis-resposta principais, e validar uma amostra à mão.
- **Circularidade.** Se a dificuldade vem dos mesmos modelos que ela explica (como os rótulos do Adaptive-RAG), a conclusão "a pergunta era difícil" vira tautologia. Mitigação: as features **a priori** (nível 1) têm que explicar a dificuldade empírica (nível 0), e não o contrário.
- **Erro de anotação disfarçado de dificuldade** (5.2). Mitigação: tratar a discriminação baixa ou negativa como sinal de auditoria.
- **Tamanho amostral** (5.4). Com 15 perguntas, qualquer afirmação inferencial é frágil.
- **Novidade incremental.** Um revisor pode ver o trabalho como "GRADE + Guinet em português", ou como "Pandey 2026 em português". A defesa precisa ser o fatorial completo e o recorte small-model/PT-BR, com um achado concreto (ex.: "com a evidência no contexto, o gap entre 1,7B e 7B se concentra em perguntas de agregação com duas evidências").

**Formato plausível:** um capítulo de análise da tese, e um artigo curto ou de recurso (dataset PT-BR com evidência + features + matriz de respostas de N configurações) em venue nacional (STIL, BRACIS, PROPOR) ou em trilha de reprodutibilidade/recurso de venue de RI (ECIR, SIGIR). **Não verifiquei chamadas nem datas dessas conferências.**

---

## 7. Recomendação final

1. **Fazer o nível 0 agora, sem código novo:** exportar o CSV de um experimento que já rodou com pelo menos 2 LLMs de tamanhos diferentes e as métricas `context_hit`, `chrf` e `token_f1`. Montar o heatmap pergunta × LLM e a tabela de decomposição (hit=0 / hit=1 e errou / hit=1 e acertou) por pergunta × LLM. Isso já responde à pergunta do usuário para as 15 perguntas, de forma descritiva, e diz se vale continuar. Em seguida, adicionar as condições **oráculo** e **sem recuperação**, uma vez por LLM, para ter o teto e o piso de cada modelo (seção 5.5, item a).
1b. **Trocar o contraste de tamanhos por uma escada da mesma família** (qwen3 1,7/4/8B, mesma quantização e runtime) num subconjunto fixo de configurações (seção 5.5, item b).
2. **Se houver sinal:** calcular as features do nível 1 (funções puras, sem LLM) e **ampliar o conjunto para 50–100 perguntas**, desenhado para descasar número de evidências, sobreposição léxica e tipo de resposta. Corrigir antes as referências que vão além da evidência (P2, P9, P10 etc.).
3. **Depois:** ajustar o GLMM (statsmodels/R) ou a IRT contínua (`py-irt` com a modificação do LiveRAG), reportar a variância de pergunta, a interação feature × LLM e o ranking com intervalos. Só então levar para o produto (endpoint + aba), se ajudar o usuário final.
4. **Na tese,** enquadrar como "explicar a variação por pergunta num fatorial de RAG com small models em PT-BR", citando Guinet, LiveRAG e GRADE como o estado da arte que se estende, e Pandey 2026, PRGB e Baturova et al. como o estado da arte em small models. **Não** apresentar como "primeiro trabalho sobre dificuldade de pergunta" nem como "primeiro a mostrar onde small models falham em RAG".

---

## 8. Fontes

Código do Ditto (lido em 2026-09-25, commit `3c79e13`):
- `backend/app/core/evaluation/{base,gold_metrics}.py`, `backend/app/experiments/{orchestrator,csv_loader}.py`, `backend/app/api/experiments.py`, `backend/app/core/db/models.py`, `frontend/src/pages/ExperimentDetailPage.tsx`, `database/perguntas.csv`; registries em `backend/app/core/{chunking,embedding,rag,retrieval,llm,evaluation}/`.

QPP:
- Cronen-Townsend et al. 2002: https://dl.acm.org/doi/10.1145/564376.564429 (403; conferido pelo índice de busca)
- Shtok et al. 2012 (NQC): https://dl.acm.org/doi/10.1145/2180868.2180873 (conferido pelo índice de busca)
- multHP: https://arxiv.org/abs/2308.06431
- QPP-GenRE: https://arxiv.org/abs/2404.01012
- RPP/GPP em RAG: https://arxiv.org/abs/2601.14546
- QPP em RAG agêntico: https://arxiv.org/abs/2507.10411
- DRAG: https://arxiv.org/abs/2609.17709 · https://arxiv.org/html/2609.17709

IRT / modelos mistos:
- Lalor et al. 2016: https://aclanthology.org/D16-1062/
- Rodriguez et al. 2021: https://aclanthology.org/2021.acl-long.346/
- Vania et al. 2021: https://aclanthology.org/2021.acl-long.92/
- tinyBenchmarks: https://arxiv.org/abs/2402.14992
- Easy2Hard-Bench: https://arxiv.org/abs/2409.18433
- PVI / V-usable information: https://arxiv.org/abs/2110.08420
- LEGO-IRT: https://arxiv.org/abs/2510.04051
- IRSL: https://arxiv.org/abs/2606.07616
- py-irt: https://github.com/nd-ball/py-irt
- Guinet et al. 2024: https://arxiv.org/abs/2405.13622 · https://arxiv.org/html/2405.13622 · https://github.com/amazon-science/auto-rag-eval
- LiveRAG: https://arxiv.org/abs/2511.14531 · https://arxiv.org/html/2511.14531
- RADAR: https://arxiv.org/abs/2509.25426
- NIST AI 800-3: https://www.nist.gov/publications/expanding-ai-evaluation-toolbox-statistical-models · https://doi.org/10.6028/NIST.AI.800-3

Complexidade, recuperação adaptativa e roteamento:
- Adaptive-RAG: https://arxiv.org/abs/2403.14403 · https://arxiv.org/html/2403.14403
- Self-RAG: https://arxiv.org/abs/2310.11511
- SKR: https://arxiv.org/abs/2310.05002
- Mallen et al. 2023: https://arxiv.org/abs/2212.10511
- Kandpal et al. 2023: https://arxiv.org/abs/2211.08411
- Hybrid LLM: https://arxiv.org/abs/2404.14618
- RouteLLM: https://arxiv.org/abs/2406.18665
- FrugalGPT: https://arxiv.org/abs/2305.05176

Atribuição do erro:
- Seven Failure Points: https://arxiv.org/abs/2401.05856 · https://arxiv.org/html/2401.05856
- RGB: https://arxiv.org/abs/2309.01431
- CRUD-RAG: https://arxiv.org/abs/2401.17043
- RAGChecker: https://arxiv.org/abs/2408.08067
- Sufficient Context: https://arxiv.org/abs/2411.06037 · https://arxiv.org/html/2411.06037 · https://github.com/hljoren/sufficientcontext
- Distração por contexto irrelevante: https://arxiv.org/abs/2302.00093
- Lost in the Middle: https://arxiv.org/abs/2307.03172

Features e datasets:
- Sugawara et al. 2018: https://aclanthology.org/D18-1453/
- GRADE: https://arxiv.org/abs/2508.16994 · https://arxiv.org/html/2508.16994 · https://aclanthology.org/2025.findings-emnlp.236.pdf · https://github.com/DaeyongKwon98/GRADE
- MHTS: https://arxiv.org/abs/2504.08756
- HotpotQA: https://arxiv.org/abs/1809.09600 · card: https://huggingface.co/datasets/hotpotqa/hotpot_qa
- MuSiQue: https://arxiv.org/abs/2108.00573
- Compositionality gap: https://arxiv.org/abs/2210.03350
- Survey QDET: https://dl.acm.org/doi/10.1145/3556538

Português:
- Taschetto & Fileto, STIL 2025: https://sol.sbc.org.br/index.php/stil/article/view/37846
- Brant et al. 2026 (ENEM): https://arxiv.org/abs/2602.06631
- Junqueira et al., ERAMIA-RS 2025: https://sol.sbc.org.br/index.php/eramiars/article/view/39409
- Pirá: https://arxiv.org/abs/2202.02398 · https://github.com/C4AI/Pira
- Kuratomi et al. 2025 (assistente USP): https://arxiv.org/abs/2501.13880
- Garcia et al., PROPOR 2026: https://aclanthology.org/2026.propor-2.18/
- Ferraz et al., PROPOR 2026: https://aclanthology.org/2026.propor-1.12/
- Tucano: https://arxiv.org/abs/2411.07854
- Assis, Freitas & Paes, JBCS 2025: https://journals-sol.sbc.org.br/index.php/jbcs/article/view/5814

Modelos pequenos (busca dirigida, seção 3.7):
- Pandey et al. 2026: https://arxiv.org/abs/2603.11513 · https://arxiv.org/html/2603.11513
- Baturova et al., ECML PKDD 2026: https://arxiv.org/abs/2606.30062 · https://arxiv.org/html/2606.30062
- PRGB: https://arxiv.org/abs/2507.22927 · https://arxiv.org/html/2507.22927
- Yazan, Verberne & Situmeang, IR-RAG 2024: https://arxiv.org/abs/2406.10251
- Quantização em contexto longo: https://arxiv.org/abs/2505.20276 · https://github.com/molereddy/long-context-quantization
- Evaluating Quantized LLMs: https://arxiv.org/abs/2402.18158
- FaithEval: https://arxiv.org/abs/2410.03727
- Contextual entrainment: https://arxiv.org/abs/2604.13275
- Fouilhé, Asher & Muller 2026: https://arxiv.org/abs/2609.24238
- Zhang, Meng & Collier, ACL 2026: https://arxiv.org/abs/2601.12499
- ADeLe: https://arxiv.org/abs/2503.06378 · https://arxiv.org/html/2503.06378
- IRT-Router: https://arxiv.org/abs/2506.01048
- RAGRouter: https://arxiv.org/abs/2505.23052
- MiniRAG: https://arxiv.org/abs/2501.06713 · https://github.com/HKUDS/MiniRAG
- Froma et al. 2026: https://arxiv.org/abs/2605.00964
- MultiHop-RAG: https://arxiv.org/abs/2401.15391
- Qwen3 Technical Report: https://arxiv.org/abs/2505.09388

**Não verificado:**
- O conteúdo completo de Cronen-Townsend 2002 e Shtok 2012 (ACM bloqueou; só o registro bibliográfico via busca). Não cito números deles.
- Pré-recuperação clássica de He & Ounis (SPIRE 2004): o Springer redirecionou para login, então deixei fora da nota.
- O relatório completo NIST AI 800-3 (li só o resumo) e o PDF do survey de Benedetto et al. (só o registro ACM).
- Como os níveis `level` do HotpotQA foram atribuídos (o abstract não fala; só o dataset card confirma o campo).
- O número de equipes/sistemas usados no ajuste da IRT do LiveRAG.
- O conceito de IRT explicativa com covariáveis de item (LLTM / De Boeck & Wilson): citado de memória, sem fonte aberta nesta pesquisa.
- Qualquer limiar formal de "número mínimo de perguntas" para estimar variância de efeito aleatório; o 50–100 da seção 5.4 é uma estimativa de desenho, não um número da literatura.
- Ausência de trabalhos em PT-BR sobre dificuldade de pergunta em RAG: baseada em buscas web em inglês e português. Não consultei diretamente os anais do STIL/PROPOR/BRACIS.
- Tempo de execução das 7.200 respostas sugeridas no hardware do usuário.

Da busca dirigida a small models (seção 3.7):
- **Pandey et al. 2026** é preprint sem revisão por pares. Os números vêm do abstract e do HTML lidos via extração automática; não conferi as tabelas célula a célula. A página do arXiv cita "2 additional co-authors" cujos nomes não consegui ler.
- **Baturova et al.:** a ausência de quebra por tipo de pergunta vem da leitura do HTML (tabela 3 agregada). Não li apêndices nem o repositório suplementar, onde a quebra pode existir.
- **PRGB:** a quantização dos modelos não aparece no que li; não confirmei se há modelos abaixo de 7B em alguma tabela (Gemma3 "various sizes" pode incluir menores).
- **"Does quantization affect models' performance on long-context tasks?":** não anotei os autores; o venue EMNLP 2025 vem do README do repositório oficial, não da página do arXiv.
- **Li et al. 2024 (Evaluating Quantized LLMs):** só o abstract; não sei quais categorias de tarefa são mais sensíveis à quantização.
- **ADeLe:** o venue não foi confirmado; li o HTML via extração automática.
- **MiniRAG:** o "ACL 2026" vem do README do repositório; os modelos pequenos usados e o benchmark (nome, tipos de pergunta) não aparecem no abstract.
- **Zhang, Meng & Collier:** os nomes e tamanhos dos 5 LLMs não aparecem no abstract.
- **Froma et al.:** a família dos modelos de 3B/8B/70B e se há análise por tipo de pergunta ficaram ilegíveis na extração do PDF.
- **Garcia et al. e Ferraz et al. (PROPOR 2026):** as páginas da ACL Anthology não trazem os modelos; não abri os PDFs.
- **Tucano:** o abstract não lista os tamanhos da família; não verifiquei se forma uma escada útil para RAG.
- **"Enhancing Weak LLM Performance on Edge Devices Through RAG: A Benchmark Study"** (Springer, [DOI 10.1007/978-3-032-23271-7_18](https://link.springer.com/chapter/10.1007/978-3-032-23271-7_18)): apareceu na busca, mas o Springer redirecionou para login. Fica fora da nota.
- **RoseRAG** ([arXiv 2502.10993](https://arxiv.org/abs/2502.10993), robustez de RAG com LLMs pequenos via otimização de preferência) e **RARE** ([arXiv 2506.00789](https://arxiv.org/abs/2506.00789), robustez menor em multi-hop "across all domains"): vistos só pelo título/abstract; não verifiquei se analisam o tamanho.
- Não achei, nem em inglês nem em português, trabalho que cruze **features a priori da pergunta × tamanho do modelo × configuração RAG**. É ausência de evidência nas buscas feitas (web geral + arXiv/ACL), não prova.
- A estimativa de 1–2 dias para as condições oráculo/sem recuperação (seção 5.5) é minha, a partir da leitura do `orchestrator.py`; não fiz protótipo. Também não testei se o qwen3 8B cabe no perfil de memória `low`.
