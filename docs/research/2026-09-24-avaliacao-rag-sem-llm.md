# Avaliação de respostas RAG sem depender de LLM (ou do Gemini) no Ditto

Pesquisa feita em 2026-09-24. Versões consultadas nesta data: ragas v0.4.3 (release de 2026-01-13), bert-score 0.3.13, sacrebleu 2.6.0, ranx 0.3.21, rapidfuzz 3.14.6. As afirmações sobre métodos vêm dos artigos originais (arXiv/ACL Anthology), das model cards no Hugging Face e do código-fonte no GitHub. Cada afirmação tem link para a sua fonte.

---

## 1. Resumo e recomendação

**O diagnóstico muda o problema.** Hoje o Ditto **não usa um LLM como juiz**. As seis métricas registradas são similaridade de cosseno entre embeddings (5) e ROUGE-L caseiro (1) (seção 2). A cota do Gemini estoura por dois motivos:
1. `eval_embedding` tem **`"gemini"` como padrão** (`backend/app/experiments/schemas.py:35`). Todas as métricas de embedding chamam a API de embeddings do Gemini na etapa C.
2. `llms` também tem `["gemini"]` como padrão (`schemas.py:34`), então a geração das respostas consome a mesma chave.

Para parar de gastar cota **com a avaliação**, não é preciso criar nada: basta escolher `eval_embedding = "e5"` ou `"paraphrase"`, que rodam localmente. Mesmo assim, as métricas atuais têm limitações de validade que compensam acrescentar métodos melhores. Os nomes dizem "faithfulness" e "context_precision" como no RAGAS, mas cada uma é só um cosseno entre dois textos. No RAGAS original, essas métricas usam um LLM para extrair e verificar afirmações ([docs RAGAS faithfulness](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/faithfulness/)).

**Recomendação: acrescentar 5 métricas sem LLM, todas multilíngues/PT-BR e compatíveis com o perfil `low` (≤ 8 GB).**

| # | Métrica proposta (nome no registry) | Mede | Precisa de | Custo |
|---|---|---|---|---|
| 1 | `token_f1` (+ `exact_match`) estilo SQuAD, com normalização para PT | Correção vs. referência (léxica) | `resposta_referencia` | Zero (Python puro) |
| 2 | `chrf` (sacrebleu) | Correção vs. referência (caractere, robusta a flexão) | `resposta_referencia` | Zero (CPU, sem modelo) |
| 3 | `bertscore` com `xlm-roberta-base`/`bert-base-multilingual-cased` + baseline `pt` | Correção vs. referência (semântica, por token) | `resposta_referencia` | ~0,3B params, CPU ok |
| 4 | `nli_faithfulness` (NLI multilíngue mDeBERTa, agregação estilo SummaC) | Fidelidade/groundedness ao contexto | só contextos | ~0,3B params, CPU ok |
| 5 | `context_recall_gold` / `hit@k` / `mrr` (estilo RAGAS non-LLM + ranx) | Qualidade da recuperação | **evidência de referência por pergunta (não existe hoje)** | Zero |

Opção intermediária, fora do núcleo "sem LLM": **juiz LLM local** (MLX/Ollama, que o Ditto já roda). É **dependente de LLM, mas local**, então não gasta cota. Vale como terceira via, registrada como métrica separada e marcada assim na UI (seção 3.6).

Em paralelo, há duas correções baratas nas métricas existentes (seção 5.3): o prefixo `"query: "` do e5, e trocar o ROUGE-L caseiro por uma normalização que trate pontuação.

---

## 2. Como o Ditto avalia hoje

**Interface e registry.** `EvalSample` tem `question`, `answer`, `contexts: list[str]` e `reference_answer: str | None` (`backend/app/core/evaluation/base.py:9-15`). `Evaluator` expõe `requires_reference` e `score(sample) -> float` (`base.py:18-25`). As métricas são registradas em `evaluation_registry` (`base.py:28`), e `/options` lista o registry (`backend/app/api/options.py:73`). Uma métrica nova registrada aparece automaticamente na grade de experimentos.

**Métricas registradas** (`backend/app/core/evaluation/embedding_metrics.py:84-88`, `overlap_metrics.py:40`):

| Nome | Implementação real | Linha |
|---|---|---|
| `answer_relevancy` | cos(emb(resposta), emb(pergunta)) | `embedding_metrics.py:19-26` |
| `faithfulness` | cos(emb(resposta), emb(contextos concatenados)) | `embedding_metrics.py:29-38` |
| `context_precision` | média de cos(emb(pergunta), emb(contexto_i)) | `embedding_metrics.py:41-53` |
| `context_recall` | cos(emb(referência), emb(contextos concatenados)) | `embedding_metrics.py:56-67` |
| `answer_correctness` | cos(emb(resposta), emb(referência)) | `embedding_metrics.py:70-81` |
| `rouge_l` | LCS-F1 sobre `lower().split()` | `overlap_metrics.py:19-37` |

