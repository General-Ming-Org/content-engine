import { useEffect, useMemo, useRef } from "react";
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

function currentTimeTopPx(now: Date): number | null {
  const h = now.getHours();
  const m = now.getMinutes();
  if (h < CALENDAR_START_HOUR || h >= CALENDAR_END_HOUR) return null;
  return ((h - CALENDAR_START_HOUR) * 60 + m) / 60 * HOUR_HEIGHT_PX;
}

export function WeekTimeGrid({ weekStart, events, selectedId, onSelect }: WeekTimeGridProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const days = useMemo(() => weekDays(weekStart), [weekStart]);
  const gridHeight = totalGridHeightPx();
  const hours = useMemo(() => {
    const list: number[] = [];
    for (let h = CALENDAR_START_HOUR; h < CALENDAR_END_HOUR; h++) list.push(h);
    return list;
  }, []);

  const today = new Date();
  const nowTop = currentTimeTopPx(today);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el || nowTop == null) return;
    const target = Math.max(0, nowTop - el.clientHeight * 0.25);
    el.scrollTop = target;
  }, [weekStart, nowTop]);

  return (
    <div className="border border-[#3b3a39] rounded-lg bg-[#1b1a19] overflow-hidden flex flex-col min-h-[560px] shadow-sm">
      {/* Day headers */}
      <div className="grid grid-cols-[64px_repeat(7,1fr)] border-b border-[#3b3a39] bg-[#252423] sticky top-0 z-20">
        <div className="border-r border-[#3b3a39]" />
        {days.map((day) => {
          const isToday = isSameDay(day, today);
          return (
            <div
              key={day.toISOString()}
              className={clsx(
                "py-2.5 px-2 text-center border-r border-[#3b3a39] last:border-r-0",
                isToday && "bg-[#2d2c2c]",
              )}
            >
              <p className={clsx("text-[11px] font-normal", isToday ? "text-[#c8c6c4]" : "text-[#8a8886]")}>
                {format(day, "EEE")}
              </p>
              <p
                className={clsx(
                  "text-base font-semibold leading-tight mt-1 inline-flex items-center justify-center min-w-[28px] h-7 px-1 rounded-sm",
                  isToday ? "bg-[#6264a7] text-white" : "text-[#f3f2f1]",
                )}
              >
                {format(day, "d")}
              </p>
            </div>
          );
        })}
      </div>

      {/* All-day row */}
      <div className="grid grid-cols-[64px_repeat(7,1fr)] border-b border-[#3b3a39] min-h-[40px] bg-[#252423]/80">
        <div className="text-[11px] text-[#8a8886] px-2 py-2 border-r border-[#3b3a39] text-right leading-tight">
          All day
        </div>
        {days.map((day) => {
          const { allDay } = layoutDayEvents(eventsForDay(events, day));
          return (
            <div
              key={`allday-${day.toISOString()}`}
              className="border-r border-[#3b3a39] last:border-r-0 p-1 flex flex-col gap-1 min-h-[36px]"
            >
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
      <div ref={scrollRef} className="overflow-y-auto flex-1 max-h-[760px]">
        <div className="grid grid-cols-[64px_repeat(7,1fr)] relative" style={{ minHeight: gridHeight }}>
          {/* Time labels */}
          <div className="border-r border-[#3b3a39] relative bg-[#252423]/50" style={{ height: gridHeight }}>
            {hours.map((h) => (
              <div
                key={h}
                className="absolute right-2 text-[11px] text-[#8a8886] -translate-y-1/2 tabular-nums font-normal"
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
                  "relative border-r border-[#3b3a39] last:border-r-0",
                  isToday && "bg-[#6264a7]/[0.04]",
                )}
                style={{ height: gridHeight }}
              >
                {hours.map((h) => (
                  <div key={h}>
                    <div
                      className="absolute left-0 right-0 border-t border-[#3b3a39]"
                      style={{ top: (h - CALENDAR_START_HOUR) * HOUR_HEIGHT_PX }}
                    />
                    <div
                      className="absolute left-0 right-0 border-t border-dashed border-[#3b3a39]/60"
                      style={{ top: (h - CALENDAR_START_HOUR) * HOUR_HEIGHT_PX + HOUR_HEIGHT_PX / 2 }}
                    />
                  </div>
                ))}

                {isToday && nowTop != null && (
                  <div
                    className="absolute left-0 right-0 z-20 pointer-events-none flex items-center"
                    style={{ top: nowTop }}
                  >
                    <div className="w-2 h-2 rounded-full bg-[#c50f1f] -ml-1 flex-shrink-0" />
                    <div className="flex-1 h-[2px] bg-[#c50f1f]" />
                  </div>
                )}

                {timed.map((ev) => {
                  const pos = layout.get(ev.id) ?? { col: 0, cols: 1 };
                  const widthPct = 100 / pos.cols;
                  const leftPct = pos.col * widthPct;
                  const top = eventTopPx(ev.start, false);
                  const height = eventHeightPx(ev.start, ev.end, false);
                  if (top + height > gridHeight + 4) return null;
                  const colors = STATUS_COLORS[ev.status] ?? STATUS_COLORS.queued;

                  return (
                    <button
                      key={ev.id}
                      type="button"
                      onClick={() => onSelect(ev)}
                      className={clsx(
                        "absolute rounded-sm px-1.5 py-0.5 text-left overflow-hidden border border-l-[3px] text-[11px] leading-snug transition-shadow z-10",
                        colors.bg,
                        colors.border,
                        colors.text,
                        colors.accent,
                        selectedId === ev.id && "ring-2 ring-[#6264a7] ring-offset-0",
                        "hover:brightness-110 shadow-sm",
                      )}
                      style={{
                        top,
                        height,
                        left: `calc(${leftPct}% + 3px)`,
                        width: `calc(${widthPct}% - 6px)`,
                      }}
                      title={ev.title}
                    >
                      <span className="font-semibold block truncate">{format(ev.start, "h:mm a")}</span>
                      <span className="block truncate opacity-95">{ev.title}</span>
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
        "w-full text-left rounded-sm border border-l-[3px] px-1.5 py-0.5 truncate flex items-center gap-1",
        colors.bg,
        colors.border,
        colors.text,
        colors.accent,
        compact ? "text-[10px]" : "text-xs",
        selected && "ring-2 ring-[#6264a7]",
        "hover:brightness-110",
      )}
      title={event.title}
    >
      {event.kind === "post" ? (
        <Linkedin className="w-3 h-3 flex-shrink-0 text-[#4f6bed]" />
      ) : (
        <FileText className="w-3 h-3 flex-shrink-0 text-[#ca5010]" />
      )}
      <span className="truncate">{event.title}</span>
    </button>
  );
}
