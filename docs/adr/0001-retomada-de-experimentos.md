# Retomada de experimentos: perguntas no banco, sem retomada automática, thread travada abandonada

Para um Experimento poder ser retomado depois de uma Pausa ou de uma Interrupção (a API reiniciou), as perguntas do CSV passam a ser gravadas no banco junto com o Experimento. Até aqui elas viviam só na memória da tarefa em segundo plano. Depois de uma Interrupção os Experimentos ficam em Pausa e nunca retomam sozinhos: a causa mais provável de um reinício é falta de memória, e retomar automaticamente derrubaria a máquina de novo. Quando há Travamento, o watchdog pausa o Experimento, libera o slot de trabalho e abandona a thread presa, descartando qualquer resultado que ela traga depois, porque Python não consegue matar uma thread. A defesa principal é um timeout duro em cada chamada ao LLM e ao embedder remoto (metade do limite de Travamento), para que uma chamada travada falhe sozinha.

## Considered Options

- **Cada Combinação num subprocesso que pode ser morto**: mataria a chamada travada de verdade, mas exigiria refazer a gestão de memória (ModelManager, embedders compartilhados, cache de vetores das perguntas), que hoje depende de tudo rodar num só processo. Rejeitada por enquanto: os LLMs locais (MLX/Ollama) já rodam em outro processo e são acessados por HTTP, então na prática a thread presa fica esperando num socket e o timeout resolve.
- **Retomada automática no boot**: rejeitada pelo risco de repetir um crash por memória sem ninguém olhando.
