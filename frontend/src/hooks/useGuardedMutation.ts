import { useCallback, useEffect, useRef, useState } from "react";
import {
  useMutation,
  type UseMutationOptions,
  type UseMutationResult,
} from "@tanstack/react-query";
import { useToast } from "../components/ToastProvider";
import { formatCooldownMessage, getApiErrorMessage, getRetryAfterSeconds } from "../lib/apiErrors";

export interface GuardedMutationMeta {
  successMessage?: string;
  /** Applied on click before the request completes. */
  cooldownSeconds?: number;
  useRetryAfter?: boolean;
  errorMessage?: (error: unknown) => string;
}

type GuardedOptions<TData, TError, TVariables, TContext> = UseMutationOptions<
  TData,
  TError,
  TVariables,
  TContext
> &
  GuardedMutationMeta;

export function useGuardedMutation<
  TData = unknown,
  TError = Error,
  TVariables = void,
  TContext = unknown,
>(
  options: GuardedOptions<TData, TError, TVariables, TContext>,
): UseMutationResult<TData, TError, TVariables, TContext> & {
  guardedMutate: (variables?: TVariables) => void;
  actionDisabled: boolean;
  cooldownSecondsLeft: number;
} {
  const toast = useToast();
  const inFlightRef = useRef(false);
  const cooldownUntilRef = useRef(0);
  const [cooldownUntil, setCooldownUntil] = useState(0);

  const {
    successMessage,
    cooldownSeconds = 0,
    useRetryAfter = true,
    errorMessage,
    onSuccess,
    onError,
    onSettled,
    ...mutationOptions
  } = options;

  const cooldownSecondsLeft = Math.max(0, Math.ceil((cooldownUntilRef.current - Date.now()) / 1000));

  useEffect(() => {
    if (cooldownUntilRef.current <= Date.now()) return;
    const t = window.setTimeout(() => {
      cooldownUntilRef.current = 0;
      setCooldownUntil(0);
    }, cooldownUntilRef.current - Date.now());
    return () => window.clearTimeout(t);
  }, [cooldownUntil]);

  const applyCooldown = useCallback((seconds: number) => {
    if (seconds <= 0) return;
    const until = Date.now() + seconds * 1000;
    cooldownUntilRef.current = until;
    setCooldownUntil(until);
  }, []);

  const isOnCooldown = useCallback(() => cooldownUntilRef.current > Date.now(), []);

  const mutation = useMutation<TData, TError, TVariables, TContext>({
    ...mutationOptions,
    onSuccess: (data, variables, context) => {
      if (successMessage) toast.success(successMessage);
      onSuccess?.(data, variables, context);
    },
    onError: (error, variables, context) => {
      if (useRetryAfter) {
        const retry = getRetryAfterSeconds(error);
        if (retry != null) applyCooldown(retry);
        else if (cooldownSeconds > 0) applyCooldown(cooldownSeconds);
      }
      toast.error(errorMessage ? errorMessage(error) : getApiErrorMessage(error));
      onError?.(error, variables, context);
    },
    onSettled: (data, error, variables, context) => {
      inFlightRef.current = false;
      onSettled?.(data, error, variables, context);
    },
  });

  const guardedMutate = useCallback(
    (variables?: TVariables) => {
      if (isOnCooldown()) {
        const left = Math.max(1, Math.ceil((cooldownUntilRef.current - Date.now()) / 1000));
        toast.error(formatCooldownMessage(left));
        return;
      }
      if (inFlightRef.current || mutation.isPending) {
        toast.info("Please wait — that action is already in progress.");
        return;
      }

      inFlightRef.current = true;
      if (cooldownSeconds > 0) applyCooldown(cooldownSeconds);

      mutation.mutate((variables ?? undefined) as TVariables);
    },
    [
      applyCooldown,
      cooldownSeconds,
      cooldownSecondsLeft,
      isOnCooldown,
      mutation,
      toast,
    ],
  );

  return {
    ...mutation,
    guardedMutate,
    actionDisabled: mutation.isPending || inFlightRef.current || isOnCooldown(),
    cooldownSecondsLeft,
  };
}
