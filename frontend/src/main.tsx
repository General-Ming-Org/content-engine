import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ApiError } from "./lib/api";
import App from "./App";
import { ThemeProvider } from "./components/ThemeProvider";
import { ToastProvider } from "./components/ToastProvider";
import { applyTheme, getStoredTheme } from "./lib/themes";
import "./index.css";

// Apply theme before first paint so login → dashboard does not flash wrong colors.
applyTheme(getStoredTheme());

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: (failureCount, error) => {
        if (error instanceof ApiError && (error.status === 401 || error.status === 403)) {
          return false;
        }
        return failureCount < 2;
      },
    },
  },
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ThemeProvider>
      <ToastProvider>
        <QueryClientProvider client={queryClient}>
          <App />
        </QueryClientProvider>
      </ToastProvider>
    </ThemeProvider>
  </React.StrictMode>
);
