import type { ComboboxItem } from "@mantine/core";

import type { Options } from "../api/types";
import type { Choice } from "./ChoiceGroup";

const LOCATION_LABEL: Record<string, string> = { local: "local", remote: "remoto" };

/** LLM choices: real model names with a local/remote tag. */
export function llmChoices(options: Options | null): Choice[] {
  if (!options) return [];
  if (options.llm_options) {
    return options.llm_options.map(({ value, label, location }) => ({
      value,
      name: label,
      tag: LOCATION_LABEL[location] ?? location,
      description:
        location === "local"
          ? "Roda no servidor local (MLX ou Ollama), sem custo de API."
          : "Chamado via API externa.",
    }));
  }
  return options.llms.map((value) => ({ value, name: value }));
}

/** Select data for a single-model field, with the location in the label. */
export function llmSelectData(options: Options | null): ComboboxItem[] {
  return llmChoices(options).map((c) => ({
    value: c.value,
    label: c.tag ? `${c.name} (${c.tag})` : c.name,
  }));
}
