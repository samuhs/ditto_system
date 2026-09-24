import { Link } from "react-router-dom";

import { type Task, useTasks } from "../context/TasksContext";
import { CloseIcon } from "./icons";
import { StatusTag } from "./StatusTag";

const KIND_LABEL: Record<Task["kind"], string> = {
  ingest: "Preparação de documentos",
  experiment: "Experimento",
};

/** Background jobs keep running while the user moves around; each one reports here. */
export function TasksToast() {
  const { tasks, dismissTask } = useTasks();
  if (tasks.length === 0) return null;

  return (
    <section className="ditto-tasks" aria-label="Tarefas em segundo plano" aria-live="polite">
      {tasks.map((task) => (
        <div key={task.id} className="ditto-task" data-status={task.status}>
          <span className="ditto-task-kind">{KIND_LABEL[task.kind]}</span>
          <span className="ditto-task-label" title={task.label}>
            {task.label}
          </span>
          <StatusTag status={task.status} />
          {task.message && <span className="ditto-task-message">{task.message}</span>}
          <span className="ditto-task-side">
            {task.status !== "running" && (
              <button
                className="ditto-task-close"
                onClick={() => dismissTask(task.id)}
                aria-label="Fechar aviso"
              >
                <CloseIcon />
              </button>
            )}
            {task.kind === "experiment" && (
              <Link className="ditto-task-open" to={`/results/${task.experimentId}`}>
                Abrir
              </Link>
            )}
          </span>
        </div>
      ))}
    </section>
  );
}
