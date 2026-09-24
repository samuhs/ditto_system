import { createContext } from "react";

/**
 * The app is organised like a tabbed reference manual: each division is a
 * task stage with its own board hue. Routes map to a division so the shell
 * can colour the board and extend the current tab.
 */
export type SectionId =
  | "inicio"
  | "preparar"
  | "experimentar"
  | "comparar"
  | "conversar"
  | "ajustar";

export interface SectionPage {
  to: string;
  label: string;
}

export interface Section {
  id: SectionId;
  /** Workflow step number, when the division is part of the main sequence. */
  step?: number;
  label: string;
  /** One-line purpose, shown on the home table of contents. */
  purpose: string;
  pages: SectionPage[];
}

export const SECTIONS: Section[] = [
  {
    id: "inicio",
    label: "Início",
    purpose: "Visão geral e próximo passo.",
    pages: [{ to: "/", label: "Início" }],
  },
  {
    id: "preparar",
    step: 1,
    label: "Preparar",
    purpose: "Envie documentos e gere os índices de busca.",
    pages: [{ to: "/ingest", label: "Documentos" }],
  },
  {
    id: "experimentar",
    step: 2,
    label: "Experimentar",
    purpose: "Combine técnicas e rode as perguntas.",
    pages: [{ to: "/experiment", label: "Novo experimento" }],
  },
  {
    id: "comparar",
    step: 3,
    label: "Comparar",
    purpose: "Veja qual combinação respondeu melhor.",
    pages: [{ to: "/results", label: "Resultados" }],
  },
  {
    id: "conversar",
    step: 4,
    label: "Conversar",
    purpose: "Converse com seus documentos e avalie os diálogos.",
    pages: [
      { to: "/chat", label: "Conversa" },
      { to: "/chat-configs", label: "Configurações de chat" },
      { to: "/dialogues", label: "Diálogos salvos" },
    ],
  },
  {
    id: "ajustar",
    label: "Ajustar",
    purpose: "Prompts, agente, personas e chaves do sistema.",
    pages: [
      { to: "/prompts", label: "Prompts" },
      { to: "/agente", label: "Agente e personas" },
      { to: "/configuracoes", label: "Sistema" },
    ],
  },
];

function matches(pathname: string, to: string): boolean {
  if (to === "/") return pathname === "/";
  return pathname === to || pathname.startsWith(`${to}/`);
}

export function sectionForPath(pathname: string): Section {
  return SECTIONS.find((s) => s.pages.some((p) => matches(pathname, p.to))) ?? SECTIONS[0];
}

export function isPageActive(pathname: string, to: string): boolean {
  return matches(pathname, to);
}

/** The division the current page belongs to; provided by the app shell. */
export const SectionContext = createContext<Section | null>(null);
