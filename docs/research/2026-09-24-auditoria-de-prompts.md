# Auditoria de prompts — padrões datados e erros de contrato

Data: 2026-09-24 · Método: `/claude-api prompt-audit` (guia `shared/prompt-audit.md`) · Nenhuma edição aplicada; o diff abaixo é proposta.

## Premissas (corrija rodando de novo com um escopo mais estreito)

- **Escopo:** toda a superfície de prompt do repositório (inventário abaixo). Ficaram de fora os arquivos do impeccable (`.claude/skills/impeccable/`, `.claude/agents/impeccable-*.md`), que são de terceiros e instalados pela ferramenta, os `SKILL.md` dentro de `backend/.venv` e os planos antigos em `docs/superpowers/plans/`, que são registro histórico.
- **Modelo-alvo:** o repositório não chama a API da Anthropic. Os marcadores de outros provedores são `langchain_google_genai` (`backend/app/core/llm/gemini.py:18`), `ChatOpenAI` apontando para Ollama/MLX (`backend/app/core/llm/ollama.py`, `custom.py`) e `gemini-2.5-flash-lite` (`gemini.py:5`). Por isso o alvo é o que o código usa: **Gemini 2.5 Flash-Lite** e LLMs locais pequenos (Qwen2.5-7B-Instruct-4bit no MLX, qwen3:1.7b no Ollama). A exceção é `CLAUDE.md` e os hooks do Claude Code, cujo alvo é o modelo do Claude Code (Claude Opus 5.5 nesta sessão). Esta auditoria não propõe trocar nada para o SDK da Anthropic.
- **Consequência:** as tabelas de padrões do guia se apoiam no comportamento documentado dos modelos Claude, e esse raciocínio não se transfere sozinho para Gemini e modelos locais de 1,7B–7B. Para modelos pequenos, linguagem enfática de formato (`APENAS`, "exatamente") costuma ser necessária de fato. Por isso quase todo achado do Grupo 1a vira `flag` de baixa confiança, e os achados fortes deste relatório são **erros de contrato e de contexto**, verificáveis no próprio código.
- **Proveniência:** todos os prompts são de 2026-07 (`git log -- backend/prompts`) e foram escritos já para esses modelos. Não há resíduo de gerações antigas de Claude.

## Inventário

| Superfície | Arquivos |
|---|---|
| Prompts das técnicas de RAG | `backend/prompts/{naive,agentic,hyde,rerank,crag,compression,multi_query}/*.md` + padrões embutidos em `backend/app/core/prompts/loader.py` |
| Nós da conversa | `backend/prompts/conversation/{guardrail,triage,memory,persona_compose}.md` + padrões em `backend/app/core/chat/flow_prompts.py` |
| Personas | `backend/prompts/personas/{travel_guide,assistant}.md` + padrões em `backend/app/core/personas/loader.py` |
| Montagem das requisições | `backend/app/core/llm/{gemini,ollama,custom}.py`: sem `temperature`, `stop` nem JSON forçado. Saídas lidas por `startswith`/regex em `crag.py:37`, `rerank.py:17`, `agentic.py:39-43`, `chat/graph.py:35,39` |
| Definições de ferramentas | nenhuma (`bind_tools`/`@tool` não aparecem no código) |
| Regras do Claude Code | `CLAUDE.md`, `.claude/settings.json` (hooks do graphify) |

## Resumo

- **Grupo 1 (texto datado):** 2 achados com proposta (memória, idioma dos prompts de resposta) e 4 flags de baixa confiança.
- **Grupo 2 (arquivos de regras):** 1 achado de alta confiança (`CLAUDE.md` manda ler um arquivo que não existe).
- **Grupo 3 (ferramentas):** 1 achado de confiança média-alta (as personas mandam usar uma ferramenta de busca que não existe).
- **Grupo 4 (configuração/arquitetura):** 2 flags (número de chamadas por mensagem no chat e hook do graphify em todo Bash).

Os três achados de maior impacto:

1. **Os prompts de resposta estão em idiomas diferentes conforme a técnica.** `naive` e `agentic` pedem a resposta em inglês; `hyde`, `rerank`, `crag` e `compression`, em português. Além disso, o `agentic` não tem a cláusula "se o contexto não bastar". Numa comparação entre técnicas de RAG, isso mistura o efeito da técnica com o efeito do prompt, e o ROUGE-L e as métricas de embedding comparam com referências em PT-BR.
2. **As personas descrevem uma ferramenta que o modelo não tem.** O fluxo da conversa não expõe ferramentas: o RAG roda no nó de triagem e o resultado entra como "Informação de apoio". A instrução "use a ferramenta de busca" não tem como ser seguida.
3. **`CLAUDE.md` abre com uma instrução para ler `HANDOFF.md`,** que foi removido no commit `725c283`. Toda sessão começa tentando ler um arquivo inexistente.

