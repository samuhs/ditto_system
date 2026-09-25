import { Route, Routes, useLocation } from "react-router-dom";

import { Sidebar, SubNav } from "./components/Sidebar";
import { TasksToast } from "./components/TasksToast";
import { TasksProvider } from "./context/TasksContext";
import { AgentePage } from "./pages/AgentePage";
import { AvaliacaoPage } from "./pages/AvaliacaoPage";
import { ChatConfigsPage } from "./pages/ChatConfigsPage";
import { ChatPage } from "./pages/ChatPage";
import { DialoguePage } from "./pages/DialoguePage";
import { DialoguesPage } from "./pages/DialoguesPage";
import { ExperimentDetailPage } from "./pages/ExperimentDetailPage";
import { ExperimentPage } from "./pages/ExperimentPage";
import { HomePage } from "./pages/HomePage";
import { IngestPage } from "./pages/IngestPage";
import { PromptsPage } from "./pages/PromptsPage";
import { ResultsPage } from "./pages/ResultsPage";
import { SettingsPage } from "./pages/SettingsPage";
import { SectionContext, sectionForPath } from "./sections";

export function App() {
  const location = useLocation();
  const section = sectionForPath(location.pathname);

  return (
    <TasksProvider>
      <SectionContext.Provider value={section}>
        <a className="ditto-skip" href="#conteudo">
          Pular para o conteúdo
        </a>
        <div className="ditto-shell" data-section={section.id}>
          <Sidebar />
          <div className="ditto-board">
            <main id="conteudo" className="ditto-leaf" tabIndex={-1}>
              <SubNav />
              {/* keyed by path so each page turn replays the hinge */}
              <div className="ditto-page" key={location.pathname}>
                <Routes location={location}>
                  <Route path="/" element={<HomePage />} />
                  <Route path="/ingest" element={<IngestPage />} />
                  <Route path="/experiment" element={<ExperimentPage />} />
                  <Route path="/results" element={<ResultsPage />} />
                  <Route path="/results/:id" element={<ExperimentDetailPage />} />
                  <Route path="/prompts" element={<PromptsPage />} />
                  <Route path="/chat-configs" element={<ChatConfigsPage />} />
                  <Route path="/chat" element={<ChatPage />} />
                  <Route path="/dialogues" element={<DialoguesPage />} />
                  <Route path="/dialogues/:id" element={<DialoguePage />} />
                  <Route path="/agente" element={<AgentePage />} />
                  <Route path="/avaliacao" element={<AvaliacaoPage />} />
                  <Route path="/configuracoes" element={<SettingsPage />} />
                </Routes>
              </div>
            </main>
          </div>
          <TasksToast />
        </div>
      </SectionContext.Provider>
    </TasksProvider>
  );
}
