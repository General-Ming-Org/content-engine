import {
  addDays,
  addMinutes,
  differenceInMinutes,
  isSameDay,
  parseISO,
  startOfDay,
  startOfWeek,
} from "date-fns";
import type { Article, Post } from "../../lib/api";

export const CALENDAR_START_HOUR = 6;
export const CALENDAR_END_HOUR = 22;
export const SLOT_MINUTES = 30;
export const HOUR_HEIGHT_PX = 48;

export type CalendarEventKind = "post" | "article";

export interface CalendarEvent {
  id: string;
  kind: CalendarEventKind;
  title: string;
  subtitle?: string | null;
  status: string;
  start: Date;
  end: Date;
  allDay: boolean;
  post?: Post;
  article?: Article;
}

export function itemStartIso(item: {
  scheduled_at: string | null;
  published_at: string | null;
  queued_at: string | null;
  created_at?: string;
}) {
  return item.scheduled_at || item.published_at || item.queued_at || item.created_at || null;
}

export function postToEvent(post: Post): CalendarEvent | null {
  const raw = itemStartIso(post);
  if (!raw) return null;
  let start: Date;
  try {
    start = parseISO(raw);
  } catch {
    return null;
  }
  if (Number.isNaN(start.getTime())) return null;

  const hasTime =
    post.scheduled_at != null || post.published_at != null || /T\d{2}:\d{2}/.test(raw);
  const allDay = !hasTime;
  const end = addMinutes(start, post.linked_article_id ? 45 : 30);

  return {
    id: post.id,
    kind: "post",
    title: post.content.slice(0, 80) + (post.content.length > 80 ? "…" : ""),
    status: post.status,
    start: allDay ? startOfDay(start) : start,
    end: allDay ? addMinutes(startOfDay(start), 24 * 60 - 1) : end,
    allDay,
    post,
  };
}

export function articleToEvent(article: Article): CalendarEvent | null {
  const raw = itemStartIso(article);
  if (!raw) return null;
  let start: Date;
  try {
    start = parseISO(raw);
  } catch {
    return null;
  }
  if (Number.isNaN(start.getTime())) return null;

  const hasTime =
    article.scheduled_at != null ||
    article.published_at != null ||
    /T\d{2}:\d{2}/.test(raw);
  const allDay = !hasTime;
  const end = addMinutes(start, 60);

  return {
    id: article.id,
    kind: "article",
    title: article.title,
    subtitle: article.subtitle,
    status: article.status,
    start: allDay ? startOfDay(start) : start,
    end: allDay ? addMinutes(startOfDay(start), 24 * 60 - 1) : end,
    allDay,
    article,
  };
}

export function eventsInWeek(
  posts: Post[],
  articles: Article[],
  weekStart: Date,
): CalendarEvent[] {
  const end = addDays(weekStart, 7);
  const inRange = (d: Date) => d >= weekStart && d < end;
  const events: CalendarEvent[] = [];
  for (const p of posts) {
    const e = postToEvent(p);
    if (e && inRange(e.start)) events.push(e);
  }
  for (const a of articles) {
    const e = articleToEvent(a);
    if (e && inRange(e.start)) events.push(e);
  }
  return events.sort((a, b) => a.start.getTime() - b.start.getTime());
}

export function eventsForDay(events: CalendarEvent[], day: Date) {
  return events.filter((e) => isSameDay(e.start, day));
}

export function eventTopPx(start: Date, allDay: boolean): number {
  if (allDay) return 0;
  const minutesFromStart =
    (start.getHours() - CALENDAR_START_HOUR) * 60 + start.getMinutes();
  return Math.max(0, (minutesFromStart / 60) * HOUR_HEIGHT_PX);
}

export function eventHeightPx(start: Date, end: Date, allDay: boolean): number {
  if (allDay) return 0;
  const mins = Math.max(SLOT_MINUTES, differenceInMinutes(end, start));
  return Math.max(22, (mins / 60) * HOUR_HEIGHT_PX);
}

export function totalGridHeightPx(): number {
  return (CALENDAR_END_HOUR - CALENDAR_START_HOUR) * HOUR_HEIGHT_PX;
}

export function weekDays(weekStart: Date): Date[] {
  return Array.from({ length: 7 }, (_, i) => addDays(weekStart, i));
}

export function defaultWeekStart(): Date {
  return startOfWeek(new Date(), { weekStartsOn: 1 });
}

export const STATUS_COLORS: Record<string, { bg: string; border: string; text: string }> = {
  queued: {
    bg: "bg-amber-500/20",
    border: "border-amber-500/50",
    text: "text-amber-100",
  },
  scheduled: {
    bg: "bg-blue-500/20",
    border: "border-blue-500/50",
    text: "text-blue-100",
  },
  published: {
    bg: "bg-emerald-500/20",
    border: "border-emerald-500/50",
    text: "text-emerald-100",
  },
  failed: {
    bg: "bg-red-500/20",
    border: "border-red-500/50",
    text: "text-red-100",
  },
};
