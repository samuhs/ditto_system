import { Link, useLocation } from "react-router-dom";

import { SECTIONS, isPageActive, sectionForPath } from "../sections";
import { DittoMark } from "./icons";

/** The manual's tab rail: one divider per task stage; the current one extends into the board. */
export function Sidebar() {
  const { pathname } = useLocation();
  const current = sectionForPath(pathname);

  return (
    <nav className="ditto-rail" aria-label="Navegação principal">
      <Link to="/" className="ditto-brand">
        <DittoMark />
        <span>
          <span className="ditto-brand-word">Ditto</span>
          <span className="ditto-brand-sub">Experimentos de RAG</span>
        </span>
      </Link>

      <ul className="ditto-tabs">
        {SECTIONS.map((section) => {
          const active = section.id === current.id;
          const showPages = active && section.pages.length > 1;
          return (
            <li
              key={section.id}
              className="ditto-tab"
              data-section={section.id}
              data-active={active}
            >
              <Link
                to={section.pages[0].to}
                className="ditto-tab-link"
                aria-current={active && !showPages ? "page" : undefined}
              >
                <span className="ditto-tab-num" aria-hidden>
                  {section.step ?? ""}
                </span>
                <span>{section.label}</span>
              </Link>
              {showPages && (
                <ul className="ditto-tab-pages">
                  {section.pages.map((page) => (
                    <li key={page.to}>
                      <Link
                        to={page.to}
                        className="ditto-tab-page"
                        aria-current={isPageActive(pathname, page.to) ? "page" : undefined}
                      >
                        {page.label}
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </li>
          );
        })}
      </ul>

      <div className="ditto-rail-foot">
        Ditto v0.1 · pesquisa de doutorado
      </div>
    </nav>
  );
}

/** On narrow screens the rail hides sub-pages; they appear here, at the top of the leaf. */
export function SubNav() {
  const { pathname } = useLocation();
  const section = sectionForPath(pathname);
  if (section.pages.length < 2) return null;
  return (
    <nav className="ditto-subnav" aria-label={`Páginas de ${section.label}`}>
      {section.pages.map((page) => (
        <Link
          key={page.to}
          to={page.to}
          aria-current={isPageActive(pathname, page.to) ? "page" : undefined}
        >
          {page.label}
        </Link>
      ))}
    </nav>
  );
}
