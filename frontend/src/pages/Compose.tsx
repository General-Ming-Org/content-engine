import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Send, Save, Linkedin, FileText } from "lucide-react";
import { createPost, createArticle } from "../lib/api";
import { getComposeSaveReady } from "../lib/formActions";
import { ActionButton } from "../components/ActionButton";

type Mode = "post" | "article" | "both";

export default function Compose() {
  const qc = useQueryClient();
  const [mode, setMode] = useState<Mode>("post");

  // Post fields
  const [postContent, setPostContent] = useState("");
  const [postHashtags, setPostHashtags] = useState("");
  const [postVoice, setPostVoice] = useState<"opinionated" | "analytical" | "tutorial">("analytical");

  // Article fields
  const [articleTitle, setArticleTitle] = useState("");
  const [articleSubtitle, setArticleSubtitle] = useState("");
  const [articleBody, setArticleBody] = useState("");
  const [articleVoice, setArticleVoice] = useState<"opinionated" | "analytical" | "tutorial">("analytical");

  // Shared
  const [scheduledAt, setScheduledAt] = useState("");

  const charCount = postContent.length;
  const charColor = charCount > 1800 ? "text-red-400" : charCount > 1500 ? "text-yellow-400" : "text-gray-500";

  const createPostMut = useMutation({
    mutationFn: () =>
      createPost({
        content: postContent,
        hashtags: postHashtags.split(/\s+/).filter((t) => t.startsWith("#")),
        voice_style: postVoice,
        scheduled_at: scheduledAt || undefined,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["posts-all"] });
      setPostContent("");
      setPostHashtags("");
    },
  });

  const createArticleMut = useMutation({
    mutationFn: () =>
      createArticle({
        title: articleTitle,
        subtitle: articleSubtitle || undefined,
        body_markdown: articleBody,
        voice_style: articleVoice,
        scheduled_at: scheduledAt || undefined,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["articles-all"] });
      setArticleTitle("");
      setArticleSubtitle("");
      setArticleBody("");
    },
  });

  const saveReady = getComposeSaveReady(mode, postContent, articleTitle, articleBody);
  const savePending = createPostMut.isPending || createArticleMut.isPending;

  const handleSave = () => {
    if (!saveReady.canSave) return;
    if (mode === "post" || mode === "both") createPostMut.mutate();
    if (mode === "article" || mode === "both") createArticleMut.mutate();
  };

  return (
    <div>
      <div className="page-header">
        <h1 className="text-xl font-semibold text-gray-100">Compose</h1>
      </div>

      {/* Mode selector */}
      <div className="flex gap-2 mb-6">
        {([
          { value: "post", icon: Linkedin, label: "LinkedIn Post" },
          { value: "article", icon: FileText, label: "Substack Article" },
          { value: "both", icon: Send, label: "Paired (both)" },
        ] as { value: Mode; icon: typeof Linkedin; label: string }[]).map(({ value, icon: Icon, label }) => (
          <button
            key={value}
            onClick={() => setMode(value)}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm transition-colors border ${
              mode === value
                ? "bg-accent border-accent text-white"
                : "bg-gray-900 border-gray-800 text-gray-400 hover:text-gray-100"
            }`}
          >
            <Icon className="w-4 h-4" />
            {label}
          </button>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-4">
          {(mode === "post" || mode === "both") && (
            <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
              <div className="flex items-center gap-2 mb-4">
                <Linkedin className="w-4 h-4 text-blue-400" />
                <h2 className="text-sm font-medium text-gray-200">LinkedIn Post</h2>
              </div>

              <textarea
                className="input resize-none font-mono text-xs leading-relaxed"
                rows={12}
                placeholder="Write your post. First line is the hook. End with a question."
                value={postContent}
                onChange={(e) => setPostContent(e.target.value)}
              />
              <div className="flex items-center justify-between mt-1">
                <span className={`text-xs ${charColor}`}>{charCount} / 1800 chars</span>
                {charCount > 0 && (
                  <span className={`text-xs ${charCount >= 1200 && charCount <= 1800 ? "text-green-400" : "text-yellow-400"}`}>
                    {charCount >= 1200 && charCount <= 1800 ? "Good length" : charCount < 1200 ? "Too short" : "Too long"}
                  </span>
                )}
              </div>

              <div className="mt-3">
                <input
                  className="input"
                  placeholder="#Hashtags #separated #by #spaces"
                  value={postHashtags}
                  onChange={(e) => setPostHashtags(e.target.value)}
                />
              </div>

              <div className="flex gap-2 mt-3">
                {(["opinionated", "analytical", "tutorial"] as const).map((v) => (
                  <button
                    key={v}
                    onClick={() => setPostVoice(v)}
                    className={`px-3 py-1 rounded-md text-xs capitalize transition-colors ${
                      postVoice === v ? "bg-accent text-white" : "bg-gray-800 text-gray-400 hover:text-gray-200"
                    }`}
                  >
                    {v}
                  </button>
                ))}
              </div>
            </div>
          )}

          {(mode === "article" || mode === "both") && (
            <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
              <div className="flex items-center gap-2 mb-4">
                <FileText className="w-4 h-4 text-orange-400" />
                <h2 className="text-sm font-medium text-gray-200">Substack Article</h2>
              </div>

              <input
                className="input mb-3"
                placeholder="Article title"
                value={articleTitle}
                onChange={(e) => setArticleTitle(e.target.value)}
              />
              <input
                className="input mb-3"
                placeholder="Subtitle (optional)"
                value={articleSubtitle}
                onChange={(e) => setArticleSubtitle(e.target.value)}
              />
              <textarea
                className="input resize-none font-mono text-xs leading-relaxed"
                rows={16}
                placeholder="Write in Markdown. Use ## for headers, ``` for code blocks."
                value={articleBody}
                onChange={(e) => setArticleBody(e.target.value)}
              />
              <div className="flex gap-2 mt-3">
                {(["opinionated", "analytical", "tutorial"] as const).map((v) => (
                  <button
                    key={v}
                    onClick={() => setArticleVoice(v)}
                    className={`px-3 py-1 rounded-md text-xs capitalize transition-colors ${
                      articleVoice === v ? "bg-accent text-white" : "bg-gray-800 text-gray-400 hover:text-gray-200"
                    }`}
                  >
                    {v}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Sidebar */}
        <div className="space-y-4">
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
            <h2 className="text-sm font-medium text-gray-200 mb-4">Schedule</h2>
            <label className="block text-xs text-gray-500 mb-1.5">Scheduled date & time</label>
            <input
              type="datetime-local"
              className="input"
              value={scheduledAt}
              onChange={(e) => setScheduledAt(e.target.value)}
            />
            <p className="text-xs text-gray-600 mt-2">
              Leave blank to add to the 1-hour queue immediately.
            </p>
          </div>

          <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 space-y-3">
            {saveReady.reason && !savePending && (
              <p className="text-xs text-gray-500">{saveReady.reason}</p>
            )}
            <ActionButton
              variant="primary"
              className="w-full flex items-center justify-center gap-2"
              disabled={!saveReady.canSave || savePending}
              title={saveReady.reason ?? undefined}
              onClick={handleSave}
            >
              <Save className="w-4 h-4" />
              {savePending ? "Saving…" : "Save as Draft"}
            </ActionButton>
            {(createPostMut.isSuccess || createArticleMut.isSuccess) && (
              <p className="text-xs text-green-400 text-center">Saved to drafts.</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
