/** Palette-driven theme system.
 *
 * Each theme provides a CSS-variable map; ThemeProvider writes them to the
 * <html> element so Tailwind utilities (gray-900, accent, etc., remapped in
 * tailwind.config.js) pick them up automatically.
 *
 * Names + accent choices are inspired by popular VS Code themes:
 *   https://itsfoss.com/vs-code-themes/
 */

export type ThemeId =
  | "linear-dark"
  | "linear-light"
  | "dracula"
  | "one-dark-pro"
  | "tokyo-night"
  | "catppuccin-mocha"
  | "catppuccin-latte";

export interface Theme {
  id: ThemeId;
  label: string;
  mode: "dark" | "light";
  /** CSS variable name → color. Keep keys in sync with index.css :root vars. */
  vars: Record<string, string>;
}

/** Variables every theme must provide. Tailwind aliases (see tailwind.config.js)
 *  reference these tokens so utility classes work across all themes. */
const REQUIRED_KEYS = [
  "--bg-base",       // canvas (deepest layer)
  "--bg-surface",    // panels / sidebar
  "--bg-elevated",   // cards / inputs
  "--bg-hover",      // subtle hover background
  "--border",        // hairlines
  "--border-strong", // emphasized borders
  "--text-primary",
  "--text-secondary",
  "--text-muted",
  "--text-inverse",  // text on accent button
  "--accent",
  "--accent-hover",
  "--accent-muted",  // for backgrounds tinted with accent
  "--danger",
  "--warning",
  "--success",
] as const;

