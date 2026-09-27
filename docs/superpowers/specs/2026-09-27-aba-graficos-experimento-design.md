# Aba "Gráficos" no detalhe do experimento

**Status:** design aprovado, falta o plano de implementação.
**Contexto:** o detalhe do experimento (`frontend/src/pages/ExperimentDetailPage.tsx`) só mostra tabelas: ranking das combinações, respostas por pergunta, dificuldade e prompts. Uma bateria grande gera dezenas de combinações × dezenas de perguntas, e nas tabelas não dá para ver *por que* uma combinação ganha. A nova aba mostra isso em gráficos e, por padrão, só um recorte: as N melhores contra as N piores.

## 1. Objetivo

A aba responde quatro perguntas, uma por figura:

1. **Onde as piores perdem?** O perfil de métricas das N melhores contra as N piores combinações.
2. **Qual escolha pesa mais?** O efeito de cada dimensão (corte, embedding, RAG, busca, modelo) na qualidade.
3. **Vale o custo?** Qualidade contra latência ou tokens, com a fronteira de Pareto.
4. **É consistente?** A distribuição dos scores por pergunta e quais perguntas quebram cada combinação.

Fora de escopo: comparar experimentos entre si, exportar imagens dos gráficos e controlar interações entre dimensões (a Fig. 2 é efeito marginal).

## 2. Onde fica e de onde vêm os dados

- É uma aba nova, **"Gráficos"**, entre "Ranking das combinações" e "Respostas por pergunta".
- Usa só o `detail.results` que a página já carrega: uma linha por pergunta × combinação, com `scores`, `latency_ms` e `tokens`. **Não muda nada na API.**
- Com o experimento em `running`/`pending`, a aba se atualiza junto com o polling da página, e cada legenda de figura indica "parcial: X de Y combinações".

## 3. Barra de foco

É uma barra fixa no topo da aba e controla quais combinações ficam "em foco" em todas as figuras. A Fig. 2 é a exceção: ela sempre agrega todas.

| Controle | Valores | Padrão |
|---|---|---|
| Modo | `Top e bottom` · `Só top` · `Todas` | `Top e bottom` |
| N | 1–10 | 3 |
| Métrica dos gráficos | `Média` ou qualquer métrica presente em `metricKeys` | `Média` |
| Seleção manual | "+ combinação" abre a lista do ranking; marca/desmarca qualquer combinação | vazia |

Regras:
- O top e o bottom vêm sempre do ranking pela **média**, o mesmo da aba "Ranking". A "métrica dos gráficos" muda só o eixo de qualidade das Fig. 2–4.
- Se houver menos de 2N combinações, top e bottom se juntam sem repetir: uma combinação que caberia nos dois grupos fica no top.
- As combinações escolhidas à mão formam um terceiro grupo, **manual**. Uma combinação que já está no top ou no bottom não entra de novo.
- O estado da barra fica em `ExperimentDetailPage` (as abas usam `keepMounted={false}`), então sobrevive à troca de aba. Não fica guardado entre visitas.

### Identidade visual das combinações

