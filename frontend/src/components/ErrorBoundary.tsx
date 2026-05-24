import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

/** Catches render errors so a single bad component does not blank the whole app. */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("UI render error", error, info.componentStack);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="min-h-screen flex items-center justify-center bg-gray-950 px-6">
          <div className="max-w-md text-center">
            <h1 className="text-lg font-semibold text-gray-100 mb-2">Something went wrong</h1>
            <p className="text-sm text-gray-400 mb-6">
              The page hit an unexpected error. Reload to try again, or sign in again if the problem
              persists.
            </p>
            <button
              type="button"
              onClick={() => window.location.reload()}
              className="btn-primary"
            >
              Reload page
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
