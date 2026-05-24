import { useCallback, useEffect, useRef, useState } from "react";
import { useToast } from "../components/ToastProvider";
import { formatCooldownMessage, getApiErrorMessage, getRetryAfterSeconds } from "../lib/apiErrors";

export interface UseAsyncActionOptions {
  successMessage?: string;
  /** Applied immediately on click (before the request finishes). */
  cooldownSeconds?: number;
  storageKey?: string;
  onSuccess?: () => void;
  onError?: (message: string) => void;
}

function readStoredCooldown(key: string): number {
  try {
    const raw = sessionStorage.getItem(key);
    if (!raw) return 0;
    const until = parseInt(raw, 10);
    return Number.isFinite(until) ? until : 0;
  } catch {
    return 0;
  }
}

function writeStoredCooldown(key: string, untilMs: number) {
  try {
    sessionStorage.setItem(key, String(untilMs));
  } catch {
    /* ignore */
  }
}

function clearStoredCooldown(key: string) {
  try {
    sessionStorage.removeItem(key);
  } catch {
    /* ignore */
  }
}

/**
 * Guards async user actions: blocks double-clicks, enforces cooldowns (sync via ref),
 * and always surfaces blocked / error / success states via toast.
 */
export function useAsyncAction<T extends unknown[]>(
  action: (...args: T) => Promise<void>,
  options: UseAsyncActionOptions = {},
) {
  const toast = useToast();
  const inFlightRef = useRef(false);
  const cooldownUntilRef = useRef(
    options.storageKey ? readStoredCooldown(options.storageKey) : 0,
  );
  const [running, setRunning] = useState(false);
  const [cooldownUntil, setCooldownUntil] = useState(cooldownUntilRef.current);
  const [, setTick] = useState(0);

  const cooldownSecondsLeft = Math.max(0, Math.ceil((cooldownUntilRef.current - Date.now()) / 1000));

  useEffect(() => {
    if (cooldownUntilRef.current <= Date.now()) return;
    const timer = window.setInterval(() => {
      if (Date.now() >= cooldownUntilRef.current) {
        cooldownUntilRef.current = 0;
        setCooldownUntil(0);
        if (options.storageKey) clearStoredCooldown(options.storageKey);
      }
      setTick((t) => t + 1);
    }, 500);
    return () => window.clearInterval(timer);
  }, [cooldownUntil, options.storageKey]);

  const applyCooldown = useCallback(
    (seconds: number) => {
      if (seconds <= 0) return;
      const until = Date.now() + seconds * 1000;
      cooldownUntilRef.current = until;
      setCooldownUntil(until);
      if (options.storageKey) writeStoredCooldown(options.storageKey, until);
    },
    [options.storageKey],
  );

  const isOnCooldown = useCallback(() => cooldownUntilRef.current > Date.now(), []);

  const run = useCallback(
    async (...args: T) => {
      if (isOnCooldown()) {
        const left = Math.max(1, Math.ceil((cooldownUntilRef.current - Date.now()) / 1000));
        toast.error(formatCooldownMessage(left));
        return;
      }
      if (inFlightRef.current) {
        toast.info("Please wait — that request is already in progress.");
        return;
      }

      inFlightRef.current = true;
      setRunning(true);

      // Lock immediately so rapid clicks after the first response cannot spam.
      const defaultCd = options.cooldownSeconds ?? 0;
      if (defaultCd > 0) applyCooldown(defaultCd);

      try {
        await action(...args);
        if (options.successMessage) toast.success(options.successMessage);
        options.onSuccess?.();
      } catch (err) {
        const retrySec = getRetryAfterSeconds(err);
        if (retrySec != null) applyCooldown(retrySec);
        else if (defaultCd > 0) applyCooldown(defaultCd);

        const message = getApiErrorMessage(err);
        toast.error(message);
        options.onError?.(message);
      } finally {
        inFlightRef.current = false;
        setRunning(false);
      }
    },
    [action, applyCooldown, cooldownSecondsLeft, isOnCooldown, options, toast],
  );

  return {
    run,
    running,
    disabled: running || isOnCooldown(),
    cooldownSecondsLeft,
  };
}
