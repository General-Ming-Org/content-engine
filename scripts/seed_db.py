#!/usr/bin/env python3
"""Seed the database with sample research topics and a goal for local development."""
import asyncio
import sys
import uuid
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, "backend")

from sqlalchemy import select

from database import AsyncSessionLocal, Base, engine
from models.analytics import Goal
from models.research import ResearchTopic
from models.user import User


async def main():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as db:
        user = (
            await db.execute(select(User).where(User.is_active.is_(True)).order_by(User.created_at).limit(1))
        ).scalar_one_or_none()
        if user is None:
            print("No active user found. Sign up first, then run seed_db.py.")
            return

        topics = [
            ResearchTopic(
                id=uuid.uuid4(),
                user_id=user.id,
                title="eBPF-Based Observability: Replacing Traditional APM Agents",
                summary="eBPF enables kernel-level telemetry collection without process injection, "
                        "eliminating the 3-8% CPU overhead typical APM agents carry.",
                sources=[{
                    "url": "https://example.com/ebpf-observability",
                    "title": "eBPF Observability Deep Dive",
                    "content": "Sample content",
                    "synthesis": {
                        "key_facts": [
                            "eBPF agents use <1% CPU vs 3-8% for Java APM agents",
                            "Cilium Hubble provides L7 visibility without sidecar proxies",
                            "Requires Linux kernel 5.8+ for full CO-RE support",
                        ],
                        "why_it_matters": "Eliminates the performance tax of traditional observability",
                        "trade_offs": "Steep learning curve; kernel version requirements block some enterprise environments",
                        "suggested_voice": "analytical",
                        "confidence": 9,
                    }
                }],
                domain="sre_infra",
                relevance_score=0.92,
                status="new",
            ),
            ResearchTopic(
                id=uuid.uuid4(),
                user_id=user.id,
                title="LLM Inference at the Edge: Apple Silicon vs NVIDIA for On-Prem Deployment",
                summary="Apple M-series chips deliver 60-80 tokens/sec on 7B models at 15W, "
                        "making them viable alternatives to cloud inference for privacy-sensitive workloads.",
                sources=[{
                    "url": "https://example.com/edge-llm",
                    "title": "Edge LLM Benchmark Report",
                    "content": "Sample content",
                    "synthesis": {
                        "key_facts": [
                            "M3 Max: 78 tok/s on Llama 3.1 7B at 15W thermal envelope",
                            "A100 comparison: 800 tok/s but 400W + $3/hour cloud cost",
                            "llama.cpp Metal backend enables full GPU offload on macOS",
                        ],
                        "why_it_matters": "Private inference for regulated industries without cloud API costs",
                        "trade_offs": "Context window limited to available unified memory; 64GB max on M3 Ultra",
                        "suggested_voice": "opinionated",
                        "confidence": 8,
                    }
                }],
                domain="ai_ml",
                relevance_score=0.89,
                status="new",
            ),
            ResearchTopic(
                id=uuid.uuid4(),
                user_id=user.id,
                title="Apache Iceberg vs Delta Lake: The Table Format War in 2025",
                summary="Iceberg's multi-engine compatibility and Delta Lake's Databricks ecosystem lock-in "
                        "represent fundamentally different bets on the future of the lakehouse.",
                sources=[{
                    "url": "https://example.com/iceberg-delta",
                    "title": "Table Format Comparison 2025",
                    "content": "Sample content",
                    "synthesis": {
                        "key_facts": [
                            "Iceberg supports Spark, Flink, Trino, Hive, and Snowflake natively",
                            "Delta 3.0 introduced UniForm for cross-format compatibility",
                            "Iceberg partition evolution requires no data rewrite",
                        ],
                        "why_it_matters": "Your table format choice determines your query engine options for 5+ years",
                        "trade_offs": "Delta has better Spark optimizations; Iceberg has broader ecosystem support",
                        "suggested_voice": "analytical",
                        "confidence": 9,
                    }
                }],
                domain="data_eng",
                relevance_score=0.87,
                status="new",
            ),
        ]

        goals = [
            Goal(
                id=uuid.uuid4(),
                user_id=user.id,
                metric_name="linkedin_followers",
                target_value=1000,
                target_date=date.today() + timedelta(days=120),
                current_value=0,
                status="active",
            ),
            Goal(
                id=uuid.uuid4(),
                user_id=user.id,
                metric_name="avg_engagement_rate",
                target_value=3.0,
                target_date=date.today() + timedelta(days=180),
                current_value=0,
                status="active",
            ),
        ]

        for item in topics + goals:
            db.add(item)
        await db.commit()

    print(f"Seeded {len(topics)} research topics and {len(goals)} goals for user {user.email}.")


if __name__ == "__main__":
    asyncio.run(main())
