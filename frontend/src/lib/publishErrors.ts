import { ApiError } from "./api";
import { getApiErrorMessage } from "./apiErrors";

export type PublishPlatform = "linkedin" | "substack";

const CONNECT_HINT: Record<PublishPlatform, string> = {
  linkedin:
    "Complete LinkedIn setup in Settings: save your Developer App credentials, then connect your account.",
  substack: "Add your Substack credentials in Settings before publishing.",
};

export function publishNotConnectedMessage(platform: PublishPlatform): string {
  return CONNECT_HINT[platform];
}

/** Map API / worker errors to short toast copy. */
export function formatPublishError(err: unknown, platform: PublishPlatform): string {
  if (err instanceof ApiError) {
    const msg = err.message.toLowerCase();
    if (
      err.status === 403 ||
      msg.includes("not authorized") ||
      msg.includes("not configured") ||
      msg.includes("credentials")
    ) {
      return CONNECT_HINT[platform];
    }
  }
  if (err instanceof Error && err.message) {
    const lower = err.message.toLowerCase();
    if (lower.includes("not authorized") || lower.includes("linkedin not")) {
      return CONNECT_HINT.linkedin;
    }
    if (lower.includes("substack") && lower.includes("credential")) {
      return CONNECT_HINT.substack;
    }
  }
  return getApiErrorMessage(
    err,
    platform === "linkedin"
      ? "LinkedIn publish failed. Try again or check Settings."
      : "Substack publish failed. Try again or check Settings.",
  );
}
