import { ApiError } from "./api";

/** Human-readable message for any failed API call (for toasts and inline errors). */
export function getApiErrorMessage(err: unknown, fallback = "Something went wrong. Please try again."): string {
  if (err instanceof ApiError) {
    if (err.status === 0) {
      return "Can't reach the server. Check your connection and try again.";
    }
    return err.message || fallback;
  }
  if (err instanceof Error && err.message && err.message !== "__in_flight__") {
    return err.message;
  }
  return fallback;
}

export function getRetryAfterSeconds(err: unknown): number | null {
  if (err instanceof ApiError && err.retryAfterSeconds != null) {
    return err.retryAfterSeconds;
  }
  return null;
}

export function formatCooldownMessage(seconds: number): string {
  if (seconds <= 1) return "Please wait a moment before trying again.";
  if (seconds < 60) return `Please wait ${seconds}s before trying again.`;
  const mins = Math.ceil(seconds / 60);
  return `Please wait ${mins} minute${mins === 1 ? "" : "s"} before trying again.`;
}
