# Proposta consolidada: ações de maior retorno para a tese

Escrito em 2026-10-12. Junta três relatórios do mesmo dia e os revisa diante do estado real do projeto:

- `2026-10-12-paralelo-literatura-campanha-rag.md`: literatura geral, as 3 ameaças e as ações iniciais (a), (b) e (c);
- `2026-10-12-rag-portugues-modelos-pequenos.md`: RAG em PT-BR e modelos pequenos;
- `2026-10-12-solucoes-ameacas-validade.md`: soluções para as 3 ameaças.

As referências centrais dos dois relatórios novos foram conferidas na fonte (arXiv, ACL Anthology, SBC). A seção 5 lista as correções.

**Restrições consideradas:** Mac de 8 GB, LLMs com até 4B parâmetros em MLX, um pesquisador, 40 perguntas congeladas por base e a campanha 2 em andamento (B2.E1.1 concluída).

---

## 1. O que mudou desde a proposta inicial

1. **A lacuna da tese ficou mais precisa.** Não há estudo publicado de RAG com LLM gerador de até 8B, rodando localmente, em português.
   - Os dois trabalhos mais próximos usam geradores maiores. O PROPOR 2026 hospitalar, de Cunha et al. ([2026.propor-1.74](https://aclanthology.org/2026.propor-1.74/)), usa Gemini 2.5 Flash. O SEMISH 2025, de Medeiros & Oliveira, usa Gemma 2 9B.
   - O survey de LLMs em PT-BR (Cruz-Castañeda & Amadeus, JBCS 2025, [doi:10.5753/jbcs.2025.5789](https://doi.org/10.5753/jbcs.2025.5789)) cobre 76 artigos e não menciona RAG nenhuma vez.
   - Em qualquer língua, nenhum estudo compara técnicas avançadas com naive em modelos de até 4B. O mais próximo é Pandey et al. 2026 ([2603.11513](https://arxiv.org/abs/2603.11513)), que varia só as condições de recuperação.
2. **Agora existe âncora externa barata para os embeddings.** O MTEB-PT ([2607.04071](https://arxiv.org/abs/2607.04071), BRACIS 2026, com revisão por pares) e o MTEB-BR ([2607.04581](https://arxiv.org/abs/2607.04581), preprint de autor único) saíram em julho de 2026. Os dois mostram que o ranking multilíngue não prevê o ranking em PT. No MTEB-BR, ρ = 0,75 e um modelo cai do 3º para o 49º lugar. Rodar esses benchmarks exige só os embedders, sem LLM, então custa horas e não dias. A primeira versão da ação (a) previa o Pt-HotpotQA, que é bem mais caro.
3. **O MIRACL não inclui português.** Ele sai de qualquer texto da tese que o cite como cobertura de PT.
4. **O Tucano 2 foi pós-treinado com dados de RAG** ([2603.03543](https://arxiv.org/abs/2603.03543)). Isso entra como hipótese para o desempenho dele, sem afirmar causa. Nas pontes da campanha 1 ele empatou com o Qwen3.5-4B (0,680 contra 0,677).
5. **Primeiro dado da B2 (B2.E1.1, #82).**

   | Trio | all_hops |
   |---|---|
   | recursive+similarity (melhor) | 0,825 |
   | markdown+similarity (era o I1 do guia) | 0,800 |
   | fixed+parent_document (pior) | 0,700 |

   - Todos os trios ficam abaixo do 0,861 do guia.
   - A queda está nas pontes, com all_hops entre 0,17 e 0,50. As perguntas simples ficam em 1,0.
   - É a primeira evidência a favor de H1 e mostra onde H2 tem chance de aparecer.
   - O dado é parcial: faltam e5 e granite, e o `oracle − naive` só sai na fase 2.
6. **Dados retroativos disponíveis.** Os JSON da campanha 1 (`docs/experimentos/dados/fase*_results.json`) guardam `answer`, `reference` e `scores`, mas não os contextos recuperados.
   - Dá para reavaliar `answer_correctness` e fazer a anotação humana sem rodar nada de novo.
   - Para reavaliar o `faithfulness` da campanha 1, os contextos teriam de estar no Postgres. Pela listagem da API, os experimentos visíveis vão do #57 em diante, então isso ainda precisa ser conferido.

## 2. Revisão das ações iniciais

| Ação inicial | Veredito | Por quê |
|---|---|---|
| (a) Âncora externa em PT (Pt-HotpotQA) + filtro de perguntas respondíveis sem contexto | **Dividir.** O filtro sobe para "fazer já". A âncora passa a ser o MTEB-PT/BR; o Pt-HotpotQA fica para depois | O filtro custa ~1h, porque o `closed_book` já está no plano. O MTEB-PT/BR responde à crítica "embedding escolhido só com as próprias perguntas" sem LLM. O Pt-HotpotQA continua sendo a única âncora multi-hop em PT, mas exige uma fase de LLM (1–2 dias) |
| (b) Validação humana de ~50 itens, com kappa e juiz calibrado | **Manter como a ação de maior retorno**, agora com 60 itens estratificados e a métrica de fatos-chave junto | É a única forma de dizer o que significa "0,65 de answer_correctness". O piso de 0,435 a 0,58 com respostas certas mostra que o cosseno não discrimina bem. Sem isso, as conclusões de D2 e D3 ficam frágeis numa banca |
| (c) Correção de múltiplas comparações declarada antes + poder | **Manter e detalhar.** Holm por família de hipótese, juntando as bases, e MDE ao lado de cada resultado "não significativo" | Com o σ real da campanha 1 (0,06–0,13), n = 40 detecta Δ ≈ 0,05, mas não Δ ≈ 0,03. Os resultados nulos de técnicas da campanha 1 têm de ser lidos como "abaixo do detectável", não como "sem efeito" |

## 3. Onde discordo das soluções propostas

1. **Trocar o `eval_embedding` para `paraphrase` nas bases novas.** Não recomendo.
   - A troca quebra a comparação entre bases, de que H3 e H5 dependem.
   - O instrumento escolhido seria o pior embedder do painel.
   - A circularidade pesa pouco na seleção, porque a D1 decide por `context_all_hops`, que não usa embedder.
   - **Alternativa:** manter o `embeddinggemma` como métrica de continuidade e reavaliar offline com um segundo embedder (granite) só como teste de sensibilidade. A métrica principal de qualidade da resposta passa a ser a de fatos-chave, calibrada pela anotação humana.
2. **Juiz LLM local de outra família (Phi-4-mini ou Ministral).** Fica para depois. Um juiz de 3–4B tende a ser fraco, e sem a amostra humana não dá para saber se ele ajuda. Ordem certa: anotação humana, depois fatos-chave e, só se a correlação dos dois ficar baixa, um juiz.
3. **Análise de subgrupo por tipo de pergunta.** O relatório não aborda isso. Cada tipo tem só 8 a 12 perguntas por base. Os números por tipo, como o das pontes da B2.E1.1, servem como descrição e não entram em testes confirmatórios.
4. **Expandir o painel com Amadeus-Verbo pequeno e Tucano 2 de 0,5B e 1,5B.** É boa ideia para a curva de escala dos modelos em PT, mas cada modelo custa uma fase 3 inteira na máquina de 8 GB. Fica para a tese, depois da campanha 2.

## 4. Proposta: ações em ordem de retorno sobre custo

### Fazer já (antes da B2.E1.2; ~3 h de trabalho, sem máquina extra)

1. **Declarar no plano a regra de vazamento antes de olhar os dados** (ameaça 1).
   - Uma pergunta conta como "possível vazamento" quando a resposta do `closed_book` da B2.E2.1 contém o fato-chave da referência.
   - H1 e H2 são reportadas com e sem essas perguntas.
   - Na B3, o filtro roda antes do congelamento, e as perguntas reprovadas são reescritas.
2. **Declarar as famílias de teste de H1 a H6 e a correção de Holm por família.** Exemplo: a família de H2 são as 8 técnicas × 2 bases. Declarar também a separação: campanha 1 e D1 são exploratórias; H1 a H6 em B2 e B3 são confirmatórias (ameaça 3).
3. **Registrar no plano a leitura correta dos resultados por tipo:** só descritivos, porque n ≤ 12.

### Antes de fechar a campanha 2 (~20 h, quase tudo trabalho humano)

4. **Métrica de fatos-chave** (`key_fact_coverage`): uma coluna nova `fatos_chave` nas 76 perguntas e um avaliador com rapidfuzz, sem embedder nem LLM. Pode ser calculada sobre todo o histórico, porque o `answer` está nos JSON. Custo: ~5 h.
5. **Anotação humana de 60 respostas**, com nota 0/1/2 para correção e para fundamentação.
   - Amostra: 20 do guia e 40 de Maceió, estratificadas por tipo de pergunta e por condição (`closed_book`, `oracle`, `naive`, `agentic`, `compression`).
   - Concordância: com segundo anotador (orientador ou colega, ~1–2 h dele), Cohen ponderado ou Krippendorff α. Sem segundo anotador, teste-reteste com 2 semanas de intervalo e α.
   - Correlação de Spearman entre a nota humana e cada métrica automática, para escolher a métrica principal da tese.
   - Custo: ~6–8 h.
6. **Tabelas com MDE e Holm por família** em `compute_tables.py` (~4–6 h).
7. **Sensibilidade dos vereditos de H1 a H6** a três variações: sem as perguntas com vazamento, reavaliação com granite como `eval_embedding` e BH no lugar de Holm. Se o veredito mudar em alguma, ele cai para "Inconclusivo" (~3 h).

### Âncoras externas (podem rodar em paralelo à campanha, sem bloqueá-la)

8. **MTEB-PT, tarefas de retrieval, com os 4 embedders do painel.** Só CPU e embedders; meio dia a 1 dia. Responde "a escolha de embedding vale fora das minhas perguntas?" e posiciona o Ditto diante de um benchmark nativo com revisão por pares.
9. **Pt-HotpotQA, subconjunto de 50–100 perguntas, com I1 e L0 em `naive` e `oracle`** (1–2 dias). É a única âncora multi-hop em PT. Fica para a tese, depois da campanha 2.

### Para a tese (posicionamento, sem custo de máquina)

10. **Reescrever a afirmação central da tese em torno da lacuna confirmada:** "primeiro estudo fatorial de técnicas de RAG com LLMs ≤ 4B executados localmente, em PT-BR, sobre bases municipais brasileiras, com perguntas multi-hop e evidência anotada". Citar como contexto a relevância para o setor público:
    - o PBIA (MCTI, 2024), que não cita RAG;
    - o estudo da E-Compós sobre chatbots de governos estaduais e capitais, com 24% de respostas adequadas, que ainda precisa ser conferido na fonte antes de citar.
11. **Inferência por predição** (Angelopoulos et al., [2301.09633](https://arxiv.org/abs/2301.09633)), usada para levar a incerteza da amostra humana às métricas automáticas. Só faz sentido depois do item 5.

### Resumo do retorno esperado

| # | Ação | Custo | Ameaça | Retorno |
|---|---|---|---|---|
| 1–3 | Regras declaradas antes dos dados (vazamento, famílias, subgrupos) | ~3 h | 1, 3 | Alto: só dá para fazer agora, antes da B2.E2.1 |
| 5 | Anotação humana de 60 itens | ~8 h | 2 | **O mais alto**: valida todas as conclusões de D2 e D3 |
| 4 | Fatos-chave | ~5 h | 2 | Alto: métrica interpretável, aplicável retroativamente |
| 6–7 | MDE, Holm por família e sensibilidade | ~8 h | 3 | Alto para a banca: evita ler "não significativo" como "igual" |
| 8 | MTEB-PT | ~1 dia de CPU | 1 | Médio-alto: âncora externa barata, com revisão por pares |
| 9 | Pt-HotpotQA | 1–2 dias | 1 | Médio: âncora multi-hop, mas cara |
| 10 | Afirmação central e posicionamento | ~2 h de escrita | — | Alto para o texto da tese |

## 5. Correções feitas nos relatórios dos agentes

- **Survey JBCS 2025:** o relatório de PT-BR dizia que ele lista RAG e modelos pequenos como direções futuras. A palavra "RAG" e o termo "retrieval-augmented" não aparecem em nenhum trecho do PDF. Corrigido nas duas passagens.
- **Tucano 2 nas pontes:** o relatório o chamava de "melhor do painel". O 0,680 empata com o 0,677 do Qwen3.5-4B. Corrigido.
- **Inferência por predição:** o ID 2301.09633 foi conferido, assim como os autores (Angelopoulos, Bates, Fannjiang, Jordan, Zrnic).
- **Referências conferidas e corretas:**
  - Tucano 2 (2603.03543), com a menção a RAG no abstract;
  - MTEB-PT (2607.04071), aceito no BRACIS 2026, com 14 datasets e 17 modelos;
  - MTEB-BR (2607.04581), com ρ = 0,75 em 55 modelos e o modelo que cai do 3º para o 49º lugar;
  - PROPOR 2026 (e5-small + Gemini 2.5 Flash, pp. 749–758).
- **Ainda não conferidos** e que precisam ser verificados antes de citar na tese:
  - os números do SEMISH 2025;
  - o "24%" do estudo da E-Compós;
  - a concordância de 89,5% contra 94,5% do BLUEX v2;
  - a faixa de 31–78% do SeedRG.
