/** Centralized API client. All fetch calls go through here. */
import { getToken, clearToken, notifyAuthExpired } from "./auth";

const BASE = "/api";

/** Thrown by `request()` for any non-2xx response. Carries the HTTP status
 *  and the best human-readable message we could extract from the body. */
export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public detail?: unknown,
    public retryAfterSeconds?: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** FastAPI returns errors as { detail: string } for HTTPException and
 *  { detail: [{loc, msg, ...}] } for validation errors. Render both nicely. */
function extractMessage(body: unknown, status: number): string {
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === "string" && detail.trim()) return detail;
    if (Array.isArray(detail)) {
      const msgs = detail
        .map((d: any) => {
          const field =
            Array.isArray(d?.loc) && d.loc.length > 1 ? `${d.loc[d.loc.length - 1]}: ` : "";
          return `${field}${d?.msg ?? "Invalid value"}`;
        })
        .filter(Boolean);
      if (msgs.length) return msgs.join(" • ");
    }
  }
  // Fall back to status-code-specific defaults.
  switch (status) {
    case 400: return "That request couldn't be processed. Please double-check the inputs.";
    case 401: return "Your session has expired. Please sign in again.";
    case 403: return "You don't have permission to do that.";
    case 404: return "That resource wasn't found.";
    case 409: return "That conflicts with something that already exists.";
    case 429: return "Too many requests — please slow down and try again shortly.";
    case 500: case 502: case 503: case 504:
      return "Something went wrong on our end. Please try again in a moment.";
    default:
      return `Request failed (${status}).`;
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string> | undefined),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, { ...options, headers });
  } catch (err) {
    throw new ApiError(0, "Can't reach the server. Check your connection and try again.", err);
  }

  // Successful but no body.
  if (res.status === 204) return undefined as T;

  // Parse the body once. Some endpoints return text, most return JSON.
  let body: unknown;
  const ctype = res.headers.get("content-type") ?? "";
  if (ctype.includes("application/json")) {
    body = await res.json().catch(() => null);
  } else {
    body = await res.text().catch(() => null);
  }

  if (res.ok) return body as T;

  // 401 on a non-auth route means our token went stale → bounce to /login.
  // We deliberately don't redirect when the user is actively submitting a
  // login/signup form so the error can be shown inline.
  if (res.status === 401 && !path.startsWith("/auth/")) {
    clearToken();
    notifyAuthExpired();
  }

  const retryAfter = parseRetryAfter(res.headers.get("Retry-After"));
  throw new ApiError(res.status, extractMessage(body, res.status), body, retryAfter);
}

function parseRetryAfter(header: string | null): number | undefined {
  if (!header) return undefined;
  const n = parseInt(header, 10);
  if (!Number.isNaN(n) && n > 0) return n;
  const when = Date.parse(header);
  if (!Number.isNaN(when)) {
    const sec = Math.ceil((when - Date.now()) / 1000);
    return sec > 0 ? sec : undefined;
  }
  return undefined;
}

// ── Auth ──────────────────────────────────────────────────────────────────────
export interface AuthUser {
  id: string;
  email: string;
  name: string;
  role: "admin" | "user";
  is_active: boolean;
  email_verified: boolean;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_at: string;
  user: AuthUser;
}

export const login = (email: string, password: string) =>
  request<TokenResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });

export const signup = (
  email: string,
  password: string,
  password_confirm: string,
  name: string,
) =>
  request<TokenResponse>("/auth/signup", {
    method: "POST",
    body: JSON.stringify({ email, password, password_confirm, name }),
  });

export const getMe = () => request<AuthUser>("/auth/me");

export const verifyEmail = (token: string) =>
  request<AuthUser>("/auth/verify-email", {
    method: "POST",
    body: JSON.stringify({ token }),
  });

export const resendVerification = (email: string) =>
  request<{ detail: string }>("/auth/resend-verification", {
    method: "POST",
    body: JSON.stringify({ email }),
  });

export const changePassword = (current_password: string, new_password: string) =>
  request<void>("/auth/change-password", {
    method: "POST",
    body: JSON.stringify({ current_password, new_password }),
  });

// ── Users (admin) ─────────────────────────────────────────────────────────────
export const listUsers = () => request<AuthUser[]>("/users");
export const setUserRole = (id: string, role: "admin" | "user") =>
  request<AuthUser>(`/users/${id}/role`, { method: "PATCH", body: JSON.stringify({ role }) });
export const setUserActive = (id: string, is_active: boolean) =>
  request<{ id: string; is_active: boolean }>(`/users/${id}/active`, {
    method: "PATCH",
    body: JSON.stringify({ is_active }),
  });

