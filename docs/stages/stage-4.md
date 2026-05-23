# Stage 4 — Keyword management UI + LLM recommendations

**Goal:** Replace the static `sources.json` keyword list with a user-managed list in SQLite. Position in the list becomes a weight that influences ranking. Add a screen to view, reorder, edit, delete, and add keywords, plus an LLM-driven "suggest more" action.

**Branch off:** main (after the Stage 3 close commit).

**Why now:** today every keyword is treated equally, and the list is config in `sources.json`. Yaniv sees too many irrelevant items because the keyword list does not reflect what he actually cares about right now. Moving control into the UI and giving each keyword a weight derived from its position lets him sharpen relevance without touching code.

**Provider context:** same as Stage 3 — Azure OpenAI, default deployment `gpt-4o`. The new LLM-based suggestion endpoint reuses `LLMUsageTracker` from the Stage 3 cost-tracking commit, so its cost is captured in the cumulative totals.

**Permissions note:** reads/searches auto-run; edits, deletes, and git commit/push still prompt. Same as Stage 3.

---

## Feature 1 — DB-backed keywords with discrete tier weights

- New SQLite table `keywords` with columns: `id`, `keyword` (unique, lowercased), `tier` (`LOW` / `MEDIUM` / `HIGH`), `created_at`, `updated_at`. Tier maps to a fixed weight via a module-level constant: `LOW = 0.3`, `MEDIUM = 0.6`, `HIGH = 1.0`.
- On startup (or `init-db`), if the table is empty, seed from `sources.json`'s current `keywords` list **all at MEDIUM**. Seeding is **one-shot** — once the user edits, re-running `init-db` does NOT overwrite.
- `Settings.keywords` becomes legacy-only (still loaded from `sources.json` as the seed source). Runtime reads the live list from `SQLiteStore.list_keywords()` / `list_keywords_for_matching()`.
- `matches_keywords` in `sources/base.py` keeps its boolean signature — tier does NOT gate inclusion at fetch time, only ranking. The adapter filter remains: any matching keyword (at any tier) passes.
- `ranking/scorer.py` replaces `keyword_score = min(hits, 5) * 0.45` with `keyword_score = min(sum(matched_tier_weights), 3.0)`. Cap of 3.0 keeps keywords on par with `source_weight` and below `recency_score` — influential but not dominant. A single HIGH match contributes 1.0; three HIGH matches saturate the cap.

## Feature 2 — CRUD + reorder UI at `/keywords`

- New page `/keywords` in the dashboard, linked from the top nav.
- Shows the list sorted server-side `HIGH → MEDIUM → LOW`, oldest-first within tier. Each row: keyword text, tier badge, created_at, tier-change dropdown (the "move to higher importance" control), delete button.
- "+ Add keyword" form at the top of the page: text input + tier select + add button.
- All ops via dedicated endpoints under `/api/keywords`:
  - `GET /api/keywords` → ordered list with tier + weight.
  - `POST /api/keywords` body `{keyword, tier}` → create. 409 on duplicate (case-insensitive); 400 on invalid tier.
  - `PATCH /api/keywords/{id}` body `{tier}` → change tier.
  - `DELETE /api/keywords/{id}` → remove.

## Feature 3 — LLM-driven keyword suggestions

- "Get suggestions" button on `/keywords`.
- Calls `POST /api/keywords/suggest`:
  - Inputs to the LLM: current keyword list (ordered) plus the Top 10 trends from the latest completed run (title + summary text).
  - Persona context: includes Yaniv's CTO / AI-architect angle, loaded from `prompts/linkedin_system_prompt.txt` so the model judges fit against his actual voice and topic interests.
  - Model: `azure/gpt-4o` (same plumbing as `summarize()`).
- Returns array of `{keyword, suggested_tier, reasoning}` — typically 5-8 suggestions. `suggested_tier` is one of `LOW` / `MEDIUM` / `HIGH`.
- UI shows them in an inline panel below the list; each row has "Add" (creates and inserts at bottom of list, then disappears from the suggestions panel).
- Uses the existing `LLMUsageTracker`, so the call's cost is captured in the cumulative totals shown in the Summarize panels and on article-detail pages.

---

## Out of scope (keep the stage focused)

- Smart Rank (full-article fetch over top 10) — Stage 3's deferred Feature 3, will become a separate stage if/when Yaniv wants it.
- Per-source weight edits — stay in `sources.json`.
- Source enable/disable toggle in the UI — stays in `sources.json`.
- Automatic LinkedIn publishing — that's the existing "later/optional" item, now Stage 5.

## Definition of Done

- `/keywords` page exists, lists current keywords sorted by tier, supports add, tier change, and delete.
- A new manual run reflects the tiered weighting: items matching HIGH keywords rank higher than items matching only LOW keywords (verifiable by examining `rank_score` and the evidence string in `/runs/{id}`).
- "Get suggestions" produces sensible LLM suggestions that match Yaniv's persona, each with a `suggested_tier` and a one-line reason. Clicking "Add" persists the new keyword at the suggested tier.
- All 15 existing tests still pass; new tests cover at minimum the CRUD endpoints and the weight computation.
- One-shot seeding behavior verified: editing keywords, then re-running `init-db`, does NOT overwrite the user's list.

## Approval ritual (per CLAUDE.md)

Same as Stage 3: reads/searches auto-run; edits and git ask. Show plans before each feature, three features → three commits, separate commit/push approval. When Stage 4 is done → Yaniv approves → update `PROGRESS.md` Stage 4 to `done` → ask separately about commit.
