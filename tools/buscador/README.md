# Buscador: coleta de dados abertos para bases de conhecimento

Scripts para montar uma base de conhecimento sobre um município brasileiro a partir de fontes gratuitas e abertas. É a "camada 1" (bases prontas) e uma coleta simples de páginas da "camada 3" do plano em `../../../buscador.md`. Os scripts usam só a biblioteca padrão do Python 3.10+, sem venv e sem chave de API. Ficam fora do backend do Ditto de propósito.

## Fluxo

```bash
# 1. Dados abertos do município: IBGE, Wikidata, Wikipedia, Wikivoyage, OpenStreetMap, CNES
python3 tools/buscador/coletar_cidade.py "Santo Antônio da Alegria" SP
#    -> database/fontes_brutas/santo_antonio_da_alegria/{ibge_municipio,wikidata,osm_pois,cnes_estabelecimentos}.json,
#       wikipedia_pt.txt, manifesto.json (URL, licença, data de coleta)

# 2. Páginas da web (site da prefeitura, turismo): texto + URL + data
python3 tools/buscador/baixar_paginas.py database/fontes_brutas/<cidade>/web URL [URL ...]
python3 tools/buscador/baixar_paginas.py database/fontes_brutas/<cidade>/web \
    --from-file urls.txt --modo direto --paralelo 3
#    --modo jina   (padrão) Jina Reader: renderiza JavaScript, ~20 páginas/min sem chave
#    --modo direto HTML do servidor, sem dependências: bem mais rápido em sites de prefeitura

# 3. Escrever o arquivo-mestre anotado (à mão ou com um LLM), um bloco ### por unidade,
#    seguindo database/DIRETRIZES.md, com um comentário de fontes em cada bloco:
#      ### Bar do Hélio: bar e restaurante em Santo Antônio da Alegria
#      <!-- fontes: pref:turismo/bar-do-helio, osm:way/452300226 | confianca: oficial -->
#    e comentários <!-- conflito: ... --> e <!-- lacuna: ... --> para o que as fontes não resolvem.

# 4. Compilar: base limpa para o /ingest + JSON de fontes + verificação das diretrizes
python3 tools/buscador/compilar_base.py database/fontes_brutas/<cidade>/guia.anotado.md \
    --saida database/guia_<cidade>.md --brutos database/fontes_brutas/<cidade> \
    --prefeitura https://<site-da-prefeitura>/
#    -> database/guia_<cidade>.md (sem comentários) e database/guia_<cidade>.fontes.json
#    sai com código 1 se algum bloco violar as diretrizes (tamanho, [n], tempo relativo, sem fonte)
```

## Níveis de confiança usados nas anotações

| Valor | Quando usar |
|---|---|
| `oficial` | Prefeitura, IBGE, CNES e outros órgãos públicos |
| `aberto` | Wikipedia, Wikidata, OpenStreetMap |
| `secundario` | Páginas de terceiros, ou conteúdo lido só pelo resumo de um buscador |
| `nao_verificado` | Afirmação sem fonte encontrada (ex.: o FAQ gerado pelo Manus) |

## Regras de coleta (de `buscador.md`)

- Só fontes gratuitas e abertas. Não raspar Google Maps, TripAdvisor nem outros sites cujos termos proíbem guardar os dados.
- CAPTCHA ou bloqueio encerra a coleta daquele domínio. Nunca contornar. O erro fica registrado em `paginas.json`.
- User-Agent identifica o projeto; pausa entre requisições; no máximo 3 conexões simultâneas em sites pequenos.
- Guardar o texto bruto antes de qualquer resumo, com URL e data, para auditoria.
- LGPD: não copiar para a base nomes de pessoas físicas que não sejam agentes públicos, nem contatos pessoais (ex.: consultórios com nome de profissional, contatos de pessoas em anúncios de hospedagem).
- A licença de cada fonte fica no `manifesto.json` e no `.fontes.json`. OpenStreetMap exige a atribuição "© OpenStreetMap contributors" (ODbL), e texto da Wikipedia é CC BY-SA.
