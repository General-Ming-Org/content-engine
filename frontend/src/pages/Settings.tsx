import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Send, Play, Check, Palette } from "lucide-react";
import {
  getSettings,
  updateSetting,
  getSchedulerStatus,
  triggerTask,
  getSmtpTo,
  setSmtpTo,
} from "../lib/api";
import { LinkedInSetup } from "../components/LinkedInSetup";
import { useAuth } from "../lib/auth";
import { useTheme } from "../components/ThemeProvider";
import { useGuardedMutation } from "../hooks/useGuardedMutation";

export default function Settings() {
  const { data: settings } = useQuery({ queryKey: ["settings"], queryFn: getSettings });
  const { data: schedulerData } = useQuery({ queryKey: ["scheduler-status"], queryFn: getSchedulerStatus });

  return (
    <div>
      <div className="page-header">
        <h1 className="text-xl font-semibold text-gray-100">Settings</h1>
      </div>

      <div className="max-w-3xl space-y-6">
        <LinkedInSetup />
        <AppearanceSettings />
        <ScheduleSettings settings={settings} />
        <EmailSettings settings={settings} />
        <ToneSettings settings={settings} />
        <SchedulerStatus tasks={schedulerData?.tasks ?? []} />
      </div>
    </div>
  );
}

function AppearanceSettings() {
  const { theme, themes, setTheme } = useTheme();
  const dark = themes.filter((t) => t.mode === "dark");
  const light = themes.filter((t) => t.mode === "light");

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
      <h2 className="text-sm font-semibold text-gray-200 mb-1 flex items-center gap-2">
        <Palette className="w-4 h-4 text-[color:var(--accent)]" />
        Appearance & Themes
      </h2>
      <p className="text-xs text-gray-500 mb-4">
        Theme palettes inspired by popular VS Code themes. Changes apply immediately and sync across tabs.
      </p>

      <div className="space-y-4">
        <ThemeGroup title="Dark" themes={dark} active={theme} onSelect={setTheme} />
        <ThemeGroup title="Light" themes={light} active={theme} onSelect={setTheme} />
      </div>
    </div>
  );
}

