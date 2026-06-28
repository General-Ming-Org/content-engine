"""Rotating Tavily query lists — AI/ML-first with AI-adjacent supporting domains.

Style mix per domain (~4 practitioner / ~2 news / ~2 problem). Queries are
concrete and tool-specific so Tavily returns substantive engineering sources.
"""

DOMAIN_SWEEP_COUNTS: dict[str, int] = {
    "ai_ml": 3,
    "software_eng": 1,
    "sre_infra": 1,
    "data_eng": 1,
}

DOMAIN_QUERIES: dict[str, list[str]] = {
    "ai_ml": [
        # practitioner
        "LLM inference batching vLLM TGI production latency",
        "RAG retrieval augmented generation production architecture",
        "AI agents tool use function calling production reliability",
        "multimodal vision language models production deployment",
        "LLM fine-tuning LoRA QLoRA production benchmarks",
        "vector database embedding search HNSW performance tuning",
        # news
        "frontier LLM model release benchmark open weights",
        "recent AI safety alignment evaluation red teaming",
        # problem
        "RAG hallucination when retrieval fails production mitigation",
        "LLM cost optimization token usage production strategies",
        "when not to use fine-tuning vs RAG vs prompt engineering",
        "AI inference cold start scaling bottlenecks production",
    ],
    "software_eng": [
        # practitioner — AI application engineering
        "LLM application architecture patterns production backend",
        "LLM eval harness CI regression testing production",
        "structured output JSON schema reliability LLM API",
        "prompt versioning management production deployment",
        # news
        "LLM SDK framework release LangChain LlamaIndex updates",
        "AI coding assistant IDE integration production experience",
        # problem
        "LLM guardrails content filtering production false positives",
        "when to build vs buy LLM features production tradeoffs",
    ],
    "sre_infra": [
        # practitioner — AI infra / ops
        "Kubernetes GPU scheduling inference autoscaling production",
        "model serving SLO latency vLLM TensorRT production",
        "LLM inference cost FinOps GPU utilization optimization",
        "OpenTelemetry LLM trace observability production",
        # news
        "NVIDIA GPU inference hardware release datacenter AI",
        "managed model serving platform release comparison",
        # problem
        "LLM serving OOM GPU memory exhaustion production fixes",
        "inference queue saturation rate limiting production",
    ],
    "data_eng": [
        # practitioner — AI data plane
        "RAG chunking strategy embedding pipeline production",
        "vector database scaling Qdrant Pinecone Weaviate ops",
        "ML feature store online inference real-time serving",
        "eval dataset construction LLM benchmark quality",
        # news
        "embedding model release benchmark MTEB retrieval",
        "Iceberg Delta Lake ML training data lakehouse updates",
        # problem
        "embedding drift detection production monitoring ML",
        "RAG data quality stale documents retrieval degradation",
    ],
}
