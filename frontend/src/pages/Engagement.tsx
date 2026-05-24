import { useQuery, useQueryClient } from "@tanstack/react-query";
import { format } from "date-fns";
import { MessageSquare, CheckCircle, XCircle, RefreshCw } from "lucide-react";
import { getEngagementLog, triggerEngagement } from "../lib/api";
import { useGuardedMutation } from "../hooks/useGuardedMutation";

export default function Engagement() {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ["engagement-log"],
    queryFn: () => getEngagementLog(),
  });

  const sweepMut = useGuardedMutation({
    mutationFn: triggerEngagement,
    successMessage: "Engagement sweep started.",
    cooldownSeconds: 30,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["engagement-log"] }),
  });

  const actions = data?.actions ?? [];
  const posted = actions.filter((a) => a.status === "posted").length;
  const pending = actions.filter((a) => a.status === "pending").length;
  const failed = actions.filter((a) => a.status === "failed").length;

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="text-xl font-semibold text-gray-100">Engagement</h1>
          <p className="text-sm text-gray-500 mt-0.5">Replies to comments on your LinkedIn posts</p>
        </div>
        <button
          onClick={() => sweepMut.guardedMutate()}
          disabled={sweepMut.actionDisabled}
          className="btn-primary flex items-center gap-2"
        >
          <RefreshCw className={`w-4 h-4 ${sweepMut.isPending ? "animate-spin" : ""}`} />
          {sweepMut.isPending ? "Sweeping…" : "Run Sweep"}
        </button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-3 gap-4 mb-8">
        <div className="stat-card">
          <span className="text-xs text-gray-500">Replies Sent</span>
          <span className="text-2xl font-semibold text-green-400">{posted}</span>
        </div>
        <div className="stat-card">
          <span className="text-xs text-gray-500">Pending</span>
          <span className="text-2xl font-semibold text-yellow-400">{pending}</span>
        </div>
        <div className="stat-card">
          <span className="text-xs text-gray-500">Failed</span>
          <span className="text-2xl font-semibold text-red-400">{failed}</span>
        </div>
      </div>

      {isLoading ? (
        <div className="space-y-3">
          {[...Array(4)].map((_, i) => <div key={i} className="h-32 bg-gray-900 rounded-xl animate-pulse" />)}
        </div>
      ) : actions.length === 0 ? (
        <div className="text-center py-16">
          <MessageSquare className="w-8 h-8 text-gray-700 mx-auto mb-3" />
          <p className="text-gray-500">No engagement actions yet.</p>
          <p className="text-sm text-gray-600 mt-1">Run a sweep to check for new comments on your posts.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {actions.map((action) => (
            <div key={action.id} className="bg-gray-900 border border-gray-800 rounded-xl p-4">
              <div className="flex items-start justify-between gap-4 mb-3">
                <div className="flex items-center gap-2">
                  {action.status === "posted" ? (
                    <CheckCircle className="w-4 h-4 text-green-400 flex-shrink-0" />
                  ) : action.status === "failed" ? (
                    <XCircle className="w-4 h-4 text-red-400 flex-shrink-0" />
                  ) : (
                    <div className="w-4 h-4 rounded-full border border-yellow-400 flex-shrink-0" />
                  )}
                  <span className={`badge ${action.status === "posted" ? "badge-published" : action.status === "failed" ? "badge-failed" : "badge-queued"}`}>
                    {action.status}
                  </span>
                </div>
                <span className="text-xs text-gray-600 flex-shrink-0">
                  {action.posted_at
                    ? format(new Date(action.posted_at), "MMM d, HH:mm")
                    : format(new Date(action.created_at), "MMM d, HH:mm")}
                </span>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div className="bg-gray-800/60 rounded-lg p-3">
                  <p className="text-xs text-gray-500 mb-1.5">Original comment</p>
                  <p className="text-xs text-gray-300">{action.original_comment}</p>
                </div>
                <div className="bg-accent/5 border border-accent/20 rounded-lg p-3">
                  <p className="text-xs text-accent/60 mb-1.5">Your reply</p>
                  <p className="text-xs text-gray-300">{action.reply_text}</p>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
