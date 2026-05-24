import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { format } from "date-fns";
import { Sparkles, Archive, ChevronDown, ChevronUp, Loader2 } from "lucide-react";
import { getTopics, updateTopic, type ResearchTopic } from "../lib/api";
import { useAuth } from "../lib/auth";
import { ResearchSweepProgressBar } from "../components/ResearchSweepProgress";
import { TaskProgressBar } from "../components/TaskProgressBar";
import { useResearchSweep } from "../hooks/useResearchSweep";
import { useContentGeneration } from "../hooks/useContentGeneration";

const DOMAIN_LABELS: Record<string, string> = {
  ai_ml: "AI/ML", software_eng: "Software Eng", sre_infra: "SRE/Infra", data_eng: "Data Eng",
};
const DOMAIN_COLORS: Record<string, string> = {
  ai_ml: "bg-purple-900/40 text-purple-400",
  software_eng: "bg-blue-900/40 text-blue-400",
  sre_infra: "bg-orange-900/40 text-orange-400",
  data_eng: "bg-teal-900/40 text-teal-400",
};
const VOICE_COLORS: Record<string, string> = {
  opinionated: "text-red-400", analytical: "text-blue-400", tutorial: "text-green-400",
};

export default function Research() {
  const qc = useQueryClient();
  const { isAdmin } = useAuth();
  const [domain, setDomain] = useState<string>("");
  const [expanded, setExpanded] = useState<string | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["topics", domain],
    queryFn: () => getTopics(domain ? { domain, status: "new" } : { status: "new" }),
  });

  const sweep = useResearchSweep({
    onComplete: () => qc.invalidateQueries({ queryKey: ["topics"] }),
  });

  const archiveMut = useMutation({
    mutationFn: (id: string) => updateTopic(id, { status: "archived" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["topics"] }),
  });

  const contentGen = useContentGeneration({
    onComplete: () => qc.invalidateQueries({ queryKey: ["topics"] }),
  });

  const topics = dedupeTopicsByTitle(data?.topics ?? []);

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="text-xl font-semibold text-gray-100">Research</h1>
          <p className="text-sm text-gray-500 mt-0.5">{topics.length} topics available</p>
        </div>
        {isAdmin ? (
          <button
            onClick={() => sweep.trigger()}
            disabled={sweep.isBusy}
            className="btn-primary"
          >
            {sweep.isBusy ? "Sweeping…" : "Run Research Sweep"}
          </button>
        ) : (
          <p className="text-xs text-gray-500" title="The shared research pool is refreshed by admins.">
            Sweeps run on a schedule.
          </p>
        )}
      </div>

      <ResearchSweepProgressBar progress={sweep.progress} visible={sweep.showProgressBar} />
      <TaskProgressBar
        progress={contentGen.progress}
        visible={contentGen.showProgressBar}
        hint={
          contentGen.timedOut
            ? "Generation took too long to report status — check Calendar and Library for new items, or try again."
            : "Generation failed — check Notifications. LinkedIn publish also requires OAuth in Settings."
        }
      />
      {contentGen.error && (
        <p className="text-sm text-red-400 mb-4" role="alert">
          {contentGen.error instanceof Error ? contentGen.error.message : "Content generation failed."}
        </p>
      )}

      {/* Domain filter */}
      <div className="flex gap-2 mb-6">
        {["", "ai_ml", "software_eng", "sre_infra", "data_eng"].map((d) => (
          <button
            key={d}
            onClick={() => setDomain(d)}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
              domain === d
                ? "bg-accent text-white"
                : "bg-gray-800 text-gray-400 hover:text-gray-100"
            }`}
          >
            {d ? DOMAIN_LABELS[d] : "All"}
          </button>
        ))}
      </div>

      {isLoading ? (
        <div className="space-y-3">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="h-28 bg-gray-900 rounded-xl animate-pulse" />
          ))}
        </div>
      ) : topics.length === 0 ? (
        <div className="text-center py-16">
          <p className="text-gray-500 mb-2">No research topics found.</p>
          <p className="text-sm text-gray-600">Run a research sweep to discover new topics.</p>
        </div>
      ) : (
        <div className="space-y-2">
          {topics.map((topic) => (
            <TopicCard
              key={topic.id}
              topic={topic}
              isExpanded={expanded === topic.id}
              onToggle={() => setExpanded(expanded === topic.id ? null : topic.id)}
              onArchive={() => archiveMut.mutate(topic.id)}
              onGenerate={() => contentGen.generate(topic.id)}
              isGenerating={contentGen.isGeneratingTopic(topic.id)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

/** Hide duplicate titles in the list until DB cleanup runs (keeps highest score). */
function dedupeTopicsByTitle(topics: ResearchTopic[]): ResearchTopic[] {
  const byKey = new Map<string, ResearchTopic>();
  for (const t of topics) {
    const key = t.title.trim().toLowerCase();
    const existing = byKey.get(key);
    if (!existing || (t.relevance_score ?? 0) > (existing.relevance_score ?? 0)) {
      byKey.set(key, t);
    }
  }
  return [...byKey.values()].sort(
    (a, b) => (b.relevance_score ?? 0) - (a.relevance_score ?? 0),
  );
}

function TopicCard({
  topic, isExpanded, onToggle, onArchive, onGenerate, isGenerating,
}: {
  topic: ResearchTopic;
  isExpanded: boolean;
  onToggle: () => void;
  onArchive: () => void;
  onGenerate: () => void;
  isGenerating: boolean;
}) {
  const synthesis = (topic.sources as any)?.[0]?.synthesis ?? {};

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
      <div
        className="flex items-start gap-4 p-4 cursor-pointer hover:bg-gray-800/40 transition-colors"
        onClick={onToggle}
      >
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className={`badge ${DOMAIN_COLORS[topic.domain]}`}>
              {DOMAIN_LABELS[topic.domain]}
            </span>
            {synthesis.suggested_voice && (
              <span className={`text-xs font-medium ${VOICE_COLORS[synthesis.suggested_voice]}`}>
                {synthesis.suggested_voice}
              </span>
            )}
            {topic.relevance_score != null && (
              <span className="text-xs text-gray-600 ml-auto">
                score {topic.relevance_score.toFixed(2)}
              </span>
            )}
          </div>
          <h3 className="text-sm font-medium text-gray-100 line-clamp-2">{topic.title}</h3>
          {!isExpanded && topic.summary && (
            <p className="text-xs text-gray-500 mt-1 line-clamp-1">{topic.summary}</p>
          )}
        </div>
        <div className="flex-shrink-0">
          {isExpanded ? <ChevronUp className="w-4 h-4 text-gray-500" /> : <ChevronDown className="w-4 h-4 text-gray-500" />}
        </div>
      </div>

      {isExpanded && (
        <div className="px-4 pb-4 border-t border-gray-800 pt-4 animate-fade-in">
          {topic.summary && (
            <p className="text-sm text-gray-300 mb-3">{topic.summary}</p>
          )}
          {synthesis.key_facts?.length > 0 && (
            <div className="mb-3">
              <p className="text-xs font-medium text-gray-500 mb-1.5">Key facts</p>
              <ul className="space-y-1">
                {synthesis.key_facts.map((f: string, i: number) => (
                  <li key={i} className="text-xs text-gray-400 flex gap-2">
                    <span className="text-accent mt-0.5">·</span>{f}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {synthesis.trade_offs && (
            <p className="text-xs text-gray-500 mb-3">
              <span className="text-gray-400 font-medium">Trade-offs: </span>
              {synthesis.trade_offs}
            </p>
          )}
          <div className="flex items-center gap-2 pt-2">
            <button
              onClick={(e) => {
                e.stopPropagation();
                onGenerate();
              }}
              disabled={isGenerating}
              className="flex items-center gap-1.5 btn-primary text-xs py-1.5 min-w-[148px] justify-center"
            >
              {isGenerating ? (
                <>
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  Generating…
                </>
              ) : (
                <>
                  <Sparkles className="w-3.5 h-3.5" />
                  Generate Content
                </>
              )}
            </button>
            <button
              onClick={onArchive}
              className="flex items-center gap-1.5 btn-ghost text-xs py-1.5"
            >
              <Archive className="w-3.5 h-3.5" />
              Archive
            </button>
            <span className="text-xs text-gray-600 ml-auto">
              {format(new Date(topic.created_at), "MMM d, HH:mm")}
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
