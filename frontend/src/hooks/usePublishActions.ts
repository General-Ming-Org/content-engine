import { useQuery } from "@tanstack/react-query";
import {
  approveArticle,
  approvePost,
  cancelArticle,
  cancelPost,
  linkedinStatus,
  substackStatus,
} from "../lib/api";
import { formatPublishError, publishNotConnectedMessage } from "../lib/publishErrors";
import { useToast } from "../components/ToastProvider";
import { useItemAction } from "./useItemAction";

export function usePublishActions(options?: { onInvalidate?: () => void }) {
  const toast = useToast();
  const invalidate = () => options?.onInvalidate?.();

  const { data: linkedIn } = useQuery({
    queryKey: ["linkedin-status"],
    queryFn: linkedinStatus,
    staleTime: 30_000,
  });
  const { data: substack } = useQuery({
    queryKey: ["substack-status"],
    queryFn: substackStatus,
    staleTime: 60_000,
  });

  const publishPostAction = useItemAction(approvePost, {
    loadingMessage: "Publishing to LinkedIn…",
    successMessage: "Post queued for LinkedIn.",
    cooldownSeconds: 3,
    errorMessage: (err) => formatPublishError(err, "linkedin"),
    onSuccess: invalidate,
  });

  const publishArticleAction = useItemAction(approveArticle, {
    loadingMessage: "Publishing to Substack…",
    successMessage: "Article queued for Substack.",
    cooldownSeconds: 3,
    errorMessage: (err) => formatPublishError(err, "substack"),
    onSuccess: invalidate,
  });

  const cancelPostAction = useItemAction(cancelPost, {
    loadingMessage: "Removing post from queue…",
    successMessage: "Post removed from queue.",
    errorMessage: (err) => formatPublishError(err, "linkedin"),
    onSuccess: invalidate,
  });

  const cancelArticleAction = useItemAction(cancelArticle, {
    loadingMessage: "Removing article from queue…",
    successMessage: "Article removed from queue.",
    errorMessage: (err) => formatPublishError(err, "substack"),
    onSuccess: invalidate,
  });

  function publishPost(postId: string) {
    if (linkedIn?.app_configured === false) {
      toast.error(
        "Set up your LinkedIn Developer App in Settings (Client ID and Secret), then connect your account.",
      );
      return;
    }
    if (!linkedIn?.configured) {
      toast.error(publishNotConnectedMessage("linkedin"));
      return;
    }
    void publishPostAction.run(postId);
  }

  function publishArticle(articleId: string) {
    if (!substack?.configured) {
      toast.error(publishNotConnectedMessage("substack"));
      return;
    }
    void publishArticleAction.run(articleId);
  }

  function isPostBusy(postId: string) {
    return publishPostAction.isLocked(postId) || cancelPostAction.isLocked(postId);
  }

  function isArticleBusy(articleId: string) {
    return publishArticleAction.isLocked(articleId) || cancelArticleAction.isLocked(articleId);
  }

  return {
    publishPost,
    publishArticle,
    cancelPost: (id: string) => void cancelPostAction.run(id),
    cancelArticle: (id: string) => void cancelArticleAction.run(id),
    isPostBusy,
    isArticleBusy,
    linkedInConnected: !!linkedIn?.configured,
    linkedInAccountConnected: !!linkedIn?.configured,
    linkedInAppConfigured: linkedIn?.app_configured === true,
    substackConnected: !!substack?.configured,
  };
}
