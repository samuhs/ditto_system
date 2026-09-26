# Formatação da base de dados para RAG: o que a literatura recomenda e o que mudar em `faq_manus_completa.md`

Pesquisa feita em 2026-09-26. As afirmações sobre métodos vêm dos artigos originais (arXiv, ACL Anthology, anais de conferência), de documentação oficial (LangChain, Unstructured, Microsoft Learn, model card do e5 no Hugging Face) e do post técnico da Anthropic sobre Contextual Retrieval. Cada afirmação tem link para a fonte. Cada recomendação traz um **nível de evidência**:

- **forte**: resultado empírico publicado, com comparação controlada, em mais de um conjunto de dados;
- **misto**: há resultado empírico, mas em um domínio, com resultados contraditórios ou longe do nosso cenário (outra língua, outro tipo de documento);
- **só fornecedor**: guia de fornecedor ou de ferramenta, sem experimento publicado que o sustente;
- **conjectura**: raciocínio meu, sem fonte direta.

---

## 1. Resumo e recomendação

**A pergunta tem duas metades que é bom separar.** Uma parte do que se chama "formatar os dados" é propriedade do **documento** (o que está escrito e como). A outra parte é propriedade do **pipeline** (como o chunker corta, o que vai no payload, como o embedder é chamado). No Ditto, os problemas maiores de hoje estão no pipeline (seção 2). O chunker `recursive` junta 2–3 pares pergunta/resposta num chunk e às vezes separa uma lista do título dela. O payload não guarda o título da seção. O `e5` roda sem os prefixos `passage: `/`query: `. Nenhuma reescrita do arquivo resolve isso por completo.

**Do lado do documento, a literatura converge em quatro pontos**, com força de evidência desigual:

| # | Princípio | Evidência | Onde bate no `faq_manus_completa.md` |
|---|---|---|---|
| 1 | Cada unidade recuperável deve ser **autocontida**: entidade explícita, sem "lá", "isso", "como mencionei" | forte (Dense X) + misto (correferência) + fornecedor com números (Contextual Retrieval) | L15, L137–140, L146–149, L173, L241 |
| 2 | **Estrutura explícita e consistente** (um cabeçalho por unidade, listas presas ao título) que o chunker consiga respeitar | misto (chunking por elemento em relatórios financeiros) + fornecedor (Unstructured, LangChain) | já existe `###` por pergunta; listas em L85–92, L131–135, L181–187 |
| 3 | **Em FAQ, a pergunta é o sinal mais forte**: título fiel ao conteúdo e, se possível, paráfrases | forte para FAQ retrieval (Karan & Šnajder; Mass et al.), mas em inglês e pré-LLM | L43 (título "lojas", resposta sobre Ilha do Ar/AiJapa), L231 (resto de template) |
| 4 | **Remover ruído** que não carrega significado (marcadores de citação órfãos, saudações, datas relativas) e **explicitar metadados** (fonte, data, entidades) | misto (ruído de formatação degrada RAG em OHRBench, mas é ruído de OCR) + fornecedor (Azure) | 63 marcadores `[n]` sem lista de fontes; L3, L243; "Outubro de 2025" em L139/L148 |

