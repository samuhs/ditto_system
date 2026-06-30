import { AppShell, NavLink, Title } from "@mantine/core";
import { Link, Route, Routes, useLocation } from "react-router-dom";

import { ExperimentPage } from "./pages/ExperimentPage";
import { IngestPage } from "./pages/IngestPage";
import { ResultsPage } from "./pages/ResultsPage";

const NAV = [
  { to: "/", label: "Inserir documentos" },
  { to: "/experiment", label: "Gerar teste" },
  { to: "/results", label: "Resultados" },
];

export function App() {
  const location = useLocation();
  return (
    <AppShell navbar={{ width: 220, breakpoint: "sm" }} padding="md">
      <AppShell.Navbar p="md">
        <Title order={4} mb="md">
          Ditto
        </Title>
        {NAV.map((item) => (
          <NavLink
            key={item.to}
            component={Link}
            to={item.to}
            label={item.label}
            active={location.pathname === item.to}
          />
        ))}
      </AppShell.Navbar>
      <AppShell.Main>
        <Routes>
          <Route path="/" element={<IngestPage />} />
          <Route path="/experiment" element={<ExperimentPage />} />
          <Route path="/results" element={<ResultsPage />} />
        </Routes>
      </AppShell.Main>
    </AppShell>
  );
}
