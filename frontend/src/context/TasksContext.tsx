import { createContext, useCallback, useContext, useRef, useState } from "react";

import { getExperiment } from "../api/client";
import type { IngestResult } from "../api/types";

type TaskStatus = "running" | "done" | "failed" | "paused";

interface BaseTask {
  id: string;
  status: TaskStatus;
  message?: string;
}

export interface IngestTask extends BaseTask {
  kind: "ingest";
  label: string;
}

export interface ExperimentTask extends BaseTask {
  kind: "experiment";
  label: string;
  experimentId: number;
}

export type Task = IngestTask | ExperimentTask;

interface TasksContextValue {
  tasks: Task[];
  addIngestTask: (label: string, promise: Promise<IngestResult>) => void;
  addExperimentTask: (experimentId: number, name: string) => void;
  dismissTask: (id: string) => void;
}

const TasksContext = createContext<TasksContextValue | null>(null);

const POLL_MS = 2000;
const AUTO_DISMISS_MS = 8000;

export function TasksProvider({ children }: { children: React.ReactNode }) {
  const [tasks, setTasks] = useState<Task[]>([]);
  const timers = useRef<Map<string, number>>(new Map());

  function patch(id: string, changes: Partial<Task>) {
    setTasks((prev) => prev.map((t) => (t.id === id ? ({ ...t, ...changes } as Task) : t)));
  }

  function scheduleAutoDismiss(id: string) {
    const timer = window.setTimeout(() => {
      timers.current.delete(id + "_auto");
      setTasks((prev) => prev.filter((t) => t.id !== id));
    }, AUTO_DISMISS_MS);
    timers.current.set(id + "_auto", timer);
  }

  function pollExperiment(taskId: string, experimentId: number) {
    const timer = window.setTimeout(() => {
      timers.current.delete(taskId);
      getExperiment(experimentId)
        .then((detail) => {
          const p = detail.progress;
          const progressMsg =
            p && p.total > 0 ? `${p.completed}/${p.total} combinações` : undefined;
          if (detail.status === "done") {
            patch(taskId, {
              status: "done",
              message: p && p.total > 0 ? `${p.total} combinações concluídas` : undefined,
            });
            scheduleAutoDismiss(taskId);
          } else if (detail.status === "paused") {
            patch(taskId, {
              status: "paused",
              message: p && p.total > 0 ? `pausado em ${p.completed}/${p.total}` : "pausado",
            });
          } else if (detail.status === "failed") {
            patch(taskId, { status: "failed", message: detail.error ?? undefined });
          } else {
            patch(taskId, { message: progressMsg });
            pollExperiment(taskId, experimentId);
          }
        })
        .catch((err) => {
          patch(taskId, {
            status: "failed",
            message: err instanceof Error ? err.message : String(err),
          });
        });
    }, POLL_MS);
    timers.current.set(taskId, timer);
  }

  const addIngestTask = useCallback((label: string, promise: Promise<IngestResult>) => {
    const id = crypto.randomUUID();
    setTasks((prev) => [...prev, { id, kind: "ingest", label, status: "running" }]);
    promise
      .then((result) => {
        patch(id, {
          status: "done",
          message: `${result.total_chunks} trechos em ${result.collections.length} coleção(ões)`,
        });
        scheduleAutoDismiss(id);
      })
      .catch((err) => {
        patch(id, {
          status: "failed",
          message: err instanceof Error ? err.message : String(err),
        });
      });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const addExperimentTask = useCallback((experimentId: number, name: string) => {
    const id = crypto.randomUUID();
    setTasks((prev) => [
      ...prev,
      { id, kind: "experiment", label: name, experimentId, status: "running" },
    ]);
    pollExperiment(id, experimentId);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const dismissTask = useCallback((id: string) => {
    window.clearTimeout(timers.current.get(id));
    window.clearTimeout(timers.current.get(id + "_auto"));
    timers.current.delete(id);
    timers.current.delete(id + "_auto");
    setTasks((prev) => prev.filter((t) => t.id !== id));
  }, []);

  return (
    <TasksContext.Provider value={{ tasks, addIngestTask, addExperimentTask, dismissTask }}>
      {children}
    </TasksContext.Provider>
  );
}

export function useTasks(): TasksContextValue {
  const ctx = useContext(TasksContext);
  if (!ctx) throw new Error("useTasks must be used within TasksProvider");
  return ctx;
}
