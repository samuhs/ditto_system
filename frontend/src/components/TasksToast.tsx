import { Loader } from "@mantine/core";

import { type Task, useTasks } from "../context/TasksContext";

function StatusIcon({ task }: { task: Task }) {
  if (task.status === "running") return <Loader size={14} color="#05dbf2" />;
  if (task.status === "done") return <span style={{ color: "#07f285", fontSize: "1rem" }}>✓</span>;
  if (task.status === "paused") return <span style={{ color: "#f2ec91", fontSize: "1rem" }}>⏸</span>;
  return <span style={{ color: "#f26d6d", fontSize: "1rem" }}>✕</span>;
}

export function TasksToast() {
  const { tasks, dismissTask } = useTasks();
  if (tasks.length === 0) return null;

  return (
    <div className="ditto-tasks-tray">
      {tasks.map((task) => (
        <div key={task.id} className="ditto-task-card" data-status={task.status}>
          <div className="ditto-task-icon">
            <StatusIcon task={task} />
          </div>
          <div className="ditto-task-body">
            <span className="ditto-task-kind">
              {task.kind === "ingest" ? "Inserção" : "Experimento"}
            </span>
            <span className="ditto-task-label" title={task.label}>
              {task.label}
            </span>
            {task.message && (
              <span className="ditto-task-message">{task.message}</span>
            )}
          </div>
          {task.status !== "running" && (
            <button
              className="ditto-task-dismiss"
              onClick={() => dismissTask(task.id)}
              aria-label="Fechar notificação"
            >
              ✕
            </button>
          )}
        </div>
      ))}
    </div>
  );
}
