"""DEP-4: B3 question set (atendimento ao cidadão de Maceió), built from the candidate questions.

Questions come from two sources only: the candidates written by Claude Sonnet 5 from the
table of contents (perguntas_candidatas_sonnet.csv and _rodada2.csv, n = Sonnet number) and real citizen
doubts from the official FAQs (perguntas_reais_faq_triagem.csv, n = "faq<N>"). Question
wording is kept; the only edits are recorded in `edicao`. Reference answers and evidence
were written after reading the frozen base; every evidence passage is copied verbatim and
checked here against both versions. Run from the repository root:

    python3 database/fontes_brutas/maceio_atendimento/monta_perguntas.py
"""
import csv
import re
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE.parents[1] / "maceio_atendimento"
OUT = HERE.parents[1] / "perguntas_atendimento_maceio.csv"

# (origem, tipo, pergunta, resposta_referencia, [(evidência, salto)], entidades_ponte, edicao)
Q = [
    # ---------------- simples ----------------
    ("sonnet1", "simples", "Quanto custa pra tirar o boletim de acidente de trânsito?",
     "Na Prefeitura de Maceió (DMTT), a emissão do Boletim de Ocorrência de Acidente de Trânsito (BOAT) custa R$ 212,57, e a declaração de acidentes custa R$ 52,36.",
     [("Taxa: Emissão de BOAT: R$ 212,57 Emissão de DECLARACAO ACIDENTES: R$52,36", 1)], [], ""),
    ("sonnet2", "simples", "Qual secretaria cuida de poda de árvore em terreno particular?",
     "A poda em área particular é responsabilidade do proprietário, mas precisa de autorização prévia da ALURB (Autarquia de Desenvolvimento Sustentável e Limpeza Urbana).",
     [("A poda e supressão de árvore em área particular são de responsabilidade do proprietário do imóvel. No entanto, para realizá-las, é indispensável a autorização prévia da ALURB.", 1)], [], ""),
    ("sonnet4", "simples", "Como eu agendo a castração do meu bichinho de estimação?",
     "O pedido é cadastrado na Central de Atendimento da Secretaria de Bem Estar Animal (SEBEMA), pelo WhatsApp (82) 98752-6505; depois da triagem com veterinário, se o animal estiver apto, a equipe liga para agendar a cirurgia.",
     [("Cadastrar o pedido de serviço por meio da Central de Atendimento da Secretaria de Bem Estar Animal, no WhatsApp: (82) 98752-6505.", 1),
      ("Estando apto para castração a equipe do Gabinete ligará fazendo o agendamento do procedimento cirúrgico.", 1)], [], ""),
    ("sonnet5", "simples", "Quem pode propor uma emenda na lei orgânica do município?",
     "O Prefeito Municipal, pelo menos um terço dos membros da Câmara Municipal ou no mínimo 5% dos eleitores inscritos no município (art. 31 da Lei Orgânica).",
     [("Art. 31 A Lei Orgânica do Município poderá ser emendada mediante proposta do Prefeito Municipal, de pelo menos um terço (1/3) dos membros da Câmara Municipal ou de no mínimo cinco por cento (5%) dos eleitores inscritos no município.", 1)], [], ""),
    ("sonnet6", "simples", "O que pode acontecer com o prefeito se ele cometer uma falta grave no cargo?",
     "O Prefeito é julgado pelo Tribunal de Justiça do Estado nos crimes comuns e de responsabilidade, e pela Câmara Municipal nas infrações político-administrativas, caso em que a decisão se limita à cassação do mandato (art. 57).",
     [("Art. 57 O Prefeito Municipal será processado e julgado:", 1),
      ("pela Câmara Municipal, nas infrações político-administrativas, nos termos do Regimento Interno, assegurados, entre outros requisitos de validade, o contraditório, a publicidade, a ampla defesa e a suficiente motivação da decisão final, que se limitará à decretação da cassação do mandato do Prefeito", 1)], [], ""),
    ("sonnet11", "simples", "Como eu registro uma denúncia pela ouvidoria da prefeitura?",
     "Pelo site da Ouvidoria de Maceió (CGM): escolher o tipo de manifestação, o órgão e o assunto, descrever o caso, indicar o local da ocorrência e, sendo denúncia, informar o agente público envolvido (nome, função, órgão); a Ouvidoria garante sigilo.",
     [("Se for Denúncia, incluir informações sobre o agente público envolvido na situação denunciada (Nome, Função do Envolvido, Órgão / Empresa / Setor)", 1),
      ("Indicar o Local da ocorrência e um Ponto de Referência da Ocorrência (obrigatório).", 1)], [], ""),
    ("sonnet14", "simples", "Como funciona o processo pra aprovar uma lei na câmara municipal?",
     "Concluída a votação na Câmara, o projeto aprovado vai ao Prefeito, que o promulga ou o veta em até 15 dias úteis; o silêncio do Prefeito depois desse prazo vale como sanção (art. 36).",
     [("Art. 36 A Câmara, uma vez concluída a votação, remeterá o projeto de lei aprovado ao Prefeito Municipal que aquiescendo o promulgará.", 1),
      ("§ 3º Decorrido o prazo de quinze (15) dias, o silêncio do Prefeito importará sanção.", 1)], [], ""),
    ("faq36", "simples", "Como gerar a Guia de IPTU?",
     "Pelo site de serviços da SEFAZ (online.maceio.al.gov.br): em Guias de pagamento > Emissão de guias de pagamento, escolher o filtro IM Imobiliária (usado para IPTU e Taxa de Lixo), informar a matrícula do imóvel, pesquisar, selecionar as guias e imprimir. Não há taxa.",
     [("Filtros: “IM Imobiliária” para IPTU e Taxa de Lixo", 1),
      ("Selecionar a opção “Guias de pagamento“ > “Emissão de guias de pagamento“;", 1)], [],
     "numeração da FAQ removida; entrou no lugar de sonnet15, que o L0 acertou sem contexto (filtro R1)"),
    ("faq7", "simples", "Quais as garantias de proteção à minha identidade?",
     "A Ouvidoria de Maceió garante sigilo total nas manifestações, e é possível escolher a opção de não se identificar.",
     [("A Ouvidoria garante sigilo total nas suas manifestações.", 1),
      ("Selecionar opção de cadastro¹: Identificação Básica, Cadastro Completo ou Não quero me identificar.", 1)], [], "numeração da FAQ removida"),
    ("faq16", "simples", "Como acompanhar a resposta à manifestação?",
     "Quem tem cadastro completo acessa o histórico de manifestações e as respostas; quem fez a manifestação sem cadastro precisa informar o número do protocolo e o e-mail para consultar o andamento.",
     [("Se você fizer uma manifestação sem se cadastrar, precisará informar o número do protocolo e o seu e-mail para consultar o andamento.", 1),
      ("acesso ao histórico de manifestações e às respostas oferecidas pelo órgão ou entidade.", 1)], [], "numeração da FAQ removida"),
    ("faq17", "simples", "Para fazer um pedido de acesso à informação, como proceder?",
     "Pelo sistema da Lei de Acesso à Informação da CGM: fazer cadastro (ou entrar com CPF e senha), registrar o pedido escolhendo o tipo e a natureza, descrevê-lo e enviar; o órgão responde diretamente ao cidadão. Não há taxa.",
     [("A Lei de Acesso à Informação assegura o direito constitucional de solicitar e obter informações dos órgãos e entidades públicas.", 1),
      ("Na aba Registrar Pedido, clicar em REGISTRAR.", 1)], [], "numeração da FAQ removida"),
    ("faq37", "simples", "Não sei o número da inscrição do meu imóvel. Como descobrir este número?",
     "Pelo site de serviços da SEFAZ (online.maceio.al.gov.br), em Serviços imobiliários > Buscar inscrição imobiliária > Localização de inscrição, buscando por CPF + CEP, endereço, condomínio ou loteamento; a inscrição imobiliária também é chamada de Inscrição do IPTU.",
     [("A Inscrição Imobiliária, também conhecida como Inscrição do IPTU, é o número de identificação do imóvel presente no cadastro imobiliário do município.", 1),
      ("Buscar informando CPF + CEP OU Endereço OU Condomínio OU Loteamento;", 1)], [], "texto inicial truncado da extração da FAQ removido"),
    # ---------------- ponte ----------------
    ("sonnet16", "ponte", "Quem cuida da poda de árvore dentro do meu quintal, e quanto custa esse serviço?",
     "A autorização é da ALURB; a taxa de vistoria da poda é de R$ 70,00, independentemente da quantidade de árvores.",
     [("A poda e supressão de árvore em área particular são de responsabilidade do proprietário do imóvel. No entanto, para realizá-las, é indispensável a autorização prévia da ALURB.", 1),
      ("Taxa: Poda (independente de quantidade): R$70,00", 2)],
     ["Pedido de autorização para poda e supressão de árvore em área particular"], ""),
    ("sonnet20", "ponte", "Quem aprova o orçamento da prefeitura, e quem fiscaliza as contas depois de aprovado?",
     "O orçamento municipal é aprovado pela Câmara Municipal, por pelo menos dois terços dos votos; a fiscalização contábil, financeira e orçamentária também cabe à Câmara, por controle externo com auxílio do Tribunal de Contas do Estado, além do controle interno de cada poder.",
     [("e) o Orçamento Municipal;", 1),
      ("Art. 39 A fiscalização contábil, financeira, orçamentária, patrimonial e operacional do Município", 2),
      ("Art. 41 O controle externo será exercido com o auxilio do Tribunal de Contas do Estado", 2)],
     ["Câmara Municipal"], ""),
    ("sonnet21", "ponte", "Quem recolhe os resíduos sólidos na minha rua, e quais outros serviços de limpeza esse mesmo setor oferece pro meu bairro?",
     "O serviço de resíduos sólidos é da ALURB, que também oferece agendamento de coleta de volumosos, limpeza/capinação/varrição e poda de árvores.",
     [("A Declaração de viabilidade de Recolhimento de Resíduos Sólidos é um documento emitido pela Autarquia Municipal de Desenvolvimento Sustentável e Limpeza Urbana - ALURB", 1),
      ("A Coleta de Volumosos é ofertada pela Prefeitura de Maceió, através da ALURB, com o objetivo de evitar que a população faça o descarte irregular de materiais inservíveis.", 2)],
     ["ALURB"], ""),
    ("sonnet22", "ponte", "Quem define os limites dos distritos da cidade, e como isso se relaciona com as regiões administrativas de Maceió?",
     "A divisão do território em distritos é feita por lei local, observados critérios de lei estadual; cada distrito pode constituir uma Região Administrativa (arts. 90 e 98).",
     [("Art. 90 O território Municipal pode ser divido em distritos e este em subdistritos, conforme dispuser a lei local, observados os critérios estabelecidos em lei estadual especifica.", 1),
      ("Art. 98 Cada distrito poderá constituir Região Administrativa.", 2)],
     ["distrito"], ""),
    ("sonnet24", "ponte", "Quem cuida do licenciamento de um evento de rua, e que outra licença eu preciso pedir separado pra colocar mesa e cadeira na calçada?",
     "O licenciamento de eventos é da SEMSC; para usar a calçada com mesas e cadeiras (bares e restaurantes) é preciso a Licença de Mesas e Cadeiras, também da SEMSC.",
     [("Por meio deste serviço, o interessado solicita o licenciamento de eventos (festa, espetáculo, solenidade, procissões, etc.) organizados com objetivos institucionais, comunitários ou promocionais.", 1),
      ("Por meio deste serviço, o interessado solicita o licenciamento da utilização de área de passeio público com mesas e cadeiras por bares e restaurantes.", 2)],
     ["SEMSC"], ""),
    ("sonnet25", "ponte", "Quem recebe o pedido do seguro-desemprego, e onde eu atualizo minha carteira de trabalho no mesmo atendimento?",
     "O seguro-desemprego é atendido pela SEMTES, que também orienta sobre a Carteira de Trabalho Digital, disponível no aplicativo para celular (iOS e Android) e na web.",
     [("O Seguro-Desemprego é um benefício integrante da seguridade social", 1),
      ("A CARTEIRA DE TRABALHO DIGITAL está disponível para os cidadãos através de Aplicativo para celular nas versões iOS e Android e Web.", 2)],
     ["SEMTES"], ""),
    ("sonnet30", "ponte", "Quem autoriza a reforma de uma casa, e depois de pronta quem faz a vistoria final pra liberar o uso dela?",
     "A reforma ou ampliação é autorizada pela SEMURB (Alvará de reforma e/ou ampliação); concluída a obra, é obrigatório pedir a vistoria ao órgão municipal competente para obter a Carta Habite-se, que autoriza o uso da edificação.",
     [("Por meio deste serviço, o interessado solicita a análise do projeto quando há necessidade de reformar ou ampliar", 1),
      ("Após a conclusão da obra é obrigatória a solicitação de vistoria junto ao órgão municipal competente para obtenção da carta de habite-se.", 2)],
     ["Carta Habite-se"], ""),
    ("sonnet32", "ponte", "Quem cuida da emissão de nota fiscal de serviço, e que cadastro prévio a prefeitura exige antes disso?",
     "A emissão de nota fiscal de serviço é da SEFAZ; antes é preciso o Cadastro de Vínculo do Contribuinte, que vincula a matrícula mercantil ou o CPF ao sistema de notas (o MEI emite no portal nacional gov.br/nfse).",
     [("Por meio deste serviço auxiliamos o contribuinte na emissão da nota fiscal de serviço.", 1),
      ("Por meio deste serviço cadastramos o acesso do contribuinte ao sistema de emissão de notas fiscais de serviço", 2)],
     ["Cadastro de Vínculo do Contribuinte para Emissão de Nota"], ""),
    ("sonnet34", "ponte", "O que a lei orgânica fala sobre desenvolvimento urbano, e como isso se relaciona com as regras que a prefeitura usa pra aprovar um projeto de construção?",
     "A Lei Orgânica manda a lei disciplinar obras e edificações com normas de segurança, higiene, salubridade e estética; o Alvará de aprovação de projeto da SEMURB verifica justamente a consonância do projeto com a legislação urbanística e edilícia do município.",
     [("Art. 107 A lei disciplinará a execução de obras e edificações no território do Município", 1),
      ("Por meio deste serviço, o interessado solicita a concordância com os termos técnicos do projeto e sua consonância com a legislação urbanística e edilícia do município.", 2)],
     ["legislação urbanística e edilícia"], ""),
    ("sonnet35", "ponte", "Pra marcar uma consulta ou exame pelo SMS, onde eu pego os remédios que já uso no tratamento?",
     "A marcação é feita pela Central de Atendimento da Secretaria Municipal de Saúde no WhatsApp (82) 3312.5492; quais medicamentos e insumos a Prefeitura oferece e onde solicitá-los é informado no site da Coordenação de Farmácia da SMS.",
     [("Solicitar o agendamento da consulta ou exame por meio da Central de Atendimento da Secretaria Municipal de Saúde", 1),
      ("o cidadão pode solicitar informações sobre quais medicamentos e insumos estão sendo oferecidos pela Prefeitura e onde solicitálos.", 2)],
     ["Secretaria Municipal de Saúde"], ""),
    ("sonnet79", "ponte", "quem decide se deixa eu juntar dois terrenos vizinhos num terreno só?",
     "O pedido é o de Remembramento e Desmembramento (parcelamento do solo para separar ou juntar áreas), feito à SEMURB.",
     [("Por meio deste serviço, o interessado solicita autorização para realizar o parcelamento do solo (para separar ou juntar áreas).", 1),
      ("SEMURB - Secretaria Municipal de meio Ambiente e Urbanismo", 2)],
     ["Remembramento e Desmembramento"], ""),
    ("sonnet81", "ponte", "quando o prefeito e o vice-prefeito não podem assumir ao mesmo tempo, até quando fica no comando quem entra no lugar deles?",
     "Assume o Presidente da Câmara Municipal, até a nova eleição, feita 90 dias após a abertura da última vaga; se as vagas ocorrerem nos dois últimos anos do mandato, a Câmara elege os sucessores 30 dias após a última vaga.",
     [("Art. 49 Nas faltas, impedimentos ou vacância do Prefeito e o Vice-Prefeito, substituí- Ios-á o Presidente da Câmara Municipal de Maceió.", 1),
      ("Art. 50 Vagando os cargos de Prefeito e de Vice-Prefeito, far-se-á eleição noventa (90) dias após a abertura da última vaga.", 2)],
     ["Presidente da Câmara Municipal"], ""),
    # ---------------- comparacao ----------------
    ("sonnet41", "comparacao", "Qual pede mais requisitos pra entrar, o cadastro do Qualifica Maceió ou os cursos do Emprega Mulher?",
     "O Qualifica Maceió (SEMTES) pede documentos (RG, CPF, comprovante de residência e declaração de escolaridade); o Emprega Mulher (SEMUC) pede condições: ter no mínimo 18 anos, estar no CadÚnico, morar em Maceió e ser mulher. O Emprega Mulher tem mais condições de elegibilidade.",
     [("Declaração de escolaridade original, com no máximo 30 dias de emitida, ou cópia histórico escolar.", 1),
      ("O Programa Emprega Mulher promove a autonomia financeira para mulheres em situação de vulnerabilidade social", 2)],
     ["Qualifica Maceió", "Emprega Mulher"], ""),
    ("sonnet43", "comparacao", "O que muda no processo da câmara entre aprovar uma lei comum e aprovar uma emenda à lei orgânica?",
     "A lei comum é votada uma vez, em regra por maioria simples, e vai à sanção do Prefeito; a emenda à Lei Orgânica exige dois turnos com intervalo mínimo de dez dias, dois terços dos membros da Câmara em cada um, e é promulgada pela Mesa da Câmara.",
     [("Art. 25 As deliberações da Câmara Municipal, ressalvados os casos para os quais diversamente disponha esta lei, serão votadas pela maioria simples dos Vereadores presentes", 1),
      ("§ 1º A proposta será discutida e votada em dois turnos, realizados com intervalo mínimo de dez dias, sendo aprovada caso obtiver, em cada uma das votações, a aprovação de pelo menos dois terços (2/3) dos membros da Câmara Municipal.", 2),
      ("§ 2º A Emenda à Lei Orgânica será promulgada pela Mesa da Câmara Municipal.", 2)],
     ["lei ordinária", "Emenda à Lei Orgânica"], ""),
    ("sonnet48", "comparacao", "Qual cartão dá mais desconto, o VAMU Cidadão ou o VAMU Sênior?",
     "O VAMU Sênior, destinado a idosos a partir de 65 anos, garante gratuidade no transporte público urbano; o VAMU Cidadão é o cartão do usuário comum, sem gratuidade.",
     [("O Cartão Vamu Sênior é o cartão destinado aos idosos, com idade a partir de 65 (sessenta e cinco) anos e garante a gratuidade no transporte público urbano no município de Maceió", 2),
      ("O Cartão Vamu Cidadão é o cartão voltado para o usuário comum", 1)],
     ["Cartão VAMU Cidadão", "Cartão VAMU Sênior"], ""),
    ("sonnet46", "comparacao", "Qual exige mais passos, pedir autorização pra colocar faixa de táxi ou pedir a aferição do taxímetro?",
     "Os dois têm o mesmo roteiro no sistema da DMTT (acessar o sistema, informar os dados, imprimir e entregar a autorização); a diferença é que a autorização de faixa pede o alvará e o RENAVAM, e a aferição do taxímetro pede só o alvará. Nenhum dos dois cobra taxa.",
     [("Para Autorização para colocar faixa - Táxi", 1), ("Informar o alvará e o RENAVAM.", 1),
      ("Para Aferição de Taxímetro", 2)],
     ["autorização para colocar faixa", "aferição de taxímetro"], ""),
    ("sonnet61", "comparacao", "entre o cartão de estacionamento pra idoso e o cartão pra pessoa com deficiência, o que pedem de documento diferente pra cada um?",
     "Os dois pedem RG, CPF e comprovante de residência de no máximo 3 meses; a credencial de pessoa com deficiência pede também atestado médico emitido há no máximo 2 meses que ateste a dificuldade de locomoção.",
     [("A credencial é o documento obrigatório para uso das vagas de estacionamento destinadas a pessoas idosas.", 1),
      ("Atestado médico emitido no máximo há 2 meses, que ateste a dificuldade de locomoção.", 2)],
     ["credencial de estacionamento para idoso", "credencial de estacionamento para pessoa com deficiência"], ""),
    ("sonnet66", "comparacao", "entre entrar pro cadastro do banco da mulher empreendedora e entrar num curso do qualifica maceió, quem pode se inscrever em cada um?",
     "O Banco da Mulher Empreendedora (SEMUC) é para mulheres com no mínimo 18 anos, inscritas no CadÚnico e residentes em Maceió, empreendedoras ou com vontade de empreender; o Qualifica Maceió (SEMTES) aceita candidatos com menos de 18 anos, desde que o representante legal apresente também os documentos.",
     [("Ser Mulher (já sendo empreendedora ou que possua vontade de empreender);", 1),
      ("Em caso do candidato ter menos de 18 anos, o representante legal deverá apresentar também cópias e originais dos documentos (menos a documentação escolar).", 2)],
     ["Banco da Mulher Empreendedora", "Qualifica Maceió"], ""),
    ("sonnet69", "comparacao", "entre a certidão de tempo de contribuição e a certidão negativa do iprev, o que pedem de documento pra emitir cada uma?",
     "A Certidão Negativa do IPREV pede só o CPF; a Certidão de Tempo de Contribuição pede uma lista longa: requerimento, RG ou CNH, CPF, comprovante de residência, PIS/PASEP, ato de nomeação e termo de exercício, ato de exoneração, fichas financeiras e declaração do órgão de origem.",
     [("Ato de nomeação e termo de efetivo exercício ou termo de opção pelo regime estatutário (transmudação).", 1),
      ("A Certidão Negativa é o documento utilizado para comprovar o não recebimento de benefício de Aposentadoria ou Pensão por morte", 2),
      ("Digitar CPF do requerente", 2)],
     ["Certidão de Tempo de Contribuição", "Certidão Negativa"], ""),
    ("sonnet73", "comparacao", "entre criar um distrito novo e criar uma região administrativa nova, quem decide isso dentro da prefeitura?",
     "Nos dois casos é a lei: a divisão em distritos é feita conforme a lei local, observados critérios de lei estadual, e a lei divide o território em regiões administrativas para desconcentrar as atividades do Executivo.",
     [("Art. 90 O território Municipal pode ser divido em distritos e este em subdistritos, conforme dispuser a lei local, observados os critérios estabelecidos em lei estadual especifica.", 1),
      ("Art. 95 A lei dividirá o território Municipal em regiões administrativas, objetivando a desconcentração das atividades do Poder Executivo.", 2)],
     ["distrito", "região administrativa"], ""),
    # ---------------- agregacao ----------------
    ("faq2", "agregacao", "Quais são os tipos de solicitações podem ser apresentadas à Ouvidoria?",
     "Denúncia, reclamação, solicitação de serviço, sugestão e elogio.",
     [("Denúncia serve para comunicação de prática de ato ilícito cuja solução dependa da atuação de órgão de controle interno ou externo.", 1),
      ("Reclamações são registros de insatisfação e de problemas com serviço público realizado pela Prefeitura de Maceió", 2),
      ("Sugestão é a proposição de ideia ou formulação de proposta de aprimoramento de políticas públicas", 3),
      ("Elogio é quando o interessado deseja expressar reconhecimento ou satisfação sobre o serviço oferecido", 4)],
     ["Denúncia", "Reclamação", "Sugestão", "Elogio"], "numeração da FAQ removida"),
    ("sonnet51", "agregacao", "Quantos tipos de certidão dá pra tirar no IPREV?",
     "Dois: a Certidão de Tempo de Contribuição do Regime Próprio e a Certidão Negativa (que comprova o não recebimento de aposentadoria ou pensão pelo IPREV).",
     [("A Certidão de Tempo de Contribuição é o documento que comprova os recolhimentos previdenciários dos servidores públicos efetivos", 1),
      ("A Certidão Negativa é o documento utilizado para comprovar o não recebimento de benefício de Aposentadoria ou Pensão por morte", 2)],
     ["Certidão de Tempo de Contribuição", "Certidão Negativa"], ""),
    ("sonnet52", "agregacao", "Quais secretarias oferecem algum curso profissionalizante pra quem tá procurando emprego?",
     "SEMTES (Qualifica Maceió), SEMUC (Emprega Mulher) e SELJ (Emprega Jovem, com o SENAI, e Jovem Empreendedor, com o SEBRAE).",
     [("O Programa Qualifica Maceió oferece cursos de capacitação e qualificação e faz a intermediação com as empresas para inserção no mercado de trabalho.", 1),
      ("O Programa Emprega Mulher promove a autonomia financeira para mulheres em situação de vulnerabilidade social", 2),
      ("Cadastro para cursos do Emprega Jovem em parceria com o SENAI (cursos profissionalizantes)", 3)],
     ["SEMTES", "SEMUC", "SELJ"], ""),
    ("sonnet54", "agregacao", "Quais serviços da prefeitura atendem especificamente pessoa com alguma deficiência ou transtorno?",
     "A Carteira de Transtorno do Espectro Autista (SEMDES) e a credencial de estacionamento para pessoa com deficiência (DMTT), que também vale para pessoas com TEA e fibromialgia.",
     [("O documento confere a identificação à pessoa diagnosticada com Transtorno do Espectro Autista.", 1),
      ("Destinado a pessoas residentes em Maceió, portadoras de alguma deficiência que dificulte sua locomoção permanentemente", 2)],
     ["Carteira de Transtorno do Espectro Autista", "credencial de estacionamento"], ""),
    ("sonnet55", "agregacao", "Quantos tipos de alvará o SEMURB emite pra quem vai construir ou reformar?",
     "Sete: Alvará de Execução de Obra, de Alteração, de aprovação de projeto, de reforma e/ou ampliação, de renovação de projeto e execução, de Autorização e de Demolição.",
     [("Alvará de renovação de projeto e execução", 1), ("Alvará de Demolição", 1)],
     ["SEMURB"], ""),
    ("sonnet56", "agregacao", "Quais órgãos recebem algum tipo de reclamação ou denúncia do cidadão?",
     "A CGM, pela Ouvidoria (denúncias, reclamações sobre serviço público e outras manifestações), e o PROCON Maceió (reclamações sobre relações de consumo).",
     [("Denúncia serve para comunicação de prática de ato ilícito cuja solução dependa da atuação de órgão de controle interno ou externo.", 1),
      ("Por meio deste serviço, o cidadão pode realizar reclamação relativa a situações envolvendo relações de consumo e seus direitos.", 2)],
     ["CGM", "PROCON"], ""),
    ("sonnet57", "agregacao", "Quantos serviços voltados pra juventude o SELJ oferece?",
     "Cinco: cadastro para o ID Jovem, elaboração de currículo, cursos do Jovem Empreendedor (SEBRAE), cursos do Emprega Jovem (SENAI) e cadastro de expositor na Feira da Juventude.",
     [("Cadastro para participação como expositor na Feira da Juventude", 1),
      ("Cadastro para obtenção do ID JOVEM", 1)],
     ["SELJ"], ""),
    ("sonnet60", "agregacao", "Quais secretarias têm cadastro voltado pra quem quer empreender?",
     "A SEMUC (pré-inscrição no Banco da Mulher Empreendedora e cadastro de expositora na Feira da Mulher Empreendedora) e a SELJ (cursos do Jovem Empreendedor com o SEBRAE e expositor na Feira da Juventude, que incentiva jovens ao empreendedorismo).",
     [("O PROGRAMA SOCIAL PARA MULHERES EMPREENDEDORAS, intitulado “Banco da Mulher”, vem estimular o empreendedorismo feminino", 1),
      ("com o objetivo de incentivar os jovens entre 18 e 29 anos ao empreendedorismo", 2)],
     ["SEMUC", "SELJ"], ""),
]


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).lower()
    return re.sub(r"\s+", " ", s).strip()


def main() -> None:
    texts = {f.name: norm(f.read_text(encoding="utf-8")) for f in BASE.glob("*.md")}
    raw = " ".join(t for n, t in texts.items() if "normalizado" not in n)
    nor = " ".join(t for n, t in texts.items() if "normalizado" in n)
    problems = 0
    for origem, tipo, perg, resp, ev, ponte, _ in Q:
        for e, _hop in ev:
            if norm(e) not in nor:
                problems += 1
                print(f"[{origem}] not verbatim in normalized: {e[:70]}")
    rows = [{"pergunta": p, "resposta_referencia": r, "evidencia_referencia": "|".join(e for e, _ in ev),
             "tipo": t, "evidencia_salto": "|".join(str(h) for _, h in ev), "entidades_ponte": "|".join(b)}
            for _, t, p, r, ev, b, _ in Q]
    with open(OUT, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    with open(HERE / "perguntas_origem.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["pergunta", "origem", "edicao"])
        w.writerows([(p, o, ed) for o, _, p, _, _, _, ed in Q])
    from collections import Counter
    print(f"{len(rows)} questions {dict(Counter(r['tipo'] for r in rows))}; verbatim problems: {problems}")


if __name__ == "__main__":
    main()
