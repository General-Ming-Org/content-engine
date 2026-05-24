"""Initial schema

Revision ID: 001
Revises:
Create Date: 2026-01-01 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enums
    op.execute("CREATE TYPE domain_enum AS ENUM ('ai_ml', 'software_eng', 'sre_infra', 'data_eng')")
    op.execute("CREATE TYPE research_status_enum AS ENUM ('new', 'assigned', 'used', 'archived')")
    op.execute("CREATE TYPE voice_style_enum AS ENUM ('opinionated', 'analytical', 'tutorial')")
    op.execute("CREATE TYPE post_status_enum AS ENUM ('draft', 'queued', 'scheduled', 'published', 'failed', 'cancelled')")
    op.execute("CREATE TYPE article_status_enum AS ENUM ('draft', 'queued', 'scheduled', 'published', 'failed', 'cancelled')")
    op.execute("CREATE TYPE engagement_status_enum AS ENUM ('pending', 'posted', 'failed')")
    op.execute("CREATE TYPE platform_enum AS ENUM ('linkedin', 'substack')")
    op.execute("CREATE TYPE report_type_enum AS ENUM ('daily_summary', 'weekly_deep_dive')")
    op.execute("CREATE TYPE goal_status_enum AS ENUM ('active', 'achieved', 'missed')")
    op.execute("CREATE TYPE notification_type_enum AS ENUM ('error', 'system')")

    # research_topics
    op.create_table(
        "research_topics",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("sources", postgresql.JSONB(), nullable=True),
        sa.Column("domain", postgresql.ENUM("ai_ml", "software_eng", "sre_infra", "data_eng", name="domain_enum", create_type=False), nullable=False),
        sa.Column("relevance_score", sa.Float(), nullable=True),
        sa.Column("status", postgresql.ENUM("new", "assigned", "used", "archived", name="research_status_enum", create_type=False), nullable=False, server_default="new"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    # articles (before posts, since posts has FK to articles)
    op.create_table(
        "articles",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("research_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("linked_post_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("subtitle", sa.Text(), nullable=True),
        sa.Column("body_markdown", sa.Text(), nullable=False),
        sa.Column("voice_style", postgresql.ENUM("opinionated", "analytical", "tutorial", name="voice_style_enum", create_type=False), nullable=False),
        sa.Column("status", postgresql.ENUM("draft", "queued", "scheduled", "published", "failed", "cancelled", name="article_status_enum", create_type=False), nullable=False, server_default="draft"),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("substack_url", sa.Text(), nullable=True),
        sa.Column("metrics", postgresql.JSONB(), nullable=True),
        sa.Column("is_manual", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["research_id"], ["research_topics.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )

    # posts
    op.create_table(
        "posts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("research_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("linked_article_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("hashtags", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("voice_style", postgresql.ENUM("opinionated", "analytical", "tutorial", name="voice_style_enum", create_type=False), nullable=False),
        sa.Column("status", postgresql.ENUM("draft", "queued", "scheduled", "published", "failed", "cancelled", name="post_status_enum", create_type=False), nullable=False, server_default="draft"),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("linkedin_post_id", sa.Text(), nullable=True),
        sa.Column("metrics", postgresql.JSONB(), nullable=True),
        sa.Column("is_manual", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["research_id"], ["research_topics.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["linked_article_id"], ["articles.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )

    # Add FK from articles.linked_post_id → posts.id (circular, added after posts table exists)
    op.create_foreign_key(
        "fk_articles_linked_post_id", "articles", "posts", ["linked_post_id"], ["id"],
        ondelete="SET NULL",
    )

    # engagement_actions
    op.create_table(
        "engagement_actions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("post_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("original_comment", sa.Text(), nullable=False),
        sa.Column("reply_text", sa.Text(), nullable=False),
        sa.Column("status", postgresql.ENUM("pending", "posted", "failed", name="engagement_status_enum", create_type=False), nullable=False, server_default="pending"),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["post_id"], ["posts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # metric_snapshots
    op.create_table(
        "metric_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("platform", postgresql.ENUM("linkedin", "substack", name="platform_enum", create_type=False), nullable=False),
        sa.Column("data", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_metric_snapshots_date_platform", "metric_snapshots", ["snapshot_date", "platform"])

    # strategy_reports
    op.create_table(
        "strategy_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("report_type", postgresql.ENUM("daily_summary", "weekly_deep_dive", name="report_type_enum", create_type=False), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("report_json", postgresql.JSONB(), nullable=False),
        sa.Column("top_posts", postgresql.JSONB(), nullable=True),
        sa.Column("benchmark_comparison", postgresql.JSONB(), nullable=True),
        sa.Column("goal_progress", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    # goals
    op.create_table(
        "goals",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("metric_name", sa.Text(), nullable=False),
        sa.Column("target_value", sa.Float(), nullable=False),
        sa.Column("target_date", sa.Date(), nullable=False),
        sa.Column("current_value", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("status", postgresql.ENUM("active", "achieved", "missed", name="goal_status_enum", create_type=False), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    # notifications
    op.create_table(
        "notifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("type", postgresql.ENUM("error", "system", name="notification_type_enum", create_type=False), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("emailed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_notifications_is_read", "notifications", ["is_read"])

    # user_settings
    op.create_table(
        "user_settings",
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("value", postgresql.JSONB(), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )

    # Seed default settings
    op.execute("""
        INSERT INTO user_settings (key, value) VALUES
        ('posting_schedule', '{"linkedin": {"days": ["tuesday", "wednesday", "thursday"], "time": "09:00", "timezone": "America/New_York"}, "substack": {"day": "saturday", "time": "09:00", "timezone": "America/New_York"}}'::jsonb),
        ('domain_weights', '{"ai_ml": 0.25, "software_eng": 0.25, "sre_infra": 0.25, "data_eng": 0.25}'::jsonb),
        ('email_digest', '{"morning_time": "07:00", "evening_time": "21:00", "timezone": "America/New_York", "enabled": true}'::jsonb),
        ('tone_preferences', '{"voice_rotation": ["opinionated", "analytical", "tutorial"], "emoji_max": 2, "hashtag_min": 3, "hashtag_max": 5}'::jsonb),
        ('circuit_breaker', '{"linkedin_paused_until": null, "pause_duration_minutes": 60}'::jsonb)
        ON CONFLICT (key) DO NOTHING
    """)


def downgrade() -> None:
    op.drop_table("user_settings")
    op.drop_index("ix_notifications_is_read", "notifications")
    op.drop_table("notifications")
    op.drop_table("goals")
    op.drop_table("strategy_reports")
    op.drop_index("ix_metric_snapshots_date_platform", "metric_snapshots")
    op.drop_table("metric_snapshots")
    op.drop_table("engagement_actions")
    op.drop_constraint("fk_articles_linked_post_id", "articles", type_="foreignkey")
    op.drop_table("posts")
    op.drop_table("articles")
    op.drop_table("research_topics")
    for enum in [
        "notification_type_enum", "goal_status_enum", "report_type_enum",
        "platform_enum", "engagement_status_enum", "article_status_enum",
        "post_status_enum", "voice_style_enum", "research_status_enum", "domain_enum",
    ]:
        op.execute(f"DROP TYPE IF EXISTS {enum}")