## Achados

### A1 — `CLAUDE.md` aponta para um arquivo removido
- **Local:** `CLAUDE.md:5-6`
- **Evidência:** "## ⚠️ Ao iniciar a sessão — **Leia o `HANDOFF.md` na raiz** — ele resume o estado, as decisões e as pendências da última sessão."
- **Padrão:** Grupo 2, informação volátil (afirmações factuais que apodrecem quando o código muda).
- **Por que está obsoleto:** `HANDOFF.md` não existe. O commit `725c283` diz "drop the internal HANDOFF.md session scratch". O Claude Code segue esse tipo de instrução ao pé da letra e gasta a abertura de toda sessão numa leitura que falha. O `⚠️` ainda dá peso a uma instrução morta.
- **Confiança:** alta (fato verificável).
- **Ação:** `remove`.

### A2 — As personas mandam usar uma ferramenta de busca que não existe
- **Local:** `backend/prompts/personas/travel_guide.md:1`, `backend/prompts/personas/assistant.md:1`, `backend/app/core/personas/loader.py:12-14,18-19`
- **Evidência:** "Sempre que precisar de informações específicas sobre o destino, use a ferramenta de busca disponível e baseie a resposta no que encontrar." / "Use a ferramenta de busca para fundamentar respostas…"
- **Padrão:** Grupo 3, nomes de ferramenta na prosa que não correspondem à lista real (a descrição precisa bater com o comportamento, e divergência de contrato leva o modelo por caminhos que nenhum texto conserta).
- **Por que está obsoleto:** `chat/graph.py` não liga ferramentas ao LLM. A busca é decidida pelo nó `triage` e o texto recuperado chega pelo placeholder `{context}` como "Informação de apoio" (`persona_compose.md:5`). Um modelo pequeno que lê "use a ferramenta de busca" pode escrever que vai buscar, ou dizer que não conseguiu. Aproveitei para corrigir "Voce detem" na mesma linha.
- **Confiança:** média-alta. O descompasso é certo; o efeito no comportamento não foi medido.
- **Ação:** `rewrite` (hunks H2a–H2c).

### A3 — Prompts de resposta em idiomas diferentes entre as técnicas comparadas
- **Local:** `backend/prompts/naive/answer.md:1-8`, `backend/prompts/agentic/answer.md:1-8`, e os padrões em `backend/app/core/prompts/loader.py` (naive e `agentic.answer`, linhas 45-46)
- **Evidência:** naive: "Use the context below to answer the question. If the context is not enough, say what you can." · agentic: "Answer the question using the context." · hyde/rerank/crag/compression: "Use o contexto abaixo para responder a pergunta. Se o contexto nao for suficiente, diga o que for possivel."
- **Padrão:** a regra de rebaseline do guia ("re-baselining adds text too"). Não é resíduo de modelo antigo; é contexto que falta ou diverge.
- **Por que importa:** o Ditto compara técnicas de RAG. Com prompts de resposta diferentes em idioma e em conteúdo (o `agentic` não diz o que fazer quando o contexto não basta), parte da diferença de nota vem do prompt e não da técnica. Modelos pequenos seguem o idioma do prompt com mais frequência que o da pergunta. Uma resposta em inglês comparada a uma referência em PT-BR derruba o ROUGE-L (sobreposição de palavras) e reduz o cosseno mesmo com embedders multilíngues.
- **Confiança:** média (fundamentada no desenho experimental do projeto; o tamanho do efeito não foi medido).
- **Ação:** `rewrite` (H3a–H3c) para o mesmo texto PT-BR das outras técnicas. Os prompts ficam salvos em cada experimento (`_snapshot_prompts`), então os resultados antigos continuam rastreáveis, mas não são diretamente comparáveis com os novos.

### A4 — Instrução para um caso que o código já trata
- **Local:** `backend/prompts/conversation/memory.md:1`, `backend/app/core/chat/flow_prompts.py:29`
- **Evidência:** "Se estiver vazio, responda com vazio."
- **Padrão:** Grupo 1d, instrução sem efeito (uma regra que o código já garante não precisa estar em prosa).
- **Por que está obsoleto:** `chat/graph.py:50-52` retorna `{"summary": ""}` sem chamar o modelo quando o histórico está vazio. O modelo nunca recebe histórico vazio, e a frase só ensina uma resposta ("vazio") que poderia vazar para o resumo de um histórico curto.
- **Confiança:** média.
- **Ação:** `remove` (H4a–H4b).

### Flags (sem edição proposta)

