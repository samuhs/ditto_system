# Portão de qualidade do extrator do Grafo de conhecimento: primeira rodada

Rodada feita em 2026-10-03 com `scripts/graph_extraction_gate.py`. O script mede o prompt `graph/extract` contra o gabarito `database/guia_santo_antonio_da_alegria.grafo_gabarito.json`: 10 seções do guia com 54 entidades e 41 relações anotadas. O portão, definido no ticket #4, exige **recall de entidades ≥ 60%**.

**Ressalvas.** O gabarito foi redigido pelo agente e **ainda não foi revisado por uma pessoa**. O spec pede o Qwen2.5-7B, mas o servidor MLX só tinha o **Qwen2.5-3B-Instruct-4bit**. A comparação de nomes ignora caixa, acentos e apelidos entre parênteses, e aceita pequenas diferenças de grafia (`rapidfuzz.ratio` ≥ 90). As variantes de nome estão listadas como aliases no gabarito. Relações não têm direção.

## Resultados (Qwen2.5-3B-Instruct-4bit, MLX, temperatura 0)

| Prompt | Recall de entidades | Precisão de entidades | Recall de relações | Precisão de relações | Linhas com falha de formato | Portão |
|---|---|---|---|---|---|---|
| v1 (o prompt versionado) | **0,61** | 0,88 | 0,51 | 0,53 | 1 | passou, por pouco |
| v2 (v1 + "liste todas as entidades antes", "datas e valores não são entidades") | 0,61 | 0,73 | 0,37 | 0,47 | 4 | passou; **pior**, descartado |

Uma rodada anterior, com a temperatura padrão do servidor, deu recall de entidades de 0,59. Cada seção leva de 5 a 45 s. As 10 seções levaram cerca de 3 min no total.

## O que se vê nas saídas

- **Entidades que só aparecem dentro de relações.** O modelo para de listar entidades cedo e cita "Prefeitura" ou "Distrito Industrial" só como origem ou destino de relação. Isso derruba o recall de entidades.
- **Relações com coisas que não são entidades**: datas ("9 a 12 de junho de 2022"), horários, partes de uma obra ("calçadas", "lixeiras"). Isso derruba a precisão de relações.
- **Alucinação pontual**: "Praça João Batista de Paiva" no lugar de "Rua João Batista de Paiva".
- **Apelido entre parênteses no nome** ("Cachoeira do Deosdédi (Cachoeira do Dédi)"). Isso é resolvido na consolidação (ticket #10), não na extração.
- **O formato com delimitadores funciona**: 1 linha malformada em cerca de 150.

Pedir explicitamente "liste todas as entidades antes" (v2) não resolveu o primeiro problema e piorou o resto. Isso é coerente com a nota de pesquisa: modelos pequenos seguem regras extras de formato com custo (seção 5.2 de `2026-10-03-graphrag-estado-da-arte.md`).

## Próximos passos

1. Revisar o gabarito (campo `revisado` no JSON) e rodar de novo.
2. Rodar com o Qwen2.5-7B (`make model-add Qwen2.5-7B-Instruct-4bit`), que é o extrator previsto no spec.
3. Se o 7B não passar com folga, as opções mais baratas são:
   - promover a `entidade`, na consolidação, toda origem ou destino de relação sem linha própria;
   - descartar relações cujo destino não é entidade.

   As duas são pós-processamento, sem mudar o prompt.
