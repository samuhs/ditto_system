# Design: Preencher Tudo + Resultados Agrupados

**Data:** 2026-06-30  
**Status:** Aprovado  

## Contexto

Duas melhorias de UX nas telas de Inserir documentos, Gerar teste de qualidade e Resultados:

1. Botão "Preencher tudo" para selecionar todas as combinações disponíveis de uma vez
2. Tela de Resultados reorganizada com lista de experimentos e painel de detalhe fixo no topo

## Escopo de mudanças

Ambas as features são **frontend-only**. O backend já suporta múltiplas seleções em todos os campos e roda o produto cartesiano de combinações. Nenhuma rota nova, migração ou schema é necessário.

| Arquivo | Mudança |
|---------|---------|
| `frontend/src/pages/IngestPage.tsx` | Botão "Preencher tudo / Limpar tudo" no card do formulário |
| `frontend/src/pages/ExperimentPage.tsx` | Mesmo botão (5 campos: cortes, embeddings, rags, retrievers, métricas) |
| `frontend/src/pages/ResultsPage.tsx` | Lista clicável de experimentos + painel de detalhe fixo no topo |

---

## Feature 1: Botão "Preencher tudo"

### Comportamento

- Aparece no canto superior direito do card do formulário em `IngestPage` e `ExperimentPage`
- Ao clicar: todos os MultiSelects recebem todos os valores disponíveis (vindos de `options`)
- O botão vira **"Limpar tudo"** (mesmo local, `variant="subtle"`, cor diferente)
- Clicar em "Limpar tudo" zera todos os campos selecionáveis de volta ao estado vazio
- Se o usuário altera qualquer campo manualmente após "Preencher tudo", o botão volta a mostrar "Preencher tudo"

### Estado do botão

```
allFilled = todos os campos com pelo menos 1 opção disponível estão completamente selecionados
```

- `allFilled === true` → botão mostra "Limpar tudo"
- `allFilled === false` → botão mostra "Preencher tudo"
- `options === null` (ainda carregando) → botão desabilitado

### Campos afetados

**IngestPage:** `chunkings`, `embeddings`  
**ExperimentPage:** `chunkings`, `embeddings`, `rags`, `retrievers`, `metrics`

---

## Feature 2: Resultados agrupados com painel de detalhe

### Layout geral

```
[ Painel de detalhe (aparece ao selecionar)        ]  ← topo da seção
  Nome do experimento | status chip | botão ✕
  [ tabela de resultados com linhas expansíveis ]

[ Lista de experimentos                            ]  ← sempre visível abaixo
  ▶ experimento-abc  [done]
  ▶ experimento-xyz  [running]
  ▶ ...
```

### Lista de experimentos

- Cada item é uma linha clicável com: nome e chip de status colorido
- Contagem de resultados **não** é exibida na lista (o endpoint `GET /experiments` não retorna esse dado; evita chamada extra por item)
- O experimento selecionado recebe destaque visual (borda esquerda colorida com a cor do status)
- Sem dropdown `<Select>` — a lista substitui completamente o seletor atual

### Painel de detalhe

- Renderizado **acima** da lista quando um experimento está selecionado
- Cabeçalho: nome + status chip + botão "✕" para fechar/deselecionar
- Corpo: tabela de resultados existente (linhas expansíveis com scores, resposta completa, latência, tokens)
- **Loading state:** enquanto `getExperiment(id)` carrega, exibe `Loader` centralizado no painel em vez da tabela
- **Estado vazio:** se `results.length === 0` e status não é `"done"`, exibe mensagem "Experimento em andamento..."
- Fechar (✕) limpa o detalhe e remove o destaque da lista

### Fluxo de interação

1. Página carrega → `listExperiments()` é chamado, painel ausente
2. Clique num experimento → painel aparece, `getExperiment(id)` é disparado, loader visível
3. Detalhe chega → tabela renderizada no painel
4. Clique em outro experimento → painel atualiza (loader → nova tabela)
5. Clique em ✕ → painel some, nenhum experimento selecionado

---

## Tratamento de erros

- Erro em `listExperiments()` → Alert vermelho no lugar da lista
- Erro em `getExperiment(id)` → Alert vermelho dentro do painel de detalhe (painel permanece aberto)

## Testes existentes

Os testes de `ResultsPage.test.tsx` e `ExperimentPage.test.tsx` precisarão ser atualizados para refletir os novos elementos de UI (botão "Preencher tudo", lista de experimentos, painel). A lógica de API não muda.