// ── Credentials ───────────────────────────────────────────────────────────────
export const listCredentials = () => request<Record<string, any>>("/credentials");
export type LinkedInRedirectMode = "app" | "api";

export interface LinkedInRedirectOption {
  mode: LinkedInRedirectMode;
  label: string;
  uri: string;
}

export interface LinkedInAppStatus {
  configured: boolean;
  source: "user" | null;
  client_id: string | null;
  has_secret: boolean;
  redirect_uri: string;
  redirect_mode: LinkedInRedirectMode;
  redirect_options: LinkedInRedirectOption[];
}

export interface LinkedInStatus {
  configured: boolean;
  app_configured?: boolean;
  person_urn?: string | null;
  expires_at?: string | null;
}

export const linkedinAppStatus = () => request<LinkedInAppStatus>("/credentials/linkedin/app");
export const setLinkedinApp = (body: { client_id: string; client_secret?: string }) =>
  request<{ configured: boolean; client_id: string }>("/credentials/linkedin/app", {
    method: "PUT",
    body: JSON.stringify(body),
  });
export const deleteLinkedinApp = () =>
  request<void>("/credentials/linkedin/app", { method: "DELETE" });
export const setLinkedinRedirectMode = (mode: LinkedInRedirectMode) =>
  request<{
    redirect_mode: LinkedInRedirectMode;
    redirect_uri: string;
    redirect_options: LinkedInRedirectOption[];
  }>("/credentials/linkedin/app/redirect-mode", {
    method: "PUT",
    body: JSON.stringify({ mode }),
  });

export const linkedinStatus = () => request<LinkedInStatus>("/credentials/linkedin/status");
export const startLinkedinOAuth = () =>
  request<{ url: string; redirect_uri: string; scopes: string }>("/publish/linkedin/oauth-url");
export const deleteLinkedin = () => request<void>("/credentials/linkedin", { method: "DELETE" });

export const substackStatus = () => request<any>("/credentials/substack/status");
export const setSubstack = (creds: { email: string; password: string; publication_url: string }) =>
  request<any>("/credentials/substack", { method: "PUT", body: JSON.stringify(creds) });
export const deleteSubstack = () => request<void>("/credentials/substack", { method: "DELETE" });

export const getSmtpTo = () =>
  request<{
    configured: boolean;
    to_address: string | null;
    override: string | null;
    account_email: string;
    uses_account_email: boolean;
  }>("/credentials/smtp-to");
export const setSmtpTo = (to_address: string) =>
  request<{ to_address: string }>("/credentials/smtp-to", { method: "PUT", body: JSON.stringify({ to_address }) });

export const issueMcpToken = () =>
  request<{ token: string; warning: string }>("/credentials/mcp-token", { method: "POST" });
export const revokeMcpToken = () =>
  request<void>("/credentials/mcp-token", { method: "DELETE" });

// ── AI model selection ────────────────────────────────────────────────────────
export interface ModelCatalogEntry {
  id: string;
  label: string;
  provider: string;
  supports_caching: boolean;
  supports_mcp: boolean;
}

export interface AiModelsResponse {
  provider: string;
  model: string;
  model_id: string;
  configured: boolean;
  info: ModelCatalogEntry | null;
  catalog: ModelCatalogEntry[];
}

export const getAiModels = () => request<AiModelsResponse>("/ai/models");

// ── Health ────────────────────────────────────────────────────────────────────
export const getHealth = () => request<HealthStatus>("/health");

// ── Research ──────────────────────────────────────────────────────────────────
export const getTopics = (params?: Record<string, string>) =>
  request<{ topics: ResearchTopic[] }>(`/research/topics${params ? "?" + new URLSearchParams(params) : ""}`);
export const triggerResearch = () =>
  request<TaskResult>("/research/trigger", { method: "POST" });
export const getResearchSweepStatus = (taskId?: string) =>
  request<ResearchSweepStatusResponse>(
    `/research/sweep/status${taskId ? `?task_id=${encodeURIComponent(taskId)}` : ""}`,
  );
export const updateTopic = (id: string, data: Partial<ResearchTopic>) =>
  request<ResearchTopic>(`/research/topics/${id}`, { method: "PATCH", body: JSON.stringify(data) });

// ── Content ───────────────────────────────────────────────────────────────────
export const getCalendar = (view?: string) =>
  request<CalendarData>(`/content/calendar${view ? `?view=${view}` : ""}`);
export const getPosts = (params?: Record<string, string>) =>
  request<{ posts: Post[] }>(`/content/posts${params ? "?" + new URLSearchParams(params) : ""}`);
