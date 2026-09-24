import { type ReactNode, useContext } from "react";
import { Link } from "react-router-dom";

import { SectionContext } from "../sections";

import { ArrowIcon } from "./icons";

interface PageHeaderProps {
  title: string;
  lede?: ReactNode;
  /** Link back to the parent list, e.g. { to: "/results", label: "Voltar aos experimentos" }. */
  back?: { to: string; label: string };
}

export function PageHeader({ title, lede, back }: PageHeaderProps) {
  const section = useContext(SectionContext);
  return (
    <header className="ditto-page-head">
      {back && (
        <Link to={back.to} className="ditto-back">
          <ArrowIcon />
          {back.label}
        </Link>
      )}
      <h1 className="ditto-page-title">
        {section?.step && (
          <span className="ditto-page-num" title={`Etapa ${section.step}: ${section.label}`}>
            <span className="visually-hidden">Etapa {section.step}, {section.label}: </span>
            <span aria-hidden>{section.step}</span>
          </span>
        )}
        <span>{title}</span>
      </h1>
      {lede && <p className="ditto-page-lede">{lede}</p>}
    </header>
  );
}
