---
name: montando-base-de-cidade
description: Use quando o usuário pedir para montar, enriquecer, atualizar ou verificar uma base de conhecimento sobre um município brasileiro (cidade, turismo, história, eventos, estabelecimentos, serviços, saúde) para RAG ou consulta, ou para achar e checar fatos de uma cidade em fontes abertas e oficiais.
---

# Montando base de conhecimento de cidade

## Visão geral

A base só afirma o que uma fonte coletada sustenta. Colete primeiro, guarde o bruto com URL, licença e data, escreva um **arquivo-mestre anotado** e compile dele a base limpa. Texto gerado por LLM (inclusive FAQs prontos) é fonte `nao_verificado`: nunca vale mais que uma fonte oficial.

Scripts em `scripts/` (só stdlib, Python 3.10+). Rode `python3 <skill>/scripts/<script>.py --help` para as opções. Regras de escrita dos blocos: `regras-de-escrita.md`. Se o projeto tiver `database/DIRETRIZES.md`, ele prevalece.

## Fluxo

1. **Dados abertos** (IBGE, Wikidata, Wikipedia, Wikivoyage, OSM, CNES):
   `python3 scripts/coletar_cidade.py "Nome da Cidade" UF` → `fontes_brutas/<cidade>/` + `manifesto.json`.
   O código IBGE é resolvido pelo nome e pela UF. **Nunca digite o código à mão.**
2. **Site da Prefeitura**: procure a seção de turismo ou o guia (costuma haver `/turismo/?categoria=N`, história, telefones úteis, agenda). Baixe as páginas de categoria, extraia os links de detalhe e baixe:
   `python3 scripts/baixar_paginas.py fontes_brutas/<cidade>/web --from-file urls.txt --modo direto --paralelo 3`
   Use `--modo jina` só quando a página depende de JavaScript.
3. **Busca na web** para eventos, datas e gastronomia (secretaria estadual de turismo, circuitos turísticos, notícias). Conteúdo lido só pelo resumo do buscador conta como `secundario`.
4. **Ler o bruto e cruzar os fatos**. Para cada divergência, siga `oficial` > `aberto` > `secundario` > `nao_verificado` e registre `<!-- conflito: ... -->`. O que ninguém confirma vai em `<!-- lacuna: ... -->`.
5. **Escrever `fontes_brutas/<cidade>/guia.anotado.md`** seguindo `regras-de-escrita.md`. Cada bloco `###` leva `<!-- fontes: ... | confianca: ... | nota: ... -->`.
6. **Compilar e corrigir até sair com código 0**:
   `python3 scripts/compilar_base.py fontes_brutas/<cidade>/guia.anotado.md --saida guia_<cidade>.md --brutos fontes_brutas/<cidade> --prefeitura https://<site>/`
7. **Se houver conjunto de perguntas com evidências anotadas**, confira se cada evidência ainda aparece em algum chunk e liste as respostas de referência que a base nova contradiz. Não edite o conjunto de teste sem pedir.
8. **Relatar ao usuário**: quantos blocos há por nível de confiança, os conflitos resolvidos, as lacunas e os bloqueios de coleta.

## Referência rápida

| Fonte | Traz | Confiança | Licença |
|---|---|---|---|
| Prefeitura (site) | atrações, hospedagem, comércio, horários, telefones, história, eventos | oficial | dado público |
| IBGE / CNES | código, hierarquia territorial / unidades de saúde, turno 24 h | oficial | dado público |
| Wikidata / Wikipedia | população, área, vizinhos / história, cultura | aberto | CC0 / CC BY-SA |
| OpenStreetMap (Overpass) | morros com altitude, rios, polícia, rodoviária | aberto | ODbL (atribuir) |
| Resumo de buscador, sites de terceiros | eventos, siglas, contexto | secundario | verificar termos |

## Regras de coleta

- Só fontes gratuitas e abertas. Não raspe Google Maps, TripAdvisor nem sites cujos termos proíbem guardar os dados.
- CAPTCHA ou bloqueio encerra a coleta naquele domínio. Registre o bloqueio em `paginas.json` e não tente contornar.
- No máximo 3 conexões por site pequeno, com User-Agent que identifique o projeto.
- LGPD: não leve para a base nomes nem contatos de pessoas físicas, como consultórios com nome de profissional, contatos pessoais em anúncios ou coveiro. Agentes públicos eleitos podem aparecer.

## Erros comuns

| Erro | Correção |
|---|---|
| Código IBGE digitado à mão (errado); CNES e OSM devolvem outra cidade | Use o código de `ibge_municipio.json`. O CNES usa os 6 primeiros dígitos |
| Extração de HTML descarta endereço e telefone (linhas curtas) | O modo `direto` já mantém linhas com dígito ou "@". Confira uma página antes do lote |
| Jina lento (~20 páginas/min) | `--modo direto --paralelo 3`. Retome com `--pular-existentes` |
| Página estadual renderizada por JS vem vazia (Jina ou WebFetch) | Use o resumo do buscador como `secundario` |
| FAQ gerado por LLM com nome de lugar inventado ou horário errado | Verifique cada fato de FAQ gerado na fonte oficial, corrija e registre o conflito |
| Página de evento sem ano | Não invente o ano. Diga "a página não informa o ano" na `nota` |
| "hoje", "atualmente", "este ano" no texto | Use datas absolutas. O compilador acusa |
