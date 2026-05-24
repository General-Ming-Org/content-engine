import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar, Legend,
} from "recharts";
import { format } from "date-fns";
import { Plus, Trash2, TrendingUp, TrendingDown, Target } from "lucide-react";
import {
  getMetrics, getBenchmarks, getGoals, getReports, createGoal, deleteGoal, triggerMetricCollection,
  type Goal,
} from "../lib/api";

type Tab = "metrics" | "benchmarks" | "goals" | "reports";

export default function Analytics() {
  const [tab, setTab] = useState<Tab>("metrics");

  return (
    <div>
      <div className="page-header">
        <h1 className="text-xl font-semibold text-gray-100">Analytics</h1>
      </div>

      <div className="flex gap-1 mb-6 bg-gray-900 rounded-lg p-1 w-fit border border-gray-800">
        {(["metrics", "benchmarks", "goals", "reports"] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-1.5 rounded-md text-sm capitalize transition-colors ${
              tab === t ? "bg-gray-800 text-gray-100 font-medium" : "text-gray-500 hover:text-gray-300"
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      {tab === "metrics" && <MetricsTab />}
      {tab === "benchmarks" && <BenchmarksTab />}
      {tab === "goals" && <GoalsTab />}
      {tab === "reports" && <ReportsTab />}
    </div>
  );
}

function MetricsTab() {
  const qc = useQueryClient();
  const [platform, setPlatform] = useState<string>("linkedin");

  const { data } = useQuery({
    queryKey: ["metrics", platform],
    queryFn: () => getMetrics({ platform }),
  });

  const collectMut = useMutation({
    mutationFn: triggerMetricCollection,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["metrics"] }),
  });

  const snapshots = (data?.snapshots ?? []).slice().reverse();
  const chartData = snapshots.map((s) => ({
    date: format(new Date(s.snapshot_date), "MMM d"),
    followers: (s.data.followers as number) ?? 0,
    impressions: (s.data.impressions_total as number) ?? 0,
    engagement: (s.data.avg_engagement_rate as number) ?? 0,
  }));

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex gap-2">
          {["linkedin", "substack"].map((p) => (
            <button
              key={p}
              onClick={() => setPlatform(p)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium capitalize transition-colors ${
                platform === p ? "bg-accent text-white" : "bg-gray-800 text-gray-400 hover:text-gray-100"
              }`}
            >
              {p}
            </button>
          ))}
        </div>
        <button
          onClick={() => collectMut.mutate()}
          disabled={collectMut.isPending}
          className="btn-primary text-xs"
        >
          {collectMut.isPending ? "Collecting…" : "Collect Now"}
        </button>
      </div>

      {chartData.length === 0 ? (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-8 text-center">
          <p className="text-gray-500">No metric data yet. Click "Collect Now" to gather your first snapshot.</p>
        </div>
      ) : (
        <>
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
            <p className="text-xs font-medium text-gray-500 mb-4">Followers / Subscribers</p>
            <ResponsiveContainer width="100%" height={200}>
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#28282c" />
                <XAxis dataKey="date" tick={{ fill: "#62626a", fontSize: 11 }} />
                <YAxis tick={{ fill: "#62626a", fontSize: 11 }} />
                <Tooltip
                  contentStyle={{ background: "#1c1c1f", border: "1px solid #3a3a3f", borderRadius: 8 }}
                  labelStyle={{ color: "#b4b4be" }}
                />
                <Line type="monotone" dataKey="followers" stroke="#5b5bd6" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>

          <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
            <p className="text-xs font-medium text-gray-500 mb-4">Avg Engagement Rate (%)</p>
            <ResponsiveContainer width="100%" height={200}>
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#28282c" />
                <XAxis dataKey="date" tick={{ fill: "#62626a", fontSize: 11 }} />
                <YAxis tick={{ fill: "#62626a", fontSize: 11 }} />
                <Tooltip
                  contentStyle={{ background: "#1c1c1f", border: "1px solid #3a3a3f", borderRadius: 8 }}
                  labelStyle={{ color: "#b4b4be" }}
                />
                <Line type="monotone" dataKey="engagement" stroke="#22c55e" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </>
      )}
    </div>
  );
}

function BenchmarksTab() {
  const { data } = useQuery({ queryKey: ["benchmarks"], queryFn: getBenchmarks });
  if (!data) return <div className="text-gray-500">Loading…</div>;

  const items = Object.entries(data.tech_content).filter(([k]) => !k.includes("note"));

  return (
    <div className="space-y-4">
      <p className="text-xs text-gray-500">
        Source: {data.sources.join(", ")} — Updated {data.last_updated}
      </p>
      <div className="grid grid-cols-2 gap-3">
        {items.map(([key, val]) => (
          <div key={key} className="bg-gray-900 border border-gray-800 rounded-xl p-4">
            <p className="text-xs text-gray-500 mb-1">{key.replace(/_/g, " ")}</p>
            <p className="text-xl font-semibold text-gray-100">
              {typeof val === "number" ? (key.includes("rate") || key.includes("pct") ? `${val}%` : val.toLocaleString()) : val}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}

function GoalsTab() {
  const qc = useQueryClient();
  const { data } = useQuery({ queryKey: ["goals"], queryFn: getGoals });
  const [newGoal, setNewGoal] = useState({ metric_name: "", target_value: "", target_date: "" });
  const [showForm, setShowForm] = useState(false);

  const createMut = useMutation({
    mutationFn: () => createGoal({ ...newGoal, target_value: parseFloat(newGoal.target_value) }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["goals"] }); setShowForm(false); },
  });

  const deleteMut = useMutation({
    mutationFn: deleteGoal,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["goals"] }),
  });

  const goals = data?.goals ?? [];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-gray-400">{goals.length} goals</p>
        <button onClick={() => setShowForm(!showForm)} className="btn-primary text-xs">
          <Plus className="w-3.5 h-3.5 inline mr-1" /> New Goal
        </button>
      </div>

      {showForm && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 space-y-3">
          <input
            className="input"
            placeholder="Metric name (e.g. linkedin_followers)"
            value={newGoal.metric_name}
            onChange={(e) => setNewGoal((g) => ({ ...g, metric_name: e.target.value }))}
          />
          <div className="grid grid-cols-2 gap-3">
            <input
              className="input"
              type="number"
              placeholder="Target value"
              value={newGoal.target_value}
              onChange={(e) => setNewGoal((g) => ({ ...g, target_value: e.target.value }))}
            />
            <input
              className="input"
              type="date"
              value={newGoal.target_date}
              onChange={(e) => setNewGoal((g) => ({ ...g, target_date: e.target.value }))}
            />
          </div>
          <div className="flex gap-2">
            <button onClick={() => createMut.mutate()} className="btn-primary text-xs">Save</button>
            <button onClick={() => setShowForm(false)} className="btn-ghost text-xs">Cancel</button>
          </div>
        </div>
      )}

      {goals.map((g) => <GoalRow key={g.id} goal={g} onDelete={() => deleteMut.mutate(g.id)} />)}
    </div>
  );
}

function GoalRow({ goal, onDelete }: { goal: Goal; onDelete: () => void }) {
  const pct = Math.min(goal.progress_pct, 100);
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
      <div className="flex items-center justify-between mb-3">
        <div>
          <p className="text-sm font-medium text-gray-100">{goal.metric_name.replace(/_/g, " ")}</p>
          <p className="text-xs text-gray-500">
            {goal.current_value.toLocaleString()} / {goal.target_value.toLocaleString()} · due {format(new Date(goal.target_date), "MMM d, yyyy")}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className={`badge ${goal.status === "achieved" ? "badge-published" : goal.status === "missed" ? "badge-failed" : "badge-queued"}`}>
            {goal.status}
          </span>
          <button onClick={onDelete} className="text-gray-600 hover:text-red-400 transition-colors">
            <Trash2 className="w-4 h-4" />
          </button>
        </div>
      </div>
      <div className="h-2 bg-gray-800 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full ${pct >= 100 ? "bg-green-500" : "bg-accent"}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <p className="text-xs text-gray-600 mt-1">{pct.toFixed(0)}% complete</p>
    </div>
  );
}

function ReportsTab() {
  const { data } = useQuery({ queryKey: ["reports"], queryFn: () => getReports() });
  const reports = data?.reports ?? [];

  if (reports.length === 0) {
    return <div className="text-center py-16 text-gray-500">No reports generated yet.</div>;
  }

  return (
    <div className="space-y-4">
      {reports.map((r) => (
        <div key={r.id} className="bg-gray-900 border border-gray-800 rounded-xl p-5">
          <div className="flex items-center justify-between mb-3">
            <div>
              <span className={`badge ${r.report_type === "weekly_deep_dive" ? "badge-scheduled" : "badge-published"} mr-2`}>
                {r.report_type.replace(/_/g, " ")}
              </span>
              <span className="text-xs text-gray-500">
                {r.period_start} — {r.period_end}
              </span>
            </div>
            <span className="text-xs text-gray-600">{format(new Date(r.created_at), "MMM d, HH:mm")}</span>
          </div>
          {r.report_json.headline && (
            <p className="text-sm text-gray-300 mb-3">{r.report_json.headline as string}</p>
          )}
          {r.report_json.observations && (
            <ul className="space-y-1">
              {(r.report_json.observations as string[]).map((obs, i) => (
                <li key={i} className="text-xs text-gray-500 flex gap-2">
                  <span className="text-accent">·</span> {obs}
                </li>
              ))}
            </ul>
          )}
        </div>
      ))}
    </div>
  );
}