export const getPost = (id: string) => request<Post>(`/content/posts/${id}`);
export const createPost = (data: Partial<Post>) =>
  request<Post>("/content/posts", { method: "POST", body: JSON.stringify(data) });
export const updatePost = (id: string, data: Partial<Post>) =>
  request<Post>(`/content/posts/${id}`, { method: "PUT", body: JSON.stringify(data) });
export const cancelPost = (id: string) =>
  request<Post>(`/content/posts/${id}/cancel`, { method: "PATCH" });
export const approvePost = (id: string) =>
  request<TaskResult>(`/content/posts/${id}/approve`, { method: "PATCH" });
export const reschedulePost = (id: string, scheduledAt: string) =>
  request<Post>(`/content/posts/${id}/reschedule`, { method: "PATCH", body: JSON.stringify({ scheduled_at: scheduledAt }) });

export const getArticles = (params?: Record<string, string>) =>
  request<{ articles: Article[] }>(`/content/articles${params ? "?" + new URLSearchParams(params) : ""}`);
export const getArticle = (id: string) => request<Article>(`/content/articles/${id}`);
export const createArticle = (data: Partial<Article>) =>
  request<Article>("/content/articles", { method: "POST", body: JSON.stringify(data) });
export const updateArticle = (id: string, data: Partial<Article>) =>
  request<Article>(`/content/articles/${id}`, { method: "PUT", body: JSON.stringify(data) });
export const cancelArticle = (id: string) =>
  request<Article>(`/content/articles/${id}/cancel`, { method: "PATCH" });
export const approveArticle = (id: string) =>
  request<TaskResult>(`/content/articles/${id}/approve`, { method: "PATCH" });
export const generateContent = (researchTopicId: string) =>
  request<TaskResult>("/content/generate", { method: "POST", body: JSON.stringify({ research_topic_id: researchTopicId }) });
export const getContentGenerationStatus = (taskId?: string) =>
  request<ContentGenerationStatusResponse>(
    `/content/generate/status${taskId ? `?task_id=${encodeURIComponent(taskId)}` : ""}`,
  );

// ── Publishing ────────────────────────────────────────────────────────────────
export const publishLinkedIn = (postId: string) =>
  request<TaskResult>(`/publish/linkedin/${postId}`, { method: "POST" });
export const publishSubstack = (articleId: string) =>
  request<TaskResult>(`/publish/substack/${articleId}`, { method: "POST" });

// ── Engagement ────────────────────────────────────────────────────────────────
export const getEngagementLog = (params?: Record<string, string>) =>
  request<{ actions: EngagementAction[] }>(`/engagement/log${params ? "?" + new URLSearchParams(params) : ""}`);
export const triggerEngagement = () =>
  request<TaskResult>("/engagement/trigger", { method: "POST" });

// ── Analytics ─────────────────────────────────────────────────────────────────
export const getMetrics = (params?: Record<string, string>) =>
  request<{ snapshots: MetricSnapshot[] }>(`/analytics/metrics${params ? "?" + new URLSearchParams(params) : ""}`);
export const getCurrentMetrics = () =>
  request<Record<string, MetricSnapshot | null>>("/analytics/metrics/current");
export const getBenchmarks = () => request<BenchmarkData>("/analytics/benchmarks");
export const getReports = (params?: Record<string, string>) =>
  request<{ reports: StrategyReport[] }>(`/analytics/reports${params ? "?" + new URLSearchParams(params) : ""}`);
export const getLatestReport = (reportType?: string) =>
  request<StrategyReport>(`/analytics/reports/latest${reportType ? `?report_type=${reportType}` : ""}`);
export const triggerMetricCollection = () =>
  request<TaskResult>("/analytics/trigger-collection", { method: "POST" });
export const getGoals = () => request<{ goals: Goal[] }>("/analytics/goals");
export const createGoal = (data: Partial<Goal>) =>
  request<Goal>("/analytics/goals", { method: "POST", body: JSON.stringify(data) });
export const updateGoal = (id: string, data: Partial<Goal>) =>
  request<Goal>(`/analytics/goals/${id}`, { method: "PUT", body: JSON.stringify(data) });
export const deleteGoal = (id: string) =>
  request<void>(`/analytics/goals/${id}`, { method: "DELETE" });

// ── Notifications ─────────────────────────────────────────────────────────────
export const getNotifications = (unreadOnly?: boolean) =>
  request<{ notifications: Notification[] }>(`/notifications${unreadOnly ? "?unread_only=true" : ""}`);
export const markRead = (id: string) =>
  request<void>(`/notifications/${id}/read`, { method: "PATCH" });
