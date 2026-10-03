/** How a GraphRAG run's Grafo de conhecimento reads in the results. */
import type { GraphStats } from "../api/types";

/** "12 entidades · 8 relações · 30 trechos · 10% das linhas com falha". */
export function graphStatsText(stats: GraphStats): string {
  const failedPct = stats.lines > 0 ? Math.round((stats.failed_lines / stats.lines) * 100) : 0;
  const parts = [
    `${stats.entities} entidades`,
    `${stats.relations} relações`,
    `${stats.chunks} trechos`,
    `${failedPct}% das linhas com falha`,
  ];
  if (stats.failed_chunks > 0) parts.push(`${stats.failed_chunks} trechos sem extração`);
  return parts.join(" · ");
}
