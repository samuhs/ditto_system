# Soluções para as 3 ameaças à validade da Campanha 2

Escrito em 2026-10-12. Parte de `2026-10-12-paralelo-literatura-campanha-rag.md` (que identificou as três ameaças) e de `2026-10-12-campanha-generalizacao.md` (plano, hipóteses H1–H6, desenho). Lê também as seções 2, 5 e 6.1–6.5 de `2026-10-10-campanha-small-llms.md`, o código de `backend/app/core/evaluation/` (`gold_metrics.py`, `embedding_metrics.py`, `overlap_metrics.py`) e `2026-09-24-avaliacao-rag-sem-llm.md`.

**Estado real da campanha 2 neste momento** (confirmado no log da seção 10 de `campanha-generalizacao.md`): só rodou `B2.E0` — ingestão, validação de evidências e o piloto de 3 perguntas. Nenhuma fatia de recuperação, técnica ou LLM rodou ainda. Isso muda o cálculo de custo/benefício: a maioria das correções abaixo é **prospectiva e quase sem custo extra** (muda o próximo passo, não desfaz nada), e só a campanha 1 (guia, 36 perguntas, fases 0–4 completas) e o piloto de B2 exigem reanálise retroativa em vez de nova coleta.

As três seções seguem a ordem do pedido: diagnóstico concreto, soluções ordenadas por custo/benefício (fundamento, passo a passo no Ditto, custo, retroatividade), e para a ameaça 2 um protocolo de anotação humana e alternativas de juiz, para a ameaça 3 uma análise de poder com números reais.

---

## 1. Ameaça 1 — perguntas geradas a partir do próprio documento

### 1.1 Diagnóstico concreto

As 40 perguntas de `database/perguntas_guia_maceio.csv` foram escritas por `database/fontes_brutas/maceio/gera_perguntas.py` — um script com os pares (pergunta, resposta, evidência) redigidos por Claude a partir da base já congelada, revisados e aprovados pelo usuário (`campanha-generalizacao.md`, DEP-2, log de 2026-10-12). O processo já tem três proteções: nenhuma pergunta vem de um LLM do painel avaliado (risco R5, seção 10); a evidência de cada pergunta foi conferida por `valida_perguntas.py` contra o texto congelado com o mesmo critério de `gold_metrics.py` (`partial_ratio ≥ 80`, `evidence_found_in`); e os saltos das perguntas-ponte ficam em blocos diferentes.

