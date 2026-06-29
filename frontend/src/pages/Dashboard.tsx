import { useQuery, useQueryClient } from "@tanstack/react-query";
import { formatDistanceToNow, format } from "date-fns";
import { CheckCircle, XCircle, Users, Eye, TrendingUp, Target } from "lucide-react";
import {
  getPosts,
  getGoals,
  getCurrentMetrics,
  triggerTask,
  type Post,
  type Goal,
} from "../lib/api";
import { useAuth } from "../lib/auth";
import { usePublishActions } from "../hooks/usePublishActions";
import { ResearchSweepProgressBar } from "../components/ResearchSweepProgress";
import { useResearchSweep } from "../hooks/useResearchSweep";

function excerpt(text: string | null | undefined, max: number) {
  const s = (text ?? "").trim();
  if (!s) return "—";
  return s.length > max ? `${s.slice(0, max)}…` : s;
}

function formatGoalDue(iso: string) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return format(d, "MMM d");
}

function StatusBadge({ status }: { status: Post["status"] }) {
  const cls: Record<string, string> = {
    draft: "badge-draft", queued: "badge-queued", scheduled: "badge-scheduled",
    published: "badge-published", failed: "badge-failed", cancelled: "badge-cancelled",
  };
  return <span className={cls[status] ?? "badge"}>{status}</span>;
}

function QueueCountdown({ queuedAt }: { queuedAt: string }) {
  const queued = new Date(queuedAt);
  const publishAt = new Date(queued.getTime() + 60 * 60 * 1000);
  const now = new Date();
  const msLeft = publishAt.getTime() - now.getTime();
  if (msLeft <= 0) return <span className="text-yellow-400 text-xs">Publishing soon…</span>;
  const minLeft = Math.ceil(msLeft / 60_000);
  return <span className="text-yellow-400 text-xs">{minLeft}m until auto-publish</span>;
}