| # | Local | Evidência | Padrão | Por que só flag |
|---|---|---|---|---|
| F1 | `conversation/guardrail.md:1`, `conversation/triage.md:1` | "Responda APENAS com 'OK'…", "Responda APENAS com uma palavra" | 1a, linguagem enfática | Os parsers dependem do prefixo (`graph.py:35,39`) e os modelos locais de 1,7B–7B de fato precisam de formato rígido. A razão do guia (modelos Claude atuais aplicam ênfase em excesso) não vale para esse alvo. Baixa. |
| F2 | `naive/answer.md:8`, `*/answer.md` ("Resposta:"), `hyde/hypothesis.md:5`, `rerank/rerank.md:8` | Deixa final no estilo de completion ("Answer:", "Ordem:") | Datação por estilo (estilo de modelo de completion) | Inofensivo em modelo de chat. Só datação por estilo, sem motivo documentado para o alvo. Baixa. |
| F3 | `rerank/rerank.md`, `crag/grade.md`, `agentic/decide.md`, `conversation/triage.md` | Formato forçado em prosa + parsing por regex/prefixo | 1b, forçar JSON/formato por prosa → structured outputs | Gemini aceita esquema de resposta; o servidor MLX e o Ollama variam. Trocar exige mexer nas três implementações de LLM. Vale fazer se o parsing falhar nos logs. Baixa. |
| F4 | `*/answer.md`, `crag/*.md`, `hyde/*.md`, `compression/*.md` | Português sem acento ("nao", "possivel", "paragrafo", "e") | Excesso de apego a exemplo (o modelo imita o registro do prompt) | Um modelo pequeno pode responder sem acento. O ROUGE-L do Ditto compara tokens exatos, e "nao" ≠ "não". Efeito não medido. Baixa. |
| F5 | `chat/graph.py:34-39,53,62` | Até 4 chamadas ao LLM por mensagem, mais as do RAG (guardrail, triage, memory, persona) | Grupo 4, contar os pontos de chamada ao modelo | Guardrail e triage classificam a mesma entrada e caberiam numa chamada ("OK-RAG / OK-DIRECT / BLOCK"). Isso reduz o uso de cota do Gemini, que é a dor atual. É mudança de arquitetura, não de texto. Média, mas fora do escopo de edição de prompt. |
| F6 | `.claude/settings.json:5-9` → `graphify.sh hook-guard` | O hook injeta "MANDATORY: … You MUST run `graphify query`…" em **todo** Bash (curl, make, pytest) | 1a (ênfase disparando em excesso) | O texto vem do graphify, que é de terceiros. O matcher `Bash` não filtra por comando. Poderia ser restrito a `Grep\|Glob` se atrapalhar. Baixa. |

## O que foi mantido de propósito

- Os contratos de formato (`SEARCH:`/`ANSWER:`, `SUFICIENTE`/`INSUFICIENTE`, números separados por vírgula) são lidos pelo código e ficam.
- "Preserve os fatos; nao invente" em `compression/compress.md` descreve a tarefa (extrair, não parafrasear) e fica.
- A duplicação entre os `.md` e os padrões embutidos em código é redundância que funciona (os textos batem). O guia pede para não mexer.

## Diff proposto

Um achado por hunk; aceite só os que quiser. Os planos antigos em `docs/superpowers/plans/` citam os textos velhos e ficam como registro histórico. Nenhum teste compara esses textos (`grep` feito em `backend/tests` e `frontend/src`).

### H1 — A1: remover a instrução do HANDOFF.md

```diff
--- a/CLAUDE.md
+++ b/CLAUDE.md
@@
 Sistema de doutorado: ingere documentos, roda experimentos de RAG (chunking × embedding × rag × retriever) sobre perguntas e rankeia por métricas de qualidade.
 
-## ⚠️ Ao iniciar a sessão
-**Leia o `HANDOFF.md` na raiz** — ele resume o estado, as decisões e as pendências da última sessão.
-
 ## Como iniciar o sistema (Docker)
```

### H2a — A2: persona do guia de viagem

```diff
--- a/backend/prompts/personas/travel_guide.md
+++ b/backend/prompts/personas/travel_guide.md
@@
-Você é um guia de viagem simpático e prestativo, Voce detem conhecimentos sobre a cidade de Santo Antonio da Alegria. Responda em português, de forma conversacional, ajudando o usuário a planejar e conhecer o destino. Sempre que precisar de informações específicas sobre o destino, use a ferramenta de busca disponível e baseie a resposta no que encontrar. Se não houver informação suficiente, diga o que sabe e seja honesto sobre limites.
+Você é um guia de viagem simpático e prestativo, com conhecimento sobre a cidade de Santo Antonio da Alegria. Responda em português, de forma conversacional, ajudando o usuário a planejar e conhecer o destino. Baseie as informações específicas sobre o destino na informação de apoio que acompanha a mensagem. Se ela não bastar, diga o que sabe e seja honesto sobre os limites.
```

