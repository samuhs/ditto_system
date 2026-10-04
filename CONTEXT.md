# Ditto

Bancada de experimentos de RAG de um doutorado: compara composições de técnicas sobre uma base de documentos e um conjunto de perguntas, para escolher a que melhor responde.

## Language

**Base**:
Conjunto de documentos ingeridos sob um nome, sobre um mesmo assunto (ex.: um município).
_Avoid_: corpus, dataset, coleção

**Índice**:
Uma Base cortada por uma técnica de chunking e vetorizada por um modelo de embedding; existe um por par chunking × embedding.
_Avoid_: coleção, collection

**Grafo de conhecimento**:
Entidades e relações extraídas dos chunks de um Índice, com cada entidade e relação apontando para os chunks de onde veio. É derivado de um Índice, nunca de uma Base diretamente.
_Avoid_: grafo, KG, knowledge graph

**LLM extrator**:
O LLM que lê os chunks e produz o Grafo de conhecimento. Faz parte da identidade do Grafo (Índice × LLM extrator). É escolhido na ingestão, ao gerar o Grafo, e não coincide com o LLM de resposta: o experimento só consulta Grafos já construídos e escolhe de qual LLM extrator, e todos os seus LLMs de resposta usam o mesmo Grafo.
_Avoid_: LLM do grafo

**Construção do Grafo**:
A tarefa em segundo plano que extrai os chunks de Índices de uma Base com um LLM extrator e grava seus Grafos. Pode ser pausada e retomada sem reextrair chunks: cada extração fica em cache por texto do chunk × LLM extrator × prompt.
_Avoid_: job de grafo, build

**LLM de resposta**:
O LLM que gera a resposta final de uma Técnica RAG; é a dimensão "LLM" de um experimento.

**Retriever**:
Estratégia que, dada uma pergunta, devolve chunks de um Índice como contexto.

**Técnica RAG**:
Estratégia que, dada uma pergunta, decide como recuperar contexto e gerar a resposta com um LLM.
_Avoid_: método, pipeline

**GraphRAG**:
Técnica RAG que responde a partir do Grafo de conhecimento de um Índice.

### Perguntas

**Tipo de pergunta**:
Quantos e quais trechos da Base uma pergunta exige: `simples` (um trecho), `ponte` (um trecho leva ao outro por uma entidade), `comparacao` (dois trechos comparados) ou `agregacao` (vários trechos somados ou listados).
_Avoid_: categoria, nível. Na interface, `simples` aparece como "Um trecho", porque "Simples" já nomeia a Técnica RAG naive.

**Salto**:
Cada trecho distinto da Base de que uma pergunta precisa para ser respondida; uma pergunta `simples` tem um Salto.
_Avoid_: hop, passo

**Entidade-ponte**:
A entidade que liga um Salto ao seguinte numa pergunta `ponte`.
