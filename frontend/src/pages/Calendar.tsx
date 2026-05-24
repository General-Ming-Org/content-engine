import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { addDays, format } from "date-fns";
import { getCalendar } from "../lib/api";
import { usePublishActions } from "../hooks/usePublishActions";
import { WeekTimeGrid } from "../components/calendar/WeekTimeGrid";
import { EventDetailPanel } from "../components/calendar/EventDetailPanel";
import {
  defaultWeekStart,
  eventsInWeek,
  type CalendarEvent,
} from "../components/calendar/calendarUtils";

export default function Calendar() {
  const qc = useQueryClient();
  const [weekStart, setWeekStart] = useState(defaultWeekStart);
  const [selected, setSelected] = useState<CalendarEvent | null>(null);

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["calendar"],
    queryFn: () => getCalendar("week"),
  });

  const posts = data?.posts ?? [];
  const articles = data?.articles ?? [];

  const events = useMemo(
    () => eventsInWeek(posts, articles, weekStart),
    [posts, articles, weekStart],
  );

  const publish = usePublishActions({
    onInvalidate: () => {
      qc.invalidateQueries({ queryKey: ["calendar"] });
      setSelected(null);
    },
  });

  const selectedBusy = selected
    ? selected.kind === "post"
      ? publish.isPostBusy(selected.id)
      : publish.isArticleBusy(selected.id)
    : false;

  function handlePublish() {
    if (!selected) return;
    if (selected.kind === "post") publish.publishPost(selected.id);
    else publish.publishArticle(selected.id);
  }

  function handleCancel() {
    if (!selected) return;
    if (selected.kind === "post") publish.cancelPost(selected.id);
    else publish.cancelArticle(selected.id);
  }

  return (
    <div className="max-w-[1800px]">
      <div className="page-header flex-wrap gap-4">
        <div>
          <h1 className="text-xl font-semibold text-gray-100">Calendar</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            Week view · click an event for details and actions
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <button type="button" onClick={() => setWeekStart(defaultWeekStart())} className="btn-ghost">
            Today
          </button>
          <button type="button" onClick={() => setWeekStart((w) => addDays(w, -7))} className="btn-ghost">
            ←
          </button>
          <span className="text-sm text-gray-300 min-w-[200px] text-center tabular-nums">
            {format(weekStart, "MMM d")} – {format(addDays(weekStart, 6), "MMM d, yyyy")}
          </span>
          <button type="button" onClick={() => setWeekStart((w) => addDays(w, 7))} className="btn-ghost">
            →
          </button>
        </div>
      </div>

      <div className="flex flex-wrap gap-2 mb-4 text-xs text-gray-500">
        <LegendDot className="bg-amber-500/40 border-amber-500/60" label="Queued" />
        <LegendDot className="bg-blue-500/40 border-blue-500/60" label="Scheduled" />
        <LegendDot className="bg-emerald-500/40 border-emerald-500/60" label="Published" />
        <LegendDot className="bg-red-500/40 border-red-500/60" label="Failed" />
      </div>

      {isError && (
        <div className="mb-4 p-4 rounded-xl border border-red-800/50 bg-red-950/30 text-sm text-red-200">
          Could not load calendar.{" "}
          <button type="button" onClick={() => void refetch()} className="underline hover:no-underline">
            Retry
          </button>
        </div>
      )}

      <div className="flex flex-col lg:flex-row gap-4">
        <div className="flex-1 min-w-0">
          {isLoading ? (
            <div className="border border-gray-800 rounded-xl bg-gray-900 animate-pulse min-h-[520px]" />
          ) : (
            <WeekTimeGrid
              weekStart={weekStart}
              events={events}
              selectedId={selected?.id ?? null}
              onSelect={setSelected}
            />
          )}
          {!isLoading && events.length === 0 && (
            <p className="text-sm text-gray-500 mt-3 text-center">
              No content this week. Generate posts from Research or check other weeks.
            </p>
          )}
        </div>

        <EventDetailPanel
          event={selected}
          onClose={() => setSelected(null)}
          onPublish={handlePublish}
          onCancel={handleCancel}
          actionBusy={selectedBusy}
          linkedInAppConfigured={publish.linkedInAppConfigured}
          linkedInAccountConnected={publish.linkedInAccountConnected}
          substackConnected={publish.substackConnected}
        />
      </div>
    </div>
  );
}

function LegendDot({ className, label }: { className: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className={`w-2.5 h-2.5 rounded-sm border ${className}`} />
      {label}
    </span>
  );
}
