import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { AlertCircle, CheckCircle2, Info, X } from "lucide-react";
import clsx from "clsx";

export type ToastType = "success" | "error" | "info";

interface ToastItem {
  id: string;
  type: ToastType;
  message: string;
}

interface ToastContextValue {
  success: (message: string) => void;
  error: (message: string) => void;
  info: (message: string) => void;
  dismissAll: () => void;
}

const ToastCtx = createContext<ToastContextValue | null>(null);

const ICONS = {
  success: CheckCircle2,
  error: AlertCircle,
  info: Info,
} as const;

const STYLES = {
  success: "border-green-800/50 bg-green-950/90 text-green-100",
  error: "border-red-800/50 bg-red-950/90 text-red-100",
  info: "border-gray-700 bg-gray-900/95 text-gray-100",
} as const;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  const dismiss = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const push = useCallback((type: ToastType, message: string) => {
    const id = crypto.randomUUID();
    setToasts((prev) => [...prev, { id, type, message }]);
    window.setTimeout(() => dismiss(id), 6000);
  }, [dismiss]);

  const dismissAll = useCallback(() => setToasts([]), []);

  const value = useMemo<ToastContextValue>(
    () => ({
      success: (message) => push("success", message),
      error: (message) => push("error", message),
      info: (message) => push("info", message),
      dismissAll,
    }),
    [dismissAll, push],
  );

  return (
    <ToastCtx.Provider value={value}>
      {children}
      <div
        className="fixed bottom-4 right-4 z-[9999] flex flex-col gap-2 max-w-sm w-full pointer-events-none"
        aria-live="polite"
        aria-relevant="additions"
      >
        {toasts.map((t) => {
          const Icon = ICONS[t.type];
          return (
            <div
              key={t.id}
              role="alert"
              className={clsx(
                "pointer-events-auto flex items-start gap-2.5 rounded-lg border px-4 py-3 shadow-lg text-sm",
                STYLES[t.type],
              )}
            >
              <Icon className="w-4 h-4 flex-shrink-0 mt-0.5 opacity-90" aria-hidden />
              <p className="flex-1 min-w-0 leading-snug">{t.message}</p>
              <button
                type="button"
                onClick={() => dismiss(t.id)}
                className="flex-shrink-0 opacity-60 hover:opacity-100 transition-opacity"
                aria-label="Dismiss"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          );
        })}
      </div>
    </ToastCtx.Provider>
  );
}

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastCtx);
  if (!ctx) throw new Error("useToast must be used inside <ToastProvider>");
  return ctx;
}
