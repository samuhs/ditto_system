import { Button } from "@mantine/core";
import { useEffect, useState } from "react";

import { getEvaluationSettings, saveEvalEmbedding } from "../api/client";
import type { EvaluationSettings } from "../api/types";
import { ChoiceGroup, type Choice } from "../components/ChoiceGroup";
import { Errata, Saved, errorText } from "../components/Notice";
import { PageHeader } from "../components/PageHeader";
import { term } from "../glossary";

function embeddingChoice({ name, local }: { name: string; local: boolean }): Choice {
  const t = term("embedding", name);
  const cost = local
    ? "Não gasta cota: roda na sua máquina."
    : "Cada resposta avaliada gasta cota da API.";
  return {
    value: name,
    name: t.name,
    code: name,
    tag: local ? "Local" : "API",
    description: t.description ? `${t.description} ${cost}` : cost,
  };
}

export function AvaliacaoPage() {
  const [settings, setSettings] = useState<EvaluationSettings | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    getEvaluationSettings()
      .then((s) => {
        setSettings(s);
        setSelected([s.eval_embedding]);
      })
      .catch((e) => setLoadError(errorText(e)));
  }, []);

  const current = settings?.eval_embedding;
  const choice = selected[0];
  const changed = choice !== undefined && choice !== current;

  async function save() {
    if (!choice) return;
    setSaveError(null);
    setSaved(false);
    try {
      const r = await saveEvalEmbedding(choice);
      setSettings((s) => (s ? { ...s, eval_embedding: r.eval_embedding } : s));
      setSaved(true);
    } catch (e) {
      setSaveError(errorText(e));
    }
  }

  const embeddingMetrics = settings?.metrics.filter((m) => m.uses_embedding).length ?? 0;

  return (
    <div>
      <PageHeader
        title="Avaliação"
        lede="Como o Ditto dá nota às respostas dos experimentos. Nenhuma métrica usa um modelo de linguagem como juiz: elas comparam textos."
      />

      {loadError && (
        <div style={{ marginBottom: 20 }}>
          <Errata title="Não foi possível ler a configuração de avaliação">
            {loadError}. Confira se a API está no ar e recarregue a página.
          </Errata>
        </div>
      )}

      {settings && (
        <div className="ditto-form">
          <section className="ditto-sec">
            <div className="ditto-sec-head">
              <h2 className="ditto-h2">Modelo que dá as notas</h2>
              <p className="ditto-read">
                {embeddingMetrics} das {settings.metrics.length} métricas comparam textos pelo sentido, com este
                modelo de embedding. Vale para os próximos experimentos; os já rodados guardam o modelo que
                usaram.
              </p>
            </div>
            <div className="ditto-sec-body">
              <ChoiceGroup
                legend="Embedding da avaliação"
                single
                choices={settings.embeddings.map(embeddingChoice)}
                value={selected}
                onChange={(v) => {
                  setSelected(v);
                  setSaved(false);
                }}
              />
              {saveError && (
                <Errata title="A escolha não foi salva">{saveError}. Escolha outro modelo ou tente de novo.</Errata>
              )}
              <div className="ditto-row-actions">
                <Button onClick={save} disabled={!changed}>
                  Salvar escolha
                </Button>
                {saved && <Saved>Os próximos experimentos usam {term("embedding", current ?? "").name}</Saved>}
              </div>
            </div>
          </section>

          <section className="ditto-sec">
            <div className="ditto-sec-head">
              <h2 className="ditto-h2">O que cada métrica usa</h2>
              <p className="ditto-read">
                Só as métricas marcadas com o modelo mudam de nota quando você troca a escolha acima. Todas vão
                de 0 a 1; maior é melhor.
              </p>
            </div>
            <div className="ditto-sec-body">
              <div className="ditto-table-wrap">
                <table className="ditto-table" data-stack="true">
                  <thead>
                    <tr>
                      <th>Métrica</th>
                      <th>O que mede</th>
                      <th>Compara com</th>
                      <th>Precisa da resposta de referência</th>
                    </tr>
                  </thead>
                  <tbody>
                    {settings.metrics.map((m) => {
                      const t = term("metric", m.name);
                      return (
                        <tr key={m.name}>
                          <td className="ditto-cell-title">
                            <b>{t.name}</b> <span className="ditto-mono ditto-muted">{m.name}</span>
                          </td>
                          <td className="ditto-cell-text" data-label="O que mede">
                            {t.description ?? "—"}
                          </td>
                          <td data-label="Compara com">{m.uses_embedding ? "O modelo escolhido" : "Só o texto"}</td>
                          <td data-label="Referência">{m.requires_reference ? "Sim" : "Não"}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
