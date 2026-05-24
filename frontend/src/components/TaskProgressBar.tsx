import { AlertCircle, CheckCircle2, Loader2 } from "lucide-react";

export interface TaskProgress {
  task_id: string;
  status: "running" | "complete" | "failed" | "blocked";
  percent?: number;
  message?: string;
  phase?: string;
  current?: number;
  total?: number;
}

export function TaskProgressBar({
  progress,
  visible,
  hint,
}: {
  progress: TaskProgress | null;
  visible: boolean;
  hint?: string;
}) {
  if (!visible) return null;

  const percent = progress?.percent ?? 5;
  const message = progress?.message ?? "Working…";
  const status = progress?.status;
  const running = visible && (!status || status === "running");

  const barColor =
    status === "failed" || status === "blocked"
      ? "bg-red-500"
      : status === "complete"
        ? "bg-green-500"
        : "bg-[color:var(--accent)]";

  return (
    <div
      className="mb-4 rounded-xl border border-gray-800 bg-gray-900/80 px-4 py-3"
      role="status"
      aria-live="polite"
    >
      <div className="flex items-center gap-2 mb-2">
        {running ? (
          <Loader2 className="w-4 h-4 text-[color:var(--accent)] animate-spin flex-shrink-0" />
        ) : status === "complete" ? (
          <CheckCircle2 className="w-4 h-4 text-green-400 flex-shrink-0" />
        ) : status === "failed" || status === "blocked" ? (
          <AlertCircle className="w-4 h-4 text-red-400 flex-shrink-0" />
        ) : null}
        <p className="text-sm text-gray-200 flex-1 min-w-0">{message}</p>
        <span className="text-xs text-gray-500 tabular-nums flex-shrink-0">{percent}%</span>
      </div>
      <div className="h-2 bg-gray-800 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-500 ${barColor}`}
          style={{ width: `${Math.min(100, Math.max(0, percent))}%` }}
        />
      </div>
      {progress?.phase === "enriching" && (progress.total ?? 0) > 0 && running && (
        <p className="text-xs text-gray-500 mt-2">
          Topic {progress.current} of {progress.total}
        </p>
      )}
      {(status === "failed" || status === "blocked") && !running && (
        <p className="text-xs text-red-400/90 mt-2">
          {hint ?? "Check Notifications for details and try again."}
        </p>
      )}
      {status === "complete" && !running && (
        <p className="text-xs text-green-400/90 mt-2">Done — open Calendar or Library to review queued content.</p>
      )}
      {status === "running" && percent <= 15 && (
        <p className="text-xs text-gray-500 mt-2">This usually takes 30–90 seconds while the AI writes your post and article.</p>
      )}
    </div>
  );
}
