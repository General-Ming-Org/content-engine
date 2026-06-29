import { format } from "date-fns";
import { AlertCircle, CheckCircle2, Loader2, X } from "lucide-react";

export interface TaskProgress {
  task_id: string;
  status: "running" | "complete" | "failed" | "blocked";
  percent?: number;
  message?: string;
  phase?: string;
  current?: number;
  total?: number;
  started_at?: string | null;
  finished_at?: string | null;
}

function formatTimestamp(iso: string | null | undefined) {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return format(d, "MMM d, yyyy · h:mm a");
}

export function TaskProgressBar({
  progress,
  visible,
  hint,
  onDismiss,
  label,
}: {
  progress: TaskProgress | null;
  visible: boolean;
  hint?: string;
  onDismiss?: () => void;
  label?: string;
}) {
  if (!visible) return null;

  const percent = progress?.percent ?? 5;
  const message = progress?.message ?? "Working…";
  const status = progress?.status;
  const running = visible && (!status || status === "running");
  const startedLabel = formatTimestamp(progress?.started_at);
  const finishedLabel = formatTimestamp(progress?.finished_at);

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
      <div className="flex items-start gap-2 mb-2">
        <div className="flex items-center gap-2 flex-1 min-w-0">
          {running ? (
            <Loader2 className="w-4 h-4 text-[color:var(--accent)] animate-spin flex-shrink-0 mt-0.5" />
          ) : status === "complete" ? (
            <CheckCircle2 className="w-4 h-4 text-green-400 flex-shrink-0 mt-0.5" />
          ) : status === "failed" || status === "blocked" ? (
            <AlertCircle className="w-4 h-4 text-red-400 flex-shrink-0 mt-0.5" />
          ) : null}
          <div className="min-w-0">
            {label && (
              <p className="text-[11px] font-medium uppercase tracking-wide text-gray-500 mb-0.5">
                {label}
              </p>
            )}
            <p className="text-sm text-gray-200">{message}</p>
            {(startedLabel || finishedLabel) && (
              <p className="text-xs text-gray-500 mt-1 tabular-nums">
                {startedLabel && <span>Started {startedLabel}</span>}
                {startedLabel && finishedLabel && <span className="mx-1.5 text-gray-700">·</span>}
                {finishedLabel && <span>Finished {finishedLabel}</span>}
              </p>
            )}
          </div>
        </div>
        <span className="text-xs text-gray-500 tabular-nums flex-shrink-0 pt-0.5">{percent}%</span>
        {onDismiss && (
          <button
            type="button"
            onClick={onDismiss}
            className="btn-ghost p-1 -mr-1 -mt-0.5 flex-shrink-0"
            aria-label="Dismiss"
          >
            <X className="w-4 h-4 text-gray-500" />
          </button>
        )}
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
