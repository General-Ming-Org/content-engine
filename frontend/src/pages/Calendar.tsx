import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { addDays, format } from "date-fns";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { getCalendar } from "../lib/api";
import { usePublishActions } from "../hooks/usePublishActions";
import { WeekTimeGrid } from "../components/calendar/WeekTimeGrid";
import { EventDetailPanel } from "../components/calendar/EventDetailPanel";
import {
  defaultWeekStart,
  eventsInWeek,
  STATUS_COLORS,
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

  const weekLabel = `${format(weekStart, "MMM d")} – ${format(addDays(weekStart, 6), "MMM d, yyyy")}`;

  return (
    <div className="max-w-[1800px]">
      <div className="page-header mb-3">
        <div>
          <h1 className="text-xl font-semibold text-[#f3f2f1]">Calendar</h1>
          <p className="text-sm text-[#8a8886] mt-0.5">
            {events.length} event{events.length === 1 ? "" : "s"} this week · click an event for details
          </p>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2 mb-3 p-2 rounded-lg border border-[#3b3a39] bg-[#252423]">
        <button
          type="button"
          onClick={() => setWeekStart(defaultWeekStart())}
          className="px-3 py-1.5 text-sm font-medium rounded border border-[#605e5c] text-[#f3f2f1] hover:bg-[#323130] transition-colors"
        >
          Today
        </button>
        <div className="flex items-center rounded border border-[#605e5c] overflow-hidden">
          <button
            type="button"
            onClick={() => setWeekStart((w) => addDays(w, -7))}
            className="p-2 hover:bg-[#323130] text-[#c8c6c4] transition-colors"
            aria-label="Previous week"
          >
            <ChevronLeft className="w-4 h-4" />
          </button>
          <button
            type="button"
            onClick={() => setWeekStart((w) => addDays(w, 7))}
            className="p-2 hover:bg-[#323130] text-[#c8c6c4] border-l border-[#605e5c] transition-colors"
            aria-label="Next week"
          >
            <ChevronRight className="w-4 h-4" />
          </button>
        </div>
        <h2 className="text-sm font-semibold text-[#f3f2f1] px-1 tabular-nums">{weekLabel}</h2>
        <span className="ml-auto text-xs font-medium text-[#c8c6c4] bg-[#323130] border border-[#605e5c] rounded px-2.5 py-1">
          Week
        </span>
      </div>

      <div className="flex flex-wrap gap-3 mb-3 text-[11px] text-[#8a8886]">
        {(["queued", "scheduled", "published", "failed"] as const).map((s) => (
          <span key={s} className="flex items-center gap-1.5 capitalize">
            <span
              className={`w-2.5 h-2.5 rounded-sm border-l-[3px] ${STATUS_COLORS[s].bg} ${STATUS_COLORS[s].accent} border border-[#3b3a39]`}
            />
            {s}
          </span>
        ))}
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
            <div className="border border-[#3b3a39] rounded-lg bg-[#252423] animate-pulse min-h-[560px]" />
          ) : (
            <WeekTimeGrid
              weekStart={weekStart}
              events={events}
              selectedId={selected?.id ?? null}
              onSelect={setSelected}
            />
          )}
          {!isLoading && events.length === 0 && (
            <p className="text-sm text-[#8a8886] mt-3 text-center">
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
