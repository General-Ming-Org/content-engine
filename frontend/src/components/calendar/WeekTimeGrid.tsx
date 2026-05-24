import { useMemo } from "react";
import { format, isSameDay } from "date-fns";
import clsx from "clsx";
import { FileText, Linkedin } from "lucide-react";
import {
  CALENDAR_END_HOUR,
  CALENDAR_START_HOUR,
  HOUR_HEIGHT_PX,
  STATUS_COLORS,
  eventHeightPx,
  eventTopPx,
  eventsForDay,
  totalGridHeightPx,
  weekDays,
  type CalendarEvent,
} from "./calendarUtils";

interface WeekTimeGridProps {
  weekStart: Date;
  events: CalendarEvent[];
  selectedId: string | null;
  onSelect: (event: CalendarEvent) => void;
}

function layoutDayEvents(dayEvents: CalendarEvent[]) {
  const timed = dayEvents.filter((e) => !e.allDay).sort((a, b) => a.start.getTime() - b.start.getTime());
  const columns: CalendarEvent[][] = [];

  for (const ev of timed) {
    let placed = false;
    for (const col of columns) {
      const last = col[col.length - 1];
      if (last.end <= ev.start) {
        col.push(ev);
        placed = true;
        break;
      }
    }
    if (!placed) columns.push([ev]);
  }

  const layout = new Map<string, { col: number; cols: number }>();
  timed.forEach((ev) => {
    const colIndex = columns.findIndex((c) => c.includes(ev));
    layout.set(ev.id, { col: colIndex, cols: columns.length });
  });
  return { allDay: dayEvents.filter((e) => e.allDay), timed, layout };
}

