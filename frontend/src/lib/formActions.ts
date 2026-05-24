import clsx from "clsx";
import type { LinkedInAppStatus } from "./api";

/** Tailwind classes applied with `disabled:` on primary/ghost buttons. */
export const BTN_DISABLED =
  "disabled:opacity-40 disabled:cursor-not-allowed disabled:pointer-events-none";

export function buttonClass(
  variant: "primary" | "ghost",
  extra?: string,
  disabled?: boolean,
): string {
  return clsx(variant === "primary" ? "btn-primary" : "btn-ghost", BTN_DISABLED, extra, disabled && "opacity-40 cursor-not-allowed");
}

export interface LinkedInFormState {
  clientIdForSave: string;
  secretForSave: string;
  hasStoredSecret: boolean;
  canSaveApp: boolean;
  canConnectAccount: boolean;
  saveBlockedReason: string | null;
  connectBlockedReason: string | null;
}

/**
 * LinkedIn Settings — Step 2 (save app) and Step 3 (OAuth) prerequisites.
 *
 * Flow:
 * 1. User creates Developer App (external) and copies redirect URL from UI.
 * 2. Save Client ID + Secret → `linkedin_app` in DB (or env fallback already set).
 * 3. Connect account → OAuth tokens under `linkedin`.
 * 4. Calendar/Dashboard publish requires both app + account (Substack: credentials only).
 */
export function getLinkedInFormState(
  clientIdInput: string,
  clientSecretInput: string,
  formTouched: boolean,
  app: LinkedInAppStatus | undefined,
  accountConnected: boolean,
  isSaving: boolean,
  isConnecting: boolean,
): LinkedInFormState {
  const savedClientId =
    app?.source === "user" && app.client_id ? app.client_id.trim() : "";
  const clientIdForSave = (formTouched ? clientIdInput : clientIdInput || savedClientId).trim();
  const secretForSave = clientSecretInput.trim();
  const hasStoredSecret = Boolean(app?.source === "user" && app.has_secret);

  let saveBlockedReason: string | null = null;
  if (!clientIdForSave) {
    saveBlockedReason = "Enter your Client ID.";
  } else if (!secretForSave && !hasStoredSecret) {
    saveBlockedReason = "Enter your Client Secret.";
  } else if (isSaving) {
    saveBlockedReason = "Saving…";
  }

  const canSaveApp = saveBlockedReason === null;

  let connectBlockedReason: string | null = null;
  if (!app?.configured) {
    connectBlockedReason = "Save your Client ID and Secret first.";
  } else if (accountConnected) {
    connectBlockedReason = "Already connected.";
  } else if (isConnecting) {
    connectBlockedReason = "Connecting…";
  }

  const canConnectAccount = connectBlockedReason === null;

  return {
    clientIdForSave,
    secretForSave,
    hasStoredSecret,
    canSaveApp,
    canConnectAccount,
    saveBlockedReason,
    connectBlockedReason,
  };
}

export interface PublishReadiness {
  canPublish: boolean;
  canCancel: boolean;
  publishBlockedReason: string | null;
}

export function getPublishReadiness(
  platform: "linkedin" | "substack",
  status: "queued" | string,
  actionBusy: boolean,
  linkedInAppConfigured: boolean,
  linkedInAccountConnected: boolean,
  substackConfigured: boolean,
): PublishReadiness {
  if (status !== "queued") {
    return { canPublish: false, canCancel: false, publishBlockedReason: null };
  }
  if (actionBusy) {
    return {
      canPublish: false,
      canCancel: false,
      publishBlockedReason: "Action in progress…",
    };
  }

  const canCancel = true;

  if (platform === "linkedin") {
    if (!linkedInAppConfigured) {
      return {
        canPublish: false,
        canCancel,
        publishBlockedReason: "Set up LinkedIn app credentials in Settings.",
      };
    }
    if (!linkedInAccountConnected) {
      return {
        canPublish: false,
        canCancel,
        publishBlockedReason: "Connect your LinkedIn account in Settings.",
      };
    }
    return { canPublish: true, canCancel, publishBlockedReason: null };
  }

  if (!substackConfigured) {
    return {
      canPublish: false,
      canCancel,
      publishBlockedReason: "Add Substack credentials in Settings.",
    };
  }
  return { canPublish: true, canCancel, publishBlockedReason: null };
}

export function getComposeSaveReady(
  mode: "post" | "article" | "both",
  postContent: string,
  articleTitle: string,
  articleBody: string,
): { canSave: boolean; reason: string | null } {
  const postOk = postContent.trim().length > 0;
  const articleOk = articleTitle.trim().length > 0 && articleBody.trim().length > 0;

  if (mode === "post") {
    return postOk
      ? { canSave: true, reason: null }
      : { canSave: false, reason: "Write post content to save." };
  }
  if (mode === "article") {
    return articleOk
      ? { canSave: true, reason: null }
      : { canSave: false, reason: "Title and body are required." };
  }
  if (!postOk && !articleOk) {
    return { canSave: false, reason: "Fill in post and article fields." };
  }
  if (!postOk) {
    return { canSave: false, reason: "Write post content for the paired draft." };
  }
  if (!articleOk) {
    return { canSave: false, reason: "Title and body are required for the article." };
  }
  return { canSave: true, reason: null };
}
