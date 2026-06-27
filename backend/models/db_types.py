"""Portable column types — JSON on SQLite (tests), native PG types in production."""
from sqlalchemy import JSON, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

JsonDocument = JSON().with_variant(JSONB, "postgresql")
StringList = JSON().with_variant(ARRAY(Text), "postgresql")