function ThemeGroup({
  title,
  themes,
  active,
  onSelect,
}: {
  title: string;
  themes: ReturnType<typeof useTheme>["themes"];
  active: string;
  onSelect: (id: any) => void;
}) {
  return (
    <div>
      <div className="text-xs uppercase tracking-wider text-gray-500 mb-2">{title}</div>
      <div className="grid grid-cols-2 gap-2.5">
        {themes.map((t) => {
          const isActive = t.id === active;
          return (
            <button
              key={t.id}
              onClick={() => onSelect(t.id)}
              className={`relative flex items-center gap-2.5 px-3 py-2.5 rounded-lg border text-left text-sm transition-colors ${
                isActive
                  ? "border-[color:var(--accent)] bg-[color:var(--accent)]/10"
                  : "border-gray-800 hover:border-gray-600 bg-gray-800/40"
              }`}
            >
              <span className="flex -space-x-1.5">
                <span
                  className="w-4 h-4 rounded-full border border-black/20"
                  style={{ background: t.vars["--bg-base"] }}
                />
                <span
                  className="w-4 h-4 rounded-full border border-black/20"
                  style={{ background: t.vars["--bg-elevated"] }}
                />
                <span
                  className="w-4 h-4 rounded-full border border-black/20"
                  style={{ background: t.vars["--accent"] }}
                />
              </span>
              <span className="flex-1 text-gray-200 truncate">{t.label}</span>
              {isActive && <Check className="w-4 h-4 text-[color:var(--accent)] flex-shrink-0" />}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function ScheduleSettings({ settings }: { settings: Record<string, unknown> | undefined }) {
  const qc = useQueryClient();
  const schedule = (settings?.posting_schedule as any) ?? {};
  const mut = useMutation({
    mutationFn: (v: unknown) => updateSetting("posting_schedule", v),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["settings"] }),
  });

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
      <h2 className="text-sm font-semibold text-gray-200 mb-4">Posting Schedule</h2>
      <div className="space-y-3">
        <div>
          <label className="block text-xs text-gray-500 mb-1.5">LinkedIn posting days</label>
          <div className="flex gap-2 flex-wrap">
            {["monday","tuesday","wednesday","thursday","friday","saturday","sunday"].map((day) => {
              const active = (schedule.linkedin?.days ?? []).includes(day);
              return (
                <button
                  key={day}
                  className={`px-3 py-1 rounded-md text-xs capitalize transition-colors ${
                    active ? "bg-accent text-white" : "bg-gray-800 text-gray-400 hover:text-gray-200"
                  }`}
                  onClick={() => {
                    const days = active
                      ? schedule.linkedin.days.filter((d: string) => d !== day)
                      : [...(schedule.linkedin?.days ?? []), day];
                    mut.mutate({ ...schedule, linkedin: { ...schedule.linkedin, days } });
                  }}
                >
                  {day.slice(0, 3)}
                </button>
              );
            })}
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs text-gray-500 mb-1.5">LinkedIn time (UTC)</label>
            <input
              type="time"
              className="input"
              defaultValue={schedule.linkedin?.time ?? "14:00"}
              onBlur={(e) => mut.mutate({ ...schedule, linkedin: { ...schedule.linkedin, time: e.target.value } })}
            />
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1.5">Substack day</label>
            <select
              className="input"
              defaultValue={schedule.substack?.day ?? "saturday"}
              onChange={(e) => mut.mutate({ ...schedule, substack: { ...schedule.substack, day: e.target.value } })}
            >
              {["monday","tuesday","wednesday","thursday","friday","saturday","sunday"].map((d) => (
                <option key={d} value={d}>{d.charAt(0).toUpperCase() + d.slice(1)}</option>
              ))}
            </select>
          </div>
        </div>
      </div>
    </div>
  );
}

function EmailSettings({ settings }: { settings: Record<string, unknown> | undefined }) {
  const qc = useQueryClient();
  const { user } = useAuth();
  const digestSettings = (settings?.email_digest as any) ?? {};
  const [testResult, setTestResult] = useState<string | null>(null);
  const { data: smtpTo } = useQuery({ queryKey: ["smtp-to"], queryFn: getSmtpTo });
  const mut = useMutation({
    mutationFn: (v: unknown) => updateSetting("email_digest", v),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["settings"] }),
  });
  const smtpMut = useMutation({
    mutationFn: setSmtpTo,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["smtp-to"] }),
  });
  const testMut = useGuardedMutation<void, Error, void>({
    mutationFn: () => triggerTask("morning_email"),
    successMessage: "Test email queued — check your inbox.",
    cooldownSeconds: 300,
    onSuccess: () => setTestResult("Test email queued — check your inbox."),
  });

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
      <h2 className="text-sm font-semibold text-gray-200 mb-1">Email Digests</h2>
      <p className="text-xs text-gray-500 mb-4">
        Morning and evening digests go to your account email by default. Use the field below only
        if you want a different recipient.
      </p>
      <div className="mb-4">
        <label className="block text-xs text-gray-500 mb-1.5">Send digests to</label>
        <input
          type="email"
          className="input"
          key={smtpTo?.override ?? "default"}
          defaultValue={smtpTo?.override ?? user?.email ?? ""}
          placeholder={user?.email ?? "you@example.com"}
          onBlur={(e) => {
            const value = e.target.value.trim();
            if (!value || value === user?.email) return;
            smtpMut.mutate(value);
          }}
        />
        {smtpTo?.uses_account_email && (
          <p className="text-xs text-gray-600 mt-1.5">Using your login email ({user?.email}).</p>
        )}
        {smtpTo?.override && (
          <p className="text-xs text-gray-600 mt-1.5">Override saved — digests go here instead.</p>
        )}
      </div>
      <div className="grid grid-cols-2 gap-3 mb-3">
        <div>
          <label className="block text-xs text-gray-500 mb-1.5">Morning preview time (UTC)</label>
          <input
            type="time"
            className="input"
            defaultValue={digestSettings.morning_time ?? "12:00"}
            onBlur={(e) => mut.mutate({ ...digestSettings, morning_time: e.target.value })}
          />
        </div>
        <div>
          <label className="block text-xs text-gray-500 mb-1.5">Evening recap time (UTC)</label>
          <input
            type="time"
            className="input"
            defaultValue={digestSettings.evening_time ?? "02:00"}
            onBlur={(e) => mut.mutate({ ...digestSettings, evening_time: e.target.value })}
          />
        </div>
      </div>
      <div className="flex items-center gap-3">
        <button
          onClick={() => testMut.guardedMutate()}
          disabled={testMut.actionDisabled}
          className="btn-ghost text-xs flex items-center gap-1.5"
        >
          <Send className="w-3.5 h-3.5" />
          {testMut.isPending
            ? "Sending…"
            : testMut.cooldownSecondsLeft > 0
              ? `Wait ${testMut.cooldownSecondsLeft}s`
              : "Send test morning email"}
        </button>
        {testResult && <span className="text-xs text-green-400">{testResult}</span>}
      </div>
    </div>
  );
}