export const markAllRead = () =>
  request<void>("/notifications/read-all", { method: "PATCH" });
export const getUnreadCount = () =>
  request<{ count: number }>("/notifications/unread-count");

// ── Scheduler ─────────────────────────────────────────────────────────────────
export const getSchedulerStatus = () =>
  request<{ tasks: SchedulerTask[] }>("/scheduler/status");
export const triggerTask = (taskName: string) =>
  request<TaskResult>(`/scheduler/trigger/${taskName}`, { method: "POST" });

// ── Settings ──────────────────────────────────────────────────────────────────
export const getSettings = () => request<Record<string, unknown>>("/settings");
export const updateSetting = (key: string, value: unknown) =>
  request<{ key: string; value: unknown }>(`/settings/${key}`, { method: "PUT", body: JSON.stringify(value) });

// ── Types ──────────────────────────────────────────────────────────────────────
export interface HealthStatus {
  status: "ok" | "degraded";
  services: Record<string, string>;
  version: string;
}

export interface ResearchTopic {
  id: string;
  title: string;
  summary: string | null;
  sources: unknown;
  domain: "ai_ml" | "software_eng" | "sre_infra" | "data_eng";
  relevance_score: number | null;
  status: "new" | "assigned" | "used" | "archived";
  created_at: string;
}

export interface Post {
  id: string;
  research_id: string | null;
  linked_article_id: string | null;
  content: string;
  hashtags: string[];
  voice_style: "opinionated" | "analytical" | "tutorial";
  status: "draft" | "queued" | "scheduled" | "published" | "failed" | "cancelled";
  queued_at: string | null;
  scheduled_at: string | null;
  published_at: string | null;
  linkedin_post_id: string | null;
  metrics: Record<string, number> | null;
  is_manual: boolean;
  created_at: string;
  updated_at: string;
}

export interface Article {
  id: string;
  research_id: string | null;
  linked_post_id: string | null;
  title: string;
  subtitle: string | null;
  body_markdown: string;
  voice_style: "opinionated" | "analytical" | "tutorial";
  status: "draft" | "queued" | "scheduled" | "published" | "failed" | "cancelled";
  queued_at: string | null;
  scheduled_at: string | null;
  published_at: string | null;
  substack_url: string | null;
  metrics: Record<string, number> | null;
  is_manual: boolean;
  created_at: string;
  updated_at: string;
}

export interface EngagementAction {
  id: string;
  post_id: string;
  original_comment: string;
  reply_text: string;
  status: "pending" | "posted" | "failed";
  posted_at: string | null;
  created_at: string;
}

export interface MetricSnapshot {
  id: string;
  snapshot_date: string;
  platform: "linkedin" | "substack";
  data: Record<string, number | string>;
  created_at: string;
}

export interface StrategyReport {
  id: string;
  report_type: "daily_summary" | "weekly_deep_dive";
  period_start: string;
  period_end: string;
  report_json: Record<string, unknown>;
  top_posts: unknown;
  benchmark_comparison: unknown;
  goal_progress: unknown;
  created_at: string;
}

export interface Goal {
  id: string;
  metric_name: string;
  target_value: number;
  target_date: string;
  current_value: number;
  status: "active" | "achieved" | "missed";
  progress_pct: number;
  created_at: string;
}

export interface Notification {
  id: string;
  type: "error" | "system";
  title: string;
  message: string;
  is_read: boolean;
  emailed: boolean;
  created_at: string;
}

export interface BenchmarkData {
  tech_content: Record<string, number>;
  substack: Record<string, number>;
  last_updated: string;
  sources: string[];
}

export interface CalendarData {
  posts: Post[];
  articles: Article[];
}

export interface SchedulerTask {
  name: string;
  task: string;
  schedule: string;
}

export interface TaskResult {
  status: string;
  task_id?: string;
}

export interface ContentGenerationProgress {
  task_id: string;
  topic_id?: string;
  topic_title?: string;
  status: "running" | "complete" | "failed";
  phase: "pairing" | "linkedin" | "article" | "saving" | "done";
  percent: number;
  message: string;
  result?: Record<string, unknown>;
}

export interface ContentGenerationStatusResponse {
  active: boolean;
  progress: ContentGenerationProgress | null;
}

export interface ResearchSweepProgress {
  task_id: string;
  status: "running" | "complete" | "failed" | "blocked";
  phase: "searching" | "enriching" | "done";
  current: number;
  total: number;
  percent: number;
  message: string;
  started_at?: string | null;
  finished_at?: string | null;
  result?: Record<string, unknown> | null;
}

export interface ResearchSweepStatusResponse {
  active: boolean;
  progress: ResearchSweepProgress | null;
}
