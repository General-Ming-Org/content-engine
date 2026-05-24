import { useCallback, useRef, useState } from "react";
import { useToast } from "../components/ToastProvider";
import { formatCooldownMessage, getApiErrorMessage, getRetryAfterSeconds } from "../lib/apiErrors";

export interface UseItemActionOptions {
  loadingMessage: string;
  successMessage: string;
  errorMessage?: (error: unknown) => string;
  cooldownSeconds?: number;
  onSuccess?: () => void;
}

/**
 * Per-item async guard: only one in-flight action per id; toasts for loading/success/error.
 */
export function useItemAction<TId extends string>(
  action: (id: TId) => Promise<unknown>,
  options: UseItemActionOptions,
) {
  const toast = useToast();
  const lockedRef = useRef<Set<string>>(new Set());
  const [lockedIds, setLockedIds] = useState<Set<string>>(() => new Set());
  const cooldownRef = useRef<Map<string, number>>(new Map());

  const isLocked = useCallback((id: TId) => lockedIds.has(id), [lockedIds]);

  const cooldownLeft = useCallback((id: TId) => {
    const until = cooldownRef.current.get(id) ?? 0;
    return Math.max(0, Math.ceil((until - Date.now()) / 1000));
  }, []);

  const lock = useCallback((id: string) => {
    lockedRef.current.add(id);
    setLockedIds(new Set(lockedRef.current));
  }, []);

  const unlock = useCallback((id: string) => {
    lockedRef.current.delete(id);
    setLockedIds(new Set(lockedRef.current));
  }, []);

  const run = useCallback(
    async (id: TId) => {
      if (lockedRef.current.has(id)) {
        toast.info("Please wait — this item is already being updated.");
        return;
      }
      const cd = cooldownRef.current.get(id) ?? 0;
      if (cd > Date.now()) {
        toast.error(formatCooldownMessage(cooldownLeft(id)));
        return;
      }

      lock(id);
      toast.info(options.loadingMessage);

      try {
        await action(id);
        toast.success(options.successMessage);
        options.onSuccess?.();
        if (options.cooldownSeconds && options.cooldownSeconds > 0) {
          cooldownRef.current.set(id, Date.now() + options.cooldownSeconds * 1000);
        }
      } catch (error) {
        const retry = getRetryAfterSeconds(error);
        if (retry != null) {
          cooldownRef.current.set(id, Date.now() + retry * 1000);
        } else if (options.cooldownSeconds) {
          cooldownRef.current.set(id, Date.now() + options.cooldownSeconds * 1000);
        }
        toast.error(
          options.errorMessage ? options.errorMessage(error) : getApiErrorMessage(error),
        );
      } finally {
        unlock(id);
      }
    },
    [action, cooldownLeft, lock, options, toast, unlock],
  );

  return { run, isLocked, cooldownLeft };
}