function ToneSettings({ settings }: { settings: Record<string, unknown> | undefined }) {
  const qc = useQueryClient();
  const tone = (settings?.tone_preferences as any) ?? {};
  const mut = useMutation({
    mutationFn: (v: unknown) => updateSetting("tone_preferences", v),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["settings"] }),
  });

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
      <h2 className="text-sm font-semibold text-gray-200 mb-4">Voice & Tone</h2>
      <div className="space-y-3">
        <div>
          <label className="block text-xs text-gray-500 mb-1.5">Max emojis per post</label>
          <input
            type="number"
            className="input w-24"
            min={0}
            max={5}
            defaultValue={tone.emoji_max ?? 2}
            onBlur={(e) => mut.mutate({ ...tone, emoji_max: parseInt(e.target.value) })}
          />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs text-gray-500 mb-1.5">Min hashtags</label>
            <input
              type="number"
              className="input"
              min={1}
              max={10}
              defaultValue={tone.hashtag_min ?? 3}
              onBlur={(e) => mut.mutate({ ...tone, hashtag_min: parseInt(e.target.value) })}
            />
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1.5">Max hashtags</label>
            <input
              type="number"
              className="input"
              min={1}
              max={10}
              defaultValue={tone.hashtag_max ?? 5}
              onBlur={(e) => mut.mutate({ ...tone, hashtag_max: parseInt(e.target.value) })}
            />
          </div>
        </div>
      </div>
    </div>
  );
}

function SchedulerStatus({ tasks }: { tasks: { name: string; task: string; schedule: string }[] }) {
  const qc = useQueryClient();
  const trigMut = useGuardedMutation({
    mutationFn: triggerTask,
    cooldownSeconds: 30,
    successMessage: "Task queued.",
    onSuccess: () => qc.invalidateQueries({ queryKey: ["scheduler-status"] }),
  });

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
      <h2 className="text-sm font-semibold text-gray-200 mb-1">Scheduler Tasks</h2>
      <p className="text-xs text-gray-500 mb-4">
        Run a job now, or see when it runs automatically. Times are shown in Eastern Time.
      </p>
      <div className="space-y-2">
        {tasks.map((t) => (
          <div key={t.name} className="flex items-center justify-between py-2 border-b border-gray-800 last:border-0">
            <div>
              <p className="text-xs text-gray-300 font-medium">{formatTaskName(t.name)}</p>
              <p className="text-xs text-gray-500">{describeSchedule(t.name, t.schedule)}</p>
            </div>
            <button
              onClick={() => trigMut.guardedMutate(t.name.replace(/-/g, "_"))}
              disabled={trigMut.actionDisabled}
              className="btn-ghost text-xs flex items-center gap-1.5 py-1"
            >
              <Play className="w-3 h-3" />
              {trigMut.isPending ? "Running…" : "Run now"}
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}

function formatTaskName(name: string) {
  return name
    .split("-")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function describeSchedule(name: string, schedule: string) {
  const known: Record<string, string> = {
    "research-sweep-morning": "Every day at 8:00 AM",
    "research-sweep-evening": "Every day at 6:00 PM",
    "content-generation": "Every day at 9:00 PM",
    "queue-check": "Every 5 minutes",
    "engagement-sweep": "Every 4 hours",
    "metric-collection": "Every day at 11:00 PM",
    "daily-summary": "Every day at 8:30 PM",
    "morning-email": "Every day at 7:00 AM",
    "evening-email": "Every day at 9:00 PM",
    "weekly-report": "Every Sunday at 8:00 PM",
  };
  return known[name] ?? humanizeCron(schedule);
}

function humanizeCron(schedule: string) {
  const [minute, hour, dayOfMonth, month, dayOfWeek] = schedule.split(" ");
  if (schedule === "*/5 * * * *") return "Every 5 minutes";
  if (minute === "0" && hour?.startsWith("*/")) {
    return `Every ${hour.slice(2)} hours`;
  }
  if (dayOfMonth === "*" && month === "*" && dayOfWeek === "*") {
    return `Every day at ${formatUtcAsEastern(hour, minute)}`;
  }
  return "Custom schedule";
}

function formatUtcAsEastern(hour: string, minute: string) {
  const h = Number(hour);
  const m = Number(minute);
  if (!Number.isFinite(h) || !Number.isFinite(m)) return "a scheduled time";
  const date = new Date(Date.UTC(2026, 0, 1, h, m));
  return new Intl.DateTimeFormat("en-US", {
    hour: "numeric",
    minute: "2-digit",
    timeZone: "America/New_York",
  }).format(date);
}
