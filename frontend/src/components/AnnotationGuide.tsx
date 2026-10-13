import { Button, Modal } from "@mantine/core";

/**
 * "Como avaliar": the instructions an Avaliador reads before (and while) scoring, kept next to the
 * Rubrica v1 the backend serves. Plain text on purpose: Avaliadores need not know RAG.
 */
export function AnnotationGuide({ opened, onClose }: { opened: boolean; onClose: () => void }) {
  return (
    <Modal opened={opened} onClose={onClose} title="Como avaliar" size="lg" returnFocus={false}>
      <div className="ditto-guide">
        <p>
          Você vai ler respostas geradas por um sistema automático para perguntas sobre cidades e dar duas notas a cada
          uma. Você não sabe qual técnica ou modelo gerou cada resposta, e isso é proposital: avalie só o que está
          escrito.
        </p>

        <h3>Passo a passo</h3>
        <ol>
          <li>Escolha o seu nome (ou cadastre-se como avaliador novo) e use sempre o mesmo nome.</li>
          <li>Escolha a rodada. Se houver uma rodada piloto, faça-a primeiro.</li>
          <li>
            Para cada resposta, leia nesta ordem: a <strong>pergunta</strong>, a <strong>resposta de referência</strong>
            {" "}e a <strong>evidência</strong> (o trecho da base que justifica a referência). Só então leia a
            {" "}<strong>resposta a avaliar</strong>.
          </li>
          <li>Dê a nota de Correção e, se couber, a de Fundamentação. Clique em <em>Salvar e seguir</em>.</li>
          <li>
            Você pode parar a qualquer momento (botão <em>Sair</em>) e continuar depois: as notas já salvas ficam
            guardadas e a tela volta para a primeira resposta sem nota. Salve antes de sair: uma escolha ainda não salva
            (a tela avisa “escolha não salva”) se perde. Enquanto a rodada estiver aberta, dá para voltar e corrigir.
          </li>
        </ol>

        <h3>Correção: a resposta está certa?</h3>
        <p>Compare com a resposta de referência. Conta o conteúdo, não o estilo nem o tamanho.</p>
        <ul>
          <li><strong>0 · Errada</strong>: dá um fato errado, contradiz a referência ou não responde (inclusive “não sei” ou “o contexto não informa”).</li>
          <li><strong>1 · Parcial</strong>: acerta parte dos fatos pedidos (por exemplo, o horário certo mas o local errado, ou 2 de 4 itens de uma lista).</li>
          <li><strong>2 · Correta</strong>: traz todos os fatos que a pergunta pede, sem erro. Informação extra correta não tira ponto.</li>
        </ul>

        <h3>Fundamentação: o que a resposta afirma está nos trechos?</h3>
        <p>
          Abra <em>Trechos que o sistema recuperou</em> e compare com os trechos recuperados, não com a referência. Uma
          resposta pode estar certa e mal fundamentada (o modelo “sabia” sem apoio no texto), ou errada e bem
          fundamentada (o texto recuperado era o errado).
        </p>
        <ul>
          <li><strong>0 · Inventa</strong>: afirma algo que não está nos trechos ou que os contradiz.</li>
          <li><strong>1 · Parcial</strong>: parte do que afirma está nos trechos, parte não.</li>
          <li><strong>2 · Apoiada</strong>: toda afirmação relevante aparece nos trechos.</li>
        </ul>
        <p>
          Quando o sistema não recuperou nenhum trecho, a Fundamentação aparece como <strong>não se aplica</strong> e
          você só dá a nota de Correção.
        </p>

        <h3>Não consigo avaliar</h3>
        <p>
          Marque <strong>Não consigo avaliar</strong> e escreva o motivo quando não der para julgar com segurança: a
          referência é ambígua, a pergunta não faz sentido, a resposta está ilegível. Na dúvida entre duas notas, não
          use esta opção: escolha a nota que melhor descreve a resposta e, se quiser, explique no comentário.
        </p>

        <h3>Comentário</h3>
        <p>Opcional. Use para registrar dúvidas ou o motivo de uma nota difícil; ajuda na discussão das discordâncias.</p>

        <h3>Atalhos</h3>
        <p>
          <strong>0</strong>, <strong>1</strong> e <strong>2</strong> dão a nota (primeiro Correção, depois
          Fundamentação), <strong>Enter</strong> salva e segue, <strong>←</strong> e <strong>→</strong> navegam entre
          as respostas.
        </p>

        <h3>Dicas</h3>
        <ul>
          <li>Não tente adivinhar qual sistema gerou a resposta; avalie cada uma por si.</li>
          <li>Não compare com as notas que você deu antes: cada resposta vale sozinha.</li>
          <li>Faça pausas. Notas dadas com cansaço discordam mais.</li>
        </ul>
        <Button onClick={onClose} mt="md">Entendi</Button>
      </div>
    </Modal>
  );
}
