# Diretrizes para documentos de entrada

Regras para preparar qualquer base (FAQ, manual, artigo, catálogo, tabela) antes de ingeri-la no Ditto. Valem para o pipeline de hoje: chunkers `markdown`, `recursive`, `token`, `fixed` e `semantic`, e payload só com o texto do chunk. A fundamentação, com fontes e nível de evidência, está em [docs/research/2026-09-26-formatacao-de-dados-para-rag.md](../docs/research/2026-09-26-formatacao-de-dados-para-rag.md). O exemplo aplicado é `faq_manus_normalizado.md`, a versão normalizada de `faq_manus_completa.md`.

Nível de evidência entre colchetes: **[forte]** resultado publicado e controlado; **[misto]** resultado publicado, mas de outro domínio ou língua; **[fornecedor]** guia de ferramenta sem experimento; **[conjectura]** raciocínio sem fonte direta.

## 1. Nunca sobrescrever o original

- Guarde o arquivo bruto como veio (`<base>.md`) e a versão preparada ao lado, com sufixo `_normalizado` (`<base>_normalizado.md`).
- As duas versões entram nos experimentos como níveis de um mesmo fator. O efeito do formato depende do modelo e da configuração, então fixar um formato só distorce a comparação. [misto]
- A versão normalizada muda a **forma**, nunca os **fatos**. Não invente informação para preencher lacunas. Registre as lacunas (seção 9).

## 2. Arquivo

- Texto UTF-8 em Markdown (`.md`). O `/ingest` só aceita texto UTF-8 e não faz parsing de PDF, DOCX ou HTML. Converta esses formatos antes e revise o resultado da conversão (quebras de linha no meio de frase, cabeçalhos e rodapés de página repetidos, hifenização).
- Um tema por arquivo. Bases com temas diferentes viram arquivos diferentes.
- No topo, um bloco curto de contexto com o título do documento, o assunto e a data em que as informações foram reunidas (ex.: "Informações reunidas em outubro de 2025"). [fornecedor]

## 3. Unidade: um bloco por pergunta ou tópico

É a regra que mais pesa no pipeline de hoje. O `markdown` faz um chunk por cabeçalho e repete os cabeçalhos acima dele. O `recursive` corta primeiro nas **linhas em branco** e só depois junta pedaços até 1000 caracteres. Para servir aos dois:

- **Cada unidade é um bloco**: um cabeçalho `###` seguido do conteúdo, **sem nenhuma linha em branco dentro**. Linha em branco só **entre** unidades. Assim nenhum chunk começa no meio de uma resposta ou de uma lista sem o título. [misto: chunking por elemento estrutural]
- **Tamanho: até ~800 caracteres por bloco**, incluindo o cabeçalho. Um bloco maior que 1000 é cortado nas quebras de linha e perde o título. Os 800 deixam margem. Se o assunto não cabe, divida em duas unidades, cada uma com o próprio cabeçalho. [misto: chunks pequenos favorecem perguntas factuais]
- **Cabeçalho**: em FAQ, é a pergunta; em manual ou artigo, é o título da seção, escrito como a pergunta que ela responde ou como um tópico explícito ("Horário de funcionamento da biblioteca"). Sem numeração ("### 12."), que não carrega significado. [conjectura para a numeração]
- Hierarquia: o `markdown` já leva os cabeçalhos de nível acima (`#`, `##`) para cada chunk, mas os outros chunkers não. Por isso, mesmo com capítulos, o cabeçalho da unidade tem que se sustentar sozinho ("### Garantia do produto X: prazo para troca").

Com o `recursive`, dois ou três blocos pequenos ainda podem cair no mesmo chunk; com o `markdown`, não. Não force blocos maiores só para evitar a junção: é o chunker que decide.

## 4. Autocontido: cada bloco entendido sozinho

O chunk chega ao retriever e ao LLM sem os vizinhos.