- A **cor indica o grupo**: top em `hue-violet`, bottom em `hue-orange`, manual em `hue-ultramarine`. As combinações fora de foco, quando aparecem (só na Fig. 3), ficam em `line-strong`.
- O **número indica a posição**: cada marca leva a posição no ranking pela média (#1, #2, …), com o mesmo selo da aba "Ranking".
- Não há uma cor por combinação, porque isso não se sustenta com N até 10.

## 4. As figuras

As figuras seguem o estilo de manual do DESIGN.md, cada uma com legenda "**Figura k.** …" em `ditto-caption`, fios finos, Archivo com números tabulares e escala de qualidade fixa de 0 a 1.

### Figura 1. Perfil de métricas (top × bottom)

- É um gráfico de pontos (Cleveland): uma linha por métrica, com a **Média** por último e destacada; eixo X de 0 a 1; um ponto por combinação em foco, com o número da posição.
- Em cada linha, uma faixa sombreada vai da média do grupo top até a média do grupo bottom, com o vão escrito à direita (`−0,31`).
- As métricas ficam ordenadas pelo tamanho do vão, do maior para o menor. A Média fica sempre por último.
- No modo `Só top` ou `Todas`, ou sem bottom, não há faixa nem vão: só os pontos.

### Figura 2. Efeito de cada dimensão

- É sempre calculada sobre **todas** as combinações, sem olhar o foco.
- Há um painel pequeno por dimensão com mais de uma opção. Em cada um, uma linha por opção com:
  - um ponto na média da métrica dos gráficos sobre todas as combinações que usam aquela opção;
  - uma barra fina indo do menor ao maior valor entre essas combinações.
- Os painéis ficam ordenados pelo **tamanho do efeito**, que é a média da melhor opção menos a da pior. Dentro de cada painel, as opções vão da melhor para a pior.
- As dimensões com uma só opção aparecem numa linha de texto: "Fixo neste experimento: Embedding e5, Modelo qwen…".
- Se a grade estiver incompleta (o número de combinações distintas for menor que o produto das opções de cada dimensão), aparece a nota "Grade incompleta: o efeito de uma dimensão pode se misturar com o das outras."
- Os nomes das opções usam `term(dim, key).name`, como `dimName` já faz.

### Figura 3. Custo × qualidade

- É uma dispersão: o eixo X é o custo e o eixo Y é a métrica dos gráficos, com uma marca por combinação.
- Um seletor ao lado da legenda alterna o eixo X entre **Latência média (ms)** e **Tokens médios**.
- As combinações fora de foco aparecem em cinza e as em foco nas cores do grupo, com o número.
- **Fronteira de Pareto:** uma linha escalonada liga as combinações que nenhuma outra supera ao mesmo tempo, com custo menor ou igual e qualidade maior ou igual, e pelo menos uma das duas desigualdades estrita. Essas combinações ganham um anel mesmo fora do foco.
- Se nenhuma linha tiver o custo escolhido (`> 0`), o seletor passa para o outro custo. Se nenhum dos dois tiver dados, a figura dá lugar a uma `Note` "Sem dados de custo neste experimento".

### Figura 4. Estabilidade por pergunta

**4a. Distribuição.** Uma linha por combinação em foco, na ordem do ranking, com:
- um ponto por pergunta, levemente espalhado na vertical (espalhamento determinístico, derivado do índice, sem aleatoriedade);
- a mediana marcada e o intervalo interquartil como faixa.

**4b. Mapa pergunta × combinação.**
- As linhas são as perguntas, as colunas são as combinações em foco (cabeçalho com o número da posição) e cada célula mostra o valor da métrica dos gráficos para aquele par.
- A escala é sequencial de uma cor só, de `leaf` (0) a `#472d8a` (1: o matiz de `hue-violet` escurecido, hsl(257°, 51%, 36%)). O texto é `ink` abaixo de 0.68 e branco a partir dele; para que toda nota de 0 a 1 tenha contraste ≥ 4.5:1, a escala pula a faixa estreita de luminância em que nenhuma das duas cores chega lá (um degrau pequeno em 0.68, junto com a troca da cor do texto). Célula sem valor aparece hachurada.
- As perguntas vão da mais difícil para a mais fácil, pela média entre as combinações em foco.
- As linhas são compactas, com o texto da pergunta truncado e completo no tooltip.
- Clicar numa célula abre o drawer **"Detalhe do resultado"** que já existe, com aquele `ExperimentResultRow`.

### Comum a todas as figuras

- O tooltip ao passar o mouse mostra a combinação completa (`Traits`), os valores e, quando uma métrica faltou em parte das perguntas, "n = 7 de 10 perguntas".
- As marcas recebem foco pelo teclado. Enter numa marca de combinação chama `showAnswersOf(combo)`; Enter numa célula da Fig. 4b abre o drawer.
- Cada figura tem uma tabela equivalente só para leitores de tela (`visually-hidden`).
- A largura vem do contêiner (`ResizeObserver`), com uma largura padrão quando a medida é 0 (jsdom). Em telas estreitas os painéis da Fig. 2 ficam empilhados e a Fig. 4b ganha rolagem horizontal própria.

## 5. Arquitetura

```
frontend/src/
  experiments/ranking.ts          mean, rowMedia, comboKey, rankCombinations, RankRow, DIMS
                                  (saem de ExperimentDetailPage.tsx; tabela e gráficos usam o mesmo código)
  components/charts/
    aggregate.ts                  funções puras (seção 5.1)
    ChartsPanel.tsx               FocusBar + as quatro figuras
    FocusBar.tsx
    MetricProfile.tsx             Fig. 1
    DimensionEffects.tsx          Fig. 2
    CostQuality.tsx               Fig. 3
    Stability.tsx                 Fig. 4a + 4b
    primitives.tsx                eixo, marca com número da posição, tooltip, useChartWidth
```

- **Dependências novas:** `d3-scale` e `d3-array`, mais `@types/d3-scale` e `@types/d3-array`. Só escalas e estatística; o SVG é desenhado pelos componentes React.
- **Interface do painel:**
  ```ts
  <ChartsPanel
    results={results}
    metricKeys={metricKeys}
    ranking={rankingByMedia}
    focus={focus} onFocusChange={setFocus}
    partial={isRunning ? { completed, total } : null}
    onShowAnswers={showAnswersOf}
    onOpenRow={setOpenRow}
  />
  ```
- As figuras recebem dados já calculados e só desenham. Todo o cálculo fica em `aggregate.ts` e em `useMemo` no `ChartsPanel`.

### 5.1 `aggregate.ts`

| Função | Entrada → saída |
|---|---|
| `focusSet(ranking, focus)` | `{ top, bottom, manual }` de `RankRow`, com as regras da seção 3 |
| `metricValue(rows, metric)` | média da métrica (ou de `rowMedia` para "Média") e `n` de linhas que a têm |
| `metricProfile(focused, metricKeys)` | por métrica: valores por combinação, médias top/bottom e vão; ordenado pelo vão |
| `dimensionEffects(results, metric)` | por dimensão: opções com média, mín. e máx. entre combinações; tamanho do efeito; dimensões fixas; flag `incompleteGrid` |
| `costPoints(results, cost, metric)` | por combinação: custo médio e qualidade |
| `paretoFrontier(points)` | pontos não dominados, ordenados por custo |
| `quartiles(values)` | `{ q1, median, q3 }` |
| `questionMatrix(results, focused, metric)` | perguntas ordenadas da mais difícil para a mais fácil, com as células (valor + linha de origem) |

## 6. Casos-limite

| Situação | Comportamento |
|---|---|
| 1 combinação | Fig. 1 só com ela, sem faixa; Fig. 2 e 3 dão lugar a `Note` "Precisa de ao menos 2 combinações"; Fig. 4 normal |
| Todas as dimensões fixas | Fig. 2 mostra só a linha "Fixo neste experimento…" |
| Métrica ausente em parte das linhas | entra na média só o que existe; o tooltip mostra `n` |
| Métrica escolhida some (troca de experimento) | a barra volta para "Média" |
| Seleção manual com combinação que não existe mais | ignorada |
| Sem custo | seção 4, Fig. 3 |
| Experimento rodando | legendas com "parcial"; as figuras se recalculam a cada polling |

## 7. Testes (vitest, sem rede)

- `experiments/ranking.test.ts`: `rankCombinations` com as mesmas garantias de antes da extração.
- `components/charts/aggregate.test.ts`:
  - `focusSet`: sobreposição com menos de 2N combinações, `Só top`, `Todas`, manual sem duplicar;
  - `metricProfile`: vão e ordenação;
  - `dimensionEffects`: efeito, dimensões fixas e `incompleteGrid`;
  - `paretoFrontier`: dominância com empates;
  - `quartiles`: listas pares, ímpares e com um item;
  - `questionMatrix`: ordem por dificuldade e células faltando.
- `components/charts/ChartsPanel.test.tsx`:
  - trocar modo ou N muda as marcas renderizadas (por `aria-label` com a posição);
  - a seleção manual adiciona uma marca do grupo manual;
  - clicar ou dar Enter numa marca chama `onShowAnswers`;
  - clicar numa célula da Fig. 4b chama `onOpenRow`;
  - as tabelas para leitor de tela existem;
  - os casos-limite da seção 6 renderizam as `Note`.
- `pages/ExperimentDetailPage.test.tsx`: os testes atuais continuam passando; a aba "Gráficos" aparece; o foco escolhido sobrevive a ir para "Respostas" e voltar.

## 8. Implementação visual

A tela é construída e revisada com a skill **impeccable** contra o `DESIGN.md`: tokens de cor e tipografia, legendas "Figura k." e o mesmo ritmo de espaçamento das outras abas. Os estilos novos entram em `frontend/src/styles/global.css` com o prefixo `ditto-chart-`.
