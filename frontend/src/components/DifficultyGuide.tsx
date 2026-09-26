import { Button, Modal } from "@mantine/core";
import { useState } from "react";

import { InfoIcon } from "./icons";

/** "Como ler esta tabela": a plain-language guide to the difficulty table, in a modal. */
export function DifficultyGuide() {
  const [opened, setOpened] = useState(false);
  return (
    <>
      <Button variant="default" size="sm" leftSection={<InfoIcon />} onClick={() => setOpened(true)}>
        Como ler esta tabela
      </Button>
      <Modal opened={opened} onClose={() => setOpened(false)} title="Como ler a dificuldade por pergunta" size="xl">
        <div className="ditto-guide">
          <h3 className="ditto-h3">Por que depende de uma métrica</h3>
          <p>
            Pense numa prova: uma questão é difícil quando muitos alunos erram, e para saber quem
            errou é preciso um critério de correção. Aqui, as <b>questões</b> são as suas perguntas,
            os <b>alunos</b> são as combinações (corte × embedding × técnica × busca × modelo) e o{" "}
            <b>critério</b> é a métrica escolhida no topo. Uma pergunta é difícil quando as respostas
            dela tiram nota baixa <b>naquela métrica</b>. Por isso a tabela muda quando você troca a
            métrica.
          </p>

          <h3 className="ditto-h3">Qual métrica escolher</h3>
          <div className="ditto-table-wrap">
            <table className="ditto-table" data-stack="true">
              <thead>
                <tr>
                  <th>Grupo</th>
                  <th>Métricas</th>
                  <th>A dificuldade quer dizer</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td className="ditto-cell-title">A resposta está certa?</td>
                  <td className="ditto-cell-text" data-label="Métricas"><b>chrF</b>, F1 de palavras, ROUGE-L, Correção</td>
                  <td className="ditto-cell-text" data-label="A dificuldade quer dizer">O sistema erra a resposta desta pergunta. <b>É a leitura principal.</b></td>
                </tr>
                <tr>
                  <td className="ditto-cell-title">A resposta é adequada?</td>
                  <td className="ditto-cell-text" data-label="Métricas">Relevância, Fidelidade</td>
                  <td className="ditto-cell-text" data-label="A dificuldade quer dizer">A resposta foge do assunto ou inventa o que não está nos trechos.</td>
                </tr>
                <tr>
                  <td className="ditto-cell-title">A busca achou o trecho?</td>
                  <td className="ditto-cell-text" data-label="Métricas">Acerto da busca, MRR, Evidência recuperada, Precisão e Cobertura do contexto</td>
                  <td className="ditto-cell-text" data-label="A dificuldade quer dizer">A busca não acha o trecho desta pergunta. Não diz nada sobre o modelo.</td>
                </tr>
              </tbody>
            </table>
          </div>
          <p>
            Use o <b>chrF</b> (o padrão): compara a resposta com a de referência e aceita variações
            como “restaurante” e “restaurantes”. Com as métricas de busca, as colunas “Sem busca” e
            “Oráculo” ficam vazias ou sem sentido, porque essas condições não buscam nada.
          </p>

          <h3 className="ditto-h3">O que cada coluna responde</h3>
          <dl className="ditto-kv">
            <dt>TRI</dt>
            <dd>Esta pergunta é mais difícil que as outras? Acima de 0, mais difícil que a média.</dd>
            <dt>Com busca</dt>
            <dd>Quão bem o seu sistema responde: a média de todas as configurações.</dd>
            <dt>± ao lado</dt>
            <dd>A configuração faz diferença? Alto: depende muito dela. Baixo: todas vão parecido.</dd>
            <dt>Sem busca</dt>
            <dd>Quanto o modelo sabe sozinho, sem os documentos. É o piso.</dd>
            <dt>Oráculo</dt>
            <dd>Quanto o modelo acerta com o trecho correto no contexto. É o teto.</dd>
            <dt>Evidência</dt>
            <dd>Em quantas buscas o trecho correto veio.</dd>
          </dl>

          <h3 className="ditto-h3">A regra simples: piso → seu sistema → teto</h3>
          <ul>
            <li>
              <b>Com busca perto do Oráculo:</b> está bom, a pergunta é fácil.
            </li>
            <li>
              <b>Com busca longe do Oráculo e Evidência baixa:</b> a busca falha. Mexer no corte, no
              embedding ou na busca ajuda.
            </li>
            <li>
              <b>Oráculo baixo:</b> a pergunta é difícil para o modelo. Nem com o trecho certo ele
              acerta, e nenhuma configuração de busca resolve.
            </li>
            <li>
              <b>Com busca abaixo de Sem busca:</b> a busca atrapalha; os trechos errados confundem o
              modelo.
            </li>
          </ul>
          <p>
            <b>Difícil só para o modelo pequeno?</b> Compare o Oráculo entre os modelos. Se o maior
            acerta com o trecho certo e o pequeno não, a dificuldade é do modelo pequeno.
          </p>

          <h3 className="ditto-h3">Exemplo</h3>
          <p>
            “Horário da Ilha do Ar?” com TRI +0,8; no modelo pequeno, Com busca 0,30 ± 0,05, Sem
            busca 0,10, Oráculo 0,32 e Evidência 90%. A pergunta é mais difícil que a média. A busca
            acha o trecho quase sempre, mas mesmo com ele o modelo tira 0,32:{" "}
            <b>o problema é o modelo, não a busca</b>. O ± baixo confirma que trocar de configuração
            não muda nada.
          </p>

          <h3 className="ditto-h3">Sinais que não dependem da resposta</h3>
          <p>
            A Tabela 3, abaixo da principal, mostra quais sinais medidos <b>sem olhar as respostas</b>{" "}
            andam junto com a dificuldade: características da pergunta (tamanho, negação, horário,
            termos raros), da evidência, da busca e a <b>perplexidade</b> (o quanto o texto da
            pergunta surpreende cada modelo; só modelos MLX). Um valor perto de +1 quer dizer que o
            sinal prevê bem a dificuldade. Validados no experimento grande, esses sinais permitem
            prever se uma pergunta nova será difícil para o modelo pequeno antes de rodá-la.
          </p>

          <h3 className="ditto-h3">Dois cuidados</h3>
          <ul>
            <li>
              Nenhuma métrica chega a 1 numa resposta correta escrita com outras palavras (no chrF,
              uns 0,6–0,8). Olhe as <b>diferenças entre colunas</b>, não o valor sozinho.
            </li>
            <li>
              Com poucas perguntas, a tabela serve para ver se tudo funciona, não para concluir. É o
              que diz o aviso “TRI só indicativa”.
            </li>
          </ul>
        </div>
      </Modal>
    </>
  );
}
