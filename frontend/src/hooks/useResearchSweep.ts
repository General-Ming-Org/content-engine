import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useGuardedMutation } from "./useGuardedMutation";
import {
  getResearchSweepStatus,
  triggerResearch,
  type ResearchSweepProgress,
  type TaskResult,
} from "../lib/api";

type TriggerFn = () => Promise<TaskResult>;

function isTerminal(status: ResearchSweepProgress["status"] | undefined) {
  return status === "complete" || status === "failed" || status === "blocked";
}

export function useResearchSweep(options?: {
  triggerFn?: TriggerFn;
  onComplete?: () => void;
}) {
  const qc = useQueryClient();
  const triggerFn = options?.triggerFn ?? triggerResearch;
  const [taskId, setTaskId] = useState<string | null>(null);
  const [showProgressBar, setShowProgressBar] = useState(false);
  const [isBusy, setIsBusy] = useState(false);
  const [dismissed, setDismissed] = useState(false);

  const { data: activeData } = useQuery({
    queryKey: ["research-sweep-active"],
    queryFn: () => getResearchSweepStatus(),
    refetchInterval: (query) => {
      if (isBusy) return false;
      return query.state.data?.active ? 1500 : 5000;
    },
  });

  useEffect(() => {
    if (dismissed) return;
    if (!isBusy && !taskId && activeData?.active && activeData.progress?.task_id) {
      setTaskId(activeData.progress.task_id);
      setIsBusy(true);
      setShowProgressBar(true);
    }
  }, [activeData, isBusy, taskId, dismissed]);

  const triggerMutation = useGuardedMutation({
    mutationFn: triggerFn,
    cooldownSeconds: 30,
    onMutate: () => {
      setDismissed(false);
      setIsBusy(true);
      setShowProgressBar(true);
    },
    onSuccess: (data) => {
      if (data.task_id) {
        setTaskId(data.task_id);
      }
    },
    onError: () => {
      setIsBusy(false);
      setShowProgressBar(false);
    },
  });

  const { data: statusData } = useQuery({
    queryKey: ["research-sweep-status", taskId],
    queryFn: () => getResearchSweepStatus(taskId ?? undefined),
    enabled: !!taskId,
    refetchInterval: (query) => {
      if (!taskId) return false;
      const status = query.state.data?.progress?.status;
      if (!status || status === "running") return 1500;
      return false;
    },
  });

  const progress = statusData?.progress ?? activeData?.progress ?? null;
  const terminal = isTerminal(progress?.status);

  useEffect(() => {
    if (!progress || progress.status === "running") return;
    qc.invalidateQueries({ queryKey: ["notifications"] });
    qc.invalidateQueries({ queryKey: ["notifications", "unread-count"] });
    qc.invalidateQueries({ queryKey: ["topics"] });
    qc.invalidateQueries({ queryKey: ["research-sweep-active"] });
    options?.onComplete?.();
  }, [progress?.status, progress?.task_id, qc, options]);

  // Re-enable the button as soon as the sweep finishes; keep the bar until dismissed.
  useEffect(() => {
    if (!terminal) return;
    setIsBusy(false);
  }, [terminal, progress?.task_id]);

  const dismiss = () => {
    setDismissed(true);
    setShowProgressBar(false);
    if (terminal) setTaskId(null);
  };

  const trigger = () => triggerMutation.guardedMutate();

  return {
    trigger,
    dismiss,
    isBusy: isBusy || triggerMutation.isPending,
    showProgressBar: !dismissed && (showProgressBar || triggerMutation.isPending),
    progress,
    taskId,
    error: triggerMutation.error,
  };
}

export type { ResearchSweepProgress };