Nenhuma delas chama um LLM. Todas as de embedding usam o **embedder de avaliação** (`ExperimentConfig.eval_embedding`, padrão `"gemini"`, `schemas.py:35`).

**Execução.** `evaluate_sample` pula métricas com `requires_reference` quando não há referência e injeta o embedder só nas classes cujo `__init__` tem parâmetro `embedder` (`backend/app/core/evaluation/runner.py:25-53`). Um `_MemoEmbedder` evita embutir o mesmo texto duas vezes (`runner.py:8-22`). Com `staged=True` (padrão), a pontuação acontece na **etapa C**: o LLM local é descarregado, o embedder de avaliação é adquirido **uma vez** pelo `ModelManager` e todas as respostas guardadas são pontuadas (`backend/app/experiments/orchestrator.py:228-257`). Isso é importante para a recomendação, porque na etapa C a memória do LLM já foi liberada e cabe um modelo de avaliação local.

**Dados disponíveis por pergunta.** O CSV aceita `pergunta` e `resposta_referencia` (opcional) (`backend/app/experiments/csv_loader.py:8-20`). `database/perguntas.csv` tem 15 perguntas, **todas com resposta de referência** curta (1–2 frases, PT-BR, sem pontuação interna em alguns casos). **Não há passagens ou chunks de referência (gold).** Os contextos recuperados chegam como dicts com `source_doc`, `chunking_strategy`, `embedding_model`, `chunk_index` e `text` (`backend/app/ingestion/pipeline.py:49-57`). O `chunk_index` depende do chunker, então um ID de chunk não serve de rótulo estável entre combinações. O documento `database/faq_manus_completa.md` é dividido em 50 seções `### N. <pergunta>`, e as perguntas 1–11 do CSV são paráfrases das seções 1–11. Isso permite derivar evidência de referência **por texto** (seção 5.2).

**Memória.** Perfil `low`: `max_local_models=1`, embedders em CPU, concorrência ≤ 2 (`backend/app/core/memory/profile.py:24-27`). O `ModelManager` só gerencia **embedders** (`backend/app/core/memory/manager.py:58-67`), e o preflight já avisa quando o embedder de avaliação e o de busca são locais e diferentes (`backend/app/experiments/preflight.py:16-24`). Os embedders locais são `intfloat/multilingual-e5-small` (`e5`) e `paraphrase-multilingual-MiniLM-L12-v2` (`paraphrase`) (`backend/app/core/embedding/huggingface.py:48-60`).