export default function Dashboard() {
  const qc = useQueryClient();
  const { isAdmin } = useAuth();

  const { data: postsData } = useQuery({ queryKey: ["posts"], queryFn: () => getPosts() });
  const { data: goalsData } = useQuery({ queryKey: ["goals"], queryFn: getGoals });
  const { data: metricsData } = useQuery({ queryKey: ["current-metrics"], queryFn: getCurrentMetrics });

  const researchSweep = useResearchSweep({
    triggerFn: () => triggerTask("research_sweep"),
    onComplete: () => qc.invalidateQueries({ queryKey: ["posts"] }),
  });
  const showSweepTrigger = isAdmin;

  const publish = usePublishActions({
    onInvalidate: () => qc.invalidateQueries({ queryKey: ["posts"] }),
  });

  const posts = postsData?.posts ?? [];
  const goals = goalsData?.goals ?? [];
  const queuedPosts = posts.filter((p) => p.status === "queued");
  const publishedThisWeek = posts.filter((p) => {
    if (!p.published_at) return false;
    const d = new Date(p.published_at);
    const weekAgo = new Date(Date.now() - 7 * 86400_000);
    return d > weekAgo;
  });

  const liMetrics = metricsData?.linkedin?.data ?? {};
  const subMetrics = metricsData?.substack?.data ?? {};

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="text-xl font-semibold text-gray-100">Dashboard</h1>
          <p className="text-sm text-gray-500 mt-0.5">{format(new Date(), "EEEE, MMMM d")}</p>
        </div>
        {showSweepTrigger && (
          <button
            onClick={() => researchSweep.trigger()}
            disabled={researchSweep.isBusy}
            className="btn-primary"
          >
            {researchSweep.isBusy ? "Running…" : "Run Research Sweep"}
          </button>
        )}
      </div>

      {(showSweepTrigger || researchSweep.showProgressBar) && (
        <ResearchSweepProgressBar
          progress={researchSweep.progress}
          visible={researchSweep.showProgressBar}
          onDismiss={researchSweep.dismiss}
        />
      )}

      {/* Stat cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
        <div className="stat-card">
          <div className="flex items-center justify-between">
            <span className="text-xs text-gray-500">LinkedIn Followers</span>
            <Users className="w-4 h-4 text-gray-600" />
          </div>
          <span className="text-2xl font-semibold text-gray-100">
            {(liMetrics.followers as number | undefined)?.toLocaleString() ?? "—"}
          </span>
        </div>
        <div className="stat-card">
          <div className="flex items-center justify-between">
            <span className="text-xs text-gray-500">Substack Subscribers</span>
            <Users className="w-4 h-4 text-gray-600" />
          </div>
          <span className="text-2xl font-semibold text-gray-100">
            {(subMetrics.subscriber_count as number | undefined)?.toLocaleString() ?? "—"}
          </span>
        </div>
        <div className="stat-card">
          <div className="flex items-center justify-between">
            <span className="text-xs text-gray-500">Impressions (7d)</span>
            <Eye className="w-4 h-4 text-gray-600" />
          </div>
          <span className="text-2xl font-semibold text-gray-100">
            {(liMetrics.impressions_total as number | undefined)?.toLocaleString() ?? "—"}
          </span>
        </div>
        <div className="stat-card">
          <div className="flex items-center justify-between">
            <span className="text-xs text-gray-500">Avg Engagement</span>
            <TrendingUp className="w-4 h-4 text-gray-600" />
          </div>
          <span className="text-2xl font-semibold text-gray-100">
            {liMetrics.avg_engagement_rate != null
              ? `${liMetrics.avg_engagement_rate}%`
              : "—"}
          </span>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Queue */}
        <div className="lg:col-span-2 space-y-4">
          {queuedPosts.length > 0 && (
            <div>
              <p className="section-title">1-Hour Queue ({queuedPosts.length})</p>
              <div className="space-y-2">
                {queuedPosts.map((p) => (
                  <QueueItem
                    key={p.id}
                    post={p}
                    onPublish={() => publish.publishPost(p.id)}
                    onCancel={() => publish.cancelPost(p.id)}
                    busy={publish.isPostBusy(p.id)}
                    canPublish={
                      publish.linkedInAppConfigured &&
                      publish.linkedInAccountConnected
                    }
                    publishHint={
                      !publish.linkedInAppConfigured
                        ? "Set up LinkedIn app in Settings"
                        : !publish.linkedInAccountConnected
                          ? "Connect LinkedIn account in Settings"
                          : null
                    }
                  />
                ))}
              </div>
            </div>
          )}

          <div>
            <p className="section-title">Published This Week ({publishedThisWeek.length})</p>
            {publishedThisWeek.length === 0 ? (
              <p className="text-sm text-gray-600">No posts published yet this week.</p>
            ) : (
              <div className="space-y-2">
                {publishedThisWeek.slice(0, 5).map((p) => (
                  <div key={p.id} className="bg-gray-900 border border-gray-800 rounded-lg p-4">
                    <div className="flex items-start justify-between gap-4">
                      <p className="text-sm text-gray-300 line-clamp-2">{excerpt(p.content, 120)}</p>
                      <StatusBadge status={p.status} />
                    </div>
                    <div className="flex items-center gap-4 mt-2">
                      <span className="text-xs text-gray-600">
                        {p.published_at ? formatDistanceToNow(new Date(p.published_at), { addSuffix: true }) : ""}
                      </span>
                      {p.metrics && (
                        <span className="text-xs text-gray-600">
                          {p.metrics.impressions?.toLocaleString() ?? 0} impressions
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Goals */}
        <div>
          <p className="section-title">Goals</p>
          {goals.length === 0 ? (
            <p className="text-sm text-gray-600">No goals set. Add them in Analytics → Goals.</p>
          ) : (
            <div className="space-y-4">
              {goals.filter((g) => g.status === "active").slice(0, 4).map((g) => (
                <GoalCard key={g.id} goal={g} />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function QueueItem({
  post,
  onPublish,
  onCancel,
  busy,
  canPublish,
  publishHint,
}: {
  post: Post;
  onPublish: () => void;
  onCancel: () => void;
  busy?: boolean;
  canPublish: boolean;
  publishHint: string | null;
}) {
  return (
    <div className="bg-yellow-900/10 border border-yellow-800/40 rounded-lg p-4">
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <p className="text-sm text-gray-200 line-clamp-2">{excerpt(post.content, 140)}</p>
          {post.queued_at && <QueueCountdown queuedAt={post.queued_at} />}
          {publishHint && !busy && (
            <p className="text-xs text-amber-400/90 mt-1.5">{publishHint}</p>
          )}
        </div>
        {busy ? (
          <span className="text-xs text-gray-500 flex-shrink-0">Updating…</span>
        ) : (
          <div className="flex items-center gap-2 flex-shrink-0">
            <button
              type="button"
              onClick={onPublish}
              disabled={!canPublish}
              title={publishHint ?? undefined}
              className="flex items-center gap-1 text-xs text-green-400 hover:text-green-300 px-2 py-1 rounded border border-green-800/40 hover:bg-green-900/20 transition-colors disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-transparent"
            >
              <CheckCircle className="w-3 h-3" />
              Publish now
            </button>
            <button
              type="button"
              onClick={onCancel}
              className="flex items-center gap-1 text-xs text-red-400 hover:text-red-300 px-2 py-1 rounded border border-red-800/40 hover:bg-red-900/20 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <XCircle className="w-3 h-3" />
              Cancel
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

function GoalCard({ goal }: { goal: Goal }) {
  const pct = Math.min(goal.progress_pct, 100);
  const colorClass = goal.status === "achieved"
    ? "bg-green-500"
    : pct > 66
    ? "bg-accent"
    : pct > 33
    ? "bg-yellow-500"
    : "bg-gray-600";

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs text-gray-400 font-medium">{goal.metric_name.replace(/_/g, " ")}</span>
        <Target className="w-3.5 h-3.5 text-gray-600" />
      </div>
      <div className="flex items-end justify-between mb-2">
        <span className="text-lg font-semibold text-gray-100">
          {(goal.current_value ?? 0).toLocaleString()}
        </span>
        <span className="text-xs text-gray-500">/ {(goal.target_value ?? 0).toLocaleString()}</span>
      </div>
      <div className="h-1.5 bg-gray-800 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all ${colorClass}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <p className="text-xs text-gray-600 mt-1.5">{pct.toFixed(0)}% · due {formatGoalDue(goal.target_date)}</p>
    </div>
  );
}
