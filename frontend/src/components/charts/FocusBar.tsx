import { MultiSelect, SegmentedControl, Select } from "@mantine/core";

import { MEDIA_KEY, type RankRow, comboText } from "../../experiments/ranking";
import { type FocusMode, type FocusState, metricLabel } from "./aggregate";

const N_OPTIONS = Array.from({ length: 10 }, (_, i) => String(i + 1));

export function FocusBar({
  focus, onChange, ranked, metricKeys,
}: {
  focus: FocusState;
  onChange: (f: FocusState) => void;
  ranked: RankRow[];
  metricKeys: string[];
}) {
  const set = (patch: Partial<FocusState>) => onChange({ ...focus, ...patch });
  return (
    <div className="ditto-filters ditto-chart-focus" role="group" aria-label="Combinações em foco">
      <div className="ditto-chart-focus-mode">
        <span className="ditto-chart-focus-label">Mostrar</span>
        <SegmentedControl
          size="sm"
          value={focus.mode}
          onChange={(v) => set({ mode: v as FocusMode })}
          data={[
            { value: "top_bottom", label: "Top e bottom" },
            { value: "top", label: "Só top" },
            { value: "all", label: "Todas" },
          ]}
        />
      </div>
      <Select
        label="N"
        size="sm"
        w={80}
        data={N_OPTIONS}
        value={String(focus.n)}
        onChange={(v) => set({ n: Number(v ?? 3) })}
        allowDeselect={false}
        disabled={focus.mode === "all"}
      />
      <Select
        label="Métrica dos gráficos"
        size="sm"
        data={[{ value: MEDIA_KEY, label: "Média" }, ...metricKeys.map((k) => ({ value: k, label: metricLabel(k) }))]}
        value={focus.metric}
        onChange={(v) => set({ metric: v ?? MEDIA_KEY })}
        allowDeselect={false}
      />
      <MultiSelect
        label="Adicionar combinações"
        placeholder="Escolha no ranking"
        size="sm"
        searchable
        clearable
        data={ranked.map((r, i) => ({ value: r.key, label: `#${i + 1} ${comboText(r.combo)}` }))}
        value={focus.manual}
        onChange={(v) => set({ manual: v })}
      />
    </div>
  );
}
