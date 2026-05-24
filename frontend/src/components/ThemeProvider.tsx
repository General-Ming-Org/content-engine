import { createContext, useContext, useEffect, useState } from "react";
import { applyTheme, getStoredTheme, type ThemeId, THEMES } from "../lib/themes";

interface ThemeCtx {
  theme: ThemeId;
  themes: typeof THEMES;
  setTheme: (id: ThemeId) => void;
}

const Ctx = createContext<ThemeCtx | null>(null);

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setThemeState] = useState<ThemeId>(getStoredTheme);

  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  // Keep ThemeProvider in sync when main.tsx applies theme before React mounts.
  useEffect(() => {
    setThemeState(getStoredTheme());
  }, []);

  // Sync across tabs.
  useEffect(() => {
    function onStorage(e: StorageEvent) {
      if (e.key === "content_engine_theme" && e.newValue) {
        setThemeState(e.newValue as ThemeId);
      }
    }
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  return (
    <Ctx.Provider value={{ theme, themes: THEMES, setTheme: setThemeState }}>
      {children}
    </Ctx.Provider>
  );
}

export function useTheme(): ThemeCtx {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useTheme must be used inside <ThemeProvider>");
  return ctx;
}