- **Nomeie a entidade principal em todo bloco**, no cabeçalho e no corpo (ex.: "em Santo Antônio da Alegria", não "aqui" nem "nossa cidade"). [forte: unidades autocontidas (Dense X); misto: resolução de correferência]
- **Sem referências a outras partes**: nada de "como mencionei", "acima", "lá", "isso", "o item anterior", "embora já mencionado". Repita a informação necessária.
- **Listas**: a frase de abertura diz do que é a lista ("Atividades gratuitas em …:"). Cada item carrega o qualificador essencial ("de entrada gratuita"), porque um corte pode separar item e abertura. Itens com `- `, um por linha, sem linha em branco entre eles.
- **Tempo absoluto**: troque "hoje", "esta semana", "atualmente", "a data atual" por mês e ano. Perguntas temporais do usuário ("tem evento essa semana?") são resolvidas pelo sistema, não pelo documento. [fornecedor + conjectura]

## 5. Nomes e termos consistentes

- Um **nome canônico** por entidade. Na primeira menção em cada bloco, coloque o apelido ou nome alternativo entre parênteses: "Praça Tereza Benedeti Chocair (Praça da Matriz)", "Cachoeira do Baú (Cachoeira do Deosdédi)". O usuário pode usar qualquer um dos dois. [fornecedor]
- Siglas: expanda na primeira menção do bloco. Se a expansão não for conhecida, descreva o que a sigla é ("EXPOASA, evento anual com shows…"). Não invente a expansão.
- A mesma coisa sempre com o mesmo termo (não alterne "rodoviária", "terminal" e "estação" para o mesmo lugar).

## 6. Remover ruído, manter estrutura

Remover:
- marcadores de citação sem lista de fontes (`[1]`, `[2, 3]`). Se as fontes existirem, guarde-as fora do texto;
- saudações, persona e encerramentos que não respondem a nada ("Olá, viajante!", "Como seu guia…", "Espero que aproveite!");
- interjeições e enchimento ("Ah,", "Absolutamente!", "Sem dúvida");
- ênfase inline (`**negrito**`, `_itálico_`): não há efeito medido no embedding, e ela fragmenta o texto dos chunkers por token e por caractere. [conjectura]
- restos de template ("(ou montanha, dependendo do lugar)").

Manter: cabeçalhos `###`, listas e a ordem lógica do texto. A estrutura ajuda o LLM a ler o contexto recuperado. [misto]

**[misto por analogia; remover persona é conjectura]**

## 7. Cabeçalho fiel ao conteúdo

- O cabeçalho promete exatamente o que o bloco responde. Se a pergunta original é "horário das lojas" e a resposta traz o horário de dois lugares específicos, reescreva o cabeçalho para nomeá-los. Em FAQ, casar a consulta com a pergunta é o sinal de recuperação mais forte. [forte, em inglês]
- Mantenha o registro coloquial das perguntas originais ("pra", "dá pra"), porque é como o usuário pergunta.
- **Nunca** escreva cabeçalhos ou paráfrases a partir das perguntas do conjunto de teste (`perguntas*.csv`). Isso vaza o teste para a base e infla as métricas.
- Paráfrases de perguntas, palavras-chave e resumos por bloco são **enriquecimento do pipeline** (doc2query com filtro), não edição manual do documento.

## 8. Tabelas e dados estruturados

- Tabela pequena (até ~10 linhas) cabe num bloco: cabeçalho com o assunto e uma linha por registro no formato `coluna: valor; coluna: valor`.
- Tabela grande: **um bloco por registro** (ou por grupo pequeno de registros), cada um com um cabeçalho que nomeia o registro e repete o nome das colunas. Assim nenhum chunk traz números sem saber de que coluna são. [conjectura para o nosso chunker; para o LLM ler, a literatura favorece HTML/Markdown estruturado]
- JSON, CSV ou planilhas não entram crus: converta para esses blocos até existir um parser dedicado no pipeline.

