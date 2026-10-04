# GraphRAG no guia: o experimento #21, o diagnóstico e três correções na consulta

Nota de 2026-10-04 (ticket #12). Registra o primeiro experimento do GraphRAG sobre a base do guia, os três defeitos que ele expôs na consulta do Grafo de conhecimento e o que mudou no código. Depois do ticket da construção na ingestão, esta nota ganha o experimento refeito com as correções.

## 1. O experimento #21

`graphrag-guia-qwen3b`: base `guia-graphrag` (Índice markdown × e5, 104 chunks), as 36 perguntas de `database/perguntas_guia_santo_antonio_da_alegria.csv` (simples 11, ponte 11, comparação 7, agregação 7), Qwen2.5-3B-Instruct-4bit no MLX como LLM extrator e de resposta, retriever `similarity`. Três técnicas: `naive`, `graph` (só o Grafo) e `graph_mix` ("Grafo + busca": chunks do Grafo intercalados com os do retriever).

Médias por técnica e Tipo de pergunta:

| Métrica | Técnica | simples | ponte | comparação | agregação | todas |
|---|---|---|---|---|---|---|
| context_hit | naive | 1,00 | 1,00 | 1,00 | 1,00 | 1,00 |
| | graph | 0,36 | 0,27 | 0,29 | 0,14 | **0,28** |
| | graph_mix | 1,00 | 1,00 | 1,00 | 1,00 | 1,00 |
| context_recall_gold | naive | 1,00 | 0,86 | 0,81 | 0,83 | 0,89 |
| | graph | 0,36 | 0,14 | 0,12 | 0,05 | **0,19** |
| | graph_mix | 1,00 | 0,89 | 0,81 | 0,83 | 0,90 |
| context_all_hops | naive | 1,00 | 0,73 | 0,71 | 0,71 | 0,81 |
| | graph | 0,36 | 0,09 | 0,00 | 0,00 | **0,14** |
| | graph_mix | 1,00 | 0,82 | 0,71 | 0,71 | 0,83 |
| token_f1 | naive | 0,39 | 0,27 | 0,31 | 0,33 | 0,33 |
| | graph | 0,24 | 0,19 | 0,20 | 0,16 | 0,20 |
| | graph_mix | 0,35 | 0,22 | 0,32 | 0,31 | 0,29 |
| chrF | naive | 0,46 | 0,34 | 0,39 | 0,46 | 0,41 |
| | graph | 0,28 | 0,24 | 0,28 | 0,24 | 0,26 |
| | graph_mix | 0,43 | 0,25 | 0,40 | 0,38 | 0,36 |
| ROUGE-L | naive | 0,28 | 0,15 | 0,24 | 0,25 | 0,23 |
| | graph | 0,14 | 0,10 | 0,17 | 0,17 | 0,14 |
| | graph_mix | 0,24 | 0,13 | 0,23 | 0,22 | 0,20 |

O Grafo: 251 entidades, 297 relações, 1.137 linhas de extração, 42 com falha de formato, nenhum chunk perdido. A construção levou cerca de 48 dos ~73 min do experimento. Das 26 entidades-ponte anotadas nas perguntas, o Grafo achou 7.

**Leitura.** O `graph` sozinho recupera o chunk certo em pouco mais de um quarto das perguntas, e pior justamente nos Tipos em que a literatura espera ganho (ponte, comparação, agregação: seção 1 de `2026-10-03-graphrag-estado-da-arte.md`). O `graph_mix` empata com o `naive` na recuperação (0,90 contra 0,89 em `context_recall_gold`, 0,83 contra 0,81 em `context_all_hops`), mas perde nas métricas da resposta: os chunks do Grafo tomam lugar no contexto sem trazer o que falta. Antes de concluir algo sobre GraphRAG nessa base, a consulta tinha defeitos a corrigir.

## 2. Diagnóstico

### 2.1 A sinonímia ligava quase tudo

A consolidação ligava como sinônimas as entidades cujos nomes tinham cosseno ≥ 0,8 no embedder do Índice. Com o e5 (nomes embutidos sem os prefixos `query:`/`passage:`), os cossenos entre nomes curtos ficam entre 0,80 e 0,92 para quase qualquer par. Resultado: **31.168 pares** de sinônimos para 251 entidades, praticamente todos os 31.375 pares possíveis. "São Paulo" ficava sinônimo de "Correios". Na expansão, cada semente passava nota a quase todo o Grafo, e o que decidia o ranking era a especificidade.

### 2.2 A especificidade 1/n punia a entidade certa

A nota de um nó era similaridade × especificidade, com especificidade = 1/n (n = chunks em que a entidade aparece; a *node specificity* do HippoRAG). Na pergunta "Em que mês e em que parque acontece o Encontro de Carros Antigos?", a entidade certa teve a maior similaridade (0,886), mas aparece em 2 chunks: especificidade 0,5, nota 0,443. Entidades irrelevantes de um chunk só ficaram na frente: "Creche Maria do Carmo" (0,808) e "Perguntas frequentes de turistas" (0,796), com nota ~0,8. Com 1/n, ser citada em dois chunks custa metade do peso, e a faixa estreita de similaridades do e5 (décimos de diferença) não compensa.

### 2.3 Títulos de seção viravam entidades

O chunker `markdown` antepõe a cada chunk o caminho de headings ("# Guia de Santo Antônio da Alegria (SP): turismo, história e serviços", "## Perguntas frequentes de turistas sobre ..."). O extrator lia esses títulos como parte do texto e os listava como entidades: "Guia de Santo Antônio da Alegria" apareceu em 94 dos 104 chunks e "Perguntas frequentes de turistas" virou semente de pergunta.

## 3. Correções

1. **Sinonímia por grafia** (`consolidation.link_synonyms`). Os nomes são comparados como texto, sem caixa e sem acentos, com `rapidfuzz.fuzz.ratio` ≥ 85. O peso do vínculo é a razão / 100. A intenção original era "Serra da Lajinha" ~ "Serra da Laginha" (93,75), não conceitos parecidos: "São Paulo" ~ "Correios" dá 23,5 e "Cachoeira do Adilson" ~ "Cachoeira do Deosdédi", 73. A função não recebe mais o embedder, e o vínculo é feito na etapa `merge` da construção, antes de o embedder ser alugado.
2. **Especificidade em IDF suave** (`KnowledgeGraph.specificity`): log((N+1)/n) / log(N+1), com N = chunks do Índice. Vale 1 para uma entidade em um chunk e perto de 0 para uma em quase todos (a cidade, n = 94 de 104: 0,02). O +1 evita o 0 exato para uma entidade presente em todos os chunks: com 0 ela não passaria nota nenhuma, e uma pergunta cuja única semente fosse ela ficaria sem contexto. Em 2 de 104 chunks a entidade fica com 0,85 em vez de 0,5: o Encontro de Carros Antigos passa de 0,443 para 0,75. Sozinha, a mudança ainda não põe a entidade certa acima de uma de 1 chunk com similaridade 0,81, mas sem a sinonímia espalhando nota e sem as entidades de título essas concorrentes deixam de aparecer; e os 2 chunks do evento entram no top-k de chunks.
3. **Extração sem o caminho de headings** (`extraction.without_headings`). A construção tira as linhas de heading do início de cada chunk antes de mandá-lo ao extrator; o chunk guardado no Índice (o que a recuperação e a resposta leem) continua com elas. Escolhi isso, e não mudar o prompt, por três motivos: é determinístico; o portão da seção 5 de `2026-10-03-graphrag-estado-da-arte.md` mostrou que regras extras no prompt custam qualidade a modelos pequenos (o prompt v2 do portão piorou); e o corpo de cada seção da base repete o nome do seu assunto (regra de `database/DIRETRIZES.md`), então o heading da própria seção não leva informação que falte. A chave do cache de extração passa a ser o texto sem headings, o que invalida as extrações antigas desses chunks, como esperado.

Grafos construídos antes destas mudanças guardam a sinonímia antiga e entidades de título. O metadado do Grafo ganhou `graph_version` (= 2): um Grafo sem ele, ou com outra versão, é considerado desatualizado e reconstruído pela própria aplicação na próxima vez que for usado.

O portão do extrator (`scripts/graph_extraction_gate.py`) passou a aplicar o mesmo `without_headings` ao texto de cada seção, para medir o que a construção de fato manda ao LLM.

## 4. Verificação

### 4.1 Portão do extrator (Qwen2.5-3B-Instruct-4bit, MLX, temperatura 0)

`make graph-gate MODEL=mlx-community/Qwen2.5-3B-Instruct-4bit`, com o texto de cada seção sem o heading:

| Rodada | Recall de entidades | Precisão de entidades | Recall de relações | Precisão de relações | Linhas com falha de formato | Portão |
|---|---|---|---|---|---|---|
| 2026-10-03, com o heading (`2026-10-03-portao-extracao-grafo.md`) | 0,61 | 0,88 | 0,51 | 0,53 | 1 | passou |
| 2026-10-04, sem o heading | **0,70** | **0,96** | 0,39 | 0,48 | 0 | passou |

Tirar o heading não custou recall de entidades; subiu de 0,61 para 0,70, e a precisão de 0,88 para 0,96. O recall de relações caiu (0,51 → 0,39). Parte da diferença pode ser variação entre rodadas: duas seções ("Ilha do Ar" e "Encontro de Carros Antigos") ficaram com recall de relações 0, e as relações já oscilavam na rodada anterior. A consulta usa as relações como fatos e como arestas de 1 salto, então vale acompanhar no próximo experimento.

### 4.2 Grafo do guia reconstruído

GRAPH_RESULTS

## 5. Próximos passos

1. Refazer o experimento #21 com as correções, depois do ticket da construção na ingestão, e atualizar esta nota.
2. Se o `graph` continuar atrás do `naive` em `context_hit`, olhar a ligação pergunta → entidade: o e5 comprime as similaridades numa faixa estreita, e a nota de um nó depende quase só da especificidade.
