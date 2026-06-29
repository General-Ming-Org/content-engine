import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { format } from "date-fns";
import { AlertCircle, Info, CheckCheck, Bell, X } from "lucide-react";
import { getNotifications, markRead, markAllRead, dismissNotification, type Notification } from "../lib/api";

export default function Notifications() {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ["notifications"],
    queryFn: () => getNotifications(),
  });

  const markAllMut = useMutation({
    mutationFn: markAllRead,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["notifications"] });
      qc.invalidateQueries({ queryKey: ["notifications", "unread-count"] });
    },
  });

  const markOneMut = useMutation({
    mutationFn: markRead,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["notifications", "unread-count"] }),
  });

  const dismissMut = useMutation({
    mutationFn: dismissNotification,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["notifications"] });
      qc.invalidateQueries({ queryKey: ["notifications", "unread-count"] });
    },
  });

  const notifications = data?.notifications ?? [];
  const unread = notifications.filter((n) => !n.is_read).length;

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="text-xl font-semibold text-gray-100">Notifications</h1>
          {unread > 0 && <p className="text-sm text-gray-500 mt-0.5">{unread} unread</p>}
        </div>
        {unread > 0 && (
          <button
            onClick={() => markAllMut.mutate()}
            className="btn-ghost flex items-center gap-2 text-sm"
          >
            <CheckCheck className="w-4 h-4" />
            Mark all read
          </button>
        )}
      </div>

      {isLoading ? (
        <div className="space-y-2">
          {[...Array(4)].map((_, i) => <div key={i} className="h-16 bg-gray-900 rounded-xl animate-pulse" />)}
        </div>
      ) : notifications.length === 0 ? (
        <div className="text-center py-16">
          <Bell className="w-8 h-8 text-gray-700 mx-auto mb-3" />
          <p className="text-gray-500">No notifications yet.</p>
        </div>
      ) : (
        <div className="space-y-2">
          {notifications.map((n) => (
            <NotificationRow
              key={n.id}
              notification={n}
              onRead={() => markOneMut.mutate(n.id)}
              onDismiss={() => dismissMut.mutate(n.id)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function NotificationRow({
  notification: n,
  onRead,
  onDismiss,
}: {
  notification: Notification;
  onRead: () => void;
  onDismiss: () => void;
}) {
  return (
    <div
      className={`flex items-start gap-3 p-4 rounded-xl border transition-colors ${
        n.is_read
          ? "bg-gray-900 border-gray-800 opacity-60"
          : "bg-gray-900 border-gray-800 hover:border-gray-700"
      }`}
    >
      <button
        type="button"
        className={`mt-0.5 flex-shrink-0 ${n.type === "error" ? "text-red-400" : "text-gray-500"}`}
        onClick={() => !n.is_read && onRead()}
        aria-label={n.is_read ? "Read notification" : "Mark as read"}
      >
        {n.type === "error" ? <AlertCircle className="w-4 h-4" /> : <Info className="w-4 h-4" />}
      </button>
      <button
        type="button"
        className="flex-1 min-w-0 text-left"
        onClick={() => !n.is_read && onRead()}
      >
        <div className="flex items-center justify-between gap-2">
          <p className={`text-sm font-medium ${n.is_read ? "text-gray-500" : "text-gray-100"}`}>
            {n.title}
          </p>
          <span className="text-xs text-gray-600 flex-shrink-0 tabular-nums">
            {format(new Date(n.created_at), "MMM d, yyyy · h:mm a")}
          </span>
        </div>
        <p className="text-xs text-gray-500 mt-0.5">{n.message}</p>
      </button>
      {!n.is_read && (
        <div className="w-2 h-2 rounded-full bg-accent flex-shrink-0 mt-1.5" />
      )}
      <button
        type="button"
        onClick={onDismiss}
        className="btn-ghost p-1.5 -mr-1 flex-shrink-0"
        aria-label="Dismiss notification"
      >
        <X className="w-4 h-4 text-gray-500" />
      </button>
    </div>
  );
}