export const THEMES: Theme[] = [
  {
    id: "linear-dark",
    label: "Linear Dark (default)",
    mode: "dark",
    vars: {
      "--bg-base":       "#0a0a0b",
      "--bg-surface":    "#111113",
      "--bg-elevated":   "#1c1c1f",
      "--bg-hover":      "#28282c",
      "--border":        "#1c1c1f",
      "--border-strong": "#3a3a3f",
      "--text-primary":   "#ebebf0",
      "--text-secondary": "#b4b4be",
      "--text-muted":     "#8b8b96",
      "--text-inverse":   "#ffffff",
      "--accent":         "#5b5bd6",
      "--accent-hover":   "#6e6ede",
      "--accent-muted":   "#3d3d9e",
      "--danger":  "#ef4444",
      "--warning": "#eab308",
      "--success": "#10b981",
    },
  },
  {
    id: "dracula",
    label: "Dracula",
    mode: "dark",
    vars: {
      "--bg-base":       "#21222c",
      "--bg-surface":    "#282a36",
      "--bg-elevated":   "#343746",
      "--bg-hover":      "#44475a",
      "--border":        "#343746",
      "--border-strong": "#6272a4",
      "--text-primary":   "#f8f8f2",
      "--text-secondary": "#bdbdce",
      "--text-muted":     "#6272a4",
      "--text-inverse":   "#21222c",
      "--accent":         "#bd93f9",
      "--accent-hover":   "#caa9fa",
      "--accent-muted":   "#44475a",
      "--danger":  "#ff5555",
      "--warning": "#f1fa8c",
      "--success": "#50fa7b",
    },
  },
  {
    id: "one-dark-pro",
    label: "One Dark Pro",
    mode: "dark",
    vars: {
      "--bg-base":       "#1e2227",
      "--bg-surface":    "#282c34",
      "--bg-elevated":   "#2c313a",
      "--bg-hover":      "#3a3f4b",
      "--border":        "#2c313a",
      "--border-strong": "#4b5263",
      "--text-primary":   "#abb2bf",
      "--text-secondary": "#9aa0aa",
      "--text-muted":     "#5c6370",
      "--text-inverse":   "#1e2227",
      "--accent":         "#61afef",
      "--accent-hover":   "#7bbcf2",
      "--accent-muted":   "#3b4862",
      "--danger":  "#e06c75",
      "--warning": "#e5c07b",
      "--success": "#98c379",
    },
  },
  {
    id: "tokyo-night",
    label: "Tokyo Night",
    mode: "dark",
    vars: {
      "--bg-base":       "#16161e",
      "--bg-surface":    "#1a1b26",
      "--bg-elevated":   "#24283b",
      "--bg-hover":      "#2f334d",
      "--border":        "#24283b",
      "--border-strong": "#414868",
      "--text-primary":   "#c0caf5",
      "--text-secondary": "#a9b1d6",
      "--text-muted":     "#565f89",
      "--text-inverse":   "#1a1b26",
      "--accent":         "#7aa2f7",
      "--accent-hover":   "#92b5fa",
      "--accent-muted":   "#3d59a1",
      "--danger":  "#f7768e",
      "--warning": "#e0af68",
      "--success": "#9ece6a",
    },
  },
  {
    id: "catppuccin-mocha",
    label: "Catppuccin Mocha",
    mode: "dark",
    vars: {
      "--bg-base":       "#11111b",
      "--bg-surface":    "#1e1e2e",
      "--bg-elevated":   "#313244",
      "--bg-hover":      "#45475a",
      "--border":        "#313244",
      "--border-strong": "#585b70",
      "--text-primary":   "#cdd6f4",
      "--text-secondary": "#bac2de",
      "--text-muted":     "#6c7086",
      "--text-inverse":   "#1e1e2e",
      "--accent":         "#cba6f7",
      "--accent-hover":   "#d4b8f9",
      "--accent-muted":   "#45475a",
      "--danger":  "#f38ba8",
      "--warning": "#f9e2af",
      "--success": "#a6e3a1",
    },
  },
  {
    id: "linear-light",
    label: "Linear Light",
    mode: "light",
    vars: {
      "--bg-base":       "#fafaf9",
      "--bg-surface":    "#ffffff",
      "--bg-elevated":   "#f5f5f4",
      "--bg-hover":      "#ececea",
      "--border":        "#e7e7e5",
      "--border-strong": "#c4c4c0",
      "--text-primary":   "#1c1c1a",
      "--text-secondary": "#52524f",
      "--text-muted":     "#8a8a85",
      "--text-inverse":   "#ffffff",
      "--accent":         "#5b5bd6",
      "--accent-hover":   "#4a4ac4",
      "--accent-muted":   "#e8e8ff",
      "--danger":  "#dc2626",
      "--warning": "#ca8a04",
      "--success": "#059669",
    },
  },
  {
    id: "catppuccin-latte",
    label: "Catppuccin Latte",
    mode: "light",
    vars: {
      "--bg-base":       "#eff1f5",
      "--bg-surface":    "#ffffff",
      "--bg-elevated":   "#e6e9ef",
      "--bg-hover":      "#dce0e8",
      "--border":        "#e6e9ef",
      "--border-strong": "#bcc0cc",
      "--text-primary":   "#4c4f69",
      "--text-secondary": "#5c5f77",
      "--text-muted":     "#8c8fa1",
      "--text-inverse":   "#ffffff",
      "--accent":         "#8839ef",
      "--accent-hover":   "#7c2fe0",
      "--accent-muted":   "#dcd6f5",
      "--danger":  "#d20f39",
      "--warning": "#df8e1d",
      "--success": "#40a02b",
    },
  },
];

const STORAGE_KEY = "content_engine_theme";
const DEFAULT_THEME: ThemeId = "linear-dark";

export function getStoredTheme(): ThemeId {
  if (typeof window === "undefined") return DEFAULT_THEME;
  const stored = localStorage.getItem(STORAGE_KEY) as ThemeId | null;
  if (stored && THEMES.some((t) => t.id === stored)) return stored;
  return DEFAULT_THEME;
}

export function applyTheme(id: ThemeId): void {
  const theme = THEMES.find((t) => t.id === id) ?? THEMES[0];
  const root = document.documentElement;
  for (const key of REQUIRED_KEYS) {
    root.style.setProperty(key, theme.vars[key] ?? "");
  }
  root.dataset.theme = theme.id;
  root.dataset.themeMode = theme.mode;
  if (theme.mode === "dark") root.classList.add("dark");
  else root.classList.remove("dark");
  localStorage.setItem(STORAGE_KEY, theme.id);
  // Broadcast so other tabs / subscribers can react.
  window.dispatchEvent(new CustomEvent("ce-theme-change", { detail: theme.id }));
}
