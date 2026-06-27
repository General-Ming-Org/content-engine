import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { format } from "date-fns";
import { Eye, ThumbsUp, ExternalLink } from "lucide-react";
import { getPosts, getArticles, type Post, type Article } from "../lib/api";

type Platform = "all" | "linkedin" | "substack";
type Status = "all" | "draft" | "queued" | "scheduled" | "published" | "failed" | "cancelled";

function StatusBadge({ status }: { status: string }) {
  const cls: Record<string, string> = {
    draft: "badge-draft", queued: "badge-queued", scheduled: "badge-scheduled",
    published: "badge-published", failed: "badge-failed", cancelled: "badge-cancelled",
  };
  return <span className={`badge ${cls[status] ?? "badge"}`}>{status}</span>;
}

export default function Library() {
  const [platform, setPlatform] = useState<Platform>("all");
  const [status, setStatus] = useState<Status>("all");

  const { data: postsData } = useQuery({
    queryKey: ["posts-all"],
    queryFn: () => getPosts({ limit: "200" }),
  });
  const { data: articlesData } = useQuery({
    queryKey: ["articles-all"],
    queryFn: () => getArticles({ limit: "200" }),
  });

  const posts = (postsData?.posts ?? []).filter((p) => {
    if (platform === "substack") return false;
    if (status !== "all" && p.status !== status) return false;
    return true;
  });

  const articles = (articlesData?.articles ?? []).filter((a) => {
    if (platform === "linkedin") return false;
    if (status !== "all" && a.status !== status) return false;
    return true;
  });

  const total = posts.length + articles.length;

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="text-xl font-semibold text-gray-100">Content Library</h1>
          <p className="text-sm text-gray-500 mt-0.5">{total} items</p>
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3 mb-6">
        <div className="flex gap-1 bg-gray-900 border border-gray-800 rounded-lg p-1">
          {(["all", "linkedin", "substack"] as Platform[]).map((p) => (
            <button
              key={p}
              onClick={() => setPlatform(p)}
              className={`px-3 py-1 rounded-md text-xs capitalize transition-colors ${
                platform === p ? "bg-gray-800 text-gray-100 font-medium" : "text-gray-500 hover:text-gray-300"
              }`}
            >
              {p}
            </button>
          ))}
        </div>
        <div className="flex gap-1 bg-gray-900 border border-gray-800 rounded-lg p-1">
          {(["all", "published", "queued", "scheduled", "draft", "failed"] as Status[]).map((s) => (
            <button
              key={s}
              onClick={() => setStatus(s)}
              className={`px-3 py-1 rounded-md text-xs capitalize transition-colors ${
                status === s ? "bg-gray-800 text-gray-100 font-medium" : "text-gray-500 hover:text-gray-300"
              }`}
            >
              {s}
            </button>
          ))}
        </div>
      </div>

      {/* Table */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-800">
              <th className="text-left px-4 py-3 text-xs text-gray-500 font-medium">Content</th>
              <th className="text-left px-4 py-3 text-xs text-gray-500 font-medium w-24">Platform</th>
              <th className="text-left px-4 py-3 text-xs text-gray-500 font-medium w-20">Voice</th>
              <th className="text-left px-4 py-3 text-xs text-gray-500 font-medium w-24">Date</th>
              <th className="text-left px-4 py-3 text-xs text-gray-500 font-medium w-28">Metrics</th>
              <th className="text-left px-4 py-3 text-xs text-gray-500 font-medium w-24">Status</th>
            </tr>
          </thead>
          <tbody>
            {posts.map((p) => <PostRow key={`li-${p.id}`} post={p} />)}
            {articles.map((a) => <ArticleRow key={`sub-${a.id}`} article={a} />)}
            {total === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-12 text-center text-gray-600">
                  No content found. Generate some from the Research page.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function PostRow({ post }: { post: Post }) {
  const m = post.metrics ?? {};
  return (
    <tr className="border-b border-gray-800/50 hover:bg-gray-800/20 transition-colors">
      <td className="px-4 py-3">
        <p className="text-gray-200 line-clamp-1 text-xs">{post.content.slice(0, 100)}</p>
        {post.is_manual && <span className="text-xs text-accent">manual</span>}
      </td>
      <td className="px-4 py-3">
        <span className="badge bg-blue-900/30 text-blue-400">LinkedIn</span>
      </td>
      <td className="px-4 py-3">
        <span className="text-xs text-gray-500 capitalize">{post.voice_style}</span>
      </td>
      <td className="px-4 py-3">
        <span className="text-xs text-gray-500">
          {post.published_at
            ? format(new Date(post.published_at), "MMM d")
            : post.scheduled_at
            ? format(new Date(post.scheduled_at), "MMM d")
            : "—"}
        </span>
      </td>
      <td className="px-4 py-3">
        {post.status === "published" ? (
          <div className="flex items-center gap-2 text-xs text-gray-500">
            <span className="flex items-center gap-0.5"><Eye className="w-3 h-3" />{m.impressions ?? 0}</span>
            <span className="flex items-center gap-0.5"><ThumbsUp className="w-3 h-3" />{m.likes ?? 0}</span>
          </div>
        ) : (
          <span className="text-xs text-gray-700">—</span>
        )}
      </td>
      <td className="px-4 py-3"><StatusBadge status={post.status} /></td>
    </tr>
  );
}

function ArticleRow({ article }: { article: Article }) {
  const m = article.metrics ?? {};
  return (
    <tr className="border-b border-gray-800/50 hover:bg-gray-800/20 transition-colors">
      <td className="px-4 py-3">
        <p className="text-gray-200 text-xs font-medium">{article.title}</p>
        {article.subtitle && <p className="text-xs text-gray-500 line-clamp-1">{article.subtitle}</p>}
      </td>
      <td className="px-4 py-3">
        <span className="badge bg-orange-900/30 text-orange-400">Substack</span>
      </td>
      <td className="px-4 py-3">
        <span className="text-xs text-gray-500 capitalize">{article.voice_style}</span>
      </td>
      <td className="px-4 py-3">
        <span className="text-xs text-gray-500">
          {article.published_at ? format(new Date(article.published_at), "MMM d") : "—"}
        </span>
      </td>
      <td className="px-4 py-3">
        <span className="text-xs text-gray-500">{m.opens ?? "—"} opens</span>
      </td>
      <td className="px-4 py-3">
        <div className="flex items-center gap-2">
          <StatusBadge status={article.status} />
          {article.substack_url && (
            <a href={article.substack_url} target="_blank" rel="noreferrer" className="text-gray-600 hover:text-accent">
              <ExternalLink className="w-3.5 h-3.5" />
            </a>
          )}
        </div>
      </td>
    </tr>
  );
}