**Achados colaterais.**
- `HuggingFaceEmbedder.embed_query` codifica o texto cru, sem prefixo (`huggingface.py:35-37`). A model card do e5 diz que o prefixo `"query: "` é necessário, "otherwise you will see a performance degradation", e recomenda `"query: "` nas duas pontas para similaridade simétrica ([model card](https://huggingface.co/intfloat/multilingual-e5-small)). A mesma card avisa que os cossenos do e5 se concentram entre **0,7 e 1,0** por causa da temperatura 0,01 do InfoNCE, e que "what matters is the relative order". Na prática, as métricas de cosseno com `e5` ficam comprimidas e ninguém deve ler 0,85 como "bom" em termos absolutos.
- O `rouge_l` usa `split()` por espaço, então `"cidade."` ≠ `"cidade"`. Isso penaliza pontuação.

---

## 3. Catálogo de métodos (agrupados pelo que medem)

### 3.1 Correção da resposta vs. referência: sobreposição léxica

**Exact Match e token-F1 (SQuAD).** O script oficial do SQuAD v1.1 normaliza (lowercase, remove pontuação, remove artigos **em inglês** `a|an|the`, colapsa espaços) e calcula F1 sobre o multiconjunto de tokens em comum ([evaluate-v1.1.py](https://raw.githubusercontent.com/allenai/bi-att-flow/master/squad/evaluate-v1.1.py); artigo SQuAD: [arXiv 1606.05250](https://arxiv.org/abs/1606.05250)).
- Entradas: resposta + referência. Custo zero. Python puro.
- PT-BR: é preciso trocar a lista de artigos (`o|a|os|as|um|uma|uns|umas`) e manter acentos. Com `str.lower()` o Python preserva á/ç.
- Limitação: EM é inútil para respostas longas geradas por LLM. Kamalloo et al. mostram que "lexical matching fails completely when a plausible candidate answer does not appear in the list of gold answers" e que mais da metade das falhas são respostas semanticamente equivalentes ([arXiv 2305.06984](https://arxiv.org/abs/2305.06984)). O token-F1 é mais tolerante, mas é penalizado por verbosidade (precisão cai).
- No RAGAS: `ExactMatch` e `StringPresence` ([docs non-LLM](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/traditional/)).

**ROUGE (L, 1, 2).** Definido por Lin 2004 para sumarização ([ACL W04-1013](https://aclanthology.org/W04-1013/)). O pacote de referência `rouge-score` (Google, Apache-2.0) **apaga caracteres não-ASCII**: o tokenizador troca `[^a-z0-9]+` por espaço ([tokenize.py](https://raw.githubusercontent.com/google-research/google-research/master/rouge/tokenize.py)). Assim, "não"→"n o" e "praça"→"pra a". O `RougeScore` do RAGAS instancia `RougeScorer([...], use_stemmer=True)` **sem tokenizer customizado** ([ragas `_rouge_score.py`](https://raw.githubusercontent.com/explodinggradients/ragas/main/src/ragas/metrics/_rouge_score.py)) e ainda aplica o stemmer Porter, que é para inglês. **Conclusão para PT-BR: não usar `rouge-score`/RAGAS `RougeScore` sem passar um tokenizer próprio.** O ROUGE-L caseiro do Ditto não tem esse bug, só o da pontuação.

**BLEU.** Precisão de n-gramas com penalidade de brevidade ([Papineni et al. 2002, ACL P02-1040](https://aclanthology.org/P02-1040/)). Foi desenhado para nível de corpus em tradução e é instável em frases curtas. Disponível em `sacrebleu` (Apache-2.0) ([GitHub](https://github.com/mjpost/sacrebleu)) e no RAGAS `BleuScore`. Pouco adequado para respostas de 1–3 frases.

**chrF.** F-score de n-gramas de **caractere** (ordem 6, β=2 no sacrebleu; chrF++ acrescenta bigramas de palavra) ([sacrebleu](https://github.com/mjpost/sacrebleu)). Popović (WMT 2015) afirma que ele "is absolutely language independent and also tokenisation independent" e leva em conta "some morpho-syntactic phenomena". A variante chrF3 teve as maiores correlações em nível de segmento no WMT14 para tradução a partir do inglês, superando as melhores métricas do shared task ([ACL W15-3049](https://aclanthology.org/W15-3049/)). Para o PT-BR, que tem flexão rica (plural, gênero, conjugação), n-gramas de caractere dão crédito parcial a "restaurante"/"restaurantes", coisa que o token-F1 não faz. API: `sacrebleu.sentence_chrf`. No RAGAS: `CHRFScore`.

**METEOR.** Alinhamento com exato → stem → sinônimo WordNet ([ACL W05-0909](https://aclanthology.org/W05-0909/)). A implementação do NLTK usa `PorterStemmer` e WordNet por padrão, ambos em inglês ([docs NLTK](https://www.nltk.org/api/nltk.translate.meteor_score.html)). Em PT-BR fica reduzido a match exato. **Não recomendado.**

**Similaridade de string (Levenshtein/Jaro).** `NonLLMStringSimilarity` do RAGAS, via `rapidfuzz` (MIT) ([docs](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/traditional/), [RapidFuzz](https://github.com/rapidfuzz/RapidFuzz)). Útil como bloco de construção (comparar chunk × evidência), fraco como métrica de resposta.

### 3.2 Correção da resposta vs. referência: semântica

**Similaridade de embeddings (SemScore / RAGAS Semantic Similarity).** É o que o `answer_correctness` do Ditto já faz. O RAGAS define a métrica como cosseno entre embeddings de referência e resposta, sem limiar ([docs](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/semantic_similarity/)). O SemScore (Aynetdinov & Akbik 2024) compara saídas com respostas-alvo via STS e relata que ela "outperforms all other, in many cases more complex, evaluation metrics in terms of correlation to human evaluation", em 12 LLMs instruction-tuned e 8 métricas ([arXiv 2401.17072](https://arxiv.org/abs/2401.17072)). **Isso valida a métrica atual**, desde que o embedder seja bom e seja usado corretamente (prefixo do e5).

**BERTScore.** Casa tokens do candidato e da referência por cosseno de embeddings contextuais e devolve P/R/F1 ([arXiv 1904.09675](https://arxiv.org/abs/1904.09675), ICLR 2020). Os autores afirmam que ele "correlates better with human judgments and provides stronger model selection performance than existing metrics" em 363 sistemas de tradução e legendagem (mesmo abstract). Pacote `bert-score` 0.3.13, MIT ([GitHub](https://github.com/Tiiiger/bert_score)).
- PT-BR: para línguas sem modelo próprio, o padrão é `bert-base-multilingual-cased` (mesmo README). **Existem baselines de reescala para `pt`** com `bert-base-multilingual-cased`, `xlm-roberta-base`, `xlm-roberta-large` e `xlm-mlm-100-1280` ([rescale_baseline/pt](https://github.com/Tiiiger/bert_score/tree/master/bert_score/rescale_baseline/pt)). `rescale_with_baseline` só deixa a escala mais legível e não muda a ordenação (README).
- Alternativa PT nativa: BERTimbau base (110M) / large (335M), MIT ([model card](https://huggingface.co/neuralmind/bert-base-portuguese-cased)). Não tem baseline de reescala pronto e exige escolher `num_layers` manualmente (não verificado qual camada rende melhor).
- Custo: base ≈ 0,1–0,3B params, roda em CPU. Cabe no perfil `low` na etapa C.

### 3.3 Fidelidade / groundedness (resposta ↔ contexto recuperado, sem referência)

**NLI (inferência textual) com agregação por sentença: SummaC.** Laban et al. mostram que NLI "não era competitivo" para detectar inconsistências por causa do descompasso de granularidade (sentença × documento). O SummaCConv segmenta em sentenças e agrega os escores por par, com "balanced accuracy of 74.4%" no benchmark SummaC ([arXiv 2111.09525](https://arxiv.org/abs/2111.09525), TACL 2022; [GitHub, Apache-2.0](https://github.com/tingofurro/summac)). O modelo NLI padrão (`vitc`) e os dados são em **inglês** (README). **A ideia transfere para PT trocando o NLI.**

**NLI multilíngue para PT-BR.** `MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7`: 0,3B params, MIT, 3 rótulos (entailment/neutral/contradiction), treinado em ~3,29 M pares em 27 línguas, **incluindo `pt`**. Não há acurácia específica para PT publicada ([model card](https://huggingface.co/MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7)). Alternativa mais leve: `MoritzLaurer/multilingual-MiniLMv2-L6-mnli-xnli`, ~107M params, MIT. **Português não aparece** na lista de línguas da card ([API HF](https://huggingface.co/api/models/MoritzLaurer/multilingual-MiniLMv2-L6-mnli-xnli)), então funcionaria só por transferência cross-lingual (não verificado).

**AlignScore.** Função de alinhamento treinada em 4,7 M exemplos de 7 tarefas. Os autores dizem que ela "matches or even outperforms metrics based on ChatGPT and GPT-4" ([arXiv 2305.16739](https://arxiv.org/abs/2305.16739), ACL 2023; [GitHub, MIT](https://github.com/yuh-zha/AlignScore)). Base RoBERTa (125M/355M) e segmentação com spaCy `en_core_web_sm`: **só inglês**. Não serve para PT-BR sem retreino.

**Vectara HHEM-2.1-Open.** Classificador (premissa, hipótese) → [0,1] sobre `flan-t5-base`, <600 MB em fp32, contexto ilimitado, ~1,5 s para 2k tokens em CPU x86, Apache-2.0. **A versão aberta é só inglês**; o PT é suportado apenas pela HHEM-2.3 comercial ([model card](https://huggingface.co/vectara/hallucination_evaluation_model)). O `FaithfulnesswithHHEM` do RAGAS **continua usando LLM** para extrair as afirmações (`assert self.llm is not None` antes de `_create_statements`) e só troca a verificação pelo HHEM ([ragas `_faithfulness.py`](https://raw.githubusercontent.com/explodinggradients/ragas/main/src/ragas/metrics/_faithfulness.py)). Portanto, não resolve o problema.

**QA-based (QAGS, QuestEval).** Geram perguntas a partir da resposta e respondem com o contexto ([QAGS, arXiv 2004.04228](https://arxiv.org/abs/2004.04228); [QuestEval, arXiv 2103.12693](https://arxiv.org/abs/2103.12693)). Dependem de modelos de geração e resposta de perguntas treinados em inglês, e cada avaliação roda vários modelos seq2seq. Pesado para 8 GB e sem suporte a PT. **Não recomendado.**

**Sobreposição resposta↔contexto (heurística).** Fração dos tokens de conteúdo (ou n-gramas de caractere, via chrF com o contexto como "referência") da resposta que aparecem no contexto. É o equivalente léxico barato da groundedness: detecta alucinação de entidades (nomes e horários inventados), mas não detecta negação nem paráfrase. Não achei fonte primária que valide essa heurística como métrica isolada, então ela deve ser tratada como diagnóstico, não como métrica da tese.

### 3.4 Relevância da resposta à pergunta (sem referência)

O RAGAS `answer_relevancy` original gera perguntas a partir da resposta com um LLM ([arXiv 2309.15217](https://arxiv.org/abs/2309.15217)). Sem LLM sobram:
- **Cosseno pergunta↔resposta com bi-encoder** (o `answer_relevancy` atual). Mede proximidade de tópico, não se a pergunta foi respondida.
- **Cross-encoder de reranking** como juiz de relevância: `BAAI/bge-reranker-v2-m3` recebe (pergunta, texto) e devolve um escore que "can be mapped to a float value in [0,1] by sigmoid". É multilíngue, Apache-2.0, ~568M params ([model card](https://huggingface.co/BAAI/bge-reranker-v2-m3)). Foi treinado para relevância pergunta↔passagem, não para qualidade de resposta, então usá-lo para avaliar respostas é extrapolação (não verificado na literatura). Serviria melhor como `context_precision` (pergunta↔chunk) que o cosseno atual.

### 3.5 Qualidade da recuperação

**Com rótulos de relevância (gold):** Recall@k, Hit@k, MRR, nDCG, MAP, implementados no `ranx` (MIT, qrels/run como dicts, Numba) ([GitHub](https://github.com/AmenRa/ranx)). O RAGAS tem `IDBasedContextPrecision` = IDs corretos / IDs recuperados e `IDBasedContextRecall` = IDs de referência encontrados / total de referência ([precision](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/context_precision/), [recall](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/context_recall/)). Também tem `NonLLMContextPrecisionWithReference` e `NonLLMContextRecall`, que comparam o **texto** dos contextos recuperados com contextos de referência por distância de string (`rapidfuzz`) (mesmas páginas). **A variante por texto é a que cabe no Ditto**, porque os IDs de chunk mudam com o chunker.

**Ressalva da literatura:** Salemi & Zamani mostram que avaliar o retriever com rótulos de relevância consulta↔documento "shows a small correlation with the RAG system's downstream performance". A proposta deles (eRAG) usa o próprio LLM por documento ([arXiv 2404.13781](https://arxiv.org/abs/2404.13781)). Métricas de recuperação devem complementar, e não substituir, as de resposta.

**Sem gold:** o `context_precision` atual (cosseno pergunta↔chunk) é um proxy. Um cross-encoder (3.4) é um proxy melhor.

### 3.6 Opção intermediária: juiz LLM local (depende de LLM, mas não de cota)

Zheng et al.: juízes fortes (GPT-4) atingem "over 80% agreement" com humanos, no mesmo nível da concordância entre humanos, mas têm vieses de posição, verbosidade e autopromoção ([arXiv 2306.05685](https://arxiv.org/abs/2306.05685)). Juízes abertos especializados, como o Prometheus 2, relatam a "highest correlation and agreement with humans and proprietary LM judges among all tested open evaluator LMs" ([arXiv 2405.01535](https://arxiv.org/abs/2405.01535)). No Ditto, um juiz rodaria no servidor MLX/Ollama que já existe (ex.: Qwen2.5-7B-Instruct-4bit). **Riscos:** (a) modelos de 1,7–7B não foram validados como juízes em PT-BR nas fontes acima (não verificado); (b) viés de autopromoção quando o juiz é o mesmo modelo que gerou; (c) na etapa C seria preciso **recarregar** o LLM que acabou de ser descarregado (`orchestrator.py:230-232`), o que no perfil `low` exclui carregar também um modelo de avaliação local.

---

## 4. Tabela comparativa

| Método | Mede | Referência? | Outra entrada | PT-BR | Custo / memória | Pacote · licença | Evidência de correlação (fonte) |
|---|---|---|---|---|---|---|---|
| Exact Match | correção | sim | — | com normalização PT | zero | Python / RAGAS `ExactMatch` · Apache-2.0 | falha em respostas longas ([2305.06984](https://arxiv.org/abs/2305.06984)) |
| Token-F1 (SQuAD) | correção | sim | — | trocar artigos | zero | script SQuAD / próprio | idem, mais tolerante |
| ROUGE-L | correção | sim | — | **`rouge-score` apaga acentos** | zero | `rouge-score` · Apache-2.0 | sumarização ([W04-1013](https://aclanthology.org/W04-1013/)) |
| BLEU | correção | sim | — | ok (sacrebleu) | zero | `sacrebleu` · Apache-2.0 | nível de corpus ([P02-1040](https://aclanthology.org/P02-1040/)) |
| **chrF / chrF++** | correção | sim | — | **bom (independe de língua/tokenização)** | zero | `sacrebleu` · Apache-2.0 | melhor segmento WMT14 ([W15-3049](https://aclanthology.org/W15-3049/)) |
| METEOR | correção | sim | — | ruim (WordNet/Porter EN) | zero | `nltk` | — |
| Cosseno de embeddings (SemScore) | correção | sim | — | depende do embedder (e5/paraphrase ok) | já carregado | atual | melhor correlação entre 8 métricas ([2401.17072](https://arxiv.org/abs/2401.17072)) |
| **BERTScore** | correção | sim | — | mBERT/XLM-R com baseline `pt` | 0,1–0,3B, CPU | `bert-score` · MIT | > métricas anteriores ([1904.09675](https://arxiv.org/abs/1904.09675)) |
| **NLI + agregação SummaC (mDeBERTa)** | fidelidade | não | contextos | **sim (27 línguas, inclui pt)** | 0,3B, CPU | `transformers` · MIT (modelo) | 74,4% bal. acc. em EN ([2111.09525](https://arxiv.org/abs/2111.09525)); PT não medido |
| AlignScore | fidelidade | não | contextos | não (EN) | 125–355M | MIT | ≈ GPT-4 em EN ([2305.16739](https://arxiv.org/abs/2305.16739)) |
| HHEM-2.1-Open | fidelidade | não | contextos | não (PT só na versão paga) | <600 MB | Apache-2.0 | ([card](https://huggingface.co/vectara/hallucination_evaluation_model)) |
| QAGS / QuestEval | fidelidade | não | contextos | não | vários seq2seq | — | ([2004.04228](https://arxiv.org/abs/2004.04228), [2103.12693](https://arxiv.org/abs/2103.12693)) |
| Sobreposição resposta↔contexto | fidelidade (léxica) | não | contextos | sim | zero | próprio | sem validação primária |
| Cross-encoder (bge-reranker-v2-m3) | relevância / precisão de contexto | não | pergunta | sim | ~568M | Apache-2.0 | treinado p/ ranking, não p/ avaliação |
| **Recall@k / Hit@k / MRR / nDCG (gold por texto)** | recuperação | **evidência gold** | contextos | sim | zero | `ranx` · MIT; `rapidfuzz` · MIT | baixa correlação com downstream ([2404.13781](https://arxiv.org/abs/2404.13781)) |
| Juiz LLM local | tudo | opcional | todos | depende do modelo | LLM 1,7–7B | MLX/Ollama | >80% com GPT-4 ([2306.05685](https://arxiv.org/abs/2306.05685)); pequenos não verificados |

---

## 5. Recomendação para o Ditto

### 5.1 As cinco métricas e como encaixam (sem mudar código agora, só o desenho)

Todas seguem a convenção **interface + registry**: uma classe `Evaluator` com `score(sample)` e `requires_reference`, registrada em `evaluation_registry` e importada em `backend/app/core/evaluation/__init__.py`, que já é importado em `main.py` para o registro. Assim, `/options` passa a listá-las sozinho.

1. **`token_f1` e `exact_match`** → novo `overlap_metrics.py` (ao lado do `RougeL`). `requires_reference = True`, sem `__init__` com `embedder`, então o runner as instancia sem argumentos (`runner.py:50-51`). Uma função `_normalize_pt` compartilhada (lowercase, remove pontuação Unicode, remove artigos PT, colapsa espaços) também serviria para corrigir a pontuação do `rouge_l`.
2. **`chrf`** → mesma família, `sacrebleu.sentence_chrf(answer, [reference]).score / 100`. Nova dependência leve (`sacrebleu`) no grupo principal, sem torch.
3. **`bertscore`** → nova classe que precisa de um modelo local. **Aqui a interface atual não basta:** o runner só sabe injetar `embedder` (detectado por `inspect.signature`, `runner.py:25-31`). Duas opções de desenho:
   - (a) generalizar a injeção: o runner passa a reconhecer outros parâmetros nomeados (ex.: `scorer_model`) e o orquestrador adquire esse modelo pelo `ModelManager` na etapa C, igual faz com `config.eval_embedding` (`orchestrator.py:242-248`);
   - (b) a própria classe carrega o modelo de forma preguiçosa, num cache de módulo. É mais simples, mas fica **fora** do `ModelManager` e do limite `max_local_models`, o que contraria a regra de "todo modelo passa por ele".
   Recomendo (a). O `ModelManager` hoje é tipado para `Embedder` (`manager.py:12, 58`), então precisaria aceitar "modelos de avaliação" genéricos (factory + `is_local`). Deve ficar no grupo opcional `local` do `pyproject.toml`, porque depende de torch.
4. **`nli_faithfulness`** → mesma infraestrutura do item 3, com o modelo `mDeBERTa-v3-base-xnli-multilingual-nli-2mil7`. Algoritmo estilo SummaC-ZS: dividir a resposta em sentenças (regex, sem spaCy), dividir os contextos em sentenças ou janelas curtas, e para cada sentença da resposta tomar o **máximo** de P(entailment) sobre as premissas. O escore final é a **média** entre as sentenças. `requires_reference = False`. Escolhi este modelo, e não AlignScore/HHEM, porque é o único dos três com PT no treino.
5. **Recuperação com gold por texto** (`context_recall_gold`, `context_hit_at_k`, `context_mrr`) → requer dados novos (5.2). Uma nova coluna opcional no CSV (ex.: `evidencia_referencia`, trecho literal do FAQ) → `QuestionItem.reference_contexts` → `EvalSample.reference_contexts: list[str] | None`. Um chunk recuperado conta como relevante se `rapidfuzz.fuzz.partial_ratio(evidência, chunk) ≥ limiar` ou se a cobertura de tokens da evidência passa de X. Esse é o mecanismo do `NonLLMContextRecall` do RAGAS, e funciona para qualquer chunker. Precisa de um atributo novo tipo `requires_reference_contexts`, para o runner pular a métrica quando a coluna faltar (como já faz com `requires_reference`, `runner.py:44-45`). Os contextos chegam **na ordem do retriever**, então MRR e Hit@k saem direto. Não é preciso usar `ranx` para 15 perguntas, mas ele serve para testes de significância entre combinações.

**Memória (perfil `low`).** Na etapa C o LLM já foi descarregado (`orchestrator.py:230-232`). Com `max_local_models=1`, carregar em sequência o embedder de avaliação, depois o BERTScore e depois o NLI (um por vez, cada um liberado antes do próximo) cabe folgado: cada modelo tem ≤ 0,3B params, cerca de 1,2 GB em fp32. Isso exige que a etapa C pontue **por modelo** (todas as linhas com o modelo A, libera, todas com o B), e não por linha. Hoje ela já itera linhas dentro de um único `with` (`orchestrator.py:248-256`).

### 5.2 Criar a evidência de referência (gold) para o FAQ

As perguntas 1–11 de `perguntas.csv` correspondem às seções `### 1.`–`### 11.` de `faq_manus_completa.md`. As 12–15 (atrações, cachoeira, hospedagem, como chegar de SP) aparecem em seções como 26, 27 e 42 e precisam de conferência manual. Anotar 1–2 frases literais do FAQ por pergunta leva poucos minutos para 15 perguntas e destrava toda a família de métricas de recuperação. Usar o texto, e não o `chunk_index`, mantém o gold válido para todos os chunkers.

### 5.3 Ajustes baratos nas métricas existentes

- Mudar o padrão de `eval_embedding` para um embedder local, ou avisar na UI que `"gemini"` consome cota. Hoje o preflight sugere o próprio Gemini como forma de economizar memória (`preflight.py:23`).
- e5: prefixar `"query: "` nos dois lados nas métricas de similaridade (recomendação da model card) e documentar que os valores ficam na faixa 0,7–1,0. Para comparar combinações, isso importa menos do que parece, porque a ordem é preservada.
- `rouge_l`: normalizar pontuação antes do `split()`.
- Renomear ou documentar na UI que `faithfulness`, `context_precision` etc. são **proxies de cosseno** e não as métricas homônimas do RAGAS. A distinção importa na tese.

---

## 6. Questões em aberto

1. **Evidência gold:** quem anota e com qual granularidade (frase, parágrafo, seção)? Sem isso, o item 5 da recomendação fica bloqueado.
2. **Referências curtas × respostas longas:** as referências do CSV têm 1–2 frases, e o LLM tende a responder mais longo. Token-F1 e ROUGE punem a verbosidade pela precisão. Vale reportar **recall** separado de F1 para essas métricas?
3. **Validação em PT-BR:** nenhuma das fontes mede a correlação com julgamento humano de BERTScore, chrF ou NLI em **QA em português**. Para a tese, anotar manualmente uma amostra (ex.: 50 respostas × nota 1–5) e calcular Spearman/Kendall contra cada métrica justifica a escolha. As conversas salvas "para avaliação humana" (`backend/app/core/db/models.py:83`) podem ser o embrião disso.
4. **Limiar do fuzzy match** para "chunk relevante" (partial_ratio ≥ 80? cobertura ≥ 0,5?) precisa de calibração em alguns casos à mão.
5. **Tamanho do contexto no NLI:** a janela máxima do mDeBERTa não foi verificada na model card. Contextos longos precisam ser fatiados, e o número de pares (sentenças da resposta × premissas) define o tempo em CPU.
6. **Juiz local:** vale como métrica da tese? Só com validação contra a amostra humana do item 3 e com juiz ≠ gerador.
7. **Geração continua no Gemini:** as métricas novas eliminam a cota **da avaliação**. A geração só deixa de gastar cota escolhendo LLMs locais em `llms`.

---

## 7. Fontes

Código do Ditto (lido em 2026-09-24, commit `b07f64e`):
- `backend/app/core/evaluation/{base,embedding_metrics,overlap_metrics,runner}.py`, `backend/app/experiments/{schemas,orchestrator,preflight,csv_loader}.py`, `backend/app/core/memory/{profile,manager}.py`, `backend/app/core/embedding/huggingface.py`, `backend/app/ingestion/pipeline.py`, `database/perguntas.csv`, `database/faq_manus_completa.md`

Primárias:
- RAGAS, artigo: https://arxiv.org/abs/2309.15217 · métricas non-LLM: https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/traditional/ · semantic similarity: https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/semantic_similarity/ · context precision: https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/context_precision/ · context recall: https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/context_recall/ · faithfulness: https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/faithfulness/
- RAGAS código: https://raw.githubusercontent.com/explodinggradients/ragas/main/src/ragas/metrics/_rouge_score.py · https://raw.githubusercontent.com/explodinggradients/ragas/main/src/ragas/metrics/_faithfulness.py · repo (Apache-2.0): https://github.com/explodinggradients/ragas
- SQuAD: https://arxiv.org/abs/1606.05250 · script: https://raw.githubusercontent.com/allenai/bi-att-flow/master/squad/evaluate-v1.1.py
- Kamalloo et al. 2023: https://arxiv.org/abs/2305.06984
- ROUGE: https://aclanthology.org/W04-1013/ · tokenizador `rouge-score`: https://raw.githubusercontent.com/google-research/google-research/master/rouge/tokenize.py
- BLEU: https://aclanthology.org/P02-1040/
- chrF: https://aclanthology.org/W15-3049/ · sacrebleu: https://github.com/mjpost/sacrebleu
- METEOR: https://aclanthology.org/W05-0909/ · NLTK: https://www.nltk.org/api/nltk.translate.meteor_score.html
- SemScore: https://arxiv.org/abs/2401.17072
- BERTScore: https://arxiv.org/abs/1904.09675 · https://github.com/Tiiiger/bert_score · baselines pt: https://github.com/Tiiiger/bert_score/tree/master/bert_score/rescale_baseline/pt
- BERTimbau: https://huggingface.co/neuralmind/bert-base-portuguese-cased
- SummaC: https://arxiv.org/abs/2111.09525 · https://github.com/tingofurro/summac
- AlignScore: https://arxiv.org/abs/2305.16739 · https://github.com/yuh-zha/AlignScore
- HHEM: https://huggingface.co/vectara/hallucination_evaluation_model
- QAGS: https://arxiv.org/abs/2004.04228 · QuestEval: https://arxiv.org/abs/2103.12693
- NLI multilíngue: https://huggingface.co/MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7 · https://huggingface.co/MoritzLaurer/multilingual-MiniLMv2-L6-mnli-xnli
- multilingual-e5-small: https://huggingface.co/intfloat/multilingual-e5-small
- bge-reranker-v2-m3: https://huggingface.co/BAAI/bge-reranker-v2-m3
- ranx: https://github.com/AmenRa/ranx · RapidFuzz: https://github.com/rapidfuzz/RapidFuzz
- eRAG: https://arxiv.org/abs/2404.13781
- LLM-as-a-judge: https://arxiv.org/abs/2306.05685 · Prometheus 2: https://arxiv.org/abs/2405.01535

Não verificado:
- Correlação com julgamento humano de qualquer uma dessas métricas em QA/RAG **em português**.
- Acurácia do mDeBERTa-xnli em PT (a card não publica) e sua janela máxima de tokens.
- Desempenho de LLMs pequenos (1,7–7B) como juízes em PT-BR.
- Melhor camada (`num_layers`) do BERTimbau para BERTScore.
- Uso do bge-reranker como juiz de relevância de **respostas** (só foi treinado para passagens).