### H2b — A2: persona do assistente

```diff
--- a/backend/prompts/personas/assistant.md
+++ b/backend/prompts/personas/assistant.md
@@
-Você é um assistente prestativo e objetivo. Responda em português. Use a ferramenta de busca para fundamentar respostas quando a pergunta depender de informações específicas do domínio.
+Você é um assistente prestativo e objetivo. Responda em português. Quando a pergunta depender de informações específicas do domínio, baseie a resposta na informação de apoio que acompanha a mensagem.
```

### H2c — A2: padrões embutidos das personas

```diff
--- a/backend/app/core/personas/loader.py
+++ b/backend/app/core/personas/loader.py
@@
     "travel_guide": (
         "Você é um guia de viagem simpático e prestativo. Responda em português, "
         "de forma conversacional, ajudando o usuário a planejar e conhecer o destino. "
-        "Sempre que precisar de informações específicas sobre o destino, use a "
-        "ferramenta de busca disponível e baseie a resposta no que encontrar. "
-        "Se não houver informação suficiente, diga o que sabe e seja honesto sobre limites."
+        "Baseie as informações específicas sobre o destino na informação de apoio "
+        "que acompanha a mensagem. Se ela não bastar, diga o que sabe e seja honesto "
+        "sobre os limites."
     ),
     "assistant": (
         "Você é um assistente prestativo e objetivo. Responda em português. "
-        "Use a ferramenta de busca para fundamentar respostas quando a pergunta "
-        "depender de informações específicas do domínio."
+        "Quando a pergunta depender de informações específicas do domínio, baseie "
+        "a resposta na informação de apoio que acompanha a mensagem."
     ),
```

### H3a — A3: prompt de resposta do naive

```diff
--- a/backend/prompts/naive/answer.md
+++ b/backend/prompts/naive/answer.md
@@
-Use the context below to answer the question. If the context is not enough, say what you can.
+Use o contexto abaixo para responder a pergunta. Se o contexto nao for suficiente, diga o que for possivel.
 
-Context:
+Contexto:
 {context}
 
-Question: {question}
+Pergunta: {question}
 
-Answer:
+Resposta:
```

### H3b — A3: prompt de resposta do agentic

```diff
--- a/backend/prompts/agentic/answer.md
+++ b/backend/prompts/agentic/answer.md
@@
-Answer the question using the context.
+Use o contexto abaixo para responder a pergunta. Se o contexto nao for suficiente, diga o que for possivel.
 
-Context:
+Contexto:
 {context}
 
-Question: {question}
+Pergunta: {question}
 
-Answer:
+Resposta:
```

### H3c — A3: padrões embutidos (naive e agentic)

Aplicar em `backend/app/core/prompts/loader.py` o mesmo texto de H3a/H3b nos padrões `naive.answer` e `agentic.answer` (linhas 45-46 para o agentic), para que o fallback sem arquivo tenha o mesmo comportamento. Se F4 for aceito depois, os acentos entram nos seis `answer.md` de uma vez; os textos devem continuar idênticos entre as técnicas.

### H4a — A4: memória (arquivo)

```diff
--- a/backend/prompts/conversation/memory.md
+++ b/backend/prompts/conversation/memory.md
@@
-Resuma em poucas frases o histórico de conversa abaixo, mantendo o que importa para continuar o diálogo. Se estiver vazio, responda com vazio.
+Resuma em poucas frases o histórico de conversa abaixo, mantendo o que importa para continuar o diálogo.
```

### H4b — A4: memória (padrão embutido)

```diff
--- a/backend/app/core/chat/flow_prompts.py
+++ b/backend/app/core/chat/flow_prompts.py
@@
     "memory": (
         "Resuma em poucas frases o histórico de conversa abaixo, mantendo o que "
-        "importa para continuar o diálogo. Se estiver vazio, responda com vazio.\n\n"
+        "importa para continuar o diálogo.\n\n"
         "Histórico:\n{history}"
     ),
```

## Verificação sugerida (Passo 7)

- **A3:** rode o mesmo experimento pequeno (`database/perguntas_min.csv`, uma LLM local, `naive` + `hyde`) antes e depois de H3. Compare o idioma das respostas e o ROUGE-L do `naive`. Se as respostas já saírem em português, a mudança só remove o confundidor sem mudar notas.
- **A2:** converse com a persona `travel_guide` e procure respostas que falem em "buscar", "ferramenta" ou "pesquisar". Faça isso antes e depois.
- **A4:** confira alguns resumos de memória com 1 ou 2 turnos de histórico.
