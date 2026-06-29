/** Token storage + auth context. Tokens live in localStorage; auth state is a
 * lightweight subscription store so any component can call useAuth() without
 * threading a Context through props. */
import { useEffect, useState } from "react";
import type { AuthUser } from "./api";

const TOKEN_KEY = "content_engine_token";
const USER_KEY = "content_engine_user";

/** Dispatched when a non-auth API call returns 401 so the router can redirect in-app. */
export const AUTH_EXPIRED_EVENT = "ce-auth-expired";

export function notifyAuthExpired() {
  if (typeof window !== "undefined") {
    window.dispatchEvent(new CustomEvent(AUTH_EXPIRED_EVENT));
  }
}

type Listener = () => void;
const listeners = new Set<Listener>();

function notify() {
  listeners.forEach((l) => l());
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function getStoredUser(): AuthUser | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as AuthUser;
  } catch {
    localStorage.removeItem(USER_KEY);
    return null;
  }
}

export function setSession(token: string, user: AuthUser) {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
  notify();
}

export function updateStoredUser(user: AuthUser) {
  localStorage.setItem(USER_KEY, JSON.stringify(user));
  notify();
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
  notify();
}

export function useAuth() {
  const [user, setUser] = useState<AuthUser | null>(getStoredUser);
  const [token, setTok] = useState<string | null>(getToken);

  useEffect(() => {
    const l = () => {
      setUser(getStoredUser());
      setTok(getToken());
    };
    listeners.add(l);
    window.addEventListener("storage", l);
    return () => {
      listeners.delete(l);
      window.removeEventListener("storage", l);
    };
  }, []);

  return {
    user,
    token,
    isAuthenticated: !!token,
    isVerified: user?.email_verified === true,
    logout: clearToken,
  };
}
