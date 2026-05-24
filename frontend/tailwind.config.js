/** @type {import('tailwindcss').Config} */

/* Theme tokens are defined as CSS custom properties by ThemeProvider and
 * applied to <html>. The existing component classes (bg-gray-900,
 * border-gray-800, text-accent, …) were re-aliased here so that swapping
 * themes only requires updating the CSS vars — no component rewrites. */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        gray: {
          950: "var(--bg-base)",
          900: "var(--bg-surface)",
          800: "var(--bg-elevated)",
          700: "var(--bg-hover)",
          600: "var(--border-strong)",
          500: "var(--text-muted)",
          400: "var(--text-secondary)",
          300: "var(--text-secondary)",
          200: "var(--text-primary)",
          100: "var(--text-primary)",
          50:  "var(--text-primary)",
        },
        neutral: {
          950: "var(--bg-base)",
          900: "var(--bg-surface)",
          800: "var(--bg-elevated)",
          700: "var(--bg-hover)",
          600: "var(--border-strong)",
          500: "var(--text-muted)",
          400: "var(--text-secondary)",
          300: "var(--text-secondary)",
          200: "var(--text-primary)",
          100: "var(--text-primary)",
          50:  "var(--text-primary)",
        },
        accent: {
          DEFAULT: "var(--accent)",
          hover:   "var(--accent-hover)",
          muted:   "var(--accent-muted)",
        },
        border: {
          DEFAULT: "var(--border)",
          strong:  "var(--border-strong)",
        },
        danger:  "var(--danger)",
        warning: "var(--warning)",
        success: "var(--success)",
      },
      fontFamily: {
        sans: [
          "Inter",
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "sans-serif",
        ],
        mono: ["JetBrains Mono", "Fira Code", "Menlo", "monospace"],
      },
      animation: {
        "fade-in": "fadeIn 0.15s ease-out",
        "slide-in": "slideIn 0.2s ease-out",
      },
      keyframes: {
        fadeIn: {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
        slideIn: {
          "0%": { transform: "translateY(-4px)", opacity: "0" },
          "100%": { transform: "translateY(0)", opacity: "1" },
        },
      },
    },
  },
  plugins: [],
};
