import { AnimatePresence } from "framer-motion";
import { Route, Routes, useLocation } from "react-router-dom";

import { TasksToast } from "./components/TasksToast";
import { PageTransition } from "./components/PageTransition";
import { Sidebar } from "./components/Sidebar";
import { TasksProvider } from "./context/TasksContext";
import { ExperimentDetailPage } from "./pages/ExperimentDetailPage";
import { ExperimentPage } from "./pages/ExperimentPage";
import { HomePage } from "./pages/HomePage";
import { IngestPage } from "./pages/IngestPage";
import { ResultsPage } from "./pages/ResultsPage";

export function App() {
  const location = useLocation();

  return (
    <TasksProvider>
      <div className="ditto-shell">
        <Sidebar />
        <main className="ditto-main">
          <div className="ditto-main-inner">
            <AnimatePresence mode="wait">
              <Routes location={location} key={location.pathname}>
                <Route
                  path="/"
                  element={
                    <PageTransition>
                      <HomePage />
                    </PageTransition>
                  }
                />
                <Route
                  path="/ingest"
                  element={
                    <PageTransition>
                      <IngestPage />
                    </PageTransition>
                  }
                />
                <Route
                  path="/experiment"
                  element={
                    <PageTransition>
                      <ExperimentPage />
                    </PageTransition>
                  }
                />
                <Route
                  path="/results"
                  element={
                    <PageTransition>
                      <ResultsPage />
                    </PageTransition>
                  }
                />
                <Route
                  path="/results/:id"
                  element={
                    <PageTransition>
                      <ExperimentDetailPage />
                    </PageTransition>
                  }
                />
              </Routes>
            </AnimatePresence>
          </div>
        </main>
        <TasksToast />
      </div>
    </TasksProvider>
  );
}