**Recomendação metodológica (a mais importante para a tese).** A proposta do Ditto é achar a melhor configuração para *qualquer* base crua. Se a base de referência for reescrita à mão, o resultado deixa de valer para bases cruas e o ganho da reescrita se mistura ao ganho do chunker/retriever. A literatura sobre sensibilidade a formato recomenda **relatar a faixa de desempenho entre formatos plausíveis** em vez de fixar um só ([Sclar et al., ICLR 2024](https://arxiv.org/abs/2310.11324)). Por isso a sugestão é **não substituir** o arquivo, e sim tratar o formato como **mais um eixo do experimento**: `raw` (o arquivo de hoje), `limpo` (mesmo conteúdo, sem ruído) e `autocontido` (um registro por par pergunta/resposta, com contexto explícito). Esse eixo pode entrar no produto cartesiano como uma técnica plugável (`interface + registry`, como o resto do Ditto) e ser aplicado a qualquer base nova (seção 6).

---

## 2. Como o Ditto ingere documentos hoje

**Entrada.** `/ingest` recebe arquivos, exige UTF-8 e cria um `Document(name, text)` com o texto inteiro, sem parsing de Markdown (`backend/app/api/ingest.py:61-72`, `backend/app/ingestion/schemas.py:5-9`). O Markdown chega aos chunkers como texto cru, com `###`, `**` e `*` dentro.

**Chunkers registrados** (`backend/app/core/chunking/splitters.py:11-57`, `semantic.py:11-39`):
- `fixed`: janelas de 1000 caracteres, overlap 100, `separator=""` (corta no meio de palavra);
- `recursive`: `RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)` com os separadores padrão (`"\n\n"`, `"\n"`, `" "`, `""`), que não conhecem cabeçalhos Markdown;
- `token`: 256 tokens `cl100k_base`, overlap 20;
- `semantic`: quebra entre frases quando a distância de cosseno passa de 0,5.

Nenhum deles é *structure-aware* (não existe um `MarkdownHeaderTextSplitter` ou similar).

**Payload no Qdrant.** Cada chunk guarda só `source_doc`, `chunking_strategy`, `embedding_model`, `chunk_index` e `text` (`backend/app/ingestion/pipeline.py:49-57`). Não há título da seção, id do par pergunta/resposta, fonte ou data.

**Embedder local.** `HuggingFaceEmbedder.embed_documents` e `embed_query` codificam o texto sem prefixo (`backend/app/core/embedding/huggingface.py:27-37`). A model card do `multilingual-e5-small` diz: "Each input text should start with "query: " or "passage: ", even for non-English texts" e, na FAQ da card, que sem isso "you will see a performance degradation" ([model card](https://huggingface.co/intfloat/multilingual-e5-small)). A mesma card avisa que textos longos são truncados em 512 tokens. Isso já foi apontado em [2026-09-24-avaliacao-rag-sem-llm.md](2026-09-24-avaliacao-rag-sem-llm.md). Aqui só registro que o problema vale também para os **documentos**, não só para as consultas.

**O que o `recursive` faz com este arquivo.** O arquivo tem 25.147 caracteres e 50 seções `### N.`. A menor tem 274 caracteres, a maior 990, e a mediana fica em 463. Rodei o splitter do projeto (`chunk_size=1000`, `overlap=100`) sobre o arquivo e saíram **32 chunks**:
- A maioria mistura **2 ou 3 pares** pergunta/resposta (por exemplo, o chunk 3 tem as seções 4, 5 e 6). O embedding do chunk vira uma média de assuntos distintos.
- Três chunks **começam no meio de uma lista, sem o título dela**: o chunk 12 abre em "Santo Antônio da Alegria oferece várias opções gratuitas!" (seção 20, L85), o chunk 17 em "*   **Altinópolis (aprox. 30 km):**" (seção 27, L133) e o chunk 23 em "Para se integrar bem..." (seção 38, L181). Nesses casos o item "Visitar a **Ilha do Ar**" chega ao LLM sem a informação de que a lista é de atividades **gratuitas**.

Esse é o ponto de partida concreto. A seção 5 separa o que se resolve no arquivo e o que se resolve no pipeline.

**Avaliação que depende do texto do arquivo.** `database/perguntas.csv` tem a coluna `evidencia_referencia`, com trechos copiados literalmente do arquivo (inclusive os marcadores `[1]`). As métricas gold procuram esses trechos nos chunks por alinhamento aproximado (`rapidfuzz.partial_ratio ≥ 80`, depois de normalizar pontuação e Markdown) (`backend/app/core/evaluation/gold_metrics.py:14-32`). Tirar `**` ou `[1]` não quebra o alinhamento. **Reescrever frases** (resolver correferência, trocar "nossa cidade" por "Santo Antônio da Alegria") pode baixar o `partial_ratio` abaixo de 80 e zerar o acerto sem que a recuperação tenha piorado. Qualquer versão reescrita do arquivo precisa ter a evidência reanotada para o seu próprio texto.

---

## 3. O que a literatura diz

### 3.1 Estrutura e marcação: Markdown, HTML, texto puro, JSON

**Para o LLM ler, preservar estrutura ajuda.** O HtmlRAG (WWW 2025) compara passar o conhecimento recuperado ao LLM como HTML limpo, texto puro ou Markdown, em seis datasets de QA. Os autores concluem que HTML "is better than plain text" porque preserva cabeçalhos e tabelas que o texto puro perde ([Tan et al., arXiv 2411.02959](https://arxiv.org/abs/2411.02959)). Para tabelas, Sui et al. compararam NL+separadores, Markdown, JSON, XML e HTML. HTML ganhou, com "a 6.76% improvement" sobre NL+Sep, e os autores atribuem isso à quantidade de HTML e código no pré-treino ([Table Meets LLM, WSDM 2024, arXiv 2305.13062](https://arxiv.org/abs/2305.13062)).

**O formato em si muda o resultado, e o efeito depende do modelo.** He et al. testaram texto puro, Markdown, JSON e YAML nos prompts. O GPT-3.5-turbo variou "up to 40%" numa tarefa de tradução de código, e o GPT-4 foi mais robusto ([arXiv 2411.10541](https://arxiv.org/abs/2411.10541)). Sclar et al. mediram "performance differences of up to 76 accuracy points" no LLaMA-2-13B só trocando formatação. Eles viram que o melhor formato de um modelo não é o melhor do outro e recomendam relatar a faixa de desempenho em vários formatos ([ICLR 2024, arXiv 2310.11324](https://arxiv.org/abs/2310.11324)). Esses dois estudos são sobre **prompts**, não sobre a base indexada. Servem de analogia e justificam tratar o formato como variável, mas não dizem qual formato é melhor para uma base de FAQ.

**Lacuna.** Não achei estudo controlado que compare Markdown com texto puro **para o embedding** em retrieval denso. Os resultados acima são sobre o que o LLM lê. Se `**negrito**` e `###` ajudam ou atrapalham o `e5`, só um experimento nosso responde. É mais um motivo para o eixo de formato (seção 6).

### 3.2 Unidades autocontidas ("atômicas")

**Proposições.** Dense X Retrieval (EMNLP 2024) define proposições como "atomic expressions within text, each encapsulating a distinct factoid and presented in a concise, self-contained natural language format". Indexar a Wikipédia por proposições em vez de passagens aumentou o Recall@5 em +12,0 pontos (SimCSE) e +9,3 (Contriever). Com retrievers supervisionados o ganho foi pequeno dentro da distribuição, mas grande em dados não vistos (SQuAD: +25% de Recall@5 com DPR). No QA com orçamento de tokens, o ganho foi de cerca de +2,8 a +4,1 EM. O ganho é maior para entidades raras ("long-tailed information"). Para gerar as proposições foi preciso **resolver pronomes e correferências** ([Chen et al., arXiv 2312.06648](https://arxiv.org/abs/2312.06648); números da [versão HTML](https://arxiv.org/html/2312.06648)). Limites: só Wikipédia em inglês e só retrievers densos de duas torres. O nosso caso (FAQ turístico em PT-BR, entidades locais raras) é justamente de cauda longa, o que puxa a favor. É uma extrapolação.

**Correferência.** Jang et al. (ACL 2025 SRW) resolveram correferências nos documentos antes do RAG e relatam melhora na recuperação e no QA. O ganho é maior em modelos menores ([arXiv 2507.07847](https://arxiv.org/abs/2507.07847)). É um workshop de estudantes, então conta como evidência moderada. A direção bate com o Dense X, e o Ditto roda LLMs locais pequenos, justamente o caso em que o efeito foi maior.

**Contexto do documento no chunk.** O post de Contextual Retrieval da Anthropic gera, com um LLM, 50–100 tokens de contexto por chunk e os antepõe antes de embutir e indexar no BM25. A falha de recuperação top-20 caiu 35% com embeddings contextuais (5,7% → 3,7%), 49% somando BM25 contextual (→ 2,9%) e 67% com rerank (→ 1,9%) ([Anthropic, "Introducing Contextual Retrieval"](https://www.anthropic.com/news/contextual-retrieval)). É um relatório de fornecedor, com números mas sem revisão por pares. Merola & Singh (workshop KEIR @ ECIR 2025) compararam contextual retrieval com late chunking. A conclusão: contextual retrieval "preserves semantic coherence more effectively but requires greater computational resources", e late chunking é mais barato, mas perde relevância e completude ([arXiv 2504.19754](https://arxiv.org/abs/2504.19754)).

**Late chunking** embute o documento inteiro num modelo de contexto longo e só depois faz o pooling por chunk. Nos BeIR testados, o nDCG@10 médio subiu de 52,2 para 54,0 com janelas fixas. O ganho é maior com chunks pequenos e documentos longos e some com chunks grandes ([Günther et al., arXiv 2409.04701](https://arxiv.org/abs/2409.04701)). É técnica de **pipeline** e exige um embedder de contexto longo (o `e5-small` trunca em 512 tokens). Fica aqui só para mostrar que o problema "chunk sem contexto" pode ser atacado dos dois lados.

**RAPTOR** (resumos hierárquicos recursivos) deu +20% absoluto no QuALITY com GPT-4 ([Sarthi et al., arXiv 2401.18059](https://arxiv.org/abs/2401.18059)). Foi pensado para documentos longos com raciocínio de vários passos. Um FAQ de 50 pares curtos não é esse caso. É técnica de pipeline e fora do escopo aqui.

### 3.3 Tamanho, fronteiras e estrutura do chunk

- **Chunking por elemento estrutural.** Em relatórios financeiros (FinanceBench), cortar por elemento do documento (título, parágrafo, tabela) deu 53,19% de acurácia de QA contra 48,23% do melhor chunking por tokens (512), e 84,4% contra 68,09% de recuperação por página ([Jimeno Yepes et al., arXiv 2402.05131](https://arxiv.org/abs/2402.05131); números da [versão HTML](https://arxiv.org/html/2402.05131)). É um domínio só, mas a evidência a favor de respeitar a estrutura é direta.
- **Ferramentas.** O `by_title` do Unstructured garante que "a single chunk will never contain text that occurred in two different sections", nunca junta tabelas com outro conteúdo e combina seções pequenas até encher a janela ([docs Unstructured](https://docs.unstructured.io/open-source/core-functionality/chunking)). O `MarkdownHeaderTextSplitter` da LangChain faz chunks "within specific header groups" e põe os cabeçalhos no metadata ([docs LangChain](https://docs.langchain.com/oss/python/integrations/splitters/markdown_header_metadata_splitter)). Essas duas são só guia de ferramenta, mas dão a direção: **a estrutura só ajuda se o chunker a ler**.
- **Tamanho.** A Chroma mediu recall e precisão por token e achou até 9% de diferença de recall entre estratégias. O `RecursiveCharacterTextSplitter` com 200 tokens sem overlap ficou entre os melhores, e o padrão da OpenAI (800 tokens, overlap 400) teve "the lowest scores across all other metrics" ([Smith & Troynikov, Chroma, jul/2024](https://www.trychroma.com/research/evaluating-chunking)). Bhat et al. acharam que datasets factuais de resposta curta preferem chunks pequenos (64–128 tokens) e que a preferência depende também do embedder ([arXiv 2505.21700](https://arxiv.org/abs/2505.21700)). As respostas do FAQ têm entre ~70 e ~250 tokens. Um par por chunk está na faixa "pequena a média". Juntar três pares num chunk de 1000 caracteres, como hoje, sai dela.
- **Chunking semântico.** Qu, Tu & Bao (Vectara) acharam que o chunking semântico só ganhou em documentos artificialmente costurados com alta variedade de tópicos. Em documentos reais, "fixed-size chunking remains a more efficient and reliable choice" ([arXiv 2410.13070](https://arxiv.org/abs/2410.13070)). Para um FAQ que já tem fronteiras explícitas, o `semantic` provavelmente perde para cortar pela estrutura. Isso é inferência minha.

### 3.4 FAQ: pergunta contra pergunta, pergunta contra resposta

A literatura de FAQ retrieval separa casar a consulta com a **pergunta** do FAQ (q-Q) e casar com a **resposta** (q-A). Sakata et al. (SIGIR 2019) combinam BM25/TSUBAKI entre consulta e pergunta com um BERT entre consulta e resposta ([arXiv 1905.02851](https://arxiv.org/abs/1905.02851)). Mass et al. (ACL 2020) treinam os dois modelos sem supervisão e geram paráfrases das perguntas com GPT-2. Nos resultados, "BERT-Q-q was the best" (FAQIR: P@5 0,67 contra 0,54 do melhor re-ranker baseado no texto). Os autores escrevem que isso "confirms previous findings (Karan and Šnajder, 2016), that Q-to-q matching gives the best signal in FAQ retrieval". A fusão dos dois sinais foi ainda melhor ([Mass et al., ACL 2020](https://aclanthology.org/2020.acl-main.74/)).

Duas consequências para o dado:
1. **O texto da pergunta vale mais do que parece.** Um título que não corresponde à resposta, como a seção 10 (L43, "horário de funcionamento das **lojas**", com resposta sobre Ilha do Ar e AiJapa), prejudica justamente o sinal mais forte.
2. **Paráfrases ajudam.** Tanto Mass et al. (paráfrases geradas) quanto doc2query ([Nogueira et al., arXiv 1904.08375](https://arxiv.org/abs/1904.08375)) expandem a base com perguntas prováveis. O Doc2Query-- mostra que as expansões alucinam e que **filtrá-las** melhora a eficácia em até 16% e reduz o índice em 33% ([Gospodinov et al., ECIR 2023, arXiv 2301.03266](https://arxiv.org/abs/2301.03266)). HyDE é a versão do lado da consulta: gera um documento hipotético e busca por ele ([Gao et al., arXiv 2212.10496](https://arxiv.org/abs/2212.10496)). O Ditto já tem HyDE como técnica de RAG (`backend/app/core/rag/hyde.py`).

Limites: FAQIR e StackFAQ estão em inglês, são de fórum e usam BERT-base, sem embedders multilíngues nem LLM. A direção "q-Q é o sinal mais forte" é consistente entre os trabalhos. A magnitude no nosso cenário é desconhecida.

### 3.5 Limpeza, ruído e metadados

- **Ruído de formatação degrada RAG.** O OHRBench (ICCV 2025) separa ruído de OCR em "semantic noise" e "formatting noise" e mostra que o desempenho do RAG cai à medida que o ruído aumenta ([Zhang et al., arXiv 2412.02592](https://arxiv.org/abs/2412.02592)). O nosso arquivo não tem erros de OCR. O paralelo é com os marcadores `[n]` sem destino e o texto de persona, e isso é extrapolação.
- **Distratores parecidos atrapalham.** Cuconasu et al. (SIGIR 2024) mostram que passagens bem ranqueadas mas irrelevantes pioram a resposta, enquanto documentos aleatórios, surpreendentemente, podem melhorá-la ([arXiv 2401.14887](https://arxiv.org/abs/2401.14887)). A "Rua da Gastronomia" aparece em 18 linhas do arquivo e a "Ilha do Ar" em 12. Uma pergunta sobre comida recupera vários pares que mencionam a rua de passagem. O efeito é conjectura minha, mas a redundância é um fato do arquivo.
- **Guia da Microsoft** (Azure Architecture Center, fase de enriquecimento de chunks, atualizado em 2026). Recomenda corrigir grafia, expandir abreviações, normalizar texto e "Prefer localizing at the document level", e manter o chunk original num campo separado do chunk limpo que vai para o vetor. Para metadados sugere título, resumo, palavras-chave, entidades, fonte, idioma e "Questions that the chunk can answer". Também alerta que remover stop words e caracteres Unicode tem que ser testado, porque alguns carregam sentido ([Microsoft Learn](https://learn.microsoft.com/en-us/azure/architecture/ai-ml/guide/rag/rag-enrichment-phase)). O guia sugere ainda baixar a caixa do texto, mas isso não se aplica a embedders modernos multilíngues, cujo tokenizador já lida com maiúsculas. É guia de fornecedor sem experimento publicado.

---

## 4. Formato de dados ou pipeline?

| Problema observado | É do dado | É do pipeline | Onde resolver primeiro |
|---|---|---|---|
| Chunk com 2–3 pares misturados | não | `recursive` 1000 chars sem saber de `###` | pipeline: chunker por cabeçalho |
| Lista separada do título (chunks 12, 17, 23) | em parte (itens sem sujeito) | sim | pipeline + frase de abertura autocontida |
| Título da seção fora do payload | não | `pipeline.py:49-57` | pipeline |
| `e5` sem `passage: `/`query: ` | não | `huggingface.py:27-37` | pipeline |
| "até lá", "como mencionei", "nessa época" | **sim** | não | dado (ou contextualização automática) |
| Datas relativas ("data atual", "nesta semana") | **sim** | não | dado |
| Marcadores `[n]` sem lista de fontes | **sim** | não | dado |
| Título que não bate com a resposta (L43) | **sim** | não | dado |
| Nomes de entidade variáveis | **sim** | em parte (BM25 ajudaria) | dado |
| Falta de conteúdo (hospedagem, como chegar de SP) | **conteúdo**, não formato | não | fora do escopo |

A regra prática: o que se corrige com uma transformação **automática e aplicável a qualquer base** (cortar por cabeçalho, antepor o título ao chunk, contextualizar com LLM, prefixo do e5) é pipeline e deve virar técnica plugável. O que só se corrige **editando este arquivo à mão** é dado e deve virar uma variante versionada, sem substituir a original.

---

## 5. Recomendações para `database/faq_manus_completa.md`

As linhas se referem ao arquivo atual (243 linhas). Os exemplos "depois" são ilustrativos. Não editei o arquivo.

### R1. Tornar cada par pergunta/resposta autocontido. Evidência: **forte** (Dense X) / **misto** (correferência)

Resolver referências a outras seções, ao "aqui" implícito e ao contexto da conversa. Casos no arquivo:
- L15: `### 3. Dá pra ir a pé até lá ou é melhor pegar um táxi?` ("lá" depende da seção 2);
- L173: `Como mencionei, Santo Antônio da Alegria não tem aeroporto.`;
- L241: `...o **Córrego Fundo** ou a **Cachoeira do Baú**, que, embora mencionadas, ainda guardam...`;
- L137: `### 28. Como é o clima nessa época do ano?`;
- títulos com "aqui"/"por aqui" sem o nome da cidade: L11, L15, L27, L63, L107, L159.

Antes (L15):
```markdown
### 3. Dá pra ir a pé até lá ou é melhor pegar um táxi?
```
Depois:
```markdown
### 3. Dá pra ir a pé até o centro de Santo Antônio da Alegria ou é melhor pegar um táxi?
```
Antes (L173): `Como mencionei, Santo Antônio da Alegria não tem aeroporto.`
Depois: `Santo Antônio da Alegria não tem aeroporto; os mais próximos são o de Ribeirão Preto (RAO) e o de Viracopos (VCP).`

Cuidado: essa reescrita muda o texto que a `evidencia_referencia` cita. Veja a seção 6.

### R2. Um registro por par, com estrutura que o chunker consiga ler. Evidência: **misto** (Jimeno Yepes) + **só fornecedor** (Unstructured, LangChain)

O `### N. pergunta` já é um bom delimitador e deve ficar. O que falta:
- **Listas presas ao contexto.** Em L85–92 (seção 20), os itens não dizem que são gratuitos. Basta que a frase de abertura carregue o sujeito, e cada item pode repetir o qualificador essencial. Antes (L87): `*   Visitar a **Ilha do Ar** e apreciar a vista e o pôr do sol [7].` Depois: `*   Visitar a **Ilha do Ar** (entrada gratuita) e apreciar a vista e o pôr do sol.`
- **Uma versão estruturada do FAQ** em JSONL (um objeto por linha: `id`, `pergunta`, `resposta`, `entidades`, `fonte`, `verificado_em`) como formato alternativo. Isso deixa o pipeline indexar a pergunta e a resposta em campos separados (R6) sem depender de regex no Markdown. Hoje o `/ingest` aceita qualquer texto UTF-8, então esse formato exige um parser no pipeline.

A correção principal aqui é de pipeline: um chunker `markdown_header` que corte em `###` e antepõe o título ao texto do chunk. Sem ele, R2 do lado do dado ajuda pouco com o `recursive` de 1000 caracteres.

### R3. Remover ruído sem remover estrutura. Evidência: **misto** (OHRBench, por analogia) / **conjectura** para o texto de persona

- **Marcadores de citação órfãos.** São 63 ocorrências de `[1]` … `[28]` (por exemplo, L13, L17, L25), mas o arquivo **não tem a lista de fontes**. Os números não significam nada para o embedder nem para o LLM, e o LLM pode copiá-los na resposta. Duas opções: tirar os marcadores, ou recuperar a lista de fontes do Manus e guardá-la como metadado `fonte` por registro. A segunda é melhor, porque dá rastreabilidade.
- **Texto de persona e saudações** que não respondem a nada: L3 ("Olá, viajante! ... Vamos lá!"), L243 ("Espero que este guia..."), aberturas como "Ah, o coração de Santo Antônio da Alegria!" (L9) e "Absolutamente!" (L81). Entram no embedding e o diluem. O ganho de tirar isso é conjectura, porque não achei estudo que isole esse efeito.
- **Manter** `###` e as listas, porque a estrutura ajuda o LLM a ler (HtmlRAG, Table Meets LLM). O `**negrito**` (61 linhas) não tem efeito medido no embedding. Remover ou manter é uma boa candidata a variante do eixo de formato.

Antes (L9, início): `Ah, o coração de Santo Antônio da Alegria! O centro da nossa charmosa cidade se desenvolve principalmente ao redor da **Praça Tereza Benedeti Chocair**...`
Depois: `O centro de Santo Antônio da Alegria fica ao redor da **Praça Tereza Benedeti Chocair**, conhecida como Praça da Matriz...`

### R4. Trocar tempo relativo por tempo absoluto e registrar a data de verificação. Evidência: **só fornecedor** (Azure: metadados) / **conjectura**

- L139 e L148: `(Considerando a data atual, Outubro de 2025)`;
- L149: `Nesta semana, em **outubro**, temos dois eventos...`;
- L140: `Estamos em **outubro**...`.

Uma resposta sobre "eventos desta semana" lida em 2026 fica errada sem que o texto mostre isso. Antes (L146–149): `### 30. Tem algum evento rolando essa semana?` / `Nesta semana, em outubro, temos...`. Depois: `### 30. Que eventos acontecem em Santo Antônio da Alegria em outubro?` / `Em outubro acontecem a Festa do Doce e o Encontro de Carros Antigos... (informação verificada em outubro de 2025).`

A pergunta "o que está rolando essa semana" continua legítima **do lado do usuário**. Resolver "essa semana" é papel do sistema (a data atual no prompt), não do documento.

### R5. Nomes canônicos de entidades, com apelidos na primeira menção de cada registro. Evidência: **só fornecedor** (Azure; BM25 contextual da Anthropic) / **conjectura**

O arquivo alterna "Praça Tereza Benedeti Chocair", "Praça da Matriz" e "praça da Igreja do Rosário" (L165), "Cachoeira do Baú (ou do Deosdédi)", "Cachoeira do Baú (do Deosdédi)" e "Cachoeira do Baú", e "Ilha do Ar (Serra da Laginha)" e "Ilha do Ar". Numa unidade autocontida (R1), a entidade tem que aparecer com o nome canônico **e** o apelido, porque o usuário pode usar qualquer um. Antes (L113, trecho): `o **Parque Ecológico José Jorge Felício** se transforma...` já está bom. O problema está em registros como L29, que dizem só "Praça da Matriz". Depois: `Praça da Matriz (Praça Tereza Benedeti Chocair)`. O mesmo vale para siglas: "EXPOASA" (L99) sem expansão. O guia Azure recomenda expandir abreviações. Se eu não souber a expansão oficial, melhor descrever: `EXPOASA (exposição agropecuária anual, em julho)`. Não verifiquei o significado da sigla.

### R6. Título fiel à resposta, sem restos de template. Evidência: **forte** para FAQ retrieval (q-Q é o sinal mais forte), em inglês

- L43: `### 10. Qual é o horário de funcionamento das lojas?`, mas a resposta dá horário da **Ilha do Ar** e do **AiJapa** e diz que, para lojas, "é sempre bom verificar". O título casa com consultas sobre lojas e a resposta não serve para elas. Depois: `### 10. Qual é o horário de funcionamento de atrações e restaurantes (Ilha do Ar, AiJapa) e das lojas?`
- L231: `### 48. Qual é o melhor jeito de ir até a praia (ou montanha, dependendo do lugar)?` é resto do template genérico que gerou o FAQ. Depois: `### 48. Tem praia ou montanha perto de Santo Antônio da Alegria? Como chegar?`

**Não** reescrever os títulos para ficarem parecidos com as perguntas do `perguntas.csv`. Isso é vazamento do conjunto de teste para a base e infla todas as métricas. O coloquial ("pra", "por aqui") também deve ficar: é o registro real de quem pergunta, e o e5 multilíngue lida com ele.

### R7. Paráfrases de perguntas e metadados por registro, gerados automaticamente. Evidência: **forte** para expansão de documentos (doc2query, Mass et al.) com filtro (Doc2Query--) / **só fornecedor** para os demais metadados (Azure)

Isso é enriquecimento, não formatação manual. Tem que ser uma **técnica do pipeline** (gerar 3–5 paráfrases por pergunta com o LLM local, filtrar por relevância e guardar num campo separado ou numa coleção só de perguntas), para funcionar em qualquer base. Não deve ser escrito à mão neste arquivo. Os metadados que valem para qualquer base são `id`, `titulo` (o `###`), `fonte`, `verificado_em` e `entidades`. O dado precisa **fornecer** título, fonte e data. As entidades o pipeline consegue extrair.

### R8. Lacunas de conteúdo que afetam a avaliação. Evidência: fato, sem nível de evidência a atribuir

Duas perguntas do `perguntas.csv` não têm registro próprio no FAQ:
- "Onde me hospedar em Santo Antônio da Alegria?": só há menções de passagem ao Sítio Sossego das Grutas (L37, L209);
- "Como chegar a Santo Antônio da Alegria vindo de São Paulo?": só a menção a ônibus da Viação São Bento (L49).

Isso não se resolve com formatação. Vale **rotular** essas perguntas como parcialmente respondíveis. Perguntas sem resposta na base são úteis para medir se o sistema admite que não sabe, desde que as métricas as tratem à parte.

---

## 6. Proposta: formato de dados como eixo experimental

**Por que um eixo e não uma correção.** (a) O efeito do formato depende do modelo ([Sclar et al.](https://arxiv.org/abs/2310.11324); [He et al.](https://arxiv.org/abs/2411.10541)), então fixar um formato favorece algumas configurações. (b) O ganho de respeitar a estrutura aparece junto com o chunker ([Jimeno Yepes et al.](https://arxiv.org/abs/2402.05131)). Um chunker por cabeçalho pode tornar R2 redundante, e só o produto cartesiano mostra essa interação. (c) A pergunta da tese ("a melhor configuração para uma base qualquer") precisa de uma linha de base **crua**. Se a base de referência for limpa à mão, o resultado vale para bases limpas à mão.

**Níveis sugeridos** (um arquivo por nível, todos com o mesmo conteúdo factual):

| Nível | O que muda | Como gerar | Reprodutível em base nova? |
|---|---|---|---|
| `raw` | nada (arquivo de hoje) | — | sim |
| `limpo` | R3 + R4 + R6 (ruído, tempo, títulos) | à mão aqui; em base nova, regras e um LLM | parcialmente |
| `autocontido` | `limpo` + R1 + R5 (correferência, entidades) | LLM com prompt fixo e revisão | sim, se automatizado |
| `enriquecido` | `autocontido` + R7 (paráfrases, metadados) | técnica de pipeline | sim |

Para a tese, o caminho mais defensável é que `limpo`/`autocontido` venham de um **normalizador automático** (`DocumentNormalizer` atrás de interface + registry, como os chunkers), e não de edição manual. Assim o nível se aplica a qualquer base e a comparação mede a técnica, não o meu trabalho de edição. A versão feita à mão serve de teto ("oráculo"), do mesmo jeito que o Ditto já tem um RAG `oracle`.

**Cuidados de avaliação.**
1. **Reanotar a evidência por nível.** Com o `partial_ratio ≥ 80` atual, reescrever frases pode tirar o acerto de um chunk certo (seção 2). Cada nível precisa de uma `evidencia_referencia` própria, ou de um mapeamento de ids de registro que substitua o alinhamento por texto.
2. **Separar base e teste.** Nada do `perguntas.csv` pode entrar na base (títulos, paráfrases, palavras-chave).
3. **Uma variável por vez.** Se `raw` → `limpo` mudar título, ruído e datas juntos, não dá para saber qual mudança pesou. Com 50 registros, uma ablação por recomendação é barata.

---

## 7. O que não consegui verificar ou onde a evidência é fraca

- **Markdown contra texto puro para o embedding**: não achei estudo controlado. HtmlRAG e Table Meets LLM medem o que o LLM lê, não a recuperação.
- **Efeito de remover texto de persona/saudação**: nenhum estudo isola isso. R3 é conjectura nesse ponto.
- **FAQ retrieval em PT-BR com embedders multilíngues**: todos os resultados de q-Q contra q-A que li são em inglês (FAQIR, StackFAQ) ou japonês (localgovFAQ). Não achei benchmark de FAQ em português para citar.
- **Magnitude do ganho da resolução de correferência**: o resumo de Jang et al. não traz números e não li a tabela completa.
- **Contextual Retrieval**: os números são de um relatório da Anthropic, sem revisão por pares, e medidos em corpora e embedders diferentes dos nossos.
- **Significado da sigla EXPOASA** e **veracidade dos fatos do FAQ** (horários, preços de táxi, distâncias): fora do escopo. O arquivo foi gerado por um agente (Manus) e cita fontes que não estão nele.
- Na página do Financial Report Chunking, os números de quantidade de chunks estão inconsistentes entre si. Citei só as acurácias.

---

## 8. Referências

Artigos:
- Chen et al. *Dense X Retrieval: What Retrieval Granularity Should We Use?* EMNLP 2024. https://arxiv.org/abs/2312.06648
- Günther et al. *Late Chunking: Contextual Chunk Embeddings Using Long-Context Embedding Models.* https://arxiv.org/abs/2409.04701
- Merola & Singh. *Reconstructing Context: Evaluating Advanced Chunking Strategies for Retrieval-Augmented Generation.* KEIR @ ECIR 2025. https://arxiv.org/abs/2504.19754
- Sarthi et al. *RAPTOR: Recursive Abstractive Processing for Tree-Organized Retrieval.* ICLR 2024. https://arxiv.org/abs/2401.18059
- Qu, Tu & Bao. *Is Semantic Chunking Worth the Computational Cost?* https://arxiv.org/abs/2410.13070
- Bhat et al. *Rethinking Chunk Size For Long-Document Retrieval: A Multi-Dataset Analysis.* https://arxiv.org/abs/2505.21700
- Jimeno Yepes et al. *Financial Report Chunking for Effective Retrieval Augmented Generation.* https://arxiv.org/abs/2402.05131
- Tan et al. *HtmlRAG: HTML is Better Than Plain Text for Modeling Retrieved Knowledge in RAG Systems.* WWW 2025. https://arxiv.org/abs/2411.02959
- Sui et al. *Table Meets LLM: Can Large Language Models Understand Structured Table Data?* WSDM 2024. https://arxiv.org/abs/2305.13062
- He et al. *Does Prompt Formatting Have Any Impact on LLM Performance?* https://arxiv.org/abs/2411.10541
- Sclar et al. *Quantifying Language Models' Sensitivity to Spurious Features in Prompt Design.* ICLR 2024. https://arxiv.org/abs/2310.11324
- Sakata et al. *FAQ Retrieval using Query-Question Similarity and BERT-Based Query-Answer Relevance.* SIGIR 2019. https://arxiv.org/abs/1905.02851
- Mass et al. *Unsupervised FAQ Retrieval with Question Generation and BERT.* ACL 2020. https://aclanthology.org/2020.acl-main.74/
- Nogueira et al. *Document Expansion by Query Prediction.* https://arxiv.org/abs/1904.08375
- Gospodinov, MacAvaney & Macdonald. *Doc2Query--: When Less is More.* ECIR 2023. https://arxiv.org/abs/2301.03266
- Gao et al. *Precise Zero-Shot Dense Retrieval without Relevance Labels* (HyDE). ACL 2023. https://arxiv.org/abs/2212.10496
- Jang et al. *From Ambiguity to Accuracy: The Transformative Effect of Coreference Resolution on RAG Systems.* ACL 2025 SRW. https://arxiv.org/abs/2507.07847
- Zhang et al. *OCR Hinders RAG: Evaluating the Cascading Impact of OCR on Retrieval-Augmented Generation* (OHRBench). ICCV 2025. https://arxiv.org/abs/2412.02592
- Cuconasu et al. *The Power of Noise: Redefining Retrieval for RAG Systems.* SIGIR 2024. https://arxiv.org/abs/2401.14887

Relatórios técnicos e documentação:
- Anthropic. *Introducing Contextual Retrieval.* https://www.anthropic.com/news/contextual-retrieval
- Smith & Troynikov (Chroma). *Evaluating Chunking Strategies for Retrieval.* jul/2024. https://www.trychroma.com/research/evaluating-chunking
- Microsoft Learn. *Develop a RAG Solution — Chunk Enrichment Phase.* https://learn.microsoft.com/en-us/azure/architecture/ai-ml/guide/rag/rag-enrichment-phase
- Unstructured. *Chunking* (`by_title`). https://docs.unstructured.io/open-source/core-functionality/chunking
- LangChain. *MarkdownHeaderTextSplitter.* https://docs.langchain.com/oss/python/integrations/splitters/markdown_header_metadata_splitter
- intfloat. *multilingual-e5-small* (model card, FAQ sobre prefixos). https://huggingface.co/intfloat/multilingual-e5-small
