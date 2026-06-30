import { Alert, Collapse, Select, Stack, Table, Text, Title } from "@mantine/core";
import { Fragment, useEffect, useState } from "react";

import { getExperiment, listExperiments } from "../api/client";
import type { ExperimentDetail, ExperimentSummary } from "../api/types";

function summarizeScores(scores: Record<string, number>): string {
  return Object.entries(scores)
    .map(([key, value]) => `${key}: ${value.toFixed(2)}`)
    .join(" · ");
}

function truncateAnswer(answer: string, max = 60): string {
  return answer.length > max ? `${answer.slice(0, max)}…` : answer;
}

export function ResultsPage() {
  const [experiments, setExperiments] = useState<ExperimentSummary[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<ExperimentDetail | null>(null);
  const [openRow, setOpenRow] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listExperiments()
      .then((rows) => {
        setExperiments(rows);
        if (rows.length > 0) setSelected(String(rows[0].id));
      })
      .catch((e) => setError(String(e)));
  }, []);

  useEffect(() => {
    if (selected) getExperiment(Number(selected)).then(setDetail).catch((e) => setError(String(e)));
  }, [selected]);

  return (
    <Stack>
      <Title order={2}>Resultados</Title>
      {error && (
        <Alert color="red" title="Erro">
          {error}
        </Alert>
      )}
      <Select
        label="Experimento"
        data={experiments.map((e) => ({ value: String(e.id), label: `${e.name} (${e.status})` }))}
        value={selected}
        onChange={setSelected}
        maw={360}
      />
      {detail && (
        <Table highlightOnHover withTableBorder>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Combinação</Table.Th>
              <Table.Th>Pergunta</Table.Th>
              <Table.Th>Resposta</Table.Th>
              <Table.Th>Scores</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {detail.results.map((row, index) => (
              <Fragment key={index}>
                <Table.Tr
                  onClick={() => setOpenRow(openRow === index ? null : index)}
                  style={{ cursor: "pointer" }}
                >
                  <Table.Td>{`${row.chunking}/${row.embedding}/${row.rag}/${row.retriever}`}</Table.Td>
                  <Table.Td>{row.question}</Table.Td>
                  {/* Hide answer preview when row is expanded to avoid duplicate matches */}
                  <Table.Td>{openRow === index ? null : truncateAnswer(row.answer)}</Table.Td>
                  <Table.Td>{summarizeScores(row.scores)}</Table.Td>
                </Table.Tr>
                <Table.Tr>
                  <Table.Td colSpan={4} p={0} style={{ border: 0 }}>
                    <Collapse in={openRow === index}>
                      {/* Conditionally render so content is not in DOM when collapsed */}
                      {openRow === index && (
                        <Stack p="md" gap="xs">
                          <Text fw={600}>Resposta completa</Text>
                          <Text>{row.answer}</Text>
                          <Text size="sm" c="dimmed">
                            {summarizeScores(row.scores)} · latência: {row.latency_ms} ms · tokens:{" "}
                            {row.tokens}
                          </Text>
                        </Stack>
                      )}
                    </Collapse>
                  </Table.Td>
                </Table.Tr>
              </Fragment>
            ))}
          </Table.Tbody>
        </Table>
      )}
    </Stack>
  );
}
