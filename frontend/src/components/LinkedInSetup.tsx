import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Copy, ExternalLink, Linkedin, Loader2, Unlink } from "lucide-react";
import { useSearchParams } from "react-router-dom";
import {
  deleteLinkedin,
  deleteLinkedinApp,
  linkedinAppStatus,
  linkedinStatus,
  setLinkedinApp,
  setLinkedinRedirectMode,
  startLinkedinOAuth,
  type LinkedInAppStatus,
  type LinkedInRedirectMode,
} from "../lib/api";
import { getLinkedInFormState } from "../lib/formActions";
import { useGuardedMutation } from "../hooks/useGuardedMutation";
import { useToast } from "./ToastProvider";
import { ActionButton } from "./ActionButton";

export function LinkedInSetup() {
  const qc = useQueryClient();
  const toast = useToast();
  const [searchParams, setSearchParams] = useSearchParams();
  const [banner, setBanner] = useState<{ type: "ok" | "err"; text: string } | null>(null);
  const [clientId, setClientId] = useState("");
  const [clientSecret, setClientSecret] = useState("");
  const [formTouched, setFormTouched] = useState(false);

  const { data: app, isLoading: appLoading } = useQuery({
    queryKey: ["linkedin-app"],
    queryFn: linkedinAppStatus,
  });

  const { data: account, isLoading: accountLoading } = useQuery({
    queryKey: ["linkedin-status"],
    queryFn: linkedinStatus,
  });

  const accountConnected = !!account?.configured;

  const saveAppMut = useGuardedMutation({
    mutationFn: () => {
      const state = getLinkedInFormState(
        clientId,
        clientSecret,
        formTouched,
        app,
        accountConnected,
        false,
        false,
      );
      return setLinkedinApp({
        client_id: state.clientIdForSave,
        client_secret: state.secretForSave || undefined,
      });
    },
    successMessage: "LinkedIn app credentials saved.",
    cooldownSeconds: 2,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["linkedin-app"] });
      qc.invalidateQueries({ queryKey: ["linkedin-status"] });
      setClientSecret("");
      setFormTouched(false);
    },
    onError: (err) => {
      setBanner({
        type: "err",
        text: err instanceof Error ? err.message : "Could not save LinkedIn app credentials.",
      });
    },
  });

  const redirectModeMut = useMutation({
    mutationFn: (mode: LinkedInRedirectMode) => setLinkedinRedirectMode(mode),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["linkedin-app"] });
      toast.success("Redirect URL mode updated — use the URL shown in Step 1 in LinkedIn.");
    },
    onError: (err) => {
      toast.error(err instanceof Error ? err.message : "Could not update redirect URL mode.");
    },
  });

  const clearAppMut = useMutation({
    mutationFn: () => deleteLinkedinApp(),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["linkedin-app"] });
      qc.invalidateQueries({ queryKey: ["linkedin-status"] });
      setClientId("");
      setClientSecret("");
      setFormTouched(false);
      toast.success("LinkedIn app credentials removed.");
    },
    onError: (err) => {
      toast.error(err instanceof Error ? err.message : "Could not remove app credentials.");
    },
  });

  const connectMut = useGuardedMutation({
    mutationFn: () => startLinkedinOAuth(),
    cooldownSeconds: 3,
    onSuccess: (data) => {
      window.location.href = data.url;
    },
    onError: (err) => {
      setBanner({
        type: "err",
        text: err instanceof Error ? err.message : "Could not start LinkedIn sign-in.",
      });
    },
  });

  const disconnectMut = useGuardedMutation<void, Error, void>({
    mutationFn: () => deleteLinkedin(),
    successMessage: "LinkedIn account disconnected.",
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["linkedin-status"] });
      setBanner({ type: "ok", text: "LinkedIn account disconnected." });
    },
  });

  useEffect(() => {
    const result = searchParams.get("linkedin");
    if (!result) return;

    const reason = searchParams.get("reason");

    if (result === "connected") {
      setBanner({ type: "ok", text: "LinkedIn connected — you can publish from Calendar." });
      qc.invalidateQueries({ queryKey: ["linkedin-status"] });
    } else if (result === "denied") {
      setBanner({
        type: "err",
        text: reason
          ? `LinkedIn denied access: ${reason}`
          : "LinkedIn sign-in was cancelled.",
      });
    } else {
      setBanner({
        type: "err",
        text:
          reason ??
          "LinkedIn connection failed. Register the exact redirect URL shown in Step 1 (including port and path).",
      });
    }
    setSearchParams({}, { replace: true });
  }, [searchParams, setSearchParams, qc]);

  const loading = appLoading || accountLoading;

  const uiFormState = useMemo(
    () =>
      getLinkedInFormState(
        clientId,
        clientSecret,
        formTouched,
        app,
        accountConnected,
        saveAppMut.isPending,
        connectMut.isPending,
      ),
    [
      clientId,
      clientSecret,
      formTouched,
      app,
      accountConnected,
      saveAppMut.isPending,
      connectMut.isPending,
    ],
  );

  const displayClientId =
    formTouched || clientId ? clientId : app?.client_id ?? "";

  function copyRedirectUri() {
    if (!app?.redirect_uri) return;
    void navigator.clipboard.writeText(app.redirect_uri).then(
      () => toast.success("Redirect URL copied."),
      () => toast.error("Could not copy — select and copy the URL manually."),
    );
  }

  const saveDisabled = !uiFormState.canSaveApp || saveAppMut.actionDisabled;
  const connectDisabled = !uiFormState.canConnectAccount || connectMut.actionDisabled;

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
      <h2 className="text-sm font-semibold text-gray-200 mb-1 flex items-center gap-2">
        <Linkedin className="w-4 h-4 text-blue-400" />
        LinkedIn
      </h2>
      <p className="text-xs text-gray-500 mb-4">
        Connect your own LinkedIn Developer App, then sign in to publish posts and run engagement
        replies. Content generation works without LinkedIn.
      </p>

      {banner && (
        <p
          role="alert"
          className={`text-xs mb-4 px-3 py-2 rounded-lg border ${
            banner.type === "ok"
              ? "text-green-400 bg-green-950/40 border-green-800/50"
              : "text-red-400 bg-red-950/40 border-red-800/50"
          }`}
        >
          {banner.text}
        </p>
      )}

      <SetupInstructions
        app={app}
        onCopyRedirect={copyRedirectUri}
        redirectMode={app?.redirect_mode ?? "app"}
        redirectOptions={app?.redirect_options ?? []}
        onSelectRedirectMode={(mode) => redirectModeMut.mutate(mode)}
        redirectModeBusy={redirectModeMut.isPending}
      />

      {app?.source === "env" && (
        <p className="text-xs text-amber-400/90 mt-4 px-3 py-2 rounded-lg border border-amber-800/40 bg-amber-950/20">
          Server-level LinkedIn credentials are active. Save your own Client ID and Secret below to
          use your app instead.
        </p>
      )}

      <div className="mt-5 space-y-3">
        <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">
          Step 2 — App credentials
        </p>
        <div>
          <label className="block text-xs text-gray-500 mb-1.5" htmlFor="linkedin-client-id">
            Client ID <span className="text-red-400/80">*</span>
          </label>
          <input
            id="linkedin-client-id"
            className="input font-mono text-sm"
            value={displayClientId}
            onChange={(e) => {
              setFormTouched(true);
              setClientId(e.target.value);
            }}
            placeholder="Paste from LinkedIn Developer Portal"
            autoComplete="off"
            required
          />
        </div>
        <div>
          <label className="block text-xs text-gray-500 mb-1.5" htmlFor="linkedin-client-secret">
            Client Secret{" "}
            {uiFormState.hasStoredSecret ? (
              <span className="text-gray-600">(leave blank to keep saved)</span>
            ) : (
              <span className="text-red-400/80">*</span>
            )}
          </label>
          <input
            id="linkedin-client-secret"
            type="password"
            className="input font-mono text-sm"
            value={clientSecret}
            onChange={(e) => setClientSecret(e.target.value)}
            placeholder={
              uiFormState.hasStoredSecret
                ? "Leave blank to keep existing secret"
                : "Paste from LinkedIn Developer Portal"
            }
            autoComplete="new-password"
          />
        </div>
        {uiFormState.saveBlockedReason && !saveAppMut.isPending && (
          <p className="text-xs text-gray-500">{uiFormState.saveBlockedReason}</p>
        )}
        <div className="flex flex-wrap gap-2">
          <ActionButton
            variant="primary"
            className="text-xs"
            disabled={saveDisabled}
            title={uiFormState.saveBlockedReason ?? undefined}
            onClick={() => {
              if (!uiFormState.canSaveApp) return;
              saveAppMut.guardedMutate();
            }}
          >
            {saveAppMut.isPending ? (
              <>
                <Loader2 className="w-3.5 h-3.5 animate-spin inline mr-1" />
                Saving…
              </>
            ) : (
              "Save app credentials"
            )}
          </ActionButton>
          {app?.source === "user" && (
            <ActionButton
              variant="ghost"
              className="text-xs"
              disabled={clearAppMut.isPending}
              onClick={() => clearAppMut.mutate()}
            >
              Clear saved app
            </ActionButton>
          )}
        </div>
      </div>

      <div className="mt-6 pt-5 border-t border-gray-800">
        <p className="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-3">
          Step 3 — Connect your account
        </p>
        {loading ? (
          <p className="text-xs text-gray-500">Checking connection…</p>
        ) : (
          <div className="flex items-start justify-between gap-4">
            <div>
              {accountConnected ? (
                <div className="space-y-0.5">
                  <p className="text-xs text-green-400 flex items-center gap-1">
                    <Check className="w-3.5 h-3.5" /> Account connected
                  </p>
                  {account?.expires_at && (
                    <p className="text-xs text-gray-500">
                      Token expires {formatExpires(account.expires_at)}
                    </p>
                  )}
                </div>
              ) : (
                <>
                  <p className="text-xs text-gray-400">
                    {app?.configured
                      ? "App credentials ready — sign in with LinkedIn to authorize publishing."
                      : "Complete Step 2 before connecting your account."}
                  </p>
                  {uiFormState.connectBlockedReason && !accountConnected && (
                    <p className="text-xs text-gray-500 mt-1">{uiFormState.connectBlockedReason}</p>
                  )}
                </>
              )}
            </div>
            <div className="flex flex-col gap-2 flex-shrink-0">
              {accountConnected ? (
                <ActionButton
                  variant="ghost"
                  className="text-xs flex items-center gap-1.5"
                  disabled={disconnectMut.actionDisabled}
                  onClick={() => disconnectMut.guardedMutate()}
                >
                  {disconnectMut.isPending ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <Unlink className="w-3.5 h-3.5" />
                  )}
                  Disconnect account
                </ActionButton>
              ) : (
                <ActionButton
                  variant="primary"
                  className="text-xs flex items-center gap-1.5"
                  disabled={connectDisabled}
                  title={uiFormState.connectBlockedReason ?? undefined}
                  onClick={() => connectMut.guardedMutate()}
                >
                  {connectMut.isPending ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <ExternalLink className="w-3.5 h-3.5" />
                  )}
                  Connect LinkedIn
                </ActionButton>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function SetupInstructions({
  app,
  onCopyRedirect,
  redirectMode,
  redirectOptions,
  onSelectRedirectMode,
  redirectModeBusy,
}: {
  app: LinkedInAppStatus | undefined;
  onCopyRedirect: () => void;
  redirectMode: LinkedInRedirectMode;
  redirectOptions: { mode: LinkedInRedirectMode; label: string; uri: string }[];
  onSelectRedirectMode: (mode: LinkedInRedirectMode) => void;
  redirectModeBusy: boolean;
}) {
  const redirectUri =
    app?.redirect_uri ?? "http://localhost:3000/api/publish/linkedin/callback";
  const options =
    redirectOptions.length > 0
      ? redirectOptions
      : [
          {
            mode: "app" as const,
            label: "Web app (port 3000)",
            uri: "http://localhost:3000/api/publish/linkedin/callback",
          },
          {
            mode: "api" as const,
            label: "API directly (port 8000)",
            uri: "http://localhost:8000/api/publish/linkedin/callback",
          },
        ];

  return (
    <div className="rounded-lg border border-gray-800 bg-gray-800/30 p-4 text-xs text-gray-400 leading-relaxed space-y-3">
      <p className="text-gray-300 font-medium text-sm">Step 1 — Create a LinkedIn Developer App</p>
      <ol className="list-decimal list-inside space-y-2 marker:text-gray-500">
        <li>
          Open the{" "}
          <a
            href="https://www.linkedin.com/developers/apps"
            target="_blank"
            rel="noopener noreferrer"
            className="text-blue-400 hover:underline"
          >
            LinkedIn Developer Portal
          </a>{" "}
          and click <strong className="text-gray-300">Create app</strong> (use your company page if
          prompted).
        </li>
        <li>
          On the app’s <strong className="text-gray-300">Products</strong> tab, request{" "}
          <strong className="text-gray-300">Share on LinkedIn</strong> and{" "}
          <strong className="text-gray-300">Sign In with LinkedIn using OpenID Connect</strong>.
        </li>
        <li>
          Choose which redirect URL you registered in LinkedIn, then add that exact URL under{" "}
          <strong className="text-gray-300">Auth → OAuth 2.0 → Authorized redirect URLs</strong>:
        </li>
      </ol>
      <fieldset className="space-y-2" disabled={redirectModeBusy}>
        <legend className="sr-only">OAuth redirect URL mode</legend>
        {options.map((opt) => (
          <label
            key={opt.mode}
            className={`flex items-start gap-2.5 rounded-lg border p-2.5 cursor-pointer ${
              redirectMode === opt.mode
                ? "border-blue-600/60 bg-blue-950/20"
                : "border-gray-700 bg-gray-950/40 hover:border-gray-600"
            }`}
          >
            <input
              type="radio"
              name="linkedin-redirect-mode"
              className="mt-0.5"
              checked={redirectMode === opt.mode}
              onChange={() => onSelectRedirectMode(opt.mode)}
            />
            <span className="min-w-0">
              <span className="block text-gray-300 text-[11px] font-medium">{opt.label}</span>
              <code className="block text-[10px] text-gray-500 break-all font-mono mt-0.5">
                {opt.uri}
              </code>
            </span>
          </label>
        ))}
      </fieldset>
      <div className="flex items-start gap-2 bg-gray-950/80 border border-gray-700 rounded-lg p-2.5">
        <code className="flex-1 text-[11px] text-gray-300 break-all font-mono">{redirectUri}</code>
        <ActionButton
          variant="ghost"
          className="p-1.5 flex-shrink-0"
          title="Copy redirect URL"
          onClick={onCopyRedirect}
        >
          <Copy className="w-3.5 h-3.5" />
        </ActionButton>
      </div>
      <p className="text-amber-400/90 font-medium">
        The URL in LinkedIn must match the selection above character-for-character (port and path).
        If you registered <code className="text-amber-300">:8000</code>, select{" "}
        <strong className="text-gray-300">API directly (port 8000)</strong>.
      </p>
      <p>
        Copy the <strong className="text-gray-300">Client ID</strong> and{" "}
        <strong className="text-gray-300">Client Secret</strong> from the Auth tab into Step 2.
        Enable products <strong className="text-gray-300">Share on LinkedIn</strong> and{" "}
        <strong className="text-gray-300">Sign In with LinkedIn using OpenID Connect</strong>.
      </p>
    </div>
  );
}

function formatExpires(iso: string) {
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}
