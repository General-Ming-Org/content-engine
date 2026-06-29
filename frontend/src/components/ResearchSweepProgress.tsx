import type { ResearchSweepProgress } from "../lib/api";
import { TaskProgressBar } from "./TaskProgressBar";

export function ResearchSweepProgressBar({
  progress,
  visible,
  onDismiss,
}: {
  progress: ResearchSweepProgress | null;
  visible: boolean;
  onDismiss?: () => void;
}) {
  return (
    <TaskProgressBar
      progress={progress}
      visible={visible}
      onDismiss={onDismiss}
      label="Research sweep"
      hint="Check Notifications for details. Fix LLM or search settings and run again."
    />
  );
}
