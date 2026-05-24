import { format } from "date-fns";
import { FileText, Linkedin, Loader2, X } from "lucide-react";
import clsx from "clsx";
import type { CalendarEvent } from "./calendarUtils";
import { STATUS_COLORS } from "./calendarUtils";
import { getPublishReadiness } from "../../lib/formActions";
import { ActionButton } from "../ActionButton";

export interface EventDetailPanelProps {
  event: CalendarEvent | null;
  onClose: () => void;
  onPublish: () => void;
  onCancel: () => void;
  actionBusy: boolean;
  linkedInAppConfigured: boolean;
  linkedInAccountConnected: boolean;
  substackConnected: boolean;
}

export function EventDetailPanel({
  event,
  onClose,
  onPublish,
  onCancel,
  actionBusy,
  linkedInAppConfigured,
  linkedInAccountConnected,
  substackConnected,
}: EventDetailPanelProps) {
  if (!event) return null;

  const colors = STATUS_COLORS[event.status] ?? STATUS_COLORS.queued;
  const isPost = event.kind === "post";
  const platform = isPost ? "linkedin" : "substack";

  const readiness = getPublishReadiness(
    platform,
    event.status,
    actionBusy,
    linkedInAppConfigured,
    linkedInAccountConnected,
    substackConnected,
  );

  const showActions = event.status === "queued";

  return (
    <aside
      className="w-full lg:w-[360px] flex-shrink-0 bg-gray-900 border border-gray-800 rounded-xl flex flex-col max-h-[calc(100vh-8rem)] lg:sticky lg:top-4"
      aria-label="Event details"
    >
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-800">
        <div className="flex items-center gap-2 min-w-0">
          {isPost ? (
            <Linkedin className="w-4 h-4 text-blue-400 flex-shrink-0" />
          ) : (
            <FileText className="w-4 h-4 text-orange-400 flex-shrink-0" />
          )}
          <span className="text-sm font-medium text-gray-200 truncate">
            {isPost ? "LinkedIn post" : "Substack article"}
          </span>
        </div>
        <button type="button" onClick={onClose} className="btn-ghost p-1.5" aria-label="Close">
          <X className="w-4 h-4" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        <div className="flex flex-wrap items-center gap-2">
          <span
            className={clsx(
              "text-xs font-medium px-2 py-0.5 rounded border capitalize",
              colors.bg,
              colors.border,
              colors.text,
            )}
          >
            {event.status}
          </span>
          <span className="text-xs text-gray-500">
            {format(event.start, event.allDay ? "EEE, MMM d" : "EEE, MMM d · h:mm a")}
          </span>
        </div>

        {isPost && event.post ? (
          <p className="text-sm text-gray-100 whitespace-pre-wrap leading-relaxed">{event.post.content}</p>
        ) : (
          <>
            <h2 className="text-base font-semibold text-gray-100">{event.title}</h2>
            {event.subtitle && <p className="text-sm text-gray-400">{event.subtitle}</p>}
          </>
        )}

        {event.status === "failed" && (
          <p className="text-sm text-red-400/90">
            {isPost
              ? "Publishing failed. Finish LinkedIn setup in Settings, then try again."
              : "Publishing failed. Check Substack credentials in Settings."}
          </p>
        )}

        {showActions && readiness.publishBlockedReason && !actionBusy && (
          <p className="text-sm text-amber-400/90">{readiness.publishBlockedReason}</p>
        )}
      </div>

      {showActions && (
        <div className="p-4 border-t border-gray-800 flex flex-col gap-2">
          {actionBusy ? (
            <div className="flex items-center justify-center gap-2 py-2 text-sm text-gray-400">
              <Loader2 className="w-4 h-4 animate-spin" />
              Working…
            </div>
          ) : (
            <>
              <ActionButton
                variant="primary"
                className="w-full justify-center"
                disabled={!readiness.canPublish}
                title={readiness.publishBlockedReason ?? undefined}
                onClick={onPublish}
              >
                Publish now
              </ActionButton>
              <ActionButton
                variant="ghost"
                className="w-full border border-gray-700 text-gray-300"
                disabled={!readiness.canCancel}
                onClick={onCancel}
              >
                Remove from queue
              </ActionButton>
            </>
          )}
        </div>
      )}
    </aside>
  );
}
