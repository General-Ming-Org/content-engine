import type { ResearchSweepProgress } from "../lib/api";
import { TaskProgressBar } from "./TaskProgressBar";

export function ResearchSweepProgressBar({
  progress,
  visible,
}: {
  progress: ResearchSweepProgress | null;
  visible: boolean;
}) {
  return (
    <TaskProgressBar
      progress={progress}
      visible={visible}
      hint="Check Notifications for details. Fix LLM or search settings and run again."
    />
  );
}
