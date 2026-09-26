# Regras de escrita dos blocos

Regras condensadas de `database/DIRETRIZES.md` do projeto Ditto. A fundamentação está em `docs/research/2026-09-26-formatacao-de-dados-para-rag.md` desse projeto. Onde houver `DIRETRIZES.md` no projeto, siga-o.

## Arquivo

- Markdown UTF-8. Na primeira linha, `# Guia de <Cidade> (<UF>): ...`. Logo abaixo, um parágrafo de contexto: o que a base cobre, de quais fontes veio, quando os dados foram coletados, e o aviso de que horários, telefones e datas podem mudar.
- Seções `## <Tema> de <Cidade>`. Cada unidade é um bloco `### ...` seguido do texto, **sem linha em branco dentro do bloco**. Linha em branco só entre blocos.
- Cada bloco tem **no máximo ~800 caracteres**. Se não couber, divida em dois blocos, cada um com o seu cabeçalho.

## Cabeçalho: qual formato

- **Tema explicativo** (história, geografia, como é uma festa): pergunta natural com o nome da cidade. Ex.: `### Por que a cidade se chama Santo Antônio da Alegria?`
- **Entidade ou diretório**: nome, tipo e cidade. Ex.: `### Cachoeira do Beto Teixeira em Santo Antônio da Alegria`, `### Farmácias de <Cidade>`. Entidades pequenas do mesmo tipo vão juntas num bloco, uma por linha: `- Nome: endereço; telefone; horário.`
- **FAQ já existente**: mantém a forma de pergunta e resposta, numa seção própria.
- O cabeçalho tem que corresponder ao que o bloco responde. Nunca copie perguntas de um conjunto de teste.

## Texto

- **Autocontido**: nomeie a cidade e a entidade em todo bloco. Nada de "aqui", "lá", "nossa cidade", "como mencionei", "acima".
- **Nomes canônicos**: na primeira menção de cada bloco, coloque o nome alternativo entre parênteses, como `Cachoeira do Deosdédi (Cachoeira do Dédi)`. Expanda as siglas quando a expansão tiver fonte.
- **Datas absolutas**: escreva "em outubro", "de 9 a 12 de junho de 2022", nunca "hoje", "esta semana" ou "atualmente". Se a fonte não informa o ano, não invente.
- **Horários por extenso e compactos**: "de segunda a sábado, das 6h às 19h; domingo, das 6h às 12h".
- **Sem ruído**: nada de marcadores `[n]`, persona ("Olá, viajante!"), negrito, numeração nos cabeçalhos ou caixa-alta copiada da fonte.
- **Divergência sem vencedor**: registre as duas versões no próprio texto ("segundo a Prefeitura…; segundo a Wikipedia…").

## Anotação (só no arquivo-mestre)

Logo abaixo do cabeçalho de cada bloco:

```
<!-- fontes: pref:turismo/bar-do-helio, osm:way/452300226, cnes:9208887, wiki, wikidata, ibge, web:https://..., manus | confianca: oficial|aberto|secundario|nao_verificado | nota: texto livre -->
```

Comentários soltos, fora dos blocos: `<!-- conflito: ... -->` e `<!-- lacuna: ... -->`. O `compilar_base.py` tira todos os comentários da base, gera o `.fontes.json` e acusa as violações.
