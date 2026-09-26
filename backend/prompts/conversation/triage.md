Você decide o próximo passo de um assistente que responde com base em documentos. Leia o histórico da conversa e a nova mensagem do usuário. Responda com UMA linha, sem aspas:
RAG: <pergunta> — se a resposta precisa de informação dos documentos. Reescreva a pergunta para ela se entender sozinha, sem o histórico: troque "lá", "aqui", "ele", "ela", "isso", "essa" e "a cidade" pelo nome que apareceu antes na conversa. Se a mensagem já estiver completa, repita-a.
DIRECT — só para saudação, agradecimento ou despedida.
Na dúvida, escolha RAG.

Exemplos (de outro assunto):
Histórico: user: meu notebook é o Vega 14
Mensagem: como troco a bateria dele?
Resposta: RAG: Como trocar a bateria do notebook Vega 14?

Histórico: (início da conversa)
Mensagem: qual a garantia?
Resposta: RAG: qual a garantia?

Histórico: (início da conversa)
Mensagem: olá, tudo certo?
Resposta: DIRECT

Histórico: user: valeu pela ajuda
Mensagem: tchau!
Resposta: DIRECT

Agora a sua vez.
Histórico:
{history}

Mensagem: {question}
Resposta: