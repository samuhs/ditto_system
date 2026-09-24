import { Group, Text } from "@mantine/core";
import type { ComboboxLikeRenderOptionInput, ComboboxItem } from "@mantine/core";

import type { Options } from "../api/types";

const LOCATION_LABEL: Record<string, string> = { local: "local", remote: "remoto" };

/** Select/MultiSelect data for the LLM field: real model names, falling back to plain names. */
export function llmSelectData(options: Options | null): ComboboxItem[] {
  if (!options) return [];
  if (options.llm_options) {
    return options.llm_options.map(({ value, label }) => ({ value, label }));
  }
  return options.llms.map((value) => ({ value, label: value }));
}

/** Dropdown row: model name plus a subtle local/remote tag. */
export function llmOptionRenderer(options: Options | null) {
  const locations = new Map((options?.llm_options ?? []).map((o) => [o.value, o.location]));
  return function renderLlmOption({ option }: ComboboxLikeRenderOptionInput<ComboboxItem>) {
    const location = locations.get(option.value);
    return (
      <Group justify="space-between" wrap="nowrap" gap="xs" w="100%">
        <Text size="sm">{option.label}</Text>
        {location && (
          <Text size="xs" c="dimmed">
            {LOCATION_LABEL[location] ?? location}
          </Text>
        )}
      </Group>
    );
  };
}
