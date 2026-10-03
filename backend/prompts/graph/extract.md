Extraia do texto abaixo as entidades e as relações entre elas, para montar um grafo de conhecimento.

Entidades: lugares, estabelecimentos, eventos, pessoas, organizações, produtos e serviços citados no texto. Para cada uma, escreva uma linha:
entidade<|>nome<|>tipo<|>descrição

- nome: como aparece no texto, sem abreviar.
- tipo: um destes: lugar, estabelecimento, evento, pessoa, organizacao, produto, servico.
- descrição: uma frase com o que o texto diz sobre a entidade.

Relações: ligações entre duas entidades que você listou. Para cada uma, escreva uma linha:
relacao<|>origem<|>destino<|>palavras-chave<|>descrição

- origem e destino: nomes exatamente iguais aos das linhas de entidade.
- palavras-chave: duas a quatro palavras sobre a natureza da ligação, separadas por vírgula.
- descrição: uma frase com o que o texto diz sobre a ligação.

Regras:
- Use só o que está escrito no texto. Não invente.
- Uma entidade ou relação por linha, sem numeração, sem marcadores e sem comentários.
- Escreva <|FIM|> na última linha.

Exemplo
Texto: A Praça Tiradentes, no centro de Ouro Preto, abriga o Museu da Inconfidência, que guarda objetos do período colonial.
Saída:
entidade<|>Praça Tiradentes<|>lugar<|>Praça no centro de Ouro Preto.
entidade<|>Ouro Preto<|>lugar<|>Cidade onde fica a Praça Tiradentes.
entidade<|>Museu da Inconfidência<|>estabelecimento<|>Museu que guarda objetos do período colonial.
relacao<|>Praça Tiradentes<|>Ouro Preto<|>localização, centro<|>A Praça Tiradentes fica no centro de Ouro Preto.
relacao<|>Museu da Inconfidência<|>Praça Tiradentes<|>localização, sede<|>O Museu da Inconfidência fica na Praça Tiradentes.
<|FIM|>

Texto: {text}
Saída:
