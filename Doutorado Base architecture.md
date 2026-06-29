Preciso construir um sistema para meu doutorado, o projeto é basicamente um sistema onde usuário insere um conjunto de documentos, ele é inserido em um banco vetorial, essa inserção é feita com várias técnicas de corte de documentos que vão ser listadas. Ao fim é aplicado várias técnicas de RAG com, todas as múltiplas opções de retriever criadas, com das respostas feitas é avaliado através de algumas métricas a qualidade da resposta para indicar qual composição de metodologia (rag \+ retriever) geram a melhor resposta. Pode ser possível trocar o modelo de LLM e o modelo de embedding, portanto os testes serão configuráveis dado um conjunto de opção.

A segunda parte do sistema é, dado que a melhor solução descoberta anteriormente é criar um sistema agêntico que utiliza ela. A ideia desse sistema é ser um agente que sabe responder perguntas buscando na técnica de RAG e responder. Ao fim da interação a conversa será salva. Deverá ser exibida em outra tela para uma avaliação. O modelo de LLM aqui pode ser facilmente trocado.

Por fim com diálogos salvo do processo, ideia fazer o fine-tuning de um modelo com as respostas bem avaliadas e usar ela no processo anterior.

Base do projeto como um todo é criar um sistema que define melhor cold-start do modelo trazendo um bom fluxo com rags para dar boas respostas, porém com o passar  do tempo e do uso, ideia é q o modelo seja fine-tundado e própria rag nao seja relevante mais para o sistema.

O modelo final idealmente será um modelo pequeno, com poucos B mas vamos usar alguns modelos maiores durante a fase de desenvolvimento.

 ele é composto por alguns componentes:

- **Frontend**: Responsável por "pilotar” os fluxos de backend. Esse front conta com algumas telas:  
  - Tela de inserir documentos: Deve ser possível inserir 1 ou mais documentos em formato txt. Essa tela de inserção deve passar algumas configurações de inserções, quais técnicas de rag usar, qual nome da base das coleções que deve ser criado, quais modelos (dos disponíveis) de embedding usar.  
  - Tela de gerar teste de qualidade: dado base disponível do processo anterior, uma tela para selecionar quais técnicas (das disponíveis) usar e quais metodologias de avaliação usar. Ao ser pedido isso, deve ser criado um nome do experimento para associar essa execução, que pode ser um nome aleatório ou um inserido pelo usuário. Nessa tela para avaliação deverá ser passado um arquivo com as perguntas que devem ser feitas no experimento. Essa tela deve virar a tela de visualização de resultados ao fim da geração deles.  
  - Tela de visualização de resultados: tela para dado um experimento criado visualizar com pergunta feita, resposta gerada, configuração que gerou a resposta e scores de métrica. A visualização pode ser clean e ao clicar na row abrir um card com os dados completos dessa informação do experimento.  
  - Tela de configurações de chat: dado os experimentos e as configurações, uma tela onde você pode criar uma configuração de chat para quando entrar no chat o agente de conversa do back saber qual rag, embedding, e retriever usar naquele diálogo.  
  - Tela de conversa: onde é um chat, mesmo que você possa selecionar uma configuração e dialogar com o agent, ao fim da conversa ( que é ditado pelo usuário) deve-se perguntar se quer ou não salvar o diálogo realizado.  
  - Tela de avaliação de diálogo, dado um diálogo anterior ocorrido, o usuário pode abrir o diálogo, ler a conversa e dizer se foi um diálogo positivo ou negativo. Então é salvo essa avaliação humana.

- **Insert Doc Backend**: Responsável por pegar os documentos, fazer os devidos recortes com as técnicas de retriever listadas abaixo, fazer embedding dos documentos e inserir no banco vetorial. Isso dado uma configuração passada.  
  - Técnicas de corte de documento que devem ser implementadas:   
  - embeddings:  
  -   
- **Técnicas de Rag**: Módulo responsável por esta codificado a lógica das rag. Nela terá todo código das múltiplas opções disponíveis para se usar uma rag. Algumas opções além dessa podem ser adicionadas ao processo e isso deve ser feito de modo simples. O modelo de LLM usado nesses processo deve ser facilmente trocado também. Esse módulo deve ser ativado conforme as configurações passadas.

 Técnicas já listadas:

- Naive rag  
  - AgenticRag  
  - GraphRag  
- **avaliação de respostas**: Dado um uma pergunta, uma resposta base(opcional) e resposta gerada pela IA gerar um score de avaliação com algumas métricas da area.   
  - Tecnicas: Me ajude a definir as técnicas de avaliação que podem ser usadas.  
- **Sistema conversacional**: Dado uma configuração definida pelos módulos anteriores, criar um agent completo onde o intuito é o agent ser capaz de responder  a pergunta da pessoa conversando com ela. Isso vai muito além das técnicas de rag feitas anteriormente visto que agora não é só gerar melhor resposta mas sim conversar. Como linha de base do projeto vamos criar um fluxo agentico focando em ser um guia de viagem, onde dado um destino, que  terá todas as docs sobre esses destino fornecidas ali, por isso importância desse módulo, o agent conversacional deverá responder o usuário como uma conversa guiando ele conforme as perguntas que forem fazendo chamando a RAG sempre que necessário. Leve em conta que a ideia principal é que esse módulo seja de fácil manutenção e possivelmente trocar a persona fácil, uma hora ser um guia de viagem, outra ser um ajudante de um sac, etc.Esse sistema terá q ter uma memória, pode ser curta no momento, e limpa sempre q tiver um novo diálogo, porém terá que ser salvo todo diálogo ocorrido para depois posteriormente ser avaliado.  
- **avaliação de diálogo** : back disso será simples, basta puxar as conversas de onde estejam salvas e mandar pro front depois basta salvar com as notas.  
- **Fine-tunning**: esse modelo deve ser completamente desacoplado dos demais, e também será usado somente no futuro, então podemos ter apenas um código básico e não precisa testar se está funcionando ou não. Pode ser uma pasta chamada fine-tuning, nele quero q seja um notebook com 2 função  
  - Puxar os dados e preparar para o fine-tunning  
  - Executar o fine-tunning e gerar o modelo


  

  Tecnologias a serem usadas


- Frontend: pode ser um alguma tecnologia baseada em javascript, Importante é ser leve e funcionar, me ajude a escolher  
- Backend: Preferencial que seja tudo em python, um fastapi.   
  - Nesse ponto me ajude a entender melhor, temos vários modelos, e várias classes que podem ser reutilizadas em vários módulos, é melhor termos 1 serviço de back com vários endpoint ou vários serviços? O que eu não quero é ter código replicado, vários códigos de LLM e avaliação podem ser reaproveitados.  
- LLM: Para uso da LLM, Rags e embeddings, vamos usar o langchain como base de desenvolvimento. Os agents mais complexos vamos usar LangChain que é construído em cima do langchain. Importante aqui que tenhamos módulos para usar LLM custom aqui e também vamos usar o gemini via API KEY além do custo, visto que tem uso gratuito muito bom.  
- Fine-Tunning: Será feito com o unsloth como base. Os modelos serão passados no futuro.

	Diretrizes de implementação

- Mantenha o código simples, evite códigos complexos com uso de muitas classes, use apenas quando for necessário para evitar replicação de código.  
- Siga padrão PEP-8  
- Evite comentários dentro do código apenas o necessário e use docstring nas funções.  
- Use docker e docker compose para os componentes da aplicação  
- Crie um make file para comandar os usos da aplicação, principalmente para testar o uso depois.