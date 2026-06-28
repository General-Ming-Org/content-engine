# Legacy paths: search-as-substance design

The pipeline was refactored to mine **stances** from opinion-rich sources instead of
treating search snippets as article substance. These locations still assume the old model.
Confirm before removing — some are fallbacks, some are unused by the new sweep.

## Replaced in the new daily flow

| File | Symbol | Old assumption |
|------|--------|----------------|
| `queries.py` | `DOMAIN_QUERIES`, `DOMAIN_SWEEP_COUNTS` | **Removed** — hyper-specific vendor keyword soup as search substance |
| `searcher.py` | `sweep()` via `enrich_topic` | Search hit → neutral synthesis → topic |
| `stance_extractor.py` | `extract_stances_from_results` | **New** — opinions mined from snippets |
| `stance_gates.py` | `apply_stance_gates` | **New** — relevance + debatability axes |
| `scorer.py` | `store_stance` | **New** — persists stance-shaped topics |
| `linkedin.py` | `generate_post_from_stance` | **New** — argues extracted stance |
| `prompts.py` | `STANCE_EXTRACTION_PROMPT`, `STANCE_LINKEDIN_DRAFT_USER_PROMPT` | **New** |

## Still present — legacy substance path

| File | Symbol | Risk if removed now |
|------|--------|---------------------|
| `deep_dive.py` | `enrich_topic`, `synthesize_topic` | Manual research triggers; cache layer |
| `deep_dive.py` | `check_cache` | Vector dedup for old synthesis shape |
| `prompts.py` | `RESEARCH_SYNTHESIS_PROMPT` | Used by `deep_dive.synthesize_topic` |
| `scorer.py` | `score_and_store`, `_compute_score` | Scores `key_facts` / `confidence`, not debatability |
| `calendar.py` | `generate_for_topic` synthesis branch | Fallback when `sources[].stance` missing |
| `linkedin.py` | `generate_post` | Fallback drafting from `key_facts` / `trade_offs` |
| `substack.py` | `generate_article` | Same synthesis fields for long-form |
| `prompts.py` | `LINKEDIN_POST_USER_PROMPT` | Fact-driven post template |
| `prompts.py` | `PAIRING_DECISION_PROMPT` | Uses `key_facts_count` from old synthesis |

## Data shape mismatch (pre-existing)

`calendar.generate_for_topic` reads `topic.sources[0].synthesis`, but `score_and_store`
never wrote synthesis into Postgres `sources` — only Qdrant payload. Stance topics store
`sources[0].stance` explicitly.

## Skip-on-low-quality (load-bearing)

- `stance_gates.DEBATABILITY_MIN_SCORE` — no stance → `sweep` stores 0 topics
- `calendar._generate_for_user` — no qualifying topics → no generation that day
- No "always post something" fallback anywhere in the new path