O que falta é exatamente o que SeedRG (2026, [arXiv:2605.08838](https://arxiv.org/abs/2605.08838)) chama de "modo de falha fundamental": nenhuma pergunta foi testada em modo `closed_book` **antes** do congelamento. O plano prevê `closed_book` dentro de `B2.E2.1` (seção 5, fase 2 de técnicas), mas o log de DEP-2 já decide isso: *"O teste sem contexto (R1) sai do `closed_book` da B2.E2.1, sem rodada extra"* — ou seja, o teste de vazamento é **subproduto de uma fase posterior**, não um filtro aplicado antes de ranquear os sistemas. Maceió é uma capital com quase 1 milhão de habitantes (957.916, Censo 2022), muito mais conhecida do que Santo Antônio da Alegria (6.775 hab.); o próprio plano já reconhece isso como risco R1, mas sem um critério de corte definido para "essa pergunta está contaminada, excluir do ranking".

Sem esse filtro, uma pergunta respondível de cor (ex.: um fato turístico famoso de Maceió) infla `naive` e `oracle` do mesmo jeito, e pode estar por trás do piso alto já observado: `closed_book` do guia deu `answer_correctness` = 0,435 mesmo sem o modelo saber nada sobre a cidade (`campanha-small-llms.md`, 6.2), e o piloto de Maceió (B2.E0.S, #81) já registrou respostas corretas com `answer_correctness` 0,47–0,58 — na faixa do piso, não muito acima dele. Isso mistura dois fenômenos que precisam ficar separados: piso de métrica (ameaça 2) e vazamento de conhecimento paramétrico (ameaça 1).

### 1.2 Soluções, por custo/benefício

**1. Filtro de vazamento como análise pré-registrada sobre o `closed_book` já planejado (não precisa de rodada nova).**
Fundamento: SeedRG ([2605.08838](https://arxiv.org/abs/2605.08838); preprint de maio de 2026, não revisado por pares, faixa de vazamento 31–78% citada no resumo não confirmada no corpo do artigo nesta pesquisa) e CRUD-RAG ([arXiv:2401.17043](https://arxiv.org/abs/2401.17043)), que usa notícias posteriores à data de corte do modelo exatamente para evitar esse problema.
Passo a passo: antes de usar `B2.E2.1` para decidir H1/H2, ler as 40 respostas de `closed_book` (a maioria das perguntas tem resposta numérica ou nominal curta — "42 metros", "R$ 3", uma data —, fácil de conferir manualmente) e marcar como "possível vazamento" toda pergunta cuja resposta `closed_book` contenha o fato-chave certo sem contexto. Reportar a proporção, e repetir os testes de H1/H2 excluindo essas perguntas (ver análise de sensibilidade, seção 3.5). Documentar a regra de corte **antes** de olhar as respostas, para não virar um ajuste post-hoc.
Custo: ~1–2h de leitura manual (as respostas já vão ser geradas pela fase 2 planejada; não é rodada extra). Retroativo: sim, é análise sobre dados que ainda vão ser coletados na própria ordem do plano — zero desperdício.

**2. Comparar o piso de `closed_book` entre bases (G vs. B2), já com a regra 1 aplicada.**
Fundamento: é o próprio mecanismo de controle de contaminação de CRUD-RAG, adaptado para comparar cidade pequena vs. grande em vez de data de corte.
Passo a passo: depois de `B2.E2.1`, comparar a distribuição de `closed_book` por tipo de pergunta entre o guia (0,435 médio, campanha 1) e Maceió. Se o piso de Maceió for muito mais alto, é evidência direta de que a escolha de uma capital elevou o vazamento, e o relatório da campanha deve declarar isso como limitação explícita de H1/H3 nessa base — já antecipado como risco R1 na seção 10 do plano, só falta reportar o número ao lado do `oracle` como a seção 7 do plano já promete fazer.
Custo: análise pura (~1h), nenhuma coleta nova. Retroativo: sim.

**3. Âncora externa em PT-BR: Pt-HotpotQA ou Quati como controle de terceiros.**
Fundamento: Pt-HotpotQA ([JBCS, artigo 5801](https://journals-sol.sbc.org.br/index.php/jbcs/article/view/5801), periódico revisado) e Quati ([arXiv:2404.06976](https://arxiv.org/abs/2404.06976)), os dois benchmarks de recuperação/QA em PT-BR mais próximos encontrados na revisão da literatura. Responde diretamente à crítica "as perguntas foram escritas pelo próprio autor/LLM a partir do documento usado no experimento".
Passo a passo: rodar o(s) melhor(es) trio(s) de recuperação do Ditto (I1 de cada base) sobre um subconjunto pequeno (50–100 perguntas) de um desses benchmarks, sem re-treinar nada — só ingestão do corpus do benchmark e execução do pipeline existente — e comparar o ranking de métricas de recuperação (`context_all_hops`, `context_mrr`) com o ranking interno do Ditto.
Custo: maior que as anteriores — adaptar o carregador de corpus/perguntas ao formato do benchmark (provavelmente 1 dia de engenharia) mais o tempo de máquina de uma fase de recuperação (ordem de 1–2h, pelo custo por amostra já medido). Retroativo: não aplicável (é um experimento novo, independente do que já rodou); não atrasa nem invalida nada em curso.
Quando fazer: não é bloqueante para fechar a campanha 2; é candidata a entrar antes da tese, não antes de B3.

**4. Filtro de vazamento como critério de aceite *antes* do congelamento, para toda base futura (B3 em diante).**
Fundamento: mesmo princípio de SeedRG, mas aplicado na ordem certa — antes, não depois, do congelamento.
Passo a passo: adicionar à seção 3.4 de `campanha-generalizacao.md` ("Critérios de aceite das perguntas") um passo explícito: depois de redigir as perguntas candidatas de uma base nova e antes de congelar o CSV, rodar o LLM baseline (L0) em `closed_book` sobre as perguntas candidatas; reescrever ou descartar as que o modelo responde bem sem contexto. Isso é diferente da regra 1 porque acontece **antes** do congelamento, então pode mudar o conteúdo das perguntas sem violar o próprio protocolo de "nunca editar depois de congelado" — a edição acontece exatamente no ponto em que o protocolo já permite edição.
Custo: a diferença de custo sobre o que já está planejado é quase zero — é reordenar um teste que já ia rodar, mais o tempo de reescrever 2–5 perguntas que falharem. Para B2, que já está congelada, esta correção **não** pode ser aplicada retroativamente sem violar o próprio congelamento (o que recriaria o problema do "garden of forking paths" da ameaça 3) — para B2 vale a solução 1. Para B3 (`DEP-3`, ainda não existe), é a ordem certa desde o início.

**O que não foi possível confirmar**: a faixa exata de vazamento (31–78%) citada em resumos de terceiros sobre SeedRG não está confirmada no abstract do arXiv consultado; o artigo é um preprint de maio de 2026 sem revisão por pares até onde verificado. Tratar como hipótese de trabalho, não como número a citar sem ressalva.

---

## 2. Ameaça 2 — métricas sem validação humana e circularidade do instrumento

### 2.1 Diagnóstico concreto

As cinco métricas de embedding do Ditto (`backend/app/core/evaluation/embedding_metrics.py`) são todas cosseno entre dois textos embutidos pelo mesmo `eval_embedding`:

- `AnswerCorrectness.score`: `cos(emb(resposta), emb(referência))` (linhas 75–86);
- `Faithfulness.score`: `cos(emb(resposta), emb(contextos concatenados))` (linhas 29–40);
- `ContextPrecision`, `ContextRecall`, `AnswerRelevancy`: a mesma lógica de cosseno (linhas 19–72).

Nenhuma delas chama um LLM para extrair ou verificar afirmações, diferente do RAGAS original (`faithfulness`/`context_precision` do RAGAS usam um LLM, [arXiv:2309.15217](https://arxiv.org/abs/2309.15217); isso já está documentado em `docs/research/2026-09-24-avaliacao-rag-sem-llm.md`, seção 2). O `eval_embedding` é fixo em `embeddinggemma` nas duas campanhas (`campanha-small-llms.md` seção 2; `campanha-generalizacao.md` seção 4). Só que `embeddinggemma` também é o embedding do **índice I1** (o melhor índice da campanha 1, D1: `embeddinggemma+markdown`), e o campo é usado, sem variar, para pontuar literalmente todas as combinações, inclusive as que não usam `embeddinggemma` para recuperar. Isso cria duas formas de circularidade a distinguir:

1. **Piso/escala comprimida da métrica.** O piso de `closed_book` (0,435 no guia; 0,47–0,58 no piloto de Maceió com respostas corretas e recuperação perfeita) mostra que o cosseno de `embeddinggemma` não vai a zero mesmo para respostas erradas ou sem contexto, e satura relativamente perto do teto mesmo para respostas certas. Isso não é peculiar a `embeddinggemma` — a model card do `e5` já avisa que seus cossenos se concentram entre 0,7 e 1,0 ([model card e5](https://huggingface.co/intfloat/multilingual-e5-small), citado em `2026-09-24-avaliacao-rag-sem-llm.md` seção 2) —, mas significa que o valor absoluto de `answer_correctness`/`faithfulness` não pode ser lido como "qualidade real da resposta" sem calibração.
2. **O mesmo modelo usado como índice e como instrumento de avaliação.** Nenhuma fonte consultada na revisão de literatura testa exatamente esse caso (embedder de recuperação = embedder de avaliação); o paralelo mais próximo é o "self-enhancement bias" de juízes LLM (Zheng et al., [arXiv:2306.05685](https://arxiv.org/abs/2306.05685)), que é sobre LLM gerador = LLM juiz, não embedder = embedder. É honesto tratar isso como **extensão por analogia**, não como resultado replicado: o risco real não é necessariamily "embeddinggemma vence porque se autoavalia" (a escolha do índice depende de `context_all_hops`, métrica sem embedder, não de `answer_correctness`), e sim que toda comparação de qualidade de resposta na campanha usa o mesmo instrumento que também é a melhor opção de recuperação — confundindo "o Ditto escolheu bem o embedding" com "o instrumento de avaliação tem viés desconhecido para texto gerado a partir de contexto recuperado por ele mesmo".

### 2.2 Soluções, por custo/benefício

**1. Separar o `eval_embedding` de qualquer candidato a índice, por desenho — elimina a circularidade (2) sem precisar de dados novos.**
Fundamento: não há uma fonte primária específica para esta recomendação (é engenharia experimental, não um resultado de paper); o princípio geral é o mesmo de nunca deixar o conjunto de teste coincidir com o de seleção de modelo (analogia a Recht et al. 2019, [arXiv:1902.10811](https://arxiv.org/abs/1902.10811), sobre reaproveitar o mesmo conjunto para escolher e depois comparar).
Passo a passo: a campanha 2 já reduziu os candidatos a índice para `{embeddinggemma, e5, granite}` (seção 5 do plano). O embedder `paraphrase` ficou fora da triagem de recuperação de B2/B3 por ser o pior da campanha 1 — e é exatamente por isso que serve como **`eval_embedding` dedicado**: nunca vai ser I1, então nunca coincide com o índice sob teste. Trocar `eval_embedding` de `embeddinggemma` para `paraphrase` em `B2.E2.1` em diante (nada da fase 1, que usa só métricas sem embedder, muda). Documentar a regra na seção 4 de `campanha-generalizacao.md`: "`eval_embedding` nunca é um candidato a índice da base".
Custo: zero de máquina adicional (troca um parâmetro de configuração); a única perda é não ter mais a comparação direta com a escala de `embeddinggemma` da campanha 1 nas bases novas — mitigada pela solução 2. Retroativo: não se aplica a campanha 1 (já rodou com `embeddinggemma`), mas a campanha 2 não gastou nada além do piloto, então a mudança é puramente prospectiva e sem custo de oportunidade.

**2. Reavaliação offline com `eval_embedding` alternativo sobre os dados já coletados, sem regenerar nenhuma resposta.**
Fundamento: mesmo raciocínio da solução 1, mas para os dados que **já existem** (campanha 1 completa, piloto de B2) e não podem ser recoletados sem desperdício.
Passo a passo: o banco Postgres guarda, por linha de resultado, `generated_answer`, `reference_answer`, `question` e `retrieved_context` (chunks de texto completos, não apenas IDs) em `backend/app/core/db/models.py:74-98` (`RunResult`). Isso permite escrever um script independente do orquestrador que lê essas colunas diretamente do banco (sem chamar `/experiments`, sem recarregar nenhum LLM) e recalcula `AnswerCorrectness`/`Faithfulness`/`ContextPrecision`/`ContextRecall` com `e5` e `granite` em vez de `embeddinggemma`, usando as mesmas classes de `embedding_metrics.py`. Comparar: (a) se o ranking de técnicas/LLMs muda; (b) se os Δs significativos da campanha 1 (ex.: `compression` faithfulness +0,189*, Qwen3.5-4B +0,054*) continuam significativos com outro embedder.
Custo: ~3–5h de desenvolvimento do script + custo de máquina trivial (só *forward pass* de embedding em CPU sobre textos curtos já existentes, sem LLM, ordem de minutos para centenas de linhas). Retroativo: sim, é o caso de uso principal desta solução — mas depende de os registros ainda existirem no Postgres (não confirmado nesta pesquisa se o volume local já foi limpo; conferir com `make status`/consulta direta antes de assumir que os dados estão lá).

**3. Métricas baseadas em evidência gold, já implementadas e sem embedder nem LLM, como contraponto obrigatório ao cosseno.**
Fundamento: é o próprio mecanismo não-LLM de `context_recall` do RAGAS (`NonLLMContextRecall`, citado em `2026-09-24-avaliacao-rag-sem-llm.md` seção 3.5), já implementado no Ditto.
Passo a passo: `context_hit`, `context_mrr`, `context_recall_gold` e `context_all_hops` (`backend/app/core/evaluation/gold_metrics.py`) comparam texto contra texto por `rapidfuzz.fuzz.partial_ratio` (linha 34), sem nenhum embedder — são imunes à ameaça 2 por construção. Hoje já decidem D1 (seleção de índice), mas não são reportadas sistematicamente como checagem cruzada das decisões de D2/D3 (que usam `answer_correctness`). Passo concreto: toda tabela de Δ de técnica/LLM no relatório da campanha 2 deve vir ao lado da variação equivalente em `context_all_hops`/`context_recall_gold` (quando a técnica muda o contexto) — se a técnica piora `answer_correctness` mas não piora `context_all_hops`, o problema é de geração, não de recuperação, e vice-versa.
Custo: zero — é reportar métricas que já são calculadas em toda fatia, só falta colocá-las lado a lado na análise (`compute_tables.py`). Retroativo: sim, totalmente, inclusive para a campanha 1.

**4. Métrica "a resposta contém os fatos-chave", nova e sem LLM nem embedder, aplicável retroativamente às respostas já geradas.**
Fundamento: é a versão determinística do princípio por trás do `StringPresence`/`ExactMatch` do RAGAS não-LLM (citado em `2026-09-24-avaliacao-rag-sem-llm.md`, seção 3.1) e do crítica de Kamalloo et al. de que correspondência lexical falha quando a lista de respostas-gabarito é pobre ([arXiv:2305.06984](https://arxiv.org/abs/2305.06984)) — aqui resolvida anotando múltiplos fatos atômicos por pergunta em vez de um único texto de referência.
Passo a passo: a maioria das `resposta_referencia` já é, na prática, uma lista curta de fatos (ex.: "42 metros (Roda Massay-ó-k)."; "R$ 3, com fichas vendidas a partir das 10h30."). Decompor manualmente cada uma das 40 perguntas de Maceió e das 36 do guia numa lista `fatos_chave` (string normalizada curta, ex.: `["42 metros", "Roda Massay-ó-k"]`), acrescentar essa coluna ao CSV, e registrar uma nova classe `Evaluator` em `overlap_metrics.py` (`requires_reference_contexts`-like, sem `__init__` com `embedder`) que verifica, por fato, se ele aparece na resposta gerada via `normalize_pt_tokens` (já existente, linha 16) mais correspondência aproximada (`rapidfuzz`, como `gold_metrics.py` já faz). Pontuação = fração de fatos encontrados.
Custo: ~2–3h para extrair/revisar os fatos-chave das 76 perguntas (guia + Maceió) + ~2h de implementação da classe e dos testes. Retroativo: sim — como o texto da resposta gerada (`generated_answer`) já está salvo no Postgres (ou no JSON exportado, que também guarda `answer`), essa métrica pode ser calculada sobre todo o histórico sem reprocessar nenhuma geração de LLM.

### 2.3 Protocolo mínimo de anotação humana

**Tamanho da amostra.** Não foi encontrada nesta pesquisa uma fórmula de fonte primária para dimensionar amostras de anotação para kappa que se aplique diretamente aqui — marcar como não confirmado. A recomendação abaixo é prática, não derivada de um cálculo de poder para kappa: ARES usa um conjunto humano pequeno para calibrar juízes automáticos ([arXiv:2311.09476](https://arxiv.org/abs/2311.09476)), e a revisão de literatura já sugeria 10–15% das respostas de cada campanha (`2026-10-12-paralelo-literatura-campanha-rag.md`, seção 3, item 3). Dado o volume de amostras por campanha (centenas a milhares de linhas, porque cada pergunta se repete em muitas combinações), 10–15% do total é caro demais para anotação manual solo. Proposta concreta e orçável: **60 respostas**, estratificadas para cobrir o que decide H1–H6 — não uma amostra aleatória simples do universo de combinações:
- ~20 do guia (campanha 1, já geradas): cobrindo `closed_book`, `oracle`, `naive` e as 2 técnicas vencedoras (T1=`agentic`, T2=`compression`), distribuídas pelos 4 tipos de pergunta.
- ~20–40 de Maceió (conforme B2 avançar): mesma lógica, mais ênfase nas perguntas marcadas como possível vazamento (seção 1.2, solução 1) e nas perguntas-ponte (mais difíceis).

**Rubrica** (escala 0/1/2, por resposta, comparando com `resposta_referencia` e com os contextos recuperados):
- *Correção*: 0 = errada ou contradiz a referência; 1 = parcialmente correta (acerta parte dos fatos-chave); 2 = correta e completa.
- *Fundamentação* (análogo humano do `faithfulness`): 0 = inventa ou contradiz o contexto recuperado; 1 = parcialmente apoiada; 2 = toda afirmação relevante está no contexto.
- Para perguntas-ponte/agregação, registrar separadamente se **todos** os saltos/itens esperados aparecem (análogo humano do `context_all_hops`/da própria pergunta).

**Concordância.** O projeto tem um único pesquisador, o que é uma restrição real para Cohen's/Fleiss' kappa (exigem ≥ 2 anotadores independentes). Duas saídas, em ordem de preferência:
1. Recrutar um segundo anotador (orientador ou colega) só para esta amostra de calibração (60 itens, rubrica de 2–3 escalas, ~1–2h de trabalho de terceiro) e calcular Cohen's kappa ponderado (escalas ordinais 0/1/2) ou Krippendorff's α (tolera dados ordinais e itens não totalmente cruzados). Como referência de leitura — não verificada nesta sessão com fonte primária, é a convenção comum na área —, α ≥ 0,80 costuma ser lido como "confiável" e 0,667–0,80 como "tentativo"; tratar como heurística, não como limiar derivado estatisticamente para este caso.
2. Se não houver segundo anotador disponível: confiabilidade intra-anotador (teste-reteste). Anotar os mesmos 60 itens duas vezes, com ≥ 2 semanas de intervalo e sem ver as notas da primeira rodada (embaralhar a ordem, remover qualquer rótulo de técnica/LLM da tela de anotação). Calcular Krippendorff's α entre as duas rodadas. É evidência mais fraca (não há segunda perspectiva), mas é factível solo e muito melhor do que nenhuma validação.

**Uso do resultado.** Calcular correlação (Spearman, por ser ordinal) entre a nota humana de *Correção* e cada métrica automática candidata (`answer_correctness`, `token_f1`, `chrf`, a nova `fatos_chave`), e entre *Fundamentação* humana e `faithfulness`. Isso não troca a métrica automática pela humana — serve para (a) decidir qual métrica automática usar como principal na tese (a de maior correlação) e (b) estimar quanto do "piso" de `answer_correctness` (0,435/0,47–0,58) é artefato de escala vs. erro real, comparando com a nota humana média nas mesmas respostas. Para propagar a incerteza da amostra humana para as métricas automáticas em escala (em vez de só reportar uma correlação), a referência metodológica é a inferência com predição potenciada / *prediction-powered inference* de Angelopoulos, Bates, Fannjiang, Jordan e Zrnic (2023) — **citação não reconferida nesta sessão** (sem acesso à web neste momento; confirmar o ID exato do arXiv antes de usar na tese, de memória é algo como `2301.09633`), que é o mecanismo estatístico que o ARES adapta para calibrar juízes automáticos contra poucas anotações humanas ([arXiv:2311.09476](https://arxiv.org/abs/2311.09476)).

### 2.4 Alternativas de juiz (em vez de só cosseno)

1. **LLM local, maior e de família diferente dos avaliados.** Os LLMs do painel de referência (M1 Qwen3.5-4B, M2 Tucano 2 — que também é arquitetura Qwen —, M3 Gemma 4 E2B) compartilham família Qwen em 2 de 3 casos. Um juiz como Qwen2.5-7B-Instruct-4bit herdaria o mesmo risco de "self-enhancement" que Zheng et al. documentam para juízes da mesma família do gerador ([arXiv:2306.05685](https://arxiv.org/abs/2306.05685)). Prefira Phi-4-mini ou Ministral 3 (já baixados em algum momento da campanha 1, famílias diferentes) como juiz, mesmo sendo tecnicamente do mesmo porte dos avaliados — família diferente pesa mais que tamanho para esse viés específico. Rodar o juiz na etapa C (depois do LLM gerador ser descarregado, perfil `low`, `max_local_models=1`), só sobre a amostra de calibração de 60 itens, não sobre a campanha inteira.
2. **Gemini gratuito, só para a amostra de calibração.** A cota é baixa demais para avaliar toda a campanha (já esgotou em 100 req/min na campanha 1, seção 6 do plano antigo), mas cabe perfeitamente nos 60 itens da amostra humana — nesse caso soma-se uma terceira perspectiva (humano × juiz LLM local × Gemini) para a mesma amostra, o que fortalece a validação sem gastar a cota na campanha de produção.
3. **Métrica baseada em evidência gold já existente** (`context_all_hops`, `context_recall_gold`): não é um "juiz" de qualidade de resposta, mas evita completamente o problema de juiz-circular porque não embute texto nem chama LLM. Serve como o contraponto obrigatório descrito na solução 3 da seção 2.2.
4. **"A resposta contém os fatos-chave"** (solução 4 da seção 2.2): o candidato mais barato e já endereçável sem rodar nenhum LLM extra; é o primeiro a implementar antes de decidir se vale o custo de carregar um juiz LLM.

---

## 3. Ameaça 3 — triagem sequencial por fases com n pequeno

### 3.1 Diagnóstico concreto

O desenho de ambas as campanhas é sequencial por triagem: fase 1 escolhe índice/retriever (D1), fase 2 escolhe técnica (D2, só campanha 1), fase 3 varia LLM sobre a configuração vencedora (D3). Cada decisão usa o vencedor da fase anterior como fato consumado na fase seguinte, sem repetir a incerteza da escolha anterior nos intervalos de confiança seguintes — o mecanismo que Gelman & Loken chamam de "garden of forking paths" mesmo sem intenção de inflar resultados (Gelman & Loken, 2013, [PDF](https://sites.stat.columbia.edu/gelman/research/unpublished/p_hacking.pdf)), e que Recht et al. descrevem como "adaptive overfitting"/viés do vencedor ao reaproveitar o mesmo conjunto para escolher e depois comparar muitos modelos ([arXiv:1902.10811](https://arxiv.org/abs/1902.10811)). O n efetivo é pequeno — 36 perguntas na campanha 1, 40 na campanha 2 — exatamente o cenário que Card et al. mostram ser subdimensionado na NLP em geral, inflando conclusões de diferença entre modelos ([arXiv:2010.06595](https://arxiv.org/abs/2010.06595)).

O Ditto já faz parte do caminho certo: Friedman + Nemenyi para comparar vários LLMs/técnicas e Wilcoxon pareado + correção de Holm para comparar dois (seção 5 de `campanha-small-llms.md`), que é exatamente a recomendação de Demšar para esse par de situações (JMLR 2006, vol. 7, pp. 1–30). As hipóteses H1–H6 da campanha 2 foram pré-registradas antes de qualquer dado das bases novas e não podem ser editadas depois da primeira fatia rodar (`campanha-generalizacao.md`, seção 2) — isso já é a prática recomendada contra "forking paths" deliberado. O que falta é: (a) a correção de Holm hoje é aplicada por comparação pareada dentro de uma fase, não necessariamente pela família completa de uma hipótese entre as 3 bases; (b) não há relato de poder/MDE (mínima diferença detectável) ao lado de "não significativo", o que, combinado com n pequeno, corre o risco de ler "sem evidência de diferença" como "sem diferença"; (c) a escolha do índice/técnica vencedor na fase 1/2 não propaga incerteza para as fases seguintes.

### 3.2 Análise de poder, com os números da campanha 1

Os desvios-padrão pareados abaixo foram calculados diretamente de `docs/experimentos/dados/fase2_results.json` e `fase3_results.json` (Δ de `answer_correctness`, pareado por pergunta):

| Comparação (n pareado) | Média do Δ | Desvio-padrão do Δ |
|---|---|---|
| Qwen3.5-2B vs. Qwen2.5-3B (n=36) | +0,038 | 0,058 |
| Gemma 4 E2B vs. Qwen2.5-3B (n=36) | +0,030 | 0,070 |
| Qwen3.5-4B vs. Qwen2.5-3B (n=36) | +0,054 | 0,079 |
| Ministral 3 vs. Qwen2.5-3B (n=36) | +0,019 | 0,074 |
| Tucano 2 vs. Qwen2.5-3B (n=36) | +0,045 | 0,104 |
| Phi-4-mini vs. Qwen2.5-3B (n=36) | −0,017 | 0,130 |
| `agentic` vs. `naive` (n=72, I1+I2) | +0,009 | 0,091 |
| `rerank` vs. `naive` (n=72) | +0,001 | 0,113 |
| `compression` vs. `naive` (n=72) | −0,030 | 0,113 |

O desvio-padrão do Δ pareado varia de ~0,06 a ~0,13 segundo a comparação. Usando a aproximação normal padrão para teste pareado (duas pontas, α=0,05, poder=80%: $n = (z_{0,975}+z_{0,80})^2 \sigma^2/\Delta^2$, com $(1,96+0,84)^2 \approx 7,85$) — aproximação, não o teste real usado pelo Ditto (Wilcoxon + bootstrap), que é mais robusto a não-normalidade mas tem eficiência assintótica comparável para distribuições simétricas (Dror et al., [arXiv:1809.01448](https://arxiv.org/abs/1809.01448), Apêndice):

| σ observado | n para Δ=0,03 | n para Δ=0,05 | MDE em n=36 | MDE em n=40 |
|---|---|---|---|---|
| 0,06 | 31 | 11 | 0,028 | 0,027 |
| 0,07 | 43 | 15 | 0,033 | 0,031 |
| 0,08 | 56 | 20 | 0,037 | 0,035 |
| 0,09 | 71 | 25 | 0,042 | 0,040 |
| 0,11 | 106 | 38 | 0,051 | 0,049 |
| 0,13 | 147 | 53 | 0,061 | 0,058 |

Leitura direta, sem inventar nenhum número fora da tabela: para a maioria das comparações observadas (σ entre 0,07 e 0,11), **36–40 perguntas bastam para detectar Δ≈0,05 com poder razoável, mas não bastam para Δ≈0,03** — precisaria de 55 a mais de 100 perguntas, dependendo da variância da comparação específica. Isso explica, em retrospecto, por que Ministral (+0,019, σ=0,074, MDE em n=36 ≈ 0,036) e SmolLM3 (+0,006) e Phi-4-mini (−0,017) não deram diferenças significativas contra o baseline: os Δs observados estão abaixo do que 36 perguntas conseguem detectar com aquela variância, então "não significativo" não deve ser lido como "sem diferença real" — deve ser lido como "diferença, se existir, está abaixo do que este n consegue separar do ruído". O mesmo raciocínio vale para `rerank`, `hyde` e `crag` vs. `naive` na fase 2 (Δs de 0,001 a 0,014 com σ ≈ 0,09–0,11, muito abaixo do MDE de ~0,04–0,05 em n=72).

Esta tabela deve constar explicitamente ao lado de toda tabela de Δ na tese (seção 5 do plano de ambas as campanhas já promete reportar IC; falta reportar também o MDE correspondente). Como a correção de 40 perguntas da campanha 2 já está fixada e congelada (não é recomendável nem possível mudar o n retroativamente sem reabrir o desenho), a recomendação prática não é "aumentar o n" — é **declarar o MDE junto de cada "não significativo"**, e reservar a leitura de "H2 não se confirma" apenas para quando Δ observado estiver claramente abaixo do MDE, não apenas quando o IC cruza o zero por uma margem pequena.

### 3.3 Correção de múltiplas comparações por família de hipóteses

Fundamento: Holm (procedimento sequencial que controla o erro familywise, referência padrão citada por Demšar 2006 e já em uso no Ditto) e Benjamini-Hochberg (controle de taxa de falsas descobertas, maior poder ao custo de permitir algumas falsas descobertas entre as rejeições — referência clássica, *Journal of the Royal Statistical Society B*, 1995, não arXiv).

Passo a passo:
1. Definir a família de testes de cada hipótese **antes** de olhar os dados de B2/B3 (H1–H6 já declaram o teste principal; falta declarar o conjunto completo de testes pareados que entram em cada família). Por exemplo, a família de H2 ("alguma técnica supera `naive`") deveria ser todas as comparações técnica-vs-`naive` nas duas bases novas juntas (até 8 técnicas × 2 bases = até 16 testes), não 8 testes corrigidos separadamente por base.
2. Aplicar Holm dentro de cada família assim definida, para as afirmações confirmatórias que vão para a conclusão da tese (mantém o controle forte de falso positivo que Demšar recomenda).
3. Para a etapa exploratória de triagem de índice (fase 1, Friedman+Nemenyi já cobre isso por construção, porque compara todos os trios de uma vez) não é preciso Holm adicional — o Nemenyi já é um post-hoc com correção embutida.
4. Opcionalmente, reportar também a versão com Benjamini-Hochberg ao lado de Holm nas tabelas de sensibilidade (seção 3.5): se a conclusão muda dependendo da correção escolhida, isso por si só é informação sobre a robustez do achado.
Custo: ~2–4h para adaptar `compute_tables.py` a operar sobre a família completa de testes de cada hipótese em vez de por fase/base isolada. Retroativo: sim, é reanálise sobre tabelas de p-valor já calculadas.

### 3.4 Separação exploratório vs. confirmatório

O próprio desenho da campanha 2 já faz a parte difícil certo: H1–H6 foram escritas antes de qualquer dado de B2/B3 e travadas contra edição posterior (`campanha-generalizacao.md`, seção 2). O que falta é declarar essa separação explicitamente no relatório final, em vez de deixá-la implícita:

- **Exploratório** (pode reexaminar, reajustar, comparar muitos candidatos sem perder validade, porque já usa correção própria): toda a campanha 1 (guia) e a escolha de I1/R* por base (D1 de B2 e D1 de B3), porque são seleção de modelo via Friedman+Nemenyi, que já absorve a multiplicidade.
- **Confirmatório**: os testes de H1–H6 sobre B2 e sobre B3, porque foram fixados antes dos dados existirem. A regra prática (análoga ao conjunto de teste reamostrado de Recht et al., [arXiv:1902.10811](https://arxiv.org/abs/1902.10811)): se um teste de H1–H6 falhar em B2, isso **não** libera uma nova rodada de ajuste de critério para "salvar" a hipótese em B3 — o resultado em B2 é reportado como está, e B3 roda o mesmo teste pré-registrado, servindo de confirmação **independente**, não de segunda chance para a mesma hipótese.
Custo: zero, é disciplina de relato, não código ou coleta. Aplicar já, antes de B2.E1.1.

### 3.5 Análise de sensibilidade

Fundamento: é a prática padrão de reportar robustez de uma conclusão a escolhas de análise alternativas e razoáveis — a mesma lógica geral de Gelman & Loken (2013) de que, se muitas escolhas razoáveis dessem conclusões diferentes, a conclusão não é tão forte quanto parece com uma única escolha.

Passo a passo concreto, unindo as três ameaças: para cada veredito confirmatório de H1–H6 (ex.: "H2 se confirma em B2 com `agentic`"), reportar se o veredito se mantém sob pelo menos três perturbações razoáveis:
1. Excluindo as perguntas marcadas como possível vazamento (seção 1.2, solução 1);
2. Reescorando com `eval_embedding` alternativo — `e5`/`granite` em vez de `embeddinggemma`/`paraphrase` (seção 2.2, solução 2);
3. Troca de correção de múltiplas comparações (Holm vs. Benjamini-Hochberg, seção 3.3).
Se o veredito muda sob qualquer uma das três, o relato deve rebaixar a classificação de "Generaliza" (seção 7 do plano) para "Inconclusivo", independentemente do que a análise principal tenha dito.
Custo: depende das soluções 1 e 2 já estarem implementadas; o custo incremental da própria análise de sensibilidade é baixo (reexecutar o mesmo pipeline de teste estatístico 3 vezes a mais sobre dados já existentes, sem coleta nova).

---

## 4. Plano mínimo recomendado

**Fazer já (antes de `B2.E1.1`, sem custo de máquina além do que já está planejado):**
1. Trocar `eval_embedding` para `paraphrase` em `B2`/`B3` a partir da fase 2 em diante (ameaça 2, solução 1). ~15 min de configuração.
2. Documentar na seção 4 de `campanha-generalizacao.md` a regra "`eval_embedding` nunca é candidato a índice" e a separação exploratório/confirmatório da seção 3.4 desta pesquisa. ~30 min.
3. Adicionar à seção 3.4 ("critérios de aceite das perguntas") o filtro de `closed_book` **antes do congelamento** para B3 (ameaça 1, solução 4). Sem custo adicional, é reordenar um passo que já existe.
4. Preparar o script de leitura manual do `closed_book` de `B2.E2.1` com a regra de corte de vazamento já escrita, antes da fase rodar (ameaça 1, solução 1). ~1h.

Total estimado: **~2h de trabalho humano, zero máquina extra.**

**Antes de fechar a campanha 2 (depois de B2 e, se possível, B3 completarem a fase 3, antes de escrever os vereditos finais de H1–H6):**
5. Extrair os fatos-chave das 76 perguntas (guia + Maceió) e implementar `key_fact_coverage` (ameaça 2, solução 4). ~4–5h.
6. Reescorar offline os dados já coletados (campanha 1 + B2) com `e5`/`granite` como `eval_embedding` alternativo e comparar rankings/Δs (ameaça 2, solução 2). ~5–6h de desenvolvimento + minutos de máquina.
7. Protocolo de anotação humana: 60 itens, rubrica 0/1/2, kappa ou confiabilidade teste-reteste (ameaça 2, seção 2.3). ~4–8h (2 sessões de anotação + análise), mais o tempo de um segundo anotador se disponível.
8. Juiz LLM local (Phi-4-mini ou Ministral) sobre a mesma amostra de 60 itens, e opcionalmente Gemini gratuito na mesma amostra (ameaça 2, seção 2.4). ~1–2h de máquina (amostra pequena) + ~2h de análise.
9. Adaptar `compute_tables.py` para correção por família de hipótese (Holm, com Benjamini-Hochberg como alternativa reportada) e para reportar MDE ao lado de cada Δ não significativo (ameaça 3, seções 3.2–3.3). ~4–6h.
10. Rodar a análise de sensibilidade combinando 1+2+3 sobre os vereditos de H1–H6 (ameaça 3, seção 3.5). ~2–3h, depois dos itens 5–9 estarem prontos.

Total estimado: **~25–35h de trabalho humano + poucas horas de máquina (tudo CPU/embeddings, sem reprocessar LLM)**, distribuído em cerca de 1 semana de trabalho de um único pesquisador, sem bloquear o avanço de `B2.E1.1` em diante.

**Deixar para a tese (não bloqueia o fechamento da campanha 2):**
11. Âncora externa em Pt-HotpotQA ou Quati (ameaça 1, solução 3). ~1–2 dias.
12. Geração de perguntas resistente a vazamento por substituição de entidades (estilo SeedRG) para qualquer base futura além de B3 (ameaça 1, solução 4 estendida). Tratar o próprio SeedRG com cautela adicional, por ser preprint de 2026 sem revisão por pares confirmada.
13. Escalar a anotação humana além dos 60 itens de calibração, com inferência de predição potenciada (Angelopoulos et al. 2023, citação a reconferir) para propagar a incerteza da amostra humana para toda a escala automática — é o que torna a calibração publicável, não só uma checagem de sanidade.
14. Métricas de fidelidade com NLI multilíngue (mDeBERTa-xnli) e BERTScore com baseline `pt`, já especificadas em `2026-09-24-avaliacao-rag-sem-llm.md` seção 5.1 — reforça a ameaça 2 a longo prazo, mas exige generalizar a injeção de modelo no `runner.py` (mudança de arquitetura, não só de configuração).

---

## O que não foi possível confirmar nesta pesquisa

- A faixa de vazamento (31–78%) atribuída a SeedRG em resumos de terceiros não foi confirmada no abstract/arXiv consultado.
- O ID do arXiv de Angelopoulos et al., "Prediction-Powered Inference", é `2301.09633` (conferido pela sessão principal; publicado na *Science*, 2023).
- Os limiares de leitura de Krippendorff's α (≥0,80 "confiável", 0,667–0,80 "tentativo") são uma convenção comum na área de anotação de conteúdo, não uma fórmula derivada nesta pesquisa; tratar como heurística de bolso, a confirmar com a fonte primária (Krippendorff) antes de citar na tese.
- Se os registros do Postgres das campanhas já rodadas (campanha 1, piloto de B2) ainda existem no volume local, permitindo a reavaliação offline da seção 2.2 (solução 2) sem recoleta — não verificado nesta pesquisa; confirmar com `make status`/consulta ao banco antes de planejar essa solução como certa.
- Nenhum número de poder/MDE fora dos calculados diretamente de `fase2_results.json`/`fase3_results.json` nesta sessão foi inventado; a tabela da seção 3.2 usa a aproximação normal padrão para teste pareado, que é uma simplificação do teste real (Wilcoxon + bootstrap) — útil para dimensionamento, não para o valor-p final reportado na tese.
