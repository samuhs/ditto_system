import { motion } from "framer-motion";
import type { ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";

import { ChartIcon, FlaskIcon, HomeIcon, UploadIcon } from "./icons";

interface NavItem {
  to: string;
  label: string;
  icon: ReactNode;
}

const NAV: NavItem[] = [
  { to: "/", label: "Início", icon: <HomeIcon /> },
  { to: "/ingest", label: "Inserir documentos", icon: <UploadIcon /> },
  { to: "/experiment", label: "Gerar teste", icon: <FlaskIcon /> },
  { to: "/results", label: "Resultados", icon: <ChartIcon /> },
  { to: "/prompts", label: "Prompts", icon: <FlaskIcon /> },
  { to: "/chat-configs", label: "Config. de chat", icon: <FlaskIcon /> },
  { to: "/chat", label: "Conversa", icon: <FlaskIcon /> },
  { to: "/agente", label: "Agente", icon: <FlaskIcon /> },
];

export function Sidebar() {
  const { pathname } = useLocation();

  return (
    <nav className="ditto-sidebar" aria-label="Navegação principal">
      <Link to="/" className="ditto-brand" aria-label="Ditto — início">
        <span className="ditto-brand-mark" aria-hidden />
        <span className="ditto-brand-word">Ditto</span>
      </Link>

      {NAV.map((item) => {
        const active = item.to === "/" ? pathname === "/" : pathname.startsWith(item.to);
        return (
          <Link
            key={item.to}
            to={item.to}
            className="ditto-navlink"
            data-active={active}
            aria-current={active ? "page" : undefined}
          >
            {active && (
              <motion.span
                layoutId="nav-active"
                className="ditto-nav-active"
                transition={{ type: "spring", stiffness: 380, damping: 32 }}
              />
            )}
            {item.icon}
            <span>{item.label}</span>
          </Link>
        );
      })}

      <div className="ditto-sidebar-foot">
        <div>v0.1 · pesquisa de doutorado</div>
        <div>RAG · chunking × embedding × técnica</div>
      </div>
    </nav>
  );
}
