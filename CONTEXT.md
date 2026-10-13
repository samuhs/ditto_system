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

### Experimentos

**Experimento**:
Uma comparação, sobre uma Base e um conjunto de perguntas, de todas as Combinações escolhidas; cada pergunta respondida por cada Combinação vira um resultado avaliado por métricas.
_Avoid_: job, execução

**Combinação**:
Um par chunking × embedding (o Índice) com uma Técnica RAG, um Retriever e um LLM de resposta, dentro de um Experimento.
_Avoid_: run, pipeline, composição

**Comparação**:
Combinações escolhidas de um ou mais Experimentos, comparadas pergunta a pergunta contra uma Linha de base, para dizer se uma é significativamente melhor que outra. Só se comparam pergunta a pergunta Combinações da mesma Base, e só nas perguntas que têm em comum; as de outra Base aparecem lado a lado, sem pareamento. Cada item é identificado por Experimento × Combinação, porque a mesma Combinação pode ter rodado em Experimentos diferentes. Não é salva: existe enquanto o link existir.
_Avoid_: benchmark, ranking (o ranking é o de um Experimento só)

**Linha de base**:
A Combinação da Comparação contra a qual todas as outras são medidas.
_Avoid_: baseline, referência (referência é a resposta de referência da pergunta)

**Pausa**:
Estado de um Experimento parado antes de terminar, com tudo o que já foi respondido preservado, à espera de Retomada. Toda Pausa tem um motivo: manual, Travamento, falhas consecutivas ou Interrupção.

**Travamento**:
Um Experimento em andamento que passa do tempo limite (10 min por padrão) sem gravar nenhum progresso; causa uma Pausa automática.
_Avoid_: timeout, hang

**Falhas consecutivas**:
Perguntas seguidas que falham depois de todas as tentativas (3 por padrão), em qualquer Combinação; um sucesso zera a contagem. Causam uma Pausa automática, porque indicam que o LLM ou o servidor caiu. Erros previstos de uma Combinação (ex.: GraphRAG sem Grafo atual) não contam.

**Interrupção**:
Pausa registrada quando a API reinicia com Experimentos em andamento ou na fila; eles nunca retomam sozinhos.

**Retomada**:
Continuar um Experimento em Pausa (ou que falhou) de onde parou: só as perguntas sem resposta válida rodam de novo, as que deram erro inclusive; respostas válidas nunca são refeitas. A configuração não muda, exceto a concorrência, e é bloqueada se um Índice ou Grafo usado mudou desde a Pausa.
_Avoid_: restart, reexecução

**Registro de pausa**:
O histórico de Pausas de um Experimento: quando, motivo, etapa, perguntas em andamento, último erro, memória naquele momento e quando foi retomado.
_Avoid_: log de erro

### Perguntas

**Tipo de pergunta**:
Quantos e quais trechos da Base uma pergunta exige: `simples` (um trecho), `ponte` (um trecho leva ao outro por uma entidade), `comparacao` (dois trechos comparados) ou `agregacao` (vários trechos somados ou listados).
_Avoid_: categoria, nível. Na interface, `simples` aparece como "Um trecho", porque "Simples" já nomeia a Técnica RAG naive.

**Salto**:
Cada trecho distinto da Base de que uma pergunta precisa para ser respondida; uma pergunta `simples` tem um Salto.
_Avoid_: hop, passo

**Entidade-ponte**:
A entidade que liga um Salto ao seguinte numa pergunta `ponte`.

### Anotação humana

**Avaliador**:
Pessoa que dá notas às respostas na Anotação humana. Todos avaliam na máquina do pesquisador; o Avaliador se cadastra na própria tela de avaliação, só com o nome, sem senha. Desativado, some da lista de identificação, mas as notas ficam.
_Avoid_: anotador, usuário, juiz (juiz é o LLM que avalia)

**Rodada de anotação**:
Respostas sorteadas de Experimentos, com semente gravada, para os Avaliadores darem notas. Aberta, aceita notas; fechada, congela as notas para a análise.
_Avoid_: lote, batch

**Item de anotação**:
Uma resposta de uma Rodada, copiada do resultado de origem (pergunta, referência, evidência, trechos recuperados, resposta e métricas automáticas), para que a Rodada sobreviva ao Experimento ser apagado. O Avaliador nunca vê a Técnica RAG, o LLM nem o Experimento de origem.

**Rubrica**:
As dimensões e os níveis das notas, fixos no código e versionados; a Rodada grava a versão. A v1 tem Correção (0 errada, 1 parcial, 2 correta e completa) e Fundamentação (0 inventa, 1 parcial, 2 toda afirmação está nos trechos recuperados).

**Nota final**:
A nota de um Item depois da Adjudicação: a nota comum quando os Avaliadores concordam, a do adjudicador quando discordam.

**Adjudicação**:
A decisão de um terceiro (ex.: o orientador) sobre a nota dos Itens em que os Avaliadores discordam.

**Concordância**:
Quanto as notas de Avaliadores diferentes coincidem, medida por kappa ponderado ou α de Krippendorff.
_Avoid_: acordo, acurácia