## 9. Avaliação: perguntas e evidências

- A `evidencia_referencia` de cada pergunta é um trecho **copiado do texto da versão ingerida**. As métricas gold procuram o trecho nos chunks por alinhamento aproximado (`partial_ratio ≥ 80`, depois de ignorar caixa, pontuação e Markdown, em `backend/app/core/evaluation/gold_metrics.py`).
- Ao reescrever uma frase citada como evidência, prefira manter o trecho literal. Se não der, reanote a evidência para a versão nova. Um conjunto de perguntas só serve às duas versões (bruta e normalizada) se as evidências casarem nas duas (seção 10).
- Perguntas que a base não responde, ou responde só de passagem, devem ser marcadas como tal. Ex.: no FAQ de referência, "onde me hospedar" e "como chegar vindo de São Paulo".

## 10. Verificação antes de ingerir

Checklist por arquivo normalizado:

- [ ] original preservado; versão com sufixo `_normalizado`
- [ ] bloco de contexto no topo, com a data das informações
- [ ] toda unidade começa com `###`, sem linha em branco dentro, com até ~800 caracteres
- [ ] entidade principal nomeada em todo bloco; nenhum "aqui", "lá", "como mencionei", "acima"
- [ ] nenhuma data relativa
- [ ] nomes canônicos com apelido na primeira menção do bloco; siglas explicadas
- [ ] sem `[n]`, persona, negrito ou restos de template
- [ ] cabeçalhos fiéis à resposta e não copiados do conjunto de teste
- [ ] nenhum fato novo em relação ao original
- [ ] toda `evidencia_referencia` casa com algum chunk das versões usadas

Os itens mecânicos podem ser conferidos com o chunker e a métrica do próprio projeto (rodar de `backend/`):

```bash
PYTHONPATH=. ./.venv/bin/python - <<'EOF'
import csv
from pathlib import Path
from app.core.chunking.splitters import RecursiveChunker
from app.core.evaluation.gold_metrics import evidence_found_in

doc = Path("../database/faq_manus_normalizado.md").read_text(encoding="utf-8")
questions = Path("../database/perguntas.csv")

blocks = doc.split("\n\n")
print("blocos > 800 caracteres:", [b.splitlines()[0] for b in blocks if len(b) > 800])
chunks = RecursiveChunker().split(doc)
print("chunks que não começam em cabeçalho:", sum(not c.lstrip().startswith("#") for c in chunks))
for row in csv.DictReader(questions.open(encoding="utf-8")):
    for ev in row["evidencia_referencia"].split("|"):
        if not any(evidence_found_in(ev.strip(), c) for c in chunks):
            print("evidência sem chunk:", row["pergunta"], "->", ev.strip())
EOF
```

No FAQ de referência, o resultado é o seguinte. Com o `recursive`, o bruto gera 32 chunks, 28 com mais de uma pergunta e 3 começando no meio de uma resposta. O normalizado gera 30 chunks, 19 com mais de uma pergunta e nenhum começando fora de um cabeçalho. Com o `markdown`, os dois arquivos ficam com uma pergunta por chunk (52 e 51 chunks). Todas as evidências de `perguntas.csv` casam nas duas versões, com qualquer um dos dois chunkers.

## 11. O que não é papel do documento

Não tente compensar no texto o que é do pipeline. Já resolvidos no pipeline:
- um bloco por chunk: chunker `markdown` (`backend/app/core/chunking/markdown.py`);
- prefixos `passage: `/`query: ` do e5 (`backend/app/core/embedding/huggingface.py`).

Ainda pendentes, como técnicas plugáveis (interface + registry):
- guardar o cabeçalho e a data no payload do Qdrant;
- contextualização automática de chunks, paráfrases (doc2query) e extração de entidades;
- um normalizador automático que aplique estas diretrizes a bases novas, para que o nível "normalizado" seja reprodutível e não dependa de edição manual.
