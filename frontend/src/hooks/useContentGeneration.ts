import { useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { generateContent, getContentGenerationStatus } from "../lib/api";
import type { TaskProgress } from "../components/TaskProgressBar";
import { getApiErrorMessage } from "../lib/apiErrors";
import { useGuardedMutation } from "./useGuardedMutation";

const POLL_MS = 1500;
const TIMEOUT_MS = 120_000;

function isTerminal(status: TaskProgress["status"] | undefined) {
  return status === "complete" || status === "failed" || status === "blocked";
}

function fallbackProgress(taskId: string | null, topicId: string | null): TaskProgress {
  return {
    task_id: taskId ?? "pending",
    status: "running",
    percent: 12,
    message: "Generating content (LinkedIn + Substack)…",
    phase: "pairing",
  };
}

export function useContentGeneration(options?: { onComplete?: () => void }) {
  const qc = useQueryClient();
  const [taskId, setTaskId] = useState<string | null>(null);
  const [generatingTopicId, setGeneratingTopicId] = useState<string | null>(null);
  const [showProgressBar, setShowProgressBar] = useState(false);
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [timedOut, setTimedOut] = useState(false);

  const isTracking = !!(taskId || generatingTopicId);

  const { data: statusData, error: statusError } = useQuery({
    queryKey: ["content-generation-status", taskId],
    queryFn: () => getContentGenerationStatus(taskId ?? undefined),
    enabled: !!taskId,
    refetchInterval: (query) => {
      if (!taskId || timedOut) return false;
      const status = query.state.data?.progress?.status;
      if (!status || status === "running") return POLL_MS;
      return false;
    },
  });

  const generateMutation = useGuardedMutation({
    mutationFn: (topicId: string) => generateContent(topicId),
    cooldownSeconds: 5,
    onMutate: (topicId) => {
      setGeneratingTopicId(topicId);
      setShowProgressBar(true);
      setStartedAt(Date.now());
      setTimedOut(false);
      setTaskId(null);
    },
    onSuccess: (data) => {
      if (data.task_id) {
        setTaskId(data.task_id);
      } else {
        setTimedOut(true);
      }
    },
    onError: () => {
      setGeneratingTopicId(null);
      setShowProgressBar(false);
      setTaskId(null);
      setStartedAt(null);
    },
    errorMessage: (err) =>
      getApiErrorMessage(err, "Content generation failed. Check Notifications or try again."),
  });

  const progress = (statusData?.progress ?? null) as TaskProgress | null;
  const terminal = timedOut || isTerminal(progress?.status);

  const displayProgress = useMemo((): TaskProgress | null => {
    if (progress) return progress;
    if (isTracking && !terminal) return fallbackProgress(taskId, generatingTopicId);
    return null;
  }, [progress, isTracking, terminal, taskId, generatingTopicId]);

  const isBusy = isTracking && !terminal;

  useEffect(() => {
    if (!startedAt || terminal) return;
    const timer = setTimeout(() => {
      setTimedOut(true);
      setGeneratingTopicId(null);
      qc.invalidateQueries({ queryKey: ["topics"] });
      qc.invalidateQueries({ queryKey: ["calendar"] });
      qc.invalidateQueries({ queryKey: ["posts"] });
      qc.invalidateQueries({ queryKey: ["articles"] });
      options?.onComplete?.();
    }, TIMEOUT_MS);
    return () => clearTimeout(timer);
  }, [startedAt, terminal, qc, options]);

  useEffect(() => {
    if (!progress || progress.status === "running") return;
    setGeneratingTopicId(null);
    qc.invalidateQueries({ queryKey: ["topics"] });
    qc.invalidateQueries({ queryKey: ["calendar"] });
    qc.invalidateQueries({ queryKey: ["posts"] });
    qc.invalidateQueries({ queryKey: ["articles"] });
    qc.invalidateQueries({ queryKey: ["notifications"] });
    options?.onComplete?.();
  }, [progress?.status, progress?.task_id, qc, options]);

  useEffect(() => {
    if (!terminal) return;
    const timer = setTimeout(() => {
      setShowProgressBar(false);
      setTaskId(null);
      setStartedAt(null);
      setTimedOut(false);
    }, 12_000);
    return () => clearTimeout(timer);
  }, [terminal, progress?.task_id, timedOut]);

  const generate = (topicId: string) => generateMutation.guardedMutate(topicId);
  const isGeneratingTopic = (topicId: string) =>
    generatingTopicId === topicId && (generateMutation.isPending || isBusy);

  return {
    generate,
    isGeneratingTopic,
    isBusy: isBusy || generateMutation.isPending,
    showProgressBar: showProgressBar || generateMutation.isPending,
    progress: displayProgress,
    error: generateMutation.error ?? statusError,
    timedOut,
  };
}