export function WeekTimeGrid({ weekStart, events, selectedId, onSelect }: WeekTimeGridProps) {
  const days = useMemo(() => weekDays(weekStart), [weekStart]);
  const gridHeight = totalGridHeightPx();
  const hours = useMemo(() => {
    const list: number[] = [];
    for (let h = CALENDAR_START_HOUR; h < CALENDAR_END_HOUR; h++) list.push(h);
    return list;
  }, []);

  const today = new Date();

  return (
    <div className="border border-gray-800 rounded-xl bg-gray-950 overflow-hidden flex flex-col min-h-[520px]">
      {/* Day headers */}
      <div className="grid grid-cols-[56px_repeat(7,1fr)] border-b border-gray-800 bg-gray-900/80 sticky top-0 z-20">
        <div className="border-r border-gray-800" />
        {days.map((day) => {
          const isToday = isSameDay(day, today);
          return (
            <div
              key={day.toISOString()}
              className={clsx(
                "py-2 px-2 text-center border-r border-gray-800 last:border-r-0",
                isToday && "bg-accent/10",
              )}
            >
              <p className={clsx("text-[10px] uppercase tracking-wide font-semibold", isToday ? "text-accent" : "text-gray-500")}>
                {format(day, "EEE")}
              </p>
              <p
                className={clsx(
                  "text-lg font-semibold leading-tight mt-0.5 inline-flex items-center justify-center w-8 h-8 rounded-full",
                  isToday ? "bg-accent text-white" : "text-gray-100",
                )}
              >
                {format(day, "d")}
              </p>
            </div>
          );
        })}
      </div>

      {/* All-day row */}
      <div className="grid grid-cols-[56px_repeat(7,1fr)] border-b border-gray-800 min-h-[36px] bg-gray-900/40">
        <div className="text-[10px] text-gray-600 px-1 py-2 border-r border-gray-800 text-right leading-tight">
          All day
        </div>
        {days.map((day) => {
          const { allDay } = layoutDayEvents(eventsForDay(events, day));
          return (
            <div key={`allday-${day.toISOString()}`} className="border-r border-gray-800 last:border-r-0 p-0.5 flex flex-col gap-0.5 min-h-[32px]">
              {allDay.map((ev) => (
                <EventChip
                  key={ev.id}
                  event={ev}
                  selected={selectedId === ev.id}
                  onSelect={() => onSelect(ev)}
                  compact
                />
              ))}
            </div>
          );
        })}
      </div>

      {/* Scrollable time grid */}
      <div className="overflow-y-auto flex-1 max-h-[720px]">
        <div className="grid grid-cols-[56px_repeat(7,1fr)] relative" style={{ minHeight: gridHeight }}>
          {/* Time labels */}
          <div className="border-r border-gray-800 relative" style={{ height: gridHeight }}>
            {hours.map((h) => (
              <div
                key={h}
                className="absolute right-1 text-[10px] text-gray-600 -translate-y-1/2 tabular-nums"
                style={{ top: (h - CALENDAR_START_HOUR) * HOUR_HEIGHT_PX }}
              >
                {format(new Date(2000, 0, 1, h), "h a")}
              </div>
            ))}
          </div>

          {/* Day columns */}
          {days.map((day) => {
            const dayEvents = eventsForDay(events, day);
            const { timed, layout } = layoutDayEvents(dayEvents);
            const isToday = isSameDay(day, today);

            return (
              <div
                key={day.toISOString()}
                className={clsx(
                  "relative border-r border-gray-800 last:border-r-0",
                  isToday && "bg-accent/[0.03]",
                )}
                style={{ height: gridHeight }}
              >
                {hours.map((h) => (
                  <div
                    key={h}
                    className="absolute left-0 right-0 border-t border-gray-800/80"
                    style={{ top: (h - CALENDAR_START_HOUR) * HOUR_HEIGHT_PX }}
                  />
                ))}
                {timed.map((ev) => {
                  const pos = layout.get(ev.id) ?? { col: 0, cols: 1 };
                  const widthPct = 100 / pos.cols;
                  const leftPct = pos.col * widthPct;
                  const top = eventTopPx(ev.start, false);
                  const height = eventHeightPx(ev.start, ev.end, false);
                  if (top + height > gridHeight + 4) return null;

                  return (
                    <button
                      key={ev.id}
                      type="button"
                      onClick={() => onSelect(ev)}
                      className={clsx(
                        "absolute rounded px-1 py-0.5 text-left overflow-hidden border text-[11px] leading-tight transition-shadow z-10",
                        (STATUS_COLORS[ev.status] ?? STATUS_COLORS.queued).bg,
                        (STATUS_COLORS[ev.status] ?? STATUS_COLORS.queued).border,
                        (STATUS_COLORS[ev.status] ?? STATUS_COLORS.queued).text,
                        selectedId === ev.id && "ring-2 ring-accent ring-offset-1 ring-offset-gray-950",
                        "hover:brightness-110",
                      )}
                      style={{
                        top,
                        height,
                        left: `calc(${leftPct}% + 2px)`,
                        width: `calc(${widthPct}% - 4px)`,
                      }}
                      title={ev.title}
                    >
                      <span className="font-medium block truncate">{format(ev.start, "h:mm a")}</span>
                      <span className="block truncate opacity-90">{ev.title}</span>
                    </button>
                  );
                })}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function EventChip({
  event,
  selected,
  onSelect,
  compact,
}: {
  event: CalendarEvent;
  selected: boolean;
  onSelect: () => void;
  compact?: boolean;
}) {
  const colors = STATUS_COLORS[event.status] ?? STATUS_COLORS.queued;
  return (
    <button
      type="button"
      onClick={onSelect}
      className={clsx(
        "w-full text-left rounded border px-1.5 py-0.5 truncate flex items-center gap-1",
        colors.bg,
        colors.border,
        colors.text,
        compact ? "text-[10px]" : "text-xs",
        selected && "ring-2 ring-accent",
        "hover:brightness-110",
      )}
      title={event.title}
    >
      {event.kind === "post" ? (
        <Linkedin className="w-3 h-3 flex-shrink-0 text-blue-400" />
      ) : (
        <FileText className="w-3 h-3 flex-shrink-0 text-orange-400" />
      )}
      <span className="truncate">{event.title}</span>
    </button>
  );
}
